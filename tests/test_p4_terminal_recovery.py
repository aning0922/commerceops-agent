"""原unknown恢复的离线读前契约；真实PG/once/native进程另由整链节点证明。"""

import json
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.contracts import ProjectionRequest, ReadbackDiagnostic

from tests.test_p4_base_adapter import MemoryRecords, execute
from tests.test_p4_base_contract import request, sample, terminal
from tests.test_p4_base_reconciliation import row
from tests.test_p4_queued_terminal import queued_terminal_value

pytestmark = pytest.mark.offline


def recovery_request() -> ProjectionRequest:
    return request(
        terminal(business_status="closed"),
        operation="update",
        external_id="synthetic-row",
        verified_v1=sample(),
    )


@pytest.mark.parametrize("omitted", [False, True])
@pytest.mark.parametrize("digits", [False, True])
def test_trusted_full_v1_allows_one_update_and_full_v2_readback(
    omitted: bool, digits: bool
) -> None:
    old = row()
    if omitted:
        for name in ("ResolutionReason", "ResolvedBy", "ResolvedAt"):
            del old["fields"][name]
    if digits:
        for name in ("Quantity", "SyncVersion"):
            old["fields"][name] = str(old["fields"][name])
    records = MemoryRecords([old])
    result = execute(records, recovery_request())
    assert result.outcome == "verified" and result.observed_version == 2
    assert [call[0] for call in records.calls] == ["query", "update", "query"]
    assert result.observed_fields == recovery_request().projection.fields()


@pytest.mark.parametrize(
    "change",
    [
        "required",
        "quantity",
        "immutable",
        "timestamp",
        "terminal",
        "record",
        "duplicate",
        "version_float",
        "quantity_float",
        "future",
        "v2_missing",
        "v2_mismatch",
    ],
)
def test_incomplete_wrong_or_untrusted_readback_cannot_authorize_write(change: str) -> None:
    old = row()
    if change == "required":
        del old["fields"]["Quantity"]
    elif change == "quantity":
        old["fields"]["Quantity"] = "0100"
    elif change == "immutable":
        old["fields"]["SKU"] = "other"
    elif change == "timestamp":
        old["fields"]["UpdatedAt"] = "2026-10-11T03:00:01+00:00"
    elif change == "terminal":
        old["fields"]["ResolutionReason"] = "other"
    elif change == "record":
        old["record_id"] = "other"
    elif change == "version_float":
        old["fields"]["SyncVersion"] = 1.0
    elif change == "quantity_float":
        old["fields"]["Quantity"] = 100.0
    elif change == "future":
        old["fields"]["SyncVersion"] = 3
    elif change in ("v2_missing", "v2_mismatch"):
        old = row(terminal(business_status="closed"))
        if change == "v2_missing":
            del old["fields"]["ResolutionReason"]
        else:
            old["fields"]["ResolvedBy"] = "other"
    records = MemoryRecords([old, row(identifier="duplicate")] if change == "duplicate" else [old])
    assert execute(records, recovery_request()).outcome != "verified"
    assert [call[0] for call in records.calls] == ["query"]


@pytest.mark.parametrize("count", [True, 0, 2, "1"])
def test_terminal_recovery_count_is_exact_nonbool_integer(count: object) -> None:
    from commerceops.application.feishu_business.recovery import TerminalRecovery

    body = dict(
        recovery_count=count,
        failed_window_id=str(uuid4()),
        failed_gateway_termination_id=str(uuid4()),
        failed_worker_owner=str(uuid4()),
        failed_worker_termination_id=str(uuid4()),
        **{
            name: "a" * 64
            for name in (
                "failed_window_hash",
                "failed_sdk_window_hash",
                "failed_ledger_hash",
                "failed_delivery_hash",
                "failed_gateway_hash",
            )
        },
    )
    with pytest.raises(ValueError):
        TerminalRecovery.model_validate_json(json.dumps(body))


def test_recovery_carrier_keeps_same_sealed_profile_caps_and_roundtrip() -> None:
    from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow

    settings, value = queued_terminal_value()
    value["terminal_update"]["recovery_of"] = dict(
        recovery_count=1,
        failed_window_id=str(uuid4()),
        failed_gateway_termination_id=str(uuid4()),
        failed_worker_owner=str(uuid4()),
        failed_worker_termination_id=str(uuid4()),
        **{
            name: "a" * 64
            for name in (
                "failed_window_hash",
                "failed_sdk_window_hash",
                "failed_ledger_hash",
                "failed_delivery_hash",
                "failed_gateway_hash",
            )
        },
    )
    window = ControlledWorkerWindow.model_validate_json(json.dumps(value))
    assert window.requires_sealed_source and sum(window.window(settings).caps.values()) == 11
    assert ControlledWorkerWindow.model_validate_json(window.model_dump_json()) == window


def test_already_full_v2_settles_with_no_update() -> None:
    records = MemoryRecords([row(terminal(business_status="closed"))])
    assert execute(records, recovery_request()).outcome == "verified"
    assert [call[0] for call in records.calls] == ["query"]


def test_nullable_compatibility_requires_internal_v1_and_never_applies_to_v2() -> None:
    old = row()
    for name in ("ResolutionReason", "ResolvedBy", "ResolvedAt"):
        del old["fields"][name]
    records = MemoryRecords([old])
    value = request(
        terminal(business_status="closed"), operation="update", external_id="synthetic-row"
    )
    assert execute(records, value).code == "INCOMPLETE_READBACK"
    assert len(records.calls) == 1
    records = MemoryRecords([row()])
    forged = recovery_request().model_copy(update={"verified_v1": sample(quantity=101)})
    assert execute(records, forged).code == "INVALID_PROJECTION_REQUEST"
    assert not records.calls


def test_diagnostic_is_closed_and_contains_no_values_or_external_identifiers() -> None:
    old = row()
    del old["fields"]["Quantity"]
    result = execute(MemoryRecords([old]), recovery_request())
    assert result.diagnostic == ReadbackDiagnostic(
        stage="fields",
        reason="required",
        fields=("Quantity",),
        pagination_complete=True,
        unique=True,
    )
    for changes in (
        dict(fields=("private-value",)),
        dict(reason="private-value"),
        dict(raw="private-value"),
    ):
        with pytest.raises(ValueError):
            ReadbackDiagnostic.model_validate(dict(stage="fields", reason="required") | changes)
