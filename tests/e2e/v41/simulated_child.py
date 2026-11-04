"""Fixed short-lived test processes only; never a service or business adapter."""

import json
import os
import sys
import time
from pathlib import Path

from .process import MODES


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in MODES:
        raise ValueError("fixed simulation mode required")
    mode, directory = sys.argv[1], Path(sys.argv[2])
    if mode == "sleep":
        time.sleep(30)
    if mode == "observer":
        fd = os.open(directory / "observation.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"status": "SIMULATION_OBSERVED"}, stream)
    return 3 if mode == "fail" else 4 if mode == "cleanup_fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
