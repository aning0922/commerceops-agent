"""仅本次B04私有窗口撤销其自有approver；原scope与审计记录保留。"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from commerceops.infrastructure.database import DatabaseSettings, connect

from tests.e2e.web.live_batch_owner import verify

p = Path(sys.argv[1])
w = json.loads((p / "window.json").read_text())
if "owner_uid" in w:
    verify(p, w, "items")
elif not w["project"].startswith("p3b04-") or w["owner"] != "phase3-B-WTa266":
    raise ValueError("owned B04 window required")
if datetime.now(UTC) >= datetime.fromisoformat(w["stop_at_utc"]):
    raise ValueError("owned B04 window expired")
a = json.loads((p / "web-accounts.json").read_text())
s = DatabaseSettings.model_validate_json((p / "owner-settings.json").read_text())
with connect(s) as db:
    actor = UUID(a["approver"]["principal"])
    db.execute("SELECT 1 FROM business.principals WHERE id=%s FOR UPDATE", (actor,))
    db.execute(
        "UPDATE business.principal_role_shop_grants SET enabled=false WHERE principal_id=%s",
        (actor,),
    )
print("owned B04 approver scope revoked; values withheld")
