"""仅两个报告冻结事务写入，读取只验证不可变原结果。"""

import json
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg.types.json import Jsonb

from commerceops.application.commerce.inventory_facts import InventoryReport
from commerceops.application.model_explanation.contracts import ReferenceIds
from commerceops.application.model_explanation.service import ModelExplanationService, line
from commerceops.application.replenishment.template_result import (
    TEMPLATE_VERSION,
    P3TemplateRead,
    SourceKind,
    TemplateContent,
    TemplateRenderError,
)
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure.explanation_repository import payload
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe


@dataclass(frozen=True)
class TemplateBinding:
    organization_id: UUID
    shop_id: UUID
    requester_id: UUID
    p3_task_id: UUID
    source_kind: SourceKind
    source_task_id: UUID
    observation_id: UUID | None
    snapshot_id: UUID
    report_id: UUID
    facts_hash: str

    def key(self) -> str:
        fields: list[str | None] = [
            "p3-template-v1",
            str(self.organization_id),
            str(self.shop_id),
            str(self.requester_id),
            str(self.p3_task_id),
            self.source_kind,
            str(self.source_task_id),
            str(self.observation_id) if self.observation_id is not None else None,
            str(self.snapshot_id),
            str(self.report_id),
            self.facts_hash,
            TEMPLATE_VERSION,
        ]
        return "p3-template-v1:" + facts_hash(fields)

    def identity(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "template_version": TEMPLATE_VERSION,
            "logical_key": self.key(),
            "id": uuid5(NAMESPACE_URL, self.key()),
        }

    def check_report(self, report: InventoryReport) -> InventoryReport:
        checked = InventoryReport.model_validate(report.model_dump())
        if (
            checked.facts_hash != self.facts_hash
            or (self.source_kind == "p3_observation") != (self.observation_id is not None)
            or self.observation_id is not None
            and self.snapshot_id != self.observation_id
        ):
            raise AnalysisUnsafe("P3_TEMPLATE_SOURCE_INVALID")
        return checked


async def render(binding: TemplateBinding, report: InventoryReport) -> dict[str, Any]:
    """原 provider=None 分支内无 network await；不包装未知 formatter/数据错误。"""
    result = await ModelExplanationService(provider=None).explain(
        report,
        reference_ids=ReferenceIds(str(binding.snapshot_id), str(binding.report_id)),
    )
    if result.metadata.error_code in ("INVALID_REPORT", "INVALID_REFERENCES"):
        raise AnalysisUnsafe("P3_TEMPLATE_FACTS_OR_REFERENCE_INVALID")
    value = TemplateContent.model_validate_json(json.dumps(payload(result)))
    validate_content(value, binding, report)
    return value.model_dump(mode="json")


def validate_content(
    content: TemplateContent, binding: TemplateBinding, report: InventoryReport
) -> None:
    refs = ReferenceIds(str(binding.snapshot_id), str(binding.report_id))
    # 复用原单行确定性 formatter 验证所有 SKU/数字/质量语义；不创建结果或调用 provider。
    expected = [line(fact, report, refs) for fact in report.items]
    # 固定 v1 的摘要/无 provider 原因是验证白名单；不构造解释结果或运行 service。
    summary = "仅解释已有分析事实，未执行采购、库存修改或审批。"
    if not report.items:
        summary += " 当前没有可说明的商品事实。"
    if not report.complete or not report.source_complete:
        summary += " 数据不完整，需核对来源；说明不能补齐事实。"
    if report.scope_required:
        summary += " 需要缩小分析范围。"
    required = (
        not report.complete
        or not report.source_complete
        or report.requires_review
        or report.scope_required
        or not report.items
        or any(fact.required_assumptions or fact.inbound_units is None for fact in report.items)
    )
    if (
        content.summary != summary
        or content.metadata.error_code != ("TEMPLATE_REQUIRED" if required else "NO_PROVIDER")
        or content.facts_hash != binding.facts_hash
        or content.reference_ids.snapshot_id != refs.snapshot_id
        or content.reference_ids.report_id != refs.report_id
        or len(content.lines) != len(expected)
        or any(
            (got.sku_key, got.reason, got.text, got.facts_hash)
            != (wanted.sku_key, wanted.reason, wanted.text, wanted.facts_hash)
            or got.reference_ids != content.reference_ids
            for got, wanted in zip(content.lines, expected, strict=True)
        )
    ):
        raise AnalysisUnsafe("P3_TEMPLATE_RESULT_INVALID")


def verify_row(
    row: dict[str, Any], binding: TemplateBinding, report: InventoryReport
) -> TemplateContent | None:
    report = binding.check_report(report)
    if any(row.get(key) != value for key, value in binding.identity().items()):
        raise AnalysisUnsafe("P3_TEMPLATE_ROW_BINDING_INVALID")
    if row["status"] == "unavailable":
        if row["safe_error_code"] != "TEMPLATE_RENDER_FAILED" or any(
            row[key] is not None for key in ("result", "canonical_result", "result_hash")
        ):
            raise AnalysisUnsafe("P3_TEMPLATE_UNAVAILABLE_INVALID")
        return None
    if (
        row["status"] != "ready"
        or row["safe_error_code"] is not None
        or canonical_bytes(row["result"]).decode() != row["canonical_result"]
        or facts_hash(row["result"]) != row["result_hash"]
    ):
        raise AnalysisUnsafe("P3_TEMPLATE_CANONICAL_INVALID")
    content = TemplateContent.model_validate_json(row["canonical_result"])
    validate_content(content, binding, report)
    return content


async def freeze(db: Any, binding: TemplateBinding, report: InventoryReport) -> UUID:
    """同键重放核全部来源/hash/status；并发 INSERT 冲突后比较完整候选。"""
    report = binding.check_report(report)
    cur = await db.execute(
        "SELECT * FROM business.p3_template_results WHERE logical_key=%s", (binding.key(),)
    )
    old = await cur.fetchone()
    if old:
        verify_row(old, binding, report)
        return UUID(str(old["id"]))
    status, error = "ready", None
    try:
        result = await render(binding, report)
    except TemplateRenderError:
        status, error, result = "unavailable", "TEMPLATE_RENDER_FAILED", None
    raw = canonical_bytes(result).decode() if result is not None else None
    digest = facts_hash(result) if result is not None else None
    identity = binding.identity()
    cur = await db.execute(
        """INSERT INTO business.p3_template_results
        (id,organization_id,shop_id,requester_id,p3_task_id,source_kind,source_task_id,
        observation_id,snapshot_id,report_id,facts_hash,template_version,logical_key,
        status,safe_error_code,result,canonical_result,result_hash)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(logical_key) DO NOTHING RETURNING *""",
        (
            identity["id"],
            binding.organization_id,
            binding.shop_id,
            binding.requester_id,
            binding.p3_task_id,
            binding.source_kind,
            binding.source_task_id,
            binding.observation_id,
            binding.snapshot_id,
            binding.report_id,
            binding.facts_hash,
            TEMPLATE_VERSION,
            binding.key(),
            status,
            error,
            Jsonb(result) if result is not None else None,
            raw,
            digest,
        ),
    )
    saved = await cur.fetchone()
    if saved is None:
        cur = await db.execute(
            "SELECT * FROM business.p3_template_results WHERE logical_key=%s", (binding.key(),)
        )
        saved = await cur.fetchone()
    if saved is None:
        raise AnalysisUnsafe("P3_TEMPLATE_INSERT_UNKNOWN")
    verify_row(saved, binding, report)
    if (
        saved["status"],
        saved["safe_error_code"],
        saved["canonical_result"],
        saved["result_hash"],
    ) != (
        status,
        error,
        raw,
        digest,
    ):
        raise AnalysisUnsafe("P3_TEMPLATE_REPLAY_CONFLICT")
    return UUID(str(saved["id"]))


def read(db: Any, binding: TemplateBinding, report: InventoryReport) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT * FROM business.p3_template_results WHERE logical_key=%s", (binding.key(),)
    ).fetchone()
    if row is None:
        return None
    content = verify_row(row, binding, report)
    if content is None:
        return None
    return P3TemplateRead.model_validate_json(
        json.dumps(
            {
                "task_id": str(binding.p3_task_id),
                "source_task_id": str(binding.source_task_id),
                "source_kind": binding.source_kind,
                "observation_id": str(binding.observation_id) if binding.observation_id else None,
                "explanation_id": str(row["id"]),
                "report_id": str(binding.report_id),
                "snapshot_id": str(binding.snapshot_id),
                "facts_hash": binding.facts_hash,
                "template_version": TEMPLATE_VERSION,
                "created_at": row["created_at"].isoformat(),
                "result": content.model_dump(mode="json"),
            }
        )
    ).model_dump(mode="json")
