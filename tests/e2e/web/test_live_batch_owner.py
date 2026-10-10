"""三类测试owner登记边界；纯离线，不启动进程或PG。"""

import os
from pathlib import Path

import pytest

from tests.e2e.web.live_batch_owner import OWNERS, verify

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("owner", OWNERS.values())
def test_closed_owner_in_current_checkout(tmp_path: Path, owner: str) -> None:
    tmp_path.chmod(0o700)
    verify(tmp_path, registration(tmp_path, owner), "items")


def registration(directory: Path, owner: str = OWNERS["b"]) -> dict[str, object]:
    return {
        "owner": owner,
        "owner_uid": os.getuid(),
        "checkout": str(Path(__file__).resolve().parents[3]),
        "private_directory": str(directory.resolve()),
        "project": "p3b04-items-0123456789",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner", "other"),
        ("owner_uid", -1),
        ("checkout", "/other-checkout"),
        ("private_directory", "/other-private"),
        ("project", "p3b04-write-0123456789"),
        ("project", "p3b04-items-unknown"),
    ],
)
def test_foreign_registration_rejected(tmp_path: Path, field: str, value: object) -> None:
    tmp_path.chmod(0o700)
    window = registration(tmp_path)
    window[field] = value
    with pytest.raises(ValueError, match="registration"):
        verify(tmp_path, window, "items")


def test_nonprivate_directory_rejected(tmp_path: Path) -> None:
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match="registration"):
        verify(tmp_path, registration(tmp_path), "items")
