"""B02专用自有库准备；复用已审A01预置/Worker，秘密仅600文件。"""

import asyncio
import json
import secrets
import sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

from commerceops.adapters.commerce.mock import Fixture, MockCommerce
from commerceops.application.commerce.collection import InventoryCollector
from commerceops.application.replenishment.security import password_hash
from commerceops.domain.commerce_values import facts_hash, sku_key, stock_pool_key
from commerceops.entrypoints.api import create_app
from commerceops.entrypoints.database import grant_runtime, migrate, setup_checkpointer
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from fastapi.testclient import TestClient

from tests.inventory_support import DIRECTORY
from tests.p3_support import initialize_p3, run_graphs


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, default=str))
    path.chmod(0o600)


def main(directory: Path) -> None:
    settings = DatabaseSettings()
    migrate(settings)
    asyncio.run(setup_checkpointer(settings))
    grant_runtime(settings)
    app = settings.model_copy(
        update={"user": "commerceops_app", "password_file": settings.runtime_password_file}
    )
    f = initialize_p3(settings, app, directory)
    configuration = json.loads(f.config_file.read_text())
    configuration.update(
        origins=["http://127.0.0.1", "http://127.0.0.1:3460"],
        config_version="p3b02-owned-v1",
        approval_ttl_seconds=1800,
        revalidation_max_age_seconds=450,
        recovery_scan_seconds=10,
    )
    save(f.config_file, configuration)
    f.config = replace(
        f.config,
        origins=tuple(configuration["origins"]),
        config_version=configuration["config_version"],
        approval_ttl_seconds=1800,
        revalidation_max_age_seconds=450,
        recovery_scan_seconds=10,
    )
    f.store = ReplenishmentStore(f.config, DIRECTORY)
    f.client.close()
    f.client = TestClient(
        create_app(web_config=f.config, replenishment_store=f.store), base_url="http://127.0.0.1"
    )
    shop_b = uuid4()
    accounts = {}
    with connect(settings) as db:
        db.execute(
            "SELECT 1 FROM business.principals WHERE id=%s FOR UPDATE", (f.actor.principal_id,)
        )
        db.execute(
            "UPDATE business.principals SET roles=ARRAY['operator'], "
            "display_name='自有测试运营',auth_version=auth_version+1 WHERE id=%s",
            (f.actor.principal_id,),
        )
        db.execute(
            "DELETE FROM business.principal_role_shop_grants WHERE principal_id=%s AND "
            "role='approver'",
            (f.actor.principal_id,),
        )
        db.execute(
            "INSERT INTO "
            "business.shops(id,organization_id,adapter_kind,external_shop_key,timezon"
            "e,currency,config_ref,environment) VALUES (%s,%s,'mock','owned-b','Asia/"
            "Shanghai','CNY','b02-owned','test')",
            (shop_b, f.actor.organization_id),
        )
        accounts["operator"] = {
            "login": f.login,
            "password": f.password.get_secret_value(),
            "principal": str(f.actor.principal_id),
        }
        for role, roles, grants in [
            ("approver", ["approver"], [("approver", f.inventory.data.shop)]),
            ("admin", ["admin"], [("admin", f.inventory.data.shop)]),
            (
                "dual",
                ["operator", "approver"],
                [("operator", f.inventory.data.shop), ("approver", shop_b)],
            ),
            ("foreign", ["operator"], [("operator", f.inventory.data.shop)]),
        ]:
            principal, identity = uuid4(), uuid4()
            login, password = "b-" + uuid4().hex[:16], secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO business.principals(id,organization_id,display_name,roles) VALUES "
                "(%s,%s,%s,%s)",
                (principal, f.actor.organization_id, "自有测试" + role, roles),
            )
            db.execute(
                "INSERT INTO "
                "business.identities(id,organization_id,principal_id,provider,app_id,tena"
                "nt_key,external_subject) VALUES (%s,%s,%s,'web',%s,%s,%s)",
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
            for shop in set(shop for _, shop in grants):
                db.execute(
                    "INSERT INTO business.principal_shop_scopes VALUES (%s,%s,%s,true)",
                    (f.actor.organization_id, shop, principal),
                )
            for grant, shop in grants:
                db.execute(
                    "INSERT INTO business.principal_role_shop_grants VALUES (%s,%s,%s,%s,true)",
                    (f.actor.organization_id, shop, principal, grant),
                )
            accounts[role] = {"login": login, "password": password, "principal": str(principal)}
    f.relogin()
    receipts = []
    # 11 real T1 pairs => 22 public P2/P3 records for scoped pagination. No UI writes.
    for _ in range(10):
        receipts.append(f.create(f.new_cycle()))
    baseline = Fixture.load(DIRECTORY)
    provenance = baseline.source.provenance.model_copy(
        update={
            "fixture_version": "p3b02-owned-20",
            "raw_hash": facts_hash({"controlled_fixture": "p3b02-owned-20"}),
        }
    )
    source = baseline.source.model_copy(update={"provenance": provenance})
    products, orders, inventories = [], [], []
    for n in range(20):
        product_id = "b02-" + str(n)
        key = sku_key(source.shop_id, product_id, None)
        pool = stock_pool_key(source.shop_id, product_id)
        products.append(
            baseline.products[0].model_copy(
                update={
                    "product_id": product_id,
                    "sku_key": key,
                    "stock_pool_key": pool,
                    "source": provenance,
                    "sku_label": "完整披露中文商品名称用于验证窄屏换行与未知在途风险" + str(n),
                }
            )
        )
        orders.append(
            baseline.orders[0].model_copy(
                update={"order_id": "b02-order-" + str(n), "sku_key": key, "source": provenance}
            )
        )
        inventories.append(
            baseline.inventories[0].model_copy(
                update={
                    "sku_key": key,
                    "stock_pool_key": pool,
                    "source": provenance,
                    "inbound_units": None if n == 19 else baseline.inventories[0].inbound_units,
                    "inbound_quality": "unknown" if n == 19 else "reliable",
                    "inbound_reason": "UNKNOWN_INBOUND" if n == 19 else None,
                }
            )
        )
    controlled = replace(
        baseline,
        source=source,
        products=tuple(products),
        orders=tuple(orders),
        inventories=tuple(inventories),
    )
    collector = InventoryCollector(MockCommerce(controlled), source, baseline.now)
    receipt = f.create(f.new_cycle())
    receipts.append(receipt)
    asyncio.run(run_graphs(f, UUID(receipt["task_id"]), factory=lambda request: collector))
    with connect(settings) as db:
        plan = db.execute(
            "SELECT p.id,p.version AS plan_version,a.id AS approval_id,"
            "a.eligible_principal_ids FROM "
            "business.replenishment_plans p JOIN business.approvals a ON a.plan_id=p.id "
            "WHERE p.task_id=%s",
            (UUID(receipt["task_id"]),),
        ).fetchone()
        assert plan and UUID(accounts["approver"]["principal"]) in plan["eligible_principal_ids"]
        assert UUID(accounts["dual"]["principal"]) not in plan["eligible_principal_ids"]
        source_row = db.execute(
            "SELECT source_report_id AS report_id FROM business.p3_task_sources WHERE task_id=%s",
            (UUID(receipt["task_id"]),),
        ).fetchone()
        assert source_row
        runtime_flags = db.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE "
            "rolname='commerceops_app'"
        ).fetchone()
        assert runtime_flags and not any(runtime_flags.values())
    save(directory / "web-accounts.json", accounts)
    # Public source references, not credentials. Detailed wire bodies are not saved.
    save(
        directory / "web-facts.json",
        {
            "task": receipt["task_id"],
            "source_task": receipt["source_task_id"],
            "report": str(source_row["report_id"]),
            "approval": str(plan["approval_id"]),
            "plan": str(plan["id"]),
            "version": plan["plan_version"],
            "request": receipt["request_key"],
            "shop_a": str(f.inventory.data.shop),
            "shop_b": str(shop_b),
            "operator": str(f.actor.principal_id),
            "public_tasks": 22,
            "source_mode": "mock",
            "identity_mode": "session",
        },
    )
    save(directory / "owner-settings.json", settings.model_dump(mode="json"))
    f.client.close()
    print(
        "B02 owned PG prepared: 22 public task records, 20-SKU frozen plan, five "
        "provisioned identities; values withheld"
    )


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1]))
    except Exception as error:
        print(json.dumps({"stage": "B02-owned-seed", "failure_category": type(error).__name__}))
        raise SystemExit(2) from None
