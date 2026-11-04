"""Offline namespace and private export checks. No seed/PG/service/browser execution."""

import json
import stat
from pathlib import Path
from uuid import uuid4

import pytest
from commerceops.adapters.commerce.mock import Fixture
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.readonly_inquiry_config import InquiryDeployment

from scripts import m3_inquiry_demo as demo

pytestmark = pytest.mark.offline


def settings(tmp_path: Path) -> DatabaseSettings:
    return DatabaseSettings(
        host="127.0.0.1",
        name="m3_inquiry_demo_owned",
        user="unused",
        password_file=tmp_path / "not-read-owner",
        runtime_password_file=tmp_path / "not-read-app",
    )


@pytest.mark.parametrize(
    "damage", ["mode", "database", "runtime", "existing", "relative", "port", "symlink"]
)
def test_scope_rejected_before_any_database_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    monkeypatch.setenv("COMMERCEOPS_MODE", "m3-inquiry-demo")
    value = settings(tmp_path)
    path = tmp_path.resolve() / "new"
    port = 3410
    if damage == "mode":
        monkeypatch.setenv("COMMERCEOPS_MODE", "test")
    elif damage == "database":
        value = value.model_copy(update={"name": "m3_daily_demo_old"})
    elif damage == "runtime":
        value = value.model_copy(update={"runtime_password_file": None})
    elif damage == "existing":
        path.mkdir()
    elif damage == "relative":
        path = Path("relative")
    elif damage == "port":
        port = 80
    else:
        path.symlink_to(tmp_path / "absent")

    def forbidden(*args: object) -> None:
        raise AssertionError("scope must fail before database connection")

    monkeypatch.setattr(demo, "connect", forbidden)
    with pytest.raises(ValueError):
        demo.seed(value, path, port)


def test_fixed_copy_and_typed_private_export_roundtrip(tmp_path: Path) -> None:
    directory = tmp_path.resolve() / "private"
    directory.mkdir(mode=0o700)
    organization, shop = uuid4(), uuid4()
    public = demo.export(directory, organization, shop)
    deployment = InquiryDeployment.load(directory / "inquiry-deployment.json")
    assert deployment.shop_id == shop and deployment.enabled
    assert deployment.model_mode == "offline_stub"
    assert not deployment.model_requests_enabled and not deployment.external_sender_enabled
    fixture = Fixture.load(deployment.fixture_directory)
    assert fixture == Fixture.load(demo.FIXTURE)
    assert fixture.source.shop_id == "demo" and fixture.source.timezone == "Asia/Shanghai"
    assert public["shop_id"] == str(shop) and public["commerce_external_shop"] == "demo"
    assert json.loads((directory / "demo.json").read_text()) == public
    for file in directory.rglob("*"):
        assert stat.S_IMODE(file.stat().st_mode) == (0o700 if file.is_dir() else 0o600)
    original = (directory / "inquiry-deployment.json").read_bytes()
    with pytest.raises(FileExistsError):
        demo.export(directory, organization, uuid4())
    assert (directory / "inquiry-deployment.json").read_bytes() == original
