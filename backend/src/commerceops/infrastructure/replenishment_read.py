"""P3受scope约束的只读投影；列表页和计数来自同一SQL快照。"""

import base64
import hmac
import json
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

from commerceops.application.replenishment.contracts import (
    TASK_KIND,
    Actor,
    FeishuActor,
    WebActor,
    WebFailure,
)
from commerceops.domain.commerce_values import canonical_bytes, utc_time
from commerceops.infrastructure.approval_decisions import decision_fields, may_decide, nonce_for
from commerceops.infrastructure.database import connect
from commerceops.infrastructure.feishu_delivery_read import (
    external_enabled,
    safe_code,
    sender_gates,
)
from commerceops.infrastructure.inventory_repository import _stored
from commerceops.infrastructure.replenishment_repository import (
    SOURCE_SQL,
    ReplenishmentStore,
    has_capability,
    source_binding,
    visible_task,
)
from commerceops.infrastructure.web_sessions import (
    DB,
    actor_guard,
    deployment,
    envelope,
    now,
    role_scope,
)


def complete_pure[T](operation: Coroutine[Any, Any, T]) -> T:
    """仅复用既有 provider=None 的 P204 验证：禁止挂起/外部 await，不建 loop。"""
    try:
        operation.send(None)
    except StopIteration as result:
        return result.value  # type: ignore[no-any-return]
    finally:
        operation.close()
    raise WebFailure("SERVICE_UNAVAILABLE", 503)


def read_visible_task(db: DB, actor: Actor, task_id: UUID) -> dict[str, Any]:
    task = visible_task(db, actor, task_id)
    if isinstance(actor, FeishuActor):
        trusted = db.execute(
            """SELECT 1 FROM business.conversations c
            WHERE c.id=%s AND c.organization_id=%s AND c.channel='feishu' AND c.chat_id=%s
            UNION ALL SELECT 1 FROM business.p4_card_bindings b
            JOIN business.outbox o ON o.id=b.outbox_id
            WHERE o.task_id=%s AND o.organization_id=%s AND o.shop_id=%s
            AND b.source_mode='feishu' AND b.chat_id=%s LIMIT 1""",
            (
                task["conversation_id"],
                actor.organization_id,
                actor.chat_id,
                task_id,
                actor.organization_id,
                task["shop_id"],
                actor.chat_id,
            ),
        ).fetchone()
        if trusted is None:
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
    return task


STATES = (
    "queued",
    "analyzing",
    "awaiting_approval",
    "executing",
    "completed",
    "rejected",
    "expired",
    "needs_reapproval",
    "failed",
    "needs_attention",
)


class ReplenishmentReadStore:
    def __init__(self, store: ReplenishmentStore):
        self.store, self.config, self.settings = store, store.config, store.settings

    async def explanation(self, actor: Actor, task_id: UUID, report_id: UUID) -> dict[str, Any]:
        with connect(self.settings) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            return self.explanation_in_transaction(db, actor, task_id, report_id)

    def explanation_in_transaction(
        self, db: DB, actor: Actor, task_id: UUID, report_id: UUID
    ) -> dict[str, Any]:
        from commerceops.application.commerce.explanation_task import (
            ExplanationTaskRequest,
            logical_key,
        )
        from commerceops.infrastructure.explanation_repository import (
            ExplanationStore,
            payload,
            validated_row,
        )

        self._business(db, actor)
        task = read_visible_task(db, actor, task_id)
        source = self._source(db, task)
        if source and source["id"] != report_id and task["kind"] == TASK_KIND:
            observation = db.execute(
                """SELECT * FROM business.p3_observations WHERE task_id=%s
                AND organization_id=%s AND shop_id=%s AND report_id=%s""",
                (task_id, actor.organization_id, task["shop_id"], report_id),
            ).fetchone()
            if observation:
                binding = db.execute(
                    "SELECT * FROM business.p3_task_sources WHERE task_id=%s", (task_id,)
                ).fetchone()
                if not binding:
                    raise WebFailure("NOT_READY")
                from commerceops.infrastructure.replenishment_execution import ExecutionStore

                _, report = ExecutionStore.verify_row(observation, binding)
                return self.template_explanation(db, task, report_id, observation, report)

        if not source or source["id"] != report_id:
            raise WebFailure("RESOURCE_NOT_FOUND", 404)
        row = db.execute(
            """SELECT e.*,t.normalized_request FROM business.model_explanations e
        JOIN business.explanation_links l ON l.child_task_id=e.child_task_id
        JOIN business.business_tasks t ON t.id=e.child_task_id
        JOIN business.explanation_task_results x ON x.child_task_id=t.id AND
 x.result_id=e.id
        WHERE e.organization_id=%s AND e.shop_id=%s AND e.parent_task_id=%s
        AND l.requester_id=%s AND e.report_id=%s AND e.facts_hash=%s
        ORDER BY e.created_at DESC,e.id DESC LIMIT 1""",
            (
                actor.organization_id,
                task["shop_id"],
                source["task_id"],
                source["requester_id"],
                report_id,
                source["facts_hash"],
            ),
        ).fetchone()
        if not row:
            if task["kind"] == TASK_KIND:
                return self.template_explanation(
                    db,
                    task,
                    report_id,
                    source,
                    _stored(source, source["normalized_request"]).report,
                )
            raise WebFailure("NOT_READY")
        req = ExplanationTaskRequest.model_validate_json(json.dumps(row["normalized_request"]))
        expected = logical_key(
            actor.organization_id,
            task["shop_id"],
            source["requester_id"],
            source["task_id"],
            report_id,
            source["facts_hash"],
            req.body_hash,
            req.evidence_mode,
        )
        if req.logical_key != expected:
            raise WebFailure("NOT_READY")
        result = validated_row(row, req, actor.organization_id, task["shop_id"])
        complete_pure(
            ExplanationStore.verify(
                result, _stored(source, source["normalized_request"]).report, req
            )
        )
        return envelope(
            db,
            task_id=task_id,
            report_id=report_id,
            explanation={
                "schema_version": "p204-read-v1",
                "analysis_only": True,
                "execution_available": False,
                "identity_mode": "simulated",
                "task_id": str(source["task_id"]),
                "explanation_id": str(row["id"]),
                "child_task_id": str(row["child_task_id"]),
                "result": payload(result),
            },
        )

    @staticmethod
    def template_explanation(
        db: DB, task: dict[str, Any], report_id: UUID, evidence: dict[str, Any], report: Any
    ) -> dict[str, Any]:
        from commerceops.infrastructure.p3_template_results import TemplateBinding, read

        observation = evidence.get("schema_version") == "p3-observation-v1"
        content = read(
            db,
            TemplateBinding(
                task["organization_id"],
                task["shop_id"],
                task["requester_id"],
                task["id"],
                "p3_observation" if observation else "p2_original",
                evidence["source_task_id"] if observation else evidence["task_id"],
                evidence["id"] if observation else None,
                evidence["id"] if observation else evidence["snapshot_id"],
                report_id,
                evidence["facts_hash"],
            ),
            report,
        )
        if content is None:
            raise WebFailure("NOT_READY")
        return envelope(db, task_id=task["id"], report_id=report_id, explanation=content)

    def cursor(
        self,
        actor: WebActor,
        endpoint: str,
        filters: object,
        last: dict[str, Any],
        order: str = "created_at-desc/id-desc",
    ) -> str:
        claims = [
            str(actor.organization_id),
            str(actor.principal_id),
            actor.auth_version,
            endpoint,
            filters,
            order,
            utc_time(last["created_at"]),
            str(last["id"]),
        ]
        body = canonical_bytes(claims)
        signature = hmac.digest(self.config.nonce_secret, b"p3-cursor-v1\x00" + body, "sha256")
        return base64.urlsafe_b64encode(body + signature).decode().rstrip("=")

    def page_after(
        self,
        actor: WebActor,
        endpoint: str,
        filters: object,
        cursor: str | None,
        order: str = "created_at-desc/id-desc",
    ) -> tuple[Any, UUID | None]:
        if cursor is None:
            return None, None
        try:
            if len(cursor) > 2048:
                raise ValueError
            raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            body, signature = raw[:-32], raw[-32:]
            expected = hmac.digest(self.config.nonce_secret, b"p3-cursor-v1\x00" + body, "sha256")
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            claims = json.loads(body)
            binding = [
                str(actor.organization_id),
                str(actor.principal_id),
                actor.auth_version,
                endpoint,
                filters,
                order,
            ]
            if (
                type(claims) is not list
                or len(claims) != 8
                or claims[:6] != binding
                or type(claims[2]) is not int
            ):
                raise ValueError
            return utc_time(claims[6]), UUID(claims[7])
        except (ValueError, TypeError, UnicodeError):
            raise WebFailure("INVALID_CURSOR", 400) from None

    @staticmethod
    def _business(db: DB, actor: Actor) -> None:
        if not has_capability(db, actor, "operator") and not has_capability(db, actor, "approver"):
            raise WebFailure("ACCESS_DENIED", 403)

    @staticmethod
    def _sync(db: DB, task: UUID, aggregate: UUID | None = None) -> dict[str, Any]:
        rows = db.execute(
            """SELECT o.*,i.version AS target_version,d.status AS delivery_status,
            d.observed_version,d.complete_unique_verified,d.attempts AS delivery_attempts,
            d.last_checked_at,d.last_error AS delivery_error,d.verification_mode
            FROM business.outbox o LEFT JOIN business.replenishment_items i ON i.id=o.aggregate_id
            AND i.task_id=o.task_id LEFT JOIN business.p4_base_deliveries d ON d.outbox_id=o.id
            WHERE o.task_id=%s AND (%s::uuid IS NULL OR o.aggregate_id=%s)
            ORDER BY o.created_at,o.id""",
            (task, aggregate, aggregate),
        ).fetchall()
        gates = sender_gates(db, rows[0]["organization_id"], [rows[0]["shop_id"]]) if rows else []
        projections = []
        for row in rows:
            status = row["delivery_status"]
            state = (
                "synced"
                if status == "verified" and row["complete_unique_verified"]
                else "unknown"
                if status == "unknown"
                else "failed"
                if status in ("fatal", "conflict", "stale")
                else "pending"
                if status is not None
                else "synced"
                if row["status"] == "sent" and row["external_id"]
                else "unknown"
                if row["status"] == "unknown"
                else "failed"
                if row["status"] == "dead"
                else "pending"
            )
            alias = "Base" if row["destination"] == "bitable" else "IM"
            target_version = row["target_version"] or row["aggregate_version"]
            projections.append(
                {
                    "outbox_id": row["id"],
                    "aggregate_id": row["aggregate_id"],
                    "projection_version": row["aggregate_version"],
                    "outbox_status": row["status"],
                    "state": state,
                    "source_mode": row["source_mode"],
                    "destination_alias": alias,
                    "target_version": target_version,
                    "observed_version": row["observed_version"],
                    "complete_unique_verified": bool(row["complete_unique_verified"]),
                    "is_current_version": row["aggregate_version"] == target_version,
                    "attempts": row["delivery_attempts"] if status is not None else row["attempts"],
                    "verification_mode": row["verification_mode"],
                    "as_of": row["last_checked_at"] or row["created_at"],
                    "error_code": safe_code(
                        row["delivery_error"] if status is not None else row["last_error"]
                    ),
                }
            )
        latest: dict[str, dict[str, Any]] = {}
        for projection in projections:
            key = str(projection["aggregate_id"])
            if (
                key not in latest
                or projection["projection_version"] > latest[key]["projection_version"]
            ):
                latest[key] = projection
        current = {projection["state"] for projection in latest.values()}
        summary = next(
            (state for state in ("unknown", "failed", "pending", "synced") if state in current),
            "not_requested",
        )
        return {
            "state": summary,
            "sender_enabled": external_enabled(gates),
            "sender_gates": gates,
            "projections": projections,
        }

    def _summary(self, db: DB, task: dict[str, Any]) -> dict[str, Any]:
        outcome = None
        if task["state"] == "completed":
            if task["kind"] == TASK_KIND:
                outcome = "no_action" if not task["active_plan_id"] else "items_created"
            else:
                report = db.execute(
                    "SELECT outcome FROM business.analysis_reports WHERE task_id=%s", (task["id"],)
                ).fetchone()
                outcome = report["outcome"] if report else None
        return {
            "task_id": task["id"],
            "shop_id": task["shop_id"],
            "kind": task["kind"],
            "workflow_version": task["workflow_version"],
            "state": task["state"],
            "created_at": utc_time(task["created_at"]),
            "updated_at": utc_time(task["updated_at"]),
            "outcome": outcome,
            "sync": self._sync(db, task["id"]),
        }

    @staticmethod
    def _source(db: DB, task: dict[str, Any]) -> dict[str, Any] | None:
        source_id = task["id"]
        if task["kind"] == TASK_KIND:
            binding = db.execute(
                "SELECT * FROM business.p3_task_sources WHERE task_id=%s", (task["id"],)
            ).fetchone()
            if not binding:
                raise WebFailure("NOT_READY")
            source_id = binding["source_task_id"]
        return db.execute(
            SOURCE_SQL, (source_id, task["organization_id"], task["shop_id"])
        ).fetchone()

    def read_task(self, actor: Actor, task_id: UUID) -> dict[str, Any]:
        with connect(self.settings) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            return self.task_in_transaction(db, actor, task_id)

    def task_in_transaction(self, db: DB, actor: Actor, task_id: UUID) -> dict[str, Any]:
        self._business(db, actor)
        task = read_visible_task(db, actor, task_id)
        source = self._source(db, task)
        approval = db.execute(
            "SELECT * FROM business.approvals WHERE plan_id=%s", (task["active_plan_id"],)
        ).fetchone()
        plan = (
            db.execute(
                "SELECT * FROM business.replenishment_plans WHERE id=%s",
                (task["active_plan_id"],),
            ).fetchone()
            if approval
            else None
        )
        can_decide = bool(
            approval and plan and may_decide(db, self.config, actor, task, approval, plan)
        )
        execution = db.execute(
            "SELECT id FROM business.executions WHERE task_id=%s", (task_id,)
        ).fetchone()
        item_rows = db.execute(
            "SELECT id,status FROM business.replenishment_items WHERE task_id=%s ORDER BY id",
            (task_id,),
        ).fetchall()
        can_resolve = any(x["status"] == "open" for x in item_rows) and role_scope(
            db, actor, task["shop_id"], "approver"
        )
        return envelope(
            db,
            task=self._summary(db, task),
            source=source_binding(source) if source else None,
            current_plan_id=task["active_plan_id"],
            approval_id=approval["id"] if approval else None,
            execution_id=execution["id"] if execution else None,
            visible_item_ids=[x["id"] for x in item_rows],
            actions={
                "can_decide": can_decide,
                "can_resolve": can_resolve,
                "can_start_new_cycle": task["state"] == "completed"
                and source is not None
                and source["shop_id"] == task["shop_id"]
                and role_scope(db, actor, task["shop_id"], "operator"),
                "can_recompute": False,
                "disabled_reasons": ["RECOMPUTE_DISABLED"],
            },
            failure_code=task["failure_code"],
        )

    def report(
        self, actor: WebActor, task_id: UUID, report_id: UUID | None = None
    ) -> dict[str, Any]:
        with connect(self.settings) as db:
            self._business(db, actor)
            task = visible_task(db, actor, task_id)
            row = self._source(db, task)
            if not row:
                raise WebFailure("NOT_READY")
            if task["kind"] == TASK_KIND:
                plan = db.execute(
                    "SELECT * FROM business.replenishment_plans WHERE id=%s",
                    (task["active_plan_id"],),
                ).fetchone()
                if (
                    report_id
                    and report_id != row["id"]
                    or (report_id is None and plan and plan["evidence_kind"] == "p3_observation")
                ):
                    observation = db.execute(
                        """SELECT o.* FROM business.p3_observations o
                        WHERE o.task_id=%s AND o.organization_id=%s AND o.shop_id=%s
                        AND ((%s::uuid IS NOT NULL AND o.report_id=%s) OR
                        (%s::uuid IS NULL AND o.id=%s))""",
                        (
                            task_id,
                            actor.organization_id,
                            task["shop_id"],
                            report_id,
                            report_id,
                            report_id,
                            plan["p3_observation_id"] if plan else None,
                        ),
                    ).fetchone()
                    if not observation:
                        raise WebFailure("RESOURCE_NOT_FOUND", 404)
                    binding = db.execute(
                        "SELECT * FROM business.p3_task_sources WHERE task_id=%s", (task_id,)
                    ).fetchone()
                    if not binding:
                        raise WebFailure("NOT_READY")
                    from commerceops.infrastructure.replenishment_execution import ExecutionStore

                    _, facts = ExecutionStore.verify_row(observation, binding)
                    return envelope(
                        db,
                        task_id=task_id,
                        source=ExecutionStore.source(observation),
                        facts=facts.model_dump(mode="json"),
                    )
            if report_id and report_id != row["id"]:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            data = _stored(row, row["normalized_request"])
            return envelope(
                db,
                task_id=task_id,
                source=source_binding(row),
                facts=data.report.model_dump(mode="json"),
            )

    def execution(self, actor: WebActor, task_id: UUID) -> dict[str, Any]:
        with connect(self.settings) as db:
            self._business(db, actor)
            visible_task(db, actor, task_id)
            row = db.execute(
                "SELECT * FROM business.executions WHERE task_id=%s", (task_id,)
            ).fetchone()
            if not row:
                raise WebFailure("NOT_READY")
            valid = db.execute(
                "SELECT business.valid_p3_execution(%s) AS valid", (row["id"],)
            ).fetchone()
            if not valid or not valid["valid"]:
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            return envelope(
                db,
                execution_id=row["id"],
                task_id=task_id,
                plan_id=row["plan_id"],
                approval_id=row["approval_id"],
                operation_key=row["operation_key"],
                request_hash=row["request_hash"],
                revalidation_snapshot_id=row["revalidation_snapshot_id"],
                status=row["status"],
                item_ids=row["item_ids"],
                completed_at=row["completed_at"],
                error_code=row["error_code"],
                sync=self._sync(db, task_id),
            )

    def plan(self, actor: WebActor, task_id: UUID, version: int) -> dict[str, Any]:
        with connect(self.settings) as db:
            self._business(db, actor)
            task = visible_task(db, actor, task_id)
            row = db.execute(
                "SELECT * FROM business.replenishment_plans WHERE task_id=%s AND version=%s",
                (task_id, version),
            ).fetchone()
            if not row:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            approval = db.execute(
                "SELECT * FROM business.approvals WHERE plan_id=%s", (row["id"],)
            ).fetchone()
            allowed = bool(approval and may_decide(db, self.config, actor, task, approval, row))
            return envelope(
                db,
                plan=self._plan(row),
                can_decide=allowed,
                nonce=nonce_for(self.config, approval) if allowed and approval else None,
                disabled_reasons=[] if allowed else ["NOT_DECIDABLE"],
            )

    @staticmethod
    def _plan(row: dict[str, Any]) -> dict[str, Any]:
        content = row["content"]
        fields = (
            "plan_id",
            "task_id",
            "plan_version",
            "hash_version",
            "source",
            "currency",
            "rule_version",
            "parameters",
            "config_version",
            "expires_at",
            "items",
            "item_count",
            "total_units",
            "required_assumptions",
            "hard_blocks",
            "quality_flags",
            "disclosure_complete",
        )
        return {
            **{k: content[k] for k in fields},
            "plan_hash": row["plan_hash"],
            "status": row["status"],
            "created_at": row["created_at"],
        }

    def approval(self, actor: WebActor, approval_id: UUID) -> dict[str, Any]:
        with connect(self.settings) as db:
            self._business(db, actor)
            row = db.execute(
                "SELECT * FROM business.approvals WHERE id=%s AND organization_id=%s",
                (approval_id, actor.organization_id),
            ).fetchone()
            if not row:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            task = visible_task(db, actor, row["task_id"])
            plan = db.execute(
                "SELECT * FROM business.replenishment_plans WHERE id=%s", (row["plan_id"],)
            ).fetchone()
            if not plan:
                raise WebFailure("NOT_READY")
            allowed = may_decide(db, self.config, actor, task, row, plan)
            decision = decision_fields(db, row)
            return envelope(
                db,
                approval={
                    "approval_id": row["id"],
                    "task_id": row["task_id"],
                    "plan_id": row["plan_id"],
                    "plan_version": row["plan_version"],
                    "plan_hash": row["plan_hash"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "expires_at": row["expires_at"],
                    "ready_at": row["ready_at"],
                    "can_decide": allowed,
                    "item_count": plan["content"]["item_count"],
                    "total_units": plan["content"]["total_units"],
                },
                plan=self._plan(plan),
                nonce=nonce_for(self.config, row) if allowed else None,
                decision=envelope(
                    db, request_key=row["decision_request_key"], duplicate=False, **decision
                )
                if decision
                else None,
                disabled_reasons=[] if allowed else ["NOT_DECIDABLE"],
            )

    def request(self, actor: WebActor, key: UUID, operation: str) -> dict[str, Any]:
        with connect(self.settings) as db:
            actor_guard(db, actor)
            row = db.execute(
                """SELECT * FROM business.web_requests WHERE principal_id=%s
            AND organization_id=%s AND operation=%s AND request_key=%s""",
                (actor.principal_id, actor.organization_id, operation, key),
            ).fetchone()
            if not row:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            if operation == "resolve":
                from commerceops.infrastructure.replenishment_items import ItemStore

                ItemStore(self.store).visible(db, actor, UUID(row["result"]["item"]["item_id"]))
            else:
                visible_task(db, actor, row["task_id"])
            return envelope(
                db,
                request_key=key,
                status="succeeded",
                receipt={"operation": operation, "result": row["result"]},
            )

    def tasks(
        self,
        actor: WebActor,
        limit: int = 20,
        state: str | None = None,
        kind: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise WebFailure("INVALID_REQUEST", 422)
        if (
            state
            and state not in STATES
            or kind
            and kind not in (TASK_KIND, "inventory_analysis_only")
        ):
            raise WebFailure("INVALID_FILTER", 400)
        with connect(self.settings) as db:
            self._business(db, actor)
            after, after_id = self.page_after(actor, "tasks", [state, kind], cursor)
            # 一个SELECT提供filtered rows/total/counts；没有先查全店数再隐藏行。
            row = db.execute(
                """WITH visible AS MATERIALIZED (
            SELECT t.* FROM business.business_tasks t WHERE t.organization_id=%s
            AND t.kind IN ('inventory_analysis_only','inventory_replenishment') AND EXISTS(
            SELECT 1 FROM business.principal_role_shop_grants g
            JOIN business.principal_shop_scopes s ON s.organization_id=g.organization_id
            AND s.shop_id=g.shop_id AND s.principal_id=g.principal_id
            JOIN business.principals p ON p.id=g.principal_id
            AND p.organization_id=g.organization_id
            WHERE g.principal_id=%s AND g.organization_id=t.organization_id AND g.shop_id=t.shop_id
            AND g.enabled AND s.enabled AND p.enabled AND g.role=ANY(p.roles)
            AND ((g.role='operator' AND t.requester_id=p.id) OR (g.role='approver'
            AND t.kind='inventory_replenishment' AND EXISTS(SELECT 1 FROM business.approvals a
            WHERE a.task_id=t.id AND p.id=ANY(a.eligible_principal_ids)))))),
            filtered AS MATERIALIZED(SELECT * FROM visible WHERE (%s::text IS NULL OR state=%s)
            AND (%s::text IS NULL OR kind=%s)) SELECT
            (SELECT COALESCE(jsonb_agg(to_jsonb(page)),'[]'::jsonb) FROM
             (SELECT * FROM filtered WHERE (%s::timestamptz IS NULL OR (created_at,id)<(%s,%s))
             ORDER BY created_at DESC,id DESC LIMIT %s) page) AS items,
            (SELECT count(*) FROM filtered) AS total,
            (SELECT COALESCE(jsonb_object_agg(state,n),'{}'::jsonb)
             FROM (SELECT state,count(*) AS n FROM filtered GROUP BY state) c) AS counts,
            clock_timestamp() AS as_of""",
                (
                    actor.organization_id,
                    actor.principal_id,
                    state,
                    state,
                    kind,
                    kind,
                    after,
                    after,
                    after_id,
                    limit + 1,
                ),
            ).fetchone()
            if not row:
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            items = row["items"][:limit]
            next_cursor = (
                self.cursor(actor, "tasks", [state, kind], items[-1])
                if len(row["items"]) > limit
                else None
            )
            summaries = []
            for item in items:
                item["id"], item["shop_id"] = UUID(item["id"]), UUID(item["shop_id"])
                summaries.append(self._summary(db, item))
            return envelope(
                db,
                items=summaries,
                total=row["total"],
                counts={s: row["counts"].get(s, 0) for s in STATES},
                as_of=row["as_of"],
                next_cursor=next_cursor,
            )

    def config_read(self, actor: WebActor, shop: UUID) -> dict[str, Any]:
        with connect(self.settings) as db:
            self._business(db, actor)
            if not any(role_scope(db, actor, shop, role) for role in ("operator", "approver")):
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            row = db.execute(
                "SELECT timezone FROM business.shops WHERE id=%s AND organization_id=%s",
                (shop, actor.organization_id),
            ).fetchone()
            if not row:
                raise WebFailure("RESOURCE_NOT_FOUND", 404)
            return envelope(
                db,
                shop_id=shop,
                config=deployment(
                    self.config,
                    row["timezone"],
                    db=db,
                    organization=actor.organization_id,
                    shops=[shop],
                ),
            )

    def operations(self, actor: WebActor) -> dict[str, Any]:
        with connect(self.settings) as db:
            if not has_capability(db, actor, "admin"):
                raise WebFailure("ACCESS_DENIED", 403)
            gates = sender_gates(db, actor.organization_id, None)
            return envelope(
                db,
                config_version=self.config.config_version,
                transport_mode=self.config.transport_mode,
                worker_state="running"
                if any(g["worker_ready"] is True for g in gates)
                else "stopped"
                if any(g["worker_ready"] is False for g in gates)
                else "unknown",
                graph_concurrency_limit=1,
                external_sender_enabled=external_enabled(gates),
                sender_gates=gates,
                recovery_scan_seconds=self.config.recovery_scan_seconds,
                approval_ttl_seconds=self.config.approval_ttl_seconds,
                revalidation_max_age_seconds=self.config.revalidation_max_age_seconds,
            )

    def plans(
        self, actor: WebActor, task_id: UUID, limit: int = 20, cursor: str | None = None
    ) -> dict[str, Any]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise WebFailure("INVALID_REQUEST", 422)
        with connect(self.settings) as db:
            self._business(db, actor)
            task = visible_task(db, actor, task_id)
            after, after_id = self.page_after(actor, "plans", str(task_id), cursor)
            row = db.execute(
                """WITH all_versions AS MATERIALIZED (
            SELECT * FROM business.replenishment_plans WHERE task_id=%s)
            SELECT (SELECT count(*) FROM all_versions) AS total,
            (SELECT COALESCE(jsonb_agg(to_jsonb(page)),'[]'::jsonb) FROM (
             SELECT * FROM all_versions WHERE (%s::timestamptz IS NULL OR (created_at,id)<(%s,%s))
             ORDER BY created_at DESC,id DESC LIMIT %s) page) AS items,
             clock_timestamp() AS as_of""",
                (task_id, after, after, after_id, limit + 1),
            ).fetchone()
            if not row:
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            page = row["items"][:limit]
            summaries = []
            for item in page:
                summaries.append(
                    {
                        "plan_id": item["id"],
                        "task_id": str(task_id),
                        "plan_version": item["version"],
                        "plan_hash": item["plan_hash"],
                        "status": item["status"],
                        "created_at": item["created_at"],
                        "expires_at": item["expires_at"],
                        "item_count": item["content"]["item_count"],
                        "total_units": item["content"]["total_units"],
                    }
                )
            current = db.execute(
                "SELECT version FROM business.replenishment_plans WHERE id=%s",
                (task["active_plan_id"],),
            ).fetchone()
            return envelope(
                db,
                items=summaries,
                current_plan_version=current["version"] if current else None,
                total=row["total"],
                as_of=row["as_of"],
                next_cursor=self.cursor(actor, "plans", str(task_id), page[-1])
                if len(row["items"]) > limit
                else None,
            )

    def events(
        self, actor: WebActor, task_id: UUID, limit: int = 20, cursor: str | None = None
    ) -> dict[str, Any]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise WebFailure("INVALID_REQUEST", 422)
        with connect(self.settings) as db:
            self._business(db, actor)
            task = visible_task(db, actor, task_id)
            source = self._source(db, task)
            related = [task_id] + (
                [source["task_id"]] if source and source["task_id"] != task_id else []
            )
            order = "occurred_at-asc/event_id-asc"
            after, after_id = self.page_after(actor, "events", str(task_id), cursor, order)
            rows = db.execute(
                """SELECT e.*,c.channel,a.decision_source FROM business.audit_events e
            JOIN business.business_tasks t ON t.id=e.task_id
            JOIN business.conversations c ON c.id=t.conversation_id
            LEFT JOIN business.approvals a ON a.id::text=e.entity_id AND e.entity_type='approval'
            WHERE e.task_id=ANY(%s) AND e.organization_id=%s
            AND e.source IN ('replenishment','inventory_analysis','feishu_delivery')
            AND (%s::timestamptz IS NULL OR (e.occurred_at,e.id)>(%s,%s))
            ORDER BY e.occurred_at,e.id LIMIT %s""",
                (related, actor.organization_id, after, after, after_id, limit + 1),
            ).fetchall()
            labels = {
                "workflow_created": "正式工作流已创建",
                "approval_prepared": "不可变计划与审批意图已保存",
                "analysis_started": "来源分析开始",
                "analysis_report_saved": "来源报告已保存",
                "analysis_failed": "来源分析失败",
            }
            page = rows[:limit]
            tools = {
                "workflow_created": ("T1", "replenishment.create_workflow"),
                "approval_prepared": ("T2", "replenishment.freeze_plan"),
                "approval_decided": ("T3", "replenishment.record_decision"),
                "execution_committed": ("T4", "replenishment.create_internal_items"),
                "item_completed": ("T6", "replenishment.complete_internal_item"),
                "item_closed": ("T6", "replenishment.close_internal_item"),
                "analysis_started": ("analysis", "inventory.analyze"),
                "analysis_report_saved": ("analysis", "inventory.persist_report"),
                "base_projection_checked": ("projection", "feishu.base.project"),
            }
            items = []
            for r in page:
                operation = tools.get(r["action"])
                reference = None
                kind = {
                    "analysis_report": "report",
                    "replenishment_item": "item",
                    "outbox": "projection",
                }.get(r["entity_type"], r["entity_type"])
                if kind in (
                    "task",
                    "report",
                    "plan",
                    "approval",
                    "execution",
                    "item",
                    "projection",
                ):
                    try:
                        reference = {"kind": kind, "id": UUID(r["entity_id"])}
                    except (ValueError, TypeError):
                        pass
                sdk = r["source"] == "feishu_delivery"
                facts = r["after_state"] if sdk and isinstance(r["after_state"], dict) else {}
                origin = r["decision_source"] or r["channel"]
                channel = origin if origin in ("web", "feishu") else "unknown"
                items.append(
                    {
                        "event_id": r["id"],
                        "occurred_at": r["occurred_at"],
                        "action": r["action"],
                        "step": operation[0] if operation else None,
                        "duration_ms": None,
                        "result_ref": reference["id"] if reference else None,
                        "safe_summary": labels.get(r["action"], "业务记录已保存"),
                        "recovery": None,
                        "record_trace_id": r["trace_id"],
                        "task_id": r["task_id"],
                        "relation": "task" if r["task_id"] == task_id else "source",
                        "channel": channel
                        if r["action"] in ("workflow_created", "approval_decided")
                        else "worker",
                        "tool": {
                            "category": "sdk_adapter" if sdk else "deterministic",
                            "name": operation[1],
                            "selected_by_model": False,
                            "sdk_method": None,
                            "verification_mode": facts.get("verification_mode")
                            if facts.get("verification_mode") in ("offline_fake", "controlled_sdk")
                            else None,
                        }
                        if operation
                        else None,
                        "references": [{"kind": "task", "id": r["task_id"]}]
                        + ([reference] if reference else []),
                        "safe_code": safe_code(facts.get("safe_code")),
                    }
                )
            last = {"created_at": page[-1]["occurred_at"], "id": page[-1]["id"]} if page else None
            return envelope(
                db,
                items=items,
                as_of=now(db),
                next_cursor=self.cursor(actor, "events", str(task_id), last, order)
                if len(rows) > limit and last
                else None,
            )

    def approvals(
        self,
        actor: WebActor,
        limit: int = 20,
        state: str | None = None,
        view: str = "visible",
        cursor: str | None = None,
    ) -> dict[str, Any]:
        statuses = ("pending", "approved", "rejected", "expired", "superseded")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise WebFailure("INVALID_REQUEST", 422)
        if state and state not in statuses or view not in ("visible", "mine", "history"):
            raise WebFailure("INVALID_FILTER", 400)
        with connect(self.settings) as db:
            self._business(db, actor)
            after, after_id = self.page_after(actor, "approvals", [state, view], cursor)
            row = db.execute(
                """WITH visible AS MATERIALIZED (
            SELECT a.*,p.content,p.status AS plan_status,t.active_plan_id,
            (a.status='pending' AND p.status='current' AND t.active_plan_id=a.plan_id
             AND t.state IN ('awaiting_approval','needs_reapproval')
             AND a.expires_at>clock_timestamp()
             AND a.nonce_key_version=%s AND %s=ANY(a.eligible_principal_ids)
             AND EXISTS(SELECT 1 FROM business.principal_role_shop_grants g
              JOIN business.principals pr ON pr.id=g.principal_id
              WHERE g.principal_id=%s AND g.organization_id=a.organization_id
              AND g.shop_id=a.shop_id AND g.role='approver' AND g.enabled
              AND pr.enabled AND 'approver'=ANY(pr.roles))) AS can_decide
            FROM business.approvals a
            JOIN business.replenishment_plans p ON p.id=a.plan_id
            JOIN business.business_tasks t ON t.id=a.task_id
            WHERE a.organization_id=%s AND EXISTS(
            SELECT 1 FROM business.principal_role_shop_grants g
            JOIN business.principal_shop_scopes s ON s.organization_id=g.organization_id
            AND s.shop_id=g.shop_id AND s.principal_id=g.principal_id
            JOIN business.principals principal ON principal.id=g.principal_id
            WHERE g.organization_id=a.organization_id AND g.shop_id=a.shop_id AND g.principal_id=%s
            AND g.enabled AND s.enabled AND principal.enabled AND g.role=ANY(principal.roles)
            AND ((g.role='operator' AND t.requester_id=g.principal_id)
            OR (g.role='approver' AND g.principal_id=ANY(a.eligible_principal_ids))))),
            filtered AS MATERIALIZED (SELECT * FROM visible WHERE (%s::text IS NULL OR status=%s)
            AND (%s<>'history' OR status<>'pending') AND (%s<>'mine' OR can_decide))
            SELECT (SELECT count(*) FROM filtered) AS total,
            (SELECT COALESCE(jsonb_agg(to_jsonb(page)),'[]'::jsonb) FROM (
             SELECT * FROM filtered WHERE (%s::timestamptz IS NULL OR (created_at,id)<(%s,%s))
             ORDER BY created_at DESC,id DESC LIMIT %s) page) AS items,
            (SELECT COALESCE(jsonb_object_agg(status,n),'{}'::jsonb)
             FROM (SELECT status,count(*) AS n FROM filtered GROUP BY status) c) AS counts,
            clock_timestamp() AS as_of""",
                (
                    self.config.key_version,
                    actor.principal_id,
                    actor.principal_id,
                    actor.organization_id,
                    actor.principal_id,
                    state,
                    state,
                    view,
                    view,
                    after,
                    after,
                    after_id,
                    limit + 1,
                ),
            ).fetchone()
            if not row:
                raise WebFailure("SERVICE_UNAVAILABLE", 503)
            page = row["items"][:limit]
            items = [
                {
                    "approval_id": r["id"],
                    "task_id": r["task_id"],
                    "plan_id": r["plan_id"],
                    "plan_version": r["plan_version"],
                    "plan_hash": r["plan_hash"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "expires_at": r["expires_at"],
                    "ready_at": r["ready_at"],
                    "can_decide": r["can_decide"],
                    "item_count": r["content"]["item_count"],
                    "total_units": r["content"]["total_units"],
                }
                for r in page
            ]
            return envelope(
                db,
                items=items,
                total=row["total"],
                as_of=row["as_of"],
                counts={s: row["counts"].get(s, 0) for s in statuses},
                next_cursor=self.cursor(actor, "approvals", [state, view], page[-1])
                if len(row["items"]) > limit
                else None,
            )
