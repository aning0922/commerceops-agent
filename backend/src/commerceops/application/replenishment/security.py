"""固定scrypt/HMAC编码；密钥、密码和capability不进入日志/URL。"""

import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime
from uuid import UUID

from commerceops.domain.commerce_values import canonical_bytes


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    result = hashlib.scrypt(
        password.encode(), salt=salt, n=131072, r=8, p=1, dklen=32, maxmem=256 * 1024 * 1024
    )
    return "scrypt-v1$131072$8$1$" + salt.hex() + "$" + result.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        version, n, r, p, salt, expected = stored.split("$")
        if (version, n, r, p) != ("scrypt-v1", "131072", "8", "1"):
            return False
        if re.fullmatch(r"[a-f0-9]{32}", salt) is None:
            return False
        if re.fullmatch(r"[a-f0-9]{64}", expected) is None:
            return False
        actual = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=131072,
            r=8,
            p=1,
            dklen=32,
            maxmem=256 * 1024 * 1024,
        )
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def capability(secret: bytes, purpose: str, binding: object) -> str:
    return (
        base64.urlsafe_b64encode(
            hmac.digest(secret, purpose.encode() + b"\x00" + canonical_bytes(binding), "sha256")
        )
        .decode()
        .rstrip("=")
    )


def csrf_token(secret: bytes, session_id: UUID) -> str:
    return capability(secret, "p3-csrf-v1", str(session_id))


def approval_nonce(
    secret: bytes,
    approval_id: UUID,
    plan_id: UUID,
    version: int,
    plan_hash: str,
    expires_at: datetime,
) -> str:
    return capability(
        secret,
        "p3-nonce-v1",
        {
            "approval_id": str(approval_id),
            "plan_id": str(plan_id),
            "plan_version": version,
            "plan_hash": plan_hash,
            "expires_at": expires_at,
        },
    )
