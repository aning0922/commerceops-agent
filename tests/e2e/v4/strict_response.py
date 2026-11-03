"""Use the existing locked Ajv, with no dependency/contract mutation."""

import json
import subprocess
from pathlib import Path
from typing import Any

from .supervisor import Budget

ROOT = Path(__file__).resolve().parents[3]


def validate_response(operation: str, status: int, payload: Any, budget: Budget) -> None:
    result = subprocess.run(
        [
            str(ROOT / ".tools/node/bin/node"),
            str(Path(__file__).with_name("validate_response.mjs")),
        ],
        input=json.dumps({"operation": operation, "status": status, "payload": payload}),
        capture_output=True,
        text=True,
        env={},
        cwd=ROOT,
        timeout=budget.timeout(5),
        check=False,
    )
    if result.returncode != 0 or json.loads(result.stdout) != {"valid": True}:
        raise AssertionError("strict frozen V4 response validation failed")
