"""受控装配本地fixture绑定；没有PG/SDK/Secret或状态修复。"""

import pytest
from commerceops.application.feishu_business.mock_shop import require_fixture_shop

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("case", ["baseline", "known_inbound"])
def test_matching_frozen_mock_shop_is_accepted(case: str) -> None:
    require_fixture_shop(
        {"external_shop_key": "demo", "currency": "CNY", "timezone": "Asia/Shanghai"}, case
    )


@pytest.mark.parametrize(
    "change",
    [
        {"external_shop_key": "p4-ro-only"},
        {"currency": "USD"},
        {"timezone": "UTC"},
    ],
)
def test_wrong_mock_shop_metadata_is_rejected_without_normalizing(change: dict[str, str]) -> None:
    row = {"external_shop_key": "demo", "currency": "CNY", "timezone": "Asia/Shanghai"}
    row.update(change)
    original = dict(row)
    with pytest.raises(PermissionError, match="^P4_CONTROLLED_FIXTURE_SCOPE_REQUIRED$"):
        require_fixture_shop(row, "known_inbound")
    assert row == original


def test_missing_or_untrusted_fixture_is_rejected() -> None:
    cases: tuple[tuple[dict[str, object], str], ...] = (
        ({}, "known_inbound"),
        ({}, "not_a_fixture"),
    )
    for row, case in cases:
        with pytest.raises(PermissionError, match="^P4_CONTROLLED_FIXTURE_SCOPE_REQUIRED$"):
            require_fixture_shop(row, case)
