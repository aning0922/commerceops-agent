"""V4 QA preparation only: inspect committed contracts and a proposed owned window.

No network, Docker, credential generation, service launch or cleanup capability.
Successful validation is not runtime authorization or an E2E result.
"""

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "docs/v4/baseline"
CONTRACTS = (
    "DOMAIN_SOURCE_CONTRACT.md",
    "PERMISSION_DEMO_CONTRACT.md",
    "UI_ROUTES_CONTRACT.md",
    "API_EVENTS_CONTRACT.md",
    "v4-public-openapi.json",
)
OPERATIONS = {
    "bootstrap",
    "createDemoSession",
    "readCurrentDemoSession",
    "switchDemoPersona",
    "readDemoSeedSummary",
    "resetCurrentDemoTenant",
    "logoutDemoSession",
    "readDemoControlReceipt",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, timeout=10).strip()


def contract_inventory() -> dict[str, Any]:
    schema = json.loads((BASELINE / "v4-public-openapi.json").read_text())
    operations = [
        operation
        for path in schema["paths"].values()
        for method, operation in path.items()
        if method in {"get", "post"}
    ]
    if len(operations) != 8 or {op["operationId"] for op in operations} != OPERATIONS:
        raise ValueError("frozen eight-operation inventory changed; Root review required")
    for path in schema["paths"].values():
        if "post" not in path:
            continue
        op = path["post"]
        body = op["requestBody"]["content"]["application/json"]["schema"]
        headers = {p["name"] for p in op["parameters"] if p.get("required")}
        if body.get("additionalProperties") is not False or not {"Origin", "X-CSRF-Token"}.issubset(
            headers
        ):
            raise ValueError("strict write boundary missing")
    return {
        "operation_count": len(operations),
        "sha256": {
            name: hashlib.sha256((BASELINE / name).read_bytes()).hexdigest() for name in CONTRACTS
        },
    }


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("window times must explicitly use UTC")
    return parsed


def validate_window(window: dict[str, Any], source: str, tree: str) -> dict[str, Any]:
    expected = {
        "owner",
        "project",
        "database",
        "volume",
        "api_port",
        "web_port",
        "source_sha",
        "source_tree",
        "starts_at",
        "deadline",
        "cleanup_reserve_seconds",
    }
    if set(window) != expected:
        raise ValueError("exact non-secret window fields required")
    if window["owner"] != "QA" or git("status", "--porcelain"):
        raise ValueError("QA owner and clean committed source required")
    if window["source_sha"] != source or window["source_tree"] != tree:
        raise ValueError("window does not bind current exact source and tree")
    for name in ("project", "database", "volume"):
        if not isinstance(window[name], str) or not re.fullmatch(
            r"v4qa_[a-z0-9_]{8,50}", window[name]
        ):
            raise ValueError("new v4qa_ resource names required")
    ports = [window["api_port"], window["web_port"]]
    if any(type(port) is not int or not 1024 <= port <= 65535 for port in ports):
        raise ValueError("explicit unprivileged API/Web ports required")
    if ports[0] == ports[1]:
        raise ValueError("API/Web ports must differ")
    start, end = utc(window["starts_at"]), utc(window["deadline"])
    reserve = window["cleanup_reserve_seconds"]
    if type(reserve) is not int or reserve < 180:
        raise ValueError("at least 180 seconds cleanup reserve required")
    if not 0 < (end - start).total_seconds() <= 1800:
        raise ValueError("proposed QA slice must be bounded to at most 1800 seconds")
    if (end - max(start, datetime.now(UTC))).total_seconds() <= reserve:
        raise ValueError("expired or insufficient work window; no automatic extension")
    return {"status": "VALIDATED_PROPOSAL_ONLY", **window}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", type=Path, help="Root-proposed non-secret window JSON")
    args = parser.parse_args()
    try:
        source, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
        report = {
            "status": "PREPARATION_ONLY",
            "source_sha": source,
            "source_tree": tree,
            "dirty": bool(git("status", "--porcelain")),
            "contracts": contract_inventory(),
            "runtime": "NOT_RUN",
            "full": "NOT_RUN",
            "hosted": "NOT_RUN",
            "actual_tokens_cost": "UNKNOWN",
        }
        if args.window:
            report["window"] = validate_window(json.loads(args.window.read_text()), source, tree)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as exc:
        # Do not echo arbitrary window content, paths, credentials or raw subprocess output.
        print(json.dumps({"status": "REFUSED", "reason_type": type(exc).__name__}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
