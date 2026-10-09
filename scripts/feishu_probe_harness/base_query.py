"""从冻结runtime提取的受限技术核心；实际平台证据不覆盖公开适配版本。"""

from typing import Any
from uuid import UUID

import requests
from commerceops.adapters.feishu.base import request_hash, validate_fields

from .base_live_core import BoundaryFailure, ScopedRecordSDK, snapshot


def safe_category(error: Any) -> Any:
    pairs = (
        (requests.exceptions.SSLError, "TLS_FAILURE"),
        (requests.exceptions.ConnectTimeout, "CONNECT_TIMEOUT"),
        (requests.exceptions.ReadTimeout, "READ_TIMEOUT"),
        (requests.exceptions.Timeout, "REQUEST_TIMEOUT"),
        (requests.exceptions.ConnectionError, "CONNECTION_FAILURE"),
        (requests.exceptions.HTTPError, "HTTP_CLIENT_EXCEPTION"),
        (TimeoutError, "DEADLINE_OR_TIMEOUT"),
        (AttributeError, "SDK_DTO_ATTRIBUTE_EXCEPTION"),
        (TypeError, "SDK_DTO_TYPE_EXCEPTION"),
        (UnicodeError, "RESPONSE_DECODE_EXCEPTION"),
        (ValueError, "VALUE_OR_VALIDATION_EXCEPTION"),
    )
    return next(
        (label for kind, label in pairs if isinstance(error, kind)), "OTHER_UNKNOWN_EXCEPTION"
    )


class QueryOnlySDK(ScopedRecordSDK):
    def __init__(self: Any, *a: Any, **k: Any) -> None:
        super().__init__(*a, **k)
        self.safe_exceptions: list[dict[str, Any]] = []

    def before(self: Any, kind: Any, app_token: Any, table_id: Any) -> Any:
        if kind != "list" or self.counts["list"] >= 2:
            raise BoundaryFailure()
        super().before(kind, app_token, table_id)

    def list(self: Any, *args: Any) -> Any:
        try:
            return super().list(*args)
        except Exception as error:
            self.safe_exceptions.append(
                dict(stage="PUBLIC_SDK_LIST_METHOD", category=safe_category(error))
            )
            raise


def query_only(probe: Any, transport: QueryOnlySDK, probe_id: Any, expected_fields: Any) -> Any:
    if probe_id.version != 4:
        raise BoundaryFailure()
    validate_fields(probe_id, expected_fields)
    row = snapshot(probe, probe_id)
    if (
        row["status"] not in ("unknown", "inflight")
        or row["pending_kind"] != "create"
        or row["pending_fields"] is not None
        or (row["pending_sha256"] is not None)
        or (expected_fields["State"] != "created")
        or (row["fields"] != expected_fields)
        or (row["request_sha256"] != request_hash(*transport.target, expected_fields))
    ):
        raise BoundaryFailure()
    token = UUID(str(row["client_token"]))
    transport.bind_token(token)
    transport.set_phase("ORIGINAL_UNKNOWN_QUERY_ONLY_STOP_AFTER_RECONCILE")
    result = probe.reconcile(probe_id)
    final = snapshot(probe, probe_id)
    if (
        UUID(str(final["client_token"])) != token
        or final["request_sha256"] != row["request_sha256"]
    ):
        raise BoundaryFailure()
    return dict(
        schema="BASE_QUERY_ONLY_SAFE_RESULT_V1",
        state="QUERY_ONLY_RECONCILED_STOPPED"
        if result == "succeeded"
        else "QUERY_ONLY_INCONCLUSIVE_STOPPED",
        reconcile_status=result,
        PG_status=final["status"],
        persistent_original_UUIDv4_key_unchanged=True,
        persistent_original_ProbeID_target_hash_fields_verified=True,
        SDK_calls=transport.counts,
        safe_HTTP_business_records=transport.records,
        safe_exception_categories=transport.safe_exceptions,
        create_update_prepare_or_new_key_executed=False,
        followup_mutations=False,
        query_only=True,
        raw_exception_message_repr_headers_body_ID_token_URL_archived=False,
        G3="INCOMPLETE",
    )
