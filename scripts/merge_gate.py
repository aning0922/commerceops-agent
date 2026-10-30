"""Fail closed on the current Full workflow's actual dependency results and checkout."""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_JOBS = frozenset({"quality", "phase3", "pg-pair", "frontend", "n01-web"})


def validate(needs: Any, source_sha: str, source_tree: str) -> None:
    if not isinstance(needs, dict) or set(needs) != REQUIRED_JOBS:
        raise ValueError("missing or unexpected Full dependency")
    if any(re.fullmatch(r"[0-9a-f]{40}", value) is None for value in (source_sha, source_tree)):
        raise ValueError("invalid current checkout identity")
    for job in sorted(REQUIRED_JOBS):
        row = needs[job]
        if (
            not isinstance(row, dict)
            or set(row) != {"result", "outputs"}
            or row["result"] != "success"
            or not isinstance(row["outputs"], dict)
        ):
            raise ValueError(f"Full dependency did not actually succeed: {job}")
        expected = (
            {"source_sha": source_sha, "source_tree": source_tree} if job == "n01-web" else {}
        )
        if row["outputs"] != expected:
            raise ValueError(f"Full dependency source/output mismatch: {job}")


def main() -> None:
    try:
        source_sha, source_tree = (
            subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True).strip()
            for ref in ("HEAD", "HEAD^{tree}")
        )
        if source_sha != os.environ["GITHUB_SHA"]:
            raise ValueError("checkout is not the current GitHub merge/source SHA")
        validate(json.loads(os.environ["MERGE_GATE_NEEDS"]), source_sha, source_tree)
    except (KeyError, ValueError, OSError, subprocess.SubprocessError) as error:
        # Never echo untrusted context, environment, credentials or raw JSON.
        raise SystemExit(f"Full merge gate rejected ({type(error).__name__})") from None
    print("Full merge gate passed: all five current-run dependencies succeeded; exact source bound")


if __name__ == "__main__":
    main()
