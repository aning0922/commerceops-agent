"""Pinned actionlint pre-publish check; no installation, network or CI dispatch."""

import hashlib
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.7.12"
# Official release archives were checksum verified before extracting these executables.
BINARY_SHA256 = {
    ("Darwin", "arm64"): "8db11704dc296f096216db4db65d86cd7f0ebfdf4c38453a1da276b137b88388",
    ("Linux", "x86_64"): "c872d6db8c6bf83a8eaa704fc93999f027d55dffbc63b8a6abdccb47df5f4cd4",
}


def executable() -> Path:
    binary = ROOT / ".tools/actionlint"
    expected = BINARY_SHA256.get((platform.system(), platform.machine()))
    if (
        expected is None
        or not binary.is_file()
        or binary.is_symlink()
        or not binary.resolve().is_relative_to(ROOT)
        or hashlib.sha256(binary.read_bytes()).hexdigest() != expected
    ):
        raise ValueError("pinned local actionlint unavailable; see docs/harness/h3/README.md")
    return binary


def main() -> None:
    try:
        binary = executable()
        workflows = sorted((ROOT / ".github/workflows").glob("*.y*ml"))
        if not workflows or any(
            p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(ROOT)
            for p in workflows
        ):
            raise ValueError("actual workflow files required")
        result = subprocess.run(
            [str(binary), "-shellcheck=", "-pyflakes=", *map(str, workflows)],
            cwd=ROOT,
            timeout=30,
            check=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Workflow semantics NOT_VERIFIED: {error}") from None
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
