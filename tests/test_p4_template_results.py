"""报告绑定/重放/封闭失败与全文读取文法，纯内存，无 PG/provider/SDK。"""

import asyncio
import copy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from commerceops.application.feishu_business.read_intents import parse_read_intent
from commerceops.application.replenishment.template_result import SourceKind, TemplateRenderError
from commerceops.domain.commerce_values import canonical_bytes, facts_hash
from commerceops.infrastructure import p3_template_results as templates
from commerceops.infrastructure.inventory_repository import AnalysisUnsafe
from pydantic import ValidationError

from tests.test_model_explanation import report

pytestmark = pytest.mark.offline


class Memory:
    def __init__(self) -> None:
        self.row: dict[str, Any] | None = None
        self.selected: dict[str, Any] | None = None
        self.inserts = 0

    async def execute(self, query: str, args: Any) -> "Memory":
        if query.startswith("SELECT"):
            self.selected = self.row
        else:
            self.inserts += 1
            names = (
                "id",
                "organization_id",
                "shop_id",
                "requester_id",
                "p3_task_id",
                "source_kind",
                "source_task_id",
                "observation_id",
                "snapshot_id",
                "report_id",
                "facts_hash",
                "template_version",
                "logical_key",
                "status",
                "safe_error_code",
                "result",
                "canonical_result",
                "result_hash",
            )
            values = list(args)
            if values[15] is not None:
                values[15] = values[15].obj
            candidate = dict(zip(names, values, strict=True), created_at=datetime.now(UTC))
            if self.row is None:
                self.row, self.selected = candidate, candidate
            else:
                self.selected = None
        return self

    async def fetchone(self) -> dict[str, Any] | None:
        return self.selected


def binding(kind: SourceKind = "p2_original") -> templates.TemplateBinding:
    observation = uuid4() if kind == "p3_observation" else None
    return templates.TemplateBinding(
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        kind,
        uuid4(),
        observation,
        observation or uuid4(),
        uuid4(),
        report().facts_hash,
    )


def test_original_report_freeze_ten_replays_one_stable_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, refs = Memory(), binding()
    called = 0
    original = templates.render

    async def counted(*args: Any) -> dict[str, Any]:
        nonlocal called
        called += 1
        return await original(*args)

    monkeypatch.setattr(templates, "render", counted)
    ids = [asyncio.run(templates.freeze(db, refs, report())) for _ in range(10)]
    assert len(set(ids)) == 1 and called == db.inserts == 1
    assert db.row and "child_task_id" not in db.row
    content = templates.verify_row(db.row, refs, report())
    assert content and content.metadata.provider is None and content.metadata.usage is None
    assert content.lines[0].text.endswith("补货估算=100。")


def test_equal_facts_different_observation_reports_never_reuse_identity() -> None:
    first = binding("p3_observation")
    second = templates.TemplateBinding(
        first.organization_id,
        first.shop_id,
        first.requester_id,
        first.p3_task_id,
        first.source_kind,
        first.source_task_id,
        uuid4(),
        uuid4(),
        uuid4(),
        first.facts_hash,
    )
    second = templates.TemplateBinding(**{**second.__dict__, "snapshot_id": second.observation_id})
    assert first.key() != second.key() and first.identity()["id"] != second.identity()["id"]


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "canonical",
        "report",
        "snapshot",
        "provider",
        "usage",
        "sku",
        "number",
        "summary",
        "error_code",
    ],
)
def test_corrupt_ready_result_refused(mutation: str) -> None:
    db, refs = Memory(), binding()
    asyncio.run(templates.freeze(db, refs, report()))
    assert db.row
    row = copy.deepcopy(db.row)
    if mutation == "hash":
        row["result_hash"] = "0" * 64
    elif mutation == "canonical":
        row["canonical_result"] += " "
    elif mutation in ("report", "snapshot"):
        row[mutation + "_id"] = uuid4()
    else:
        result = row["result"]
        if mutation == "provider":
            result["metadata"]["provider"] = "deepseek"
        elif mutation == "usage":
            result["metadata"]["usage"] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        elif mutation == "sku":
            result["lines"][0]["sku_key"] = "another-sku"
        elif mutation == "summary":
            result["summary"] = "请执行采购"
        elif mutation == "error_code":
            result["metadata"]["error_code"] = "TEMPLATE_REQUIRED"
        else:
            result["lines"][0]["text"] = "补货估算=999。"
        row["canonical_result"] = canonical_bytes(result).decode()
        row["result_hash"] = facts_hash(result)
    with pytest.raises((AnalysisUnsafe, ValidationError)):
        templates.verify_row(row, refs, report())


def test_narrow_render_error_unavailable_is_immutable_on_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, refs = Memory(), binding()

    async def rejected(*args: Any) -> dict[str, Any]:
        raise TemplateRenderError()

    monkeypatch.setattr(templates, "render", rejected)
    first = asyncio.run(templates.freeze(db, refs, report()))
    assert db.row and db.row["status"] == "unavailable"
    assert templates.verify_row(db.row, refs, report()) is None
    monkeypatch.setattr(templates, "render", lambda *args: pytest.fail("must not re-render"))
    assert asyncio.run(templates.freeze(db, refs, report())) == first and db.inserts == 1


@pytest.mark.parametrize("error_type", [RuntimeError, PermissionError, AnalysisUnsafe])
def test_other_failures_are_not_unavailable(
    error_type: type[Exception],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, refs = Memory(), binding()

    async def rejected(*args: Any) -> dict[str, Any]:
        raise error_type()

    monkeypatch.setattr(templates, "render", rejected)
    with pytest.raises(error_type):
        asyncio.run(templates.freeze(db, refs, report()))
    assert db.row is None and db.inserts == 0


@pytest.mark.parametrize("kind", ["task_status", "explain_report"])
def test_explicit_reference_read_whole_consumption(kind: str) -> None:
    task, original_report = uuid4(), uuid4()
    text = (
        f"查询任务{task}进度" if kind == "task_status" else f"解释任务{task}的报告{original_report}"
    )
    intent = parse_read_intent(text)
    assert intent and intent.kind == kind and intent.task_id == task
    for bad in (text + "然后创建", text + "\n", text + text, "上次的报告", "解释这个任务"):
        assert parse_read_intent(bad) is None
