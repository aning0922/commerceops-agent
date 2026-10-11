"""Base 适配器本地字段合同；共享 PG DTO 由 A 冻结后另行映射。"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

BASE_FIELDS = (
    "CommerceOpsItemID",
    "TaskID",
    "SKU",
    "Quantity",
    "Risk",
    "Window",
    "SourceMode",
    "ApprovalStatus",
    "ApprovedBy",
    "BusinessStatus",
    "ResolutionReason",
    "ResolvedBy",
    "ResolvedAt",
    "SyncVersion",
    "UpdatedAt",
)
EMPTY_FIELDS = frozenset({"ResolutionReason", "ResolvedBy", "ResolvedAt"})


class ProjectionContractError(ValueError):
    def __init__(self) -> None:
        super().__init__("BASE_PROJECTION_CONTRACT_INVALID")


def positive_integer(value: object) -> int:
    if type(value) is not str or re.fullmatch(r"[1-9][0-9]{0,63}", value) is None:
        raise ProjectionContractError()
    return int(value)


def canonical_uuid(value: object, *, v4: bool = False) -> str:
    if type(value) is not str:
        raise ProjectionContractError()
    try:
        parsed = UUID(value)
    except ValueError:
        raise ProjectionContractError() from None
    if str(parsed) != value or (v4 and parsed.version != 4):
        raise ProjectionContractError()
    return value


def utc_timestamp(value: str) -> None:
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        raise ProjectionContractError() from None
    if stamp.utcoffset() != timedelta(0):
        raise ProjectionContractError()


@dataclass(frozen=True)
class ProjectionFields:
    """已序列化的十五文本列快照；不是 PG/审批输入，也不生成 token。"""

    values: tuple[tuple[str, str], ...] = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.values) is not tuple
            or len(self.values) != len(BASE_FIELDS)
            or any(
                type(pair) is not tuple
                or len(pair) != 2
                or type(pair[0]) is not str
                or type(pair[1]) is not str
                for pair in self.values
            )
        ):
            raise ProjectionContractError()
        fields = dict(self.values)
        if tuple(fields) != BASE_FIELDS or any(
            len(value) > 2000 or (not value.strip() and key not in EMPTY_FIELDS)
            for key, value in fields.items()
        ):
            raise ProjectionContractError()
        canonical_uuid(fields["CommerceOpsItemID"])
        canonical_uuid(fields["TaskID"])
        positive_integer(fields["Quantity"])
        positive_integer(fields["SyncVersion"])
        utc_timestamp(fields["UpdatedAt"])
        if fields["ApprovalStatus"] != "approved":
            raise ProjectionContractError()
        status = fields["BusinessStatus"]
        if status == "open":
            if any(fields[key] for key in EMPTY_FIELDS):
                raise ProjectionContractError()
        elif status in {"completed", "closed"}:
            if any(not fields[key].strip() for key in EMPTY_FIELDS):
                raise ProjectionContractError()
            utc_timestamp(fields["ResolvedAt"])
        else:
            raise ProjectionContractError()

    @classmethod
    def from_fields(cls, fields: dict[str, str]) -> "ProjectionFields":
        if type(fields) is not dict or set(fields) != set(BASE_FIELDS):
            raise ProjectionContractError()
        return cls(tuple((key, fields[key]) for key in BASE_FIELDS))

    def as_fields(self) -> dict[str, str]:
        return dict(self.values)

    def wire_fields(self) -> dict[str, str | None]:
        # update 是增量操作，空值必须发送 null，否则旧终态原因可能残留。
        return {key: value if value else None for key, value in self.values}

    @property
    def item_id(self) -> str:
        return dict(self.values)["CommerceOpsItemID"]

    @property
    def version(self) -> int:
        return positive_integer(dict(self.values)["SyncVersion"])


@dataclass(frozen=True)
class ApiReply:
    http_status: int | None
    code: int | None
    data: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def success(self) -> bool:
        return (
            type(self.http_status) is int
            and 200 <= self.http_status < 300
            and type(self.code) is int
            and self.code == 0
        )


class RecordTransport(Protocol):
    async def create(
        self,
        app_token: str,
        table_id: str,
        token: str,
        fields: ProjectionFields,
        *,
        deadline: float | None = None,
    ) -> ApiReply: ...

    async def list(
        self,
        app_token: str,
        table_id: str,
        page_token: str | None,
        *,
        deadline: float | None = None,
    ) -> ApiReply: ...

    async def update(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: ProjectionFields,
        *,
        deadline: float | None = None,
    ) -> ApiReply: ...
