"""跨任务/重启的阶段admission；保守预留不可释放，network不在事务内。"""

from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from psycopg import AsyncConnection

from commerceops.application.commerce.explanation_task import (
    CAP_NANOS,
    MAX_CALLS,
    PRICING_VERSION,
    RESERVE_NANOS,
    STAGE_BASE,
    ExplanationTaskRequest,
)
from commerceops.application.commerce.intent_task import IntentTaskRequest
from commerceops.application.model_explanation.contracts import (
    BudgetRequest,
    ModelReply,
    Pricing,
    Reservation,
)
from commerceops.application.runner import RunRequest
from commerceops.infrastructure.explanation_repository import ExplanationStore, validated_row
from commerceops.infrastructure.intent_repository import IntentStore
from commerceops.infrastructure.p204_token_counter import COUNT_VERSION
from commerceops.infrastructure.worker_lock import open_async

PRICING = Pricing(PRICING_VERSION, Decimal("0.30"), Decimal("1.20"))


class PersistentAdmission:
    def __init__(self, store: ExplanationStore | IntentStore, request: RunRequest):
        self.store, self.request = store, request
        self.call_id: UUID | None = None
        self.cached: Any = None
        self.prior_uncertain = False

    async def cache(
        self,
        db: AsyncConnection[dict[str, Any]],
        req: ExplanationTaskRequest | IntentTaskRequest,
        report: Any,
    ) -> Any:
        if isinstance(self.store, IntentStore):
            if not isinstance(req, IntentTaskRequest):
                raise ValueError("ADMISSION_KIND_INVALID")
            return await self.store.cached(db, req, self.request)
        if not isinstance(req, ExplanationTaskRequest):
            raise ValueError("ADMISSION_KIND_INVALID")
        cur = await db.execute(
            "SELECT * FROM business.model_explanations WHERE logical_key=%s", (req.logical_key,)
        )
        row = await cur.fetchone()
        if row is None:
            return None
        result = validated_row(row, req, self.request.organization_id, self.request.shop_id)
        await self.store.verify(result, report, req)
        return result

    async def reserve(self, value: BudgetRequest) -> Reservation | None:
        async with await open_async(self.store.settings) as db, db.transaction():
            _, req, report = await self.store.guard(db, self.request)
            mode = "actual_provider" if req.evidence_mode == "actual_provider" else "offline_stub"
            if (
                req.evidence_mode == "template"
                or value.request_hash != req.body_hash
                or value.facts_hash != req.facts_hash
                or value.provider != "deepseek"
                or value.requested_model != "deepseek-flash"
                or value.prompt_version != req.prompt_version
                or value.pricing_version != PRICING_VERSION
                or value.evidence_mode != mode
                or type(value.input_tokens) is not int
                or not 1 <= value.input_tokens <= 8000
                or type(value.output_tokens) is not int
                or value.output_tokens != 800
                or value.cost_upper_bound != PRICING.cost(value.input_tokens, 800)
                or (mode == "actual_provider" and value.tokenizer_version != COUNT_VERSION)
            ):
                return None
            UUID(value.request_id)
            stage = STAGE_BASE + (":actual" if mode == "actual_provider" else ":offline")
            await db.execute(
                """INSERT INTO business.model_stage_budgets(stage_key)
                VALUES (%s) ON CONFLICT DO NOTHING""",
                (stage,),
            )
            cur = await db.execute(
                "SELECT * FROM business.model_stage_budgets WHERE stage_key=%s FOR UPDATE", (stage,)
            )
            budget = await cur.fetchone()
            if budget is None:
                raise ValueError("MODEL_STAGE_MISSING")
            cached_result = await self.cache(db, req, report)
            if cached_result is not None:
                self.cached = cached_result
                return None
            cur = await db.execute(
                "SELECT id FROM business.model_calls WHERE logical_key=%s", (req.logical_key,)
            )
            prior = await cur.fetchone()
            if prior:
                self.prior_uncertain = True
                await db.execute(
                    """UPDATE business.model_stage_budgets SET halted=true,
                    updated_at=clock_timestamp() WHERE stage_key=%s""",
                    (stage,),
                )
                await db.execute(
                    """INSERT INTO business.model_call_observations
                    (call_id,outcome,safe_error,stop_required)
                    VALUES (%s,'uncertain','PRIOR_UNCERTAIN',true)
                    ON CONFLICT(call_id) DO NOTHING""",
                    (prior["id"],),
                )
                return None
            if (
                budget["halted"]
                or budget["reserved_count"] >= MAX_CALLS
                or budget["reserved_nanos"] + RESERVE_NANOS > CAP_NANOS
            ):
                return None
            self.call_id = uuid4()
            await db.execute(
                """UPDATE business.model_stage_budgets SET reserved_count=reserved_count+1,
                reserved_nanos=reserved_nanos+%s,updated_at=clock_timestamp() WHERE stage_key=%s""",
                (RESERVE_NANOS, stage),
            )
            await db.execute(
                """INSERT INTO business.model_calls
                (id,organization_id,shop_id,child_task_id,intent_task_id,stage_key,logical_key,request_id,request_hash,
                facts_hash,evidence_mode,preflight_input_bound,reserved_input,reserved_output,
                reserved_nanos,pricing_version,tokenizer_version,prompt_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,8000,800,%s,%s,%s,%s)""",
                (
                    self.call_id,
                    self.request.organization_id,
                    self.request.shop_id,
                    self.request.task_id if isinstance(self.store, ExplanationStore) else None,
                    self.request.task_id if isinstance(self.store, IntentStore) else None,
                    stage,
                    req.logical_key,
                    UUID(value.request_id),
                    value.request_hash,
                    value.facts_hash,
                    mode,
                    value.input_tokens,
                    RESERVE_NANOS,
                    PRICING_VERSION,
                    value.tokenizer_version,
                    req.prompt_version,
                ),
            )
            await self.store.session.check()
        return Reservation(value.request_id, value.request_hash)

    async def recover_prior(self) -> bool:
        # 已预留而无子任务结果时，任何重试/恢复都不再发HTTP。
        async with await open_async(self.store.settings) as db, db.transaction():
            _, req, report = await self.store.guard(db, self.request)
            cached_result = await self.cache(db, req, report)
            if cached_result is not None:
                self.cached = cached_result
                return True
            cur = await db.execute(
                """SELECT * FROM business.model_calls WHERE logical_key=%s
                AND organization_id=%s AND shop_id=%s""",
                (req.logical_key, self.request.organization_id, self.request.shop_id),
            )
            call = await cur.fetchone()
            if call is None:
                return False
            await db.execute(
                "SELECT stage_key FROM business.model_stage_budgets WHERE stage_key=%s FOR UPDATE",
                (call["stage_key"],),
            )
            await db.execute(
                """UPDATE business.model_stage_budgets SET halted=true,
                updated_at=clock_timestamp() WHERE stage_key=%s""",
                (call["stage_key"],),
            )
            await db.execute(
                """INSERT INTO business.model_call_observations
                (call_id,outcome,safe_error,stop_required)
                VALUES (%s,'uncertain','PRIOR_UNCERTAIN',true) ON CONFLICT(call_id) DO NOTHING""",
                (call["id"],),
            )
            self.prior_uncertain = True
            return True

    async def settle(self, reply: ModelReply) -> ModelReply:
        if self.call_id is None:
            return reply
        async with await open_async(self.store.settings) as db, db.transaction():
            await self.store.guard(db, self.request, authorize=False)
            cur = await db.execute(
                """SELECT * FROM business.model_calls WHERE id=%s
                    AND (child_task_id=%s OR intent_task_id=%s)
                    AND organization_id=%s AND shop_id=%s""",
                (
                    self.call_id,
                    self.request.task_id,
                    self.request.task_id,
                    self.request.organization_id,
                    self.request.shop_id,
                ),
            )
            call = await cur.fetchone()
            if call is None:
                raise ValueError("MODEL_CALL_MISSING")
            cur = await db.execute(
                "SELECT call_id FROM business.model_call_observations WHERE call_id=%s",
                (self.call_id,),
            )
            if await cur.fetchone():
                return reply
            usage = reply.usage
            valid = bool(
                usage
                and all(
                    type(n) is int and n >= 0
                    for n in (usage.input_tokens, usage.output_tokens, usage.total_tokens)
                )
                and usage.input_tokens + usage.output_tokens == usage.total_tokens
                and 1 <= usage.input_tokens <= call["preflight_input_bound"]
                and usage.input_tokens <= 8000
                and usage.output_tokens <= 800
            )
            stop = (
                reply.stop_required
                or not valid
                or reply.error_code in ("TRUNCATED", "UNKNOWN_COST", "UNKNOWN_USAGE")
            )
            estimate = (
                usage.input_tokens * 300 + usage.output_tokens * 1200 if valid and usage else None
            )
            await db.execute(
                """INSERT INTO business.model_call_observations
                (call_id,outcome,input_tokens,output_tokens,total_tokens,estimate_nanos,
                 safe_error,stop_required,latency_ms)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    self.call_id,
                    "observed" if valid else "uncertain",
                    usage.input_tokens if valid and usage else None,
                    usage.output_tokens if valid and usage else None,
                    usage.total_tokens if valid and usage else None,
                    estimate,
                    reply.error_code,
                    stop,
                    reply.latency_ms,
                ),
            )
            if stop:
                await db.execute(
                    """UPDATE business.model_stage_budgets SET halted=true,
                    updated_at=clock_timestamp() WHERE stage_key=%s""",
                    (call["stage_key"],),
                )
            await self.store.session.check()

        # 不把越界usage或无法核实的价格投影成可信只读元数据；完整预留仍保留。
        return replace(
            reply,
            usage=usage if valid else None,
            cost_estimate=PRICING.cost(usage.input_tokens, usage.output_tokens)
            if valid and usage
            else None,
            stop_required=bool(stop),
        )
