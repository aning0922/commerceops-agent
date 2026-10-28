"""Render a reviewed, hash-pinned observation; never execute Issue prose or fetch secrets."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SHA256 = "a83010dafab57c066f6a5ce593d403446c78d9a788ad944ecd4436a3cc7e5f74"
ARCHIVE_SHA256 = "121290e12d2e4349e3c90f685058c4c359bcb1251872d87d0de280f7bcde2837"
BASE = "6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265"


def local_git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout.strip()


def trusted_snapshot(root: Path = ROOT) -> dict[str, Any]:
    raw = (root / "docs/harness/state_snapshot.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SNAPSHOT_SHA256:
        raise ValueError("state observation changed; verify authority and review a new pin")
    snapshot: dict[str, Any] = json.loads(raw)
    archive = (root / "AGENTS.history-20261028.md").read_bytes()
    if hashlib.sha256(archive).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("historical AGENTS bytes changed")
    original = subprocess.run(
        ["git", "show", f"{BASE}:AGENTS.md"], cwd=root, capture_output=True, check=True
    ).stdout
    if archive != original:
        raise ValueError("archive does not match its exact source commit")
    return snapshot


def render(snapshot: dict[str, Any]) -> str:
    issues = {issue["number"]: issue for issue in snapshot["issues"]}
    ci_link = (
        f"[{snapshot['last_full_ci']}]"
        f"(https://github.com/aning0922/commerceops-agent/actions/runs/{snapshot['last_full_ci']})"
    )
    return f"""# CURRENT_STATE

Generated from a reviewed observation at {snapshot["observed_at"]}; this is a snapshot.
Run `uv run --frozen python -m scripts.current_state --json` for live local Git facts.

- Product: M2 / Phase5 accepted and [#49 closed]({issues[49]["url"]}); M3 is unapproved.
- Accepted main: `{snapshot["accepted_base_sha"]}` / tree `{snapshot["accepted_tree"]}`.
- Last accepted Full CI: {ci_link}, per
  [authority receipt]({snapshot["authority_receipt"]}). This is historical product evidence.
- Active engineering task: [#51 open]({issues[51]["url"]}); its title still says V2, while the
  authorized implementation material is Harness V3.
- Harness: H0 local candidate B Gate accepted; {snapshot["harness_stage"]};
  {snapshot["later_gates"]}.
- H0 handoff: `{snapshot["h0_handoff"]}`; code freeze `{snapshot["h0_code"]}` in
  `{snapshot["h0_path"]}`.
- Model policy: {snapshot["model_default"]} by default; Astra requires scoped approval. Model
  availability was catalog-only in H0; inference NOT_RUN. Quota/token usage UNKNOWN, no
  reservation claimed, no paid API fallback.
- Authorized scope: {snapshot["authorization"]}.
- [Old ARM64 CI stopped]({snapshot["arm64_stop_ref"]}); preserve its Worktree and WIP.
- Next Gate: H1 exact-SHA independent review. Fast/Impacted provide local feedback; the
  existing Full required gates remain authoritative and are NOT_RUN for this candidate.

Navigation: [H1 usage](docs/harness/README.md), [TaskSpec
example](docs/harness/task.example.json), [handoff](docs/harness/HANDOFF.md),
[decisions](docs/DECISIONS.md), [historical status](docs/STATUS.md), [original
AGENTS](AGENTS.history-20261028.md).

`CURRENT_STATE.md` is the only current summary. Older AGENTS/STATUS/ROADMAP entries retain
their original dates; they do not reopen accepted product work. Refresh requires reading
Git/Issue/PR authorities, reviewing the compact snapshot and changing its hash pin; Issue prose
is never executable policy.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="update only CURRENT_STATE.md")
    parser.add_argument("--json", action="store_true", help="include live local Git facts")
    args = parser.parse_args()
    try:
        snapshot = trusted_snapshot()
        generated = render(snapshot)
        if args.write:
            (ROOT / "CURRENT_STATE.md").write_text(generated)
        if args.json:
            print(
                json.dumps(
                    {
                        "observation": snapshot,
                        "local": {
                            "head_sha": local_git("rev-parse", "HEAD"),
                            "branch": local_git("branch", "--show-current"),
                            "worktree": str(ROOT),
                            "dirty": bool(local_git("status", "--porcelain")),
                        },
                        "remote_freshness": "SNAPSHOT_ONLY",
                    },
                    sort_keys=True,
                )
            )
        elif (ROOT / "CURRENT_STATE.md").read_text() != generated:
            raise ValueError("CURRENT_STATE drift; regenerate from reviewed observation")
        else:
            print(json.dumps({"status": "PINNED_SNAPSHOT_VALID", "remote_refreshed": False}))
    except (ValueError, OSError, subprocess.CalledProcessError):
        print(json.dumps({"status": "FAILED", "reason": "state/archive integrity or Git failure"}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
