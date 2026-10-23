"""A 已审 d039 的唯一共享 DTO re-export，以及 B 的低层 SDK 协议。"""

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from commerceops.application.feishu_business.contracts import (
    BASE_FIELDS as BASE_FIELDS,
)
from commerceops.application.feishu_business.contracts import (
    BaseProjectionAdapter as BaseProjectionAdapter,
)
from commerceops.application.feishu_business.contracts import (
    ItemProjection as ItemProjection,
)
from commerceops.application.feishu_business.contracts import (
    ProjectionRequest as ProjectionRequest,
)
from commerceops.application.feishu_business.contracts import (
    ProjectionResult as ProjectionResult,
)
from commerceops.application.feishu_business.contracts import (
    bind_projection_result as bind_projection_result,
)
from commerceops.application.feishu_business.contracts import (
    normalize_projection_fields as normalize_projection_fields,
)


class ProjectionContractError(ValueError):
    def __init__(self) -> None:
        super().__init__("BASE_PROJECTION_CONTRACT_INVALID")


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
        projection: ItemProjection,
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
        projection: ItemProjection,
        *,
        deadline: float | None = None,
    ) -> ApiReply: ...
