"""SDK固定窗口/方法cap/合法业务与零业务scope；不连接PG或平台。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.sdk_window import SDKScope, SDKWindow

pytestmark = pytest.mark.offline


def test_method_caps_are_copied_immutable_and_default_gate_is_closed() -> None:
    caps = {"im.v1.message.create": 1}
    window = SDKWindow(uuid4(), uuid4(), uuid4(), datetime.now(UTC) + timedelta(seconds=1), caps)  # type: ignore[arg-type]
    caps["im.v1.message.create"] = 20
    assert window.caps["im.v1.message.create"] == 1
    assert not window.allows("im.v1.message.create")
    with pytest.raises(TypeError):
        window.caps["im.v1.message.create"] = 20  # type: ignore[index]


@pytest.mark.parametrize("cap", [True, 0, -1, 501])
def test_unsafe_caps_cannot_construct_window(cap: int) -> None:
    with pytest.raises(ValueError):
        SDKWindow(uuid4(), uuid4(), uuid4(), datetime.now(UTC), {"im.v1.message.create": cap})


def test_expired_gate_never_reopens_and_scope_does_not_fake_a_clarification_task() -> None:
    window = SDKWindow(
        uuid4(),
        uuid4(),
        uuid4(),
        datetime.now(UTC) - timedelta(seconds=1),
        {"im.v1.message.create": 1},
        enabled=True,
    )
    assert not window.allows("im.v1.message.create")
    SDKScope(uuid4(), None, "preflight")
    SDKScope(uuid4(), None, "clarification")
    SDKScope(uuid4(), uuid4(), "approval_card")
    with pytest.raises(ValueError):
        SDKScope(uuid4(), uuid4(), "clarification")
    with pytest.raises(ValueError):
        SDKScope(uuid4(), None, "base_projection")
