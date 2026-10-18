"""新 owned：同一固定 collector 的真实只读、原 once 与权限失败证据。"""

import json
from pathlib import Path

import pytest
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.feishu_history import HistoryRecoveryStore

from scripts.p4_acceptance import AcceptanceFailure, history_forensics
from tests.p3_support import initialize_p3
from tests.test_p4_acceptance_pg import database as database
from tests.test_p4_acceptance_pg import initialize_schema
from tests.test_p4_gateway_pg import service
from tests.test_p4_history_pg import protected, setup_history

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("state", ["absent", "hold", "verified"])
def test_fixed_collector_preserves_once_and_captures_full_related_state(
    database: tuple[DatabaseSettings, DatabaseSettings], tmp_path: Path, state: str
) -> None:
    owner, app = database
    initialize_schema(owner, "0017")
    f = initialize_p3(owner, app, tmp_path)
    try:
        inputs, request, _ = setup_history(f)
        if state == "hold":
            store = HistoryRecoveryStore(service(f))
            store.register(request)
            store.hold(request)
        elif state == "verified":
            wire = inputs.directory / "external-records.json"
            body = json.loads(wire.read_bytes())
            extra_marker = "owned-extra-wire-sensitive"
            body["history_pages"][0]["items"][0]["access_token"] = extra_marker
            wire.write_text(json.dumps(body))
            assert inputs.run("owned-fixture-history")[0] == 0
        baseline = protected(f)
        result = history_forensics(app, request)
        assert result["complete"] and result["rollback_completed"] and not result["failures"]
        queries = result["queries"]
        tx = queries["HF_TRANSACTION"][0]
        assert tx["readonly"] == "on" and tx["isolation"] == "repeatable read"
        assert (tx["I"], tx["U"], tx["D"]) == (0, 0, 0)
        assert len(queries["HF_CATALOG"]) == 59
        assert queries["HF_PRINCIPAL"][0]["id"] == str(request.principal_id)
        assert queries["HF_IDENTITY"][0]["id"] == str(request.identity_id)
        assert queries["HF_SHOP_SCOPE"] and queries["HF_ROLE_GRANTS"]
        if state == "absent":
            assert queries["HF_BATCH"] == [] and queries["HF_CALLS"] == []
        else:
            assert queries["HF_BATCH"][0]["status"] == state
            assert queries["HF_BATCH"][0]["request_hash"]
        if state == "hold":
            wrong = request.model_copy(update={"chat_id": "owned-wrong-chat"})
            denied = history_forensics(app, wrong)
            assert not denied["complete"] and denied["rollback_completed"]
            assert denied["failures"][0]["code"] == "P4A_HISTORY_FORENSICS_BINDING"
            assert "HF_MESSAGES" not in denied["queries"]
        if state == "verified":
            assert queries["HF_BATCH"][0]["page_evidence"]["complete_unique_pair"]
            assert "owned-page-two" not in json.dumps(result)
            assert "owned-extra-wire-sensitive" not in json.dumps(result)
            assert all("wire_row" not in row for row in queries["HF_MESSAGES"])
            assert len(queries["HF_MESSAGES"]) == 2 and len(queries["HF_SOURCES"]) >= 2
            assert {row["message_id"] for row in queries["HF_MESSAGES"]} <= {
                row["message_id"] for row in queries["HF_SOURCES"]
            }
            assert len(queries["HF_CALLS"]) == 4 and len(queries["HF_WINDOWS"]) == 1
            assert all(row["completed_at"] for row in queries["HF_CALLS"])
            assert all(row["status"] == "pending" for row in queries["HF_REPLIES"])
            assert {row["action"] for row in queries["HF_LIFECYCLE"]} >= {
                "started",
                "stopped",
                "termination_confirmed",
            }
        again = history_forensics(app, request)
        for name in queries:
            if name != "HF_TRANSACTION":
                assert again["queries"][name] == queries[name]
        assert protected(f) == baseline
        with pytest.raises(AcceptanceFailure, match="P4A_ROLE"):
            history_forensics(owner, request)
    finally:
        f.client.close()


def test_fixed_collector_records_real_denial_and_rolls_back_without_losing_other_queries(
    database: tuple[DatabaseSettings, DatabaseSettings], tmp_path: Path
) -> None:
    owner, app = database
    initialize_schema(owner, "0017")
    f = initialize_p3(owner, app, tmp_path)
    try:
        _, request, _ = setup_history(f)
        with connect(owner) as db:
            db.execute("REVOKE SELECT ON business.p4_sdk_calls FROM commerceops_app")
        result = history_forensics(app, request)
        assert not result["complete"] and result["rollback_completed"]
        assert {(row["query_id"], row["sqlstate"]) for row in result["failures"]} == {
            ("HF_WINDOWS", "42501"),
            ("HF_CALLS", "42501"),
        }
        assert result["queries"]["HF_TRANSACTION"][0]["I"] == 0
        assert result["queries"]["HF_PRINCIPAL"]
    finally:
        f.client.close()
