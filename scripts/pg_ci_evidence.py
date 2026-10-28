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


def read_reply_parent_parts(nodes: list[str]) -> list[list[str]]:
    """Keep the existing sorted six-node command boundary shared by scope and executor."""
    ordered = sorted(
        n for n in nodes if n.split("::", 1)[0] == "tests/test_p4_read_reply_parent_pg.py"
    )
    return [ordered[offset : offset + 6] for offset in range(0, len(ordered), 6)]


def partition(full: list[str], scope: str) -> list[str]:
    if scope not in SCOPES:
        raise ValueError("closed CI scope required")
    nodes = canonical_nodes(full)
    parent_parts = read_reply_parent_parts(nodes)
    phase3_parent = set(parent_parts[0]) if parent_parts else set()
    phase3 = [
        n
        for n in nodes
        if (
            n.split("::")[0].startswith(("tests/test_p3", "tests/test_p4"))
            and n.split("::")[0] not in EXISTING_MODULES
        )
        or n in phase3_parent
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


# V2 is opt-in. V1 scopes, fields, invocation and validation above remain unchanged.
G2_V2_REQUIRED = G2_REQUIRED | {"retired_probe_version_refused"}
PLAN_FIELDS = {
    "schema_version",
    "binding",
    "full_node_ids",
    "groups",
    "shards",
    "weights",
    "weights_sha256",
    "algorithm",
    "plan_sha256",
}
BINDING_FIELDS = {"source_sha", "source_tree", "fingerprints", "execution", "environment"}
ENV_FIELDS = {"os", "arch", "runner_image", "runner_version", "docker", "compose", "pg_image"}
SHARD_FIELDS = {
    "schema_version",
    "binding",
    "plan_sha256",
    "shard_id",
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
    "resources",
    "native_exit",
}


def document_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def execution_identity() -> dict[str, Any]:
    """Hosted run context only; no credentials or user-controlled free text exported."""
    import os

    value = {
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    }
    if any(not isinstance(v, str) or not re.fullmatch(r"[1-9][0-9]*", v) for v in value.values()):
        raise ValueError("Hosted run and attempt required")
    return value


def environment_identity(root: Path) -> dict[str, str]:
    import os

    def version(command: list[str]) -> str:
        return subprocess.check_output(command, cwd=root, text=True, timeout=10).strip()

    image = re.search(
        r"image: (postgres:[^\s]+@sha256:[0-9a-f]{64})", (root / "compose.yml").read_text()
    )
    if image is None:
        raise ValueError("pinned PostgreSQL image required")
    value = {
        "os": platform.system(),
        "arch": platform.machine(),
        "runner_image": os.environ.get("ImageOS", ""),
        "runner_version": os.environ.get("ImageVersion", ""),
        "docker": version(["docker", "--version"]),
        "compose": version(["docker", "compose", "version", "--short"]),
        "pg_image": image[1],
    }
    _validate_environment(value)
    return value


def _validate_environment(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != ENV_FIELDS:
        raise ValueError("closed runner/Compose/image identity required")
    if any(
        not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9:.,@+_ /=-]{1,180}", v)
        for v in value.values()
    ):
        raise ValueError("safe nonempty environment values required")
    if value["os"] != "Linux" or value["arch"] not in {"x86_64", "AMD64"}:
        raise ValueError("Hosted Linux x64 required")
    if not re.fullmatch(r"postgres:[^\s]+@sha256:[0-9a-f]{64}", value["pg_image"]):
        raise ValueError("immutable PostgreSQL image required")


def _validate_binding(binding: Any) -> None:
    if not isinstance(binding, dict) or set(binding) != BINDING_FIELDS:
        raise ValueError("closed source/tool/run binding required")
    for key in ("source_sha", "source_tree"):
        if not isinstance(binding[key], str) or not re.fullmatch(r"[0-9a-f]{40}", binding[key]):
            raise ValueError("exact source identity required")
    fp = binding["fingerprints"]
    if not isinstance(fp, dict) or set(fp) != {"files", "runtime", "binaries"}:
        raise ValueError("closed fingerprints required")
    if (
        not isinstance(fp["files"], dict)
        or set(fp["files"]) != set(LOCK_FILES)
        or not isinstance(fp["binaries"], dict)
        or set(fp["binaries"]) != {"uv", "node", "gitleaks"}
        or fp["runtime"]
        != {"python": "3.12.13", "uv": "uv 0.11.25", "node": "v24.21.0", "gitleaks": "8.30.1"}
    ):
        raise ValueError("pinned tool/lock identities required")
    if any(
        not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v)
        for v in [*fp["files"].values(), *fp["binaries"].values()]
    ):
        raise ValueError("fingerprint digests required")
    ex = binding["execution"]
    if (
        not isinstance(ex, dict)
        or set(ex) != {"run_id", "attempt"}
        or any(not isinstance(v, str) or not re.fullmatch(r"[1-9][0-9]*", v) for v in ex.values())
    ):
        raise ValueError("exact run/attempt required")
    _validate_environment(binding["environment"])


def require_same_binding(expected: Any, actual: Any, context: str) -> None:
    """Keep strict equality; diagnose only validated field paths and value digests."""
    _validate_binding(expected)
    _validate_binding(actual)
    if expected == actual:
        return
    differences = []

    def compare(left: Any, right: Any, path: str) -> None:
        if isinstance(left, dict):
            for key in sorted(left):
                compare(left[key], right[key], f"{path}.{key}" if path else key)
        elif left != right:
            differences.append(
                {
                    "field": path,
                    "expected_sha256": document_hash(left),
                    "actual_sha256": document_hash(right),
                }
            )

    compare(expected, actual, "")
    raise ValueError(f"{context}; binding_diff=" + json.dumps(differences, sort_keys=True))


def _assignment(
    groups: dict[str, list[str]], weights: dict[str, float], count: int
) -> list[dict[str, Any]]:
    smoke = [
        label
        for label, nodes in groups.items()
        if any(n.startswith("tests/test_checkpoint_pg.py::") for n in nodes)
    ]
    if len(smoke) != 1:
        raise ValueError("one complete checkpoint execution group required")
    loads = [0.0] * count
    assigned: list[list[str]] = [[] for _ in range(count)]
    costs = {
        label: sum(weights.get(node, 1.0) for node in nodes) for label, nodes in groups.items()
    }
    for label in [
        smoke[0],
        *sorted((k for k in groups if k != smoke[0]), key=lambda k: (-costs[k], k)),
    ]:
        shard = 0 if label == smoke[0] else min(range(count), key=lambda i: (loads[i], i))
        assigned[shard].append(label)
        loads[shard] += costs[label]
    if any(not group for group in assigned):
        raise ValueError("every declared shard must have execution groups")
    return [
        {"shard_id": i, "smoke": i == 0, "groups": sorted(labels)}
        for i, labels in enumerate(assigned)
    ]


def plan_shards(
    full: list[str], weights: dict[str, float], shard_count: int, binding: dict[str, Any]
) -> dict[str, Any]:
    from scripts.pg_diagnostic import combined_groups

    _validate_binding(binding)
    if type(shard_count) is not int or shard_count not in (4, 6):
        raise ValueError("four or six shards required")
    nodes = canonical_nodes(full)
    # Stale timing rows cannot select tests. Missing weights use a conservative positive hint.
    normalized = {n: weights[n] for n in nodes if n in weights}
    if any(type(v) not in (int, float) or not 0 < v < 86400 for v in normalized.values()):
        raise ValueError("finite positive timing hints required")
    groups = {k: sorted(v) for k, v in combined_groups(nodes).items()}
    plan: dict[str, Any] = {
        "schema_version": "pg-shard-plan-v2",
        "binding": binding,
        "full_node_ids": nodes,
        "groups": groups,
        "shards": _assignment(groups, normalized, shard_count),
        "weights": normalized,
        "weights_sha256": document_hash(normalized),
        "algorithm": "whole-combined-groups-lpt-v1",
    }
    plan["plan_sha256"] = document_hash(plan)
    return plan


def validate_plan(plan: dict[str, Any]) -> None:
    if (
        not isinstance(plan, dict)
        or set(plan) != PLAN_FIELDS
        or plan["schema_version"] != "pg-shard-plan-v2"
    ):
        raise ValueError("closed v2 plan required")
    rebuilt = plan_shards(
        plan["full_node_ids"], plan["weights"], len(plan["shards"]), plan["binding"]
    )
    if plan != rebuilt:
        raise ValueError("canonical exact deterministic plan required")


def shard_groups(plan: dict[str, Any], shard_id: int, full: list[str]) -> dict[str, list[str]]:
    validate_plan(plan)
    if canonical_nodes(full) != plan["full_node_ids"]:
        raise ValueError("shard collection differs from authoritative full set")
    if type(shard_id) is not int or shard_id not in range(len(plan["shards"])):
        raise ValueError("declared shard ID required")
    return {label: plan["groups"][label] for label in plan["shards"][shard_id]["groups"]}


def safe_shard_report(
    raw: dict[str, Any], binding: dict[str, Any], plan: dict[str, Any], shard_id: int
) -> dict[str, Any]:
    groups = shard_groups(plan, shard_id, raw.get("full_node_ids", []))
    _validate_binding(binding)
    if binding != plan["binding"]:
        raise ValueError("shard exporter binding differs from plan")
    execution = binding["execution"]
    # Reuse the v1 closed module projection; never copy raw report or resource records.
    v1 = safe_report(raw, binding, "all")
    return {
        "schema_version": "pg-shard-evidence-v2",
        "native_exit": None,  # Wrapper fills only after diagnostic process exits.
        "binding": binding,
        "plan_sha256": plan["plan_sha256"],
        "shard_id": shard_id,
        "full_node_ids_sha256": nodes_hash(plan["full_node_ids"]),
        "selected_node_ids": sorted(n for group in groups.values() for n in group),
        **{
            key: v1[key]
            for key in (
                "actual_node_ids",
                "modules",
                "result",
                "cleanup_exit",
                "stopping_confirmed",
                "g1_complete",
                "g1_verified_count",
                "g2_scenarios",
            )
        },
        "resources": {
            "project": raw.get("project"),
            "volume": raw.get("volume"),
            "owner": f"{execution['run_id']}/{execution['attempt']}/{shard_id}",
            "started_at": raw.get("started_at"),
            "deadline": raw.get("deadline"),
            "finished_at": raw.get("finished_at"),
            "remaining_resources": raw.get("remaining_resources"),
            "pg_image_id": raw.get("pg_image_id"),
        },
    }


def validate_shard(report: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    from datetime import datetime

    validate_plan(plan)
    if (
        not isinstance(report, dict)
        or set(report) != SHARD_FIELDS
        or report["schema_version"] != "pg-shard-evidence-v2"
    ):
        raise ValueError("closed v2 shard evidence required")
    if report["binding"] != plan["binding"] or report["plan_sha256"] != plan["plan_sha256"]:
        raise ValueError("source/tool/run/runner/plan mismatch")
    groups = shard_groups(plan, report["shard_id"], plan["full_node_ids"])
    selected = sorted(n for group in groups.values() for n in group)
    if (
        report["full_node_ids_sha256"] != nodes_hash(plan["full_node_ids"])
        or report["selected_node_ids"] != selected
    ):
        raise ValueError("exact planned selection required")
    if (
        canonical_nodes(report["actual_node_ids"]) != selected
        or report["actual_node_ids"] != selected
    ):
        raise ValueError("actual collection must equal selection")
    modules = report["modules"]
    if not isinstance(modules, list) or len(modules) != len(groups):
        raise ValueError("all execution groups required")
    labels = []
    for module in modules:
        if not isinstance(module, dict) or set(module) != {
            "label",
            "expected_node_ids",
            "actual_node_ids",
            "passed_node_ids",
            "exit_code",
            "result",
        }:
            raise ValueError("closed execution proof required")
        label = module["label"]
        if (
            not isinstance(label, str)
            or label not in groups
            or any(
                module[k] != groups[label]
                for k in ("expected_node_ids", "actual_node_ids", "passed_node_ids")
            )
        ):
            raise ValueError("exact group selected/collected/passed equality required")
        if (
            type(module["exit_code"]) is not int
            or module["exit_code"] != 0
            or module["result"] is not True
        ):
            raise ValueError("native successful group termination required")
        labels.append(label)
    if len(set(labels)) != len(labels) or set(labels) != set(groups):
        raise ValueError("unique exact execution groups required")
    if (
        report["result"] is not True
        or type(report["cleanup_exit"]) is not int
        or report["cleanup_exit"] != 0
        or report["stopping_confirmed"] is not True
    ):
        raise ValueError("native successful run/stopping/cleanup required")
    if type(report["native_exit"]) is not int or report["native_exit"] != 0:
        raise ValueError("actual diagnostic parent exit zero required")
    smoke = report["shard_id"] == 0
    if (
        report["g1_complete"] is not smoke
        or type(report["g1_verified_count"]) is not int
        or report["g1_verified_count"] != (3 if smoke else 0)
        or report["g2_scenarios"] != (sorted(G2_V2_REQUIRED) if smoke else [])
    ):
        raise ValueError("designated real G1 three/G2 six proof required")
    resource = report["resources"]
    if not isinstance(resource, dict) or set(resource) != {
        "project",
        "volume",
        "owner",
        "started_at",
        "deadline",
        "finished_at",
        "remaining_resources",
        "pg_image_id",
    }:
        raise ValueError("closed owned resource record required")
    if (
        not isinstance(resource["project"], str)
        or not re.fullmatch(r"p123-[0-9a-f]{12}", resource["project"])
        or resource["volume"] != resource["project"] + "_pg_data"
    ):
        raise ValueError("owned unique project/volume required")
    if (
        not isinstance(resource["pg_image_id"], str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", resource["pg_image_id"])
        or resource["remaining_resources"] != {"containers": 0, "networks": 0, "volumes": 0}
        or any(type(v) is not int for v in resource["remaining_resources"].values())
    ):
        raise ValueError("actual immutable image and clean owned resource inventory required")
    ex = plan["binding"]["execution"]
    if resource["owner"] != f"{ex['run_id']}/{ex['attempt']}/{report['shard_id']}":
        raise ValueError("exact resource owner required")
    times = [datetime.fromisoformat(resource[k]) for k in ("started_at", "finished_at", "deadline")]
    if any(t.utcoffset() is None for t in times) or not times[0] < times[1] <= times[2]:
        raise ValueError("actual cleanup within immutable deadline required")
    return selected


def verify_shards(
    plan: dict[str, Any], reports: list[dict[str, Any]], job_results: dict[str, str]
) -> None:
    validate_plan(plan)
    if len(reports) != len(plan["shards"]):
        raise ValueError("all expected shard artifacts required")
    if job_results != {str(i): "success" for i in range(len(plan["shards"]))}:
        raise ValueError("all declared native jobs must succeed; cancelled/skipped is not proof")
    nodes, ids, projects, images = [], [], [], []
    for report in reports:
        nodes.extend(validate_shard(report, plan))
        ids.append(report["shard_id"])
        projects.append(report["resources"]["project"])
        images.append(report["resources"]["pg_image_id"])
    if sorted(ids) != list(range(len(plan["shards"]))) or len(set(projects)) != len(projects):
        raise ValueError("distinct shards and isolated resources required")
    if len(set(images)) != 1:
        raise ValueError("all shards must execute the same actual PostgreSQL image")
    if canonical_nodes(nodes) != plan["full_node_ids"]:
        raise ValueError("disjoint actual passed union must equal full collection")


def finalize_shard(report: dict[str, Any], native_exit: int) -> dict[str, Any]:
    """Called by the shell wrapper after wait; this is not a job-success declaration."""
    if (
        set(report) != SHARD_FIELDS
        or report["schema_version"] != "pg-shard-evidence-v2"
        or report["native_exit"] is not None
        or type(native_exit) is not int
        or not 0 <= native_exit <= 255
    ):
        raise ValueError("one actual native exit finalization required")
    return {**report, "native_exit": native_exit}


def shard_main() -> None:
    import sys

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("plan")
    create.add_argument("--full", type=Path, required=True)
    create.add_argument("--weights", type=Path, required=True)
    create.add_argument("--shards", type=int, choices=(4, 6), required=True)
    create.add_argument("--output", type=Path, required=True)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--report", type=Path, required=True)
    finalize.add_argument("--exit", dest="native_exit", type=int, required=True)
    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--plan", type=Path, required=True)
    aggregate.add_argument("reports", type=Path, nargs="+")
    aggregate.add_argument("--job-results", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "finalize":
        report = finalize_shard(json.loads(args.report.read_text()), args.native_exit)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        return
    root = Path.cwd()
    binding = {
        **identity(root),
        "execution": execution_identity(),
        "environment": environment_identity(root),
    }
    if args.command == "plan":
        plan = plan_shards(
            json.loads(args.full.read_text()),
            json.loads(args.weights.read_text()),
            args.shards,
            binding,
        )
        args.output.write_text(json.dumps(plan, indent=2) + "\n")
    else:
        plan = json.loads(args.plan.read_text())
        validate_plan(plan)
        require_same_binding(
            plan["binding"],
            binding,
            "aggregate differs from exact checker checkout/run/environment",
        )
        verify_shards(
            plan,
            [json.loads(path.read_text()) for path in args.reports],
            json.loads(args.job_results.read_text()),
        )
        print("N-way exact source/run/tools/collection/groups/G1/G2/native cleanup verified")
    sys.exit(0)


def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in {"plan", "aggregate", "finalize"}:
        shard_main()
        return
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
