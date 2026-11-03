"""Foreground API assembly only for Root's isolated V4 test container.

This is the real create_app/P3/V4 stack, not production main or a stub server.
No CLI host/config override, worker, proxy, owner connection or database setup.
"""

import json
import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from commerceops.entrypoints.api import create_app
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.v4_demo_sessions import DemoConfig
from commerceops.infrastructure.web_config import WebConfig, private_bytes
from fastapi import FastAPI

RUNTIME = Path("/run/v4_api")
FIXTURE = Path(__file__).resolve().parents[3] / "tests/fixtures/commerce/inventory-v1"


def load_owned_config() -> tuple[DemoConfig, WebConfig, int]:
    info = RUNTIME.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("OWNED_RUNTIME_DIRECTORY")
    if info.st_uid != os.geteuid() or any(k.startswith("COMMERCEOPS_DB_") for k in os.environ):
        raise ValueError("OWNED_RUNTIME_IDENTITY")
    if "COMMERCEOPS_HOST" in os.environ:
        raise ValueError("OWNED_ENTRY_HAS_NO_HOST_OVERRIDE")
    web_path, demo_path = RUNTIME / "web.json", RUNTIME / "demo.json"
    if os.environ.get("COMMERCEOPS_P3_CONFIG_FILE") != str(web_path) or os.environ.get(
        "COMMERCEOPS_V4_DEMO_CONFIG_FILE"
    ) != str(demo_path):
        raise ValueError("FIXED_OWNED_CONFIG_PATHS_REQUIRED")
    demo_file = json.loads(private_bytes(demo_path))
    web_file = json.loads(private_bytes(web_path))
    # Validate all path-bearing fields before original loaders may read secrets.
    if demo_file.get("web_config_file") != str(web_path):
        raise ValueError("FIXED_WEB_CONFIG_REQUIRED")
    if web_file.get("csrf_secret_file") != str(RUNTIME / "csrf-key") or web_file.get(
        "nonce_secret_file"
    ) != str(RUNTIME / "nonce-key"):
        raise ValueError("FIXED_RUNTIME_KEYS_REQUIRED")
    database = web_file["database"]
    if (
        database.get("host") != "postgres"
        or database.get("port", 5432) != 5432
        or database.get("user") != "commerceops_app"
        or database.get("password_file") != str(RUNTIME / "runtime-password")
        or database.get("runtime_password_file") is not None
        or not re.fullmatch(r"v4_demo_[a-z0-9_]{1,48}", database.get("name", ""))
        or web_file.get("commerce_sources") is not None
    ):
        raise ValueError("FIXED_NEW_RUNTIME_DATABASE_REQUIRED")
    web = WebConfig.from_file(web_path)
    demo = DemoConfig.load(demo_path)
    parsed = urlsplit(demo.api_origin)
    port_text = os.environ.get("COMMERCEOPS_PORT", "")
    if not re.fullmatch(r"[1-9][0-9]{3,4}", port_text):
        raise ValueError("ROOT_BOUND_PORT_REQUIRED")
    port = int(port_text)
    if (
        not 1024 <= port <= 65535
        or parsed.port != port
        or demo.api_origin != f"http://127.0.0.1:{port}"
        or web.transport_mode != "local_http"
        or demo.web != web
        or not demo.enabled
        or demo.allow_non_browser_get
        or demo.api_origin not in web.origins
    ):
        raise ValueError("OWNED_LOOPBACK_DEPLOYMENT_REQUIRED")
    return demo, web, port


def build_owned_app() -> tuple[FastAPI, int]:
    demo, web, port = load_owned_config()
    store = ReplenishmentStore(web, FIXTURE)
    return create_app(web_config=web, replenishment_store=store, v4_demo_config=demo), port


def main() -> None:
    try:
        app, port = build_owned_app()
    except Exception:
        raise SystemExit("OWNED_V4_API_CONFIGURATION_INVALID") from None
    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104 -- Root-authorized isolated container; host mapping stays loopback.
        port=port,
        log_level="warning",
        proxy_headers=False,
        access_log=False,
        workers=1,
        reload=False,
    )


if __name__ == "__main__":
    main()
