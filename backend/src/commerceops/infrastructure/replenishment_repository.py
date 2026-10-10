"""P3 T1/T2 PostgreSQL权威事务；只引用P2冻结证据，不复活其completed。"""

import json
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from commerceops.adapters.commerce.mock import Fixture
from commerceops.application.commerce.analysis_task import InventoryTaskRequest
from commerceops.application.replenishment.contracts import (
    TASK_KIND,
    WORKFLOW_VERSION,
    CreateFromReport,
    CreateInput,
    CreateNewCycle,
    WebActor,
    WebFailure,
)
from commerceops.application.replenishment.planning import PlanRejected, freeze_plan
from commerceops.application.replenishment.security import approval_nonce, digest
from commerceops.application.runner import RunRequest
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe, _stored
from commerceops.infrastructure.repository import TaskRepository, TaskScope
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import DB, actor_guard, envelope, role_scope
from commerceops.infrastructure.worker_lock import WorkerSession, open_async

SOURCE_SQL = """SELECT r.*,s.content_hash,s.content AS snapshot_content,
s.complete AS source_complete,
s.collection_started_at,s.collected_at,s.consistency,s.window_start,s.window_end,
t.normalized_request,t.requester_id,t.state AS source_state,s.source_kind
FROM business.analysis_reports r JOIN business.commerce_snapshots s
ON s.id=r.snapshot_id AND s.task_id=r.task_id AND s.organization_id=r.organization_id
AND s.shop_id=r.shop_id JOIN business.business_tasks t ON t.id=r.task_id
WHERE t.id=%s AND t.organization_id=%s AND t.shop_id=%s
AND t.kind='inventory_analysis_only' AND t.workflow_version='p203-inventory-analysis-v1'"""


def source_binding(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_task_id": str(row["task_id"]),
        "report_id": str(row["id"]),
        "snapshot_id": str(row["snapshot_id"]),
        "facts_hash": row["facts_hash"],
        "collected_at": row["collected_at"],
        "collection_started_at": row["collection_started_at"],
        "source_complete": row["source_complete"],
        "consistency": row["consistency"],
    }


def parameters_of(row: dict[str, Any]) -> dict[str, Any]:
    request = InventoryTaskRequest.model_validate(row["normalized_request"])
    return request.model_dump(mode="json", exclude={"schema_version"})


def has_capability(db: DB, actor: WebActor, role: str) -> bool:
    principal = actor_guard(db, actor)
    if role not in principal["roles"]:
        return False
    row = db.execute(
        """SELECT 1 FROM business.principal_role_shop_grants g
    JOIN business.principal_shop_scopes s ON s.organization_id=g.organization_id
    AND s.shop_id=g.shop_id AND s.principal_id=g.principal_id
    WHERE g.organization_id=%s AND g.principal_id=%s AND g.role=%s AND g.enabled AND s.enabled""",
        (actor.organization_id, actor.principal_id, role),
    ).fetchone()
    return row is not None


def visible_task(db: DB, actor: WebActor, task_id: UUID) -> dict[str, Any]:
    actor_guard(db, actor)
    task = db.execute(
        "SELECT * FROM business.business_tasks WHERE id=%s AND organization_id=%s",
        (task_id, actor.organization_id),
    ).fetchone()
    if task is None:
        raise WebFailure("RESOURCE_NOT_FOUND", 404)
    if task["kind"] not in (TASK_KIND, "inventory_analysis_only"):
        raise WebFailure("RESOURCE_NOT_FOUND", 404)
    if task["requester_id"] == actor.principal_id and role_scope(
        db, actor, task["shop_id"], "operator"
    ):
        return task
    if task["kind"] == TASK_KIND and role_scope(db, actor, task["shop_id"], "approver"):
        eligible = db.execute(
            """SELECT 1 FROM business.approvals WHERE task_id=%s
        AND organization_id=%s AND shop_id=%s AND %s=ANY(eligible_principal_ids)""",
            (task_id, actor.organization_id, task["shop_id"], actor.principal_id),
        ).fetchone()
        if eligible:
            return task
    raise WebFailure("RESOURCE_NOT_FOUND", 404)


class ReplenishmentStore:
    def __init__(self, config: WebConfig, fixture_directory: Path):
        self.config, self.settings = config, config.database
        self.fixture_directory = fixture_directory

    def create(
        self, actor: WebActor, request: CreateInput, hook: Callable[[str], None] | None = None
    ) -> dict[str, Any]:
        payload = request.model_dump(mode="json", exclude={"request_key"})
        request_hash = facts_hash({"path": "/api/v1/tasks", "body": payload})
        with connect(self.settings) as db:
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"web:create_task:{actor.principal_id}:{request.request_key}",),
            )
            actor_guard(db, actor)
            old = db.execute(
                """SELECT * FROM business.web_requests
            WHERE principal_id=%s AND operation='create_task' AND request_key=%s""",
                (actor.principal_id, request.request_key),
            ).fetchone()
            if old:
                visible_task(db, actor, old["task_id"])
                if old["request_hash"] != request_hash:
                    raise WebFailure("IDEMPOTENCY_CONFLICT")
                return envelope(
                    db,
                    **{
                        k: v
                        for k, v in old["result"].items()
                        if k
                        not in (
                            "schema_version",
                            "identity_mode",
                            "server_time",
                            "trace_id",
                            "duplicate",
                        )
                    },
                    duplicate=True,
                )
            if not has_capability(db, actor, "operator"):
                raise WebFailure("ACCESS_DENIED", 403)
            if isinstance(request, CreateFromReport):
                source_task = db.execute(
                    """SELECT * FROM business.business_tasks WHERE id=%s
                AND organization_id=%s AND requester_id=%s AND kind='inventory_analysis_only'
                AND workflow_version='p203-inventory-analysis-v1'""",
                    (request.source_task_id, actor.organization_id, actor.principal_id),
                ).fetchone()
                if not source_task or not role_scope(db, actor, source_task["shop_id"], "operator"):
                    raise WebFailure("RESOURCE_NOT_FOUND", 404)
                shop = source_task["shop_id"]
                source_id = request.source_task_id
                source = db.execute(SOURCE_SQL, (source_id, actor.organization_id, shop)).fetchone()
                if source is None or source["source_state"] != "completed":
                    raise WebFailure("NOT_READY")
                if (source["id"], source["snapshot_id"], source["facts_hash"]) != (
                    request.source_report_id,
                    request.snapshot_id,
                    request.facts_hash,
                ):
                    raise WebFailure("PLAN_CHANGED")
                _stored(source, source["normalized_request"])
                params = parameters_of(source)
            else:
                shop, source_id = request.shop_id, uuid4()
                if not role_scope(db, actor, shop, "operator"):
                    raise WebFailure("RESOURCE_NOT_FOUND", 404)
                params = request.parameters.model_dump(mode="json")
                try:
                    Fixture.load(self.fixture_directory, request.parameters.fixture_case)
                except (ValueError, KeyError, OSError):
                    raise WebFailure("INVALID_REQUEST", 422) from None
                source = None
            target = db.execute(
                """SELECT * FROM business.shops WHERE id=%s AND organization_id=%s
            AND adapter_kind='mock' AND environment IN ('mock','test')""",
                (shop, actor.organization_id),
            ).fetchone()
            if not target:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            conversation = self._conversation(db, actor)
            if source is None:
                if not isinstance(request, CreateNewCycle):
                    raise WebFailure("SERVICE_UNAVAILABLE", 503)
                self._task(
                    db,
                    actor,
                    shop,
                    conversation,
                    source_id,
                    "inventory_analysis_only",
                    "p203-inventory-analysis-v1",
                    request.parameters.analysis_request().model_dump(mode="json"),
                )
                TaskRepository(db, TaskScope(actor.organization_id, shop)).enqueue(
                    source_id, "analyze", f"analysis:{source_id}", f"task:{source_id}"
                )
            task_id = uuid4()
            self._task(
                db,
                actor,
                shop,
                conversation,
                task_id,
                TASK_KIND,
                WORKFLOW_VERSION,
                {
                    "schema_version": "p3-web-v1",
                    "mode": request.mode,
                    "identity_id": str(actor.identity_id),
                    "request": payload,
                },
            )
            db.execute(
                """INSERT INTO business.p3_task_sources
            (organization_id,shop_id,task_id,source_task_id,source_report_id,snapshot_id,
            facts_hash,mode,parameters,config_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    actor.organization_id,
                    shop,
                    task_id,
                    source_id,
                    source["id"] if source else None,
                    source["snapshot_id"] if source else None,
                    source["facts_hash"] if source else None,
                    request.mode,
                    Jsonb(params),
                    self.config.config_version,
                ),
            )
            TaskRepository(db, TaskScope(actor.organization_id, shop)).enqueue(
                task_id, "analyze", f"p3:{task_id}", f"task:{task_id}"
            )
            self._audit(db, actor.organization_id, task_id, actor.principal_id, "workflow_created")
            receipt = envelope(
                db,
                request_key=request.request_key,
                task_id=task_id,
                source_task_id=source_id,
                state="queued",
                duplicate=False,
            )
            # datetime/UUID统一JSON，原回执不含Cookie/CSRF/nonce。
            from commerceops.domain.commerce_values import canonical_bytes

            db.execute(
                """INSERT INTO business.web_requests
            (organization_id,principal_id,operation,request_key,request_hash,task_id,result)
            VALUES (%s,%s,'create_task',%s,%s,%s,%s)""",
                (
                    actor.organization_id,
                    actor.principal_id,
                    request.request_key,
                    request_hash,
                    task_id,
                    Jsonb(json.loads(canonical_bytes(receipt))),
                ),
            )
            if hook:
                hook("before_commit")
        if hook:
            hook("after_commit")
        return receipt

    @staticmethod
    def _conversation(db: DB, actor: WebActor) -> UUID:
        proposed = uuid4()
        db.execute(
            """INSERT INTO business.conversations
        (id,organization_id,channel,chat_id,actor_id,topic_key)
        VALUES (%s,%s,'web',%s,%s,'p3') ON CONFLICT DO NOTHING""",
            (proposed, actor.organization_id, str(actor.principal_id), actor.principal_id),
        )
        row = db.execute(
            """SELECT id FROM business.conversations WHERE organization_id=%s
        AND channel='web' AND chat_id=%s AND actor_id=%s AND topic_key='p3'""",
            (actor.organization_id, str(actor.principal_id), actor.principal_id),
        ).fetchone()
        if row is None:
            raise WebFailure("SERVICE_UNAVAILABLE", 503)
        return row["id"]  # type: ignore[no-any-return]

    @staticmethod
    def _task(
        db: DB,
        actor: WebActor,
        shop: UUID,
        conversation: UUID,
        task: UUID,
        kind: str,
        version: str,
        payload: dict[str, Any],
    ) -> None:
        db.execute(
            """INSERT INTO business.business_tasks
        (id,organization_id,shop_id,conversation_id,requester_id,kind,normalized_request,
        workflow_version,thread_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                task,
                actor.organization_id,
                shop,
                conversation,
                actor.principal_id,
                kind,
                Jsonb(payload),
                version,
                str(task),
            ),
        )

    @staticmethod
    def _audit(db: DB, org: UUID, task: UUID, principal: UUID, action: str) -> None:
        db.execute(
            """INSERT INTO business.audit_events
        (id,organization_id,task_id,actor_id,source,action,entity_type,entity_id,trace_id)
        VALUES (%s,%s,%s,%s,'replenishment',%s,'task',%s,%s)""",
            (uuid4(), org, task, principal, action, str(task), uuid4()),
        )


class ApprovalStore:
    def __init__(
        self, config: WebConfig, session: WorkerSession, hook: Callable[[str], Any] | None = None
    ):
        self.config, self.session = config, session
        self.settings, self.hook = config.database, hook

    async def prepare(self, r: RunRequest) -> dict[str, Any]:
        if r.owner != self.session.owner or r.workflow_version != WORKFLOW_VERSION:
            raise AnalysisUnsafe("P3_WORKER_OWNER_INVALID")
        await self.session.check()
        async with await open_async(self.settings) as db, db.transaction():
            cur = await db.execute(
                """SELECT t.*,s.source_task_id,s.source_report_id,s.snapshot_id,
            s.facts_hash,s.parameters,s.config_version FROM business.business_tasks t
            JOIN business.p3_task_sources s ON s.task_id=t.id
            AND s.organization_id=t.organization_id
            AND s.shop_id=t.shop_id JOIN business.jobs j ON j.task_id=t.id
            WHERE t.id=%s AND t.organization_id=%s AND t.shop_id=%s AND t.kind=%s
            AND t.workflow_version=%s AND j.id=%s AND j.status='running' AND j.lease_owner=%s
            FOR UPDATE OF t""",
                (
                    r.task_id,
                    r.organization_id,
                    r.shop_id,
                    TASK_KIND,
                    WORKFLOW_VERSION,
                    r.job_id,
                    r.owner,
                ),
            )
            task = await cur.fetchone()
            if not task:
                raise AnalysisUnsafe("P3_TASK_OWNERSHIP_INVALID")
            if task["active_plan_id"]:
                cur = await db.execute(
                    "SELECT id FROM business.approvals WHERE plan_id=%s", (task["active_plan_id"],)
                )
                approval = await cur.fetchone()
                if not approval:
                    raise AnalysisUnsafe("P3_PLAN_APPROVAL_MISSING")
                return {
                    "plan_id": str(task["active_plan_id"]),
                    "approval_id": str(approval["id"]),
                    "outcome": "awaiting_approval",
                }
            if task["state"] == "completed":
                return {"outcome": "no_action"}
            if task["state"] not in ("queued", "analyzing"):
                raise AnalysisUnsafe("P3_STATE_INVALID")
            identity = UUID(task["normalized_request"]["identity_id"])
            cur = await db.execute(
                "SELECT auth_version FROM business.principals "
                "WHERE id=%s AND organization_id=%s FOR SHARE",
                (task["requester_id"], r.organization_id),
            )
            principal = await cur.fetchone()
            cur = await db.execute(
                "SELECT business.lock_p3_permission(%s,%s,%s,%s,%s,'operator') AS allowed",
                (
                    task["requester_id"],
                    r.organization_id,
                    r.shop_id,
                    identity,
                    principal["auth_version"] if principal else 0,
                ),
            )
            permission = await cur.fetchone()
            if not permission or not permission["allowed"]:
                raise PlanRejected("ACCESS_DENIED")
            cur = await db.execute(
                SOURCE_SQL, (task["source_task_id"], r.organization_id, r.shop_id)
            )
            source = await cur.fetchone()
            if source is None:
                cur = await db.execute(
                    "SELECT state FROM business.business_tasks WHERE id=%s",
                    (task["source_task_id"],),
                )
                state = await cur.fetchone()
                if not state or state["state"] in ("failed", "needs_attention"):
                    raise PlanRejected("DATA_INCOMPLETE")
                return {"outcome": "source_pending"}
            if (
                source["requester_id"] != task["requester_id"]
                or source["source_state"] != "completed"
            ):
                raise AnalysisUnsafe("P3_SOURCE_OWNER_INVALID")
            persisted = _stored(source, source["normalized_request"])
            if task["source_report_id"] is None:
                await db.execute(
                    """UPDATE business.p3_task_sources SET source_report_id=%s,snapshot_id=%s,
                facts_hash=%s WHERE task_id=%s""",
                    (source["id"], source["snapshot_id"], source["facts_hash"], r.task_id),
                )
            elif (task["source_report_id"], task["snapshot_id"], task["facts_hash"]) != (
                source["id"],
                source["snapshot_id"],
                source["facts_hash"],
            ):
                raise AnalysisUnsafe("P3_SOURCE_BINDING_INVALID")
            if task["config_version"] != self.config.config_version:
                raise PlanRejected("CONFIG_VERSION_UNSUPPORTED")
            cur = await db.execute("SELECT clock_timestamp() AS time")
            clock = await cur.fetchone()
            if not clock:
                raise AnalysisUnsafe("P3_CLOCK_UNAVAILABLE")
            plan_id, approval_id = uuid4(), uuid4()
            expires = clock["time"] + timedelta(seconds=self.config.approval_ttl_seconds)
            plan = freeze_plan(
                organization_id=r.organization_id,
                shop_id=r.shop_id,
                task_id=r.task_id,
                plan_id=plan_id,
                version=1,
                source=source_binding(source),
                report=persisted.report,
                expires_at=expires,
                parameters=task["parameters"],
                config_version=self.config.config_version,
                max_items=self.config.max_plan_items,
            )
            if plan is None:
                await db.execute(
                    "UPDATE business.business_tasks SET state='completed',version=version+1,"
                    "updated_at=clock_timestamp() WHERE id=%s",
                    (r.task_id,),
                )
                return {"outcome": "no_action"}
            cur = await db.execute(
                """SELECT p.id FROM business.principals p
            JOIN business.principal_role_shop_grants g ON g.principal_id=p.id
            AND g.organization_id=p.organization_id JOIN business.principal_shop_scopes s
            ON s.organization_id=g.organization_id AND s.principal_id=g.principal_id
            AND s.shop_id=g.shop_id
            WHERE p.organization_id=%s AND g.shop_id=%s AND p.enabled AND g.enabled AND s.enabled
            AND g.role='approver' AND 'approver'=ANY(p.roles) ORDER BY p.id FOR SHARE OF p""",
                (r.organization_id, r.shop_id),
            )
            eligible = [row["id"] for row in await cur.fetchall()]
            nonce = approval_nonce(
                self.config.nonce_secret, approval_id, plan_id, 1, plan.plan_hash, expires
            )
            await db.execute(
                """INSERT INTO business.replenishment_plans
            (id,organization_id,shop_id,task_id,version,source_task_id,report_id,snapshot_id,facts_hash,
            plan_hash,content,canonical_content,expires_at)
            VALUES (%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    plan_id,
                    r.organization_id,
                    r.shop_id,
                    r.task_id,
                    source["task_id"],
                    source["id"],
                    source["snapshot_id"],
                    source["facts_hash"],
                    plan.plan_hash,
                    Jsonb(plan.content),
                    plan.canonical_content,
                    expires,
                ),
            )
            await db.execute(
                """INSERT INTO business.approvals
            (id,organization_id,shop_id,task_id,plan_id,plan_version,plan_hash,eligible_principal_ids,
            nonce_hash,nonce_key_version,expires_at) VALUES (%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s)""",
                (
                    approval_id,
                    r.organization_id,
                    r.shop_id,
                    r.task_id,
                    plan_id,
                    plan.plan_hash,
                    eligible,
                    digest(nonce),
                    self.config.key_version,
                    expires,
                ),
            )
            payload = {
                "schema_version": "p3-web-v1",
                "approval_id": str(approval_id),
                "plan_id": str(plan_id),
                "plan_version": 1,
                "plan_hash": plan.plan_hash,
            }
            await db.execute(
                """INSERT INTO business.outbox
            (id,organization_id,shop_id,task_id,destination,aggregate_id,aggregate_version,
            operation,dedupe_key,request_hash,payload,provider_idempotency_key,status)
            VALUES (%s,%s,%s,%s,'feishu_card',%s,1,'approval_card',%s,%s,%s,%s,'blocked')""",
                (
                    uuid4(),
                    r.organization_id,
                    r.shop_id,
                    r.task_id,
                    approval_id,
                    f"card:{approval_id}:1",
                    facts_hash(payload),
                    Jsonb(payload),
                    uuid4(),
                ),
            )
            await db.execute(
                "UPDATE business.business_tasks SET active_plan_id=%s,state='awaiting_approval',"
                "version=version+1,updated_at=clock_timestamp() WHERE id=%s",
                (plan_id, r.task_id),
            )
            await db.execute(
                """INSERT INTO business.audit_events
            (id,organization_id,task_id,actor_id,source,action,entity_type,entity_id,trace_id)
            VALUES (%s,%s,%s,%s,'replenishment','approval_prepared','plan',%s,%s)""",
                (
                    uuid4(),
                    r.organization_id,
                    r.task_id,
                    task["requester_id"],
                    str(plan_id),
                    uuid4(),
                ),
            )
            if self.hook:
                await self.hook("before_t2_commit")
            await self.session.check()
        if self.hook:
            await self.hook("after_t2_commit")
        return {
            "plan_id": str(plan_id),
            "approval_id": str(approval_id),
            "outcome": "awaiting_approval",
        }

    async def reject(self, r: RunRequest, code: str) -> None:
        await self.session.check()
        async with await open_async(self.settings) as db:
            await db.execute(
                """UPDATE business.business_tasks t SET state='failed',failure_code=%s,
            version=version+1,updated_at=clock_timestamp() WHERE id=%s AND organization_id=%s
            AND shop_id=%s AND state IN ('queued','analyzing')
            AND EXISTS(SELECT 1 FROM business.jobs j
            WHERE j.id=%s AND j.task_id=t.id AND j.status='running' AND j.lease_owner=%s)""",
                (code, r.task_id, r.organization_id, r.shop_id, r.job_id, r.owner),
            )
