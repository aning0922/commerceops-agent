"""Dev-only additive synthetic copy seed for a fresh m3_daily_demo database.

Reuses the existing demo Web identity/scope. Never creates credentials/sessions, grants
runtime permissions, migrates, starts services, calls providers or approves copy.
"""

import argparse
import hashlib
import json
import os
import re
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from commerceops.application.knowledge_copy.citations import Embedding, ProductCitation
from commerceops.application.knowledge_copy.commands import CreateCopy
from commerceops.application.knowledge_copy.contracts import Manifest, Scope, digest
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.knowledge_copy_config import CopyDeployment
from commerceops.infrastructure.knowledge_copy_draft_store import register_copy_product
from commerceops.infrastructure.knowledge_copy_repository import register_synthetic_corpus


def validate_database(settings: DatabaseSettings, database: str) -> None:
    if (
        not re.fullmatch(r"m3_daily_demo_[a-z0-9_]{1,40}", database)
        or settings.name != database
        or settings.user == "commerceops_app"
    ):
        raise ValueError("NEW_OWNED_DEMO_REQUIRED")


def validate_target(settings: DatabaseSettings, database: str, directory: Path) -> None:
    validate_database(settings, database)
    if not directory.is_absolute() or ".." in directory.parts or not directory.name:
        raise ValueError("NEW_OWNED_DEMO_REQUIRED")


@contextmanager
def output_directory(directory: Path) -> Iterator[int]:
    """NoFollow every existing parent, then exclusively create our own 0700 directory."""
    with ExitStack() as stack:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        parent = os.open(directory.anchor, flags)
        stack.callback(os.close, parent)
        for name in directory.parts[1:-1]:
            parent = os.open(name, flags, dir_fd=parent)
            stack.callback(os.close, parent)
        os.mkdir(directory.name, mode=0o700, dir_fd=parent)
        owned = os.open(directory.name, flags, dir_fd=parent)
        stack.callback(os.close, owned)
        os.fchmod(owned, 0o700)
        yield owned


def write_owned(directory: int, name: str, body: bytes) -> None:
    if name not in ("copy-config.json", "copy-demo.json", "copy-create.json"):
        raise ValueError("DEMO_OUTPUT_INVALID")
    descriptor = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
    )
    with os.fdopen(descriptor, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def synthetic_bundle(
    organization: UUID, shop: UUID, principal: UUID, timestamp: datetime
) -> tuple[Manifest, tuple[Embedding, ...], ProductCitation, CopyDeployment, CreateCopy]:
    # Dev-only fixtures are explicitly self-authored synthetic data, not licensed live SOPs.
    from tests.test_p6_knowledge_copy_contracts import document, embedding, manifest, product, query

    scope = Scope(organization_id=str(organization), shop_id=str(shop))
    origin = document(
        "m3-copy-demo-sop-v1",
        scope=scope,
        approved_at=timestamp - timedelta(minutes=2),
        valid_from=timestamp - timedelta(minutes=1),
        expires_at=timestamp + timedelta(hours=1),
    )
    corpus = (embedding(doc=origin),)
    registry = manifest(corpus, scope=scope)
    facts = product(
        scope=scope,
        captured_at=timestamp - timedelta(seconds=1),
        expires_at=timestamp + timedelta(hours=1),
    )
    binding: dict[str, Any] = dict(
        organization_id=str(organization),
        shop_id=str(shop),
        query_ref="synthetic-name-check@v1",
        query_version="v1",
        query=query().model_dump(mode="json"),
    )
    binding["binding_digest"] = digest(binding)
    body = dict(
        schema_version="p6-copy-query-config-v1",
        enabled=True,
        bindings=[binding],
        provider_enabled=False,
        model_requests_enabled=False,
        publication_allowed=False,
    )
    deployment = CopyDeployment.model_validate_json(encoded(body | {"config_digest": digest(body)}))
    command = CreateCopy(
        shop_id=shop,
        registry_id=uuid4(),
        registry_digest=registry.manifest_digest,
        product_source_id=uuid4(),
        query_ref=binding["query_ref"],
        reviewer_id=principal,
        request_key=uuid4(),
    )
    return registry, corpus, facts, deployment, command


def seed_demo(
    settings: DatabaseSettings, organization: UUID, shop: UUID
) -> tuple[bytes, bytes, dict[str, Any]]:
    validate_database(settings, settings.name)
    with connect(settings) as db:
        db.execute("SET LOCAL statement_timeout='5s'")
        db.execute("SET LOCAL lock_timeout='5s'")
        owner = db.execute(
            "SELECT current_database()=%s AND current_user=pg_get_userbyid(relowner) AS allowed "
            "FROM pg_class WHERE oid='business.p6_knowledge_documents'::regclass",
            (settings.name,),
        ).fetchone()
        if not owner or not owner["allowed"]:
            raise ValueError("EXPLICIT_OWNER_REQUIRED")
        # Only the original new synthetic demo scope, at most one hour old.
        target = db.execute(
            """SELECT s.id FROM business.shops s
            JOIN business.organizations o ON o.id=s.organization_id
            WHERE s.id=%s AND o.id=%s AND s.adapter_kind='mock' AND s.environment='test'
            AND o.name='PG technical fixture' AND s.external_shop_key='demo'
            AND o.created_at>clock_timestamp()-interval '1 hour'
            AND (SELECT count(*) FROM business.organizations)=1 FOR SHARE OF s,o""",
            (shop, organization),
        ).fetchone()
        if not target:
            raise ValueError("FRESH_SYNTHETIC_SCOPE_REQUIRED")
        people = db.execute(
            """SELECT DISTINCT p.id FROM business.principals p
            JOIN business.principal_shop_scopes s
             ON s.principal_id=p.id AND s.organization_id=p.organization_id
            JOIN business.web_credentials w
             ON w.principal_id=p.id AND w.organization_id=p.organization_id
            JOIN business.identities i ON i.id=w.identity_id AND i.principal_id=p.id
             AND i.organization_id=p.organization_id
            WHERE p.organization_id=%s AND s.shop_id=%s AND p.enabled AND s.enabled AND w.enabled
            AND i.provider='web' AND p.roles @> ARRAY['operator','approver']::text[]
            AND NOT EXISTS(SELECT required.role_name
             FROM unnest(ARRAY['operator','approver']) AS required(role_name) WHERE NOT EXISTS(
             SELECT 1 FROM business.principal_role_shop_grants g
             WHERE g.organization_id=p.organization_id AND g.shop_id=s.shop_id
             AND g.principal_id=p.id AND g.role=required.role_name AND g.enabled))""",
            (organization, shop),
        ).fetchall()
        if len(people) != 1:
            raise ValueError("UNIQUE_EXISTING_WEB_ACTOR_REQUIRED")
        db.execute(
            "LOCK TABLE business.p6_knowledge_registries,business.p6_copy_products "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
        empty = db.execute(
            "SELECT (SELECT count(*) FROM business.p6_knowledge_documents)+"
            "(SELECT count(*) FROM business.p6_copy_products) AS n"
        ).fetchone()
        if not empty or empty["n"] != 0:
            raise ValueError("COPY_DEMO_ALREADY_SEEDED")
        clock = db.execute("SELECT clock_timestamp() AS t").fetchone()
        if not clock:
            raise ValueError("CLOCK_UNAVAILABLE")
        registry, corpus, product, deployment, command = synthetic_bundle(
            organization, shop, people[0]["id"], clock["t"]
        )
        register_synthetic_corpus(db, command.registry_id, registry, corpus)
        register_copy_product(db, command.product_source_id, product)
        raw = encoded(deployment.model_dump(mode="json"))
        public = dict(
            mode="self_authored_synthetic_only",
            organization_id=str(organization),
            shop_id=str(shop),
            operator_id=str(people[0]["id"]),
            reviewer_id=str(command.reviewer_id),
            registry_id=str(command.registry_id),
            registry_digest=command.registry_digest,
            product_source_id=str(command.product_source_id),
            query_ref=command.query_ref,
            copy_config_sha256=hashlib.sha256(raw).hexdigest(),
            config_digest=deployment.config_digest,
            expires_at=product.snapshot.expires_at.isoformat(),
            provider_enabled=False,
            model_requests_enabled=False,
            publication_allowed=False,
        )
    # Only export after the owner transaction context has returned from COMMIT.
    return raw, encoded(command.model_dump(mode="json")), public


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--organization", type=UUID, required=True)
    parser.add_argument("--shop", type=UUID, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        settings = DatabaseSettings()
        validate_target(settings, args.database, args.directory)
        with output_directory(args.directory) as owned:
            config, command, public = seed_demo(settings, args.organization, args.shop)
            public["copy_config_file"] = str(args.directory / "copy-config.json")
            public["create_request_file"] = str(args.directory / "copy-create.json")
            write_owned(owned, "copy-config.json", config)
            write_owned(owned, "copy-create.json", command)
            write_owned(owned, "copy-demo.json", encoded(public))
        print(json.dumps(public))
    except Exception:
        raise SystemExit("本地合成copy种子失败；保留新owned资源供核实，不自动重试") from None


if __name__ == "__main__":
    main()
