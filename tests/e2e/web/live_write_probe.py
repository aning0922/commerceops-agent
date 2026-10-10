"""仅B03登记窗口的受控状态/撤权与只读PG核证；不作产品接口。"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from commerceops.infrastructure.database import DatabaseSettings, connect

from tests.e2e.web.live_origins import registered_origins


def main(directory: Path, action: str) -> None:
    registered_origins(directory)
    window = json.loads((directory / "window.json").read_text())
    if window["owner"] != "phase3-B-WTa266" or not window["project"].startswith("p3b03-"):
        raise ValueError("owned B03 window required")
    if datetime.now(UTC) >= datetime.fromisoformat(window["stop_at_utc"]):
        raise ValueError("owned window expired")
    facts = json.loads((directory / "write-facts.json").read_text())
    accounts = json.loads((directory / "web-accounts.json").read_text())
    settings = DatabaseSettings.model_validate_json((directory / "owner-settings.json").read_text())
    with connect(settings) as db:
        if action == "revoke-approver":
            principal = UUID(accounts["approver"]["principal"])
            db.execute("SELECT 1 FROM business.principals WHERE id=%s FOR UPDATE", (principal,))
            db.execute(
                "UPDATE business.principal_role_shop_grants "
                "SET enabled=false WHERE principal_id=%s",
                (principal,),
            )
            print("owned B03 approver revoked; values withheld")
        elif action == "controlled-supersede":
            task = UUID(facts["records"]["supersede"]["task"])
            db.execute(
                "UPDATE business.replenishment_plans SET status='superseded' WHERE task_id=%s",
                (task,),
            )
            db.execute(
                "UPDATE business.approvals SET status='superseded' WHERE task_id=%s",
                (task,),
            )
            print("owned B03 controlled superseded fixture; no A03 new version claim")
        elif action == "audit":
            evidence = {}
            for name, record in facts["records"].items():
                task = UUID(record["task"])
                row = db.execute(
                    "SELECT state,failure_code FROM business.business_tasks WHERE id=%s", (task,)
                ).fetchone()
                assert row
                counts = {}
                for label, query in [
                    (
                        "decision",
                        "SELECT count(*) AS n FROM business.approval_resumes WHERE task_id=%s",
                    ),
                    (
                        "audit",
                        "SELECT count(*) AS n FROM business.audit_events "
                        "WHERE task_id=%s AND action='approval_decided'",
                    ),
                    (
                        "resume_job",
                        "SELECT count(*) AS n FROM business.jobs "
                        "WHERE task_id=%s AND kind='resume'",
                    ),
                ]:
                    count = db.execute(query, (task,)).fetchone()
                    assert count
                    counts[label] = count["n"]
                evidence[name] = {**row, **counts}
            model = db.execute("SELECT count(*) AS n FROM business.model_calls").fetchone()
            flags = db.execute(
                "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles "
                "WHERE rolname='commerceops_app'"
            ).fetchone()
            assert model and flags
            source = db.execute(
                "SELECT state FROM business.business_tasks WHERE id=%s",
                (UUID(facts["records"]["combined20"]["source_task"]),),
            ).fetchone()
            result = {
                "records": evidence,
                "source_analysis": source,
                "model_calls": model["n"],
                "app_flags": flags,
            }
            print(json.dumps(result))
        else:
            raise ValueError("unsupported owned probe")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
