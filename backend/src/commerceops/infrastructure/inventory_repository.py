"""受scope/owner保护的PG inventory证据；业务事务独立于checkpoint。"""

import base64
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import psycopg
from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from commerceops.application.commerce.analysis_task import (
    TASK_KIND,
    WORKFLOW_VERSION,
    CollectedInventory,
    InventoryTaskRequest,
    StoredAnalysis,
    TrustedReadIdentity,
)
from commerceops.application.commerce.inventory_analysis import analyze_inventory
from commerceops.application.commerce.inventory_facts import InventoryInput, InventoryReport
from commerceops.application.runner import RunRequest
from commerceops.domain.commerce_values import canonical_bytes, facts_hash, money, utc_time
from commerceops.domain.inventory_rules import RuleParameters
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.queue import OwnershipLost
from commerceops.infrastructure.repository import PersistenceConflict, TaskRepository, TaskScope
from commerceops.infrastructure.worker_lock import WorkerSession, open_async

READ_VERSION = "p203-read-v1"
SafeHook = Callable[[str], Awaitable[None]]


async def no_store_hook(point: str) -> None:
    pass


class ReadFailure(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status
        super().__init__(code)


class AnalysisUnsafe(ValueError):
    pass


class InventoryStore:
    def __init__(
        self, settings: DatabaseSettings, session: WorkerSession, *, hook: SafeHook = no_store_hook
    ):
        if settings != session.settings:
            raise ValueError("WORKER_SETTINGS_MISMATCH")
        self.settings, self.session, self.hook = settings, session, hook

    async def guard(
        self, db: AsyncConnection[dict[str, Any]], r: RunRequest, *, authorize: bool = True
    ) -> dict[str, Any]:
        await self.session.check()
        if (
            r.owner != self.session.owner
            or r.thread_id != str(r.task_id)
            or r.workflow_version != WORKFLOW_VERSION
        ):
            raise OwnershipLost("ANALYSIS_OWNER_VERSION_MISMATCH")
        cur = await db.execute(
            """SELECT t.*,p.enabled,p.roles,s.environment,s.adapter_kind,
            s.external_shop_key,s.currency,s.timezone,g.enabled AS scope_enabled
            FROM business.jobs j JOIN business.business_tasks t ON t.id=j.task_id
            AND t.organization_id=j.organization_id AND t.shop_id=j.shop_id
            JOIN business.principals p ON p.id=t.requester_id
            AND p.organization_id=t.organization_id
            JOIN business.shops s ON s.id=t.shop_id AND s.organization_id=t.organization_id
            LEFT JOIN business.principal_shop_scopes g ON g.organization_id=t.organization_id
            AND g.shop_id=t.shop_id AND g.principal_id=t.requester_id
            WHERE j.id=%s AND j.task_id=%s AND j.organization_id=%s AND j.shop_id=%s
            AND j.status='running' AND j.lease_owner=%s AND t.thread_id=%s
            AND t.workflow_version=%s AND t.kind=%s FOR UPDATE OF j,t FOR SHARE OF p,s""",
            (
                r.job_id,
                r.task_id,
                r.organization_id,
                r.shop_id,
                r.owner,
                r.thread_id,
                r.workflow_version,
                TASK_KIND,
            ),
        )
        row = await cur.fetchone()
        if row is None:
            raise OwnershipLost("ANALYSIS_TASK_JOB_MISMATCH")
        if authorize and (
            not row["enabled"]
            or "operator" not in row["roles"]
            or not row["scope_enabled"]
            or row["environment"] not in ("test", "mock")
            or row["adapter_kind"] != "mock"
        ):
            raise AnalysisUnsafe("ANALYSIS_PERMISSION_INVALID")
        if authorize:
            permission = await db.execute(
                "SELECT business.lock_inventory_permission(%s,%s,%s,NULL,NULL) AS allowed",
                (row["requester_id"], r.organization_id, r.shop_id),
            )
            decision = await permission.fetchone()
            if not decision or not decision["allowed"]:
                raise AnalysisUnsafe("ANALYSIS_PERMISSION_INVALID")
        if authorize:
            InventoryTaskRequest.model_validate(row["normalized_request"])
        return row

    async def load(self, r: RunRequest, *, authorize: bool = True) -> dict[str, Any]:
        async with await open_async(self.settings) as db, db.transaction():
            return await self.guard(db, r, authorize=authorize)

    async def existing(self, r: RunRequest, *, authorize: bool = True) -> StoredAnalysis | None:
        async with await open_async(self.settings) as db, db.transaction():
            task = await self.guard(db, r, authorize=authorize)
            cur = await db.execute(
                """SELECT a.*,s.content_hash,s.content AS snapshot_content,
                s.window_start,s.window_end FROM business.analysis_reports a
                JOIN business.commerce_snapshots s ON s.id=a.snapshot_id AND s.task_id=a.task_id
                WHERE a.organization_id=%s AND a.shop_id=%s AND a.task_id=%s""",
                (r.organization_id, r.shop_id, r.task_id),
            )
            row = await cur.fetchone()
            if row is None:
                if task["state"] == "completed":
                    raise AnalysisUnsafe("ANALYSIS_RESULT_MISSING")
                return None
            valid = await db.execute(
                "SELECT business.valid_inventory_result(%s,%s,%s,%s) AS valid",
                (r.task_id, r.organization_id, r.shop_id, r.workflow_version),
            )
            checked = await valid.fetchone()
            if task["state"] != "completed" or not checked or not checked["valid"]:
                raise AnalysisUnsafe("ANALYSIS_RESULT_CONFLICT")
            return _stored(row, task["normalized_request"])

    async def mark(self, r: RunRequest, state: str, code: str | None = None) -> None:
        async with await open_async(self.settings) as db, db.transaction():
            row = await self.guard(db, r, authorize=state == "analyzing")
            if row["state"] in ("completed", "failed"):
                return
            if row["state"] == state and row["failure_code"] == code:
                return
            await db.execute(
                """UPDATE business.business_tasks SET state=%s,failure_code=%s,
                version=version+1,updated_at=clock_timestamp() WHERE id=%s""",
                (state, code, r.task_id),
            )
            await db.execute(
                """INSERT INTO business.audit_events
                (id,organization_id,task_id,actor_id,source,action,entity_type,entity_id,after_state,trace_id)
                VALUES (%s,%s,%s,%s,'inventory_analysis',%s,'task',%s,%s,%s)""",
                (
                    uuid4(),
                    r.organization_id,
                    r.task_id,
                    row["requester_id"],
                    "analysis_started" if state == "analyzing" else "analysis_failed",
                    str(r.task_id),
                    Jsonb({"schema_version": READ_VERSION, "code": code, "state": state}),
                    uuid4(),
                ),
            )

    async def save(
        self, r: RunRequest, collected: CollectedInventory, report: InventoryReport
    ) -> StoredAnalysis:
        # model_copy/model_construct不执行完整验证；持久边界重新校验输入及完整报告。
        try:
            data = InventoryInput.model_validate_json(
                collected.data.model_dump_json(warnings=False)
            )
            report = InventoryReport.model_validate_json(report.model_dump_json(warnings=False))
            started = utc_time(collected.collection_started_at)
            ended = utc_time(collected.collected_at)
            if ended < started or collected.consistency != "observational":
                raise ValueError("INVALID_COLLECTION_TIME")
        except (ValueError, TypeError, AttributeError):
            raise AnalysisUnsafe("ANALYSIS_REPORT_BINDING_MISMATCH") from None
        # numeric(20,6)边界在发送SQL前校验；DB另用未舍入payload比对拒直接写入舍入。
        for row in data.order_lines:
            money(row.net_amount)
            money(row.tax_amount)
        for refund in data.refunds:
            money(refund.refund_amount)
        content = data.model_dump(mode="json")
        encoded = canonical_bytes(content).decode()
        content_hash = facts_hash(content)
        logical = f"analysis:{r.task_id}:{WORKFLOW_VERSION}"
        outcome: Literal["report_ready", "no_action"] = (
            "no_action"
            if report.complete and report.candidate_count == 0 and not report.requires_review
            else "report_ready"
        )
        async with await open_async(self.settings) as db, db.transaction():
            task = await self.guard(db, r)
            request = InventoryTaskRequest.model_validate(task["normalized_request"])
            expected = analyze_inventory(data, RuleParameters(request.L, request.R, request.S))
            if report != expected:
                raise AnalysisUnsafe("ANALYSIS_REPORT_BINDING_MISMATCH")
            if (
                data.source.shop_id != task["external_shop_key"]
                or data.source.currency != task["currency"]
                or data.source.timezone != task["timezone"]
            ):
                raise AnalysisUnsafe("ANALYSIS_SOURCE_SCOPE_MISMATCH")
            cur = await db.execute(
                """SELECT a.*,s.content_hash,s.content AS snapshot_content,
                s.window_start,s.window_end FROM business.analysis_reports a
                JOIN business.commerce_snapshots s ON s.id=a.snapshot_id WHERE a.task_id=%s""",
                (r.task_id,),
            )
            old = await cur.fetchone()
            if old is not None:
                result = _stored(old, task["normalized_request"])
                if (
                    result.content_hash != content_hash
                    or result.report.facts_hash != report.facts_hash
                ):
                    raise PersistenceConflict("ANALYSIS_REPLAY_CONFLICT")
                return result
            if task["state"] != "analyzing":
                raise AnalysisUnsafe("ANALYSIS_STATE_INVALID")
            snapshot_id, report_id = uuid4(), uuid4()
            scope = (r.organization_id, r.shop_id, r.task_id)
            await db.execute(
                """INSERT INTO business.commerce_snapshots
                (id,organization_id,shop_id,task_id,logical_key,request_content,request_hash,schema_version,source_kind,fixture_version,
                 shop_timezone,currency,window_start,window_end,collection_started_at,collected_at,complete,
                 warnings,consistency,content,canonical_content,content_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    snapshot_id,
                    *scope,
                    logical,
                    canonical_bytes(task["normalized_request"]).decode(),
                    facts_hash(task["normalized_request"]),
                    data.schema_version,
                    data.source.provenance.source_kind,
                    data.source.provenance.fixture_version,
                    data.source.timezone,
                    data.source.currency,
                    report.window.start,
                    report.window.end,
                    started,
                    ended,
                    data.complete,
                    Jsonb(list(report.warnings)),
                    collected.consistency,
                    Jsonb(content),
                    encoded,
                    content_hash,
                ),
            )
            stocks = {s.sku_key: s for s in data.inventories}
            for product in data.products:
                stock = stocks.get(product.sku_key)
                payload = {
                    "product": product.model_dump(mode="json"),
                    "inventory": stock.model_dump(mode="json") if stock else None,
                }
                await db.execute(
                    """INSERT INTO business.snapshot_products
                    (snapshot_id,organization_id,shop_id,task_id,sku_key,stock_pool_key,payload,available_stock,inbound_units)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        snapshot_id,
                        *scope,
                        product.sku_key,
                        product.stock_pool_key,
                        Jsonb(payload),
                        stock.available_stock if stock else None,
                        stock.inbound_units if stock else None,
                    ),
                )
            for row in data.order_lines:
                await db.execute(
                    """INSERT INTO business.snapshot_order_lines
                    (snapshot_id,organization_id,shop_id,task_id,order_id,line_id,sku_key,status,created_at_source,
                     paid_at,completed_at,quantity,net_amount,tax_amount,currency,payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        snapshot_id,
                        *scope,
                        row.order_id,
                        row.line_id,
                        row.sku_key,
                        row.status,
                        row.created_at,
                        row.paid_at,
                        row.completed_at,
                        row.quantity,
                        row.net_amount,
                        row.tax_amount,
                        row.currency,
                        Jsonb(row.model_dump(mode="json")),
                    ),
                )
            for row_refund in data.refunds:
                await db.execute(
                    """INSERT INTO business.snapshot_refunds
                    (snapshot_id,organization_id,shop_id,task_id,refund_id,order_id,occurred_at,refund_amount,currency,payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        snapshot_id,
                        *scope,
                        row_refund.refund_id,
                        row_refund.order_id,
                        row_refund.created_at,
                        row_refund.refund_amount,
                        row_refund.currency,
                        Jsonb(row_refund.model_dump(mode="json")),
                    ),
                )
            await self.hook("after_snapshot")
            await db.execute(
                """INSERT INTO business.analysis_reports
                (id,organization_id,shop_id,task_id,snapshot_id,logical_key,rule_version,schema_version,
                 facts,canonical_facts,facts_hash,report,outcome)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    report_id,
                    *scope,
                    snapshot_id,
                    logical,
                    report.rule_version,
                    report.schema_version,
                    Jsonb(report.canonical_facts()),
                    report.canonical_bytes().decode(),
                    report.facts_hash,
                    Jsonb(report.model_dump(mode="json")),
                    outcome,
                ),
            )
            await self.hook("after_report")
            await db.execute(
                """UPDATE business.business_tasks SET state='completed',failure_code=NULL,
                version=version+1,updated_at=clock_timestamp() WHERE id=%s""",
                (r.task_id,),
            )
            await db.execute(
                """INSERT INTO business.audit_events
                (id,organization_id,task_id,actor_id,source,action,entity_type,entity_id,after_state,trace_id)
                VALUES (%s,%s,%s,%s,'inventory_analysis','analysis_report_saved',
                'report',%s,%s,%s)""",
                (
                    uuid4(),
                    r.organization_id,
                    r.task_id,
                    task["requester_id"],
                    str(report_id),
                    Jsonb(
                        {
                            "schema_version": READ_VERSION,
                            "snapshot_id": str(snapshot_id),
                            "report_id": str(report_id),
                            "complete": report.complete,
                            "outcome": outcome,
                        }
                    ),
                    uuid4(),
                ),
            )
            await self.hook("before_commit")
            await self.session.check()
        await self.hook("after_commit")
        return StoredAnalysis(snapshot_id, report_id, content_hash, report, outcome)


def _stored(row: dict[str, Any], normalized_request: dict[str, Any]) -> StoredAnalysis:
    report = InventoryReport.model_validate_json(json.dumps(row["report"]))
    data = InventoryInput.model_validate_json(json.dumps(row["snapshot_content"]))
    request = InventoryTaskRequest.model_validate(normalized_request)
    expected = analyze_inventory(data, RuleParameters(request.L, request.R, request.S))
    if (
        report != expected
        or row["window_start"] != report.window.start
        or row["window_end"] != report.window.end
    ):
        raise AnalysisUnsafe("ANALYSIS_REPORT_BINDING_MISMATCH")
    return StoredAnalysis(
        UUID(str(row["snapshot_id"])),
        UUID(str(row["id"])),
        row["content_hash"],
        report,
        row["outcome"],
    )


def create_analysis_task(
    settings: DatabaseSettings,
    identity: TrustedReadIdentity,
    conversation: UUID,
    request: InventoryTaskRequest,
) -> tuple[UUID, UUID]:
    with connect(settings) as db:
        _authorize(db, identity)
        task_id = uuid4()
        db.execute(
            """INSERT INTO business.business_tasks
            (id,organization_id,shop_id,conversation_id,requester_id,kind,normalized_request,workflow_version,thread_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                task_id,
                identity.organization_id,
                identity.shop_id,
                conversation,
                identity.principal_id,
                TASK_KIND,
                Jsonb(request.model_dump(mode="json")),
                WORKFLOW_VERSION,
                str(task_id),
            ),
        )
        job_id = TaskRepository(db, TaskScope(identity.organization_id, identity.shop_id)).enqueue(
            task_id, "analyze", f"analysis:{task_id}", f"task:{task_id}"
        )
        return task_id, job_id


def _authorize(db: psycopg.Connection[dict[str, Any]], identity: TrustedReadIdentity) -> None:
    row = db.execute(
        "SELECT business.lock_inventory_permission(%s,%s,%s,%s,%s) AS allowed",
        (
            identity.principal_id,
            identity.organization_id,
            identity.shop_id,
            identity.identity_id,
            identity.auth_version,
        ),
    ).fetchone()
    if not row or not row["allowed"]:
        raise ReadFailure("IDENTITY_SCOPE_DENIED", 403)


class InventoryReadStore:
    def __init__(self, settings: DatabaseSettings):
        self.settings = settings

    def read(
        self,
        identity: TrustedReadIdentity,
        task_id: UUID,
        resource: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        try:
            with connect(self.settings) as db:
                _authorize(db, identity)
                task = db.execute(
                    """SELECT * FROM business.business_tasks WHERE id=%s AND organization_id=%s
                    AND shop_id=%s AND requester_id=%s AND kind=%s AND workflow_version=%s""",
                    (
                        task_id,
                        identity.organization_id,
                        identity.shop_id,
                        identity.principal_id,
                        TASK_KIND,
                        WORKFLOW_VERSION,
                    ),
                ).fetchone()
                if task is None:
                    raise ReadFailure("TASK_NOT_FOUND", 404)
                common = {
                    "schema_version": READ_VERSION,
                    "task_id": str(task_id),
                    "analysis_only": True,
                    "execution_available": False,
                    "identity_mode": "simulated",
                }
                result = db.execute(
                    """SELECT a.*,s.content_hash,s.content AS snapshot_content,
                    s.collection_started_at,s.collected_at,
                    s.complete AS source_complete,s.warnings,s.consistency,
                    s.source_kind,s.fixture_version,
                    s.window_start,s.window_end FROM business.analysis_reports a
                    JOIN business.commerce_snapshots s ON s.id=a.snapshot_id
                    AND s.organization_id=a.organization_id AND s.shop_id=a.shop_id
                    AND s.task_id=a.task_id
                    WHERE a.task_id=%s AND a.organization_id=%s AND a.shop_id=%s""",
                    (task_id, identity.organization_id, identity.shop_id),
                ).fetchone()
                persisted = _stored(result, task["normalized_request"]) if result else None
                if resource == "task":
                    return {
                        **common,
                        "state": task["state"],
                        "kind": task["kind"],
                        "workflow_version": task["workflow_version"],
                        "created_at": task["created_at"],
                        "updated_at": task["updated_at"],
                        "failure_code": task["failure_code"]
                        if task["failure_code"]
                        in (
                            "ANALYSIS_INPUT_INVALID",
                            "ANALYSIS_CHECKPOINT_UNSAFE",
                            "ANALYSIS_STORAGE_FAILURE",
                            "WORKER_TERMINATION_UNCONFIRMED",
                        )
                        else None,
                        "outcome": result["outcome"] if result else None,
                    }
                if resource == "report":
                    if result is None:
                        raise ReadFailure("REPORT_NOT_READY", 409)
                    if persisted is None:
                        raise ReadFailure("REPORT_NOT_READY", 409)
                    report = persisted.report
                    return {
                        **common,
                        "snapshot_id": str(result["snapshot_id"]),
                        "report_id": str(result["id"]),
                        "content_hash": result["content_hash"],
                        "outcome": result["outcome"],
                        "collection_started_at": result["collection_started_at"],
                        "collected_at": result["collected_at"],
                        "source_complete": result["source_complete"],
                        "consistency": result["consistency"],
                        "facts": report,
                    }
                if resource != "events":
                    raise ReadFailure("INVALID_RESOURCE", 404)
                return self._events(db, identity, task_id, common, limit, cursor)
        except ReadFailure:
            raise
        except (psycopg.Error, OSError, ValueError):
            raise ReadFailure("DATABASE_UNAVAILABLE", 503) from None

    def _events(
        self,
        db: psycopg.Connection[dict[str, Any]],
        identity: TrustedReadIdentity,
        task_id: UUID,
        common: dict[str, Any],
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ReadFailure("INVALID_PAGE_LIMIT", 400)
        binding = [
            READ_VERSION,
            str(task_id),
            str(identity.organization_id),
            str(identity.shop_id),
            str(identity.principal_id),
            identity.auth_version,
        ]
        after = datetime.min.replace(tzinfo=UTC)
        after_id = UUID(int=0)
        if cursor is not None:
            try:
                if len(cursor) > 2048:
                    raise ValueError
                body = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
                if (
                    type(body) is not list
                    or len(body) != 8
                    or body[:6] != binding
                    or type(body[5]) is not int
                    or type(body[6]) is not str
                    or type(body[7]) is not str
                ):
                    raise ValueError
                after, after_id = utc_time(body[6]), UUID(body[7])
            except (ValueError, TypeError, UnicodeError, RecursionError):
                raise ReadFailure("INVALID_EVENT_CURSOR", 400) from None
        rows = db.execute(
            """SELECT id,occurred_at,action,after_state FROM business.audit_events
            WHERE organization_id=%s AND task_id=%s AND source='inventory_analysis'
            AND action IN ('analysis_started','analysis_failed','analysis_report_saved')
            AND (occurred_at,id)>(%s,%s) ORDER BY occurred_at,id LIMIT %s""",
            (identity.organization_id, task_id, after, after_id, limit + 1),
        ).fetchall()
        page = rows[:limit]
        items = []
        for row in page:
            state = row["after_state"]
            if type(state) is not dict:
                state = {}
            safe: dict[str, Any] = {}
            for key in ("snapshot_id", "report_id"):
                try:
                    if key in state:
                        safe[key] = str(UUID(state[key]))
                except (ValueError, TypeError, AttributeError):
                    pass
            if type(state.get("complete")) is bool:
                safe["complete"] = state["complete"]
            if state.get("outcome") in ("report_ready", "no_action"):
                safe["outcome"] = state["outcome"]
            if state.get("state") in (
                "queued",
                "analyzing",
                "completed",
                "failed",
                "needs_attention",
            ):
                safe["state"] = state["state"]
            if state.get("code") in (
                "ANALYSIS_PERMISSION_INVALID",
                "ANALYSIS_STATE_INVALID",
                "ANALYSIS_INPUT_INVALID",
                "ANALYSIS_CHECKPOINT_UNSAFE",
                "ANALYSIS_STORAGE_FAILURE",
            ):
                safe["code"] = state["code"]
            items.append(
                {
                    "id": str(row["id"]),
                    "occurred_at": row["occurred_at"],
                    "action": row["action"],
                    "details": safe,
                }
            )
        next_cursor = None
        if len(rows) > limit:
            last = page[-1]
            next_cursor = base64.urlsafe_b64encode(
                canonical_bytes([*binding, last["occurred_at"], str(last["id"])])
            ).decode()
        return {**common, "items": items, "next_cursor": next_cursor}
