"""当前 Web operator/shop 的 N01 只读业务 preflight；不持久原句/草稿。"""

from typing import Any

from commerceops.adapters.commerce.mock import Fixture
from commerceops.application.commerce.inventory_analysis import _native_input_value
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.application.replenishment.nl_preflight import (
    PreflightInput,
    Window,
    parse_preflight,
)
from commerceops.domain.commerce_values import complete_days
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.replenishment_repository import ReplenishmentStore, has_capability
from commerceops.infrastructure.web_sessions import envelope, role_scope


class WebPreflightStore:
    def __init__(self, store: ReplenishmentStore):
        self.store = store

    def authorize(self, actor: WebActor) -> None:
        if not isinstance(actor, WebActor):
            raise WebFailure("ACCESS_DENIED", 403)
        with connect(self.store.settings) as db:
            if not has_capability(db, actor, "operator"):
                raise WebFailure("ACCESS_DENIED", 403)

    def parse(self, actor: WebActor, request: PreflightInput) -> dict[str, Any]:
        if not isinstance(actor, WebActor):
            raise WebFailure("ACCESS_DENIED", 403)
        with connect(self.store.settings) as db:
            if not has_capability(db, actor, "operator"):
                raise WebFailure("ACCESS_DENIED", 403)
            request = PreflightInput.model_validate(_native_input_value(request))
            if not role_scope(db, actor, request.shop_id, "operator"):
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            row = db.execute(
                """SELECT external_shop_key,currency,timezone FROM business.shops
                WHERE id=%s AND organization_id=%s AND adapter_kind='mock'
                AND environment IN ('mock','test') FOR SHARE""",
                (request.shop_id, actor.organization_id),
            ).fetchone()
            if not row:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            try:
                fixture = Fixture.load(self.store.fixture_directory, request.fixture_case)
            except (ValueError, KeyError, OSError):
                raise WebFailure("INVALID_REQUEST", 422) from None
            if (row["external_shop_key"], row["currency"], row["timezone"]) != (
                fixture.source.shop_id,
                fixture.source.currency,
                fixture.source.timezone,
            ):
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            start, end = complete_days(fixture.now, fixture.source.timezone)
            result = parse_preflight(
                request,
                Window(
                    start=start,
                    end=end,
                    timezone=fixture.source.timezone,
                    as_of=fixture.now,
                ),
            )
            return envelope(db, preflight=result.model_dump(mode="json"))
