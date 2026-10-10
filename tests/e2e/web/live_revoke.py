"""仅撤销本次登记自有测试主体scope；无Web后门。"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from commerceops.infrastructure.database import DatabaseSettings, connect

p = Path(sys.argv[1])
window = json.loads((p / "window.json").read_text())
if datetime.now(UTC) >= datetime.fromisoformat(window["stop_at_utc"]):
    raise SystemExit("owned window expired")
facts = json.loads((p / "web-facts.json").read_text())
if sys.argv[2] != facts["operator"]:
    raise SystemExit("owned principal mismatch")
settings = DatabaseSettings.model_validate_json((p / "owner-settings.json").read_text())
with connect(settings) as db:
    db.execute(
        "SELECT 1 FROM business.principals WHERE id=%s FOR UPDATE", (UUID(facts["operator"]),)
    )
    db.execute(
        "UPDATE business.principal_role_shop_grants SET enabled=false "
        "WHERE principal_id=%s",
        (UUID(facts["operator"]),),
    )
print("owned scope revoked; values withheld")
