"""三固定Web段的只读白名单PG不变量；不输出对象标识或请求内容。"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from commerceops.infrastructure.database import DatabaseSettings, connect

from tests.e2e.web.live_batch_owner import verify
from tests.e2e.web.live_origins import registered_origins


def main(directory: Path, stage: str) -> None:
    registered_origins(directory)
    if stage not in ("read", "write", "items"):
        raise ValueError("fixed stage required")
    verify(directory, json.loads((directory / "window.json").read_text()), stage)
    settings = DatabaseSettings.model_validate_json((directory / "owner-settings.json").read_text())
    result: dict[str, Any] = {"stage": stage}
    with connect(settings) as db:
        calls = db.execute("SELECT count(*) AS n FROM business.model_calls").fetchone()
        flags = db.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles "
            "WHERE rolname='commerceops_app'"
        ).fetchone()
        assert calls and flags
        result.update(model_calls=calls["n"], app_flags=flags)
        passed = calls["n"] == 0 and not any(flags.values())
        if stage == "items":
            facts = json.loads((directory / "b04-facts.json").read_text())
            totals = db.execute(
                "SELECT count(*) AS items,sum(quantity)::bigint AS units,"
                "count(*) FILTER(WHERE status<>'open' AND version=2) AS terminal "
                "FROM business.replenishment_items WHERE task_id=%s",
                (facts["completed_task"],),
            ).fetchone()
            task = db.execute(
                "SELECT state FROM business.business_tasks WHERE id=%s",
                (facts["completed_task"],),
            ).fetchone()
            execution = db.execute(
                "SELECT count(*) AS n FROM business.executions "
                "WHERE task_id=%s AND status='completed'",
                (facts["completed_task"],),
            ).fetchone()
            cases = {}
            for name in (
                "resolve_item",
                "hidden_source_item",
                "unknown_item",
                "concurrent_item",
                "revoke_item",
            ):
                item = db.execute(
                    "SELECT status,version,resolution_reason,resolution_payload_hash "
                    "FROM business.replenishment_items WHERE id=%s",
                    (facts[name],),
                ).fetchone()
                receipts = db.execute(
                    "SELECT count(*) AS n FROM business.web_requests "
                    "WHERE operation='resolve' AND result->'item'->>'item_id'=%s",
                    (facts[name],),
                ).fetchone()
                audits = db.execute(
                    "SELECT count(*) AS n FROM business.audit_events "
                    "WHERE entity_id=%s AND action IN ('item_completed','item_closed')",
                    (facts[name],),
                ).fetchone()
                projections = db.execute(
                    "SELECT count(*) AS n FROM business.outbox WHERE aggregate_id=%s "
                    "AND aggregate_version=2 AND operation='item_projection' "
                    "AND NOT sender_enabled AND external_id IS NULL",
                    (facts[name],),
                ).fetchone()
                assert item and receipts and audits and projections
                counts = [receipts["n"], audits["n"], projections["n"]]
                expected = 0 if name == "revoke_item" else 1
                passed &= counts == [expected] * 3 and item["version"] == expected + 1
                passed &= (item["status"] == "open") == (expected == 0)
                canonical_matches = True
                if expected:
                    semantic = {
                        "item_id": facts[name],
                        "action": "complete" if item["status"] == "completed" else "close",
                        "reason": item["resolution_reason"].strip(),
                        "expected_version": 1,
                    }
                    digest = hashlib.sha256(
                        json.dumps(
                            semantic, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                        ).encode()
                    ).hexdigest()
                    canonical_matches = digest == item["resolution_payload_hash"]
                    passed &= canonical_matches
                cases[name] = {
                    "status": item["status"],
                    "version": item["version"],
                    "canonical_hash_matches": canonical_matches,
                    "receipts": counts[0],
                    "audits": counts[1],
                    "version2_projections": counts[2],
                }
            assert totals and task and execution
            passed &= totals == {"items": 20, "units": 2000, "terminal": 4}
            passed &= task["state"] == "completed" and execution["n"] == 1
            result.update(
                totals=totals, task=task, completed_executions=execution["n"], cases=cases
            )
        elif stage == "read":
            facts = json.loads((directory / "web-facts.json").read_text())
            source = db.execute(
                "SELECT state FROM business.business_tasks WHERE id=%s", (facts["source_task"],)
            ).fetchone()
            assert source
            passed &= source["state"] == "completed"
            result["source_analysis"] = source
    if stage == "write":
        probe = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("live_write_probe.py")),
                str(directory),
                "audit",
            ],
            capture_output=True,
            timeout=20,
            check=True,
        )
        evidence = json.loads(probe.stdout)
        for name, record in evidence["records"].items():
            expected = (
                1
                if name
                in ("approve", "reject", "decline", "combined20", "unknown", "second_combined")
                else 0
            )
            passed &= [record[k] for k in ("decision", "audit", "resume_job")] == [expected] * 3
        passed &= evidence["source_analysis"]["state"] == "completed"
        result["write"] = evidence
    result["passed"] = passed
    print(json.dumps(result))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
