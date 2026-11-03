"""Explicit fresh M3 inquiry demo seed/export; starts no server, Worker, or provider."""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from commerceops.adapters.commerce.mock import Fixture
from commerceops.application.commerce.readonly_inquiry_service_demo import fixture_domain
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.readonly_inquiry_config import InquiryDeployment
from commerceops.infrastructure.web_config import private_bytes

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/commerce/inventory-v1"


def guard(settings: DatabaseSettings, directory: Path, web_port: int) -> None:
    if (
        os.environ.get("COMMERCEOPS_MODE") != "m3-inquiry-demo"
        or not re.fullmatch(r"m3_inquiry_demo_[a-z0-9_]{1,40}", settings.name)
        or settings.runtime_password_file is None
    ):
        raise ValueError("NEW_INQUIRY_OWNED_DATABASE_REQUIRED")
    if (
        not directory.is_absolute()
        or ".." in directory.parts
        or directory.exists()
        or directory.is_symlink()
        or directory.parent.resolve() != directory.parent
        or not directory.parent.is_dir()
        or not 1024 <= web_port <= 65535
    ):
        raise ValueError("NEW_PRIVATE_DIRECTORY_REQUIRED")


def save(path: Path, body: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(body)


def export(directory: Path, organization: UUID, shop: UUID) -> dict[str, Any]:
    """Export only the fixed committed fixture and typed server-side deployment."""
    fixture = Fixture.load(FIXTURE)
    target = directory / "fixture"
    target.mkdir(mode=0o700)
    for name in ("datasets.json", "manifest.json", "goldens.json"):
        save(target / name, (FIXTURE / name).read_bytes())
    if Fixture.load(target) != fixture:
        raise ValueError("FIXTURE_COPY_MISMATCH")
    deployment = InquiryDeployment.model_validate_json(
        json.dumps(
            {
                "schema_version": "p6-inquiry-deployment-v1",
                "shop_id": str(shop),
                "fixture_directory": str(target),
                "fixture_case": "baseline",
                "enabled": True,
                "source_kind": "mock",
                "model_mode": "offline_stub",
                "model_requests_enabled": False,
                "external_sender_enabled": False,
            }
        )
    )
    path = directory / "inquiry-deployment.json"
    save(path, deployment.model_dump_json().encode())
    public = {
        "mode": "m3_inquiry_local_synthetic_only",
        "organization_id": str(organization),
        "shop_id": str(shop),
        "commerce_external_shop": fixture.source.shop_id,
        "web_config": str(directory / "configuration.json"),
        "inquiry_config": str(path),
        "model_mode": "offline_stub",
        "model_requests_enabled": False,
        "external_sender_enabled": False,
        "source_domain": fixture_domain(fixture).model_dump(mode="json"),
    }
    save(directory / "demo.json", (json.dumps(public, indent=2) + "\n").encode())
    return public


def seed(settings: DatabaseSettings, directory: Path, web_port: int = 3410) -> dict[str, Any]:
    guard(settings, directory, web_port)
    fixture = Fixture.load(FIXTURE)
    with connect(settings) as db:
        row = db.execute("SELECT count(*) AS n FROM business.organizations").fetchone()
        if row != {"n": 0}:
            raise ValueError("EMPTY_OWNED_DATABASE_REQUIRED")
    directory.mkdir(mode=0o700)
    runtime = settings.model_copy(
        update={
            "user": "commerceops_app",
            "password_file": settings.runtime_password_file,
        }
    )
    from tests.p3_support import initialize_p3

    data = initialize_p3(settings, runtime, directory)
    try:
        with connect(settings) as db:
            row = db.execute(
                """SELECT external_shop_key,timezone,currency FROM business.shops
                WHERE id=%s AND organization_id=%s AND adapter_kind='mock'
                AND environment IN ('test','mock')""",
                (data.inventory.data.shop, data.actor.organization_id),
            ).fetchone()
            if row != {
                "external_shop_key": fixture.source.shop_id,
                "timezone": fixture.source.timezone,
                "currency": fixture.source.currency,
            }:
                raise ValueError("DEMO_SOURCE_MAPPING_MISMATCH")
        # Only this invocation's newly generated private Web config is amended.
        config = json.loads(private_bytes(data.config_file))
        config["origins"] = ["http://127.0.0.1", f"http://127.0.0.1:{web_port}"]
        descriptor = os.open(data.config_file, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(config, stream)
        save(
            directory / "local-login.json",
            json.dumps(
                {
                    "login": data.login,
                    "password": data.password.get_secret_value(),
                }
            ).encode(),
        )
        return export(directory, data.actor.organization_id, data.inventory.data.shop)
    finally:
        data.client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed/export a new owned offline inquiry demo")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--web-port", type=int, default=3410)
    args = parser.parse_args()
    try:
        print(json.dumps(seed(DatabaseSettings(), args.directory, args.web_port)))
    except Exception:
        raise SystemExit("询单演示准备失败；保留本次新资源供核实，不自动重试") from None


if __name__ == "__main__":
    main()
