"""Base最小CRUD核心：原持久模型/同表锁；成功后的平台重投不在已批准路线。"""

import json
import time
from typing import Any
from uuid import UUID

from commerceops.adapters.feishu.base import BASE_FIELDS, BaseProbe, RecordSDK, validate_fields
from lark_oapi.api.bitable.v1 import ListAppTableRecordRequest  # type: ignore[import-untyped]


class BoundaryFailure(ValueError):
    pass


class ScopedRecordSDK(RecordSDK):
    """仅既有目标与自有ProbeID；SDK方法次数/页面预算，证据不保存原响应。"""

    def __init__(
        self: Any,
        client: Any,
        probe_id: Any,
        target: tuple[str, str],
        deadline: Any,
        *,
        clock: Any = time.time,
    ) -> None:
        super().__init__(client)
        self.probe_id = probe_id
        self.target = target
        self.deadline = deadline
        self.clock = clock
        self.fixed_token = None
        self.anchor = None
        self.records: list[dict[str, Any]] = []
        self.counts = dict(create=0, list=0, update=0)
        self.phase = "PREPARE"
        self.phase_pages = 0
        self.scope_violation = False

    def bind_token(self: Any, token: Any) -> Any:
        token = UUID(str(token))
        if token.version != 4 or (self.fixed_token is not None and token != self.fixed_token):
            raise BoundaryFailure()
        self.fixed_token = token

    def set_phase(self: Any, phase: Any) -> Any:
        self.phase = phase
        self.phase_pages = 0

    def before(self: Any, kind: Any, app_token: Any, table_id: Any) -> Any:
        if (app_token, table_id) != self.target or self.clock() >= self.deadline - 6:
            raise BoundaryFailure()
        cap = dict(create=1, list=4, update=1)[kind]
        if self.counts[kind] >= cap or (kind == "list" and self.phase_pages >= 2):
            raise BoundaryFailure()
        self.counts[kind] += 1
        if kind == "list":
            self.phase_pages += 1

    def report(self: Any, kind: Any, reply: Any, *, same_key: Any = None) -> Any:
        self.records.append(
            dict(
                phase=self.phase,
                method=kind,
                http_status=reply.http_status if type(reply.http_status) is int else None,
                business_code=reply.code if type(reply.code) is int else None,
                HTTP_and_business_success=reply.success,
                same_persistent_original_token=same_key,
                request_only_approved_target_and_six_fields=True,
            )
        )
        return reply

    def create(self: Any, app_token: Any, table_id: Any, token: Any, fields: Any) -> Any:
        self.before("create", app_token, table_id)
        validate_fields(self.probe_id, fields)
        if self.fixed_token is None or UUID(token) != self.fixed_token:
            raise BoundaryFailure()
        try:
            reply = super().create(app_token, table_id, token, fields)
        except Exception:
            self.records.append(
                dict(
                    phase=self.phase,
                    method="create",
                    http_status=None,
                    business_code=None,
                    HTTP_and_business_success=False,
                    same_persistent_original_token=True,
                    request_only_approved_target_and_six_fields=True,
                )
            )
            raise
        return self.report("create", reply, same_key=True)

    def list(self: Any, app_token: Any, table_id: Any, page_token: Any) -> Any:
        self.before("list", app_token, table_id)
        query = 'AND(CurrentValue.[ProbeID]="' + str(self.probe_id) + '")'
        builder = (
            ListAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .page_size(100)
            .field_names(json.dumps(sorted(BASE_FIELDS)))
            .filter(query)
        )
        if page_token is not None:
            builder.page_token(page_token)
        try:
            reply = self._reply(
                self.client.bitable.v1.app_table_record.list(builder.build(), self.option)
            )
        except Exception:
            self.records.append(
                dict(
                    phase=self.phase,
                    method="list",
                    http_status=None,
                    business_code=None,
                    HTTP_and_business_success=False,
                    same_persistent_original_token=None,
                    request_only_approved_target_and_six_fields=True,
                )
            )
            raise
        items = reply.data.get("items")
        if reply.success and type(items) is list:
            if any(
                type(v) is not dict
                or type(v.get("fields")) is not dict
                or v["fields"].get("ProbeID") != str(self.probe_id)
                for v in items
            ):
                self.scope_violation = True
                self.report("list", reply)
                raise BoundaryFailure()
        return self.report("list", reply)

    def update(self: Any, app_token: Any, table_id: Any, record_id: Any, fields: Any) -> Any:
        self.before("update", app_token, table_id)
        validate_fields(self.probe_id, fields)
        if self.anchor is None or record_id != self.anchor:
            raise BoundaryFailure()
        try:
            reply = super().update(app_token, table_id, record_id, fields)
        except Exception:
            self.records.append(
                dict(
                    phase=self.phase,
                    method="update",
                    http_status=None,
                    business_code=None,
                    HTTP_and_business_success=False,
                    same_persistent_original_token=None,
                    request_only_approved_target_and_six_fields=True,
                )
            )
            raise
        return self.report("update", reply)


def snapshot(probe: Any, probe_id: Any) -> Any:
    with probe.connections() as connection:
        row = probe._load(connection, probe_id)
    token = UUID(str(row["client_token"]))
    if token.version != 4:
        raise BoundaryFailure()
    return row


def run_crud(
    probe: BaseProbe, transport: ScopedRecordSDK, probe_id: Any, fields: Any, updated_fields: Any
) -> Any:
    validate_fields(probe_id, fields)
    validate_fields(probe_id, updated_fields)
    if fields["State"] != "created" or updated_fields != {
        **fields,
        "State": "updated",
        "UpdatedAt": updated_fields["UpdatedAt"],
    }:
        raise BoundaryFailure()
    token = probe.prepare(probe_id, *transport.target, fields)
    transport.bind_token(token)
    row = snapshot(probe, probe_id)
    if row["status"] != "ready" or row["pending_kind"] != "create":
        raise BoundaryFailure()
    checks: list[dict[str, Any]] = []

    def done(state: Any) -> Any:
        final = snapshot(probe, probe_id)
        if UUID(str(final["client_token"])) != UUID(str(token)):
            raise BoundaryFailure()
        return dict(
            schema="BASE_CRUD_SAFE_RESULT_V1",
            state=state,
            PG_status=final["status"],
            persistent_client_token_uuidv4=True,
            persistent_token_unchanged=True,
            persistent_ProbeID_and_request_hash_verified_by_original_load=True,
            checks=checks,
            SDK_calls=transport.counts,
            safe_HTTP_business_records=transport.records,
            original_key_second_real_SDK_create_executed=False,
            success_replay_extension="UNAPPROVED_ACTUAL_EXTENSION_NOT_ARMED",
            unknown_auto_retry=False,
            new_key_generated_after_unknown=False,
            only_own_row_and_existing_six_fields=True,
            query_scope_violation=transport.scope_violation,
            raw_payload_ID_token_URL_archived=False,
            new_card_or_WS_started=False,
            G3="INCOMPLETE",
        )

    def controlled_unknown_reconcile() -> Any:
        transport.set_phase("UNKNOWN_RECONCILE_STOP_AFTER_QUERY")
        result = probe.reconcile(probe_id)
        checks.append(
            dict(stage="unknown_readonly_API_reconcile", status=result, continue_mutations=False)
        )
        return done("STOPPED_UNKNOWN_OR_RECONCILED_PARTIAL")

    transport.set_phase("CREATE_ONCE")
    created = probe.create_once(probe_id)
    checks.append(dict(stage="create", status=created))
    if created in ("unknown", "inflight"):
        return controlled_unknown_reconcile()
    if created != "succeeded":
        return done("STOPPED_REJECTION_OR_CONFLICT")
    row = snapshot(probe, probe_id)
    first_record = row["record_id"]
    transport.set_phase("CREATE_FIELDS_READBACK")
    verified = probe.reconcile(probe_id, verify_succeeded=True)
    checks.append(dict(stage="create_readback", status=verified))
    if verified != "succeeded" or transport.scope_violation:
        return done("STOPPED_READBACK_UNVERIFIED")
    row = snapshot(probe, probe_id)
    if row["record_id"] != first_record or not first_record:
        return done("STOPPED_RECORD_LINK_MISMATCH")
    transport.anchor = first_record
    transport.set_phase("UPDATE_ONCE")
    updated = probe.update_once(probe_id, state="updated", updated_at=updated_fields["UpdatedAt"])
    checks.append(dict(stage="update", status=updated))
    if updated in ("unknown", "inflight"):
        return controlled_unknown_reconcile()
    if updated != "succeeded":
        return done("STOPPED_UPDATE_REJECTION_OR_CONFLICT")
    transport.set_phase("UPDATE_FIELDS_READBACK")
    verified = probe.reconcile(probe_id, verify_succeeded=True)
    checks.append(dict(stage="update_readback", status=verified))
    if verified != "succeeded" or transport.scope_violation:
        return done("STOPPED_UPDATED_FIELDS_UNVERIFIED")
    row = snapshot(probe, probe_id)
    if (
        row["record_id"] != first_record
        or row["pending_kind"] != "update"
        or row["pending_fields"] != updated_fields
    ):
        return done("STOPPED_FINAL_BINDING_MISMATCH")
    return done("BASE_CRUD_FIELDS_READBACK_VERIFIED_NOT_GATE")
