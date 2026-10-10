"""实际窗口专用key读入口；verify仅stat，不读secret或连接provider。"""

import os
import stat
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from commerceops.application.commerce.explanation_task import CAP_NANOS, MAX_CALLS, RESERVE_NANOS
from commerceops.infrastructure.p204_token_counter import COUNT_VERSION, VerifiedTextCounter


def key_stat(path: Path) -> os.stat_result:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_uid != os.getuid()
        or not 1 <= info.st_size <= 512
    ):
        raise ValueError("MODEL_KEY_FILE_INVALID")
    return info


def read_probe_key(path: Path) -> SecretStr:
    before = key_stat(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        now = os.fstat(descriptor)
        if (now.st_dev, now.st_ino, now.st_size, now.st_mode, now.st_uid) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mode,
            before.st_uid,
        ):
            raise ValueError("MODEL_KEY_FILE_CHANGED")
        value = os.read(descriptor, 513).decode("ascii").strip()
        if not value or len(value) > 512 or any(c.isspace() or not c.isprintable() for c in value):
            raise ValueError("MODEL_KEY_INVALID")
        return SecretStr(value)
    finally:
        os.close(descriptor)


def verify_config(path: Path) -> dict[str, Any]:
    key_stat(path)
    VerifiedTextCounter()
    return {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "thinking": "disabled",
        "max_input": 8000,
        "max_output": 800,
        "absolute_deadline_seconds": 20,
        "max_stage_calls": MAX_CALLS,
        "stage_usd_cap_nanos": CAP_NANOS,
        "reserve_per_call_nanos": RESERVE_NANOS,
        "tokenizer_version": COUNT_VERSION,
        "file_mode": "600",
        "file_owned": True,
        "file_regular": True,
        "file_nonempty": True,
        "key_read": False,
        "actual_provider_requests": 0,
        "automatic_retry": False,
        "tools": False,
    }
