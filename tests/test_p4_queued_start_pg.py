"""Owned SQL/permissions/once and native-ready process evidence; platform/real secrets0."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from commerceops.entrypoints.feishu_worker_child import trusted_scope
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_queued_start import (
    admission_id,
    attempt_id,
    authorization_id,
    claim_queued_attempt,
    trusted_queued_start,
)
from commerceops.infrastructure.worker_lock import WorkerSession
from psycopg.types.json import Jsonb

from tests.p3_support import P3Fixture
from tests.p4_queued_support import prepare, start_ready, stop_ready
from tests.test_p3_pg import fixture as fixture

pytestmark = pytest.mark.integration


def audit_ids(f: P3Fixture, window: Any) -> set[Any]:
    with connect(f.config.database) as db:
        return {
            r["id"]
            for r in db.execute(
                "SELECT id FROM business.audit_events WHERE source='feishu_recovery' AND "
                "task_id=%s",
                (window.queued_start.task_id,),
            ).fetchall()
        }


def no_sdk(f: P3Fixture) -> None:
    with connect(f.config.database) as db:
        assert db.execute("SELECT count(*) AS n FROM business.p4_sdk_calls").fetchone() == {"n": 0}
        assert db.execute("SELECT count(*) AS n FROM business.p4_sdk_windows").fetchone() == {
            "n": 0
        }


def test_parent_and_worker_independent_commits_authorize_once_then_cold_replay(
    fixture: P3Fixture,
) -> None:
    f = fixture
    business, gateway, window = prepare(f)
    asyncio.run(claim_queued_attempt(f.config, business, window, gateway))
    assert audit_ids(f, window) == {attempt_id(window)}
    process, _ = start_ready(f, business, gateway)

    async def run() -> None:
        session = WorkerSession(f.config.database, business.organization_id)
        await session.start()
        try:
            await trusted_scope(f.config, business, window, worker_owner=session.owner)
            assert audit_ids(f, window) == {
                attempt_id(window),
                admission_id(window),
                authorization_id(window),
            }
            await trusted_queued_start(
                f.config, business, window, gateway, worker_owner=session.owner, claim=False
            )
            with pytest.raises(psycopg.errors.UniqueViolation):
                await trusted_scope(f.config, business, window, worker_owner=session.owner)
        finally:
            await session.close(clean=True)

    try:
        asyncio.run(run())
    finally:
        stop_ready(f, gateway, process)
    with pytest.raises(psycopg.errors.UniqueViolation):
        asyncio.run(claim_queued_attempt(f.config, business, window, gateway))
    no_sdk(f)


@pytest.mark.parametrize(
    "change", ["hash", "revoked", "job_attempt", "prior_worker", "prior_sdk", "sideeffect"]
)
def test_parent_attempt_commit_survives_failed_validator_and_replay(
    change: str, fixture: P3Fixture
) -> None:
    f = fixture
    business, gateway, window = prepare(f)
    r = window.queued_start
    assert r
    if change == "hash":
        window = window.model_copy(
            update={"queued_start": r.model_copy(update={"receipt_hash": "0" * 64})}
        )
    else:
        with connect(f.config.database) as db:
            if change == "revoked":
                db.execute(
                    "UPDATE business.principals SET enabled=false,auth_version=auth_version+1"
                    " WHERE id=%s",
                    (f.actor.principal_id,),
                )
            elif change == "job_attempt":
                db.execute("UPDATE business.jobs SET attempts=1 WHERE id=%s", (r.job_ids[0],))
            elif change == "prior_worker":
                db.execute(
                    "INSERT INTO "
                    "business.audit_events(id,organization_id,source,action,entity_type,entity_id,after_state,trace_id)"
                    " VALUES(%s,%s,'worker','started','worker_runtime',%s,%s,%s)",
                    (uuid4(), business.organization_id, str(uuid4()), Jsonb({}), uuid4()),
                )
            elif change == "prior_sdk":
                db.execute(
                    "INSERT INTO "
                    "business.p4_sdk_windows(id,organization_id,shop_id,expires_at,configured_enabled,method_caps,verification_mode)"
                    " VALUES(%s,%s,%s,%s,true,%s,'controlled_sdk')",
                    (
                        uuid4(),
                        business.organization_id,
                        business.shop_id,
                        window.expires_at,
                        Jsonb(window.caps),
                    ),
                )
            else:
                db.execute(
                    "UPDATE business.business_tasks SET state='analyzing',version=2 WHERE id=%s",
                    (r.task_id,),
                )
    with pytest.raises(PermissionError):
        asyncio.run(claim_queued_attempt(f.config, business, window, gateway))
    assert audit_ids(f, window) == {attempt_id(window)}
    with pytest.raises(psycopg.errors.UniqueViolation):
        asyncio.run(claim_queued_attempt(f.config, business, window, gateway))
    with connect(f.config.database) as db:
        assert db.execute("SELECT count(*) AS n FROM business.p4_sdk_calls").fetchone() == {"n": 0}


def test_two_parent_processes_cannot_claim_same_original_once(fixture: P3Fixture) -> None:
    f = fixture
    business, gateway, window = prepare(f)

    def invoke(_: int) -> str:
        try:
            asyncio.run(claim_queued_attempt(f.config, business, window, gateway))
            return "claimed"
        except psycopg.errors.UniqueViolation:
            return "spent"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(invoke, range(2)))
    assert sorted(outcomes) == ["claimed", "spent"] and audit_ids(f, window) == {attempt_id(window)}
    no_sdk(f)


@pytest.mark.parametrize("change", ["revoked", "transport_lost"])
def test_worker_admission_commit_survives_current_identity_or_ready_failure(
    change: str, fixture: P3Fixture
) -> None:
    f = fixture
    business, gateway, window = prepare(f)
    asyncio.run(claim_queued_attempt(f.config, business, window, gateway))
    process, directory = start_ready(f, business, gateway)
    try:
        if change == "revoked":
            with connect(f.config.database) as db:
                db.execute(
                    "UPDATE business.principals SET enabled=false,auth_version=auth_version+1"
                    " WHERE id=%s",
                    (f.actor.principal_id,),
                )
        else:
            (directory / "lost.request").touch(mode=0o600)
            end = time.monotonic() + 5
            while True:
                with connect(f.config.database) as db:
                    n = db.execute(
                        "SELECT count(*) AS n FROM business.audit_events WHERE "
                        "source='feishu_gateway' AND action='transport_lost' AND entity_id=%s",
                        (str(gateway.window_id),),
                    ).fetchone()
                if n and n["n"] == 1:
                    break
                assert time.monotonic() < end
                time.sleep(0.02)

        async def run() -> None:
            session = WorkerSession(f.config.database, business.organization_id)
            await session.start()
            try:
                with pytest.raises(PermissionError):
                    await trusted_scope(f.config, business, window, worker_owner=session.owner)
                assert audit_ids(f, window) == {attempt_id(window), admission_id(window)}
                with pytest.raises(psycopg.errors.UniqueViolation):
                    await trusted_scope(f.config, business, window, worker_owner=session.owner)
            finally:
                await session.close(clean=True)

        asyncio.run(run())
    finally:
        stop_ready(f, gateway, process)
    no_sdk(f)
