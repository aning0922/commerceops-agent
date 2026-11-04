"""GC-only owned-PG candidates. Collection is offline; actual resources are Root-gated.

A live lock/NOT_READY case and a SYNTHETIC_OWNED_HISTORICAL_FIXTURE deletion case
have different time premises. Neither is evidence of natural 24-hour lifecycle operation.
"""

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import psycopg
import pytest
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.application.v41 import contracts as dto
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.v4_demo_seed import gc_tenant
from commerceops.infrastructure.v4_demo_sessions import DB, bounded
from commerceops.infrastructure.v41_runtime import TABLES, grant_runtime
from commerceops.infrastructure.v41_security import activate_policy, binding_proof
from commerceops.infrastructure.v41_store import BusinessStore

from tests.v4.test_demo_sessions_pg import DemoPG
from tests.v4.test_demo_sessions_pg import demo as demo
from tests.v41.backend.gc_fixture import (
    CORE,
    LABEL,
    V4,
    Subject,
    _same_graph,
    catalog,
    constraints,
    fingerprints,
    graph,
    populate,
    restore,
)


@pytest.fixture
def gc_business(demo: DemoPG) -> tuple[DemoPG, BusinessStore]:
    with connect(demo.owner) as db:
        activate_policy(db, demo.config)
        grant_runtime(db, demo.config)
    return demo, BusinessStore(demo.config)


def actor(demo: DemoPG, db: DB, subject: Subject, binding: str) -> None:
    demo.store.sessions.resolve_locked(db, subject.token)
    row = db.execute(
        "SELECT business.v41_read_guard(%s,%s,%s,0,0) AS revision",
        (subject.token, binding, subject.shop),
    ).fetchone()
    assert row is not None and row["revision"]


def binding_for(demo: DemoPG, subject: Subject) -> str:
    with connect(demo.owner) as db:
        bounded(db)
        row = db.execute(
            "SELECT bound_web_session_id FROM business.v4_demo_sessions WHERE id=%s",
            (subject.session,),
        ).fetchone()
        assert row is not None
        return binding_proof(demo.config, row["bound_web_session_id"])


def assert_wait(demo: DemoPG, holder: int, waiter: int) -> None:
    end = time.monotonic() + 0.5
    while time.monotonic() < end:
        with connect(demo.owner) as db:
            bounded(db)
            blocked = db.execute(
                "SELECT %s=ANY(pg_blocking_pids(%s)) AS blocked", (holder, waiter)
            ).fetchone()
        if blocked == dict(blocked=True):
            return
        time.sleep(0.005)
    pytest.fail("original tenant lock wait was not observed before the unchanged 1s lock bound")


@pytest.mark.integration
@pytest.mark.parametrize("gc_first", [False, True], ids=["actor-first", "gc-first-not-ready"])
def test_live_actor_gc_tenant_barrier_and_not_ready_zero_delete(
    gc_business: tuple[DemoPG, BusinessStore],
    gc_first: bool,
    record_property: Callable[[str, object], None],
) -> None:
    demo, store = gc_business
    record_property("gc_time_premise", "LIVE_NOT_RETAINED")
    record_property("gc_ordering", "gc-first-not-ready" if gc_first else "actor-first")
    subject = populate(demo, store)
    binding = binding_for(demo, subject)
    with connect(demo.owner) as observer:
        before = fingerprints(observer)
    started = Event()
    waiter_pid: list[int] = []

    def waiting() -> str:
        with connect(demo.app if gc_first else demo.owner) as db:
            bounded(db)
            waiter_pid.append(db.info.backend_pid)
            started.set()
            if gc_first:
                actor(demo, db, subject, binding)
                return "ACTOR_COMMITTED"
            with pytest.raises(ValueError, match="^V4_GC_NOT_READY$"):
                gc_tenant(db, subject.tenant)
            return "GC_NOT_READY"

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        with connect(demo.owner if gc_first else demo.app) as holder:
            bounded(holder)
            if gc_first:
                # Python rejection preserves this transaction's tenant lock until explicit end.
                # The retain failure happens BEFORE the production GC's session lock query.
                with pytest.raises(ValueError, match="^V4_GC_NOT_READY$"):
                    gc_tenant(holder, subject.tenant)
            else:
                actor(demo, holder, subject, binding)
            future = pool.submit(waiting)
            try:
                assert started.wait(1)
                assert_wait(demo, holder.info.backend_pid, waiter_pid[0])
                assert not future.done()
                record_property(
                    "gc_observed_blocking_pids", f"{holder.info.backend_pid}:{waiter_pid[0]}"
                )
            finally:
                holder.rollback()  # Always release before joining; no lock-timeout counts as PASS.
            assert future.result(timeout=2) == ("ACTOR_COMMITTED" if gc_first else "GC_NOT_READY")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    with connect(demo.owner) as observer:
        after_live = fingerprints(observer)
        assert after_live == before
        record_property("gc_live_before", json.dumps(before, sort_keys=True))
        record_property("gc_live_after", json.dumps(after_live, sort_keys=True))
        assert len(graph(observer, subject)["v4_demo_personas"]) == 3
    assert (
        store.read(subject.token, 0, 0, dto.ProductQuery(shop_id=subject.shop), "products")[
            "data"
        ].total
        == 9
    )


@pytest.mark.integration
@pytest.mark.parametrize("outcome", ["commit", "rollback", "unknown"])
def test_retained_synthetic_graph_original_gc_atomic_scope_and_old_actor_rejection(
    gc_business: tuple[DemoPG, BusinessStore],
    outcome: str,
    record_property: Callable[[str, object], None],
) -> None:
    demo, store = gc_business
    record_property("gc_fixture", LABEL)
    record_property("gc_time_shift_hours", 48)
    record_property("gc_outcome", outcome)
    target = populate(demo, store)
    control = populate(demo, store)
    binding = binding_for(demo, target)
    sentinel = uuid4()
    with connect(demo.owner) as db:
        bounded(db)
        db.execute(
            "INSERT INTO business.organizations(id,name,feishu_tenant_key,feishu_app_id) "
            "VALUES(%s,'SYNTHETIC non-Demo GC control',%s,%s)",
            (sentinel, "synthetic-" + str(sentinel), "synthetic-" + str(sentinel)),
        )
        sentinel_sql = (
            "SELECT encode(sha256(convert_to(to_jsonb(o)::text,'UTF8')),'hex') digest "
            "FROM business.organizations o WHERE id=%s"
        )
        sentinel_before = db.execute(sentinel_sql, (sentinel,)).fetchone()
        before_restore = fingerprints(db)
        control_source = graph(db, control)
        before_catalog = catalog(db)
    restore(demo, target, unknown=outcome == "unknown")
    record_property("gc_restore_commit_ack", "COMMIT_AND_INDEPENDENT_VALIDATION_RETURNED")
    with connect(demo.owner) as db:
        bounded(db)
        before = fingerprints(db)
        record_property("gc_before", json.dumps(before, sort_keys=True))
        record_property(
            "gc_before_target_counts",
            json.dumps(
                {table: len(rows) for table, rows in graph(db, target).items()}, sort_keys=True
            ),
        )
        assert db.execute(sentinel_sql, (sentinel,)).fetchone() == sentinel_before
        assert catalog(db) == before_catalog
        for table in before:
            if table not in {
                *CORE,
                *("v4_demo_" + suffix for suffix in V4),
                *("v41_" + suffix for suffix in TABLES),
            }:
                assert before[table] == before_restore[table], table
        control_before = graph(db, control)
        _same_graph(control_before, control_source)
        assert db.execute(
            "SELECT count(*) n FROM business.v4_demo_tenants WHERE id=%s "
            "AND expires_at<clock_timestamp() AND retain_until<clock_timestamp()",
            (target.tenant,),
        ).fetchone() == dict(n=1)
    # This is already expired BEFORE GC; it must never be called a live actor crossing 24h.
    with pytest.raises(WebFailure, match="SESSION_INVALID"):
        demo.store.sessions.current(target.token)
    if outcome == "unknown":
        with pytest.raises(ValueError, match="^V41_PROCESS_HOLD$"), connect(demo.owner) as db:
            bounded(db)
            gc_tenant(db, target.tenant)
    elif outcome == "rollback":
        with connect(demo.owner) as db:
            bounded(db)
            gc_tenant(db, target.tenant)
            assert all(
                not rows
                for table, rows in graph(db, target).items()
                if table.startswith(("v4_demo_", "v41_"))
            )
            db.rollback()  # Intentional abort AFTER the original complete deletion path.
    else:
        with connect(demo.owner) as db:
            bounded(db)
            gc_tenant(db, target.tenant)
        # Only leaving the connection context successfully establishes actual GC COMMIT.
        record_property("gc_commit_ack", "CONNECTION_COMMIT_RETURNED")
    with connect(demo.owner) as db:
        bounded(db)
        after = fingerprints(db)
        record_property("gc_after", json.dumps(after, sort_keys=True))
        record_property(
            "gc_after_target_counts",
            json.dumps(
                {table: len(rows) for table, rows in graph(db, target).items()}, sort_keys=True
            ),
        )
        stamp = db.execute("SELECT clock_timestamp() db_utc").fetchone()
        assert stamp is not None
        record_property("gc_observed_db_utc", stamp["db_utc"].isoformat())
        assert catalog(db) == before_catalog
        assert db.execute(sentinel_sql, (sentinel,)).fetchone() == sentinel_before
        constraints(db)
        # Hash graph representations so pytest never displays private synthetic credentials.
        _same_graph(graph(db, control), control_before)
        assert db.execute(
            "SELECT count(*) n FROM business.organizations WHERE id=%s AND "
            "name='SYNTHETIC non-Demo GC control'",
            (sentinel,),
        ).fetchone() == dict(n=1)
        if outcome != "commit":
            assert after == before
            return
        deleted = graph(db, target)
        for table, rows in deleted.items():
            if table.startswith(("v4_demo_", "v41_")):
                assert not rows, table
        assert len(deleted["principals"]) == len(deleted["web_credentials"]) == 3
        assert all(not row["enabled"] for row in deleted["principals"])
        assert all(not row["enabled"] for row in deleted["web_credentials"])
        assert all(row["revoked_at"] is not None for row in deleted["web_sessions"])
        assert after["v41_security_policy"] == before["v41_security_policy"]
        assert after["v4_demo_fixture_versions"] == before["v4_demo_fixture_versions"]
        allowed = {
            "principals",
            "web_credentials",
            "web_sessions",
            *("v4_demo_" + suffix for suffix in V4),
            *("v41_" + suffix for suffix in TABLES),
        }
        assert all(after[table] == before[table] for table in after if table not in allowed)
    with pytest.raises(WebFailure, match="SESSION_INVALID"):
        demo.store.sessions.current(target.token)
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="SESSION_INVALID"),
        connect(demo.app) as db,
    ):
        bounded(db)
        db.execute(
            "SELECT business.v41_read_guard(%s,%s,%s,0,0)", (target.token, binding, target.shop)
        )
    with connect(demo.owner) as db:
        assert fingerprints(db) == after


@pytest.mark.offline
def test_history_manifest_matches_production_preview_at_shifted_time() -> None:
    """Pure golden: the shifted preview must equal production's independent construction."""
    import base64
    import copy
    from datetime import UTC, datetime, timedelta

    from commerceops.application.v41.imports import parse_file, quality_preview
    from commerceops.application.v41.previews import PreviewScope, prepare_preview

    from tests.v41.backend.gc_fixture import SHIFT, historical, sha, text, unknown_job

    now = datetime(2026, 11, 4, 8, 1, 2, 123456, tzinfo=UTC)
    scope = PreviewScope(
        tenant_id=uuid4(),
        shop_id=uuid4(),
        owner_session_id=uuid4(),
        principal_id=uuid4(),
        reset_epoch=0,
        auth_generation=0,
        data_revision="a" * 64,
        session_expires_at=now + timedelta(minutes=30),
    )
    raw = b"sku,title,price,currency\nGC-1,Synthetic,0.10,TWD\n"
    command = dto.ImportPreviewInput(
        shop_id=scope.shop_id,
        request_key=uuid4(),
        expected_epoch=0,
        expected_generation=0,
        expected_data_revision=scope.data_revision,
        format="csv",
        filename="gc.csv",
        file_base64=base64.b64encode(raw).decode(),
        mapping=dto.ColumnMapping(sku="sku", title="title", price="price", currency="currency"),
    )
    quality = quality_preview(parse_file(raw, "csv"), command.mapping, "TWD")
    identifier = uuid4()
    original = prepare_preview(scope, command, quality, (), now, identifier)
    source_job = dict(
        **{key: value for key, value in scope.model_dump().items() if key != "session_expires_at"},
        id=identifier,
        created_at=now,
        expires_at=original.data.job.expires_at,
        preview_data=original.data.model_dump(mode="json"),
        canonical_preview=original.data.model_dump_json(),
        request_digest=original.request_digest,
        normalized_digest=original.normalized_digest,
        mapping_digest=original.mapping_digest,
        job_digest=original.data.job.job_digest,
        canonical_preview_request=text(
            dict(
                command=dict(request_key=str(command.request_key)),
                file_digest=original.data.file_digest,
            )
        ),
    )
    receipt = dict(
        operation="import_confirm",
        resource_id=identifier,
        canonical_request=text(dict(body=dict(expected_job_digest=original.data.job.job_digest))),
        payload_digest="not-used-by-transform",
        committed_at=now,
    )
    source = {
        "v4_demo_sessions": [dict(expires_at=scope.session_expires_at, created_at=now)],
        "v41_import_jobs": [source_job],
        "v41_action_receipts": [receipt],
    }
    untouched = copy.deepcopy(source)
    transformed = historical(source)
    assert source == untouched
    independent_scope = scope.model_copy(
        update=dict(session_expires_at=scope.session_expires_at - SHIFT)
    )
    independent = prepare_preview(independent_scope, command, quality, (), now - SHIFT, identifier)
    actual = transformed["v41_import_jobs"][0]
    assert actual["preview_data"] == independent.data.model_dump(mode="json")
    assert actual["job_digest"] != original.data.job.job_digest
    assert actual["canonical_preview"] == text(independent.data.model_dump(mode="json"))
    shifted_receipt = transformed["v41_action_receipts"][0]
    assert (
        json.loads(shifted_receipt["canonical_request"])["body"]["expected_job_digest"]
        == independent.data.job.job_digest
    )
    assert shifted_receipt["payload_digest"] == sha(shifted_receipt["canonical_request"])
    assert shifted_receipt["committed_at"] == now - SHIFT
    unknown = unknown_job(actual)
    assert unknown["id"] != actual["id"] and unknown["preview_key"] != command.request_key
    assert unknown["preview_data"] is None and unknown["parse_state"] == "UNKNOWN"
    assert source == untouched
