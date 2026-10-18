"""CI双PG分区的安全元数据与精确集合配对；不读取配置/密码/业务行。"""

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

SCOPES = frozenset({"all", "existing", "phase3"})
# 完整模块族及新增C0恢复Gate转移既有quality余量；approval原14节点分片不变。
EXISTING_BUSINESS_MODULES = frozenset(
    {
        "tests/test_p3_approval_pg.py",
        "tests/test_p3_execution_authority_pg.py",
        "tests/test_p3_execution_recovery_pg.py",
        "tests/test_p4_first_create_pg.py",
        "tests/test_p4_first_create_negatives_pg.py",
        "tests/test_p4_template_results_pg.py",
    }
)
# 38783752352全局expires-75耗尽；迁移两个已完整通过的既有固定组。
# 旧phase3 batch-3=16节点/245.816s，batch-4=19节点/187.596s；不拆模块、不增时限。
EXISTING_REBALANCED_GROUPS = {
    # 38912191768: 原完整p3_pg命令91.921s；恢复包新增12节点实测331.260s。
    # 下列完整模块转移及两个原quality小组复用既有机制，所有节点/时限不变。
    "combined-existing-p3-native-regression": frozenset({"tests/test_p3_pg.py"}),
    "combined-existing-p3-recovery-evidence": frozenset(
        {
            "tests/test_p3_execution_authority_pg.py",
            "tests/test_p3_execution_recovery_pg.py",
            "tests/test_p3_evidence_pg.py",
            "tests/test_p3_pool_pg.py",
        }
    ),
    "combined-existing-p4-create-and-template": frozenset(
        {"tests/test_p4_first_create_pg.py", "tests/test_p4_template_results_pg.py"}
    ),
    "combined-existing-p4-a08-recovery": frozenset(
        {
            "tests/test_p4_a08_recovery_pg.py",
            "tests/test_p4_a08_scope_pg.py",
            "tests/test_p4_a08_workflow_pg.py",
        }
    ),
    "combined-existing-p4-clarification-delivery": frozenset(
        {
            "tests/test_p4_clarification_pg.py",
            "tests/test_p4_controlled_worker_pg.py",
            "tests/test_p4_delivery_pg.py",
            "tests/test_p4_explicit_ro_pg.py",
        }
    ),
    "combined-existing-p4-verified-history": frozenset({"tests/test_p4_history_pg.py"}),
    "combined-existing-p4-read-reply-parent": frozenset({"tests/test_p4_read_reply_parent_pg.py"}),
}
EXISTING_MODULES = EXISTING_BUSINESS_MODULES.union(*EXISTING_REBALANCED_GROUPS.values())
FIELDS = frozenset(
    {
        "schema_version",
        "scope",
        "source_sha",
        "source_tree",
        "fingerprints",
        "full_node_ids",
        "full_node_ids_sha256",
        "selected_node_ids",
        "actual_node_ids",
        "modules",
        "result",
        "cleanup_exit",
        "stopping_confirmed",
        "g1_complete",
        "g1_verified_count",
        "g2_scenarios",
    }
)
LOCK_FILES = (
    "uv.lock",
    "pyproject.toml",
    ".python-version",
    "frontend/package-lock.json",
    "scripts/tool_versions.json",
    "scripts/gitleaks_rules.json",
    ".gitleaks.toml",
    "compose.yml",
    "infrastructure/Dockerfile",
)
G2_REQUIRED = frozenset(
    {
        "cross_process_resume",
        "receipt_commit_checkpoint_gap",
        "graph_lock_loss_cancel",
        "graph_noncooperative_exit",
        "checkpoint_db_failure_recovered",
    }
)


def canonical_nodes(value: object) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(n, str) for n in value):
        raise ValueError("nonempty node IDs required")
    for n in value:
        path, sep, _ = n.partition("::")
        if (
            not sep
            or not path.startswith("tests/")
            or not path.endswith(".py")
            or ".." in path.split("/")
            or "\\" in path
        ):
            raise ValueError("invalid node path")
    if len(value) != len(set(value)):
        raise ValueError("duplicate node IDs")
    return sorted(value)


def nodes_hash(nodes: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(nodes, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def partition(full: list[str], scope: str) -> list[str]:
    if scope not in SCOPES:
        raise ValueError("closed CI scope required")
    nodes = canonical_nodes(full)
    phase3 = [
        n
        for n in nodes
        if n.split("::")[0].startswith(("tests/test_p3", "tests/test_p4"))
        and n.split("::")[0] not in EXISTING_MODULES
    ]
    existing = [n for n in nodes if n not in set(phase3)]
    if scope != "all" and (not phase3 or not existing):
        raise ValueError("both CI partitions must be nonempty")
    if set(phase3) & set(existing) or set(phase3 + existing) != set(nodes):
        raise ValueError("partition overlap or missing nodes")
    return nodes if scope == "all" else existing if scope == "existing" else phase3


def identity(root: Path) -> dict[str, Any]:
    def run(command: list[str]) -> str:
        return subprocess.check_output(command, cwd=root, text=True).strip()

    uv_binary = shutil.which("uv")
    if uv_binary is None:
        raise ValueError("required uv binary unavailable")
    uv_version = re.match(r"uv [0-9]+\.[0-9]+\.[0-9]+(?:\s|$)", run(["uv", "--version"]))
    if uv_version is None:
        raise ValueError("unrecognized uv version output")
    return {
        "source_sha": run(["git", "rev-parse", "HEAD"]),
        "source_tree": run(["git", "rev-parse", "HEAD^{tree}"]),
        "fingerprints": {
            "files": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in LOCK_FILES},
            "runtime": {
                "python": platform.python_version(),
                "uv": uv_version[0].strip(),
                "node": run([str(root / ".tools/node/bin/node"), "--version"]),
                "gitleaks": run([str(root / ".tools/gitleaks"), "version"]),
            },
            "binaries": {
                name: hashlib.sha256(path.read_bytes()).hexdigest()
                for name, path in {
                    "uv": Path(uv_binary),
                    "node": root / ".tools/node/bin/node",
                    "gitleaks": root / ".tools/gitleaks",
                }.items()
            },
        },
    }


def safe_report(raw: dict[str, Any], meta: dict[str, Any], scope: str) -> dict[str, Any]:
    # 不复制raw字段，只选固定结构；缺/错证据生成失败而不是伪造pass。
    modules = [
        {
            key: m[key]
            for key in (
                "label",
                "expected_node_ids",
                "actual_node_ids",
                "passed_node_ids",
                "exit_code",
                "result",
            )
        }
        for m in raw.get("combined_modules", [])
    ]
    full = raw.get("full_node_ids", [])
    selected = partition(full, scope) if full else []
    actual = [n for m in modules for n in m["actual_node_ids"]]
    records = raw.get("records", [])
    g2 = sorted(
        {
            r["data"]["scenario"]
            for r in records
            if r.get("event") == "g2_evidence"
            and isinstance(r.get("data"), dict)
            and r["data"].get("scenario") in G2_REQUIRED | {"retired_probe_version_refused"}
        }
    )
    return {
        "schema_version": "pg-ci-evidence-v1",
        "scope": scope,
        "source_sha": meta["source_sha"],
        "source_tree": meta["source_tree"],
        "fingerprints": {
            "files": {p: meta["fingerprints"]["files"][p] for p in LOCK_FILES},
            "runtime": {
                k: meta["fingerprints"]["runtime"][k] for k in ("python", "uv", "node", "gitleaks")
            },
            "binaries": {
                k: meta["fingerprints"]["binaries"][k] for k in ("uv", "node", "gitleaks")
            },
        },
        "full_node_ids": sorted(full),
        "full_node_ids_sha256": nodes_hash(sorted(full)),
        "selected_node_ids": selected,
        "actual_node_ids": sorted(actual),
        "modules": modules,
        "result": raw.get("result") == "passed_no_hang_reproduced",
        "cleanup_exit": raw.get("cleanup_exit") if type(raw.get("cleanup_exit")) is int else -1,
        "stopping_confirmed": raw.get("stopping_confirmed") is True,
        "g1_complete": raw.get("g1_complete") is True,
        "g1_verified_count": sum(
            r.get("event") == "g1_persistence"
            and r.get("kind") == "verified"
            and r.get("count_one") is True
            for r in records
        ),
        "g2_scenarios": g2,
    }


def validate(report: dict[str, Any]) -> tuple[list[str], list[str]]:
    if set(report) != FIELDS or report["schema_version"] != "pg-ci-evidence-v1":
        raise ValueError("unexpected artifact fields")
    if report["scope"] not in ("existing", "phase3"):
        raise ValueError("paired scope required")
    if type(report["g1_verified_count"]) is not int:
        raise ValueError("strict G1 proof count required")
    if (
        not isinstance(report["g2_scenarios"], list)
        or any(
            s not in G2_REQUIRED | {"retired_probe_version_refused"} for s in report["g2_scenarios"]
        )
        or report["g2_scenarios"] != sorted(set(report["g2_scenarios"]))
    ):
        raise ValueError("closed unique G2 proof scenarios required")
    if any(
        not isinstance(report[k], str) or not re.fullmatch("[0-9a-f]{40}", report[k])
        for k in ("source_sha", "source_tree")
    ):
        raise ValueError("exact source identity required")
    fp = report["fingerprints"]
    if (
        not isinstance(fp, dict)
        or set(fp) != {"files", "runtime", "binaries"}
        or set(fp["files"]) != set(LOCK_FILES)
        or set(fp["runtime"]) != {"python", "uv", "node", "gitleaks"}
        or set(fp["binaries"]) != {"uv", "node", "gitleaks"}
    ):
        raise ValueError("closed tool and lock fingerprints required")
    if any(
        not isinstance(v, str) or not re.fullmatch("[0-9a-f]{64}", v)
        for v in [*fp["files"].values(), *fp["binaries"].values()]
    ):
        raise ValueError("invalid lock fingerprints")
    if fp["runtime"] != {
        "python": "3.12.13",
        "uv": "uv 0.11.25",
        "node": "v24.21.0",
        "gitleaks": "8.30.1",
    }:
        raise ValueError("pinned runtime versions required")
    full = canonical_nodes(report["full_node_ids"])
    if report["full_node_ids"] != full or report["full_node_ids_sha256"] != nodes_hash(full):
        raise ValueError("canonical complete collection required")
    selected = canonical_nodes(report["selected_node_ids"])
    actual = canonical_nodes(report["actual_node_ids"])
    if selected != partition(full, report["scope"]) or selected != actual:
        raise ValueError("exact actual partition required")
    if (
        report["result"] is not True
        or type(report["cleanup_exit"]) is not int
        or report["cleanup_exit"] != 0
        or report["stopping_confirmed"] is not True
    ):
        raise ValueError("successful run and confirmed cleanup required")
    modules = report["modules"]
    if not isinstance(modules, list) or not modules:
        raise ValueError("module terminal proof required")
    # 同一已核runner的精确分组，拒绝伪造part label/改14-node集合或遗漏其他模块。
    from scripts.pg_diagnostic import combined_groups

    planned = {
        label: sorted(group)
        for label, group in combined_groups(full).items()
        if set(group) <= set(selected)
    }
    union = []
    for m in modules:
        if not isinstance(m, dict) or set(m) != {
            "label",
            "expected_node_ids",
            "actual_node_ids",
            "passed_node_ids",
            "exit_code",
            "result",
        }:
            raise ValueError("closed module proof required")
        expected = canonical_nodes(m["expected_node_ids"])
        observed = canonical_nodes(m["actual_node_ids"])
        passed = canonical_nodes(m["passed_node_ids"])
        if (
            expected != observed
            or expected != passed
            or m["result"] is not True
            or type(m["exit_code"]) is not int
            or m["exit_code"] != 0
        ):
            raise ValueError("all actual nodes must pass and terminate")
        if not isinstance(m["label"], str) or planned.get(m["label"]) != expected:
            raise ValueError("module label binding required")
        union.extend(expected)
    if (
        canonical_nodes(union) != actual
        or len(modules) != len(planned)
        or {m["label"] for m in modules} != set(planned)
    ):
        raise ValueError("module coverage must match actual partition")
    if report["scope"] == "existing" and (
        report["g1_complete"] is not True
        or report["g1_verified_count"] != 3
        or not G2_REQUIRED.issubset(set(report["g2_scenarios"]))
    ):
        raise ValueError("existing G1/G2 full smoke required")
    if report["scope"] == "phase3" and (
        report["g1_complete"] is not False
        or report["g1_verified_count"] != 0
        or report["g2_scenarios"] != []
    ):
        raise ValueError("phase3 scope cannot claim existing smoke")
    return full, actual


def verify_pair(existing: dict[str, Any], phase3: dict[str, Any]) -> None:
    if existing["scope"] != "existing" or phase3["scope"] != "phase3":
        raise ValueError("distinct CI job scopes required")
    a_full, a = validate(existing)
    b_full, b = validate(phase3)
    for field in ("source_sha", "source_tree", "fingerprints", "full_node_ids_sha256"):
        if existing[field] != phase3[field]:
            raise ValueError("paired source collection/tool/lock mismatch")
    if a_full != b_full or set(a) & set(b) or canonical_nodes(a + b) != a_full:
        raise ValueError("paired actual union must equal full collection without overlap")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("existing", type=Path)
    p.add_argument("phase3", type=Path)
    args = p.parse_args()
    existing = json.loads(args.existing.read_text())
    phase3 = json.loads(args.phase3.read_text())
    verify_pair(existing, phase3)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip()
    if existing["source_sha"] != head or existing["source_tree"] != tree:
        raise ValueError("paired artifacts do not match checker exact checkout")
    print("paired exact source/tool/lock/collection, all actual PG modules/G1/G2/cleanup verified")


if __name__ == "__main__":
    main()
