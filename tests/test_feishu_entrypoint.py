"""默认拒绝/脱敏与局部卡片输出；不执行外部操作。"""

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from commerceops.adapters.feishu.config import FeishuProbeSettings
from commerceops.entrypoints import feishu_probe
from pytest import MonkeyPatch as Patch

from tests.test_feishu_contracts import plan

pytestmark = pytest.mark.offline


def configure(monkeypatch: Patch) -> None:
    values = {
        "COMMERCEOPS_FEISHU_APP_ID": "probe-app",
        "COMMERCEOPS_FEISHU_TENANT_KEY": "probe-tenant",
        "COMMERCEOPS_FEISHU_BOT_OPEN_ID": "probe-bot",
        "COMMERCEOPS_FEISHU_ALLOWED_OPEN_IDS": '["probe-user-a"]',
        "COMMERCEOPS_FEISHU_ALLOWED_GROUP_CHAT_IDS": '["probe-group"]',
        "COMMERCEOPS_FEISHU_ORGANIZATION_ID": "00000000-0000-4000-8000-000000000001",
        "COMMERCEOPS_FEISHU_SHOP_ID": "00000000-0000-4000-8000-000000000002",
        "COMMERCEOPS_DB_HOST": "probe.invalid",
        "COMMERCEOPS_DB_NAME": "probe",
        "COMMERCEOPS_DB_USER": "commerceops_app",
        "COMMERCEOPS_DB_PASSWORD_FILE": "missing",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("COMMERCEOPS_FEISHU_EXTERNAL_READY", raising=False)


@pytest.mark.parametrize(
    "action", ["gateway", "send-card", "base-create", "base-reconcile", "base-update"]
)
def test_live_actions_default_block_before_client_or_db(action: str, monkeypatch: Patch) -> None:
    configure(monkeypatch)
    monkeypatch.setattr("sys.argv", ["feishu_probe", action])

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("blocked mode attempted network/DB")

    monkeypatch.setattr(feishu_probe, "live_client", forbidden)
    monkeypatch.setattr(feishu_probe, "connect", forbidden)
    with pytest.raises(SystemExit, match="blocked_external"):
        feishu_probe.main()


def test_invalid_configuration_does_not_echo_input(monkeypatch: Patch) -> None:
    configure(monkeypatch)
    monkeypatch.setenv("COMMERCEOPS_FEISHU_ALLOWED_OPEN_IDS", "CANARY_PRIVATE_INPUT")
    monkeypatch.setattr("sys.argv", ["feishu_probe", "verify-config"])
    with pytest.raises(SystemExit) as caught:
        feishu_probe.main()
    assert "CANARY_PRIVATE_INPUT" not in str(caught.value)


def test_dotenv_not_loaded(tmp_path: Path, monkeypatch: Patch) -> None:
    configure(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("COMMERCEOPS_FEISHU_EXTERNAL_READY=true\n")
    assert FeishuProbeSettings().external_ready is False


def test_card_output_only_ignored_runtime_and_private_mode(
    tmp_path: Path, monkeypatch: Patch
) -> None:
    monkeypatch.chdir(tmp_path)
    body = asdict(plan())
    body["expires_at"] = plan().expires_at.isoformat()
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(body))
    monkeypatch.setattr(
        "sys.argv",
        ["feishu_probe", "emit-card", "--plan-file", str(source), "--output", "tracked-card.json"],
    )
    with pytest.raises(SystemExit):
        feishu_probe.main()
    assert not (tmp_path / "tracked-card.json").exists()
    monkeypatch.setattr(
        "sys.argv",
        ["feishu_probe", "emit-card", "--plan-file", str(source), "--output", "runtime/card.json"],
    )
    feishu_probe.main()
    target = tmp_path / "runtime/card.json"
    assert target.stat().st_mode & 0o777 == 0o600
    assert json.loads(target.read_text())["schema"] == "2.0"
    with pytest.raises(SystemExit):
        feishu_probe.main()
