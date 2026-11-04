"""Pure config vectors; activation and concurrent revocation require separate real PG evidence."""

import secrets
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from commerceops.infrastructure.database import DatabaseSettings
from commerceops.infrastructure.v4_demo_sessions import DemoConfig
from commerceops.infrastructure.v41_security import (
    binding_proof,
    config_fingerprint,
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
