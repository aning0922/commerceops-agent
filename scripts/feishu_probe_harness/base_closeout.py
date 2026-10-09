"""既有唯一创建行一次update→完整reconcile；无create/prepare/replay。"""

from typing import Any, cast
from uuid import UUID

from commerceops.adapters.feishu.base import request_hash, validate_fields

from .base_http_deadline import DeadlineQueryOnlySDK
from .base_live_core import BoundaryFailure, ScopedRecordSDK, snapshot
from .base_query import safe_category


class UpdateReadbackSDK(DeadlineQueryOnlySDK):
    def __init__(self: Any, *a: Any, success_replay_authorized: Any = False, **k: Any) -> None:
        super().__init__(*a, **k)
        self.success_replay_authorized = cast(bool, success_replay_authorized)
        self.replay_prechecked = False
        self.replay_verified = False

    def before(self: Any, kind: Any, app_token: Any, table_id: Any) -> Any:
        if kind == "update" and self.success_replay_authorized and (not self.replay_verified):
            raise BoundaryFailure()
        if kind == "create" and (
            not self.replay_prechecked
            or self.phase != "SECOND_CREATE_ONCE_SAME_ORIGINAL_TOKEN_PAYLOAD_DEFAULT_HTTP2"
        ):
            raise BoundaryFailure()
        permitted = {"update", "list"} | ({"create"} if self.success_replay_authorized else set())
        list_cap = 4 if self.success_replay_authorized else 2
        if kind not in permitted or (kind == "list" and self.counts["list"] >= list_cap):
            raise BoundaryFailure()
        ScopedRecordSDK.before(self, kind, app_token, table_id)

    def create(self: Any, *args: Any) -> Any:
        if not self.success_replay_authorized:
            raise BoundaryFailure()
        try:
            return super().create(*args)
        except Exception as error:
            self.safe_exceptions.append(
                dict(
                    stage="PUBLIC_SDK_SECOND_ORIGINAL_CREATE_METHOD", category=safe_category(error)
                )
            )
            raise

    def update(self: Any, *args: Any) -> Any:
        try:
            return super().update(*args)
        except Exception as error:
            self.safe_exceptions.append(
                dict(stage="PUBLIC_SDK_UPDATE_METHOD", category=safe_category(error))
            )
            raise

    def list(self: Any, *args: Any) -> Any:
        reply = super().list(*args)
        items = reply.data.get("items")
        if (
            reply.success
            and type(items) is list
            and any(type(v) is not dict or v.get("record_id") != self.anchor for v in items)
        ):
            self.safe_exceptions.append(
                dict(stage="EXISTING_RECORD_ANCHOR_CHECK", category="RECORD_ANCHOR_MISMATCH")
            )
            raise BoundaryFailure()
        return reply


def finish_update_once(
    probe: Any, transport: UpdateReadbackSDK, pid: Any, created: Any, updated: Any
) -> Any:
    if transport.success_replay_authorized and (not transport.replay_verified):
        raise BoundaryFailure()
    validate_fields(pid, created)
    validate_fields(pid, updated)
    if (
        pid.version != 4
        or created["State"] != "created"
        or updated != {**created, "State": "updated", "UpdatedAt": updated["UpdatedAt"]}
    ):
        raise BoundaryFailure()
    row = dict(snapshot(probe, pid))
    if (
        row["status"] != "succeeded"
        or row["pending_kind"] != "create"
        or row["pending_fields"] is not None
        or (row["pending_sha256"] is not None)
        or (row["fields"] != created)
        or (not row["record_id"])
        or (row["request_sha256"] != request_hash(*transport.target, created))
    ):
        raise BoundaryFailure()
    token = UUID(str(row["client_token"]))
    transport.bind_token(token)
    transport.anchor = row["record_id"]
    transport.set_phase("EXISTING_RECONCILED_RECORD_UPDATE_ONCE_DEFAULT_HTTP2")
    update_status = probe.update_once(pid, state="updated", updated_at=updated["UpdatedAt"])
    transport.set_phase("UPDATE_COMPLETE_FIELDS_QUERY_HTTP5_STOP_AFTER_RECONCILE")
    reconcile_status = probe.reconcile(pid, verify_succeeded=True)
    final = snapshot(probe, pid)
    key_unchanged = UUID(str(final["client_token"])) == token
    hash_unchanged = final["request_sha256"] == row["request_sha256"] and final["fields"] == created
    pending_matches = (
        final["pending_kind"] == "update"
        and final["pending_fields"] == updated
        and (final["pending_sha256"] == request_hash(*transport.target, updated))
    )
    anchor_unchanged = final["record_id"] == row["record_id"]
    verified = (
        reconcile_status == "succeeded"
        and final["status"] == "succeeded"
        and key_unchanged
        and hash_unchanged
        and pending_matches
        and anchor_unchanged
        and (transport.counts["update"] == 1)
    )
    return dict(
        schema="BASE_UPDATE_READBACK_SAFE_RESULT_V1",
        state="UPDATE_FULL_FIELDS_RECONCILED_STOPPED_NOT_GATE"
        if verified
        else "UPDATE_OR_READBACK_INCONCLUSIVE_STOPPED",
        update_method_status=update_status,
        reconcile_status=reconcile_status,
        PG_status=final["status"],
        persistent_original_UUIDv4_key_unchanged=key_unchanged,
        persistent_original_ProbeID_target_create_hash_fields_verified=hash_unchanged,
        original_record_anchor_unchanged=anchor_unchanged,
        original_pending_update_full_fields_hash_verified=pending_matches,
        full_updated_six_fields_unique_original_record_verified=verified,
        SDK_calls=transport.counts,
        safe_HTTP_business_records=transport.records,
        safe_exception_categories=transport.safe_exceptions,
        safe_HTTP_wait_records=transport.http_wait_records,
        update_default_HTTP_wait_seconds=2.0,
        query_HTTP_wait_max_seconds=5.0,
        query_HTTP_wait_remaining_deadline_clamped=True,
        AUTH_vs_BASE_LIST_not_distinguished=True,
        prepare_new_business_key_or_WS_card_executed=False,
        success_platform_create_replay_armed=transport.success_replay_authorized,
        followup_mutations=False,
        raw_exception_message_repr_headers_body_ID_token_URL_archived=False,
        G3="INCOMPLETE",
    )


def replay_row(probe: Any, pid: Any, transport: UpdateReadbackSDK, created: Any) -> Any:
    row = dict(snapshot(probe, pid))
    if (
        row["status"] != "succeeded"
        or row["pending_kind"] != "create"
        or row["pending_fields"] is not None
        or (row["pending_sha256"] is not None)
        or (row["fields"] != created)
        or (row["request_sha256"] != request_hash(*transport.target, created))
        or (row["record_id"] != transport.anchor)
        or (UUID(str(row["client_token"])) != transport.fixed_token)
    ):
        raise BoundaryFailure()
    return row


def stopped_before_update(
    probe: Any,
    transport: UpdateReadbackSDK,
    pid: Any,
    created: Any,
    replay_status: Any,
    checks: Any,
) -> Any:
    final = snapshot(probe, pid)
    return dict(
        schema="BASE_UPDATE_READBACK_SAFE_RESULT_V1",
        state="REPLAY_STOPPED_BEFORE_UPDATE_NOT_GATE",
        update_method_status="not_attempted",
        reconcile_status=checks[-1]["status"] if checks else "unknown",
        PG_status=final["status"],
        persistent_original_UUIDv4_key_unchanged=UUID(str(final["client_token"]))
        == transport.fixed_token,
        persistent_original_ProbeID_target_create_hash_fields_verified=final["fields"] == created
        and final["request_sha256"] == request_hash(*transport.target, created),
        original_record_anchor_unchanged=final["record_id"] == transport.anchor,
        original_pending_update_full_fields_hash_verified=False,
        full_updated_six_fields_unique_original_record_verified=False,
        SDK_calls=transport.counts,
        safe_HTTP_business_records=transport.records,
        safe_exception_categories=transport.safe_exceptions,
        safe_HTTP_wait_records=transport.http_wait_records,
        success_platform_create_replay_armed=True,
        success_platform_create_replay_status=replay_status,
        replay_checks=checks,
        prepare_new_business_key_or_WS_card_executed=False,
        followup_mutations=False,
        raw_exception_message_repr_headers_body_ID_token_URL_archived=False,
        G3="INCOMPLETE",
    )


def finish_base_closeout(
    probe: Any, transport: UpdateReadbackSDK, pid: Any, created: Any, updated: Any
) -> Any:
    if not transport.success_replay_authorized:
        return finish_update_once(probe, transport, pid, created, updated)
    validate_fields(pid, created)
    validate_fields(pid, updated)
    initial = dict(snapshot(probe, pid))
    if (
        pid.version != 4
        or created["State"] != "created"
        or updated != {**created, "State": "updated", "UpdatedAt": updated["UpdatedAt"]}
    ):
        raise BoundaryFailure()
    transport.bind_token(UUID(str(initial["client_token"])))
    transport.anchor = initial["record_id"]
    replay_row(probe, pid, transport, created)
    transport.set_phase("SECOND_CREATE_PRECHECK_CURRENT_ORIGINAL_FULL_FIELDS")
    before = probe.reconcile(pid, verify_succeeded=True)
    checks = [dict(stage="precheck_current_unique_original_fields", status=before)]
    if before != "succeeded":
        return stopped_before_update(probe, transport, pid, created, "not_attempted", checks)
    replay_row(probe, pid, transport, created)
    with probe.connections() as lock_connection:
        row = probe._load(lock_connection, pid)
        key = probe._table_lock(lock_connection, row)
        try:
            locked = probe._load(lock_connection, pid)
            lock_connection.commit()
            if (
                locked["status"] != "succeeded"
                or locked["pending_kind"] != "create"
                or locked["pending_fields"] is not None
                or (locked["pending_sha256"] is not None)
                or (locked["fields"] != created)
                or (locked["record_id"] != transport.anchor)
                or (UUID(str(locked["client_token"])) != transport.fixed_token)
            ):
                raise BoundaryFailure()
            transport.replay_prechecked = True
            probe._status(pid, "inflight", record_id=transport.anchor)
            transport.set_phase("SECOND_CREATE_ONCE_SAME_ORIGINAL_TOKEN_PAYLOAD_DEFAULT_HTTP2")
            try:
                reply = transport.create(*transport.target, str(transport.fixed_token), created)
            except Exception:
                replay_status = "unknown"
                probe._status(pid, "unknown", record_id=transport.anchor)
            else:
                record = reply.data.get("record")
                exact = (
                    reply.success
                    and type(record) is dict
                    and (record.get("record_id") == transport.anchor)
                )
                replay_status = "succeeded" if exact else "unknown"
                probe._status(pid, replay_status, record_id=transport.anchor, code=reply.code)
        finally:
            lock_connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,))
    transport.set_phase("SECOND_CREATE_FULL_ORIGINAL_FIELDS_POSTCHECK_STOP_IF_UNKNOWN")
    after = probe.reconcile(pid, verify_succeeded=True)
    checks.append(dict(stage="postcheck_unique_same_anchor_original_fields", status=after))
    if replay_status != "succeeded" or after != "succeeded":
        return stopped_before_update(probe, transport, pid, created, replay_status, checks)
    replay_row(probe, pid, transport, created)
    if transport.counts["list"] > 2 or transport.deadline - 6 - transport.clock() <= 2:
        return stopped_before_update(
            probe,
            transport,
            pid,
            created,
            "succeeded_but_update_readback_budget_not_reserved",
            checks,
        )
    transport.replay_verified = True
    result = finish_update_once(probe, transport, pid, created, updated)
    result.update(
        success_platform_create_replay_status="succeeded",
        replay_checks=checks,
        second_original_UUIDv4_token_and_original_payload_verified=True,
        second_original_create_same_record_unique_full_fields_verified=True,
    )
    return result
