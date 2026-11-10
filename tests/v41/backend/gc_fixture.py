"""Narrow new-owned GC history candidate; execution requires Root's separate PG window.

SYNTHETIC_OWNED_HISTORICAL_FIXTURE is an initialization-only time transform of a
closed, normally committed synthetic graph. It is neither runtime admission nor natural soak.
No connection, environment/secret read, parser or database fixture runs on module import.
"""

import base64
import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from commerceops.application.v41 import contracts as dto
from commerceops.domain.commerce_values import canonical_bytes
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.v4_demo_seed import require_owner
from commerceops.infrastructure.v4_demo_sessions import DB, bounded
from commerceops.infrastructure.v41_runtime import TABLES
from commerceops.infrastructure.v41_store import BusinessStore
from psycopg import sql
from psycopg.types.json import Jsonb

from tests.v4.test_demo_sessions_pg import DemoPG, enter

LABEL = "SYNTHETIC_OWNED_HISTORICAL_FIXTURE"
SHIFT = timedelta(hours=48)
CORE = (
    "organizations",
    "shops",
    "principals",
    "identities",
    "principal_shop_scopes",
    "principal_role_shop_grants",
    "web_credentials",
    "web_sessions",
)
V4 = ("tenants", "shops", "personas", "bootstraps", "sessions", "receipts", "events", "overlays")
Row = dict[str, Any]
Graph = dict[str, list[Row]]


@dataclass(frozen=True)
class Subject:
    tenant: UUID
    organization: UUID
    session: UUID
    bootstrap: UUID
    shop: UUID
    token: str = field(repr=False)
    file_digest: str


def text(value: Any) -> str:
    return canonical_bytes(value).decode()


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def products(store: BusinessStore, token: str, shop: UUID) -> dto.Page[dto.Product]:
    return cast(
        dto.Page[dto.Product],
        store.read(token, 0, 0, dto.ProductQuery(shop_id=shop), "products")["data"],
    )


def populate(demo: DemoPG, store: BusinessStore) -> Subject:
    """Real normal source graph: one tag, fulfillment, confirmed import and stopped parser."""
    _, token = enter(demo)
    current = demo.store.sessions.current(token)
    csrf = current["data"]["csrf_token"]
    shop = UUID(next(s for s in current["data"]["shops"] if s["currency"] == "TWD")["shop_id"])
    page = products(store, token, shop)
    store.action(
        token,
        csrf,
        dto.SetProductTags(
            shop_id=shop,
            request_key=uuid4(),
            expected_epoch=0,
            expected_generation=0,
            expected_data_revision=page.snapshot.data_revision,
            expected_version=0,
            tags=("gc",),
        ),
        "product_tags",
        page.items[0].product_id,
    )
    orders = cast(
        dto.Page[dto.Order],
        store.read(token, 0, 0, dto.OrderQuery(shop_id=shop, days=14), "orders")["data"],
    )
    paid = next(order for order in orders.items if order.paid_at is not None)
    store.action(
        token,
        csrf,
        dto.FulfillDemoOrder(
            shop_id=shop,
            request_key=uuid4(),
            expected_epoch=0,
            expected_generation=0,
            expected_data_revision=orders.snapshot.data_revision,
            expected_version=0,
            action="mark_demo_fulfilled",
        ),
        "order_fulfillment",
        paid.order_id,
    )
    page = products(store, token, shop)
    raw = b"sku,title,price,currency,tags\nGC-ONLY,Synthetic,0.10,TWD,gc\n"
    preview = cast(
        dto.ImportPreviewData,
        store.preview(
            token,
            csrf,
            dto.ImportPreviewInput(
                shop_id=shop,
                request_key=uuid4(),
                expected_epoch=0,
                expected_generation=0,
                expected_data_revision=page.snapshot.data_revision,
                format="csv",
                filename="gc.csv",
                file_base64=base64.b64encode(raw).decode(),
                mapping=dto.ColumnMapping(
                    sku="sku", title="title", price="price", currency="currency", tags="tags"
                ),
            ),
        )["data"],
    )
    assert preview.state == "READY" and preview.confirmable
    store.action(
        token,
        csrf,
        dto.ConfirmImport(
            shop_id=shop,
            request_key=uuid4(),
            expected_epoch=0,
            expected_generation=0,
            expected_data_revision=page.snapshot.data_revision,
            expected_job_version=preview.job.version,
            expected_job_digest=preview.job.job_digest,
        ),
        "import_confirm",
        preview.job.import_job_id,
    )
    with connect(demo.owner) as db:
        bounded(db)
        row = db.execute(
            "SELECT * FROM business.v4_demo_sessions WHERE token_hash=%s", (sha(token),)
        ).fetchone()
        assert row is not None
        return Subject(
            UUID(current["context"]["tenant_id"]),
            UUID(current["context"]["organization_id"]),
            row["id"],
            row["bootstrap_id"],
            shop,
            token,
            hashlib.sha256(raw).hexdigest(),
        )


def graph(db: DB, subject: Subject) -> Graph:
    result: Graph = {}
    for table in (*CORE, *("v4_demo_" + name for name in V4), *("v41_" + name for name in TABLES)):
        column, value = "tenant_id", subject.tenant
        if table in CORE:
            column, value = (
                ("id" if table == "organizations" else "organization_id"),
                subject.organization,
            )
        elif table == "v4_demo_tenants":
            column = "id"
        elif table == "v4_demo_bootstraps":
            column, value = "id", subject.bootstrap
        result[table] = db.execute(
            sql.SQL("SELECT * FROM {} WHERE {}=%s ORDER BY to_jsonb({})::text").format(
                sql.Identifier("business", table), sql.Identifier(column), sql.Identifier(table)
            ),
            (value,),
        ).fetchall()
    return result


def fingerprints(db: DB) -> dict[str, str]:
    """Opaque whole-schema row fingerprints; never return policy capability or credentials."""
    tables = db.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='business' AND c.relkind='r' ORDER BY c.relname"
    ).fetchall()
    result: dict[str, str] = {}
    for row in tables:
        found = db.execute(
            sql.SQL(
                "SELECT encode(sha256(convert_to(coalesce(jsonb_agg(v "
                "ORDER BY v::text),'[]'::jsonb)::text,'UTF8')),'hex') AS digest FROM "
                "(SELECT to_jsonb(t) AS v FROM {} t) rows"
            ).format(sql.Identifier("business", row["relname"]))
        ).fetchone()
        assert found is not None
        result[row["relname"]] = found["digest"]
    return result


def catalog(db: DB) -> list[Row]:
    """Full trigger/FK/function and ACL definitions, including internal FK trigger modes."""
    return db.execute("""SELECT 'trigger' kind,t.oid::text id,
        jsonb_build_object('definition',pg_get_triggerdef(t.oid),'mode',t.tgenabled,
        'internal',t.tgisinternal) value FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='business'
        UNION ALL SELECT 'function',p.oid::text,jsonb_build_object('definition',
        pg_get_functiondef(p.oid),'acl',p.proacl,'owner',p.proowner,'config',p.proconfig,
        'definer',p.prosecdef) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='business' AND p.prokind='f'
        UNION ALL SELECT 'relation',c.oid::text,
        jsonb_build_object('owner',c.relowner,'acl',c.relacl)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='business'
        UNION ALL SELECT 'column',a.attrelid::text||':'||a.attnum::text,
        jsonb_build_object('acl',a.attacl,'notnull',a.attnotnull,'type',a.atttypid)
        FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n
        ON n.oid=c.relnamespace WHERE n.nspname='business' AND a.attnum>0 AND NOT a.attisdropped
        UNION ALL SELECT 'constraint',c.oid::text,jsonb_build_object('definition',
        pg_get_constraintdef(c.oid),'validated',c.convalidated) FROM pg_constraint c
        JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='business'
        UNION ALL SELECT 'index',i.indexrelid::text,jsonb_build_object('definition',
        pg_get_indexdef(i.indexrelid),'ready',i.indisready,'valid',i.indisvalid)
        FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n
        ON n.oid=c.relnamespace WHERE n.nspname='business' ORDER BY kind,id""").fetchall()


def constraints(db: DB) -> None:
    """Recheck actual rows, not convalidated: full ordered composite FKs and CHECKs."""
    foreign = db.execute("""SELECT c.conname,ns.nspname AS schema,rel.relname AS table,
        nt.nspname AS target_schema,ref.relname AS target,c.confmatchtype,
        array_agg(a.attname ORDER BY keys.n) AS columns,
        array_agg(b.attname ORDER BY keys.n) AS targets FROM pg_constraint c
        JOIN pg_class rel ON rel.oid=c.conrelid JOIN pg_namespace ns ON ns.oid=rel.relnamespace
        JOIN pg_class ref ON ref.oid=c.confrelid JOIN pg_namespace nt ON nt.oid=ref.relnamespace
        CROSS JOIN LATERAL unnest(c.conkey,c.confkey) WITH ORDINALITY keys(src,dst,n)
        JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=keys.src
        JOIN pg_attribute b ON b.attrelid=c.confrelid AND b.attnum=keys.dst
        WHERE c.contype='f' AND ns.nspname='business'
        GROUP BY c.oid,c.conname,c.confmatchtype,ns.nspname,rel.relname,nt.nspname,ref.relname
        ORDER BY c.oid""").fetchall()
    assert foreign
    for item in foreign:
        assert item["confmatchtype"] in ("s", "f")
        columns = [sql.Identifier("src", key) for key in item["columns"]]
        nonnull = sql.SQL(" AND ").join(sql.SQL("{} IS NOT NULL").format(key) for key in columns)
        match = sql.SQL(" AND ").join(
            sql.SQL("{}={}").format(a, sql.Identifier("dst", b))
            for a, b in zip(columns, item["targets"], strict=True)
        )
        bad = db.execute(
            sql.SQL(
                "SELECT count(*) n FROM {} src WHERE ({}) AND NOT EXISTS "
                "(SELECT 1 FROM {} dst WHERE {})"
            ).format(
                sql.Identifier(item["schema"], item["table"]),
                nonnull,
                sql.Identifier(item["target_schema"], item["target"]),
                match,
            )
        ).fetchone()
        assert bad == dict(n=0), item["conname"]
        if item["confmatchtype"] == "f":
            any_null = sql.SQL(" OR ").join(sql.SQL("{} IS NULL").format(key) for key in columns)
            any_nonnull = sql.SQL(" OR ").join(
                sql.SQL("{} IS NOT NULL").format(key) for key in columns
            )
            assert db.execute(
                sql.SQL("SELECT count(*) n FROM {} src WHERE ({}) AND ({})").format(
                    sql.Identifier(item["schema"], item["table"]), any_null, any_nonnull
                )
            ).fetchone() == dict(n=0), item["conname"]
    checks = db.execute("""SELECT r.relname,c.conname,pg_get_expr(c.conbin,c.conrelid) expression
        FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n
        ON n.oid=r.relnamespace WHERE n.nspname='business' AND c.contype='c'""").fetchall()
    for item in checks:
        assert db.execute(
            sql.SQL("SELECT count(*) n FROM {} WHERE ({}) IS FALSE").format(
                sql.Identifier("business", item["relname"]), sql.SQL(item["expression"])
            )
        ).fetchone() == dict(n=0), item["conname"]
    required = db.execute("""SELECT c.relname,a.attname FROM pg_attribute a JOIN pg_class c
        ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='business' AND c.relkind='r' AND a.attnum>0
        AND NOT a.attisdropped AND a.attnotnull""").fetchall()
    for item in required:
        assert db.execute(
            sql.SQL("SELECT count(*) n FROM {} WHERE {} IS NULL").format(
                sql.Identifier("business", item["relname"]), sql.Identifier(item["attname"])
            )
        ).fetchone() == dict(n=0)
    indexes = db.execute("""SELECT c.relname,i.indisvalid,i.indisready,
        coalesce(pg_get_expr(i.indpred,i.indrelid),'true') predicate,
        ARRAY(SELECT pg_get_indexdef(i.indexrelid,n,true)
          FROM generate_series(1,i.indnkeyatts) n) expressions
        FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='business' AND i.indisunique""").fetchall()
    for item in indexes:
        assert item["indisvalid"] and item["indisready"]
        # Normal UNIQUE treats any NULL key as distinct. This still checks every
        # non-NULL key, including the two partial parse-slot indexes and composites.
        expressions = [sql.SQL(part) for part in item["expressions"]]
        nonnull = sql.SQL(" AND ").join(
            sql.SQL("({}) IS NOT NULL").format(part) for part in expressions
        )
        assert db.execute(
            sql.SQL(
                "SELECT count(*) n FROM (SELECT 1 FROM {} "
                "WHERE ({}) AND ({}) GROUP BY {} HAVING count(*)>1) duplicate_keys"
            ).format(
                sql.Identifier("business", item["relname"]),
                sql.SQL(item["predicate"]),
                nonnull,
                sql.SQL(",").join(expressions),
            )
        ).fetchone() == dict(n=0), item["relname"]


def preview_digest(job: Row, session_expiry: datetime) -> str:
    data = copy.deepcopy(job["preview_data"])
    del data["job"]["job_digest"]
    scope = {
        key: job[key]
        for key in (
            "tenant_id",
            "shop_id",
            "owner_session_id",
            "principal_id",
            "reset_epoch",
            "auth_generation",
            "data_revision",
        )
    }
    scope = {key: str(value) if isinstance(value, UUID) else value for key, value in scope.items()}
    scope["session_expires_at"] = utc(session_expiry)
    return sha(
        text(
            dict(
                scope=scope,
                data=data,
                normalized_digest=job["normalized_digest"],
                request_digest=job["request_digest"],
                mapping_digest=job["mapping_digest"],
            )
        )
    )


def historical(source: Graph) -> Graph:
    """Exact in-memory manifest: times only, plus dependent preview/request digests."""
    result = copy.deepcopy(source)
    for rows in result.values():
        for row in rows:
            for key, value in row.items():
                if isinstance(value, datetime):
                    row[key] = value - SHIFT
    session = result["v4_demo_sessions"][0]
    for job in result["v41_import_jobs"]:
        job["preview_data"]["job"]["expires_at"] = utc(job["expires_at"])
        job["job_digest"] = preview_digest(job, session["expires_at"])
        job["preview_data"]["job"]["job_digest"] = job["job_digest"]
        job["canonical_preview"] = text(job["preview_data"])
        for receipt in result["v41_action_receipts"]:
            if receipt["operation"] == "import_confirm" and receipt["resource_id"] == job["id"]:
                request = json.loads(receipt["canonical_request"])
                request["body"]["expected_job_digest"] = job["job_digest"]
                receipt["canonical_request"] = text(request)
                receipt["payload_digest"] = sha(receipt["canonical_request"])
    return result


def unknown_job(source: Row) -> Row:
    """A separate historical unconfirmed reservation, never an edited confirmed job."""
    row = copy.deepcopy(source)
    row.update(
        id=uuid4(),
        preview_key=uuid4(),
        process_ref=uuid4(),
        parse_state="UNKNOWN",
        parse_slot=0,
        parse_pid=None,
        stop_proof=None,
        requested_parent_job_id=None,
        parent_job_id=None,
        chain_version=1,
        lease_digest=sha(str(uuid4())),
    )
    for key in (
        "preview_data",
        "canonical_preview",
        "normalized_rows",
        "canonical_normalized",
        "normalized_digest",
        "mapping_digest",
        "job_digest",
    ):
        row[key] = None
    request = json.loads(row["canonical_preview_request"])
    request["command"]["request_key"] = str(row["preview_key"])
    request["command"]["parent_job_id"] = None
    row["canonical_preview_request"] = text(request)
    row["request_digest"] = sha(row["canonical_preview_request"])
    return row


def _same_graph(actual: Graph, expected: Graph) -> None:
    # Hash only in assertions: raw graphs carry synthetic credential/binding material.
    def fingerprint(value: Graph) -> str:
        normalized = {
            key: sorted(json.dumps(row, default=str, sort_keys=True) for row in rows)
            for key, rows in value.items()
        }
        return sha(json.dumps(normalized, sort_keys=True))

    assert fingerprint(actual) == fingerprint(expected)


def restore(demo: DemoPG, target: Subject, *, unknown: bool) -> None:
    """Single dedicated initialization transaction; no runtime connection inherits replica."""
    assert re.fullmatch(r"v4_demo_[a-f0-9]{32}", demo.owner.name)
    with connect(demo.owner) as db:
        bounded(db)
        require_owner(db)
        assert db.execute("SELECT version_num FROM business.alembic_version").fetchone() == dict(
            version_num="0025_v41_catalog_operations"
        )
        assert db.execute("SHOW session_replication_role").fetchone() == dict(
            session_replication_role="origin"
        )
        before_catalog = catalog(db)
        assert all(
            row["value"]["mode"] == "O" for row in before_catalog if row["kind"] == "trigger"
        )
        source = graph(db, target)
        for table in (*source, "v41_security_policy"):
            assert db.execute(
                "SELECT current_user=pg_get_userbyid(relowner) allowed "
                "FROM pg_class WHERE oid=to_regclass(%s)",
                ("business." + table,),
            ).fetchone() == dict(allowed=True)
        validate(db, source, target, expired=False)
        expected = historical(source)
        db.execute("SET LOCAL session_replication_role=replica")
        for table, rows in source.items():
            for old, new in zip(rows, expected[table], strict=True):
                changes = [key for key in old if old[key] != new[key]]
                if not changes:
                    continue
                # The initialized graph uses only these immutable primary keys.
                key = "login" if table == "web_credentials" else "id"
                assert key in old, table
                values = [
                    Jsonb(new[name]) if isinstance(new[name], dict) else new[name]
                    for name in changes
                ]
                assignments = sql.SQL(",").join(
                    sql.SQL("{}=%s").format(sql.Identifier(name)) for name in changes
                )
                changed = db.execute(
                    sql.SQL("UPDATE {} SET {} WHERE {}=%s").format(
                        sql.Identifier("business", table), assignments, sql.Identifier(key)
                    ),
                    (*values, old[key]),
                ).rowcount
                assert changed == 1
        if unknown:
            row = unknown_job(expected["v41_import_jobs"][0])
            expected["v41_import_jobs"].append(row)
            db.execute(
                sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier("business", "v41_import_jobs"),
                    sql.SQL(",").join(map(sql.Identifier, row)),
                    sql.SQL(",").join(sql.Placeholder() for _ in row),
                ),
                tuple(
                    Jsonb(value) if isinstance(value, (dict, list)) else value
                    for value in row.values()
                ),
            )
        db.execute("SET LOCAL session_replication_role=origin")
        _same_graph(graph(db, target), expected)
        constraints(db)
        validate(db, expected, target, expired=True)
        assert catalog(db) == before_catalog
    # Context exit above is actual restore COMMIT; all subsequent connections are new.
    with connect(demo.owner) as verify:
        bounded(verify)
        assert verify.execute("SHOW session_replication_role").fetchone() == dict(
            session_replication_role="origin"
        )
        assert catalog(verify) == before_catalog
        _same_graph(graph(verify, target), expected)
        constraints(verify)
        validate(verify, graph(verify, target), target, expired=True)


def validate(db: DB, value: Graph, subject: Subject, *, expired: bool) -> None:
    """Historical relationships and digests, independent of time-sensitive commit triggers."""
    tenant, session = value["v4_demo_tenants"][0], value["v4_demo_sessions"][0]
    bootstrap, bound = value["v4_demo_bootstraps"][0], value["web_sessions"][0]
    assert tenant["id"] == session["tenant_id"] == subject.tenant
    assert tenant["expires_at"] == session["expires_at"]
    assert tenant["created_at"] == session["created_at"]
    assert tenant["expires_at"] - tenant["created_at"] == timedelta(minutes=30)
    assert tenant["retain_until"] - tenant["expires_at"] == timedelta(hours=24)
    assert bootstrap["expires_at"] - bootstrap["created_at"] == timedelta(seconds=300)
    assert bootstrap["created_at"] <= bootstrap["consumed_at"] < bootstrap["expires_at"]
    assert bootstrap["consumed_at"] == session["created_at"]
    assert session["bound_web_session_id"] == bound["id"]
    assert (
        tenant["created_at"]
        <= bound["created_at"]
        < bound["absolute_expires_at"]
        <= tenant["expires_at"]
    )
    assert (
        bound["created_at"]
        <= bound["last_seen_at"]
        <= bound["idle_expires_at"]
        <= tenant["expires_at"]
    )
    assert (bound["principal_id"], bound["identity_id"], bound["auth_version"]) == (
        session["principal_id"],
        session["identity_id"],
        session["auth_version"],
    )
    assert {row["persona_id"] for row in value["v4_demo_personas"]} == {
        "operator",
        "approver",
        "restricted_admin",
    }
    assert len(value["v4_demo_shops"]) == 2
    assert {row["currency"] for row in value["shops"]} == {"TWD", "CNY"}
    assert all(row["adapter_kind"] == row["environment"] == "mock" for row in value["shops"])
    assert value["organizations"][0]["name"] == "V4 synthetic demo " + str(subject.tenant)
    assert tenant["organization_id"] == bound["organization_id"] == subject.organization
    assert bootstrap["id"] == session["bootstrap_id"] == subject.bootstrap
    assert bootstrap["create_request_key"] == session["creation_request_key"]
    fixture = db.execute(
        "SELECT canonical_content,content_hash FROM "
        "business.v4_demo_fixture_versions WHERE version=%s",
        (tenant["fixture_version"],),
    ).fetchone()
    assert fixture is not None
    assert sha(fixture["canonical_content"]) == fixture["content_hash"] == tenant["fixture_digest"]
    assert text(json.loads(fixture["canonical_content"])) == fixture["canonical_content"]
    principals = {row["id"]: row for row in value["principals"]}
    identities = {row["id"]: row for row in value["identities"]}
    for persona in value["v4_demo_personas"]:
        principal = principals[persona["principal_id"]]
        identity = identities[persona["identity_id"]]
        assert principal["enabled"] and principal["organization_id"] == subject.organization
        assert identity["principal_id"] == principal["id"] and identity["provider"] == "web"
        credential = next(
            row for row in value["web_credentials"] if row["identity_id"] == identity["id"]
        )
        assert credential["enabled"] and credential["principal_id"] == principal["id"]
    for mapping in value["v4_demo_shops"]:
        shop = next(row for row in value["shops"] if row["id"] == mapping["shop_id"])
        assert shop["external_shop_key"] == mapping["template_key"]
        assert (shop["currency"], shop["timezone"]) == (
            ("TWD", "Asia/Taipei")
            if mapping["template_key"] == "v4-shop-a"
            else ("CNY", "Asia/Shanghai")
        )
    for suffix in TABLES:
        assert value["v41_" + suffix], suffix
    now = db.execute("SELECT clock_timestamp() AS stamp").fetchone()
    assert now is not None
    assert (now["stamp"] >= tenant["retain_until"]) is expired
    receipts = {row["id"]: row for row in value["v41_action_receipts"]}
    assert {row["operation"] for row in receipts.values()} == {
        "product_tags",
        "order_fulfillment",
        "import_confirm",
    }
    for table, rows in value.items():
        for row in rows:
            for canonical, digest in (
                ("canonical_request", "payload_digest"),
                ("canonical_payload", "payload_digest"),
                ("canonical_preview_request", "request_digest"),
            ):
                if canonical in row:
                    assert text(json.loads(row[canonical])) == row[canonical], table
                    assert sha(row[canonical]) == row[digest], table
            if table in ("v4_demo_receipts", "v41_action_receipts"):
                assert tenant["created_at"] <= row["committed_at"] < tenant["expires_at"]
                assert row["retain_until"] == tenant["retain_until"]
    v4_receipt = value["v4_demo_receipts"][0]
    assert v4_receipt["id"] == session["last_receipt_id"]
    assert v4_receipt["operation"] == "session_create"
    assert {row["event_kind"] for row in value["v4_demo_events"]} == {
        "demo.session_created",
        "demo.seed_materialized",
    }
    for event in value["v4_demo_events"]:
        assert event["receipt_id"] == v4_receipt["id"]
        assert event["created_at"] >= v4_receipt["committed_at"]
    for job in value["v41_import_jobs"]:
        assert tenant["created_at"] <= job["created_at"] < job["expires_at"] <= tenant["expires_at"]
        assert job["expires_at"] <= job["created_at"] + timedelta(minutes=10)
        assert job["retain_until"] == tenant["retain_until"]
        assert job["file_digest"] == subject.file_digest
        request = json.loads(job["canonical_preview_request"])
        assert request["file_digest"] == job["file_digest"]
        assert request["command"]["request_key"] == str(job["preview_key"])
        if job["parse_state"] == "UNKNOWN":
            assert (
                job["preview_data"] is None and job["stop_proof"] is None and job["parse_slot"] == 0
            )
            continue
        assert job["parse_state"] == "STOPPED" and job["parse_slot"] is None
        assert job["stop_proof"]["reaped"] is True and job["stop_proof"]["native_exit"] == 0
        assert job["stop_proof"]["pid"] == job["parse_pid"]
        data = job["preview_data"]
        assert text(data) == job["canonical_preview"]
        assert text(job["normalized_rows"]) == job["canonical_normalized"]
        assert job["normalized_digest"] == sha(
            text(
                dict(
                    rows=job["normalized_rows"],
                    parser_version=job["parser_version"],
                    import_schema_version=job["import_schema_version"],
                )
            )
        )
        assert job["mapping_digest"] == sha(text(dict(mapping=data["mapping"], mapping_version=1)))
        assert (
            job["job_digest"]
            == data["job"]["job_digest"]
            == preview_digest(job, session["expires_at"])
        )
        assert data["job"]["expires_at"] == utc(job["expires_at"])
        native = dict(
            schema_version="v41-parser-result-1",
            file_digest=job["file_digest"],
            **{
                key: data[key]
                for key in ("headers", "row_count", "state", "sample", "issues", "issue_count")
            },
            products=job["normalized_rows"],
        )
        assert sha(text(native)) == job["stop_proof"]["output_digest"]
        imported = next(row for row in value["v41_import_products"] if row["job_id"] == job["id"])
        assert imported["content"] == job["normalized_rows"][imported["import_row"] - 2]
        receipt = receipts[imported["receipt_id"]]
        assert (
            json.loads(receipt["canonical_request"])["body"]["expected_job_digest"]
            == job["job_digest"]
        )
        # Independent Python computation above must agree with the unchanged SQL helper too.
        assert db.execute(
            "SELECT business.v41_preview_digest(j) digest "
            "FROM business.v41_import_jobs j WHERE id=%s",
            (job["id"],),
        ).fetchone() == dict(digest=job["job_digest"])
    for suffix, operation, resource in (
        ("product_tags", "product_tags", "product_id"),
        ("order_fulfillments", "order_fulfillment", "order_id"),
        ("import_products", "import_confirm", "job_id"),
    ):
        for effect in value["v41_" + suffix]:
            receipt = receipts[effect["receipt_id"]]
            request = json.loads(receipt["canonical_request"])["body"]
            assert receipt["operation"] == operation and receipt["resource_id"] == effect[resource]
            for key in (
                "tenant_id",
                "organization_id",
                "shop_id",
                "owner_session_id",
                "principal_id",
                "reset_epoch",
                "auth_generation",
            ):
                assert effect[key] == receipt[key]
            assert request["expected_data_revision"] == receipt["before_revision"]
            scope = dict(
                tenant_id=str(subject.tenant),
                shop_id=str(effect["shop_id"]),
                reset_epoch=0,
                template_key="v4-shop-a",
            )
            if suffix == "product_tags":
                payload = dict(
                    scope=scope,
                    product_id=str(effect["product_id"]),
                    version=effect["version"],
                    tags=effect["tags"],
                )
                assert request["tags"] == effect["tags"]
            elif suffix == "order_fulfillments":
                payload = dict(
                    scope=scope,
                    order_id=str(effect["order_id"]),
                    version=effect["version"],
                    status=effect["status"],
                )
            else:
                job = next(row for row in value["v41_import_jobs"] if row["id"] == effect["job_id"])
                payload = dict(
                    scope=scope,
                    product_id=str(effect["product_id"]),
                    sku_id=str(effect["sku_id"]),
                    import_job_id=str(effect["job_id"]),
                    import_row=effect["import_row"],
                    file_digest=job["file_digest"],
                    product=effect["content"],
                )
            assert text(payload) == effect["canonical_payload"]
    for event in value["v41_action_events"]:
        receipt = receipts[event["receipt_id"]]
        assert (
            event["event_kind"],
            event["resource_id"],
            event["resource_version"],
            event["effect_count"],
        ) == (
            receipt["operation"],
            receipt["resource_id"],
            receipt["resource_version"],
            receipt["effect_count"],
        )
        assert event["created_at"] >= receipt["committed_at"]
        effects = [
            dict(
                kind=kind,
                object_id=str(row["product_id" if suffix != "order_fulfillments" else "order_id"]),
                payload_digest=row["payload_digest"],
            )
            for suffix, kind in (
                ("product_tags", "product_tags"),
                ("order_fulfillments", "order_fulfillment"),
                ("import_products", "import_confirm"),
            )
            for row in value["v41_" + suffix]
            if row["receipt_id"] == receipt["id"]
        ]
        effects.sort(key=lambda row: (row["kind"], row["object_id"]))
        assert len(effects) == event["effect_count"]
        assert sha(text(effects)) == event["effect_digest"]
        summary = db.execute(
            "SELECT business.v41_effect_summary(%s) value", (receipt["id"],)
        ).fetchone()
        assert summary == dict(
            value=dict(count=event["effect_count"], digest=event["effect_digest"])
        )
