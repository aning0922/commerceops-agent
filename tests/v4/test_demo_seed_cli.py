"""Pure export publication regression: real local files, no DB or old case access."""

import errno
import hashlib
import json
import os
from pathlib import Path

import pytest
from commerceops.application.v4_demo.seed_contract import generate_seed

from scripts import v4_demo_seed as cli

pytestmark = pytest.mark.offline
GOLDEN_DIGEST = "59eaeab0006af3421fb3432d2c1c199d3064eb823dc0b5a4a8b18354822211e8"


def casefold_links(monkeypatch: pytest.MonkeyPatch) -> None:
    original = os.link

    def link(
        src: str,
        dst: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
        follow_symlinks: bool,
    ) -> None:
        assert not follow_symlinks
        if any(name.casefold() == dst.casefold() for name in os.listdir(dst_dir_fd)):
            raise FileExistsError(errno.EEXIST, "casefold target already exists")
        original(
            src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd, follow_symlinks=follow_symlinks
        )

    monkeypatch.setattr(os, "link", link)


@pytest.mark.parametrize("case_insensitive", [False, True])
def test_actual_export_publishes_distinct_index_and_preserves_fixed_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_insensitive: bool,
) -> None:
    if case_insensitive:
        casefold_links(monkeypatch)
    bundle = generate_seed()
    export = tmp_path.resolve() / "new-export"
    with cli.new_directory(export) as directory:
        cli.export_fixture(directory, bundle)
    assert {path.name for path in export.iterdir()} == {
        "content.json",
        "manifest.json",
        "INDEX.json",
    }
    content = (export / "content.json").read_bytes()
    assert content == bundle.canonical_content()
    assert hashlib.sha256(content).hexdigest() == GOLDEN_DIGEST
    assert (export / "manifest.json").read_bytes() == bundle.manifest.model_dump_json().encode()
    assert json.loads((export / "INDEX.json").read_bytes()) == dict(
        status="EXPORTED",
        content="content.json",
        manifest="manifest.json",
        content_digest=GOLDEN_DIGEST,
    )
    assert not os.path.samefile(export / "manifest.json", export / "INDEX.json")
    assert export.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in export.iterdir())


def test_legacy_manifest_case_alias_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    casefold_links(monkeypatch)
    export = tmp_path.resolve() / "legacy-name-reproduction"
    with cli.new_directory(export) as directory:
        cli.write(directory, "manifest.json", b"fixed-manifest")
        cli.write(directory, ".INDEX.pending", b"fixed-index")
        with pytest.raises(FileExistsError) as captured:
            os.link(
                ".INDEX.pending",
                "MANIFEST.json",
                src_dir_fd=directory,
                dst_dir_fd=directory,
                follow_symlinks=False,
            )
        assert captured.value.errno == errno.EEXIST
    assert (export / "manifest.json").read_bytes() == b"fixed-manifest"


@pytest.mark.parametrize("existing", ["INDEX.json", "index.JSON"])
def test_existing_index_or_case_alias_is_never_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    existing: str,
) -> None:
    casefold_links(monkeypatch)
    export = tmp_path.resolve() / "existing-index"
    with cli.new_directory(export) as directory:
        descriptor = os.open(
            existing, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(b"do-not-replace")
        with pytest.raises(FileExistsError) as captured:
            cli.export_fixture(directory, generate_seed())
        assert captured.value.errno == errno.EEXIST
    assert (export / existing).read_bytes() == b"do-not-replace"
    assert ".INDEX.pending" in {path.name for path in export.iterdir()}


def test_existing_directory_is_refused_without_repair(tmp_path: Path) -> None:
    export = tmp_path.resolve() / "existing-export"
    export.mkdir(mode=0o700)
    sentinel = export / "sentinel"
    sentinel.write_bytes(b"unchanged")
    with pytest.raises(FileExistsError), cli.new_directory(export):
        pytest.fail("existing directory must not be reused")
    assert sentinel.read_bytes() == b"unchanged"
    assert {path.name for path in export.iterdir()} == {"sentinel"}


def test_existing_file_symlink_is_not_followed(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    sentinel = root / "outside"
    sentinel.write_bytes(b"unchanged")
    with cli.new_directory(root / "new-export") as directory:
        os.symlink(sentinel, "content.json", dir_fd=directory)
        with pytest.raises(FileExistsError) as captured:
            cli.write(directory, "content.json", b"replacement")
        assert captured.value.errno == errno.EEXIST
    assert sentinel.read_bytes() == b"unchanged"
