"""日报新增HTTP操作；当前会话/owner/operator重验，GET仅查冻结事实。"""

import json
from typing import Any
from uuid import UUID

from commerceops.application.daily.cursors import EvidenceContext, decode_cursor, encode_cursor
from commerceops.application.daily.http_models import (
    AcceptanceRead,
    CapabilityRead,
    CreateDailyInput,
    CreationReceiptRead,
    EvidenceRead,
    QuestionRead,
)
from commerceops.application.daily.questions import (
    QUESTION_WORKFLOW,
    Citation,
    QuestionTaskRequest,
    _safe_evidence,
)
from commerceops.application.daily.read_models import QUESTION_KINDS
from commerceops.application.daily.source import WORKFLOW, DailyTaskRequest, DailyUnsafe
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.infrastructure.daily_questions import (
    create_question,
    report_for_actor,
    verified_question,
)
from commerceops.infrastructure.daily_sources import DailyDeployment
from commerceops.infrastructure.daily_store import SOURCE_SQL, bound_metadata, create_daily_task
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.web_sessions import actor_guard, envelope, role_scope


class DailyOperations:
    def __init__(
        self, settings: DatabaseSettings, files: DailyDeployment | None, cursor_key: bytes
    ):
        self.settings, self.files, self.cursor_key = settings, files, cursor_key

    def creation_receipt(
        self, actor: WebActor, shop_id: UUID, request_key: UUID
    ) -> CreationReceiptRead:
        """只读原日报受理记录；404不证明原POST没有提交，不读当前来源配置。"""
        with connect(self.settings) as db:
            actor_guard(db, actor)
            if not role_scope(db, actor, shop_id, "operator"):
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            task = db.execute(
                """SELECT * FROM business.business_tasks WHERE organization_id=%s
            AND shop_id=%s AND requester_id=%s AND kind='daily_report' AND workflow_version=%s
            AND normalized_request->>'request_key'=%s""",
                (actor.organization_id, shop_id, actor.principal_id, WORKFLOW, str(request_key)),
            ).fetchone()
            if task is None:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            value = DailyTaskRequest.model_validate_json(json.dumps(task["normalized_request"]))
            if (
                value.daily_source.organization_id,
                value.daily_source.shop_id,
                value.request_key,
                value.conversation_id,
            ) != (actor.organization_id, shop_id, request_key, task["conversation_id"]):
                raise DailyUnsafe("DAILY_STORAGE_FAILURE")
            return CreationReceiptRead.model_validate_json(
                json.dumps(
                    envelope(
                        db,
                        receipt={
                            "schema_version": "p6-m3-web-v1",
                            "lookup_status": "accepted",
                            "operation": "daily_report.create",
                            "request_key": request_key,
                            "shop_id": shop_id,
                            "task_id": task["id"],
                            "state": task["state"],
                            "failure_code": task["failure_code"],
                            "request_hash": value.request_hash,
                            "source_config_version": value.daily_source.source_config_version,
                            "business_day": value.business_day.isoformat(),
                        },
                    )
                )
            )

    def question_receipt(
        self, actor: WebActor, shop_id: UUID, parent_id: UUID, report_id: UUID, request_key: UUID
    ) -> CreationReceiptRead:
        """原question key按owner/shop/parent/report隔离；不触发answer或新job。"""
        with connect(self.settings) as db:
            actor_guard(db, actor)
            if not role_scope(db, actor, shop_id, "operator"):
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            task = db.execute(
                """SELECT q.*,r.snapshot_id AS original_snapshot_id,
            r.facts_hash AS original_facts_hash,
            r.report->>'content_hash' AS original_content_hash FROM business.business_tasks q
            JOIN business.business_tasks p ON p.organization_id=q.organization_id
            AND p.shop_id=q.shop_id
            AND p.requester_id=q.requester_id AND p.conversation_id=q.conversation_id
            AND p.id::text=q.normalized_request->>'parent_task_id'
            JOIN business.p6_daily_reports r ON r.task_id=p.id
            AND r.organization_id=p.organization_id
            AND r.shop_id=p.shop_id AND r.id::text=q.normalized_request#>>'{input,report_id}'
            WHERE q.organization_id=%s AND q.shop_id=%s AND q.requester_id=%s
            AND q.kind='daily_question' AND q.workflow_version=%s
            AND q.normalized_request#>>'{input,request_key}'=%s
            AND p.id=%s AND p.kind='daily_report' AND p.workflow_version=%s AND r.id=%s""",
                (
                    actor.organization_id,
                    shop_id,
                    actor.principal_id,
                    QUESTION_WORKFLOW,
                    str(request_key),
                    parent_id,
                    WORKFLOW,
                    report_id,
                ),
            ).fetchone()
            if task is None:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            value = QuestionTaskRequest.model_validate_json(json.dumps(task["normalized_request"]))
            if (
                value.parent_task_id,
                value.input.request_key,
                value.input.report_id,
                value.input.snapshot_id,
                value.input.content_hash,
                value.input.facts_hash,
            ) != (
                parent_id,
                request_key,
                report_id,
                task["original_snapshot_id"],
                task["original_content_hash"],
                task["original_facts_hash"],
            ):
                raise DailyUnsafe("DAILY_STORAGE_FAILURE")
            return CreationReceiptRead.model_validate_json(
                json.dumps(
                    envelope(
                        db,
                        receipt={
                            "schema_version": "p6-m3-web-v1",
                            "lookup_status": "accepted",
                            "operation": "daily_question.create",
                            "request_key": request_key,
                            "shop_id": shop_id,
                            "task_id": task["id"],
                            "state": task["state"],
                            "failure_code": task["failure_code"],
                            "request_hash": value.request_hash,
                            "parent_task_id": parent_id,
                            "report_id": report_id,
                            "snapshot_id": value.input.snapshot_id,
                            "content_hash": value.input.content_hash,
                            "facts_hash": value.input.facts_hash,
                            "question": value.input.question.model_dump(mode="json"),
                        },
                    )
                )
            )

    def capabilities(self, actor: WebActor, shop: UUID) -> CapabilityRead:
        with connect(self.settings) as db:
            actor_guard(db, actor)
            if not role_scope(db, actor, shop, "operator"):
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            source, earliest, metric = None, None, None
            if self.files is not None:
                try:
                    active = self.files.active(actor.organization_id, shop)
                    row = db.execute(
                        SOURCE_SQL, (active.binding_id, actor.organization_id, shop)
                    ).fetchone()
                    metadata = bound_metadata(row, self.files, actor.organization_id, shop)
                    source = {
                        "source_kind": metadata.source_kind,
                        "source_config_version": metadata.source_config_version,
                        "fixture_version": getattr(metadata, "fixture_version", None),
                        "currency": metadata.currency,
                        "timezone": metadata.timezone,
                        "coverage_scope": "controlled_test_dataset",
                    }
                    earliest, metric = metadata.earliest_business_day, metadata.metric_version
                except DailyUnsafe:
                    pass
            return CapabilityRead.model_validate_json(
                json.dumps(
                    envelope(
                        db,
                        capabilities={
                            "schema_version": "p6-m3-web-v1",
                            "shop_id": shop,
                            "enabled": source is not None,
                            "source": source,
                            "earliest_business_day": earliest.isoformat()
                            if earliest is not None
                            else None,
                            "metric_version": metric,
                            "question_kinds": QUESTION_KINDS,
                            "schedule_management_mode": "controlled_cli",
                            "delivery_mode": "fake_only",
                            "model_requests_enabled": False,
                            "external_sender_enabled": False,
                        },
                    )
                )
            )

    def accepted(self, actor: WebActor, task_id: UUID) -> AcceptanceRead:
        with connect(self.settings) as db:
            actor_guard(db, actor)
            task = db.execute(
                r"""SELECT id,shop_id,state FROM business.business_tasks WHERE id=%s
AND organization_id=%s AND requester_id=%s AND kind IN
('daily_report','daily_question')""",
                (task_id, actor.organization_id, actor.principal_id),
            ).fetchone()
            if task is None or not role_scope(db, actor, task["shop_id"], "operator"):
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            return AcceptanceRead.model_validate_json(
                json.dumps(
                    envelope(
                        db,
                        accepted={
                            "schema_version": "p6-m3-web-v1",
                            "task_id": task_id,
                            "state": task["state"],
                        },
                    )
                )
            )

    def create(self, actor: WebActor, body: CreateDailyInput) -> AcceptanceRead:
        if self.files is None:
            raise WebFailure("NOT_READY", 409)
        task = create_daily_task(
            self.settings,
            self.files,
            actor,
            body.shop_id,
            body.request_key,
            body.source_config_version,
            body.business_day,
        )
        return self.accepted(actor, task)

    def _page(
        self, context: EvidenceContext, citations: tuple[Any, ...], cursor: str | None
    ) -> tuple[tuple[Any, ...], str | None]:
        try:
            offset = decode_cursor(self.cursor_key, context, cursor) if cursor is not None else 0
            if offset >= len(citations) and offset != 0:
                raise ValueError
        except ValueError:
            raise WebFailure("INVALID_CURSOR", 409) from None
        end = offset + 50
        return citations[offset:end], encode_cursor(self.cursor_key, context, end) if end < len(
            citations
        ) else None

    def evidence(
        self, actor: WebActor, task_id: UUID, report_id: UUID, cursor: str | None
    ) -> EvidenceRead:
        with connect(self.settings) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            task, _, stored = report_for_actor(db, actor, task_id)
            if report_id != stored.report_id:
                raise WebFailure("PLAN_CHANGED", 409)
            context = EvidenceContext(
                actor_id=actor.principal_id,
                auth_version=actor.auth_version,
                organization_id=actor.organization_id,
                shop_id=task["shop_id"],
                task_id=task_id,
                report_id=report_id,
                snapshot_id=stored.report.snapshot_id,
                content_hash=stored.report.content_hash,
                facts_hash=stored.report.facts_hash,
                question_id=None,
            )
            citations = tuple(_safe_evidence(item) for item in stored.report.evidence)
            page, next_cursor = self._page(context, citations, cursor)
            return EvidenceRead.model_validate_json(
                json.dumps(
                    envelope(
                        db,
                        evidence={
                            "schema_version": "p6-m3-web-v1",
                            "task_id": task_id,
                            "report_id": report_id,
                            "snapshot_id": stored.report.snapshot_id,
                            "content_hash": stored.report.content_hash,
                            "facts_hash": stored.report.facts_hash,
                            "citations": [item.model_dump(mode="json") for item in page],
                            "total_evidence_count": len(citations),
                            "next_cursor": next_cursor,
                        },
                    )
                )
            )

    def question(
        self, actor: WebActor, task_id: UUID, question_id: UUID, cursor: str | None
    ) -> QuestionRead:
        with connect(self.settings) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            parent, _, stored = report_for_actor(db, actor, task_id)
            task = db.execute(
                """SELECT * FROM business.business_tasks WHERE id=%s AND organization_id=%s
            AND shop_id=%s AND requester_id=%s AND kind='daily_question'""",
                (question_id, actor.organization_id, parent["shop_id"], actor.principal_id),
            ).fetchone()
            if task is None:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            request = QuestionTaskRequest.model_validate_json(
                json.dumps(task["normalized_request"])
            )
            if request.parent_task_id != task_id:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            row = db.execute(
                "SELECT * FROM business.p6_daily_questions WHERE task_id=%s", (question_id,)
            ).fetchone()
            result = verified_question(row, stored, request) if row else None
            page: tuple[Citation, ...] = ()
            next_cursor: str | None = None
            if result is not None:
                context = EvidenceContext(
                    actor_id=actor.principal_id,
                    auth_version=actor.auth_version,
                    organization_id=actor.organization_id,
                    shop_id=parent["shop_id"],
                    task_id=task_id,
                    report_id=stored.report_id,
                    snapshot_id=stored.report.snapshot_id,
                    content_hash=stored.report.content_hash,
                    facts_hash=stored.report.facts_hash,
                    question_id=question_id,
                )
                page, next_cursor = self._page(context, result.citations, cursor)
            elif cursor is not None:
                raise WebFailure("INVALID_CURSOR", 409)
            return QuestionRead.model_validate_json(
                json.dumps(
                    envelope(
                        db,
                        question={
                            "schema_version": "p6-m3-web-v1",
                            "parent_task_id": task_id,
                            "question_id": question_id,
                            "state": task["state"],
                            "failure_code": task["failure_code"],
                            "answer": result.answer.model_dump(mode="json") if result else None,
                            "citations": [item.model_dump(mode="json") for item in page],
                            "total_evidence_count": len(result.citations) if result else 0,
                            "next_cursor": next_cursor,
                        },
                    )
                )
            )

    def create_question(self, actor: WebActor, task_id: UUID, body: Any) -> AcceptanceRead:
        return self.accepted(actor, create_question(self.settings, actor, task_id, body))
