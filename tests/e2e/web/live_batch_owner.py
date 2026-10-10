"""作者、原独审、CI三类私有Web测试登记；不扩展业务权限。"""

import os
import re
from pathlib import Path

OWNERS = {
    "b": "phase3-B-WTa266",
    "reviewer": "phase3-WebReviewer",
    "ci": "phase3-WebCI",
}


def verify(directory: Path, window: dict[str, object], stage: str) -> None:
    root = Path(__file__).resolve().parents[3]
    if (
        stage not in ("read", "write", "items")
        or window.get("owner") not in OWNERS.values()
        or window.get("owner_uid") != os.getuid()
        or window.get("checkout") != str(root)
        or window.get("private_directory") != str(directory.resolve())
        or directory.is_symlink()
        or directory.stat().st_uid != os.getuid()
        or directory.stat().st_mode & 0o777 != 0o700
        or not re.fullmatch(r"p3b04-" + stage + r"-[a-f0-9]{10}", str(window.get("project")))
    ):
        raise ValueError("closed owned stage registration required")
