"""Read-only V41 owned-run admission; no service launch or private-config fallback."""

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tests.e2e.v4.owned_driver import validate_subnets

INPUTS = frozenset(
    {
        "uv.lock",
        "docs/v4/v4-1/CONTRACTS.md",
        "docs/v4/v4-1/API_CONTRACT.json",
        "backend/migrations/versions/0025_v41_catalog_operations.py",
        "frontend/lib/v41-schema.json",
    }
)
SCENARIOS = frozenset(
    {
        "shell_navigation",
        "dashboard_same_source",
        "catalog_orders",
        "import_csv",
        "import_xlsx",
    }
)


@dataclass(frozen=True)
class OwnedManifest:
    source_sha: str
    source_tree: str
    inputs: dict[str, str]
    scenario: str
    project: str
    database: str
    directory: str
    pg_image: str
    test_image: str
    api_port: int
    web_port: int
    pg_subnet: str
    host_subnet: str
    starts_at: str
    deadline: str
    parent_deadline: str
    uid: int

    def validate(self, root: Path, now: datetime, *, prepared: bool = False) -> None:
        if not root.is_absolute() or root.resolve() != root:
            raise ValueError("canonical source root required")
        if self.scenario not in SCENARIOS or self.uid != os.getuid() or type(self.uid) is not int:
            raise ValueError("fixed scenario and current owner required")
        if not re.fullmatch(r"v41qa_[a-z0-9_]{8,32}", self.project):
            raise ValueError("new V41 project namespace required")
        if not re.fullmatch(r"v4_demo_v41_[a-z0-9_]{1,40}", self.database):
            raise ValueError("new V41 demo database required")
        path = Path(self.directory)
        if (
            not path.is_absolute()
            or path.resolve() != path
            or (path.exists() and not prepared)
            or not path.parent.is_dir()
        ):
            raise ValueError("new canonical case directory required")
        if prepared:
            info = path.lstat()
            if not path.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o777 != 0o700:
                raise ValueError("owner-private prepared directory required")
        if (
            any(
                type(p) is not int or not 1024 <= p <= 65535 for p in (self.api_port, self.web_port)
            )
            or len({self.api_port, self.web_port}) != 2
        ):
            raise ValueError("distinct explicit loopback ports required")
        validate_subnets(self.pg_subnet, self.host_subnet)
        for image in (self.pg_image, self.test_image):
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
                raise ValueError("exact Root-bound image IDs required")
        start, end, parent = [
            datetime.fromisoformat(s) for s in (self.starts_at, self.deadline, self.parent_deadline)
        ]
        if any(
            t.tzinfo is None or t.utcoffset() != UTC.utcoffset(t) for t in (start, end, parent, now)
        ):
            raise ValueError("explicit UTC window required")
        if (
            not start <= now < end <= parent
            or not 180 < (end - now).total_seconds()
            or (end - start).total_seconds() > 1800
        ):
            raise ValueError("active bounded window and cleanup reserve required")
        for value in (self.source_sha, self.source_tree):
            if not re.fullmatch(r"[a-f0-9]{40}", value):
                raise ValueError("exact committed source required")

        def git(*args: str) -> str:
            return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

        if (
            git("rev-parse", "HEAD") != self.source_sha
            or git("rev-parse", "HEAD^{tree}") != self.source_tree
        ):
            raise ValueError("source binding differs")
        if git("status", "--porcelain"):
            raise ValueError("clean source required")
        if set(self.inputs) != INPUTS:
            raise ValueError("exact V41 migration/contract/schema/lock input set required")
        for name, digest in self.inputs.items():
            public = root / name
            if (
                public.resolve() != public
                or not public.is_file()
                or not re.fullmatch(r"[a-f0-9]{64}", digest)
            ):
                raise ValueError("fixed regular public input required")
            if hashlib.sha256(public.read_bytes()).hexdigest() != digest:
                raise ValueError("public input hash differs")

    def preflight(self, root: Path, now: datetime) -> dict[str, str]:
        self.validate(root, now)
        return {
            "status": "PUBLIC_BINDINGS_VALIDATED_ONLY",
            "source_sha": self.source_sha,
            "source_tree": self.source_tree,
            "image_inventory": "NOT_INSPECTED",
            "actual_ipam_ports_namespace": "NOT_INSPECTED",
            "runtime": "NOT_RUN",
            "next_gate": "ROOT_RUNTIME_BINDING_PENDING",
        }
