"""仅新owned父子进程测试：复用原Fake HTTP，SQL/Factory/ledger/退出均原生。"""

import hashlib
import importlib.util
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from commerceops.adapters.feishu.business_config import BusinessSettings

from scripts.p4_acceptance import bound_bytes, write_private
from tests.p3_support import P3Fixture
from tests.p4_acceptance_support import FakeHTTPTransport

MODULES = (
    "commerceops.entrypoints.feishu_business",
    "commerceops.entrypoints.feishu_worker_child",
    "commerceops.infrastructure.feishu_read_reply",
    "commerceops.infrastructure.feishu_f02_runtime",
    "commerceops.infrastructure.feishu_sdk_ledger",
    "commerceops.infrastructure.worker_lock",
    "commerceops.application.feishu_business.history",
    "commerceops.adapters.feishu.history",
    "commerceops.infrastructure.feishu_history",
    "commerceops.infrastructure.feishu_business",
    "tests.p4_parent_support",
    "tests.p4_queued_transport",
    "tests.p4_acceptance_support",
    "scripts.p4_acceptance",
)


def source_files() -> dict[str, dict[str, str]]:
    result = {}
    for name in MODULES:
        spec = importlib.util.find_spec(name)
        assert spec and spec.origin
        path = Path(spec.origin).resolve()
        result[name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


_installation: Any = None


def install_owned_HTTP() -> None:
    """sitecustomize唯一行为：严格新owned绑定后安装底层HTTP替身；无PG写/读。"""
    global _installation
    request = json.loads(bound_bytes(Path(os.environ["P4_OWNED_PARENT_HTTP"]), private=True))
    settings = BusinessSettings.model_validate_json(
        bound_bytes(Path(request["business_file"]), private=True)
    )
    web = json.loads(bound_bytes(settings.web_config_file, private=True))
    directory = Path(request["directory"])
    assert web["database"]["name"].startswith(("p3_a01_", "p4_acceptance_"))
    assert web["database"]["user"] == "commerceops_app"
    assert settings.app_secret_file.parent == directory
    material_name = "owned-app-material"
    assert settings.app_secret_file.name == material_name
    assert source_files() == request["source_files"]
    write_private(
        directory / (str(os.getpid()) + ".source.safe.json"),
        {"PID": os.getpid(), "source_files": source_files(), "all_verified": True},
    )

    class HTTP(FakeHTTPTransport):
        async def request(self, method: str, url: str, **kwargs: Any) -> Any:
            is_im = urlsplit(url).path == "/open-apis/im/v1/messages" and method == "POST"
            # 不采集认证正文或token；IM只含这个新owned样例的数据。
            if is_im:
                write_private(
                    directory / ("im-" + secrets.token_hex(6) + ".private.json"), kwargs["json"]
                )
                if self.state().get("behavior") == "im_timeout":
                    raise httpx.ReadTimeout("owned HTTP ACK unknown")
            return await super().request(method, url, **kwargs)

    _installation = HTTP(Path(request["external_records"]), settings).installed()
    _installation.__enter__()


@dataclass(frozen=True)
class ParentInputs:
    directory: Path
    business: Path
    disabled_window: Path
    active_window: Path
    mode: str
    environment: dict[str, str]

    def bind_window(self, template: dict[str, Any]) -> None:
        assert template["enabled"] is False
        write_private(self.disabled_window, template)
        activated = json.loads(bound_bytes(self.disabled_window, private=True))
        activated["enabled"] = True
        write_private(self.active_window, activated)
        write_private(
            self.directory / "input-mapping.safe.json",
            {
                "mode": self.mode,
                "disabled_window_sha256": hashlib.sha256(
                    self.disabled_window.read_bytes()
                ).hexdigest(),
                "active_window_sha256": hashlib.sha256(self.active_window.read_bytes()).hexdigest(),
                "changed_fields": ["enabled"],
                "source_files": source_files(),
                "SQL_SDK_lease_and_parent_not_replaced": True,
                "Fake_scope": "bottom HTTP only",
            },
        )

    def run(self, label: str, *, disabled: bool = False) -> tuple[int, dict[str, Any]]:
        window = self.disabled_window if disabled else self.active_window
        argv = [
            sys.executable,
            "-m",
            "commerceops.entrypoints.feishu_business",
            "worker",
            "--config",
            str(self.business),
            "--window-file",
            str(window),
            "--worker-mode",
            self.mode,
            "--live",
        ]
        write_private(
            self.directory / (label + ".command.json"), {"argv": argv, "cwd": str(Path.cwd())}
        )
        path = self.directory / (label + ".private.log")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            child = subprocess.Popen(
                argv,
                env=self.environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            write_private(self.directory / (label + ".spawn.safe.json"), {"PID": child.pid})
            try:
                code = child.wait(timeout=45)
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait(timeout=5)
        result: dict[str, Any] = {}
        for line in path.read_bytes().splitlines():
            try:
                body = json.loads(line)
            except ValueError:
                continue
            if isinstance(body, dict) and "official_summary" in body:
                result = body
        write_private(
            self.directory / (label + ".exit.safe.json"),
            {
                "CLI_exit": code,
                "parent_PID": child.pid,
                "parent_reaped": child.poll() is not None,
                "result": result,
            },
        )
        return code, result


def prepare_parent(
    f: P3Fixture, template: dict[str, Any] | None, *, mode: str, behavior: str = "normal"
) -> ParentInputs:
    assert mode in ("read_reply", "f02_clarification", "history_recovery")
    assert template is None or template["enabled"] is False
    directory = f.private / "native-parent"
    directory.mkdir(mode=0o700)
    material = directory / "owned-app-material"
    fd = os.open(material, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(secrets.token_urlsafe(32))
    settings = BusinessSettings(
        schema_version="p4-v1",
        organization_id=f.actor.organization_id,
        shop_id=f.inventory.data.shop,
        app_id=f.inventory.data.app,
        tenant_key=f.inventory.data.tenant,
        bot_open_id="synthetic-bot",
        allowed_open_ids=frozenset({"p4-synthetic-user"}),
        allowed_group_chat_ids=frozenset({"p4-synthetic-chat"}),
        app_secret_file=material,
        web_config_file=f.config_file,
        base_target_key="unused-read-only",
        base_app_token_file=directory / "never-read-base-material",
        base_table_name="unused-read-only",
        f02_enabled=mode == "f02_clarification",
    )
    business = directory / "business.json"
    disabled, active = directory / "window.disabled.json", directory / "window.active.json"
    write_private(business, settings.model_dump(mode="json"))
    state = directory / "external-records.json"
    write_private(state, {"behavior": behavior, "rows": []})
    request = directory / "HTTP-input.json"
    write_private(
        request,
        {
            "directory": str(directory),
            "business_file": str(business),
            "external_records": str(state),
            "source_files": source_files(),
        },
    )
    bootstrap = directory / "bootstrap"
    bootstrap.mkdir(mode=0o700)
    write_private_code = bootstrap / "sitecustomize.py"
    fd = os.open(write_private_code, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(
            "import os\ntry:\n"
            " from tests.p4_parent_support import install_owned_HTTP\n"
            " install_owned_HTTP()\nexcept BaseException:\n os._exit(78)\n"
        )
    env = os.environ.copy()
    env.update(
        COMMERCEOPS_MODE="p4-controlled-test",
        P4_OWNED_PARENT_HTTP=str(request),
        PYTHONPATH=os.pathsep.join(
            [
                str(bootstrap),
                str(Path(__file__).resolve().parents[1]),
            ]
        ),
    )
    inputs = ParentInputs(directory, business, disabled, active, mode, env)
    if template is not None:
        inputs.bind_window(template)
    return inputs


@contextmanager
def native_gateway(f: P3Fixture, inputs: ParentInputs, window: dict[str, Any]) -> Iterator[None]:
    """复用现有无WS Gateway helper，真实app claim/PID/锁及终止；不造audit。"""
    import asyncio

    from commerceops.entrypoints.feishu_business import confirm_gateway_child

    from tests.p4_acceptance_support import reference

    directory = inputs.directory
    window_file, request = directory / "gateway.json", directory / "gateway-input.json"
    ready = directory / "gateway-ready.safe.json"
    write_private(window_file, window)
    write_private(
        request,
        {
            "transport": "synthetic",
            "private_refs": {
                "business": reference(inputs.business),
                "window": reference(window_file),
                "web_config": reference(f.config_file),
            },
            "ready_file": str(ready),
        },
    )
    argv = [
        sys.executable,
        "-c",
        "import json,sys\nfrom scripts.p4_acceptance import gateway_stage\n"
        "with open(sys.argv[1]) as f:\n request=json.load(f)\n"
        "print(json.dumps(gateway_stage(request)))\n",
        str(request),
    ]
    # This is the existing helper, not the WS product parent; provenance remains synthetic.
    write_private(directory / "gateway.command.json", {"argv": argv})
    fd = os.open(directory / "gateway.private.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        child = subprocess.Popen(
            argv, env=inputs.environment, stdout=stream, stderr=subprocess.STDOUT
        )
        try:
            end = time.monotonic() + 15
            while not ready.exists():
                assert child.poll() is None and time.monotonic() < end
                time.sleep(0.02)
            yield
        finally:
            if child.poll() is None:
                child.terminate()
            try:
                code = child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                code = child.wait(timeout=5)
            assert code == 0
            from uuid import UUID

            asyncio.run(
                confirm_gateway_child(
                    f.config, f.actor.organization_id, UUID(window["window_id"]), child.pid, code
                )
            )
            write_private(
                directory / "gateway.exit.safe.json",
                {"exit": code, "reaped": True, "termination_confirmed": True},
            )
