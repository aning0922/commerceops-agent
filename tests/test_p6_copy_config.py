"""Owned temporary non-secret files only; no credentials, DB or provider calls."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from commerceops.application.knowledge_copy.contracts import digest
from commerceops.infrastructure.knowledge_copy_config import CopyDeployment, load_copy_deployment

from tests.test_p6_copy_drafts import ORG, SHOP
from tests.test_p6_knowledge_copy_contracts import query

pytestmark = pytest.mark.offline


def config_body() -> dict[str, Any]:
    binding = dict(
        organization_id=str(ORG),
        shop_id=str(SHOP),
        query_ref="synthetic-name@v1",
        query_version="v1",
        query=query().model_dump(mode="json"),
    )
    binding["binding_digest"] = digest(binding)
    body = dict(
        schema_version="p6-copy-query-config-v1",
        enabled=True,
        bindings=[binding],
        provider_enabled=False,
        model_requests_enabled=False,
        publication_allowed=False,
    )
    return body | {"config_digest": digest(body)}


def write_config(path: Path, body: dict[str, Any]) -> str:
    raw = json.dumps(body, ensure_ascii=False).encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def test_off_reads_nothing_and_on_requires_explicit_raw_pin(tmp_path: Path) -> None:
    absent = tmp_path / "not-read"
    assert load_copy_deployment(absent) is None
    assert not absent.exists()
    with pytest.raises(ValueError, match="COPY_QUERY_CONFIGURATION_INVALID"):
        load_copy_deployment(enabled=True)
    path = tmp_path / "queries.json"
    pin = write_config(path, config_body())
    with pytest.raises(ValueError):
        load_copy_deployment(path, enabled=True)
    value = load_copy_deployment(path, enabled=True, expected_sha256=pin)
    assert value is not None
    mapping = value.queries()
    assert mapping[(ORG, SHOP, "synthetic-name@v1")] == query()
    with pytest.raises(TypeError):
        mapping[(ORG, SHOP, "other")] = query()  # type: ignore[index]
    assert not value.provider_enabled and not value.model_requests_enabled
    assert not value.publication_allowed


@pytest.mark.parametrize(
    "change", ["extra", "duplicate", "query", "version", "boolean", "provider"]
)
def test_rehashed_config_cannot_bypass_authority_type_or_query_pins(change: str) -> None:
    body = config_body()
    binding = body["bindings"][0]
    if change == "extra":
        binding["roles"] = ["approver"]
    elif change == "duplicate":
        body["bindings"].append(binding.copy())
    elif change == "query":
        binding["query"]["text"] = "replacement without its exact query hash"
    elif change == "version":
        binding["query_version"] = "v2"
    elif change == "boolean":
        body["publication_allowed"] = 0
    else:
        body["provider_enabled"] = True
    binding["binding_digest"] = digest({k: v for k, v in binding.items() if k != "binding_digest"})
    body["config_digest"] = digest({k: v for k, v in body.items() if k != "config_digest"})
    with pytest.raises(ValueError):
        CopyDeployment.model_validate_json(json.dumps(body))


@pytest.mark.parametrize(
    "failure",
    [
        "pin",
        "mode",
        "symlink",
        "directory_link",
        "relative",
        "parent",
        "large",
        "duplicate_json",
        "nan",
        "fifo",
    ],
)
def test_loader_rejects_unpinned_or_unsafe_owned_files(tmp_path: Path, failure: str) -> None:
    path = tmp_path / "queries.json"
    pin = write_config(path, config_body())
    if failure == "pin":
        pin = "0" * 64
    elif failure == "mode":
        path.chmod(0o644)
    elif failure == "symlink":
        link = tmp_path / "link"
        link.symlink_to(path)
        path = link
    elif failure == "directory_link":
        link = tmp_path / "dirlink"
        link.symlink_to(tmp_path, target_is_directory=True)
        path = link / path.name
    elif failure == "relative":
        path = Path("queries.json")
    elif failure == "parent":
        path = tmp_path / ".." / tmp_path.name / path.name
    elif failure == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    else:
        raw = (
            b" " * 32769
            if failure == "large"
            else (json.dumps(config_body())[:-1] + ',"enabled":true}').encode()
            if failure == "duplicate_json"
            else b'{"number":NaN}'
        )
        path.write_bytes(raw)
        pin = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="^COPY_QUERY_CONFIGURATION_INVALID$"):
        load_copy_deployment(path, enabled=True, expected_sha256=pin)


def test_changed_file_new_pin_still_requires_original_binding_digest(tmp_path: Path) -> None:
    body = config_body()
    body["bindings"][0]["shop_id"] = str(ORG)
    body["config_digest"] = digest({k: v for k, v in body.items() if k != "config_digest"})
    path = tmp_path / "queries.json"
    pin = write_config(path, body)
    with pytest.raises(ValueError):
        load_copy_deployment(path, enabled=True, expected_sha256=pin)


def test_loader_rejects_wrong_owner_and_nonboolean_enable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "queries.json"
    pin = write_config(path, config_body())
    monkeypatch.setattr("commerceops.infrastructure.web_config.os.geteuid", lambda: os.getuid() + 1)
    with pytest.raises(ValueError, match="^COPY_QUERY_CONFIGURATION_INVALID$"):
        load_copy_deployment(path, enabled=True, expected_sha256=pin)
    with pytest.raises(ValueError):
        load_copy_deployment(enabled=1)  # type: ignore[arg-type]
