"""Real owned PG author matrix. Collecting is offline; fixtures never start PostgreSQL.

Execution requires Root's exact SQL review, source binding and owned UTC window. These cases
create only isolated v4_demo databases through the existing fixture and retain original errors.
"""

import base64
import hashlib
import secrets
from dataclasses import replace
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from commerceops.application.replenishment.contracts import WebFailure
from commerceops.application.v4_demo import contracts as legacy
from commerceops.application.v41 import contracts as dto
from commerceops.domain.commerce_values import canonical_bytes
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.v41_runtime import RUNTIME, TABLES, grant_runtime
from commerceops.infrastructure.v41_security import activate_policy, binding_proof
from commerceops.infrastructure.v41_store import BusinessStore
from psycopg import sql

from tests.v4.test_demo_sessions_pg import DemoPG, enter
from tests.v4.test_demo_sessions_pg import demo as demo

pytestmark = pytest.mark.integration


@pytest.fixture
def business(demo: DemoPG) -> tuple[DemoPG, BusinessStore]:
    with connect(demo.owner) as db:
        activate_policy(db, demo.config)
        grant_runtime(db, demo.config)
    return demo, BusinessStore(demo.config)


def session(demo: DemoPG) -> tuple[str, dict[str, Any], UUID]:
    _, token = enter(demo)
    current = demo.store.sessions.current(token)
    shop = next(r for r in current["data"]["shops"] if r["currency"] == "TWD")
    return token, current, UUID(shop["shop_id"])


def page(
    store: BusinessStore, token: str, shop: UUID, epoch: int = 0, generation: int = 0
) -> dto.Page[dto.Product]:
    return cast(
        dto.Page[dto.Product],
        store.read(token, epoch, generation, dto.ProductQuery(shop_id=shop), "products")["data"],
    )


def tags(
    shop: UUID, revision: str, *, version: int = 0, values: tuple[str, ...] = ("中文😀",)
) -> dto.SetProductTags:
    return dto.SetProductTags(
        shop_id=shop,
        request_key=uuid4(),
        expected_epoch=0,
        expected_generation=0,
        expected_data_revision=revision,
        expected_version=version,
        tags=values,
    )


def preview_command(
    shop: UUID,
    revision: str,
    *,
    sku: str = "NEW-1",
    parent: UUID | None = None,
    mapping: bool = True,
) -> dto.ImportPreviewInput:
    raw = f"sku,title,price,currency,tags\n{sku},导入商品,0.10,TWD,演示\n".encode()
    return dto.ImportPreviewInput(
        shop_id=shop,
        request_key=uuid4(),
        expected_epoch=0,
        expected_generation=0,
        expected_data_revision=revision,
        format="csv",
        filename="products.csv",
        file_base64=base64.b64encode(raw).decode(),
        parent_job_id=parent,
        mapping=dto.ColumnMapping(
            sku="sku", title="title", price="price", currency="currency", tags="tags"
        )
        if mapping
        else None,
    )


def test_seven_tables_private_helpers_and_low_role_no_dml(
    business: tuple[DemoPG, BusinessStore],
) -> None:
    demo, _ = business
    with connect(demo.app) as db:
        for suffix in TABLES:
            name = "business.v41_" + suffix
            row = db.execute(
                "SELECT has_table_privilege(current_user,%s,'SELECT') AS can_read,"
                "has_table_privilege(current_user,%s,'INSERT,UPDATE,DELETE,TRUNCATE') AS can_write",
                (name, name),
            ).fetchone()
            assert row == dict(can_read=True, can_write=False)
        for signature in RUNTIME:
            assert db.execute(
                "SELECT has_function_privilege(current_user,%s,'EXECUTE') AS allowed",
                ("business." + signature,),
            ).fetchone() == dict(allowed=True)
        for signature in (
            "v41_actor(text,text,text,uuid,bigint,bigint,boolean)",
            "v41_canonical(jsonb)",
            "v41_hash(jsonb)",
            "v41_text_valid(text)",
            "v41_hmac_sha256(bytea,bytea)",
            "v41_invocation_mac(bytea,uuid,text)",
        ):
            assert db.execute(
                "SELECT has_function_privilege(current_user,%s,'EXECUTE') AS allowed",
                ("business." + signature,),
            ).fetchone() == dict(allowed=False)
    with connect(demo.app) as db:
        row = db.execute(
            "SELECT has_table_privilege(current_user,%s,'SELECT') AS table_read,"
            "has_column_privilege(current_user,%s,'active_version','SELECT') AS metadata,"
            "has_column_privilege(current_user,%s,'invocation_verifier','SELECT') AS private_read",
            ("business.v41_security_policy",) * 3,
        ).fetchone()
        assert row == dict(table_read=False, metadata=True, private_read=False)
    for suffix in (*TABLES, "security_policy"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connect(demo.app) as db:
            db.execute(
                sql.SQL("DELETE FROM {} WHERE false").format(
                    sql.Identifier("business", "v41_" + suffix)
                )
            )
    with connect(demo.owner) as db:
        assert db.execute(
            "SELECT count(*) AS n FROM business.v41_security_policy"
        ).fetchone() == dict(n=1)


def test_sql_python_canonical_text_corpus(business: tuple[DemoPG, BusinessStore]) -> None:
    demo, _ = business
    corpus = (
        "中文",
        "😀",
        "é",
        "e\u0301",
        "a b",
        "=SUM(A1)",
        "+sale",
        "@tag",
        "-sale",
        " leading",
        "trailing ",
        "\u00a0x",
        "x\u00a0",
        "a\u2007b",
        "a\u202fb",
        "a\u200bb",
        "a\u202eb",
        "a\u2060b",
        "a\u0001b",
        "a\u007fb",
        "a\n",
        "a\t",
    )
    with connect(demo.owner) as db:
        for value in corpus:
            try:
                dto.canonical_tags((value,))
                accepted = True
            except ValueError:
                accepted = False
            actual = db.execute(
                "SELECT business.v41_tags_valid(to_jsonb(ARRAY[%s]::text[])) AS allowed", (value,)
            ).fetchone()
            assert actual == dict(allowed=accepted), (repr(value), accepted, actual)


def test_golden_reads_tags_receipt_replay_original_after_later_effect(
    business: tuple[DemoPG, BusinessStore],
) -> None:
    demo, store = business
    token, current, shop = session(demo)
    original = page(store, token, shop)
    assert original.total == 8 and len(original.items) == 8
    query = dto.PeriodQuery(shop_id=shop)
    report = store.read(token, 0, 0, query, "dashboard")["data"]
    assert report.snapshot.data_revision == original.snapshot.data_revision
    amounts = {row.metric: row for row in report.metrics}
    assert amounts["paid_order_amount"].known_value == "2140"
    assert amounts["paid_order_amount"].value is None
    target = original.items[0].product_id
    command = tags(shop, original.snapshot.data_revision)
    one = store.action(token, current["data"]["csrf_token"], command, "product_tags", target)[
        "data"
    ]
    for _ in range(10):
        assert (
            store.action(token, current["data"]["csrf_token"], command, "product_tags", target)[
                "data"
            ]
            == one
        )
    after = page(store, token, shop)
    changed = next(p for p in after.items if p.product_id == target)
    assert changed.tags == ("中文😀",) and changed.version == 1
    assert (
        after.snapshot.data_revision
        == one.receipt.after_revision
        != original.snapshot.data_revision
    )
    two_command = tags(shop, after.snapshot.data_revision, version=1, values=("second",))
    two = store.action(token, current["data"]["csrf_token"], two_command, "product_tags", target)[
        "data"
    ]
    assert two.receipt.resource_version == 2
    assert (
        store.action(token, current["data"]["csrf_token"], command, "product_tags", target)["data"]
        == one
    )
    recovered = store.action_lookup(
        token, 0, 0, dto.Query(shop_id=shop), "product_tags", command.request_key
    )["data"]
    assert recovered.status == "COMMITTED" and recovered.receipt == one.receipt
    with connect(demo.owner) as db:
        assert db.execute("SELECT count(*) AS n FROM business.v41_product_tags").fetchone() == dict(
            n=1
        )
        assert db.execute(
            "SELECT count(*) AS n FROM business.v41_action_receipts"
        ).fetchone() == dict(n=2)
        assert db.execute(
            "SELECT count(*) AS n FROM business.v41_action_events"
        ).fetchone() == dict(n=2)


def test_paid_unknown_fulfillment_and_atomic_rollback_on_audit_failure(
    business: tuple[DemoPG, BusinessStore],
) -> None:
    demo, store = business
    token, current, shop = session(demo)
    orders = store.read(token, 0, 0, dto.OrderQuery(shop_id=shop, days=14), "orders")["data"]
    unknown = next(o for o in orders.items if o.paid_at is None)
    command = dto.FulfillDemoOrder(
        shop_id=shop,
        request_key=uuid4(),
        expected_epoch=0,
        expected_generation=0,
        expected_data_revision=orders.snapshot.data_revision,
        expected_version=0,
        action="mark_demo_fulfilled",
    )
    with pytest.raises(psycopg.errors.CheckViolation, match="PAYMENT_STATE_UNKNOWN"):
        store.action(
            token, current["data"]["csrf_token"], command, "order_fulfillment", unknown.order_id
        )
    target = next(o for o in orders.items if o.paid_at is not None)
    with connect(demo.owner) as db:
        db.execute("""CREATE FUNCTION business.v41_author_fail() RETURNS trigger LANGUAGE plpgsql
            AS $$ BEGIN RAISE EXCEPTION 'V41_AUTHOR_AUDIT_FAILURE'; END $$""")
        db.execute("""CREATE TRIGGER v41_author_fail BEFORE INSERT ON business.v41_action_events
            FOR EACH ROW EXECUTE FUNCTION business.v41_author_fail()""")
    try:
        with pytest.raises(psycopg.Error, match="V41_AUTHOR_AUDIT_FAILURE"):
            store.action(
                token, current["data"]["csrf_token"], command, "order_fulfillment", target.order_id
            )
        with connect(demo.owner) as db:
            for suffix in ("order_fulfillments", "action_receipts", "action_events"):
                assert db.execute(
                    sql.SQL("SELECT count(*) AS n FROM {}").format(
                        sql.Identifier("business", "v41_" + suffix)
                    )
                ).fetchone() == dict(n=0)
    finally:
        with connect(demo.owner) as db:
            db.execute("DROP TRIGGER v41_author_fail ON business.v41_action_events")
            db.execute("DROP FUNCTION business.v41_author_fail()")
    committed = store.action(
        token, current["data"]["csrf_token"], command, "order_fulfillment", target.order_id
    )["data"]
    assert committed.receipt.resource_version == 1
    assert (
        store.action(
            token, current["data"]["csrf_token"], command, "order_fulfillment", target.order_id
        )["data"]
        == committed
    )


def test_real_native_preview_confirm_same_job_version_sources_and_all_result_export(
    business: tuple[DemoPG, BusinessStore],
) -> None:
    demo, store = business
    token, current, shop = session(demo)
    before = page(store, token, shop)
    command = preview_command(shop, before.snapshot.data_revision)
    preview = store.preview(token, current["data"]["csrf_token"], command)["data"]
    assert preview.state == "READY" and preview.confirmable and preview.row_count == 1
    assert store.preview(token, current["data"]["csrf_token"], command)["data"] == preview
    ref = preview.job
    confirm = dto.ConfirmImport(
        shop_id=shop,
        request_key=uuid4(),
        expected_epoch=0,
        expected_generation=0,
        expected_data_revision=before.snapshot.data_revision,
        expected_job_version=ref.version,
        expected_job_digest=ref.job_digest,
    )
    result = store.action(
        token, current["data"]["csrf_token"], confirm, "import_confirm", ref.import_job_id
    )["data"]
    for _ in range(10):
        assert (
            store.action(
                token, current["data"]["csrf_token"], confirm, "import_confirm", ref.import_job_id
            )["data"]
            == result
        )
    assert (
        result.receipt.resource_id == ref.import_job_id
        and result.receipt.resource_version == ref.version
    )
    actual = store.preview_lookup(
        token, 0, 0, dto.Query(shop_id=shop), ref.import_job_id, by_id=True
    )["data"]
    assert actual.state == "COMMITTED" and actual.job == ref and not actual.confirmable
    after = page(store, token, shop)
    imported = next(p for p in after.items if p.source.data_mode == "demo_upload")
    assert after.total == 9 and after.snapshot.data_revision == result.receipt.after_revision
    assert imported.source.import_job_id == ref.import_job_id and imported.source.import_row == 2
    assert imported.skus[0].available_units is None
    exported = store.read(token, 0, 0, dto.ProductQuery(shop_id=shop, limit=1), "product_export")[
        "data"
    ]
    assert exported.row_count == 11 and "NEW-1" in exported.csv_text
    context = store.read(
        token,
        0,
        0,
        dto.ReadContextQuery(shop_id=shop, kind="product", resource_id=imported.product_id),
        "read_context",
    )["data"]
    assert context.product == imported
    with connect(demo.owner) as db:
        row = db.execute(
            "SELECT parse_state,parse_slot,parse_pid,stop_proof FROM business.v41_import_jobs"
        ).fetchone()
        assert row is not None
        assert row["parse_state"] == "STOPPED" and row["parse_slot"] is None
        assert (
            row["stop_proof"]["pid"] == row["parse_pid"] and row["stop_proof"]["native_exit"] == 0
        )
        assert row["stop_proof"]["reaped"] is True
        for suffix in ("import_products", "action_receipts", "action_events", "import_jobs"):
            assert db.execute(
                sql.SQL("SELECT count(*) AS n FROM {}").format(
                    sql.Identifier("business", "v41_" + suffix)
                )
            ).fetchone() == dict(n=1)


def test_changed_revision_cannot_confirm_old_preview_and_reset_hides_effects(
    business: tuple[DemoPG, BusinessStore],
) -> None:
    demo, store = business
    token, current, shop = session(demo)
    before = page(store, token, shop)
    preview = store.preview(
        token, current["data"]["csrf_token"], preview_command(shop, before.snapshot.data_revision)
    )["data"]
    changed = store.action(
        token,
        current["data"]["csrf_token"],
        tags(shop, before.snapshot.data_revision),
        "product_tags",
        before.items[0].product_id,
    )["data"]
    confirm = dto.ConfirmImport(
        shop_id=shop,
        request_key=uuid4(),
        expected_epoch=0,
        expected_generation=0,
        expected_data_revision=changed.receipt.after_revision,
        expected_job_version=preview.job.version,
        expected_job_digest=preview.job.job_digest,
    )
    with pytest.raises(psycopg.errors.CheckViolation, match="SNAPSHOT_CHANGED"):
        store.action(
            token,
            current["data"]["csrf_token"],
            confirm,
            "import_confirm",
            preview.job.import_job_id,
        )
    demo.store.control(
        token,
        current["data"]["csrf_token"],
        "reset",
        legacy.ResetInput(
            request_key=uuid4(),
            expected_epoch=0,
            expected_generation=0,
            fixture_version="v4-demo-seed-1",
        ),
    )
    reset = page(store, token, shop, 1, 1)
    assert reset.total == 8 and all(p.version == 0 for p in reset.items)
    with pytest.raises(WebFailure, match="EPOCH_CHANGED"):
        page(store, token, shop)
    with pytest.raises(WebFailure, match="RESOURCE_NOT_FOUND"):
        store.preview_lookup(
            token, 1, 1, dto.Query(shop_id=shop), preview.job.import_job_id, by_id=True
        )
    with connect(demo.owner) as db:
        assert db.execute("SELECT count(*) AS n FROM business.v41_product_tags").fetchone() == dict(
            n=1
        )


def test_parent_mapping_chain_supersedes_and_disallows_old_confirm(
    business: tuple[DemoPG, BusinessStore],
) -> None:
    demo, store = business
    token, current, shop = session(demo)
    revision = page(store, token, shop).snapshot.data_revision
    first_command = preview_command(shop, revision, mapping=False)
    first = store.preview(token, current["data"]["csrf_token"], first_command)["data"]
    assert first.state == "DISCOVERED" and not first.confirmable
    child = store.preview(
        token,
        current["data"]["csrf_token"],
        preview_command(shop, revision, parent=first.job.import_job_id),
    )["data"]
    assert child.job.version == 2 and child.job.parent_job_id == first.job.import_job_id
    old = store.preview_lookup(
        token, 0, 0, dto.Query(shop_id=shop), first.job.import_job_id, by_id=True
    )["data"]
    assert old.state == "SUPERSEDED" and not old.confirmable
    with pytest.raises(psycopg.errors.CheckViolation, match="STATE_CONFLICT"):
        store.preview(
            token,
            current["data"]["csrf_token"],
            preview_command(shop, revision, parent=first.job.import_job_id),
        )


def test_missing_policy_wrong_config_old_version_and_no_implicit_reactivation(demo: DemoPG) -> None:
    token, _, shop = session(demo)
    store = BusinessStore(demo.config)
    # Separate an ungranted table from a readable-but-uninitialized policy authority.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        page(store, token, shop)
    with connect(demo.owner) as db:
        db.execute(
            "GRANT SELECT(singleton,active_version,config_digest) ON business.v41_security_policy "
            "TO commerceops_app"
        )
    with pytest.raises(WebFailure, match="SERVICE_UNAVAILABLE"):
        page(store, token, shop)
    with connect(demo.owner) as db:
        activate_policy(db, demo.config)
        grant_runtime(db, demo.config)
    assert page(store, token, shop).total == 8
    changed = replace(
        demo.config, web=replace(demo.config.web, csrf_secret=secrets.token_bytes(32))
    )
    with pytest.raises(WebFailure):
        page(BusinessStore(changed), token, shop)
    with pytest.raises(ValueError, match="V41_POLICY_VERSION_REUSE"), connect(demo.owner) as db:
        activate_policy(db, changed)
    rotated = replace(demo.config, web=replace(demo.config.web, key_version="v2"))
    with connect(demo.owner) as db:
        result = activate_policy(db, rotated)
        assert result["generation"] == 2 and result["revoked_demo_bindings"] == 1
    with pytest.raises(WebFailure):
        page(store, token, shop)
    with pytest.raises(ValueError, match="V41_POLICY_VERSION_REUSE"), connect(demo.owner) as db:
        activate_policy(db, demo.config)


def test_durable_reservation_survives_connection_release_without_expiry_reuse(
    business: tuple[DemoPG, BusinessStore],
) -> None:
    demo, store = business
    token, current, shop = session(demo)
    revision = page(store, token, shop).snapshot.data_revision
    command = preview_command(shop, revision)
    raw_digest = hashlib.sha256(base64.b64decode(command.file_base64)).hexdigest()
    canonical = canonical_bytes(
        dict(
            command=command.model_dump(mode="json", exclude={"file_base64"}), file_digest=raw_digest
        )
    ).decode()
    lease, process_ref = secrets.token_urlsafe(32), uuid4()
    with connect(demo.app) as db:
        subject = demo.store.sessions.resolve_locked(db, token)
        binding = binding_proof(demo.config, subject.session["bound_web_session_id"])
        row = db.execute(
            "SELECT * FROM business.v41_reserve_preview(%s,%s,%s,%s,%s,%s)",
            (
                token,
                current["data"]["csrf_token"],
                binding,
                canonical,
                hashlib.sha256(lease.encode()).hexdigest(),
                process_ref,
            ),
        ).fetchone()
        assert row is not None
        assert row["parse_state"] == "RESERVED" and row["parse_slot"] in (0, 1)
    # Closing its allocating connection releases every advisory lock; the held durable row remains.
    with pytest.raises(psycopg.errors.CheckViolation, match="RATE_LIMITED"):
        store.preview(
            token, current["data"]["csrf_token"], preview_command(shop, revision, sku="NEW-2")
        )
    recovered = store.preview_lookup(token, 0, 0, dto.Query(shop_id=shop), command.request_key)[
        "data"
    ]
    assert recovered.status == "UNKNOWN" and recovered.job is None
    with connect(demo.owner) as db:
        persisted = db.execute(
            "SELECT parse_state,parse_slot,stop_proof FROM business.v41_import_jobs"
        ).fetchone()
        assert persisted is not None
        assert (
            persisted["parse_state"] == "RESERVED" and persisted["parse_slot"] == row["parse_slot"]
        )
        assert persisted["stop_proof"] is None


def _exit_after_native_bind(
    config: Any, token: str, csrf: str, command: dto.ImportPreviewInput, pipe: Any
) -> None:
    """Owned process-death fixture: the actual native parser remains under its own alarm."""
    import os
    from unittest.mock import patch

    from commerceops.infrastructure.v41_parse import run_parser as original

    def lose_parent(native_command: Any, process_ref: UUID, bind: Any, stop: Any) -> Any:
        def bound(pid: int) -> None:
            bind(pid)  # Durable RUNNING/PID COMMIT first.
            pipe.send(dict(pid=pid, process_ref=str(process_ref)))
            os._exit(17)

        return original(native_command, process_ref, bound, stop)

    with patch("commerceops.infrastructure.v41_store.run_parser", lose_parent):
        BusinessStore(config).preview(token, csrf, command)
    raise AssertionError("owned parent did not stop at the registered death boundary")


def test_actual_parent_death_keeps_running_unknown_slot_without_auto_replay(
    business: tuple[DemoPG, BusinessStore],
) -> None:
    import multiprocessing

    demo, store = business
    token, current, shop = session(demo)
    revision = page(store, token, shop).snapshot.data_revision
    command = preview_command(shop, revision)
    # All parent database connections have closed before fork; the worker creates fresh ones.
    context = multiprocessing.get_context("fork")
    receive, send = context.Pipe(duplex=False)
    parent = context.Process(
        target=_exit_after_native_bind,
        args=(demo.config, token, current["data"]["csrf_token"], command, send),
    )
    parent.start()
    try:
        assert receive.poll(8), "no actual native bind receipt"
        evidence = receive.recv()
        parent.join(timeout=5)
        assert parent.exitcode == 17
        with connect(demo.owner) as db:
            row = db.execute(
                "SELECT parse_state,parse_slot,parse_pid,process_ref,stop_proof "
                "FROM business.v41_import_jobs"
            ).fetchone()
            assert row is not None and row["parse_state"] == "RUNNING"
            assert (
                row["parse_pid"] == evidence["pid"]
                and str(row["process_ref"]) == evidence["process_ref"]
            )
            assert row["stop_proof"] is None and row["parse_slot"] in (0, 1)
        with pytest.raises(psycopg.errors.CheckViolation, match="RATE_LIMITED"):
            store.preview(
                token, current["data"]["csrf_token"], preview_command(shop, revision, sku="NEW-2")
            )
        # No fabricated stop/reap proof for an orphan: unknown durable capacity remains held.
    finally:
        if parent.is_alive():
            parent.kill()
        parent.join(timeout=5)
        receive.close()
        send.close()


def test_two_actual_children_global_slots_and_reap_before_next_admission(
    business: tuple[DemoPG, BusinessStore],
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from commerceops.application.v41.parse_protocol import ParseInput
    from commerceops.infrastructure.v4_demo_sessions import bounded
    from commerceops.infrastructure.v41_parse import run_parser
    from psycopg.types.json import Jsonb

    demo, store = business
    owners = [session(demo) for _ in range(3)]
    ready = [Event(), Event()]
    release = Event()
    reservations = []
    for token, current, shop in owners[:2]:
        command = preview_command(shop, page(store, token, shop).snapshot.data_revision)
        lease, process_ref = secrets.token_urlsafe(32), uuid4()
        canonical = canonical_bytes(
            dict(
                command=command.model_dump(mode="json", exclude={"file_base64"}),
                file_digest=hashlib.sha256(base64.b64decode(command.file_base64)).hexdigest(),
            )
        ).decode()
        with connect(demo.app) as db:
            subject = demo.store.sessions.resolve_locked(db, token)
            row = db.execute(
                "SELECT * FROM business.v41_reserve_preview(%s,%s,%s,%s,%s,%s)",
                (
                    token,
                    current["data"]["csrf_token"],
                    binding_proof(demo.config, subject.session["bound_web_session_id"]),
                    canonical,
                    hashlib.sha256(lease.encode()).hexdigest(),
                    process_ref,
                ),
            ).fetchone()
            assert row is not None
            reservations.append((command, lease, process_ref, row["id"]))

    def parse(index: int) -> Any:
        command, lease, process_ref, job = reservations[index]

        def bind(pid: int) -> None:
            with connect(demo.app) as db:
                bounded(db)
                db.execute(
                    "SELECT business.v41_bind_parser(%s,%s,%s,%s)", (job, lease, process_ref, pid)
                )
            ready[index].set()
            assert release.wait(1), (
                "parent did not release actual parser input within kernel budget"
            )

        def stop(proof: dict[str, Any]) -> None:
            with connect(demo.app) as db:
                bounded(db)
                db.execute(
                    "SELECT business.v41_stop_parser(%s,%s,%s,%s)",
                    (job, lease, process_ref, Jsonb(proof)),
                )

        return run_parser(
            ParseInput(
                format=command.format,
                file_base64=command.file_base64,
                mapping=command.mapping,
                currency="TWD",
                existing_skus=(),
            ),
            process_ref,
            bind,
            stop,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(parse, index) for index in range(2)]
        try:
            assert all(event.wait(1) for event in ready), "missing actual native PID bind"
            token, current, shop = owners[2]
            revision = page(store, token, shop).snapshot.data_revision
            with pytest.raises(psycopg.errors.CheckViolation, match="RATE_LIMITED"):
                store.preview(token, current["data"]["csrf_token"], preview_command(shop, revision))
        finally:
            release.set()
        results = [future.result(timeout=5) for future in futures]
    assert all(r.proof["reaped"] and r.proof["native_exit"] == 0 for r in results)
    token, current, shop = owners[2]
    accepted = store.preview(token, current["data"]["csrf_token"], preview_command(shop, revision))[
        "data"
    ]
    assert accepted.state == "READY"


@pytest.mark.parametrize(
    "table", ["web_credentials", "principal_shop_scopes", "principal_role_shop_grants"]
)
@pytest.mark.parametrize("revoke_first", [False, True])
def test_revocation_commit_order_and_tuple_principal_crossing_no_deadlock(
    business: tuple[DemoPG, BusinessStore],
    table: str,
    revoke_first: bool,
) -> None:
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from commerceops.infrastructure.v4_demo_sessions import bounded

    demo, store = business
    token, current, shop = session(demo)
    before = page(store, token, shop)
    command = tags(shop, before.snapshot.data_revision)
    target = before.items[0].product_id
    canonical = canonical_bytes(
        dict(
            method="POST",
            path=f"/api/v4/products/{target}/tags",
            body=command.model_dump(mode="json"),
        )
    ).decode()
    where = "identity_id=%s" if table == "web_credentials" else "principal_id=%s AND shop_id=%s"
    where += " AND role='operator'" if table == "principal_role_shop_grants" else ""
    started = Event()
    revoker_pid = []
    with connect(demo.app) as active:
        bounded(active)
        subject = demo.store.sessions.resolve_locked(active, token)
        binding = binding_proof(demo.config, subject.session["bound_web_session_id"])
        values = (
            (subject.session["identity_id"],)
            if table == "web_credentials"
            else (subject.session["principal_id"], shop)
        )
        if revoke_first:
            active.rollback()  # Let the revocation actually commit before starting the action.
        actor_pid = active.info.backend_pid

        def revoke() -> None:
            with connect(demo.owner) as owner:
                bounded(owner)
                revoker_pid.append(owner.info.backend_pid)
                started.set()
                changed = owner.execute(
                    sql.SQL(
                        "UPDATE {} SET enabled=false WHERE {} AND enabled RETURNING principal_id"
                    ).format(sql.Identifier("business", table), sql.SQL(where)),
                    values,
                ).fetchall()
                assert len(changed) == 1

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(revoke)
            assert started.wait(1)
            if revoke_first:
                future.result(timeout=2)  # Only a committed revocation satisfies this ordering.
                with pytest.raises(WebFailure, match="SESSION_INVALID"):
                    store.action(
                        token, current["data"]["csrf_token"], command, "product_tags", target
                    )
            else:
                # UPDATE has acquired its credential/scope/grant tuple before its BEFORE
                # trigger waits for this exact principal SHARE lock. This was the reverse edge.
                blocked = False
                end = time.monotonic() + 0.5
                while time.monotonic() < end:
                    with connect(demo.owner) as probe:
                        row = probe.execute(
                            "SELECT %s=ANY(pg_blocking_pids(%s)) AS blocked",
                            (actor_pid, revoker_pid[0]),
                        ).fetchone()
                    if row == dict(blocked=True):
                        blocked = True
                        break
                    time.sleep(0.01)
                assert blocked, "revoker did not reach the original principal trigger wait"
                result = active.execute(
                    "SELECT * FROM business.v41_apply_action(%s,%s,%s,%s,%s,%s)",
                    (
                        token,
                        current["data"]["csrf_token"],
                        binding,
                        canonical,
                        "product_tags",
                        target,
                    ),
                ).fetchone()
                assert result is not None and result["resource_version"] == 1
                active.commit()
                future.result(timeout=2)  # Deadlock/lock-timeout/503 is never an accepted outcome.
    with connect(demo.owner) as owner:
        for suffix in ("product_tags", "action_receipts", "action_events"):
            assert owner.execute(
                sql.SQL("SELECT count(*) AS n FROM {}").format(
                    sql.Identifier("business", "v41_" + suffix)
                )
            ).fetchone() == dict(n=0 if revoke_first else 1)
    with pytest.raises(WebFailure, match="SESSION_INVALID"):
        page(store, token, shop)


def test_sql_current_policy_rejects_two_old_consistent_session_rows(
    business: tuple[DemoPG, BusinessStore],
) -> None:
    from commerceops.infrastructure.v41_security import config_fingerprint

    demo, store = business
    token, _, shop = session(demo)
    with connect(demo.app) as db:
        subject = demo.store.sessions.resolve_locked(db, token)
        binding = binding_proof(demo.config, subject.session["bound_web_session_id"])
    rotated = replace(demo.config, web=replace(demo.config.web, key_version="v3"))
    with connect(demo.owner) as owner:
        # Isolate the SQL counterexample: valid owner policy transition, intentionally leave
        # both old session key_version rows consistent and not revoked by activate_policy().
        owner.execute(
            """UPDATE business.v41_security_policy SET active_version=%s,config_digest=%s,
            generation=generation+1,retired_versions=array_append(retired_versions,active_version),
            activated_at=clock_timestamp() WHERE singleton""",
            (rotated.web.key_version, config_fingerprint(rotated)),
        )
        row = owner.execute(
            """SELECT s.key_version AS demo_version,w.key_version AS bound_version,w.revoked_at
            FROM business.v4_demo_sessions s JOIN business.web_sessions w
            ON w.id=s.bound_web_session_id WHERE s.id=%s""",
            (subject.session["id"],),
        ).fetchone()
        assert row == dict(
            demo_version=demo.config.web.key_version,
            bound_version=demo.config.web.key_version,
            revoked_at=None,
        )
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="SESSION_INVALID"),
        connect(demo.app) as app,
    ):
        app.execute("SELECT business.v41_read_guard(%s,%s,%s,%s,%s)", (token, binding, shop, 0, 0))
    with pytest.raises(WebFailure, match="SERVICE_UNAVAILABLE"):
        page(store, token, shop)


def test_private_verifier_hmac_goldens_and_forged_writable_binding_no_admission(
    business: tuple[DemoPG, BusinessStore],
) -> None:
    import hmac

    demo, store = business
    token, current, shop = session(demo)
    revision = page(store, token, shop).snapshot.data_revision
    with connect(demo.app) as db:
        subject = demo.store.sessions.resolve_locked(db, token)
        bound = subject.session["bound_web_session_id"]
        original = db.execute(
            "SELECT csrf_digest FROM business.web_sessions WHERE id=%s", (bound,)
        ).fetchone()
        assert original is not None
    for query in (
        "SELECT invocation_verifier FROM business.v41_security_policy",
        "SELECT * FROM business.v41_security_policy",
        "SELECT business.v41_hmac_sha256('a'::bytea,'b'::bytea)",
        "SELECT business.v41_invocation_mac('a'::bytea,NULL,NULL)",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connect(demo.app) as db:
            db.execute(query)
    with connect(demo.owner) as owner:
        vectors = (
            (bytes([11]) * 20, b"Hi There"),
            (b"Jefe", b"what do ya want for nothing?"),
            (bytes([170]) * 131, b"Test Using Larger Than Block-Size Key - Hash Key First"),
            (bytes(range(32)), b""),
            (bytes(range(64)), bytes(range(256))),
            (bytes(range(65)), b"longer than a block"),
        )
        for material, payload in vectors:
            row = owner.execute(
                "SELECT business.v41_hmac_sha256(%s,%s) AS digest", (material, payload)
            ).fetchone()
            assert row is not None and bytes(row["digest"]) == hmac.digest(
                material, payload, "sha256"
            )
        from commerceops.infrastructure.v41_security import invocation_key

        proof = binding_proof(demo.config, bound)
        expected = owner.execute(
            "SELECT business.v41_invocation_mac(%s,%s,%s) AS proof",
            (invocation_key(demo.config), bound, demo.config.web.key_version),
        ).fetchone()
        assert expected is not None and expected["proof"] == proof.split(".")[1]
    for bad_material, bad_payload in (
        (None, b"x"),
        (b"", b"x"),
        (b"x" * 1025, b"x"),
        (b"x", None),
        (b"x", b"x" * 4097),
    ):
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="INVALID_REQUEST"),
            connect(demo.owner) as owner,
        ):
            owner.execute("SELECT business.v41_hmac_sha256(%s,%s)", (bad_material, bad_payload))
    command = preview_command(shop, revision)
    canonical = canonical_bytes(
        dict(
            command=command.model_dump(mode="json", exclude={"file_base64"}),
            file_digest=hashlib.sha256(base64.b64decode(command.file_base64)).hexdigest(),
        )
    ).decode()
    chosen = secrets.token_urlsafe(32)
    forged = chosen + "." + secrets.token_urlsafe(32)
    with connect(demo.app) as attacker:
        # This legacy permission really exists; the new authority cannot depend solely on it.
        attacker.execute(
            "UPDATE business.web_sessions SET csrf_digest=%s WHERE id=%s",
            (hashlib.sha256(chosen.encode()).hexdigest(), bound),
        )
    try:
        wrong_session = binding_proof(demo.config, uuid4()).split(".")[1]
        wrong_version = binding_proof(
            replace(demo.config, web=replace(demo.config.web, key_version="v3")), bound
        ).split(".")[1]
        for fake in (
            chosen,
            forged,
            chosen + "." + wrong_session,
            chosen + "." + wrong_version,
            chosen + ".." + chosen,
            chosen + "." + chosen + "." + chosen,
            "",
            chosen + ".short",
        ):
            with (
                pytest.raises(psycopg.errors.CheckViolation, match="SESSION_INVALID"),
                connect(demo.app) as attacker,
            ):
                attacker.execute(
                    "SELECT * FROM business.v41_reserve_preview(%s,%s,%s,%s,%s,%s)",
                    (
                        token,
                        current["data"]["csrf_token"],
                        fake,
                        canonical,
                        hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
                        uuid4(),
                    ),
                )
        with connect(demo.owner) as owner:
            assert owner.execute(
                "SELECT count(*) AS n FROM business.v41_import_jobs"
            ).fetchone() == dict(n=0)
    finally:
        with connect(demo.app) as db:
            db.execute(
                "UPDATE business.web_sessions SET csrf_digest=%s WHERE id=%s",
                (original["csrf_digest"], bound),
            )
    assert page(store, token, shop).total == 8


@pytest.mark.parametrize(
    "table", ["web_credentials", "principal_shop_scopes", "principal_role_shop_grants"]
)
def test_demo_binding_reassignment_denied_before_original_new_principal_trigger(
    business: tuple[DemoPG, BusinessStore],
    table: str,
) -> None:
    demo, store = business
    token, _, shop = session(demo)
    with connect(demo.owner) as owner:
        personas = owner.execute(
            "SELECT * FROM business.v4_demo_personas WHERE tenant_id="
            "(SELECT tenant_id FROM business.v4_demo_sessions WHERE token_hash=%s)",
            (hashlib.sha256(token.encode()).hexdigest(),),
        ).fetchall()
        original = next(p for p in personas if p["persona_id"] == "operator")
        target = next(p for p in personas if p["persona_id"] == "approver")
        before = owner.execute(
            "SELECT id,auth_version FROM business.principals WHERE organization_id=%s ORDER BY id",
            (original["organization_id"],),
        ).fetchall()
        trigger = owner.execute(
            "SELECT tgname FROM pg_trigger WHERE tgrelid=%s::regclass "
            "AND NOT tgisinternal AND tgname IN('a_v41_demo_binding','p3_scope_principal_lock') "
            "ORDER BY tgname",
            ("business." + table,),
        ).fetchall()
        assert [r["tgname"] for r in trigger] == ["a_v41_demo_binding", "p3_scope_principal_lock"]
    where = "principal_id=%s" + (" AND shop_id=%s" if table != "web_credentials" else "")
    where += " AND role='operator'" if table == "principal_role_shop_grants" else ""
    values = (
        (original["principal_id"], shop)
        if table != "web_credentials"
        else (original["principal_id"],)
    )
    statement = sql.SQL("UPDATE {} SET principal_id=%s {} WHERE {}").format(
        sql.Identifier("business", table),
        sql.SQL(",identity_id=%s" if table == "web_credentials" else ""),
        sql.SQL(where),
    )
    assigned = (
        (target["principal_id"], target["identity_id"])
        if table == "web_credentials"
        else (target["principal_id"],)
    )
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="V41_DEMO_BINDING_IMMUTABLE"),
        connect(demo.owner) as owner,
    ):
        owner.execute(statement, assigned + values)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), connect(demo.app) as app:
        app.execute(statement, assigned + values)
    with connect(demo.owner) as owner:
        after = owner.execute(
            "SELECT id,auth_version FROM business.principals WHERE organization_id=%s ORDER BY id",
            (original["organization_id"],),
        ).fetchall()
        assert after == before
    assert page(store, token, shop).total == 8
