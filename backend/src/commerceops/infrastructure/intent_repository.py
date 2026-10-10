"""P204固定routing任务身份、候选与receipt；不生成业务批准/执行。"""

import json
from typing import Any, cast
from uuid import UUID, uuid4

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from commerceops.application.commerce.analysis_task import TrustedReadIdentity
from commerceops.application.commerce.explanation_task import Evidence
from commerceops.application.commerce.intent_task import (
    INTENT_KIND,
    INTENT_WORKFLOW,
    IntentTaskRequest,
    routing_body_hash,
    routing_input_hash,
    routing_key,
)
from commerceops.application.commerce.inventory_routing import (
    GuardedRouter,
    ModelRoute,
    RoutingDecision,
    RoutingInput,
)
from commerceops.application.model_explanation.contracts import ModelReply
from commerceops.application.runner import RunRequest
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe, ReadFailure, _authorize
from commerceops.infrastructure.repository import TaskRepository, TaskScope
from commerceops.infrastructure.worker_lock import WorkerSession, open_async


class BoundProposal:
    def __init__(self, proposal: ModelRoute):
        self.proposal = proposal

    async def route(self, text: str) -> ModelRoute:
        return self.proposal


def request_valid(req: IntentTaskRequest, org: UUID, shop: UUID, owner: UUID) -> None:
    if (
        routing_body_hash(req.input.text) != req.body_hash
        or routing_input_hash(req.input) != req.facts_hash
        or routing_key(
            org, shop, owner, req.identity_id, req.auth_version, req.input, req.evidence_mode
        )
        != req.logical_key
    ):
        raise AnalysisUnsafe("INTENT_REQUEST_INVALID")


def create_intent_task(
    settings: DatabaseSettings, identity: TrustedReadIdentity, request: RoutingInput, mode: Evidence
) -> tuple[UUID, UUID]:
    with connect(settings) as db:
        _authorize(db, identity)
        context = request.context_task_id
        if (
            context is not None
            and not db.execute(
                """SELECT id FROM business.business_tasks WHERE id=%s AND organization_id=%s
            AND shop_id=%s AND requester_id=%s AND kind='inventory_analysis_only'
            AND workflow_version='p203-inventory-analysis-v1'""",
                (context, identity.organization_id, identity.shop_id, identity.principal_id),
            ).fetchone()
        ):
            raise ReadFailure("TASK_NOT_FOUND", 404)
        conversation = db.execute(
            """SELECT id FROM business.conversations WHERE organization_id=%s
            AND actor_id=%s ORDER BY id LIMIT 1""",
            (identity.organization_id, identity.principal_id),
        ).fetchone()
        if conversation is None:
            raise ReadFailure("CONVERSATION_NOT_READY", 409)
        task = uuid4()
        req = IntentTaskRequest(
            input=request,
            identity_id=identity.identity_id,
            auth_version=identity.auth_version,
            evidence_mode=mode,
            facts_hash=routing_input_hash(request),
            body_hash=routing_body_hash(request.text),
            logical_key=routing_key(
                identity.organization_id,
                identity.shop_id,
                identity.principal_id,
                identity.identity_id,
                identity.auth_version,
                request,
                mode,
            ),
        )
        db.execute(
            """INSERT INTO business.business_tasks
            (id,organization_id,shop_id,conversation_id,requester_id,kind,normalized_request,workflow_version,thread_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                task,
                identity.organization_id,
                identity.shop_id,
                conversation["id"],
                identity.principal_id,
                INTENT_KIND,
                Jsonb(req.model_dump(mode="json")),
                INTENT_WORKFLOW,
                str(task),
            ),
        )
        db.execute(
            """INSERT INTO business.inventory_intent_requests
            (task_id,organization_id,shop_id,requester_id,identity_id,auth_version,logical_key,body_hash,input_hash,evidence_mode)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                task,
                identity.organization_id,
                identity.shop_id,
                identity.principal_id,
                identity.identity_id,
                identity.auth_version,
                req.logical_key,
                req.body_hash,
                req.facts_hash,
                mode,
            ),
        )
        job = TaskRepository(db, TaskScope(identity.organization_id, identity.shop_id)).enqueue(
            task, "analyze", f"p204-route:{task}", f"task:{task}"
        )
        return task, job


class IntentStore:
    def __init__(self, settings: DatabaseSettings, session: WorkerSession):
        if settings != session.settings:
            raise ValueError("WORKER_SETTINGS_MISMATCH")
        self.settings, self.session = settings, session

    async def guard(
        self, db: AsyncConnection[dict[str, Any]], r: RunRequest, *, authorize: bool = True
    ) -> tuple[dict[str, Any], IntentTaskRequest, RoutingInput]:
        await self.session.check()
        if (
            r.owner != self.session.owner
            or r.thread_id != str(r.task_id)
            or r.workflow_version != INTENT_WORKFLOW
        ):
            raise AnalysisUnsafe("INTENT_OWNER_VERSION_INVALID")
        cur = await db.execute(
            """SELECT t.*,i.logical_key,i.body_hash,i.input_hash,i.identity_id,
            i.auth_version,i.evidence_mode FROM business.jobs j
            JOIN business.business_tasks t ON t.id=j.task_id
            JOIN business.inventory_intent_requests i ON i.task_id=t.id
            WHERE j.id=%s AND j.status='running' AND j.lease_owner=%s AND t.id=%s
            AND t.organization_id=%s AND t.shop_id=%s AND t.kind=%s AND t.workflow_version=%s
            FOR UPDATE OF j,t""",
            (
                r.job_id,
                r.owner,
                r.task_id,
                r.organization_id,
                r.shop_id,
                INTENT_KIND,
                INTENT_WORKFLOW,
            ),
        )
        task = await cur.fetchone()
        if task is None:
            raise AnalysisUnsafe("INTENT_TASK_JOB_INVALID")
        req = IntentTaskRequest.model_validate_json(json.dumps(task["normalized_request"]))
        request_valid(req, r.organization_id, r.shop_id, task["requester_id"])
        for field in ("logical_key", "body_hash", "identity_id", "auth_version", "evidence_mode"):
            if task[field] != getattr(req, field):
                raise AnalysisUnsafe("INTENT_LINK_INVALID")
        if task["input_hash"] != req.facts_hash:
            raise AnalysisUnsafe("INTENT_LINK_INVALID")
        if authorize:
            cur = await db.execute(
                "SELECT business.lock_inventory_permission(%s,%s,%s,%s,%s) AS allowed",
                (
                    task["requester_id"],
                    r.organization_id,
                    r.shop_id,
                    req.identity_id,
                    req.auth_version,
                ),
            )
            allowed = await cur.fetchone()
            if not allowed or not allowed["allowed"]:
                raise AnalysisUnsafe("INTENT_PERMISSION_INVALID")
        if req.input.context_task_id is not None:
            cur = await db.execute(
                """SELECT id FROM business.business_tasks WHERE id=%s AND organization_id=%s
                AND shop_id=%s AND requester_id=%s AND kind='inventory_analysis_only'""",
                (req.input.context_task_id, r.organization_id, r.shop_id, task["requester_id"]),
            )
            if await cur.fetchone() is None:
                raise AnalysisUnsafe("INTENT_CONTEXT_INVALID")
        return task, req, req.input

    async def cached(
        self, db: AsyncConnection[dict[str, Any]], req: IntentTaskRequest, r: RunRequest
    ) -> dict[str, Any] | None:
        cur = await db.execute(
            """SELECT * FROM business.inventory_intent_results WHERE logical_key=%s
            ORDER BY created_at,task_id LIMIT 1""",
            (req.logical_key,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        await self.verify(row, req, r.organization_id, r.shop_id)
        return cast(dict[str, Any], row["result"])

    @staticmethod
    async def verify(row: dict[str, Any], req: IntentTaskRequest, org: UUID, shop: UUID) -> None:
        if (
            row["organization_id"] != org
            or row["shop_id"] != shop
            or row["logical_key"] != req.logical_key
            or row["input_hash"] != req.facts_hash
            or row["body_hash"] != req.body_hash
            or canonical_bytes(row["result"]).decode() != row["canonical_result"]
            or facts_hash(row["result"]) != row["result_hash"]
        ):
            raise AnalysisUnsafe("INTENT_RESULT_INVALID")
        value = row["result"]
        if (
            set(value) != {"proposal", "decision", "metadata"}
            or value["metadata"]["content"] is not None
        ):
            raise AnalysisUnsafe("INTENT_RESULT_INVALID")
        proposal = ModelRoute.model_validate_json(json.dumps(value["proposal"]))
        expected = await GuardedRouter(BoundProposal(proposal), allow_actual_routing=True).route(
            req.input
        )
        if expected.model_dump(mode="json") != value["decision"]:
            raise AnalysisUnsafe("INTENT_RESULT_INVALID")
        RoutingDecision.model_validate(value["decision"])
        from commerceops.application.commerce.explanation_read import ExplanationMetadata

        meta = ExplanationMetadata.model_validate(value["metadata"])
        expected_mode = (
            "actual_provider" if req.evidence_mode == "actual_provider" else "offline_stub"
        )
        if (
            meta.prompt_version != req.prompt_version
            or meta.evidence_mode not in ("not_used", expected_mode)
            or proposal.evidence_mode != meta.evidence_mode
        ):
            raise AnalysisUnsafe("INTENT_METADATA_INVALID")
        if (
            meta.usage is not None
            and meta.usage.input_tokens + meta.usage.output_tokens != meta.usage.total_tokens
        ):
            raise AnalysisUnsafe("INTENT_METADATA_INVALID")

    async def existing(self, r: RunRequest) -> dict[str, Any] | None:
        async with await open_async(self.settings) as db, db.transaction():
            task, req, _ = await self.guard(db, r, authorize=False)
            cur = await db.execute(
                "SELECT * FROM business.inventory_intent_results WHERE task_id=%s", (r.task_id,)
            )
            row = await cur.fetchone()
            if row:
                await self.verify(row, req, r.organization_id, r.shop_id)
                return cast(dict[str, Any], row["result"])
            if task["state"] == "completed":
                raise AnalysisUnsafe("INTENT_RESULT_MISSING")
            return None

    async def mark(self, r: RunRequest, state: str, code: str | None = None) -> None:
        async with await open_async(self.settings) as db, db.transaction():
            task, _, _ = await self.guard(db, r, authorize=state == "analyzing")
            if task["state"] != "completed":
                await db.execute(
                    """UPDATE business.business_tasks SET state=%s,failure_code=%s,
                    version=version+1,
                    updated_at=clock_timestamp() WHERE id=%s""",
                    (state, code, r.task_id),
                )

    async def save(self, r: RunRequest, proposal: ModelRoute, reply: ModelReply) -> dict[str, Any]:
        from dataclasses import asdict
        from decimal import Decimal

        async with await open_async(self.settings) as db, db.transaction():
            task, req, _ = await self.guard(db, r)
            if task["state"] != "analyzing":
                raise AnalysisUnsafe("INTENT_STATE_INVALID")
            decision = await GuardedRouter(
                BoundProposal(proposal), allow_actual_routing=True
            ).route(req.input)
            metadata = asdict(reply)
            metadata["content"] = None
            if metadata["cost_estimate"] is not None:
                cost = metadata["cost_estimate"]
                if not isinstance(cost, Decimal) or not cost.is_finite() or cost < 0:
                    raise AnalysisUnsafe("INTENT_COST_INVALID")
                metadata["cost_estimate"] = format(cost, "f")
            result = {
                "proposal": proposal.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "metadata": metadata,
            }
            # 独立task收据可复用同logical cache，但不能引入另一scope。
            old = await self.cached(db, req, r)
            if old is not None:
                result = old
            canonical = canonical_bytes(result).decode()
            await db.execute(
                """INSERT INTO business.inventory_intent_results
                (task_id,organization_id,shop_id,logical_key,body_hash,input_hash,result,canonical_result,result_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    r.task_id,
                    r.organization_id,
                    r.shop_id,
                    req.logical_key,
                    req.body_hash,
                    req.facts_hash,
                    Jsonb(result),
                    canonical,
                    facts_hash(result),
                ),
            )
            await db.execute(
                """UPDATE business.business_tasks SET state='completed',failure_code=NULL,
                version=version+1,
                updated_at=clock_timestamp() WHERE id=%s""",
                (r.task_id,),
            )
            await db.execute(
                """INSERT INTO business.audit_events
                (id,organization_id,task_id,actor_id,source,action,entity_type,entity_id,after_state,trace_id)
                VALUES (%s,%s,%s,%s,'routing','inventory_intent_saved',
                'inventory_intent',%s,%s,%s)""",
                (
                    uuid4(),
                    r.organization_id,
                    r.task_id,
                    task["requester_id"],
                    str(r.task_id),
                    Jsonb(
                        {
                            "intent": result["decision"]["intent"],
                            "evidence_mode": result["decision"]["evidence_mode"],
                            "input_hash": req.facts_hash,
                            "business_task_created": False,
                        }
                    ),
                    uuid4(),
                ),
            )
            await self.session.check()
            return result


async def read_intent(
    settings: DatabaseSettings, identity: TrustedReadIdentity, task_id: UUID
) -> dict[str, Any]:
    try:
        with connect(settings) as db:
            _authorize(db, identity)
            task = db.execute(
                """SELECT * FROM business.business_tasks WHERE id=%s AND organization_id=%s
                AND shop_id=%s AND requester_id=%s AND kind=%s AND workflow_version=%s""",
                (
                    task_id,
                    identity.organization_id,
                    identity.shop_id,
                    identity.principal_id,
                    INTENT_KIND,
                    INTENT_WORKFLOW,
                ),
            ).fetchone()
            if task is None:
                raise ReadFailure("TASK_NOT_FOUND", 404)
            req = IntentTaskRequest.model_validate_json(json.dumps(task["normalized_request"]))
            request_valid(req, identity.organization_id, identity.shop_id, identity.principal_id)
            row = db.execute(
                "SELECT * FROM business.inventory_intent_results WHERE task_id=%s", (task_id,)
            ).fetchone()
            if row:
                await IntentStore.verify(row, req, identity.organization_id, identity.shop_id)
            elif task["state"] == "completed":
                raise AnalysisUnsafe("INTENT_RESULT_MISSING")
            return {
                "schema_version": "p204-route-read-v1",
                "analysis_only": True,
                "execution_available": False,
                "identity_mode": "simulated",
                "task_id": str(task_id),
                "state": task["state"],
                "result": row["result"] if row else None,
            }
    except ReadFailure:
        raise
    except Exception:
        raise ReadFailure("DATABASE_UNAVAILABLE", 503) from None
