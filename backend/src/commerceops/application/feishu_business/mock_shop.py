"""受控Mock/test装配先核冻结fixture来源；不改源数据或放宽持久绑定。"""

from collections.abc import Mapping
from pathlib import Path

from commerceops.adapters.commerce.mock import Fixture

DIRECTORY = Path("tests/fixtures/commerce/inventory-v1")


def require_fixture_shop(row: Mapping[str, object], fixture_case: str) -> None:
    try:
        source = Fixture.load(DIRECTORY, fixture_case).source
    except ValueError:
        raise PermissionError("P4_CONTROLLED_FIXTURE_SCOPE_REQUIRED") from None
    if (
        row.get("external_shop_key") != source.shop_id
        or row.get("currency") != source.currency
        or row.get("timezone") != source.timezone
    ):
        raise PermissionError("P4_CONTROLLED_FIXTURE_SCOPE_REQUIRED")
