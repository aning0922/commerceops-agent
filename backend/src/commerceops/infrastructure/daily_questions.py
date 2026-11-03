"""冻结报告追问的受理/同Worker执行/持久回执；无模型、commerce或发送。"""

import json
from typing import Any
from uuid import UUID, uuid4

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from commerceops.application.daily.questions import (
    QUESTION_WORKFLOW,
    QuestionInput,
    QuestionResult,
    QuestionTaskRequest,
    answer,
)
from commerceops.application.daily.source import WORKFLOW, DailyTaskRequest, DailyUnsafe
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.application.runner import RunRequest, RunResult
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure.daily_store import RESULT_SQL, StoredDaily, verified_row
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.repository import TaskRepository, TaskScope
from commerceops.infrastructure.web_sessions import actor_guard, role_scope
from commerceops.infrastructure.worker_lock import WorkerSession, open_async


def report_for_actor(
    db: Any, actor: WebActor, task_id: UUID
) -> tuple[dict[str, Any], DailyTaskRequest, StoredDaily]:
    actor_guard(db, actor)
    task = db.execute(
        """SELECT * FROM business.business_tasks WHERE id=%s AND organization_id=%s
    AND requester_id=%s AND kind='daily_report' AND workflow_version=%s FOR SHARE""",
        (task_id, actor.organization_id, actor.principal_id, WORKFLOW),
    ).fetchone()
    if task is None or not role_scope(db, actor, task["shop_id"], "operator"):
        raise WebFailure("RESOURCE_NOT_FOUND", 404)
    req = DailyTaskRequest.model_validate_json(json.dumps(task["normalized_request"]))
    row = db.execute(RESULT_SQL, (task_id, actor.organization_id, task["shop_id"])).fetchone()
    if row is None:
        raise WebFailure("NOT_READY", 409)
    return task, req, verified_row(row, req)


def bound_question(stored: StoredDaily, value: QuestionInput) -> None:
    if (value.report_id, value.snapshot_id, value.content_hash, value.facts_hash) != (
        stored.report_id,
        stored.snapshot.snapshot_id,
        stored.report.content_hash,
        stored.report.facts_hash,
    ):
        raise WebFailure("PLAN_CHANGED", 409)
    # 受理时拒绝不存在的finding/不可用metric，不留下永远无法完成的任务。
    try:
        answer(stored.report_id, stored.report, value.question)
    except ValueError:
        raise WebFailure("INVALID_REQUEST", 422) from None


def create_question(
    settings: DatabaseSettings, actor: WebActor, parent_id: UUID, value: QuestionInput
) -> UUID:
    digest = facts_hash(value.model_dump(mode="json"))
    with connect(settings) as db:
        parent, _, stored = report_for_actor(db, actor, parent_id)
        old = db.execute(
            r"""SELECT id,normalized_request FROM business.business_tasks WHERE organization_id=%s
AND requester_id=%s AND kind='daily_question' AND
normalized_request#>>'{input,request_key}'=%s
FOR UPDATE""",
            (actor.organization_id, actor.principal_id, str(value.request_key)),
        ).fetchone()
        if old is not None:
            if old["normalized_request"]["request_hash"] != digest or (
                old["normalized_request"]["parent_task_id"] != str(parent_id)
            ):
                raise WebFailure("IDEMPOTENCY_CONFLICT", 409)
            return UUID(str(old["id"]))
        bound_question(stored, value)
        request = QuestionTaskRequest(
            schema_version="p6-daily-question-task-v1",
            parent_task_id=parent_id,
            input=value,
            request_hash=digest,
            requester_auth_version=actor.auth_version,
        )
        task_id = uuid4()
        row = db.execute(
            r"""INSERT INTO business.business_tasks(id,organization_id,shop_id,conversation_id,
requester_id,kind,normalized_request,workflow_version,thread_id)
VALUES(%s,%s,%s,%s,%s,'daily_question',%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id""",
            (
                task_id,
                actor.organization_id,
                parent["shop_id"],
                parent["conversation_id"],
                actor.principal_id,
                Jsonb(request.model_dump(mode="json")),
                QUESTION_WORKFLOW,
                str(task_id),
            ),
        ).fetchone()
        if row is None:
            old = db.execute(
                r"""
SELECT id,normalized_request FROM business.business_tasks WHERE organization_id=%s
AND requester_id=%s AND kind='daily_question' AND
normalized_request#>>'{input,request_key}'=%s""",
                (actor.organization_id, actor.principal_id, str(value.request_key)),
            ).fetchone()
            if old is None or old["normalized_request"] != request.model_dump(mode="json"):
                raise WebFailure("IDEMPOTENCY_CONFLICT", 409)
            return UUID(str(old["id"]))
        TaskRepository(db, TaskScope(actor.organization_id, parent["shop_id"])).enqueue(
            task_id, "analyze", f"p6-question:{task_id}:analyze", f"task:{task_id}"
        )
        db.execute(
            r"""INSERT INTO business.audit_events(id,organization_id,task_id,actor_id,source,action,
entity_type,entity_id,after_state,trace_id)
VALUES(%s,%s,%s,%s,'daily','question_accepted',
'business_task',%s,%s,%s)""",
            (
                uuid4(),
                actor.organization_id,
                task_id,
                actor.principal_id,
                task_id,
                Jsonb({"parent_task_id": str(parent_id), "report_id": str(stored.report_id)}),
                uuid4(),
            ),
        )
        return task_id


def verified_question(
    row: dict[str, Any], stored: StoredDaily, request: QuestionTaskRequest
) -> QuestionResult:
    result = QuestionResult.model_validate_json(row["canonical_result"])
    expected = QuestionResult(
        answer=answer(stored.report_id, stored.report, request.input.question)[0],
        citations=answer(stored.report_id, stored.report, request.input.question)[1],
    )
    if (
        result != expected
        or row["result"] != result.model_dump(mode="json")
        or (
            canonical_bytes(result.model_dump(mode="json")).decode() != row["canonical_result"]
            or facts_hash(result.model_dump(mode="json")) != row["result_hash"]
            or (row["report_id"], row["snapshot_id"], row["content_hash"], row["facts_hash"])
            != (
                stored.report_id,
                stored.report.snapshot_id,
                stored.report.content_hash,
                stored.report.facts_hash,
            )
        )
    ):
        raise DailyUnsafe("DAILY_STORAGE_FAILURE")
    return result


class DailyQuestionStore:
    def __init__(self, settings: DatabaseSettings, session: WorkerSession):
        self.settings, self.session = settings, session

    async def _load(
        self, db: AsyncConnection[dict[str, Any]], run: RunRequest
    ) -> tuple[dict[str, Any], QuestionTaskRequest, StoredDaily]:
        if (
            run.owner != self.session.owner
            or run.workflow_version != QUESTION_WORKFLOW
            or (
                run.kind not in ("analyze", "recover")
                or run.organization_id != self.session.organization
            )
        ):
            raise DailyUnsafe()
        cursor = await db.execute(
            r"""SELECT t.* FROM business.business_tasks t JOIN business.jobs j ON j.task_id=t.id
AND j.organization_id=t.organization_id AND j.shop_id=t.shop_id WHERE t.id=%s
AND t.organization_id=%s AND t.shop_id=%s AND t.workflow_version=%s AND
t.kind='daily_question'
AND t.thread_id=%s AND j.id=%s AND j.lease_owner=%s AND j.status='running'
AND j.kind=%s AND j.payload_ref=%s FOR UPDATE OF t""",
            (
                run.task_id,
                run.organization_id,
                run.shop_id,
                QUESTION_WORKFLOW,
                run.thread_id,
                run.job_id,
                run.owner,
                run.kind,
                run.payload_ref,
            ),
        )
        task = await cursor.fetchone()
        if task is None or run.payload_ref != f"task:{run.task_id}":
            raise DailyUnsafe()
        request = QuestionTaskRequest.model_validate_json(json.dumps(task["normalized_request"]))
        parent_cursor = await db.execute(
            r"""SELECT * FROM business.business_tasks WHERE id=%s AND organization_id=%s
AND shop_id=%s AND requester_id=%s AND kind='daily_report' AND workflow_version=%s
FOR SHARE""",
            (
                request.parent_task_id,
                run.organization_id,
                run.shop_id,
                task["requester_id"],
                WORKFLOW,
            ),
        )
        parent = await parent_cursor.fetchone()
        if parent is None or parent["conversation_id"] != task["conversation_id"]:
            raise DailyUnsafe()
        source = DailyTaskRequest.model_validate_json(json.dumps(parent["normalized_request"]))
        row = await (
            await db.execute(RESULT_SQL, (request.parent_task_id, run.organization_id, run.shop_id))
        ).fetchone()
        if row is None:
            raise DailyUnsafe()
        stored = verified_row(row, source)
        bound_question(stored, request.input)
        return task, request, stored

    async def run(self, run: RunRequest) -> RunResult:
        await self.session.check()
        try:
            async with await open_async(self.settings) as db, db.transaction():
                await db.execute("SET LOCAL statement_timeout='18000ms'")
                task, request, stored = await self._load(db, run)
                old = await (
                    await db.execute(
                        "SELECT * FROM business.p6_daily_questions WHERE task_id=%s", (run.task_id,)
                    )
                ).fetchone()
                if old is not None:
                    verified_question(old, stored, request)
                    return RunResult()
                permitted = await (
                    await db.execute(
                        "SELECT business.p6_current_permission(%s,%s,%s,%s) AS allowed",
                        (
                            task["requester_id"],
                            run.organization_id,
                            run.shop_id,
                            request.requester_auth_version,
                        ),
                    )
                ).fetchone()
                if not permitted or not permitted["allowed"]:
                    raise DailyUnsafe("DAILY_PERMISSION_INVALID")
                if task["state"] not in ("queued", "analyzing"):
                    raise DailyUnsafe()
                await db.execute(
                    r"""UPDATE business.business_tasks SET
state='analyzing',version=version+1,updated_at=clock_timestamp() WHERE id=%s""",
                    (run.task_id,),
                )
                text, citations = answer(stored.report_id, stored.report, request.input.question)
                result = QuestionResult(answer=text, citations=citations)
                body = result.model_dump(mode="json")
                await db.execute(
                    r"""
INSERT INTO
business.p6_daily_questions(task_id,organization_id,shop_id,parent_task_id,
report_id,snapshot_id,content_hash,facts_hash,result,canonical_result,result_hash)
VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        run.task_id,
                        run.organization_id,
                        run.shop_id,
                        request.parent_task_id,
                        stored.report_id,
                        stored.report.snapshot_id,
                        stored.report.content_hash,
                        stored.report.facts_hash,
                        Jsonb(body),
                        canonical_bytes(body).decode(),
                        facts_hash(body),
                    ),
                )
                await db.execute(
                    r"""
UPDATE business.business_tasks SET
state='completed',failure_code=NULL,version=version+1,updated_at=clock_timestamp()
WHERE id=%s""",
                    (run.task_id,),
                )
                await self.session.check()
            return RunResult()
        except (DailyUnsafe, WebFailure, ValueError) as error:
            code = error.code if isinstance(error, DailyUnsafe) else "DAILY_WORKFLOW_UNSAFE"
            async with await open_async(self.settings) as db:
                await db.execute(
                    r"""
UPDATE business.business_tasks SET state='needs_attention',failure_code=%s,
version=version+1,updated_at=clock_timestamp() WHERE id=%s AND organization_id=%s AND
shop_id=%s
AND kind='daily_question' AND state IN ('queued','analyzing')""",
                    (code, run.task_id, run.organization_id, run.shop_id),
                )
            return RunResult()
