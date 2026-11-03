"""从实际日报Read DTO可重复导出；不手改constraints或required。"""

import json
from pathlib import Path

from commerceops.application.daily.read_models import DailyRead

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs/contracts/p6-daily-read-v1.schema.json"


def schema_bytes() -> bytes:
    schema = DailyRead.model_json_schema(mode="serialization")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "urn:commerceops:p6-daily-read-v1"
    schema["description"] = (
        "Generated from application.daily.read_models.DailyRead; "
        "cross-field formulas, exact display, stored hashes and authorization "
        "require DTO/store validation."
    )
    return (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode()


def main() -> None:
    TARGET.write_bytes(schema_bytes())


if __name__ == "__main__":
    main()
