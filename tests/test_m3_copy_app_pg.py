"""New-owned PG composition: real owner CLI, shared main API and current Web session."""

import json
from datetime import timedelta
from uuid import uuid4

import pytest
from commerceops.application.knowledge_copy.commands import CreateCopy, ReviewCopy
from commerceops.application.knowledge_copy.contracts import digest
from commerceops.entrypoints.api import create_app
from commerceops.entrypoints.database import main
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.knowledge_copy_config import CopyDeployment
from commerceops.infrastructure.knowledge_copy_draft_store import register_copy_product
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
from fastapi.testclient import TestClient
from psycopg import sql

from tests.inventory_support import DIRECTORY
from tests.p3_support import ORIGIN
from tests.test_p3_pg import fixture as fixture
from tests.test_p6_copy_config import config_body
from tests.test_p6_knowledge_copy_contracts import product
from tests.test_p6_knowledge_copy_pg import KnowledgeFixture
from tests.test_p6_knowledge_copy_pg import knowledge as knowledge

pytestmark = pytest.mark.integration


def test_owner_cli_and_shared_main_api_preserve_real_session_and_approval(
    knowledge: KnowledgeFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    k, f = knowledge, knowledge.f
    product_id = uuid4()
    with connect(f.inventory.owner) as db:
        clock = db.execute("SELECT clock_timestamp() AS t").fetchone()
        assert clock
        register_copy_product(
            db,
            product_id,
            product(
                scope=k.manifest.scope,
                captured_at=clock["t"] - timedelta(seconds=1),
                expires_at=clock["t"] + timedelta(minutes=30),
            ),
        )
        assert db.execute(
            "SELECT has_table_privilege('commerceops_app',"
            "'business.p6_copy_candidates','INSERT') AS allowed"
        ).fetchone() == {"allowed": False}
    # Actual CLI dispatch and actual owner transaction; no DB or SessionStore replacement.
    owner = f.inventory.owner
    for key, value in {
        "HOST": owner.host,
        "PORT": str(owner.port),
        "NAME": owner.name,
        "USER": owner.user,
        "PASSWORD_FILE": str(owner.password_file),
    }.items():
        monkeypatch.setenv("COMMERCEOPS_DB_" + key, value)
    monkeypatch.setattr("sys.argv", ["database", "grant-knowledge-copy-runtime"])
    main()
    with connect(f.inventory.owner) as db:
        assert db.execute(
            "SELECT has_table_privilege('commerceops_app',"
            "'business.p6_copy_candidates','INSERT') AS allowed"
        ).fetchone() == {"allowed": True}
    body = config_body()
    binding = body["bindings"][0]
    binding.update(organization_id=str(f.actor.organization_id), shop_id=str(f.inventory.data.shop))
    binding["binding_digest"] = digest({k: v for k, v in binding.items() if k != "binding_digest"})
    body["config_digest"] = digest({k: v for k, v in body.items() if k != "config_digest"})
    deployment = CopyDeployment.model_validate_json(json.dumps(body))
    app = create_app(
        web_config=f.config,
        replenishment_store=ReplenishmentStore(f.config, DIRECTORY),
        copy_deployment=deployment,
    )
    command = CreateCopy(
        shop_id=f.inventory.data.shop,
        registry_id=k.registry,
        registry_digest=k.manifest.manifest_digest,
        product_source_id=product_id,
        query_ref=binding["query_ref"],
        reviewer_id=f.actor.principal_id,
        request_key=uuid4(),
    )
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/v1/copy/candidates/" + str(uuid4())).status_code == 401
        client.cookies.update(f.client.cookies)
        denied = client.post(
            "/api/v1/copy/candidates",
            json=command.model_dump(mode="json"),
            headers={"Origin": ORIGIN},
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "CSRF_INVALID"
        created = client.post(
            "/api/v1/copy/candidates", json=command.model_dump(mode="json"), headers=f.headers()
        )
        assert created.status_code == 202
        value = created.json()["data"]["candidate"]
        identifier = value["candidate_id"]
        recovered = client.get("/api/v1/copy/candidate-requests/" + str(command.request_key))
        assert recovered.status_code == 200 and recovered.json() == created.json()
        decision = ReviewCopy(
            candidate_version="v1",
            candidate_hash=value["candidate_hash"],
            request_key=uuid4(),
            action="approve",
            reason="Explicit review of self-authored synthetic source",
        )
        reviewed = client.post(
            f"/api/v1/copy/candidates/{identifier}/review",
            json=decision.model_dump(mode="json"),
            headers=f.headers(),
        )
        assert reviewed.status_code == 200
        result = reviewed.json()["data"]
        assert result["state"] == "saved" and result["draft_id"] is not None
        assert result["publication_allowed"] is False
        receipt = client.get(
            f"/api/v1/copy/candidates/{identifier}/review-receipts/{decision.request_key}",
            params={"candidate_hash": value["candidate_hash"]},
        )
        assert receipt.status_code == 200 and receipt.json() == reviewed.json()
        with connect(f.inventory.app) as db:
            for table in ("p6_copy_candidates", "p6_copy_decisions", "p6_copy_drafts"):
                assert db.execute(
                    sql.SQL("SELECT count(*) AS n FROM business.{}").format(sql.Identifier(table))
                ).fetchone() == {"n": 1}
        with connect(f.inventory.app) as db:
            assert db.execute("SELECT count(*) AS n FROM business.outbox").fetchone() == {"n": 0}
