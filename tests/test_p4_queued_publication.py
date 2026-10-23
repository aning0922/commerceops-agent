"""Completion-bound event/ACK reads; legacy transport fixtures remain explicit."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.p4_queued_transport import OwnedPublicationError, completed_owned_body

pytestmark = pytest.mark.offline
PUBLISHER = "a" * 64


def publish(path: Path, body: bytes, **changes: object) -> None:
    path.write_bytes(body)
    path.chmod(0o600)
    marker = path.with_name(".complete-" + path.name + ".json")
    marker.write_text(
        json.dumps(
            {
                "schema": "owned-save-complete-v1",
                "publisher_sha256": PUBLISHER,
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                **changes,
            }
        )
    )
    marker.chmod(0o600)


def test_partial_body_has_no_admission_without_completion(tmp_path: Path) -> None:
    path = tmp_path / "event-partial.json"
    path.write_bytes(b'{"partial":')
    path.chmod(0o600)
    assert completed_owned_body(path, publisher_sha256=PUBLISHER) is None
    publish(path, b'{"complete":true}')
    assert completed_owned_body(path, publisher_sha256=PUBLISHER) == b'{"complete":true}'


@pytest.mark.parametrize(
    "changes",
    [{"schema": "other"}, {"publisher_sha256": "b" * 64}, {"bytes": 1}, {"sha256": "0" * 64}],
)
def test_completed_invalid_metadata_fails_closed(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    path = tmp_path / "event-invalid.json"
    publish(path, b'{"complete":true}', **changes)
    with pytest.raises(OwnedPublicationError, match="^OWNED_PUBLICATION_INVALID$"):
        completed_owned_body(path, publisher_sha256=PUBLISHER)


@pytest.mark.parametrize("body", [b'{"truncated":', b"[]"])
def test_hash_valid_invalid_json_object_never_dispatches(tmp_path: Path, body: bytes) -> None:
    path = tmp_path / "event-invalid-json.json"
    publish(path, body)
    with pytest.raises(OwnedPublicationError) as result:
        completed_owned_body(path, publisher_sha256=PUBLISHER)
    assert result.value.stage == "json_object"


def test_private_fd_rejects_symlink_and_nonprivate_body(tmp_path: Path) -> None:
    path = tmp_path / "event-private.json"
    publish(path, b"{}")
    path.chmod(0o644)
    with pytest.raises(OwnedPublicationError):
        completed_owned_body(path, publisher_sha256=PUBLISHER)
    path.chmod(0o600)
    real = tmp_path / "real.json"
    os.rename(path, real)
    path.symlink_to(real)
    with pytest.raises(OwnedPublicationError):
        completed_owned_body(path, publisher_sha256=PUBLISHER)
