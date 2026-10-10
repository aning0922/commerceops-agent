"""T4唯一确定性authority；重观测事务外，整计划提交独立于checkpoint。"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from commerceops.application.commerce.analysis_task import CollectedInventory, InventoryTaskRequest
from commerceops.application.commerce.inventory_facts import (
    InventoryInput,
    InventoryReport,
    OpenWorkItemInput,
)
from commerceops.application.replenishment.contracts import (
    WORKFLOW_VERSION,
    DecisionInput,
    Parameters,
    WebFailure,
)
from commerceops.application.replenishment.decisions import confirm_set, decision_hash
from commerceops.application.replenishment.execution import (
    execution_hash,
    material_hash,
    operation_key,
    verified_observation,
)
from commerceops.application.replenishment.planning import PlanRejected, freeze_plan
from commerceops.application.replenishment.security import approval_nonce, digest
from commerceops.application.runner import RunRequest
from commerceops.domain.commerce_values import canonical_bytes, facts_hash, utc_time
from commerceops.infrastructure.approval_decisions import nonce_for
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe, _stored
from commerceops.infrastructure.replenishment_repository import (
    SOURCE_SQL,
    ApprovalStore,
    parameters_of,
    source_binding,
)
from commerceops.infrastructure.worker_lock import open_async
from commerceops.workflows.inventory_analysis import CollectorFactory

DB = AsyncConnection[dict[str, Any]]


def transition_digest(value: dict[str, Any]) -> str:
    fields = (
        "decision_id",
        "organization_id",
        "shop_id",
        "task_id",
        "old_plan_id",
        "old_approval_id",
        "old_plan_version",
        "old_plan_hash",
        "observation_id",
        "next_plan_id",
        "next_approval_id",
        "next_plan_version",
        "cause_job_id",
    )
    return facts_hash(
        {key: str(value[key]) if isinstance(value[key], UUID) else value[key] for key in fields}
    )


class RevalidationRequired(ValueError):
    pass


async def clock(db: DB) -> Any:
    cur = await db.execute("SELECT clock_timestamp() AS time")
    row = await cur.fetchone()
    if not row:
        raise AnalysisUnsafe("P3_CLOCK_UNAVAILABLE")
    return utc_time(row["time"])


class ExecutionStore:
    def __init__(self, store: ApprovalStore, collector_factory: CollectorFactory | None):
        self.store, self.config, self.settings = store, store.config, store.settings
        self.session, self.factory = store.session, collector_factory

    async def hook(self, point: str) -> None:
        if self.store.hook:
            await self.store.hook(point)

    @asynccontextmanager
    async def locked(
        self, r: RunRequest, state: dict[str, Any]
    ) -> AsyncIterator[tuple[DB, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]]:
        await self.session.check()
        if set(state) - {
            "workflow_version",
            "task_id",
            "request_hash",
            "plan_id",
            "approval_id",
            "plan_hash",
            "plan_version",
            "outcome",
            "decision_id",
            "decision_hash",
            "revalidation_snapshot_id",
            "execution_id",
            "failure_code",
        }:
            raise AnalysisUnsafe("P3_UNTRUSTED_CHECKPOINT_AUTHORITY_FIELD")
        if (
            r.owner != self.session.owner
            or r.workflow_version != WORKFLOW_VERSION
            or r.thread_id != str(r.task_id)
        ):
            raise AnalysisUnsafe("P3_EXECUTION_OWNER_UNSAFE")
        async with await open_async(self.settings) as db, db.transaction():
            cur = await db.execute(
                """SELECT * FROM business.business_tasks WHERE id=%s
                AND organization_id=%s AND shop_id=%s AND kind='inventory_replenishment'
                AND workflow_version=%s FOR UPDATE""",
                (r.task_id, r.organization_id, r.shop_id, WORKFLOW_VERSION),
            )
            task = await cur.fetchone()
            if not task or any(
                state.get(k) != v
                for k, v in {
                    "workflow_version": WORKFLOW_VERSION,
                    "task_id": str(r.task_id),
                    "request_hash": facts_hash(task["normalized_request"]),
                }.items()
            ):
                raise AnalysisUnsafe("P3_EXECUTION_TASK_BINDING_UNSAFE")
            cur = await db.execute(
                """SELECT * FROM business.replenishment_plans WHERE id=%s
                AND task_id=%s AND organization_id=%s AND shop_id=%s FOR UPDATE""",
                (UUID(state["plan_id"]), r.task_id, r.organization_id, r.shop_id),
            )
            plan = await cur.fetchone()
            cur = await db.execute(
                """SELECT * FROM business.approvals WHERE id=%s
                AND task_id=%s AND organization_id=%s AND shop_id=%s FOR UPDATE""",
                (UUID(state["approval_id"]), r.task_id, r.organization_id, r.shop_id),
            )
            approval = await cur.fetchone()
            if (
                not plan
                or not approval
                or approval["plan_id"] != plan["id"]
                or (
                    plan["version"],
                    plan["plan_hash"],
                    str(approval["decision_id"]),
                    approval["decision_payload_hash"],
                )
                != (
                    state.get("plan_version"),
                    state.get("plan_hash"),
                    state.get("decision_id"),
                    state.get("decision_hash"),
                )
                or type(state.get("plan_version")) is not int
            ):
                raise AnalysisUnsafe("P3_EXECUTION_PLAN_DECISION_UNSAFE")
            cur = await db.execute(
                """SELECT 1 FROM business.jobs j
                JOIN business.approval_resumes x ON x.decision_id=%s AND
 x.approval_id=%s
                WHERE j.id=%s AND j.task_id=%s AND j.organization_id=%s AND j.shop_id=%s
                AND j.status='running' AND j.lease_owner=%s AND j.kind=%s AND
 j.payload_ref=%s
                AND ((j.kind='resume' AND j.id=x.job_id AND
 j.payload_ref='decision:'||x.decision_id::text)
                OR (j.kind='recover' AND j.id=x.continuation_job_id
                AND j.payload_ref='continue:'||x.decision_id::text)) FOR SHARE OF j""",
                (
                    approval["decision_id"],
                    approval["id"],
                    r.job_id,
                    r.task_id,
                    r.organization_id,
                    r.shop_id,
                    r.owner,
                    r.kind,
                    r.payload_ref,
                ),
            )
            if not await cur.fetchone():
                raise AnalysisUnsafe("P3_EXECUTION_REGISTERED_JOB_REQUIRED")
            cur = await db.execute(
                "SELECT * FROM business.p3_task_sources WHERE task_id=%s", (r.task_id,)
            )
            binding = await cur.fetchone()
            if not binding:
                raise AnalysisUnsafe("P3_EXECUTION_SOURCE_MISSING")
            yield db, task, plan, approval, binding
            await self.session.check()

    @staticmethod
    async def existing(
        db: DB, plan: dict[str, Any], approval: dict[str, Any]
    ) -> dict[str, Any] | None:
        cur = await db.execute(
            "SELECT * FROM business.executions WHERE operation_key=%s", (operation_key(plan),)
        )
        row = await cur.fetchone()
        if row:
            cur = await db.execute("SELECT business.valid_p3_execution(%s) AS valid", (row["id"],))
            valid = await cur.fetchone()
            if (
                row["request_hash"] != execution_hash(plan, approval)
                or not valid
                or not valid["valid"]
            ):
                raise AnalysisUnsafe("P3_EXECUTION_RECEIPT_CONFLICT")
        return row

    async def authorize_new(
        self, db: DB, task: dict[str, Any], plan: dict[str, Any], approval: dict[str, Any]
    ) -> None:
        if (
            task["state"] not in ("executing", "needs_attention")
            or task["active_plan_id"] != plan["id"]
            or plan["status"] != "current"
            or approval["status"] != "approved"
            or approval["consumed_at"] is not None
        ):
            raise AnalysisUnsafe("P3_EXECUTION_NOT_CURRENT")
        if (
            task["state"] == "needs_attention"
            and task["failure_code"] != "WORKER_TERMINATION_UNCONFIRMED"
        ):
            raise AnalysisUnsafe("P3_EXECUTION_ATTENTION_BLOCKED")
        cur = await db.execute(
            "SELECT business.lock_p3_permission(%s,%s,%s,%s,%s,'approver') AS allowed",
            (
                approval["decided_by"],
                task["organization_id"],
                task["shop_id"],
                approval["decided_identity_id"],
                approval["decided_auth_version"],
            ),
        )
        row = await cur.fetchone()
        if (
            not row
            or not row["allowed"]
            or approval["decided_by"] not in approval["eligible_principal_ids"]
        ):
            raise AnalysisUnsafe("P3_EXECUTION_PERMISSION_REVOKED")
        request = DecisionInput.model_validate_json(
            json.dumps(
                {
                    "schema_version": "p3-web-v1",
                    "request_key": str(approval["decision_request_key"]),
                    "approval_id": str(approval["id"]),
                    "plan_id": str(plan["id"]),
                    "plan_version": plan["version"],
                    "plan_hash": plan["plan_hash"],
                    "action": approval["decision_action"],
                    "acknowledged_assumption_keys": approval["acknowledged_assumption_keys"],
                    "nonce": nonce_for(self.config, approval),
                }
            )
        )
        confirm_set(request, plan["content"])
        if (
            request.action not in ("approve", "approve_with_assumptions")
            or decision_hash(request) != approval["decision_payload_hash"]
            or plan["plan_hash"] != facts_hash(plan["content"])
            or canonical_bytes(plan["content"]).decode() != plan["canonical_content"]
        ):
            raise AnalysisUnsafe("P3_EXECUTION_CONFIRMATION_UNSAFE")
        if await clock(db) >= approval["expires_at"]:
            raise AnalysisUnsafe("P3_EXECUTION_APPROVAL_EXPIRED")

    async def evidence(
        self, db: DB, task: dict[str, Any], plan: dict[str, Any], binding: dict[str, Any]
    ) -> tuple[InventoryInput, InventoryReport]:
        cur = await db.execute(
            SOURCE_SQL, (binding["source_task_id"], task["organization_id"], task["shop_id"])
        )
        source = await cur.fetchone()
        if (
            not source
            or source["source_state"] != "completed"
            or (source["id"], source["snapshot_id"], source["facts_hash"])
            != (binding["source_report_id"], binding["snapshot_id"], binding["facts_hash"])
        ):
            raise AnalysisUnsafe("P3_ORIGINAL_SOURCE_UNSAFE")
        original = _stored(source, source["normalized_request"])
        Parameters.model_validate(binding["parameters"])
        if binding["parameters"] != parameters_of(source) or (
            original.report.L,
            original.report.R,
            original.report.S,
        ) != (binding["parameters"]["L"], binding["parameters"]["R"], binding["parameters"]["S"]):
            raise AnalysisUnsafe("P3_FROZEN_PARAMETER_SOURCE_UNSAFE")
        if plan["evidence_kind"] == "p2_original":
            if plan["content"]["config_version"] != binding["config_version"]:
                raise AnalysisUnsafe("P3_ORIGINAL_CONFIG_SOURCE_UNSAFE")
            if (plan["report_id"], plan["snapshot_id"], plan["facts_hash"]) != (
                original.report_id,
                original.snapshot_id,
                original.report.facts_hash,
            ):
                raise AnalysisUnsafe("P3_PLAN_ORIGINAL_EVIDENCE_UNSAFE")
            data = InventoryInput.model_validate_json(json.dumps(source["snapshot_content"]))
            self.verify_plan(plan, binding, original.report, source_binding(source))
            return data, original.report
        if plan["evidence_kind"] != "p3_observation":
            raise AnalysisUnsafe("P3_EVIDENCE_KIND_UNSAFE")
        cur = await db.execute(
            """SELECT * FROM business.p3_observations WHERE id=%s AND task_id=%s AND
 organization_id=%s AND shop_id=%s""",
            (plan["p3_observation_id"], task["id"], task["organization_id"], task["shop_id"]),
        )
        row = await cur.fetchone()
        if not row or (
            row["report_id"],
            row["id"],
            row["facts_hash"],
            row["generation_plan_id"],
            row["generation_plan_version"],
        ) != (
            plan["report_id"],
            plan["snapshot_id"],
            plan["facts_hash"],
            plan["id"],
            plan["version"],
        ):
            raise AnalysisUnsafe("P3_PLAN_OBSERVATION_UNSAFE")
        data, report = self.verify_row(row, binding)
        if plan["content"]["config_version"] != row["generation_config_version"]:
            raise AnalysisUnsafe("P3_OBSERVATION_CONFIG_SOURCE_UNSAFE")
        self.verify_plan(plan, binding, report, self.source(row))
        return data, report

    @staticmethod
    def verify_plan(
        plan: dict[str, Any],
        binding: dict[str, Any],
        report: InventoryReport,
        source: dict[str, Any],
    ) -> None:
        frozen = freeze_plan(
            organization_id=plan["organization_id"],
            shop_id=plan["shop_id"],
            task_id=plan["task_id"],
            plan_id=plan["id"],
            version=plan["version"],
            source=source,
            report=report,
            expires_at=plan["expires_at"],
            parameters=binding["parameters"],
            config_version=plan["content"]["config_version"],
            max_items=20,
        )
        if (
            frozen is None
            or frozen.plan_hash != plan["plan_hash"]
            or frozen.canonical_content != plan["canonical_content"]
        ):
            raise AnalysisUnsafe("P3_PLAN_DETERMINISTIC_EVIDENCE_UNSAFE")

    @staticmethod
    def verify_row(
        row: dict[str, Any], binding: dict[str, Any]
    ) -> tuple[InventoryInput, InventoryReport]:
        if (
            row["source_task_id"],
            row["original_report_id"],
            row["original_snapshot_id"],
            row["original_facts_hash"],
        ) != (
            binding["source_task_id"],
            binding["source_report_id"],
            binding["snapshot_id"],
            binding["facts_hash"],
        ):
            raise AnalysisUnsafe("P3_OBSERVATION_LINEAGE_UNSAFE")
        data = InventoryInput.model_validate_json(row["canonical_input"])
        saved = InventoryReport.model_validate_json(row["canonical_report"])
        _, report, normalized = verified_observation(
            CollectedInventory(data, row["collection_started_at"], row["collected_at"]),
            row["parameters"],
        )
        if (
            saved != report
            or canonical_bytes(normalized).decode() != row["canonical_input"]
            or facts_hash(normalized) != row["input_hash"]
            or facts_hash(saved.model_dump(mode="json")) != row["report_hash"]
            or saved.facts_hash != row["facts_hash"]
            or material_hash(data, row["parameters"]) != row["material_hash"]
        ):
            raise AnalysisUnsafe("P3_OBSERVATION_TYPED_HASH_UNSAFE")
        return data, saved

    async def collect(self, parameters: dict[str, Any], r: RunRequest) -> CollectedInventory:
        if self.factory is None:
            raise AnalysisUnsafe("P3_REVALIDATION_SOURCE_UNAVAILABLE")
        await self.hook("before_revalidation_collection")
        async with asyncio.timeout(20):
            collected = await self.factory(
                InventoryTaskRequest.model_validate(parameters)
            ).collect()
        async with await open_async(self.settings) as db:
            stamp = await clock(db)
            if (
                collected.collected_at > stamp
                or stamp - collected.collected_at
                > timedelta(seconds=self.config.revalidation_max_age_seconds)
                or collected.collected_at < collected.collection_started_at
            ):
                raise AnalysisUnsafe("P3_REVALIDATION_COLLECTION_STALE")
            cur = await db.execute(
                """SELECT id,sku_key,stock_pool_key,quantity FROM business.replenishment_items WHERE
 organization_id=%s AND shop_id=%s AND status='open' ORDER BY stock_pool_key,id""",
                (r.organization_id, r.shop_id),
            )
            rows = await cur.fetchall()
            internal = tuple(
                OpenWorkItemInput(
                    item_id=str(x["id"]),
                    sku_key=x["sku_key"],
                    stock_pool_key=x["stock_pool_key"],
                    quantity=int(x["quantity"]),
                    status="open",
                    source_kind="mock",
                )
                for x in rows
            )
            data = collected.data.model_copy(
                update={"open_items": tuple(collected.data.open_items) + internal}
            )
            result = CollectedInventory(data, collected.collection_started_at, stamp)
        await self.hook("after_revalidation_collection")
        return result

    async def save_observation(
        self,
        db: DB,
        r: RunRequest,
        binding: dict[str, Any],
        collected: CollectedInventory,
        generation: UUID,
        version: int,
        identities: tuple[UUID, UUID] | None = None,
    ) -> dict[str, Any]:
        data, report, normalized = verified_observation(collected, binding["parameters"])
        raw = canonical_bytes(normalized).decode()
        report_body = report.model_dump(mode="json")
        canonical_report = canonical_bytes(report_body).decode()
        cur = await db.execute(
            """INSERT INTO business.p3_observations(id,report_id,organization_id,
            shop_id,task_id,source_task_id,original_report_id,original_snapshot_id,
 original_facts_hash,
            generation_plan_id,generation_plan_version,generation_config_version,
            schema_version,hash_version,parameters,input,
            canonical_input,input_hash,report,canonical_report,report_hash,facts_hash,
 canonical_facts,
            material_hash,collection_started_at,collected_at,consistency)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'p3-observation-v1',
 'canonical-facts-v1',%s,%s,
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'observational') RETURNING *""",
            (
                identities[0] if identities else uuid4(),
                identities[1] if identities else uuid4(),
                r.organization_id,
                r.shop_id,
                r.task_id,
                binding["source_task_id"],
                binding["source_report_id"],
                binding["snapshot_id"],
                binding["facts_hash"],
                generation,
                version,
                self.config.config_version,
                Jsonb(binding["parameters"]),
                Jsonb(normalized),
                raw,
                facts_hash(normalized),
                Jsonb(report_body),
                canonical_report,
                facts_hash(report_body),
                report.facts_hash,
                report.canonical_bytes().decode(),
                material_hash(data, binding["parameters"]),
                collected.collection_started_at,
                collected.collected_at,
            ),
        )
        row = await cur.fetchone()
        if not row:
            raise AnalysisUnsafe("P3_OBSERVATION_MISSING")
        return row

    @staticmethod
    def source(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_task_id": str(row["source_task_id"]),
            "report_id": str(row["report_id"]),
            "snapshot_id": str(row["id"]),
            "facts_hash": row["facts_hash"],
            "collected_at": row["collected_at"],
            "collection_started_at": row["collection_started_at"],
            "source_complete": row["report"]["source_complete"],
            "consistency": "observational",
        }

    @staticmethod
    async def audit(
        db: DB, r: RunRequest, actor: UUID, action: str, entity: str, identifier: UUID
    ) -> None:
        await db.execute(
            """INSERT INTO business.audit_events(id,organization_id,task_id,actor_id,
            source,action,entity_type,entity_id,trace_id) VALUES(%s,%s,%s,%s,
 'replenishment',%s,%s,%s,%s)""",
            (
                uuid4(),
                r.organization_id,
                r.task_id,
                actor,
                action,
                entity,
                str(identifier),
                uuid4(),
            ),
        )

    async def revalidate(self, r: RunRequest, state: dict[str, Any]) -> dict[str, Any]:
        async with self.locked(r, state) as (db, task, plan, approval, binding):
            receipt = await self.existing(db, plan, approval)
            if receipt:
                return {"outcome": "executed", "execution_id": str(receipt["id"])}
            replacement = await self.replacement(db, r, state, task, plan, approval)
            if replacement:
                return replacement
            refused = await self.checked_new(db, r, task, plan, approval)
            if refused:
                return refused
            await self.evidence(db, task, plan, binding)
            parameters = dict(binding["parameters"])
        collected = await self.collect(parameters, r)
        data, report, _ = verified_observation(collected, parameters)
        async with self.locked(r, state) as (db, task, plan, approval, binding):
            receipt = await self.existing(db, plan, approval)
            if receipt:
                return {"outcome": "executed", "execution_id": str(receipt["id"])}
            replacement = await self.replacement(db, r, state, task, plan, approval)
            if replacement:
                return replacement
            refused = await self.checked_new(db, r, task, plan, approval)
            if refused:
                return refused
            previous, _ = await self.evidence(db, task, plan, binding)
            if (
                not report.complete
                or not report.source_complete
                or any(x.hard_blocks for x in report.items)
            ):
                observation = await self.save_observation(
                    db, r, binding, collected, plan["id"], plan["version"]
                )
                return await self.fail(
                    db, r, task, plan, approval, "DATA_INCOMPLETE", observation["id"]
                )
            if report.scope_required or report.candidate_count > self.config.max_plan_items:
                observation = await self.save_observation(
                    db, r, binding, collected, plan["id"], plan["version"]
                )
                return await self.fail(
                    db, r, task, plan, approval, "SCOPE_REQUIRED", observation["id"]
                )
            # 库存池排序锁也用于版本化决定，旧确认不会沿用到新计划。
            pools = {x["stock_pool_key"] for x in plan["content"]["items"]}
            pools.update(x.stock_pool_key for x in report.items if x.stock_pool_key is not None)
            for pool in sorted(pools):
                await db.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    (f"p3-pool:{r.shop_id}:{pool}",),
                )
            stamp = await clock(db)
            if stamp >= approval["expires_at"]:
                return await self.fail(db, r, task, plan, approval, "P3_EXECUTION_APPROVAL_EXPIRED")
            if stamp - collected.collected_at > timedelta(
                seconds=self.config.revalidation_max_age_seconds
            ):
                raise RevalidationRequired("P3_REVALIDATION_LOCK_WAIT_STALE")
            if material_hash(previous, parameters) != material_hash(data, parameters):
                return await self.replace(db, r, task, plan, approval, binding, collected, report)
            observation = await self.save_observation(
                db, r, binding, collected, plan["id"], plan["version"]
            )
            await self.audit(
                db,
                r,
                approval["decided_by"],
                "execution_revalidated",
                "snapshot",
                observation["id"],
            )
            return {
                "outcome": "execution_ready",
                "revalidation_snapshot_id": str(observation["id"]),
            }

    async def replacement(
        self,
        db: DB,
        r: RunRequest,
        state: dict[str, Any],
        task: dict[str, Any],
        plan: dict[str, Any],
        approval: dict[str, Any],
    ) -> dict[str, Any] | None:
        cur = await db.execute(
            "SELECT * FROM business.p3_revalidation_failures WHERE decision_id=%s",
            (approval["decision_id"],),
        )
        failure = await cur.fetchone()
        if failure:
            if (
                failure["plan_id"] != plan["id"]
                or failure["approval_id"] != approval["id"]
                or task["active_plan_id"] != plan["id"]
                or plan["status"] != "invalidated"
                or task["failure_code"] != failure["reason_code"]
            ):
                raise AnalysisUnsafe("P3_REVALIDATION_FAILURE_BINDING_UNSAFE")
            return {"outcome": "revalidation_blocked", "failure_code": failure["reason_code"]}
        cur = await db.execute(
            "SELECT * FROM business.p3_revalidation_transitions WHERE decision_id=%s",
            (approval["decision_id"],),
        )
        transition = await cur.fetchone()
        if not transition:
            return None
        if (
            transition["transition_hash"] != transition_digest(transition)
            or (
                transition["old_plan_id"],
                transition["old_approval_id"],
                transition["old_plan_version"],
                transition["old_plan_hash"],
                transition["task_id"],
                transition["shop_id"],
                transition["organization_id"],
            )
            != (
                plan["id"],
                approval["id"],
                plan["version"],
                plan["plan_hash"],
                r.task_id,
                r.shop_id,
                r.organization_id,
            )
            or task["active_plan_id"] != transition["next_plan_id"]
            or plan["status"] != "superseded"
            or approval["consumed_at"] is not None
            or transition["applied_at"] is not None
        ):
            raise AnalysisUnsafe("P3_REPLACEMENT_CHECKPOINT_UNSAFE")
        cur = await db.execute(
            """SELECT p.*,a.id AS next_approval_id FROM business.replenishment_plans p JOIN
 business.approvals a ON a.plan_id=p.id WHERE p.id=%s AND p.task_id=%s AND
 p.organization_id=%s AND p.shop_id=%s""",
            (transition["next_plan_id"], r.task_id, r.organization_id, r.shop_id),
        )
        target = await cur.fetchone()
        if (
            not target
            or target["next_approval_id"] != transition["next_approval_id"]
            or target["version"] != plan["version"] + 1
            or target["evidence_kind"] != "p3_observation"
            or target["p3_observation_id"] != transition["observation_id"]
            or target["plan_hash"] != facts_hash(target["content"])
        ):
            raise AnalysisUnsafe("P3_REPLACEMENT_TARGET_UNSAFE")
        return {
            "plan_id": str(target["id"]),
            "approval_id": str(target["next_approval_id"]),
            "plan_version": target["version"],
            "plan_hash": target["plan_hash"],
            "outcome": "awaiting_approval",
            "decision_id": "",
            "decision_hash": "",
            "revalidation_snapshot_id": "",
            "execution_id": "",
        }

    async def checked_new(
        self,
        db: DB,
        r: RunRequest,
        task: dict[str, Any],
        plan: dict[str, Any],
        approval: dict[str, Any],
    ) -> dict[str, Any] | None:
        try:
            await self.authorize_new(db, task, plan, approval)
        except AnalysisUnsafe as error:
            if str(error) not in (
                "P3_EXECUTION_PERMISSION_REVOKED",
                "P3_EXECUTION_APPROVAL_EXPIRED",
            ):
                raise
            return await self.fail(db, r, task, plan, approval, str(error))
        except WebFailure as error:
            if error.code != "SERVICE_UNAVAILABLE":
                raise
            return await self.fail(db, r, task, plan, approval, "P3_NONCE_KEY_UNAVAILABLE")
        return None

    async def replace(
        self,
        db: DB,
        r: RunRequest,
        task: dict[str, Any],
        plan: dict[str, Any],
        approval: dict[str, Any],
        binding: dict[str, Any],
        collected: CollectedInventory,
        report: InventoryReport,
    ) -> dict[str, Any]:
        stamp = await clock(db)
        next_plan, next_approval = uuid4(), uuid4()
        snapshot, report_id = uuid4(), uuid4()
        version = plan["version"] + 1
        expires = stamp + timedelta(seconds=self.config.approval_ttl_seconds)
        source = {
            "source_task_id": str(binding["source_task_id"]),
            "report_id": str(report_id),
            "snapshot_id": str(snapshot),
            "facts_hash": report.facts_hash,
            "collected_at": collected.collected_at,
            "collection_started_at": collected.collection_started_at,
            "source_complete": report.source_complete,
            "consistency": "observational",
        }
        try:
            frozen = freeze_plan(
                organization_id=r.organization_id,
                shop_id=r.shop_id,
                task_id=r.task_id,
                plan_id=next_plan,
                version=version,
                source=source,
                report=report,
                expires_at=expires,
                parameters=binding["parameters"],
                config_version=self.config.config_version,
                max_items=self.config.max_plan_items,
            )
            if frozen is None:
                raise PlanRejected("NO_ACTION_AFTER_REVALIDATION")
        except PlanRejected as error:
            observation = await self.save_observation(
                db, r, binding, collected, plan["id"], plan["version"]
            )
            return await self.fail(db, r, task, plan, approval, str(error), observation["id"])
        observation = await self.save_observation(
            db, r, binding, collected, next_plan, version, (snapshot, report_id)
        )
        cur = await db.execute(
            """SELECT p.id FROM business.principals p
            JOIN business.principal_role_shop_grants g ON g.principal_id=p.id AND
 g.organization_id=p.organization_id
            JOIN business.principal_shop_scopes s ON
 s.organization_id=g.organization_id AND s.shop_id=g.shop_id
             AND s.principal_id=g.principal_id WHERE p.organization_id=%s AND
 g.shop_id=%s
            AND p.enabled AND s.enabled AND g.enabled AND g.role='approver' AND
 'approver'=ANY(p.roles)
            ORDER BY p.id FOR SHARE OF p""",
            (r.organization_id, r.shop_id),
        )
        eligible = [x["id"] for x in await cur.fetchall()]
        await db.execute(
            """UPDATE business.replenishment_plans SET status='superseded' WHERE id=%s AND
 status='current'""",
            (plan["id"],),
        )
        await db.execute(
            """INSERT INTO business.replenishment_plans(id,organization_id,shop_id,task_id,
            version,source_task_id,report_id,snapshot_id,facts_hash,plan_hash,content,
 canonical_content,
            expires_at,evidence_kind,p3_observation_id) VALUES(%s,%s,%s,%s,%s,%s,%s,
 %s,%s,%s,%s,%s,%s,
            'p3_observation',%s)""",
            (
                next_plan,
                r.organization_id,
                r.shop_id,
                r.task_id,
                version,
                binding["source_task_id"],
                report_id,
                snapshot,
                report.facts_hash,
                frozen.plan_hash,
                Jsonb(frozen.content),
                frozen.canonical_content,
                expires,
                observation["id"],
            ),
        )
        nonce = approval_nonce(
            self.config.nonce_secret, next_approval, next_plan, version, frozen.plan_hash, expires
        )
        await db.execute(
            """INSERT INTO business.approvals(id,organization_id,shop_id,task_id,plan_id,
            plan_version,plan_hash,eligible_principal_ids,nonce_hash,
 nonce_key_version,expires_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                next_approval,
                r.organization_id,
                r.shop_id,
                r.task_id,
                next_plan,
                version,
                frozen.plan_hash,
                eligible,
                digest(nonce),
                self.config.key_version,
                expires,
            ),
        )
        payload = {
            "schema_version": "p3-web-v1",
            "approval_id": str(next_approval),
            "plan_id": str(next_plan),
            "plan_version": version,
            "plan_hash": frozen.plan_hash,
        }
        await db.execute(
            """INSERT INTO business.outbox(id,organization_id,shop_id,task_id,destination,
            aggregate_id,aggregate_version,operation,dedupe_key,request_hash,payload,
            provider_idempotency_key,status) VALUES(%s,%s,%s,%s,'feishu_card',%s,%s,
            'approval_card',%s,%s,%s,%s,'blocked')""",
            (
                uuid4(),
                r.organization_id,
                r.shop_id,
                r.task_id,
                next_approval,
                version,
                f"card:{next_approval}:{version}",
                facts_hash(payload),
                Jsonb(payload),
                uuid4(),
            ),
        )
        transition = {
            "decision_id": approval["decision_id"],
            "organization_id": r.organization_id,
            "shop_id": r.shop_id,
            "task_id": r.task_id,
            "old_plan_id": plan["id"],
            "old_approval_id": approval["id"],
            "old_plan_version": plan["version"],
            "old_plan_hash": plan["plan_hash"],
            "observation_id": snapshot,
            "next_plan_id": next_plan,
            "next_approval_id": next_approval,
            "next_plan_version": version,
            "cause_job_id": r.job_id,
        }
        await db.execute(
            """INSERT INTO business.p3_revalidation_transitions(decision_id,organization_id,
            shop_id,task_id,old_plan_id,old_approval_id,old_plan_version,
 old_plan_hash,observation_id,
            next_plan_id,next_approval_id,next_plan_version,cause_job_id,
 transition_hash)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                *transition.values(),
                transition_digest(transition),
            ),
        )
        await db.execute(
            """UPDATE business.business_tasks SET active_plan_id=%s,state='needs_reapproval',
            failure_code='PLAN_CHANGED',version=version+1,
 updated_at=clock_timestamp() WHERE id=%s""",
            (next_plan, r.task_id),
        )
        await self.audit(
            db, r, approval["decided_by"], "plan_reapproval_required", "plan", next_plan
        )
        await self.hook("before_replacement_commit")
        return {
            "plan_id": str(next_plan),
            "approval_id": str(next_approval),
            "plan_version": version,
            "plan_hash": frozen.plan_hash,
            "outcome": "awaiting_approval",
            "decision_id": "",
            "decision_hash": "",
            "revalidation_snapshot_id": "",
            "execution_id": "",
        }

    async def fail(
        self,
        db: DB,
        r: RunRequest,
        task: dict[str, Any],
        plan: dict[str, Any],
        approval: dict[str, Any],
        reason: str,
        observation: UUID | None = None,
    ) -> dict[str, Any]:
        await db.execute(
            """UPDATE business.replenishment_plans SET status='invalidated' WHERE id=%s AND
 status='current'""",
            (plan["id"],),
        )
        await db.execute(
            """INSERT INTO business.p3_revalidation_failures(decision_id,organization_id,
            shop_id,task_id,approval_id,plan_id,observation_id,reason_code) VALUES(%s,
 %s,%s,%s,%s,%s,%s,%s)""",
            (
                approval["decision_id"],
                r.organization_id,
                r.shop_id,
                r.task_id,
                approval["id"],
                plan["id"],
                observation,
                reason,
            ),
        )
        await db.execute(
            """UPDATE business.business_tasks SET state='needs_reapproval',failure_code=%s,
            version=version+1,updated_at=clock_timestamp() WHERE id=%s""",
            (reason, r.task_id),
        )
        await self.audit(
            db, r, approval["decided_by"], "execution_revalidation_blocked", "plan", plan["id"]
        )
        return {"outcome": "revalidation_blocked", "failure_code": reason}

    async def execute(self, r: RunRequest, state: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any]
        async with self.locked(r, state) as (db, task, plan, approval, binding):
            receipt = await self.existing(db, plan, approval)
            if receipt:
                return {"outcome": "executed", "execution_id": str(receipt["id"])}
            refused = await self.checked_new(db, r, task, plan, approval)
            if refused:
                return refused
            previous, _ = await self.evidence(db, task, plan, binding)
            cur = await db.execute(
                """SELECT * FROM business.p3_observations WHERE id=%s AND task_id=%s AND
 organization_id=%s AND shop_id=%s""",
                (UUID(state["revalidation_snapshot_id"]), r.task_id, r.organization_id, r.shop_id),
            )
            observation = await cur.fetchone()
            if not observation or (
                observation["generation_plan_id"],
                observation["generation_plan_version"],
            ) != (plan["id"], plan["version"]):
                raise AnalysisUnsafe("P3_EXECUTION_OBSERVATION_BINDING_UNSAFE")
            current, report = self.verify_row(observation, binding)
            if material_hash(previous, binding["parameters"]) != material_hash(
                current, binding["parameters"]
            ):
                raise AnalysisUnsafe("P3_EXECUTION_MATERIAL_CHANGED")
            if (
                not report.complete
                or not report.source_complete
                or report.scope_required
                or any(x.hard_blocks for x in report.items)
            ):
                raise AnalysisUnsafe("P3_EXECUTION_QUALITY_BLOCKED")
            for pool in sorted(x["stock_pool_key"] for x in plan["content"]["items"]):
                await db.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    (f"p3-pool:{r.shop_id}:{pool}",),
                )
                cur = await db.execute(
                    """SELECT id FROM business.replenishment_items
 WHERE shop_id=%s AND stock_pool_key=%s AND status='open'""",
                    (r.shop_id, pool),
                )
                if await cur.fetchone():
                    return await self.fail(
                        db, r, task, plan, approval, "OPEN_POOL_CONFLICT", observation["id"]
                    )
            stamp = await clock(db)
            if stamp >= approval["expires_at"]:
                raise AnalysisUnsafe("P3_EXECUTION_APPROVAL_EXPIRED")
            if observation["collected_at"] > stamp or stamp - observation[
                "collected_at"
            ] > timedelta(seconds=self.config.revalidation_max_age_seconds):
                raise RevalidationRequired("P3_EXECUTION_OBSERVATION_STALE")
            identifier = uuid4()
            await db.execute(
                """INSERT INTO business.executions(id,organization_id,shop_id,task_id,
                plan_id,approval_id,operation_key,request_hash,
 revalidation_snapshot_id,actor_id,
                identity_id,auth_version,plan_version,plan_hash,freshness_seconds,
 status,started_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'building',%s)""",
                (
                    identifier,
                    r.organization_id,
                    r.shop_id,
                    r.task_id,
                    plan["id"],
                    approval["id"],
                    operation_key(plan),
                    execution_hash(plan, approval),
                    observation["id"],
                    approval["decided_by"],
                    approval["decided_identity_id"],
                    approval["decided_auth_version"],
                    plan["version"],
                    plan["plan_hash"],
                    self.config.revalidation_max_age_seconds,
                    stamp,
                ),
            )
            item_ids = []
            for index, item in enumerate(plan["content"]["items"]):
                item_id = uuid4()
                await db.execute(
                    """INSERT INTO business.replenishment_items(id,organization_id,shop_id,
                    task_id,execution_id,sku_key,stock_pool_key,quantity,status,
 source_snapshot_id,
                    approved_plan_id,approved_by,created_at,updated_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'open',%s,%s,%s,%s,%s)""",
                    (
                        item_id,
                        r.organization_id,
                        r.shop_id,
                        r.task_id,
                        identifier,
                        item["sku_key"],
                        item["stock_pool_key"],
                        item["quantity"],
                        observation["id"],
                        plan["id"],
                        approval["decided_by"],
                        stamp,
                        stamp,
                    ),
                )
                payload = {
                    "schema_version": "p3-web-v1",
                    "item_id": str(item_id),
                    "version": 1,
                    "state": "open",
                }
                await db.execute(
                    """INSERT INTO business.outbox(id,organization_id,shop_id,task_id,
                    destination,aggregate_id,aggregate_version,operation,dedupe_key,
 request_hash,
                    payload,provider_idempotency_key,status) VALUES(%s,%s,%s,%s,
 'bitable',%s,1,
                    'item_projection',%s,%s,%s,%s,'pending')""",
                    (
                        uuid4(),
                        r.organization_id,
                        r.shop_id,
                        r.task_id,
                        item_id,
                        f"item:{item_id}:1",
                        facts_hash(payload),
                        Jsonb(payload),
                        uuid4(),
                    ),
                )
                item_ids.append(item_id)
                if index == 0:
                    await self.hook("after_first_t4_item")
            completed = await clock(db)
            if completed >= approval["expires_at"] or completed - observation[
                "collected_at"
            ] > timedelta(seconds=self.config.revalidation_max_age_seconds):
                raise RevalidationRequired("P3_EXECUTION_FINAL_CLOCK_STALE")
            await db.execute(
                """UPDATE business.executions SET status='completed',completed_at=%s,item_ids=%s
 WHERE id=%s""",
                (completed, sorted(item_ids), identifier),
            )
            await db.execute(
                "UPDATE business.approvals SET consumed_at=%s WHERE id=%s AND consumed_at IS NULL",
                (completed, approval["id"]),
            )
            await db.execute(
                """UPDATE business.replenishment_plans SET status='executed' WHERE id=%s AND
 status='current'""",
                (plan["id"],),
            )
            await db.execute(
                """UPDATE business.business_tasks SET state='completed',failure_code=NULL,
                version=version+1,updated_at=clock_timestamp() WHERE id=%s""",
                (r.task_id,),
            )
            await self.audit(
                db, r, approval["decided_by"], "execution_committed", "execution", identifier
            )
            await self.hook("before_t4_commit")
            result = {"outcome": "executed", "execution_id": str(identifier)}
        await self.hook("after_t4_commit")
        return result
