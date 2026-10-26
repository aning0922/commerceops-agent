"""Allowlisted lab manifests; resolved positive dates/identity never roll on serve."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

MIXED = "mixed-v1"
POSITIVE = "positive-v1"
SYNTHETIC_SHOP = "synthetic-woo-positive"
MIXED_SHA256 = "db9887552a40ba71e6fbd29d009e49a7f2a94ea626c3df2efc67441928162922"


class ProfileFailure(ValueError):
    """Fixed public diagnostic, no manifest/credential/exception contents."""


def encoded(value: Any) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode()


def profile_shop(value: str) -> str:
    if not isinstance(value, str):
        raise ProfileFailure("LAB_PROFILE_SHOP")
    if value == SYNTHETIC_SHOP:
        return value
    try:
        if str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    raise ProfileFailure("LAB_PROFILE_SHOP")


def resolve_positive(
    template: dict[str, Any], anchor: str, shop: str, now: datetime
) -> dict[str, Any]:
    profile_shop(shop)
    try:
        if not isinstance(anchor, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", anchor):
            raise ValueError
        day = date.fromisoformat(anchor)
        if day.isoformat() != anchor or day > now.astimezone(ZoneInfo("Asia/Shanghai")).date():
            raise ValueError
    except ValueError:
        raise ProfileFailure("LAB_PROFILE_ANCHOR") from None
    result: dict[str, Any] = json.loads(json.dumps(template))

    def instant(value: dict[str, Any]) -> str:
        return datetime.combine(
            day + timedelta(days=value["day_offset"]),
            time.fromisoformat(value["time"]),
            ZoneInfo("Asia/Shanghai"),
        ).isoformat()

    for field in ("clock", "created_at", "window_start", "window_end"):
        result[field] = instant(result[field])
    for order in result["orders"]:
        order["created_at"] = instant(order["created_at"])
    result.update(profile=POSITIVE, anchor_day=anchor, shop_id=shop)
    return result


def bind_profile(
    root: Path, profile: str, anchor: str | None, shop: str | None
) -> tuple[dict[str, Any], bytes]:
    if profile == MIXED:
        if anchor is not None or shop is not None:
            raise ProfileFailure("LAB_MIXED_PROFILE_ARGUMENTS")
        raw = (root / "tests/fixtures/woocommerce-local/seed.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != MIXED_SHA256:
            raise ProfileFailure("LAB_MIXED_FIXTURE_CHANGED")
        return {}, raw
    if profile != POSITIVE or anchor is None:
        raise ProfileFailure("LAB_PROFILE_REQUIRED")
    template = (root / "tests/fixtures/woocommerce-local/positive.json").read_bytes()
    shop = SYNTHETIC_SHOP if shop is None else profile_shop(shop)
    spec = resolve_positive(json.loads(template), anchor, shop, datetime.now(UTC))
    raw = encoded(spec)
    return {
        "profile": POSITIVE,
        "anchor_day": anchor,
        "shop_id": shop,
        "shop_identity": "synthetic_lab_only"
        if shop == SYNTHETIC_SHOP
        else "provided_uuid_not_pg_verified",
        "template_sha256": hashlib.sha256(template).hexdigest(),
        "spec_sha256": hashlib.sha256(raw).hexdigest(),
    }, raw


def private_bytes(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > limit
        ):
            raise ProfileFailure("LAB_PROFILE_FILE")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ProfileFailure("LAB_PROFILE_FILE")
    return raw


def read_bound_spec(root: Path, config: dict[str, Any], directory: Path) -> dict[str, Any]:
    if "profile" not in config:
        if any(
            k in config
            for k in (
                "anchor_day",
                "shop_id",
                "template_sha256",
                "spec_sha256",
                "seed_file",
                "shop_identity",
                "external_shop_key",
            )
        ):
            raise ProfileFailure("LAB_PROFILE_BINDING")
        if any(
            line.startswith("WOO_LAB_SEED_FILE=")
            for line in private_bytes(directory / "compose.env", 65536).decode().splitlines()
        ):
            raise ProfileFailure("LAB_PROFILE_MOUNT_BINDING")
        raw = (root / "tests/fixtures/woocommerce-local/seed.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != MIXED_SHA256:
            raise ProfileFailure("LAB_MIXED_FIXTURE_CHANGED")
        value: dict[str, Any] = json.loads(raw)
        return value  # Explicit legacy mixed shape; never a positive fallback.
    if config["profile"] != POSITIVE or config.get("seed_file") != str(
        directory / "seed-spec.private.json"
    ):
        raise ProfileFailure("LAB_PROFILE_BINDING")
    if config.get("external_shop_key") != config.get("project"):
        raise ProfileFailure("LAB_PROFILE_EXTERNAL_SHOP_BINDING")
    binding, expected = bind_profile(
        root, POSITIVE, config.get("anchor_day"), config.get("shop_id")
    )
    if any(config.get(k) != v for k, v in binding.items()):
        raise ProfileFailure("LAB_PROFILE_BINDING")
    raw = private_bytes(directory / "seed-spec.private.json", 2097152)
    if len(raw) > 2097152 or raw != expected:
        raise ProfileFailure("LAB_PROFILE_SPEC_MISMATCH")
    # Exact owner-generated env; no alternate mount, project or source through dotenv.
    expected_env = (
        f"WOO_LAB_PROJECT={config['project']}\nWOO_LAB_PRIVATE_DIR={directory}\n"
        f"WOO_LAB_PORT={config['port']}\n"
        f"WOO_LAB_INTERNAL_SUBNET={config['internal_subnet']}\n"
        f"WOO_LAB_INGRESS_SUBNET={config['ingress_subnet']}\n"
        f"WOO_LAB_SEED_FILE={config['seed_file']}\n"
    )
    if private_bytes(directory / "compose.env", 65536).decode() != expected_env:
        raise ProfileFailure("LAB_PROFILE_MOUNT_BINDING")
    value = json.loads(raw)
    return value
