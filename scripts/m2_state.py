"""M2 owned fixture/config and read-only business receipts; never used against existing assets.

Each call runs in the scenario parent's bounded subprocess; no resource owner lives here.
"""

import hashlib
import json
import os
import secrets
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from commerceops.application.commerce.source_binding import WooSourceMetadata
from commerceops.application.replenishment.security import digest, password_hash
from commerceops.entrypoints.commerce_source import register_owned_source
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.web_config import WebConfig, private_bytes
from psycopg import Connection

from scripts.m2_backup import REVISION, BackupFailure


def save(path: Path, value: Any) -> None:
    raw = (
        value
        if isinstance(value, bytes)
        else (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def seed(owner: DatabaseSettings, directory: Path, run_id: str) -> dict[str, Any]:
    """Fresh source only: two distinct Web principals, one Woo shop, zero business tasks."""
    with connect(owner) as db:
        if db.execute("SELECT version_num FROM business.alembic_version").fetchone() != {
            "version_num": REVISION
        }:
            raise BackupFailure("M2_SEED_REVISION")
        if db.execute("SELECT count(*) AS n FROM business.organizations").fetchone() != {"n": 0}:
            raise BackupFailure("M2_SEED_NOT_EMPTY")
        allocated = db.execute(
            "SELECT gen_random_uuid() AS organization,gen_random_uuid() AS shop"
        ).fetchone()
        if allocated is None:
            raise BackupFailure("M2_SEED_IDENTITY_ALLOCATION")
        organization, shop = allocated["organization"], allocated["shop"]
        app, tenant = str(uuid4()), str(uuid4())
        config_ref = "m2-" + run_id
        db.execute(
            "INSERT INTO business.organizations(id,name,feishu_app_id,feishu_tenant_key) "
            "VALUES (%s,%s,%s,%s)",
            (organization, "M2 owned synthetic source", app, tenant),
        )
        db.execute(
            "INSERT INTO business.shops(id,organization_id,adapter_kind,external_shop_key,"
            "timezone,currency,config_ref,environment) "
            "VALUES (%s,%s,'woocommerce_test',%s,'Asia/Shanghai','CNY',%s,'test')",
            (shop, organization, str(shop), config_ref),
        )
        accounts = {}
        for role in ("operator", "approver"):
            principal, identity = uuid4(), uuid4()
            login, password = "m2-" + uuid4().hex[:16], secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO business.principals(id,organization_id,display_name,roles) "
                "VALUES (%s,%s,%s,%s)",
                (principal, organization, "M2 owned " + role, [role]),
            )
            db.execute(
                "INSERT INTO business.identities(id,organization_id,principal_id,provider,"
                "app_id,tenant_key,external_subject) "
                "VALUES (%s,%s,%s,'web',%s,%s,%s)",
                (identity, organization, principal, app, tenant, login),
            )
            db.execute(
                "INSERT INTO business.web_credentials VALUES (%s,%s,%s,%s,%s,true)",
                (login, organization, principal, identity, password_hash(password)),
            )
            db.execute(
                "INSERT INTO business.principal_shop_scopes VALUES (%s,%s,%s,true)",
                (organization, shop, principal),
            )
            db.execute(
                "INSERT INTO business.principal_role_shop_grants VALUES (%s,%s,%s,%s,true)",
                (organization, shop, principal, role),
            )
            accounts[role] = dict(
                login=login,
                password=password,
                expected_principal_id=str(principal),
                expected_organization_id=str(organization),
                expected_shop_id=str(shop),
                expected_role=role,
            )
    result = dict(
        organization_id=str(organization),
        shop_id=str(shop),
        config_ref=config_ref,
        accounts=accounts,
    )
    save(directory / "seed.private.json", result)
    for name in ("csrf-material", "nonce-material"):
        save(directory / name, secrets.token_bytes(32))
    return result


def bind_source(owner: DatabaseSettings, directory: Path, lab: Path, anchor: str) -> dict[str, Any]:
    seed_data = json.loads(private_bytes(directory / "seed.private.json"))
    probe = json.loads(private_bytes(lab / "probe-config.private.json"))
    if probe["shop_id"] != seed_data["shop_id"]:
        raise BackupFailure("M2_LAB_SHOP_BINDING")
    metadata = WooSourceMetadata(
        organization_id=UUID(seed_data["organization_id"]),
        shop_id=UUID(seed_data["shop_id"]),
        config_ref=seed_data["config_ref"],
        source_config_version=seed_data["config_ref"] + "-v1",
        origin=probe["base_url"],
        external_shop_key=probe["shop_id"],
        currency=probe["currency"],
        timezone=probe["timezone"],
        profile="positive-v1",
        anchor_day=date.fromisoformat(anchor),
        consumer_key_file=probe["consumer_key_file"],
        consumer_secret_file=probe["consumer_secret_file"],
        ca_file=probe["ca_file"],
        private_pin_ref="m2-source-pin",
    )
    expected = json.loads(private_bytes(lab / "expected.private.json"))
    if metadata.window.model_dump(mode="json") != expected["window"]:
        # Compare actual instants below: equivalent UTC formatting may differ.
        from commerceops.application.commerce.contracts import Window

        if metadata.window != Window.model_validate(expected["window"]):
            raise BackupFailure("M2_LAB_WINDOW_BINDING")
    identifier = uuid4()
    register_owned_source(owner, identifier, metadata)
    sources = directory / "sources"
    sources.mkdir(mode=0o700)
    save(sources / f"{identifier}.json", metadata.model_dump(mode="json"))
    pins = dict(
        schema_version="p5-private-pins-v1",
        binding_id=str(identifier),
        config_digest=metadata.config_digest,
    )
    for label, path in (
        ("key", metadata.consumer_key_file),
        ("secret", metadata.consumer_secret_file),
        ("ca", metadata.ca_file),
    ):
        pins[label] = hashlib.sha256(private_bytes(Path(path))).hexdigest()
    pin_path = sources / "m2-source-pin.pins.json"
    save(pin_path, pins)
    source_config = dict(
        directory=str(sources),
        bindings=[
            dict(
                organization_id=seed_data["organization_id"],
                shop_id=seed_data["shop_id"],
                binding_id=str(identifier),
            )
        ],
        private_pin_digests={"m2-source-pin": hashlib.sha256(private_bytes(pin_path)).hexdigest()},
    )
    result = dict(
        binding_id=str(identifier),
        registration_digest=metadata.config_digest,
        source_config_version=metadata.source_config_version,
        source_config=source_config,
        metadata=metadata.model_dump(mode="json"),
    )
    save(directory / "binding.private.json", result)
    return result


def web_configuration(
    directory: Path, database: DatabaseSettings, web_origin: str
) -> dict[str, Any]:
    binding = json.loads(private_bytes(directory / "binding.private.json"))
    return dict(
        database=database.model_dump(mode="json"),
        csrf_secret_file=str(directory / "csrf-material"),
        nonce_secret_file=str(directory / "nonce-material"),
        origins=[web_origin],
        transport_mode="local_http",
        approval_ttl_seconds=900,
        commerce_sources=binding["source_config"],
    )


def pending_receipt(
    db: Connection[dict[str, Any]],
    observed: dict[str, Any],
    approval_read: dict[str, Any],
    golden: dict[str, Any],
    seed_data: dict[str, Any],
    binding: dict[str, Any],
) -> dict[str, Any]:
    """Canonicalize only after the source consumer exits and actual PG matches its receipt."""
    db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    db.execute("SET LOCAL statement_timeout=5000")
    row = db.execute(
        "SELECT t.id AS task_id,t.organization_id,t.shop_id,t.state,t.thread_id,t.requester_id,"
        "p.source_task_id,"
        "p.id AS plan_id,p.version AS plan_version,p.plan_hash,p.report_id,p.snapshot_id,"
        "p.facts_hash,p.content,"
        "a.id AS approval_id,a.status,a.expires_at,a.ready_at,a.nonce_hash,"
        "a.eligible_principal_ids,"
        "s.parameters FROM business.business_tasks t "
        "JOIN business.p3_task_sources s ON s.task_id=t.id "
        "JOIN business.replenishment_plans p ON p.task_id=t.id AND p.version=1 "
        "JOIN business.approvals a ON a.plan_id=p.id WHERE t.id=%s",
        (UUID(observed["task_id"]),),
    ).fetchone()
    if (
        row is None
        or row["state"] != "awaiting_approval"
        or row["status"] != "pending"
        or not row["ready_at"]
    ):
        raise BackupFailure("M2_SOURCE_NOT_PENDING")
    for key in (
        "task_id",
        "organization_id",
        "shop_id",
        "source_task_id",
        "plan_id",
        "report_id",
        "snapshot_id",
        "approval_id",
    ):
        if str(row[key]) != observed[key]:
            raise BackupFailure("M2_OBSERVED_PG_BINDING")
    if (
        any(str(row[key]) != observed[key] for key in ("facts_hash", "plan_hash"))
        or row["plan_version"] != observed["plan_version"]
    ):
        raise BackupFailure("M2_OBSERVED_PG_BINDING")
    if (
        str(row["organization_id"]) != seed_data["organization_id"]
        or str(row["shop_id"]) != seed_data["shop_id"]
    ):
        raise BackupFailure("M2_SOURCE_SCOPE")
    if (
        str(row["parameters"].get("source_binding_id")) != binding["binding_id"]
        or row["parameters"].get("source_config_version") != binding["source_config_version"]
    ):
        raise BackupFailure("M2_SOURCE_BINDING")
    from datetime import datetime

    if row["expires_at"] != datetime.fromisoformat(observed["expires_at"]):
        raise BackupFailure("M2_ORIGINAL_EXPIRY")
    if digest(approval_read["nonce"]) != row["nonce_hash"]:
        raise BackupFailure("M2_ORIGINAL_NONCE")
    operator = UUID(seed_data["accounts"]["operator"]["expected_principal_id"])
    if row["requester_id"] != operator:
        raise BackupFailure("M2_REQUESTER_BINDING")
    receipt = db.execute(
        "SELECT task_id,result FROM business.web_requests WHERE principal_id=%s "
        "AND operation='create_task' AND request_key=%s",
        (operator, UUID(observed["create_request_key"])),
    ).fetchone()
    if receipt is None or receipt["task_id"] != row["task_id"]:
        raise BackupFailure("M2_ORIGINAL_CREATE_RECEIPT")
    if receipt["result"].get("source_task_id") != str(row["source_task_id"]):
        raise BackupFailure("M2_ORIGINAL_CREATE_RECEIPT")
    money = db.execute(
        "SELECT count(*) AS lines,coalesce(sum(net_amount),0) AS amount,"
        "coalesce(sum(tax_amount),0) AS tax FROM business.snapshot_order_lines "
        "WHERE snapshot_id=%s",
        (row["snapshot_id"],),
    ).fetchone()
    refunds = db.execute(
        "SELECT count(*) AS n FROM business.snapshot_refunds WHERE snapshot_id=%s",
        (row["snapshot_id"],),
    ).fetchone()
    if money != {"lines": 4, "amount": 994, "tax": 0} or refunds != {"n": 0}:
        raise BackupFailure("M2_POSITIVE_ORDER_FACTS")
    approver = UUID(seed_data["accounts"]["approver"]["expected_principal_id"])
    if approver not in row["eligible_principal_ids"]:
        raise BackupFailure("M2_APPROVER_BINDING")
    for role in ("operator", "approver"):
        principal = UUID(seed_data["accounts"][role]["expected_principal_id"])
        if observed[role + "_principal_id"] != str(principal):
            raise BackupFailure("M2_CURRENT_ACTOR")
        allowed = db.execute(
            "SELECT count(*) AS n FROM business.principals p "
            "JOIN business.principal_shop_scopes s ON s.principal_id=p.id "
            "JOIN business.principal_role_shop_grants g ON g.principal_id=p.id "
            "AND g.organization_id=s.organization_id AND g.shop_id=s.shop_id "
            "JOIN business.web_credentials c ON c.principal_id=p.id "
            "JOIN business.identities i ON i.id=c.identity_id "
            "WHERE p.id=%s AND p.organization_id=%s AND s.shop_id=%s "
            "AND p.enabled AND s.enabled AND g.enabled AND c.enabled "
            "AND g.role=%s AND %s=ANY(p.roles) AND i.provider='web'",
            (principal, row["organization_id"], row["shop_id"], role, role),
        ).fetchone()
        if allowed != {"n": 1}:
            raise BackupFailure("M2_CURRENT_PERMISSION")
    if row["thread_id"] != str(row["task_id"]):
        raise BackupFailure("M2_PENDING_THREAD_BINDING")
    content = row["content"]
    assumptions = sorted(a["key"] for a in content["required_assumptions"])
    if assumptions != sorted(observed["required_assumption_keys"]) or len(assumptions) != 4:
        raise BackupFailure("M2_ASSUMPTIONS")
    wanted = {fact["sku_key"]: fact["suggested_units"] for fact in golden["facts"]}
    actual = {item["sku_key"]: item["quantity"] for item in content["items"]}
    if len(actual) != 4 or actual != wanted or sum(actual.values()) != 219:
        raise BackupFailure("M2_POSITIVE_PLAN")
    counts = db.execute(
        "SELECT count(*) AS n FROM business.executions WHERE task_id=%s", (row["task_id"],)
    ).fetchone()
    if counts != {"n": 0}:
        raise BackupFailure("M2_SOURCE_ALREADY_EXECUTED")
    cp = db.execute(
        "SELECT count(*) AS n FROM checkpoints.checkpoints WHERE thread_id=%s", (row["thread_id"],)
    ).fetchone()
    if not cp or cp["n"] == 0:
        raise BackupFailure("M2_PENDING_CHECKPOINT_MISSING")
    clock = db.execute("SELECT clock_timestamp() AS now").fetchone()
    if clock is None:
        raise BackupFailure("M2_DATABASE_CLOCK")
    return dict(
        schema_version="p5-m2-source-pg-v1",
        original_binding=True,
        pending=True,
        checkpoint_rows_present=True,
        item_count=4,
        total_quantity=219,
        assumption_count=4,
        execution_count=0,
        observed_at_utc=clock["now"].isoformat(),
    )


def completed_receipt(
    db: Connection[dict[str, Any]],
    observed: dict[str, Any],
    golden: dict[str, Any],
    seed_data: dict[str, Any],
) -> dict[str, Any]:
    db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    db.execute("SET LOCAL statement_timeout=5000")
    task = UUID(observed["task_id"])
    state = db.execute("SELECT state FROM business.business_tasks WHERE id=%s", (task,)).fetchone()
    executions = db.execute(
        "SELECT id,plan_id,approval_id,plan_version,plan_hash,status,item_ids "
        "FROM business.executions WHERE task_id=%s",
        (task,),
    ).fetchall()
    if state != {"state": "completed"} or len(executions) != 1:
        raise BackupFailure("M2_EXECUTION_CARDINALITY")
    execution = executions[0]
    if (
        execution["status"] != "completed"
        or str(execution["id"]) != observed["execution_id"]
        or str(execution["plan_id"]) != observed["plan_id"]
        or str(execution["approval_id"]) != observed["approval_id"]
        or execution["plan_version"] != observed["plan_version"]
        or execution["plan_hash"] != observed["plan_hash"]
    ):
        raise BackupFailure("M2_EXECUTION_BINDING")
    items = db.execute(
        "SELECT id,sku_key,stock_pool_key,quantity,status "
        "FROM business.replenishment_items WHERE task_id=%s",
        (task,),
    ).fetchall()
    expected = {f["sku_key"]: (f["stock_pool_key"], f["suggested_units"]) for f in golden["facts"]}
    actual = {i["sku_key"]: (i["stock_pool_key"], i["quantity"]) for i in items}
    if len(items) != 4 or actual != expected or any(i["status"] != "open" for i in items):
        raise BackupFailure("M2_EXECUTION_ITEMS")
    ids = {str(i["id"]) for i in items}
    if ids != set(observed["item_ids"]) or ids != {str(i) for i in execution["item_ids"]}:
        raise BackupFailure("M2_EXECUTION_ITEM_BINDING")
    receipt = db.execute(
        "SELECT task_id FROM business.web_requests WHERE principal_id=%s "
        "AND operation='decision' AND request_key=%s",
        (
            UUID(seed_data["accounts"]["approver"]["expected_principal_id"]),
            UUID(observed["decision_request_key"]),
        ),
    ).fetchall()
    if receipt != [{"task_id": task}]:
        raise BackupFailure("M2_ORIGINAL_DECISION_RECEIPT")
    counts = db.execute(
        "SELECT count(*) AS n FROM business.web_requests WHERE task_id=%s AND operation='decision'",
        (task,),
    ).fetchone()
    if counts != {"n": 1}:
        raise BackupFailure("M2_DUPLICATE_DECISION")
    resumes = db.execute(
        "SELECT r.approval_id,r.delivery_state FROM business.approval_resumes r "
        "JOIN business.approvals a ON a.id=r.approval_id AND a.decision_id=r.decision_id "
        "WHERE r.task_id=%s",
        (task,),
    ).fetchall()
    if resumes != [{"approval_id": execution["approval_id"], "delivery_state": "consumed"}]:
        raise BackupFailure("M2_RESUME_CARDINALITY")
    return dict(
        schema_version="p5-m2-completed-pg-v1",
        original_binding=True,
        task_completed=True,
        execution_count=1,
        item_count=4,
        total_quantity=219,
        decision_receipt_count=1,
        approval_resume_count=1,
        private_request_key_preserved=True,
    )


def validate_waiting_checkpoint(
    snapshot: Any, task: dict[str, Any], approval: dict[str, Any], observed: dict[str, Any]
) -> dict[str, Any]:
    """Validate the existing official graph contract without running a node or changing state."""
    from datetime import datetime

    from commerceops.infrastructure.approval_recovery import snapshot_binding
    from commerceops.infrastructure.inventory_repository import AnalysisUnsafe

    if (
        str(task["id"]) != observed["task_id"]
        or task["thread_id"] != observed["task_id"]
        or task["state"] != "awaiting_approval"
        or task["active_plan_id"] != approval["plan_id"]
        or str(approval["id"]) != observed["approval_id"]
        or str(approval["plan_id"]) != observed["plan_id"]
        or approval["task_id"] != task["id"]
        or approval["plan_version"] != observed["plan_version"]
        or approval["plan_hash"] != observed["plan_hash"]
        or approval["expires_at"] != datetime.fromisoformat(observed["expires_at"])
        or approval["status"] != "pending"
        or approval["decision_id"] is not None
        or approval["ready_at"] is None
    ):
        raise BackupFailure("M2_PENDING_CHECKPOINT_BUSINESS_BINDING")
    try:
        mode = snapshot_binding(snapshot, task, approval)
    except AnalysisUnsafe:
        raise BackupFailure("M2_PENDING_CHECKPOINT_SEMANTICS") from None
    if mode != "waiting" or snapshot.next != ("wait_approval",):
        raise BackupFailure("M2_PENDING_CHECKPOINT_SEMANTICS")
    from scripts.m2_backup import digest as safe_digest

    return dict(
        schema_version="p5-m2-pending-checkpoint-v1",
        checkpoint_present=True,
        official_wait_approval=True,
        original_business_binding=True,
        original_expiry_preserved=True,
        binding_sha256=safe_digest(
            dict(
                values=snapshot.values,
                next=list(snapshot.next),
                interrupt=snapshot.interrupts[0].value,
                expires_at=approval["expires_at"].isoformat(),
                checkpoint_id=snapshot.config["configurable"].get("checkpoint_id"),
            )
        ),
    )


async def pending_checkpoint(config: WebConfig, observed: dict[str, Any]) -> dict[str, Any]:
    """Read official latest state only after writers stopped; no Worker start, setup or invoke."""
    from typing import cast

    from commerceops.application.replenishment.contracts import WORKFLOW_VERSION
    from commerceops.application.runner import RunRequest
    from commerceops.domain.commerce_values import facts_hash
    from commerceops.infrastructure.checkpoint import checkpointer
    from commerceops.infrastructure.replenishment_repository import ApprovalStore
    from commerceops.infrastructure.worker_lock import WorkerSession
    from commerceops.workflows.replenishment import ApprovalRunner
    from psycopg import AsyncConnection

    from scripts.m2_backup import no_other_clients

    with connect(config.database) as db:
        db.execute("SET TRANSACTION READ ONLY")
        no_other_clients(db)
        task = db.execute(
            "SELECT * FROM business.business_tasks WHERE id=%s", (UUID(observed["task_id"]),)
        ).fetchone()
        approval = db.execute(
            "SELECT * FROM business.approvals WHERE id=%s", (UUID(observed["approval_id"]),)
        ).fetchone()
        job = db.execute(
            "SELECT id FROM business.jobs WHERE task_id=%s AND dedupe_key=%s",
            (UUID(observed["task_id"]), "p3:" + observed["task_id"]),
        ).fetchone()
    if task is None or approval is None or job is None:
        raise BackupFailure("M2_PENDING_CHECKPOINT_BUSINESS_BINDING")
    session = WorkerSession(config.database, task["organization_id"])
    runner = ApprovalRunner(ApprovalStore(config, session))
    request = RunRequest(
        job["id"],
        task["id"],
        task["organization_id"],
        task["shop_id"],
        str(task["id"]),
        WORKFLOW_VERSION,
        "analyze",
        "task:" + str(task["id"]),
        "m2-read-only-checkpoint",
        0,
    )
    expected = dict(
        workflow_version=WORKFLOW_VERSION,
        task_id=str(task["id"]),
        request_hash=facts_hash(task["normalized_request"]),
    )
    async with checkpointer(config.database) as saver:
        connection = cast(AsyncConnection[dict[str, Any]], saver.conn)
        await connection.execute("SET default_transaction_read_only=on")
        await connection.execute("SET statement_timeout=5000")
        compiled = runner.build_graph(request, expected).compile(checkpointer=saver)
        snapshot = await compiled.aget_state({"configurable": {"thread_id": str(task["id"])}})
    return validate_waiting_checkpoint(snapshot, task, approval, observed)
