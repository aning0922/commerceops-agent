"""Pure construction/owned-file guards only; seed SQL and real Web remain Root's gates."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.knowledge_copy_config import load_copy_deployment

from scripts import m3_copy_demo as demo

pytestmark = pytest.mark.offline


def settings(name: str = "m3_daily_demo_local", user: str = "owned_owner") -> DatabaseSettings:
    return DatabaseSettings(
        host="owned.invalid",
        name=name,
        user=user,
        password_file=Path("/not-read"),
        runtime_password_file=None,
    )


@pytest.mark.parametrize(
    "database,user",
    [
        ("postgres", "owner"),
        ("m3_daily_demo_", "owner"),
        ("m3_daily_demo_OLD", "owner"),
        ("m3_daily_demo_local", "commerceops_app"),
    ],
)
def test_invalid_database_stops_before_connect(
    database: str,
    user: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_: object) -> None:
        raise AssertionError("must not connect")

    monkeypatch.setattr(demo, "connect", forbidden)
    with pytest.raises(ValueError, match="NEW_OWNED_DEMO_REQUIRED"):
        demo.seed_demo(settings(database, user), UUID(int=1), UUID(int=2))


def test_explicit_database_and_absolute_new_target_are_required(tmp_path: Path) -> None:
    for directory in (Path("relative"), tmp_path / ".." / "other", Path("/")):
        with pytest.raises(ValueError):
            demo.validate_target(settings(), "m3_daily_demo_local", directory)
    with pytest.raises(ValueError):
        demo.validate_target(settings(), "m3_daily_demo_other", tmp_path / "new")


def test_synthetic_export_keeps_original_scope_and_false_provider_flags(tmp_path: Path) -> None:
    now = datetime(2026, 11, 3, 7, tzinfo=UTC)
    registry, corpus, product, config, command = demo.synthetic_bundle(
        UUID(int=1), UUID(int=2), UUID(int=3), now
    )
    assert registry.scope == product.snapshot.scope == corpus[0].citation.chunk.document.scope
    assert registry.manifest_digest == command.registry_digest
    assert product.snapshot.expires_at == now + timedelta(hours=1)
    assert command.reviewer_id == UUID(int=3) and command.query_ref.endswith("@v1")
    body = demo.encoded(config.model_dump(mode="json"))
    directory = tmp_path / "copy"
    with demo.output_directory(directory) as descriptor:
        demo.write_owned(descriptor, "copy-config.json", body)
        demo.write_owned(
            descriptor, "copy-create.json", demo.encoded(command.model_dump(mode="json"))
        )
        with pytest.raises(FileExistsError):
            demo.write_owned(descriptor, "copy-config.json", body)
        with pytest.raises(ValueError):
            demo.write_owned(descriptor, "local-session", b"not-a-session")
    loaded = load_copy_deployment(
        directory / "copy-config.json",
        enabled=True,
        expected_sha256=hashlib.sha256(body).hexdigest(),
    )
    assert loaded == config and loaded is not None
    assert not loaded.provider_enabled and not loaded.model_requests_enabled
    assert not loaded.publication_allowed
    assert (directory.stat().st_mode & 0o777) == 0o700
    assert ((directory / "copy-config.json").stat().st_mode & 0o777) == 0o600
    assert set(json.loads((directory / "copy-create.json").read_text())) == {
        "schema_version",
        "shop_id",
        "registry_id",
        "registry_digest",
        "product_source_id",
        "query_ref",
        "reviewer_id",
        "request_key",
    }
    with pytest.raises(FileExistsError), demo.output_directory(directory):
        raise AssertionError("existing directory must not be reused")


def test_symlink_parent_is_rejected_without_writes(tmp_path: Path) -> None:
    link = tmp_path / "alias"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError), demo.output_directory(link / "new"):
        raise AssertionError("symlink parent must not be followed")
    assert not (tmp_path / "new").exists()


def test_help_does_not_load_settings_or_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["m3_copy_demo", "--help"])

    def forbidden() -> None:
        raise AssertionError("must not load credentials")

    monkeypatch.setattr(demo, "DatabaseSettings", forbidden)
    with pytest.raises(SystemExit) as result:
        demo.main()
    assert result.value.code == 0
