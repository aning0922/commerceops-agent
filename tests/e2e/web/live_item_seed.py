"""B04新窗口种子；先独立B03已核seeder进程退出，再仅本批真实会话操作。"""

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

from commerceops.application.commerce.analysis_task import TrustedReadIdentity
from commerceops.application.replenishment.security import password_hash
from commerceops.entrypoints.api import create_app
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.explanation_repository import create_explanation_task
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import SessionStore
from fastapi.testclient import TestClient

from tests.e2e.web.live_origins import registered_origins
from tests.e2e.web.live_seed import save
from tests.inventory_support import DIRECTORY


def main(directory: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("live_seed.py")), str(directory)],
        env=os.environ,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=300,
    )
    if result.returncode:
        raise RuntimeError("owned base seed failed")
    web, api = registered_origins(directory)
    config = WebConfig.from_file(directory / "configuration.json")
    owner = DatabaseSettings.model_validate_json((directory / "owner-settings.json").read_text())
    facts = json.loads((directory / "web-facts.json").read_text())
    accounts = json.loads((directory / "web-accounts.json").read_text())
    client = TestClient(
        create_app(web_config=config, replenishment_store=ReplenishmentStore(config, DIRECTORY)),
        base_url=api,
    )

    def login(role: str) -> None:
        bootstrap = client.get("/api/v1/auth/csrf").json()
        response = client.post(
            "/api/v1/auth/login",
            json={
                "schema_version": "p3-web-v1",
                "login": accounts[role]["login"],
                "password": accounts[role]["password"],
            },
            headers={"Origin": web, "X-CSRF-Token": bootstrap["csrf_token"]},
        )
        assert response.status_code == 200

    login("operator")
    actor = SessionStore(config).authenticate(client.cookies.get("commerceops_session"))
    identity = TrustedReadIdentity(
        actor.identity_id,
        actor.principal_id,
        actor.organization_id,
        UUID(facts["shop_a"]),
        actor.auth_version,
    )
    _, explanation_job = create_explanation_task(
        config.database, identity, UUID(facts["source_task"]), "template"
    )
    # Real late approver appears after all frozen eligibility snapshots. No fixture rights bypass.
    with connect(owner) as db:
        row = db.execute(
            "SELECT app_id,tenant_key FROM business.identities WHERE id=%s", (actor.identity_id,)
        ).fetchone()
        assert row
        principal, identity_id = uuid4(), uuid4()
        name, password = "b04-late-" + uuid4().hex[:12], secrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO business.principals(id,organization_id,display_name,roles) "
            "VALUES (%s,%s,'自有迟来审批人',ARRAY['approver'])",
            (principal, actor.organization_id),
        )
        db.execute(
            "INSERT INTO business.identities(id,organization_id,principal_id,provider,"
            "app_id,tenant_key,external_subject) VALUES (%s,%s,%s,'web',%s,%s,%s)",
            (identity_id, actor.organization_id, principal, row["app_id"], row["tenant_key"], name),
        )
        db.execute(
            "INSERT INTO business.web_credentials VALUES (%s,%s,%s,%s,%s,true)",
            (name, actor.organization_id, principal, identity_id, password_hash(password)),
        )
        db.execute(
            "INSERT INTO business.principal_shop_scopes VALUES (%s,%s,%s,true)",
            (actor.organization_id, UUID(facts["shop_a"]), principal),
        )
        db.execute(
            "INSERT INTO business.principal_role_shop_grants VALUES (%s,%s,%s,'approver',true)",
            (actor.organization_id, UUID(facts["shop_a"]), principal),
        )
    accounts["late_approver"] = {"principal": str(principal), "login": name, "password": password}
    save(directory / "web-accounts.json", accounts)
    login("approver")
    detail = client.get("/api/v1/approvals/" + facts["approval"]).json()
    p = detail["plan"]
    current = client.get("/api/v1/auth/session").json()
    request = {
        "schema_version": "p3-web-v1",
        "request_key": str(uuid4()),
        "approval_id": facts["approval"],
        "plan_id": p["plan_id"],
        "plan_version": p["plan_version"],
        "plan_hash": p["plan_hash"],
        "action": "approve_with_assumptions",
        "acknowledged_assumption_keys": [r["key"] for r in p["required_assumptions"]],
        "nonce": detail["nonce"],
    }
    response = client.post(
        "/api/v1/approvals/" + facts["approval"] + "/decision",
        json=request,
        headers={"Origin": web, "X-CSRF-Token": current["csrf_token"]},
    )
    assert response.status_code == 200
    save(
        directory / "b04-facts.json",
        {
            "organization": str(actor.organization_id),
            "completed_task": facts["task"],
            "source_task": facts["source_task"],
            "report": facts["report"],
            "approval": facts["approval"],
            "template_job": str(explanation_job),
            "source_mode": "mock",
            "controlled_fixture": "same twenty collector for P2/T2/T4",
        },
    )
    client.close()
    print("B04 own seed/T3 queued; current scopes and raw values withheld")


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1]))
    except Exception as error:
        print(json.dumps({"stage": "B04 seed", "category": type(error).__name__}))
        raise SystemExit(2) from None
