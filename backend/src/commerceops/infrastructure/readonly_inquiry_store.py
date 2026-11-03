"""Dedicated inquiry transactions. No provider/SDK calls or shared entrypoint registration."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from commerceops.adapters.commerce.mock import Fixture
from commerceops.application.commerce.readonly_inquiry_contracts import Window
from commerceops.application.commerce.readonly_inquiry_render import render
from commerceops.application.commerce.readonly_inquiry_service_contracts import (
    KIND,
    WORKFLOW,
    CreateInquiry,
    InquiryRead,
    InquiryReceipt,
    ResultPayload,
)
from commerceops.application.commerce.readonly_inquiry_service_demo import fixture_domain
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.application.runner import RunRequest
from commerceops.domain.commerce_values import facts_hash
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.replenishment_repository import (
    ReplenishmentStore,
    has_capability,
    visible_task,
)
from commerceops.infrastructure.repository import TaskRepository, TaskScope
from commerceops.infrastructure.web_config import WebConfig
from commerceops.infrastructure.web_sessions import DB, actor_guard, now, role_scope


@dataclass(frozen=True)
class InquiryConfig:
    shop_id: UUID
    fixture_directory: Path
    fixture_case: str = "baseline"
    enabled: bool = False

    def fixture(self) -> Fixture:
        return Fixture.load(self.fixture_directory, self.fixture_case)


class InquiryStore:
    def __init__(self, config: WebConfig, inquiry: InquiryConfig):
        self.config, self.inquiry, self.settings = config, inquiry, config.database

    @staticmethod
    def bound_transaction(db: DB) -> None:
        db.execute("SET LOCAL statement_timeout='5000ms'")
        db.execute("SET LOCAL lock_timeout='1000ms'")

    def authorize_entry(self, actor: WebActor) -> None:
        with connect(self.settings) as db:
            self.bound_transaction(db)
            if not has_capability(db, actor, "operator"):
                raise WebFailure("ACCESS_DENIED", 403)

    def authorize(self, db: DB, actor: WebActor, shop: UUID) -> None:
        actor_guard(db, actor)
        if shop != self.inquiry.shop_id or not role_scope(db, actor, shop, "operator"):
            raise WebFailure("RESOURCE_NOT_FOUND", 404)

    def report_task(self, db: DB, actor: WebActor, shop: UUID, report: UUID) -> UUID:
        self.authorize(db, actor, shop)
        row = db.execute(
            """SELECT task_id FROM business.analysis_reports
            WHERE id=%s AND organization_id=%s AND shop_id=%s""",
            (report, actor.organization_id, shop),
        ).fetchone()
        if row is None:
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        visible_task(db, actor, row["task_id"])
        return UUID(str(row["task_id"]))

    def source(self, db: DB, actor: WebActor, shop: UUID) -> tuple[Fixture, Window]:
        self.authorize(db, actor, shop)
        fixture = self.inquiry.fixture()
        row = db.execute(
            """SELECT * FROM business.shops
            WHERE id=%s AND organization_id=%s FOR SHARE""",
            (shop, actor.organization_id),
        ).fetchone()
        if (
            row is None
            or row["adapter_kind"] != "mock"
            or row["environment"] not in ("mock", "test")
            or row["external_shop_key"] != fixture.source.shop_id
            or row["currency"] != fixture.source.currency
            or row["timezone"] != fixture.source.timezone
        ):
            raise WebFailure("SERVICE_UNAVAILABLE", 503)
        return fixture, fixture_domain(fixture)

    @staticmethod
    def actor(row: dict[str, Any]) -> WebActor:
        return WebActor(
            row["session_id"],
            row["principal_id"],
            row["identity_id"],
            row["organization_id"],
            row["auth_version"],
        )

    def row_guard(self, db: DB, actor: WebActor, row: dict[str, Any]) -> None:
        self.authorize(db, actor, row["shop_id"])
        if (
            row["principal_id"] != actor.principal_id
            or row["organization_id"] != actor.organization_id
        ):
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        request = CreateInquiry.model_validate_json(json.dumps(row["request"]))
        expected = facts_hash(
            {"path": "/api/v1/readonly-inquiries", "body": request.model_dump(mode="json")}
        )
        if (
            request.request_key != row["request_key"]
            or request.shop_id != row["shop_id"]
            or expected != row["request_hash"]
        ):
            raise ValueError("REQUEST_INTEGRITY")
        if row["context_report_id"] is not None:
            self.report_task(db, actor, row["shop_id"], row["context_report_id"])

    @staticmethod
    def receipt(db: DB, row: dict[str, Any], duplicate: bool) -> InquiryReceipt:
        return InquiryReceipt.model_validate(
            {
                "task_id": row["task_id"],
                "shop_id": row["shop_id"],
                "request_key": row["request_key"],
                "state": row.get("task_state", row["state"]),
                "duplicate": duplicate,
                "source_binding": row["source_binding"],
                "source_domain": Window.model_validate_json(json.dumps(row["source_domain"])),
                "server_time": now(db),
                "trace_id": uuid4(),
            }
        )

    @staticmethod
    def audit(db: DB, row: dict[str, Any], action: str) -> None:
        db.execute(
            """INSERT INTO business.audit_events
            (id,organization_id,task_id,actor_id,source,action,entity_type,entity_id,trace_id)
            VALUES(%s,%s,%s,%s,'readonly_inquiry',%s,'task',%s,%s)""",
            (
                uuid4(),
                row["organization_id"],
                row["task_id"],
                row["principal_id"],
                action,
                str(row["task_id"]),
                uuid4(),
            ),
        )

    def create(
        self, actor: WebActor, request: CreateInquiry, hook: Callable[[str], None] | None = None
    ) -> InquiryReceipt:
        # Revalidate hostile model_construct/copy and canonicalize only the public body.
        request = CreateInquiry.model_validate_json(request.model_dump_json())
        body = request.model_dump(mode="json")
        request_hash = facts_hash({"path": "/api/v1/readonly-inquiries", "body": body})
        with connect(self.settings) as db:
            self.bound_transaction(db)
            self.authorize(db, actor, request.shop_id)
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"p6-inquiry:{actor.principal_id}:{request.request_key}",),
            )
            old = db.execute(
                """SELECT i.*,t.state AS task_state FROM business.readonly_inquiries i
                JOIN business.business_tasks t ON t.id=i.task_id
                WHERE i.principal_id=%s AND i.request_key=%s""",
                (actor.principal_id, request.request_key),
            ).fetchone()
            if old:
                self.row_guard(db, actor, old)
                if old["request_hash"] != request_hash:
                    raise WebFailure("IDEMPOTENCY_CONFLICT")
                receipt = self.receipt(db, old, True)
            else:
                if not self.inquiry.enabled:
                    raise WebFailure("INQUIRY_DISABLED", 409)
                fixture, domain = self.source(db, actor, request.shop_id)
                if request.context_report_id is not None:
                    self.report_task(db, actor, request.shop_id, request.context_report_id)
                task = uuid4()
                conversation = ReplenishmentStore._conversation(db, actor)
                ReplenishmentStore._task(
                    db, actor, request.shop_id, conversation, task, KIND, WORKFLOW, body
                )
                row = db.execute(
                    """INSERT INTO business.readonly_inquiries
                    (task_id,organization_id,shop_id,principal_id,session_id,identity_id,auth_version,
                     request_key,request_hash,request,source_binding,source_domain,evidence_mode,
                     workflow_version,context_report_id)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'offline_stub',%s,%s) RETURNING *""",
                    (
                        task,
                        actor.organization_id,
                        request.shop_id,
                        actor.principal_id,
                        actor.session_id,
                        actor.identity_id,
                        actor.auth_version,
                        request.request_key,
                        request_hash,
                        Jsonb(body),
                        fixture.source.provenance.raw_hash,
                        Jsonb(domain.model_dump(mode="json")),
                        WORKFLOW,
                        request.context_report_id,
                    ),
                ).fetchone()
                if row is None:
                    raise WebFailure("SERVICE_UNAVAILABLE", 503)
                TaskRepository(db, TaskScope(actor.organization_id, request.shop_id)).enqueue(
                    task, "analyze", f"p6-inquiry:{task}", f"inquiry:{task}"
                )
                self.audit(db, row, "inquiry_accepted")
                receipt = self.receipt(db, row, False)
            if hook:
                hook("before_commit")
        if hook:
            hook("after_commit")
        return receipt

    def read(
        self, actor: WebActor, task_id: UUID | None = None, request_key: UUID | None = None
    ) -> InquiryRead:
        if (task_id is None) == (request_key is None):
            raise ValueError("ONE_LOCATOR_REQUIRED")
        with connect(self.settings) as db:
            self.bound_transaction(db)
            actor_guard(db, actor)
            row = db.execute(
                """SELECT i.*,t.state AS task_state FROM business.readonly_inquiries i
                JOIN business.business_tasks t ON t.id=i.task_id
                AND t.organization_id=i.organization_id
                WHERE i.organization_id=%s AND i.principal_id=%s
                AND (%s::uuid IS NULL OR i.task_id=%s)
                AND (%s::uuid IS NULL OR i.request_key=%s)""",
                (
                    actor.organization_id,
                    actor.principal_id,
                    task_id,
                    task_id,
                    request_key,
                    request_key,
                ),
            ).fetchone()
            if row is None:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            self.row_guard(db, actor, row)
            payload = self.decode(row)
            if payload:
                for result in payload.results:
                    if result.report_id is not None:
                        self.report_task(db, actor, row["shop_id"], UUID(result.report_id))
            metadata = self.receipt(db, row, True).model_dump()
            if row["task_state"] != row["state"]:
                metadata["state"] = "needs_attention"
                payload = None
            return InquiryRead.model_validate(
                {
                    **metadata,
                    "result": payload,
                    "answer": render(payload.outcome()).text if payload else None,
                }
            )

    @staticmethod
    def decode(row: dict[str, Any]) -> ResultPayload | None:
        if row["result"] is None:
            return None
        canonical = row["result_canonical"]
        if (
            not isinstance(canonical, str)
            or json.loads(canonical) != row["result"]
            or hashlib.sha256(canonical.encode()).hexdigest() != row["result_hash"]
        ):
            raise ValueError("RESULT_INTEGRITY")
        return ResultPayload.model_validate_json(canonical)

    def run_row(self, db: DB, run: RunRequest) -> dict[str, Any]:
        self.bound_transaction(db)
        if (
            run.thread_id != str(run.task_id)
            or run.workflow_version != WORKFLOW
            or run.kind != "analyze"
            or run.payload_ref != f"inquiry:{run.task_id}"
        ):
            raise ValueError("INQUIRY_JOB_BINDING")
        row = db.execute(
            """SELECT i.*,t.state AS task_state FROM business.readonly_inquiries i
            JOIN business.business_tasks t ON t.id=i.task_id
                AND t.organization_id=i.organization_id
            JOIN business.jobs j ON j.task_id=t.id AND j.organization_id=t.organization_id
            AND j.shop_id=t.shop_id
            WHERE i.task_id=%s AND i.organization_id=%s AND i.shop_id=%s
            AND t.kind='readonly_inquiry' AND t.workflow_version=%s
            AND j.id=%s AND j.kind='analyze' AND j.status='running'
            AND j.lease_owner=%s AND j.attempts=%s
            AND j.dedupe_key=%s AND j.payload_ref=%s FOR UPDATE OF i,t""",
            (
                run.task_id,
                run.organization_id,
                run.shop_id,
                WORKFLOW,
                run.job_id,
                run.owner,
                run.attempt,
                f"p6-inquiry:{run.task_id}",
                f"inquiry:{run.task_id}",
            ),
        ).fetchone()
        if row is None or row["task_state"] not in ("queued", "analyzing", "completed", "failed"):
            raise ValueError("INQUIRY_OWNER_OR_STATE")
        if row["state"] != row["task_state"]:
            raise ValueError("INQUIRY_STATE_DIVERGED")
        self.row_guard(db, self.actor(row), row)
        fixture, domain = self.source(db, self.actor(row), row["shop_id"])
        if (
            row["source_binding"] != fixture.source.provenance.raw_hash
            or row["source_domain"] != domain.model_dump(mode="json")
            or row["evidence_mode"] != "offline_stub"
            or row["workflow_version"] != WORKFLOW
        ):
            raise ValueError("INQUIRY_SOURCE_CHANGED")
        return row

    def load(self, run: RunRequest) -> tuple[dict[str, Any], ResultPayload | None]:
        with connect(self.settings) as db:
            row = self.run_row(db, run)
            return row, self.decode(row)

    def mark(self, run: RunRequest) -> None:
        with connect(self.settings) as db:
            row = self.run_row(db, run)
            if row["result"] is not None:
                return
            if not self.inquiry.enabled:
                raise WebFailure("INQUIRY_DISABLED")
            db.execute(
                """UPDATE business.readonly_inquiries SET state='analyzing',version=version+1,
                updated_at=clock_timestamp() WHERE task_id=%s AND result IS NULL""",
                (run.task_id,),
            )
            db.execute(
                """UPDATE business.business_tasks SET state='analyzing',version=version+1,
                updated_at=clock_timestamp() WHERE id=%s AND state IN ('queued','analyzing')""",
                (run.task_id,),
            )
            self.audit(db, row, "inquiry_started")

    def finish(self, run: RunRequest, result: ResultPayload) -> None:
        result = ResultPayload.model_validate_json(result.model_dump_json())
        render(result.outcome())
        canonical = result.model_dump_json()
        with connect(self.settings) as db:
            row = self.run_row(db, run)
            if row["result"] is not None:
                if self.decode(row) != result:
                    raise ValueError("RESULT_REPLAY_CONFLICT")
                return
            fixture = self.inquiry.fixture()
            domain = Window.model_validate_json(json.dumps(row["source_domain"]))
            for read in result.results:
                if any(
                    window.start < domain.start or window.end > domain.end
                    for window in read.windows
                ):
                    raise ValueError("RESULT_SOURCE_DOMAIN")
                if (
                    read.shop_id != fixture.source.shop_id
                    or read.source_binding != row["source_binding"]
                ):
                    raise ValueError("RESULT_SOURCE_MISMATCH")
            # Recheck all referenced report objects before committing disclosed evidence.
            for read in result.results:
                if read.report_id is not None:
                    self.report_task(db, self.actor(row), row["shop_id"], UUID(read.report_id))
            state = (
                "completed"
                if result.status in ("complete", "clarify", "unsupported", "insufficient_evidence")
                else "failed"
            )
            if row["state"] != "analyzing":
                raise ValueError("INQUIRY_NOT_RUNNING")
            db.execute(
                """UPDATE business.readonly_inquiries SET state=%s,result=%s,
                result_canonical=%s,result_hash=%s,version=version+1,updated_at=clock_timestamp()
                WHERE task_id=%s AND result IS NULL""",
                (
                    state,
                    Jsonb(result.model_dump(mode="json")),
                    canonical,
                    hashlib.sha256(canonical.encode()).hexdigest(),
                    run.task_id,
                ),
            )
            db.execute(
                """UPDATE business.business_tasks SET state=%s,version=version+1,
                updated_at=clock_timestamp() WHERE id=%s AND state='analyzing'""",
                (state, run.task_id),
            )
            self.audit(db, row, "inquiry_result_saved")
