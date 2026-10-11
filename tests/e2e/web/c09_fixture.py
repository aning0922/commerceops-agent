"""C09 新自有 PG 的最小 Web 种子/只读核证；不启动 Worker/SDK/provider。"""

import asyncio
import hashlib
import json
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from commerceops.application.replenishment.security import password_hash
from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from psycopg import sql

from tests.e2e.web.live_origins import registered_origins
from tests.e2e.web.live_seed import save
from tests.p3_support import initialize_p3

ROOT = Path(__file__).resolve().parents[3]


def checked(directory: Path) -> None:
    window = json.loads((directory / "window.json").read_text())
    if (
        directory.is_symlink()
        or directory.stat().st_mode & 0o777 != 0o700
        or window["owner"] != "phase4-C09-Web"
        or window["owner_uid"] != os.getuid()
        or window["checkout"] != str(ROOT)
        or window["private_directory"] != str(directory)
        or window["status"] not in ("registered-before-start", "running")
        or not str(window["project"]).startswith("p4c09-n01-")
        or datetime.now(UTC) >= datetime.fromisoformat(window["stop_at_utc"])
    ):
        raise ValueError("current bounded C09 owned window required")
    registered_origins(directory)


def seed(directory: Path) -> None:
    web, _ = registered_origins(directory)
    settings = DatabaseSettings()
    migrate(settings)
    asyncio.run(setup_checkpointer(settings))
    grant_runtime(settings)
    app = settings.model_copy(
        update={"user": "commerceops_app", "password_file": settings.runtime_password_file}
    )
    f = initialize_p3(settings, app, directory)
    configuration = json.loads(f.config_file.read_text())
    configuration.update(origins=[web], config_version="p4-c09-owned-v1")
    save(f.config_file, configuration)
    accounts = {
        "operator": {
            "login": f.login,
            "password": f.password.get_secret_value(),
            "principal": str(f.actor.principal_id),
        }
    }
    shop_b = uuid4()
    with connect(settings) as db:
        db.execute(
            "UPDATE business.principals SET roles=ARRAY['operator'],"
            "auth_version=auth_version+1 WHERE id=%s",
            (f.actor.principal_id,),
        )
        db.execute(
            "DELETE FROM business.principal_role_shop_grants "
            "WHERE principal_id=%s AND role='approver'",
            (f.actor.principal_id,),
        )
        db.execute(
            "INSERT INTO business.shops(id,organization_id,adapter_kind,external_shop_key,"
            "timezone,currency,config_ref,environment) VALUES (%s,%s,'mock','c09-other',"
            "'Asia/Shanghai','CNY','c09-owned','test')",
            (shop_b, f.actor.organization_id),
        )
        db.execute(
            "INSERT INTO business.principal_shop_scopes VALUES (%s,%s,%s,true)",
            (f.actor.organization_id, shop_b, f.actor.principal_id),
        )
        db.execute(
            "INSERT INTO business.principal_role_shop_grants VALUES (%s,%s,%s,'operator',true)",
            (f.actor.organization_id, shop_b, f.actor.principal_id),
        )
        principal, identity = uuid4(), uuid4()
        login, password = "c09-" + uuid4().hex[:16], secrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO business.principals(id,organization_id,display_name,roles) "
            "VALUES (%s,%s,'自有测试管理员',ARRAY['admin'])",
            (principal, f.actor.organization_id),
        )
        db.execute(
            "INSERT INTO business.identities(id,organization_id,principal_id,provider,"
            "app_id,tenant_key,external_subject) VALUES (%s,%s,%s,'web',%s,%s,%s)",
            (
                identity,
                f.actor.organization_id,
                principal,
                f.inventory.data.app,
                f.inventory.data.tenant,
                login,
            ),
        )
        db.execute(
            "INSERT INTO business.web_credentials VALUES (%s,%s,%s,%s,%s,true)",
            (login, f.actor.organization_id, principal, identity, password_hash(password)),
        )
        accounts["admin"] = {"login": login, "password": password, "principal": str(principal)}
    save(directory / "web-accounts.json", accounts)
    save(directory / "web-facts.json", {"shop": str(f.inventory.data.shop), "shop_b": str(shop_b)})
    save(directory / "owner-settings.json", settings.model_dump(mode="json"))
    f.client.close()


def snapshot(directory: Path) -> dict[str, object]:
    settings = DatabaseSettings.model_validate_json((directory / "owner-settings.json").read_text())
    result: dict[str, object] = {}
    with connect(settings) as db:
        for row in db.execute(
            "SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN "
            "('business','checkpoints') ORDER BY schemaname,tablename"
        ).fetchall():
            if row["tablename"] in ("web_credentials", "web_sessions", "web_login_attempts"):
                continue
            rows = db.execute(
                sql.SQL(
                    "SELECT row_to_json(t)::text AS canonical FROM {}.{} t "
                    "ORDER BY row_to_json(t)::text"
                ).format(sql.Identifier(row["schemaname"]), sql.Identifier(row["tablename"]))
            ).fetchall()
            canonical = json.dumps(rows, sort_keys=True).encode()
            result[row["schemaname"] + "." + row["tablename"]] = {
                "count": len(rows),
                "sha256": hashlib.sha256(canonical).hexdigest(),
            }
    return result


def revoke(directory: Path) -> None:
    settings = DatabaseSettings.model_validate_json((directory / "owner-settings.json").read_text())
    account = json.loads((directory / "web-accounts.json").read_text())["operator"]
    with connect(settings) as db:
        db.execute(
            "SELECT 1 FROM business.principals WHERE id=%s FOR UPDATE", (account["principal"],)
        )
        db.execute(
            "UPDATE business.principals SET auth_version=auth_version+1 WHERE id=%s",
            (account["principal"],),
        )


def api(directory: Path) -> None:
    from commerceops.application.replenishment.nl_preflight import parse_preflight
    from commerceops.entrypoints.api import main
    from commerceops.entrypoints.replenishment_http import install_web
    from commerceops.entrypoints.web_openapi import export_web
    from commerceops.infrastructure.web_preflight import WebPreflightStore

    kinds = {
        parse_preflight: "application/replenishment/nl_preflight.py",
        WebPreflightStore: "infrastructure/web_preflight.py",
        install_web: "entrypoints/replenishment_http.py",
        export_web: "entrypoints/web_openapi.py",
    }
    hashes = {}
    for value, relative in kinds.items():
        filename = sys.modules[value.__module__].__file__
        assert filename
        actual = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        assert (
            actual
            == hashlib.sha256(
                (ROOT / "backend/src/commerceops" / relative).read_bytes()
            ).hexdigest()
        )
        hashes[relative] = actual
    save(
        directory / "api-imports.safe.json",
        {"pid": os.getpid(), "four_imports_match": True, "hashes": hashes},
    )
    main()


if __name__ == "__main__":
    try:
        target, action = Path(sys.argv[1]), sys.argv[2]
        checked(target)
        if action == "seed":
            seed(target)
        elif action == "snapshot":
            print(json.dumps(snapshot(target)))
        elif action == "revoke":
            revoke(target)
        elif action == "api":
            api(target)
        else:
            raise ValueError("closed C09 action required")
    except Exception as error:
        print(json.dumps({"stage": "C09 owned fixture", "category": type(error).__name__}))
        raise SystemExit(2) from None
