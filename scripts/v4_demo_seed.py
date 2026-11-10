"""Explicit new-owned V4 fixture bootstrap; no old services or external sources."""

import argparse
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from commerceops.application.v4_demo.seed_contract import FixtureContent, SeedBundle, generate_seed
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.v4_demo_seed import gc_tenant, grant_v4_runtime, initialize_fixture


@contextmanager
def new_directory(path: Path) -> Iterator[int]:
    if not path.is_absolute() or ".." in path.parts or path == path.parent:
        raise ValueError("V4_EXPORT_DIRECTORY")
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        os.mkdir(path.name, mode=0o700, dir_fd=descriptor)
        child = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
        try:
            yield child
        finally:
            os.close(child)
    finally:
        os.close(descriptor)


def write(directory: int, name: str, data: bytes) -> None:
    if name not in ("content.json", "manifest.json", ".INDEX.pending"):
        raise ValueError("V4_EXPORT_FILE")
    fd = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def export_fixture(directory: int, bundle: SeedBundle) -> None:
    """Publish fixed seed files under exclusive, case-distinct physical names."""
    write(directory, "content.json", bundle.canonical_content())
    write(directory, "manifest.json", bundle.manifest.model_dump_json().encode())
    write(
        directory,
        ".INDEX.pending",
        json.dumps(
            dict(
                status="EXPORTED",
                content="content.json",
                manifest="manifest.json",
                content_digest=bundle.manifest.content_digest,
            ),
            sort_keys=True,
        ).encode(),
    )
    os.link(
        ".INDEX.pending",
        "INDEX.json",
        src_dir_fd=directory,
        dst_dir_fd=directory,
        follow_symlinks=False,
    )
    os.unlink(".INDEX.pending", dir_fd=directory)
    os.fsync(directory)


def main() -> None:
    parser = argparse.ArgumentParser(description="V4 new-owned fixture/ACL management")
    parser.add_argument("action", choices=("init-fixture", "grant-runtime", "verify-fixture", "gc"))
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--tenant", type=UUID)
    args = parser.parse_args()
    try:
        settings = DatabaseSettings()
        if not re.fullmatch(r"v4_demo_[a-z0-9_]{1,48}", settings.name):
            raise ValueError("V4_OWNED_DATABASE")
        if args.action == "init-fixture":
            if args.directory is None:
                raise ValueError("V4_EXPORT_DIRECTORY")
            with new_directory(args.directory) as directory:
                with connect(settings) as db:
                    bundle = initialize_fixture(db)
                # DB commit and file publish are separate; failure preserves original evidence.
                export_fixture(directory, bundle)
        elif args.action == "grant-runtime":
            with connect(settings) as db:
                grant_v4_runtime(db)
        elif args.action == "gc":
            if args.tenant is None:
                raise ValueError("V4_GC_TENANT_REQUIRED")
            with connect(settings) as db:
                gc_tenant(db, args.tenant)
        else:
            with connect(settings) as db:
                row = db.execute(
                    "SELECT canonical_content,content_hash FROM business.v4_demo_fixture_versions "
                    "WHERE version='v4-demo-seed-1'"
                ).fetchone()
                expected = generate_seed()
                if (
                    not row
                    or row["content_hash"] != expected.manifest.content_digest
                    or row["canonical_content"].encode() != expected.canonical_content()
                ):
                    raise ValueError("V4_FIXTURE_MISMATCH")
                FixtureContent.model_validate_json(row["canonical_content"])
        print(json.dumps(dict(status="OK", action=args.action, data_mode="demo_fixture")))
    except Exception:
        raise SystemExit(
            "V4_DEMO_OWNER_ACTION_FAILED; preserve original DB/export evidence"
        ) from None


if __name__ == "__main__":
    main()
