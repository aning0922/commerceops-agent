"""Pure owned-entry assembly and boundary checks; no listener, Docker or PG."""

import asyncio
import json
import os
import secrets
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from commerceops.infrastructure.config import Settings
from pydantic import ValidationError

from . import owned_api

pytestmark = pytest.mark.offline
CONTAINER_BIND = "0.0.0.0"  # noqa: S104 -- assertion value, no listener in pure tests.


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "runtime"
    root.mkdir(mode=0o700)
    monkeypatch.setattr(owned_api, "RUNTIME", root)
    for key in list(os.environ):
        if key.startswith("COMMERCEOPS_DB_") or key == "COMMERCEOPS_HOST":
            monkeypatch.delenv(key)
    for name in ("runtime-password", "csrf-key", "nonce-key"):
        path = root / name
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    body: dict[str, Any] = {
        "database": {
            "host": "postgres",
            "port": 5432,
            "name": "v4_demo_owned_entry_test",
            "user": "commerceops_app",
            "password_file": str(root / "runtime-password"),
            "runtime_password_file": None,
        },
        "csrf_secret_file": str(root / "csrf-key"),
        "nonce_secret_file": str(root / "nonce-key"),
        "origins": ["http://127.0.0.1:18440", "http://127.0.0.1:13440"],
        "transport_mode": "local_http",
    }
    for name, value in (
        ("web.json", body),
        (
            "demo.json",
            {
                "schema_version": "v4-demo-deployment-v1",
                "web_config_file": str(root / "web.json"),
                "api_origin": "http://127.0.0.1:18440",
                "enabled": True,
                "allow_non_browser_get": False,
            },
        ),
    ):
        path = root / name
        path.write_text(json.dumps(value))
        path.chmod(0o600)
    monkeypatch.setenv("COMMERCEOPS_PORT", "18440")
    monkeypatch.setenv("COMMERCEOPS_P3_CONFIG_FILE", str(root / "web.json"))
    monkeypatch.setenv("COMMERCEOPS_V4_DEMO_CONFIG_FILE", str(root / "demo.json"))
    return root, body


def test_real_app_has_eight_v4_routes_and_original_web_schema(
    config: tuple[Path, dict[str, Any]],
) -> None:
    app, port = owned_api.build_owned_app()
    assert port == 18440
    assert len(app.state.v4_demo_openapi["paths"]) == 8
    assert any(path.startswith("/api/v1/") for path in app.openapi()["paths"])

    async def request() -> None:
        # Real ASGI stack, no StubStore or route.fulfill. Only the Origin boundary
        # and liveness are tested without PG; actual P3 cookie rejection needs PG.
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:18440"
        ) as client:
            denied = await client.get("/api/v4/demo/session")
            assert denied.status_code == 403
            assert denied.json()["error"]["code"] == "ORIGIN_DENIED"
            assert (await client.get("/health/live")).status_code == 200

    asyncio.run(request())


@pytest.mark.parametrize(
    "field,value",
    [
        ("user", "commerceops_owner"),
        ("name", "commerceops"),
        ("host", "old-database"),
        ("password_file", "/old/runtime/private"),
        ("runtime_password_file", "/old/owner"),
    ],
)
def test_nonowned_database_or_secret_path_refused_before_loading(
    config: tuple[Path, dict[str, Any]],
    field: str,
    value: str,
) -> None:
    root, body = config
    body["database"][field] = value
    (root / "web.json").write_text(json.dumps(body))
    with pytest.raises(ValueError):
        owned_api.load_owned_config()


@pytest.mark.parametrize(
    "variable,value",
    [
        ("COMMERCEOPS_HOST", CONTAINER_BIND),
        ("COMMERCEOPS_DB_USER", "commerceops_owner"),
        ("COMMERCEOPS_PORT", "18441"),
        ("COMMERCEOPS_P3_CONFIG_FILE", "/old/web.json"),
    ],
)
def test_host_override_owner_env_port_mismatch_or_old_config_refused(
    config: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
) -> None:
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError):
        owned_api.load_owned_config()


def test_foreground_binding_is_fixed_to_owned_container(
    config: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    owned_api.main()
    assert calls == [
        dict(
            host=CONTAINER_BIND,
            port=18440,
            log_level="warning",
            proxy_headers=False,
            access_log=False,
            workers=1,
            reload=False,
        )
    ]


def test_old_settings_still_rejects_container_wildcard() -> None:
    with pytest.raises(ValidationError):
        Settings(host=CONTAINER_BIND)


def test_bad_configuration_has_fixed_safe_exit(
    config: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMMERCEOPS_PORT", "SYNTHETIC_DO_NOT_ECHO")
    with pytest.raises(SystemExit) as stopped:
        owned_api.main()
    assert str(stopped.value) == "OWNED_V4_API_CONFIGURATION_INVALID"


@pytest.mark.parametrize("unsafe", ["symlink", "0644"])
def test_runtime_password_file_guard_rejects_without_repair_or_listen(
    config: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    unsafe: str,
) -> None:
    root, _ = config
    path = root / "runtime-password"
    if unsafe == "symlink":
        outside = root.parent / "outside-synthetic-file"
        outside.write_text(secrets.token_urlsafe(48))
        outside.chmod(0o600)
        path.unlink()
        path.symlink_to(outside)
    else:
        path.chmod(0o644)
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: pytest.fail("must not listen"))
    with pytest.raises((ValueError, OSError)):
        owned_api.load_owned_config()
    with pytest.raises(SystemExit) as stopped:
        owned_api.main()
    assert str(stopped.value) == "OWNED_V4_API_CONFIGURATION_INVALID"
    if unsafe == "symlink":
        assert path.is_symlink()  # Entry never removes/replaces unknown mounts.
    else:
        assert path.stat().st_mode & 0o777 == 0o644  # Entry never chmods it.


def test_legal_runtime_password_0600_current_uid_still_loads(
    config: tuple[Path, dict[str, Any]],
) -> None:
    root, _ = config
    path = root / "runtime-password"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.stat().st_uid == os.geteuid()
    demo, web, port = owned_api.load_owned_config()
    assert demo.enabled and port == 18440
    assert web.database.password_file == path
    assert web.database.password().get_secret_value() == path.read_text().strip()
