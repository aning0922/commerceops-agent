"""框架无关的 commerce 值校验与 canonical-facts-v1 编码；没有库存计算。"""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# inventory-v1 明确支持的 ISO 4217 子集；扩展必须升级合同/能力和测试。
CURRENCIES = frozenset({"CNY", "USD", "EUR", "JPY", "GBP", "AUD", "CAD", "HKD", "CHF", "SGD"})


def integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("INVALID_INTEGER")
    return value


def identifier(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value or len(value) > 256:
        raise ValueError("INVALID_IDENTIFIER")
    return value


def sku_key(shop_id: str, product_id: str, variant_id: str | None = None) -> str:
    parts = (identifier(shop_id), identifier(product_id))
    key = "sku/" + "/".join(quote(part, safe="") for part in parts)
    return key + (
        "/v/" + quote(identifier(variant_id), safe="") if variant_id is not None else "/p"
    )


def stock_pool_key(shop_id: str, owner_id: str) -> str:
    return "pool/" + "/".join(quote(identifier(part), safe="") for part in (shop_id, owner_id))


def utc_time(value: object) -> datetime:
    if type(value) is str:
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("INVALID_TIME") from None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("NAIVE_TIME")
    return value.astimezone(UTC)


def shop_timezone(value: object) -> str:
    name = identifier(value)
    try:
        ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("INVALID_TIMEZONE") from None
    return name


def complete_days(now: datetime, timezone: str, days: int = 7) -> tuple[datetime, datetime]:
    """显式 clock 的自然日边界；DST 日不假定为 24 小时。"""
    if integer(days) <= 0:
        raise ValueError("INVALID_WINDOW")
    local = utc_time(now).astimezone(ZoneInfo(shop_timezone(timezone)))
    end = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return (end - timedelta(days=days)).astimezone(UTC), end.astimezone(UTC)


def money(value: object) -> Decimal:
    if type(value) is str:
        if re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value) is None:
            raise ValueError("INVALID_MONEY")
        value = Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("INVALID_MONEY")
    # 对齐 numeric(20,6)，不隐式舍入或依赖 Decimal context。
    exponent = value.as_tuple().exponent
    if (
        not isinstance(exponent, int)
        or exponent < -6
        or value.copy_abs() >= Decimal("100000000000000")
    ):
        raise ValueError("MONEY_OUT_OF_RANGE")
    return value


def currency(value: object) -> str:
    if type(value) is not str or value not in CURRENCIES:
        raise ValueError("UNSUPPORTED_CURRENCY")
    return value


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if value == 0 else text


def canonical(value: object) -> object:
    """排序键/无空白/UTF-8/null 保留；数组顺序为事实的一部分，float 禁止。"""
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, Decimal):
        return decimal_text(money(value))
    if isinstance(value, Fraction):
        return {"numerator": str(value.numerator), "denominator": str(value.denominator)}
    if isinstance(value, datetime):
        return utc_time(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            raise ValueError("INVALID_CANONICAL_KEY")
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    raise ValueError("INVALID_CANONICAL_VALUE")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        canonical(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def facts_hash(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
