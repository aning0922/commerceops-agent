"""纯错误/版本/回读策略；没有重试、调度、事务或业务状态修改。"""

from enum import StrEnum
from typing import Any, cast

from commerceops.adapters.feishu.projection_contract import (
    BASE_FIELDS,
    ApiReply,
    ProjectionRequest,
    ProjectionResult,
    bind_projection_result,
    normalize_projection_fields,
)


class WriteOutcome(StrEnum):
    ACKNOWLEDGED = "acknowledged"  # ACK 仍须完整 readback，不能直接标 synced。
    DEFERRED = "deferred"  # 已知拒绝，仅 A 的有界策略可决定再调用。
    REJECTED = "rejected"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


KNOWN_REJECTIONS = frozenset(
    {
        1254000,
        1254001,
        1254003,
        1254004,
        1254005,
        1254006,
        1254015,
        1254037,
        1254040,
        1254041,
        1254042,
        1254043,
        1254044,
        1254045,
        1254060,
        1254061,
        1254062,
        1254063,
        1254064,
        1254065,
        1254066,
        1254067,
        1254068,
        1254069,
        1254302,
        1254304,
    }
)


def write_outcome(reply: ApiReply) -> WriteOutcome:
    if type(reply.http_status) is not int or type(reply.code) is not int:
        return WriteOutcome.UNKNOWN
    if reply.code == 1255006 and (reply.http_status == 200 or 400 <= reply.http_status < 500):
        return WriteOutcome.CONFLICT
    if reply.http_status >= 500 or reply.code in {1255040, 1254607, 1254608}:
        return WriteOutcome.UNKNOWN
    if reply.code in {1254290, 1254291} and (
        reply.http_status == 200 or 400 <= reply.http_status < 500
    ):
        return WriteOutcome.DEFERRED
    if reply.success:
        record = reply.data.get("record")
        if type(record) is dict and type(record.get("record_id")) is str and record["record_id"]:
            return WriteOutcome.ACKNOWLEDGED
        return WriteOutcome.UNKNOWN
    if reply.code in KNOWN_REJECTIONS and (
        reply.http_status == 200 or 400 <= reply.http_status < 500
    ):
        return WriteOutcome.REJECTED
    return WriteOutcome.UNKNOWN


def readback_rows(
    request: ProjectionRequest,
    rows: list[dict[str, Any]],
) -> ProjectionResult:
    """只接受调用方确认完整扫描的行；external_link 只在完全匹配时返回。"""
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        record_id, remote = row.get("record_id"), row.get("fields")
        if (
            type(record_id) is not str
            or not record_id
            or record_id in seen
            or type(remote) is not dict
        ):
            return ProjectionResult(outcome="unknown", code="INCOMPLETE_READBACK")
        seen.add(record_id)
        # 完整分页/total 已由 caller 校验；合法空白行没有任何业务字段或 item key。
        # 仍计入分页总数与 record_id 去重，不能成为 match/anchor/15 字段证明。
        if remote == {}:
            continue
        if type(remote.get("CommerceOpsItemID")) is not str:
            return ProjectionResult(outcome="unknown", code="INCOMPLETE_READBACK")
        if remote["CommerceOpsItemID"] == str(request.projection.item_id):
            matches.append(row)
    if not matches:
        return ProjectionResult(outcome="unknown", code="ITEM_MISSING", complete=True)
    if len(matches) != 1:
        return ProjectionResult(
            outcome="conflict", code="DUPLICATE_ITEM", complete=True, matched_count=len(matches)
        )
    match = matches[0]
    if request.external_id is not None and match["record_id"] != request.external_id:
        return ProjectionResult(
            outcome="conflict", code="EXTERNAL_ID_MISMATCH", complete=True, matched_count=1
        )
    remote = match["fields"]
    # 公开合同尚未确认空列可省略；缺键与明确 null 分开，不擅自填空。
    if not set(BASE_FIELDS).issubset(remote):
        return ProjectionResult(
            outcome="unknown", code="INCOMPLETE_READBACK", complete=True, matched_count=1
        )
    try:
        normalized = normalize_projection_fields(remote)
    except ValueError:
        return ProjectionResult(
            outcome="unknown", code="INVALID_READBACK", complete=True, matched_count=1
        )
    version = cast(int, normalized["SyncVersion"])  # 唯一共享 normalize 已严格校验。
    facts: dict[str, Any] = {
        "external_id": match["record_id"],
        "observed_version": version,
        "complete": True,
        "matched_count": 1,
        "observed_fields": normalized,
    }
    if version > request.projection.sync_version:
        return ProjectionResult(outcome="stale", code="STALE_PROJECTION", **facts)
    if version < request.projection.sync_version:
        return ProjectionResult(outcome="unknown", code="READBACK_OLDER", **facts)
    # 对齐只在共享 binding 内裁决，不复制 version/content 校验器。
    bound = bind_projection_result(
        request,
        ProjectionResult(
            outcome="verified",
            code="READBACK_VERIFIED",
            content_matches=True,
            **facts,
        ),
    )
    if bound.outcome != "verified":
        return bound.model_copy(update={"content_matches": False})
    return bound


def can_update_older(request: ProjectionRequest, result: ProjectionResult) -> bool:
    """完整且原 row 的较旧版本，仅不可变列匹配时允许更新为可信 PG 新版本。"""
    if not (
        result.outcome == "unknown"
        and result.code == "READBACK_OLDER"
        and result.complete
        and result.matched_count == 1
        and request.external_id is not None
        and result.external_id == request.external_id
        and result.observed_fields is not None
    ):
        return False
    changing = {
        "BusinessStatus",
        "ResolutionReason",
        "ResolvedBy",
        "ResolvedAt",
        "SyncVersion",
        "UpdatedAt",
    }
    actual = normalize_projection_fields(result.observed_fields)
    expected = normalize_projection_fields(request.projection.fields())
    return all(actual[key] == expected[key] for key in BASE_FIELDS if key not in changing)
