"""B02专用测试前等待真实既有账号限流滑窗；只读，不清计数或降限。"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from commerceops.application.replenishment.security import digest
from commerceops.infrastructure.database import DatabaseSettings, connect

p = Path(sys.argv[1])
w = json.loads((p / "window.json").read_text())
if datetime.now(UTC) >= datetime.fromisoformat(w["stop_at_utc"]):
    raise SystemExit("owned window expired")
a = json.loads((p / "web-accounts.json").read_text())["operator"]
s = DatabaseSettings.model_validate_json((p / "owner-settings.json").read_text())
with connect(s) as db:
    row = db.execute(
        "SELECT count(*) AS count, EXTRACT(epoch FROM(max(occurred_at)+"
        "interval '300 seconds'-clock_timestamp())) AS wait_seconds "
        "FROM business.web_login_attempts WHERE login_digest=%s "
        "AND occurred_at>clock_timestamp()-interval '300 seconds'",
        (digest(a["login"]),),
    ).fetchone()
assert row is not None
wait_ms = max(0, int(float(row["wait_seconds"] or 0) * 1000)) + 1000 if row["count"] > 2 else 0
print(json.dumps({"wait_ms": wait_ms}))
