"""技术 smoke：无业务、模型或审批，不连接数据库/外部平台。"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import httpx
import pytest
from commerceops.entrypoints.api import create_app
from commerceops.infrastructure.config import Settings
from pydantic import ValidationError

pytestmark = pytest.mark.offline


def test_liveness_contract_only() -> None:
    async def request() -> None:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/live")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "service": "commerceops-api"}
            assert (await client.get("/tasks")).status_code == 404
            assert (await client.get("/openapi.json")).status_code == 404

    asyncio.run(request())


def test_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMMERCEOPS_PORT", "8123")
    assert Settings().port == 8123


@pytest.mark.parametrize(
    "key,value",
    [
        ("HOST", "0.0.0.0"),  # noqa: S104 - rejection case
        ("PORT", "0"),
        ("PORT", "65536"),
        ("LOG_LEVEL", "invalid"),
    ],
)
def test_invalid_startup_config_is_redacted(key: str, value: str) -> None:
    environment = {k: v for k, v in os.environ.items() if not k.startswith("COMMERCEOPS_")}
    environment[f"COMMERCEOPS_{key}"] = value
    process = subprocess.run(
        [sys.executable, "-m", "commerceops.entrypoints.api"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert process.returncode != 0
    assert "启动配置无效" in process.stderr
    assert "ValidationError" not in process.stderr
    assert f"input_value='{value}'" not in process.stderr


def test_dotenv_is_not_implicitly_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("COMMERCEOPS_PORT", raising=False)
    (tmp_path / ".env").write_text("COMMERCEOPS_PORT=9123\n")
    assert Settings().port == 8000
    with pytest.raises(ValidationError):
        Settings(port=0)


def test_installed_entrypoint_process() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = {k: v for k, v in os.environ.items() if not k.startswith("COMMERCEOPS_")}
    environment["COMMERCEOPS_PORT"] = str(port)
    environment["COMMERCEOPS_LOG_LEVEL"] = "error"
    command = str(Path(sys.executable).parent / "commerceops-api")
    process = subprocess.Popen(
        [command], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            assert process.poll() is None, "API 进程提前退出"
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health/live", timeout=0.5
                ) as response:  # noqa: S310 - fixed loopback
                    assert json.load(response) == {"status": "ok", "service": "commerceops-api"}
                break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.05)
        else:
            pytest.fail("API 未在 10 秒内响应 liveness")
    finally:
        process.terminate()
        process.communicate(timeout=5)
