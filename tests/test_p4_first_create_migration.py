"""前向迁移的原guard保留与窄授权静态合同；不是 PostgreSQL 执行证据。"""

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.offline
VERSIONS = Path("backend/migrations/versions")
BEGIN = "-- P4 explicit C0 persisted claim"
END = "-- End P4 explicit C0 persisted claim"


def migration(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, VERSIONS / (name + ".py"))
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def normalized(sql: str) -> str:
    value = re.sub(r"\s+", " ", sql).strip()
    return re.sub(r"\s+([,)])", r"\1", value)


def test_forward_replaces_only_function_and_preserves_every_original_guard() -> None:
    before = migration("0010_p4_base_delivery")
    old: list[str] = []
    before.op = SimpleNamespace(execute=old.append)
    before.upgrade()
    original = next(
        s for s in old if s.startswith("CREATE FUNCTION business.p4_base_delivery_identity")
    )
    after = migration("0013_p4_first_create")
    actual: list[str] = []
    after.op = SimpleNamespace(execute=actual.append)
    after.upgrade()
    assert after.down_revision == "0012_p4_preflight_methods"
    assert len(actual) == 1 and actual[0].startswith("CREATE OR REPLACE FUNCTION")
    unchanged = actual[0].split(BEGIN)[0] + actual[0].split(END)[1]
    unchanged = unchanged.replace("CREATE OR REPLACE FUNCTION", "CREATE FUNCTION")
    unchanged = unchanged.replace("DECLARE first_create boolean := false; ", "")
    assert unchanged.count("AND NOT first_create") == 2
    unchanged = unchanged.replace(" AND NOT first_create", "")
    assert normalized(unchanged) == normalized(original)
    with pytest.raises(RuntimeError, match="cannot be reset"):
        after.downgrade()


@pytest.mark.parametrize(
    "required",
    [
        "OLD.status='unknown' AND OLD.version=1 AND OLD.attempts=1",
        "OLD.last_operation='create' AND OLD.last_error='INCOMPLETE_READBACK'",
        "OLD.external_id IS NULL AND OLD.unknown_since IS NOT NULL",
        "OLD.first_attempt_at IS NOT NULL AND OLD.verification_mode='controlled_sdk'",
        "NEW.status='sending' AND NEW.last_operation='create' AND NEW.attempts=2",
        "NEW.claimed_by IS NOT NULL AND length(NEW.claimed_by)>0",
        "NEW.created_at,NEW.first_attempt_at,NEW.unknown_since,NEW.external_id",
        "OLD.projection_hash,OLD.created_at,OLD.first_attempt_at,OLD.unknown_since,OLD.external_id",
        "c.source='feishu_recovery' AND c.action='approved_workflow_claimed'",
        "c.after_state->>'profile'='approved_first_create'",
        "c.after_state->'first_create'=jsonb_build_object(",
        "'client_token',OLD.client_token::text,'version',1",
        "'projection_hash',OLD.projection_hash,'request_hash',o.request_hash",
        "c.after_state->'task_ids'=jsonb_build_array(OLD.task_id::text)",
        "c.after_state#>>'{workflow_recovery,task_version}'=t.version::text",
        "c.after_state#>>'{workflow_recovery,execution_id}'=x.id::text",
        "business.lock_p3_permission(t.requester_id,OLD.organization_id,OLD.shop_id",
        "business.lock_p3_permission(a.decided_by,OLD.organization_id,OLD.shop_id",
        "w.id=c.id",
        "w.expires_at=(c.after_state->>'expires_at')::timestamptz",
        "w.expires_at>clock_timestamp()",
        "w.method_caps=c.after_state->'caps'",
        "auth.status='returned' AND auth.http_status=200 AND auth.provider_code=0",
        "sender.worker_owner=NEW.claimed_by AND sender.configured_enabled",
        "lock.pid=sender.worker_backend_pid",
        "lock.classid=(7412438461303::bigint>>32)::oid",
        "'p4-gateway:'||org.feishu_app_id,0",
        "prior.id<>w.id AND prior.configured_enabled AND prior.expires_at>clock_timestamp()",
        "term.action='termination_confirmed'",
        "term.after_state->'child_reaped'='true'::jsonb",
        "stop.after_state IS DISTINCT FROM prior.after_state",
        "x.item_ids=ARRAY[OLD.item_id]",
        "link.target_key\n=OLD.target_key AND\nlink.item_id=OLD.item_id",
    ],
)
def test_current_persisted_scope_permissions_locks_c0_and_history_are_required(
    required: str,
) -> None:
    sql = migration("0013_p4_first_create").TRIGGER_SQL
    predicate = sql.split(BEGIN)[1].split(END)[0]
    assert normalized(required) in normalized(predicate)


def test_any_create_ledger_status_blocks_and_no_reset_or_session_switch_is_added() -> None:
    sql = migration("0013_p4_first_create").TRIGGER_SQL
    create = sql.split("AND NOT EXISTS(SELECT 1 FROM business.p4_sdk_calls call")[1].split(
        "AND NOT EXISTS(SELECT 1 FROM business.p4_sdk_windows prior"
    )[0]
    assert "call.subject_id=OLD.outbox_id" in create
    assert "call.method='bitable.v1.app_table_record.create'" in create
    assert "status" not in create  # started/raised/returned/not_called均拒绝，不能筛选已知失败。
    assert "SET LOCAL" not in sql and "current_setting" not in sql
    assert "SECURITY DEFINER" not in sql
    assert "UPDATE business." not in sql and "DELETE FROM" not in sql
    assert "NEW.status:='pending'" not in sql and "NEW.unknown_since:=NULL" not in sql


def test_fixed_sql_lexical_delimiters_are_complete_without_claiming_runtime_execution() -> None:
    sql = migration("0013_p4_first_create").TRIGGER_SQL
    without_literals = re.sub(r"'(?:[^']|'')*'", "", sql)
    balance = 0
    for char in without_literals:
        balance += (char == "(") - (char == ")")
        assert balance >= 0
    assert balance == 0 and sql.count("$$") == 2
