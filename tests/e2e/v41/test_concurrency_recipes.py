"""Race verdict boundary tests only; these are not concurrent HTTP or PG evidence."""

import copy
from typing import Any
from uuid import uuid4

import pytest

from .concurrency_recipes import receipts

pytestmark = pytest.mark.offline


def committed() -> dict[str, Any]:
    return {
        "status": "COMMITTED",
        "data": {"receipt": {"operation": "product_tags", "request_key": str(uuid4())}},
    }


def test_same_key_requires_two_identical_committed_receipts() -> None:
    one = committed()
    assert receipts([one, copy.deepcopy(one)], same_key=True) == one["data"]["receipt"]
    with pytest.raises(AssertionError, match="DIVERGED"):
        receipts([one, committed()], same_key=True)
    with pytest.raises(AssertionError, match="DIVERGED"):
        receipts([one, {"status": "UNKNOWN"}], same_key=True)


def test_distinct_keys_require_one_commit_and_expected_conflict() -> None:
    one = committed()
    denied = {"status": "REJECTED", "error": {"code": "VERSION_CONFLICT"}}
    assert receipts([one, denied], same_key=False) == one["data"]["receipt"]
    for bad in [committed(), {"status": "UNKNOWN"}, {**denied, "error": {"code": "ACCESS_DENIED"}}]:
        with pytest.raises(AssertionError):
            receipts([one, bad], same_key=False)
