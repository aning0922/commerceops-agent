"""P204可信报告引用、说明cache与子任务事务；不从GET发模型。"""

import json
from dataclasses import asdict
from decimal import Decimal
from typing import Any, get_args
from uuid import UUID, uuid4

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from commerceops.application.commerce.analysis_task import TrustedReadIdentity
from commerceops.application.commerce.explanation_task import (
    EXPLANATION_KIND,
    EXPLANATION_WORKFLOW,
    Evidence,
    ExplanationTaskRequest,
    StoredExplanation,
    explanation_body_hash,
    logical_key,
)
from commerceops.application.model_explanation.contracts import (
    ErrorCode,
    ExplanationLine,
    ExplanationResult,
    ModelReply,
    ReferenceIds,
    Usage,
)
from commerceops.application.model_explanation.service import ModelExplanationService
from commerceops.application.runner import RunRequest
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.inventory_repository import (
    AnalysisUnsafe,
    ReadFailure,
    _authorize,
    _stored,
)
from commerceops.infrastructure.repository import TaskRepository, TaskScope
from commerceops.infrastructure.worker_lock import WorkerSession, open_async


def payload(value: ExplanationResult) -> dict[str, Any]:
    result = asdict(value)
    result["lines"] = list(result["lines"])
    reply = result["metadata"]
    reply["content"] = None
    if reply["cost_estimate"] is not None:
        cost = reply["cost_estimate"]
        if not isinstance(cost, Decimal) or not cost.is_finite() or cost < 0:
            raise AnalysisUnsafe("EXPLANATION_COST_INVALID")
        reply["cost_estimate"] = format(cost, "f")  # 费用不是库存Money(20,6)。
    return result


def decode(value: dict[str, Any]) -> ExplanationResult:
    meta = dict(value["metadata"])
    if meta["cost_estimate"] is not None:
        meta["cost_estimate"] = Decimal(meta["cost_estimate"])
    if meta["usage"] is not None:
        meta["usage"] = Usage(**meta["usage"])
    refs = ReferenceIds(**value["reference_ids"]) if value["reference_ids"] else None
    lines = tuple(
        ExplanationLine(
            **{
                **line,
                "reference_ids": ReferenceIds(**line["reference_ids"])
                if line["reference_ids"] is not None
                else None,
            }
        )
        for line in value["lines"]
    )
    return ExplanationResult(
        value["facts_hash"],
        value["narrative_mode"],
        value["binding_mode"],
        value["summary"],
        lines,
        refs,
        ModelReply(**meta),
    )


def validated_row(
    row: dict[str, Any], req: ExplanationTaskRequest, org: UUID, shop: UUID
) -> ExplanationResult:
    expected = {
        "organization_id": org,
        "shop_id": shop,
        "parent_task_id": req.parent_task_id,
        "report_id": req.report_id,
        "snapshot_id": req.snapshot_id,
        "logical_key": req.logical_key,
        "body_hash": req.body_hash,
        "facts_hash": req.facts_hash,
    }
    if any(row[k] != v for k, v in expected.items()):
        raise AnalysisUnsafe("EXPLANATION_RESULT_INVALID")
    body = row["result"]
    if (
        body["metadata"]["content"] is not None
        or facts_hash(body) != row["result_hash"]
        or canonical_bytes(body).decode() != row["canonical_result"]
    ):
        raise AnalysisUnsafe("EXPLANATION_RESULT_INVALID")
    result = decode(body)
    if canonical_bytes(payload(result)) != canonical_bytes(body):
        raise AnalysisUnsafe("EXPLANATION_RESULT_INVALID")
    return result


def trusted_parent(
    db: Any, identity: TrustedReadIdentity, parent: UUID
) -> tuple[dict[str, Any], dict[str, Any]]:
    _authorize(db, identity)
    task = db.execute(
        """SELECT * FROM business.business_tasks WHERE id=%s AND organization_id=%s
        AND shop_id=%s AND requester_id=%s AND kind='inventory_analysis_only'
        AND workflow_version='p203-inventory-analysis-v1'""",
        (parent, identity.organization_id, identity.shop_id, identity.principal_id),
    ).fetchone()
    if task is None:
        raise ReadFailure("TASK_NOT_FOUND", 404)
    if task["state"] != "completed":
        raise ReadFailure("REPORT_NOT_READY", 409)
    row = db.execute(
        """SELECT a.*,s.content_hash,s.content AS snapshot_content,s.window_start,s.window_end
        FROM business.analysis_reports a
            JOIN business.commerce_snapshots s ON s.id=a.snapshot_id
        AND s.task_id=a.task_id AND s.organization_id=a.organization_id AND s.shop_id=a.shop_id
        WHERE a.task_id=%s""",
        (parent,),
    ).fetchone()
    if row is None:
        raise ReadFailure("REPORT_NOT_READY", 409)
    _stored(row, task["normalized_request"])
    return task, row


def create_explanation_task(
    settings: DatabaseSettings, identity: TrustedReadIdentity, parent: UUID, mode: Evidence
) -> tuple[UUID, UUID]:
    if mode not in ("template", "offline_stub", "actual_provider", "local_fault"):
        raise ValueError("EXPLANATION_MODE_INVALID")
    with connect(settings) as db:
        task, report = trusted_parent(db, identity, parent)
        body = explanation_body_hash(_stored(report, task["normalized_request"]).report)
        key = logical_key(
            identity.organization_id,
            identity.shop_id,
            identity.principal_id,
            parent,
            report["id"],
            report["facts_hash"],
            body,
            mode,
        )
        child = uuid4()
        req = ExplanationTaskRequest(
            parent_task_id=parent,
            snapshot_id=report["snapshot_id"],
            report_id=report["id"],
            facts_hash=report["facts_hash"],
            identity_id=identity.identity_id,
            auth_version=identity.auth_version,
            evidence_mode=mode,
            body_hash=body,
            logical_key=key,
        )
        db.execute(
            """INSERT INTO business.business_tasks
            (id,organization_id,shop_id,conversation_id,requester_id,kind,normalized_request,workflow_version,thread_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                child,
                identity.organization_id,
                identity.shop_id,
                task["conversation_id"],
                identity.principal_id,
                EXPLANATION_KIND,
                Jsonb(req.model_dump(mode="json")),
                EXPLANATION_WORKFLOW,
                str(child),
            ),
        )
        db.execute(
            """INSERT INTO business.explanation_links
            (child_task_id,organization_id,shop_id,parent_task_id,snapshot_id,report_id,requester_id,
             identity_id,auth_version,logical_key,body_hash,facts_hash,evidence_mode)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                child,
                identity.organization_id,
                identity.shop_id,
                parent,
                req.snapshot_id,
                req.report_id,
                identity.principal_id,
                req.identity_id,
                req.auth_version,
                key,
                body,
                req.facts_hash,
                mode,
            ),
        )
        job = TaskRepository(db, TaskScope(identity.organization_id, identity.shop_id)).enqueue(
            child, "analyze", f"p204:{child}", f"task:{child}"
        )
        return child, job


class ExplanationStore:
    def __init__(self, settings: DatabaseSettings, session: WorkerSession):
        if settings != session.settings:
            raise ValueError("WORKER_SETTINGS_MISMATCH")
        self.settings, self.session = settings, session

    async def guard(
        self, db: AsyncConnection[dict[str, Any]], r: RunRequest, *, authorize: bool = True
    ) -> tuple[dict[str, Any], ExplanationTaskRequest, Any]:
        await self.session.check()
        if (
            r.owner != self.session.owner
            or r.thread_id != str(r.task_id)
            or r.workflow_version != EXPLANATION_WORKFLOW
        ):
            raise AnalysisUnsafe("EXPLANATION_OWNER_VERSION_INVALID")
        cur = await db.execute(
            """SELECT t.*,l.parent_task_id,l.report_id,l.snapshot_id,l.identity_id,
            l.auth_version,l.logical_key,l.body_hash,l.facts_hash,l.evidence_mode
            FROM business.jobs j JOIN business.business_tasks t ON t.id=j.task_id
            JOIN business.explanation_links l ON l.child_task_id=t.id
            WHERE j.id=%s AND j.status='running' AND j.lease_owner=%s AND t.id=%s
            AND t.organization_id=%s AND t.shop_id=%s AND t.kind=%s AND t.workflow_version=%s
            FOR UPDATE OF j,t""",
            (
                r.job_id,
                r.owner,
                r.task_id,
                r.organization_id,
                r.shop_id,
                EXPLANATION_KIND,
                EXPLANATION_WORKFLOW,
            ),
        )
        task = await cur.fetchone()
        if task is None:
            raise AnalysisUnsafe("EXPLANATION_TASK_JOB_INVALID")
        req = ExplanationTaskRequest.model_validate_json(json.dumps(task["normalized_request"]))
        for field in (
            "parent_task_id",
            "report_id",
            "snapshot_id",
            "identity_id",
            "auth_version",
            "logical_key",
            "body_hash",
            "facts_hash",
            "evidence_mode",
        ):
            if task[field] != getattr(req, field):
                raise AnalysisUnsafe("EXPLANATION_LINK_INVALID")
        if authorize:
            decision = await db.execute(
                "SELECT business.lock_inventory_permission(%s,%s,%s,%s,%s) AS allowed",
                (
                    task["requester_id"],
                    r.organization_id,
                    r.shop_id,
                    req.identity_id,
                    req.auth_version,
                ),
            )
            allowed = await decision.fetchone()
            if not allowed or not allowed["allowed"]:
                raise AnalysisUnsafe("EXPLANATION_PERMISSION_INVALID")
        cur = await db.execute(
            """SELECT a.*,s.content_hash,s.content AS snapshot_content,
            s.window_start,s.window_end,p.normalized_request AS parent_request
            FROM business.analysis_reports a
            JOIN business.commerce_snapshots s ON s.id=a.snapshot_id
            AND s.task_id=a.task_id JOIN business.business_tasks p ON p.id=a.task_id
            WHERE a.id=%s AND a.snapshot_id=%s AND a.task_id=%s AND a.organization_id=%s
            AND a.shop_id=%s AND p.requester_id=%s AND p.state='completed'
            AND a.facts_hash=%s""",
            (
                req.report_id,
                req.snapshot_id,
                req.parent_task_id,
                r.organization_id,
                r.shop_id,
                task["requester_id"],
                req.facts_hash,
            ),
        )
        parent = await cur.fetchone()
        if parent is None:
            raise AnalysisUnsafe("EXPLANATION_PARENT_INVALID")
        report = _stored(parent, parent["parent_request"]).report
        expected_key = logical_key(
            r.organization_id,
            r.shop_id,
            task["requester_id"],
            req.parent_task_id,
            req.report_id,
            req.facts_hash,
            req.body_hash,
            req.evidence_mode,
        )
        if (
            req.logical_key != expected_key
            or report.source.provenance.source_kind != "mock"
            or explanation_body_hash(report) != req.body_hash
        ):
            raise AnalysisUnsafe("EXPLANATION_BODY_INVALID")
        return task, req, report

    async def load(
        self, r: RunRequest, *, authorize: bool = True
    ) -> tuple[dict[str, Any], ExplanationTaskRequest, Any]:
        async with await open_async(self.settings) as db, db.transaction():
            return await self.guard(db, r, authorize=authorize)

    async def existing(self, r: RunRequest) -> StoredExplanation | None:
        async with await open_async(self.settings) as db, db.transaction():
            task, req, report = await self.guard(db, r, authorize=False)
            cur = await db.execute(
                """SELECT e.* FROM business.explanation_task_results x
                JOIN business.model_explanations e ON e.id=x.result_id WHERE x.child_task_id=%s""",
                (r.task_id,),
            )
            row = await cur.fetchone()
            if row is None:
                if task["state"] == "completed":
                    raise AnalysisUnsafe("EXPLANATION_RESULT_MISSING")
                return None
            if row["logical_key"] != req.logical_key or row["facts_hash"] != req.facts_hash:
                raise AnalysisUnsafe("EXPLANATION_RESULT_INVALID")
            result = validated_row(row, req, r.organization_id, r.shop_id)
            await self.verify(result, report, req)
            return StoredExplanation(row["id"], r.task_id, req.logical_key, result)

    async def mark(self, r: RunRequest, state: str, code: str | None = None) -> None:
        async with await open_async(self.settings) as db, db.transaction():
            task, _, _ = await self.guard(db, r, authorize=state == "analyzing")
            if task["state"] == "completed":
                return
            await db.execute(
                """UPDATE business.business_tasks SET state=%s,failure_code=%s,
                version=version+1,updated_at=clock_timestamp() WHERE id=%s""",
                (state, code, r.task_id),
            )

    @staticmethod
    async def verify(result: ExplanationResult, report: Any, req: ExplanationTaskRequest) -> None:
        meta = result.metadata
        if req.facts_hash != report.facts_hash or req.body_hash != explanation_body_hash(report):
            raise AnalysisUnsafe("EXPLANATION_BODY_INVALID")
        if result.narrative_mode == "model_selected" and (
            meta.error_code is not None
            or meta.evidence_mode == "not_used"
            or meta.provider != "deepseek"
            or meta.requested_model != "deepseek-flash"
            or meta.returned_model != "deepseek-flash"
            or meta.usage is None
            or meta.request_id is None
            or meta.cost_estimate is None
            or meta.pricing_version != req.pricing_version
            or meta.stop_required
        ):
            raise AnalysisUnsafe("EXPLANATION_METADATA_INVALID")
        if (
            result.narrative_mode not in ("template", "model_selected")
            or meta.evidence_mode
            not in (
                "not_used",
                "actual_provider" if req.evidence_mode == "actual_provider" else "offline_stub",
            )
            or (meta.error_code is not None and meta.error_code not in get_args(ErrorCode))
            or meta.prompt_version != req.prompt_version
            or meta.pricing_version not in (None, "ds-v41-peak-20261010")
            or type(meta.stop_required) is not bool
            or (
                meta.latency_ms is not None
                and (type(meta.latency_ms) is not int or meta.latency_ms < 0)
            )
            or (
                meta.cost_estimate is not None
                and (
                    not isinstance(meta.cost_estimate, Decimal)
                    or not meta.cost_estimate.is_finite()
                    or meta.cost_estimate < 0
                )
            )
        ):
            raise AnalysisUnsafe("EXPLANATION_METADATA_INVALID")
        if meta.request_id is not None:
            UUID(meta.request_id)
        if meta.usage is not None and (
            any(
                type(n) is not int or n < 0
                for n in (
                    meta.usage.input_tokens,
                    meta.usage.output_tokens,
                    meta.usage.total_tokens,
                )
            )
            or meta.usage.input_tokens + meta.usage.output_tokens != meta.usage.total_tokens
        ):
            raise AnalysisUnsafe("EXPLANATION_METADATA_INVALID")
        refs = ReferenceIds(str(req.snapshot_id), str(req.report_id))
        expected = await ModelExplanationService().explain(report, reference_ids=refs)
        if (
            result.facts_hash != req.facts_hash
            or result.reference_ids != refs
            or result.summary != expected.summary
            or result.binding_mode != "caller_references"
            or len(result.lines) != len(expected.lines)
            or {line.sku_key: line for line in result.lines}
            != {line.sku_key: line for line in expected.lines}
            or len({line.sku_key for line in result.lines}) != len(result.lines)
            or result.metadata.content is not None
            or result.metadata.provider not in (None, "deepseek")
            or result.metadata.requested_model not in (None, "deepseek-flash")
            or result.metadata.returned_model not in (None, "deepseek-flash")
        ):
            raise AnalysisUnsafe("EXPLANATION_RESULT_INVALID")

    async def save(self, r: RunRequest, result: ExplanationResult) -> StoredExplanation:
        async with await open_async(self.settings) as db, db.transaction():
            task, req, report = await self.guard(db, r)
            await self.verify(result, report, req)
            if task["state"] not in ("analyzing", "completed"):
                raise AnalysisUnsafe("EXPLANATION_STATE_INVALID")
            cur = await db.execute(
                "SELECT * FROM business.model_explanations WHERE logical_key=%s", (req.logical_key,)
            )
            old = await cur.fetchone()
            if old:
                stored = validated_row(old, req, r.organization_id, r.shop_id)
                await self.verify(stored, report, req)
                result_id = old["id"]
                result = stored
            else:
                result_id = uuid4()
                body = payload(result)
                canonical = canonical_bytes(body).decode()
                await db.execute(
                    """INSERT INTO business.model_explanations
                    (id,organization_id,shop_id,child_task_id,parent_task_id,report_id,snapshot_id,
                     logical_key,facts_hash,body_hash,result,canonical_result,result_hash)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        result_id,
                        r.organization_id,
                        r.shop_id,
                        r.task_id,
                        req.parent_task_id,
                        req.report_id,
                        req.snapshot_id,
                        req.logical_key,
                        req.facts_hash,
                        req.body_hash,
                        Jsonb(body),
                        canonical,
                        facts_hash(body),
                    ),
                )
            await db.execute(
                """INSERT INTO business.explanation_task_results(child_task_id,result_id)
                VALUES (%s,%s) ON CONFLICT(child_task_id) DO NOTHING""",
                (r.task_id, result_id),
            )
            receipt = await db.execute(
                "SELECT result_id FROM business.explanation_task_results WHERE child_task_id=%s",
                (r.task_id,),
            )
            linked = await receipt.fetchone()
            if linked is None or linked["result_id"] != result_id:
                raise AnalysisUnsafe("EXPLANATION_RECEIPT_INVALID")
            await db.execute(
                """UPDATE business.business_tasks SET state='completed' ,failure_code=NULL,
                version=version+1,updated_at=clock_timestamp() WHERE id=%s""",
                (r.task_id,),
            )
            await self.session.check()
        return StoredExplanation(result_id, r.task_id, req.logical_key, result)
