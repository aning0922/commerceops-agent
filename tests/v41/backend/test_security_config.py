"""Pure config vectors; activation and concurrent revocation require separate real PG evidence."""

import secrets
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.v4_demo_sessions import DemoConfig
from commerceops.infrastructure.v41_security import (
    binding_proof,
    config_fingerprint,
    invocation_key,
    policy_matches,
)
from commerceops.infrastructure.web_config import WebConfig

pytestmark = pytest.mark.offline


def config() -> DemoConfig:
    settings = DatabaseSettings(
        host="127.0.0.1",
        name="v4_demo_configuration",
        user="commerceops_app",
        password_file=Path("/never-read/v41-config"),
    )
    web = WebConfig(
        settings,
        secrets.token_bytes(32),
        secrets.token_bytes(32),
        ("http://127.0.0.1:3100",),
        transport_mode="local_http",
    )
    return DemoConfig(web, "http://127.0.0.1:8000", True)


def test_fingerprint_is_stable_but_covers_key_material_and_origins() -> None:
    value = config()
    digest = config_fingerprint(value)
    assert len(digest) == 64 and config_fingerprint(value) == digest
    row = dict(active_version=value.web.key_version, config_digest=digest)
    assert policy_matches(row, value)
    assert not policy_matches(None, value)
    for web in (
        replace(value.web, csrf_secret=secrets.token_bytes(32)),
        replace(value.web, nonce_secret=secrets.token_bytes(32)),
        replace(value.web, key_version="next-version"),
        replace(value.web, origins=("http://127.0.0.1:3101",)),
    ):
        assert not policy_matches(row, replace(value, web=web))
    assert not policy_matches(row, replace(value, api_origin="http://127.0.0.1:8001"))


def test_disabled_or_noncanonical_key_configuration_cannot_activate() -> None:
    value = config()
    with pytest.raises(ValueError, match="POLICY_CONFIGURATION"):
        config_fingerprint(replace(value, enabled=False))
    with pytest.raises(ValueError, match="POLICY_CONFIGURATION"):
        config_fingerprint(replace(value, web=replace(value.web, key_version="unsafe version")))


def test_private_binding_proof_changes_with_bound_identity_and_current_secret() -> None:
    value = config()
    identity = uuid4()
    proof = binding_proof(value, identity)
    assert proof == binding_proof(value, identity)
    assert proof != binding_proof(value, uuid4())
    assert proof != binding_proof(
        replace(value, web=replace(value.web, csrf_secret=secrets.token_bytes(32))), identity
    )


def test_invocation_domain_version_nonce_and_legacy_segments_are_independent() -> None:
    import base64
    import hmac

    from commerceops.application.replenishment.security import csrf_token

    value = config()
    value = replace(
        value,
        web=replace(
            value.web,
            nonce_secret=bytes(range(32)),
            csrf_secret=bytes(range(32, 64)),
            key_version="v2",
        ),
    )
    identity = UUID("00000000-0000-0000-0000-000000000001")
    derived = hmac.digest(bytes(range(32)), b'v41-invocation-key-1\0{"key_version":"v2"}', "sha256")
    assert invocation_key(value) == derived and len(derived) == 32
    payload = (
        b'v41-runtime-binding-1\0{"bound_session_id":'
        b'"00000000-0000-0000-0000-000000000001","key_version":"v2"}'
    )
    expected = (
        base64.urlsafe_b64encode(hmac.digest(derived, payload, "sha256")).decode().rstrip("=")
    )
    first, second = binding_proof(value, identity).split(".")
    assert first == csrf_token(value.web.csrf_secret, identity) and second == expected
    assert len(first) == len(second) == 43 and first != second
    for changed in (
        replace(value, web=replace(value.web, key_version="v3")),
        replace(value, web=replace(value.web, nonce_secret=bytes(range(1, 33)))),
    ):
        a, b = binding_proof(changed, identity).split(".")
        assert a == first and b != second
    changed = replace(value, web=replace(value.web, csrf_secret=bytes(range(33, 65))))
    a, b = binding_proof(changed, identity).split(".")
    assert a != first and b == second
