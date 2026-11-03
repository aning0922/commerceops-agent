"""日报只读投影；GET不访问来源、秘密、模型或创建任务。"""

import json
from typing import Any
from uuid import UUID

import psycopg

from commerceops.application.daily.read_models import QUESTION_KINDS, DailyRead, public_report
from commerceops.application.daily.source import WORKFLOW, DailyTaskRequest, DailyUnsafe
from commerceops.application.replenishment.contracts import WebActor, WebFailure
from commerceops.domain.commerce_values import canonical_bytes
from commerceops.infrastructure.daily_store import RESULT_SQL, verified_row
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.web_sessions import actor_guard, envelope, role_scope


class DailyReadStore:
    def __init__(
        self,
        settings: DatabaseSettings,
        *,
        operations_enabled: bool = False,
        schedules_enabled: bool = False,
    ):
        self.settings = settings
        self.operations_enabled, self.schedules_enabled = operations_enabled, schedules_enabled

    def read(self, actor: WebActor, task_id: UUID) -> dict[str, Any]:
        try:
            with connect(self.settings) as db:
                db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                actor_guard(db, actor)
                task = db.execute(
                    """SELECT * FROM business.business_tasks WHERE id=%s
                AND organization_id=%s AND requester_id=%s AND kind='daily_report'
                AND workflow_version=%s""",
                    (task_id, actor.organization_id, actor.principal_id, WORKFLOW),
                ).fetchone()
                if task is None or not role_scope(db, actor, task["shop_id"], "operator"):
                    raise WebFailure("RESOURCE_NOT_FOUND", 404)
                request = DailyTaskRequest.model_validate_json(
                    json.dumps(task["normalized_request"])
                )
                source = db.execute(
                    """SELECT canonical_projection,config_digest FROM
                business.p6_daily_source_bindings
                WHERE id=%s AND organization_id=%s AND shop_id=%s""",
                    (
                        request.daily_source.source_binding_id,
                        actor.organization_id,
                        task["shop_id"],
                    ),
                ).fetchone()
                if source is None or source["config_digest"] != request.daily_source.config_digest:
                    raise DailyUnsafe("DAILY_STORAGE_FAILURE")
                from pydantic import TypeAdapter

                from commerceops.application.daily.source import DailyMetadata

                metadata: DailyMetadata = TypeAdapter(DailyMetadata).validate_json(
                    source["canonical_projection"]
                )
                if metadata.source(
                    request.daily_source.source_binding_id
                ) != request.daily_source or (
                    canonical_bytes(metadata.model_dump(mode="json")).decode()
                    != source["canonical_projection"]
                ):
                    raise DailyUnsafe("DAILY_STORAGE_FAILURE")
                row = db.execute(
                    RESULT_SQL, (task_id, actor.organization_id, task["shop_id"])
                ).fetchone()
                projected = None
                if row is not None:
                    saved = verified_row(row, request)
                    projected = public_report(saved.report_id, saved.report).model_dump(mode="json")
                scheduled, delivery = None, None
                ops = db.execute(
                    "SELECT to_regclass('business.p6_daily_schedule_runs') AS name"
                ).fetchone()
                if ops and ops["name"] is not None:
                    scheduled = db.execute(
                        """SELECT r.id AS run_id,r.schedule_id,r.schedule_version,r.business_day,
                    r.due_at,r.created_at AS queued_at,r.missed_periods,
                    r.skipped_first_day,r.skipped_last_day,
                    (SELECT min(a.occurred_at) FROM business.audit_events a
                    WHERE a.task_id=r.task_id
                    AND a.source='daily' AND a.action='schedule_run_started') AS actual_started_at
                    FROM business.p6_daily_schedule_runs r
                    WHERE r.task_id=%s AND r.organization_id=%s
                    AND r.shop_id=%s""",
                        (task_id, actor.organization_id, task["shop_id"]),
                    ).fetchone()
                    if scheduled is not None:
                        for field in ("business_day", "skipped_first_day", "skipped_last_day"):
                            if scheduled[field] is not None:
                                scheduled[field] = scheduled[field].isoformat()
                    delivery = db.execute(
                        """SELECT id AS delivery_id,'fake'::text AS transport,status AS state,
                    attempts,external_id,failure_code FROM business.p6_daily_deliveries
                    WHERE task_id=%s
                    AND organization_id=%s AND shop_id=%s""",
                        (task_id, actor.organization_id, task["shop_id"]),
                    ).fetchone()
                payload = envelope(
                    db,
                    daily={
                        "schema_version": "p6-m3-web-v1",
                        "task_id": str(task_id),
                        "shop_id": str(task["shop_id"]),
                        "kind": "daily_report",
                        "workflow_version": WORKFLOW,
                        "created_at": task["created_at"],
                        "updated_at": task["updated_at"],
                        "question_creation_enabled": self.operations_enabled
                        and projected is not None,
                        "question_kinds": QUESTION_KINDS,
                        "schedule_enabled": self.schedules_enabled,
                        "delivery_enabled": False,
                        "state": task["state"],
                        "failure_code": task["failure_code"],
                        "report": projected,
                        "schedule_run": scheduled,
                        "delivery": delivery,
                    },
                )
                # 输出跨字段/显示/hash语义先由实际DTO验证；不向网络返回裸DB JSON。
                return DailyRead.model_validate_json(json.dumps(payload)).model_dump(mode="json")
        except WebFailure:
            raise
        except (psycopg.Error, OSError, ValueError, KeyError, TypeError):
            raise WebFailure("SERVICE_UNAVAILABLE", 503) from None
