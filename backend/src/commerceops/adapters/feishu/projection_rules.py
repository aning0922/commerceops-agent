"""纯错误/版本/回读策略；没有重试、调度、事务或业务状态修改。"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from commerceops.adapters.feishu.projection_contract import (
    BASE_FIELDS,
    EMPTY_FIELDS,
    ApiReply,
    ProjectionContractError,
    ProjectionFields,
    positive_integer,
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
    if reply.http_status == 429:
        return WriteOutcome.DEFERRED if reply.code != 0 else WriteOutcome.UNKNOWN
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


class ReadbackOutcome(StrEnum):
    MATCHED = "matched"
    MISSING = "missing"  # 完整分页零行也不证明 unknown 写未成功。
    CONFLICT = "conflict"
    INCOMPLETE = "incomplete"
    OLDER = "older"
    NEWER = "newer"


@dataclass(frozen=True)
class Readback:
    outcome: ReadbackOutcome
    record_id: str | None = field(default=None, repr=False)


def readback_rows(
    fields: ProjectionFields,
    rows: list[dict[str, Any]],
    *,
    expected_record_id: str | None = None,
) -> Readback:
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
            or type(remote.get("CommerceOpsItemID")) is not str
        ):
            return Readback(ReadbackOutcome.INCOMPLETE)
        seen.add(record_id)
        if remote["CommerceOpsItemID"] == fields.item_id:
            matches.append(row)
    if not matches:
        return Readback(ReadbackOutcome.MISSING)
    if len(matches) != 1:
        return Readback(ReadbackOutcome.CONFLICT)
    match = matches[0]
    if expected_record_id is not None and match["record_id"] != expected_record_id:
        return Readback(ReadbackOutcome.CONFLICT)
    remote = match["fields"]
    # 公开合同尚未确认空列可省略；缺键与明确 null 分开，不擅自填空。
    if not set(BASE_FIELDS).issubset(remote):
        return Readback(ReadbackOutcome.INCOMPLETE)
    normalized = {
        key: "" if key in EMPTY_FIELDS and remote[key] is None else remote[key]
        for key in BASE_FIELDS
    }
    try:
        remote_version = positive_integer(normalized["SyncVersion"])
    except ProjectionContractError:
        return Readback(ReadbackOutcome.CONFLICT)
    if remote_version > fields.version:
        return Readback(ReadbackOutcome.NEWER)
    if remote_version < fields.version:
        return Readback(ReadbackOutcome.OLDER)
    if normalized != fields.as_fields():
        return Readback(ReadbackOutcome.CONFLICT)
    return Readback(ReadbackOutcome.MATCHED, match["record_id"])


def is_current(fields: ProjectionFields, current_pg_version: int) -> bool:
    """A 在持有唯一 Worker/同表锁时提供当前 PG 版本；纯比较不替代该锁。"""
    if type(current_pg_version) is not int or current_pg_version < 1:
        raise ProjectionContractError()
    return fields.version == current_pg_version
