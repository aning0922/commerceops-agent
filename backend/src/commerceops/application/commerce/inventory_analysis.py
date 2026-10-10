"""标准输入上的纯库存分析；无采集、网络、存储、审批/执行。"""

from collections import defaultdict
from dataclasses import replace
from typing import Any
from urllib.parse import unquote

from pydantic import BaseModel, ValidationError

from commerceops.application.commerce.contracts import (
    DTO,
    Inventory,
    OrderLine,
    Product,
    Refund,
    Window,
)
from commerceops.application.commerce.inventory_facts import (
    InventoryFact,
    InventoryInput,
    InventoryReport,
    evaluation_fields,
)
from commerceops.domain.commerce_values import (
    canonical_bytes,
    complete_days,
    facts_hash,
    sku_key,
    stock_pool_key,
)
from commerceops.domain.inventory_rules import MAX_CANDIDATES, RuleParameters, evaluate_inventory

EXCLUDED_STATUSES = frozenset({"pending", "on-hold", "cancelled", "failed", "trash"})
COLLECTION_ERRORS = frozenset(
    {
        "DUPLICATE_ID",
        "MISSING_PAGE",
        "SOURCE_CHANGED",
        "CAPACITY_LIMIT",
        "PARTIAL_FAILURE",
    }
)


class InventoryAnalysisError(ValueError):
    def __init__(self) -> None:
        super().__init__("INVALID_INVENTORY_INPUT")


def _sorted[T: DTO](rows: tuple[T, ...]) -> list[T]:
    return sorted(rows, key=lambda row: canonical_bytes(row.model_dump(mode="json")))


def _native_input_value(value: object) -> object:
    # 仅本输入边界使用，保留bool/Decimal等原始类型；不先经serializer做转换。
    if isinstance(value, BaseModel):
        return {key: _native_input_value(item) for key, item in value.__dict__.items()}
    if isinstance(value, dict):
        return {key: _native_input_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_native_input_value(item) for item in value)
    if isinstance(value, list):
        return [_native_input_value(item) for item in value]
    return value


def _key_in_shop(value: str, shop_id: str, kind: str) -> bool:
    # 本标准合同的canonical分段，复用领域构造器；无平台SDK对象。
    parts = value.split("/")
    try:
        if kind == "pool" and len(parts) == 3 and parts[0] == "pool":
            return value == stock_pool_key(shop_id, unquote(parts[2], errors="strict"))
        if kind == "sku" and parts[0] == "sku":
            if len(parts) == 4 and parts[3] == "p":
                return value == sku_key(shop_id, unquote(parts[2], errors="strict"))
            if len(parts) == 5 and parts[3] == "v":
                return value == sku_key(
                    shop_id, unquote(parts[2], errors="strict"), unquote(parts[4], errors="strict")
                )
    except ValueError:
        return False
    return False


def analyze_inventory(
    data: InventoryInput,
    parameters: RuleParameters | None = None,
) -> InventoryReport:
    # 拒绝内部model_copy绕过DTO的非法值，先验证再计数，不把bool算成1。
    try:
        data = InventoryInput.model_validate(_native_input_value(data))
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise InventoryAnalysisError() from None
    params = RuleParameters() if parameters is None else parameters
    if type(params) is not RuleParameters:
        raise ValueError("INVALID_PARAMETERS")
    params.__post_init__()
    start, end = complete_days(data.now, data.source.timezone)
    expected_window = Window(start=start, end=end)
    window = data.window or expected_window
    flags = {flag.value for flag in (*data.warnings, *data.source.provenance.quality_flags)}
    global_blocks = flags & COLLECTION_ERRORS
    unscoped_quality = flags - COLLECTION_ERRORS
    blocks: defaultdict[str, set[str]] = defaultdict(set)
    if not data.complete:
        global_blocks.add("SOURCE_INCOMPLETE")
    if window != expected_window:
        global_blocks.add("WINDOW_MISMATCH")
    products = {p.sku_key: p for p in _sorted(data.products)}
    inventories = {item.sku_key: item for item in _sorted(data.inventories)}
    unique_keys = (
        [p.sku_key for p in data.products],
        [i.sku_key for i in data.inventories],
        [(row.order_id, row.line_id) for row in data.order_lines],
        [r.refund_id for r in data.refunds],
        [item.item_id for item in data.open_items],
    )
    if any(len(keys) != len(set(keys)) for keys in unique_keys):
        global_blocks.add("DUPLICATE_ID")
    provenance = data.source.provenance
    source_rows: tuple[Product | OrderLine | Refund | Inventory, ...] = (
        *data.products,
        *data.order_lines,
        *data.refunds,
        *data.inventories,
    )
    line_skus = {(row.order_id, row.line_id): row.sku_key for row in _sorted(data.order_lines)}
    all_order_skus: defaultdict[str, set[str]] = defaultdict(set)
    for row in data.order_lines:
        all_order_skus[row.order_id].add(row.sku_key)
    for sourced_record in source_rows:
        if (
            sourced_record.source.source_kind != provenance.source_kind
            or sourced_record.source.fixture_version != provenance.fixture_version
            or sourced_record.source.schema_version != provenance.schema_version
            or sourced_record.source.captured_at != provenance.captured_at
        ):
            global_blocks.add("PROVENANCE_MISMATCH")
        record_quality = {flag.value for flag in sourced_record.source.quality_flags}
        global_blocks.update(record_quality & COLLECTION_ERRORS)
        scoped_quality = record_quality - COLLECTION_ERRORS
        if isinstance(sourced_record, Refund):
            associated: set[str] = set()
            if sourced_record.lines:
                for line in sourced_record.lines:
                    sku = line_skus.get((sourced_record.order_id, line.line_id))
                    if sku is None:
                        unscoped_quality.update(scoped_quality)
                    else:
                        associated.add(sku)
            else:
                associated.update(all_order_skus.get(sourced_record.order_id, set()))
            if not associated:
                unscoped_quality.update(scoped_quality)
            for sku in associated:
                blocks[sku].update(scoped_quality)
        else:
            blocks[sourced_record.sku_key].update(scoped_quality)
    if any(p.shop_id != data.source.shop_id for p in data.products):
        global_blocks.add("SHOP_MISMATCH")
    if (
        any(not _key_in_shop(row.sku_key, data.source.shop_id, "sku") for row in data.order_lines)
        or any(
            not _key_in_shop(i.sku_key, data.source.shop_id, "sku")
            or not _key_in_shop(i.stock_pool_key, data.source.shop_id, "pool")
            for i in data.inventories
        )
        or any(
            not _key_in_shop(p.stock_pool_key, data.source.shop_id, "pool") for p in data.products
        )
        or any(
            not _key_in_shop(i.sku_key, data.source.shop_id, "sku")
            or not _key_in_shop(i.stock_pool_key, data.source.shop_id, "pool")
            for i in data.open_items
        )
    ):
        global_blocks.add("SHOP_MISMATCH")
    if any(row.currency != data.source.currency for row in data.order_lines) or any(
        row.currency != data.source.currency for row in data.refunds
    ):
        global_blocks.add("CURRENCY_MISMATCH")

    warnings: defaultdict[str, set[str]] = defaultdict(set)
    pools: defaultdict[str, set[str]] = defaultdict(set)
    for known_product in products.values():
        pools[known_product.stock_pool_key].add(known_product.sku_key)
    for key, known_inventory in inventories.items():
        if key not in products or known_inventory.stock_pool_key != products[key].stock_pool_key:
            global_blocks.add("STOCK_POOL_MISMATCH")
        if known_inventory.pool_allocation == "unresolved":
            blocks[key].add("SHARED_POOL_UNRESOLVED")
    for pool_keys in pools.values():
        if len(pool_keys) > 1:
            # v1 DTO没有可证实的每SKU份额；不凭exact标签猜测池的拆分/代表SKU。
            for key in pool_keys:
                blocks[key].add("SHARED_POOL_UNRESOLVED")
    open_ids: defaultdict[str, set[str]] = defaultdict(set)
    for observation in data.open_items:
        product = products.get(observation.sku_key)
        if product is not None and observation.stock_pool_key != product.stock_pool_key:
            global_blocks.add("OPEN_ITEM_POOL_MISMATCH")
        for key in pools.get(observation.stock_pool_key, set()):
            blocks[key].add("OPEN_WORK_ITEM")
            open_ids[key].add(observation.item_id)

    # 标准订单行先按稳定内容排序/ID去重；重复来源硬阻断，不将重ID多计一次。
    order_lines = {(row.order_id, row.line_id): row for row in _sorted(data.order_lines)}
    included: defaultdict[str, set[str]] = defaultdict(set)
    excluded: defaultdict[str, set[str]] = defaultdict(set)
    review: defaultdict[str, set[str]] = defaultdict(set)
    gross: defaultdict[str, int] = defaultdict(int)
    valid_lines = {}
    order_skus: defaultdict[str, set[str]] = defaultdict(set)
    for ref, row in order_lines.items():
        if not window.contains(row.created_at):
            continue
        if row.sku_key not in products:
            blocks[row.sku_key].add("DELETED_PRODUCT")
        if row.status in {"processing", "completed"} or (
            row.status == "refunded"
            and any(
                instant is not None and row.created_at <= instant <= row.source.captured_at
                for instant in (row.paid_at, row.completed_at)
            )
        ):
            included[row.sku_key].add(row.order_id)
            gross[row.sku_key] += row.quantity
            valid_lines[ref] = row
            order_skus[row.order_id].add(row.sku_key)
        elif row.status in EXCLUDED_STATUSES:
            excluded[row.sku_key].add(row.order_id)
        else:
            review[row.sku_key].add(row.order_id)
            blocks[row.sku_key].add("ORDER_STATUS_REVIEW")

    known_refunds: defaultdict[str, int] = defaultdict(int)
    line_refunds: defaultdict[tuple[str, str], int] = defaultdict(int)
    unknown_refund: set[str] = set()
    for refund in {r.refund_id: r for r in _sorted(data.refunds)}.values():
        keys = order_skus.get(refund.order_id, set())
        if not keys:
            continue  # 非窗口有效订单的cashflow不混入cohort。
        if not refund.lines:
            unknown_refund.update(keys)
        for line in refund.lines:
            ref = (refund.order_id, line.line_id)
            original = valid_lines.get(ref)
            if original is None:
                for key in keys:
                    blocks[key].add("REFUND_LINE_UNRESOLVED")
                unknown_refund.update(keys)
            elif line.refunded_quantity is None:
                unknown_refund.add(original.sku_key)
            else:
                known_refunds[original.sku_key] += line.refunded_quantity
                line_refunds[ref] += line.refunded_quantity
                if line_refunds[ref] > original.quantity:
                    blocks[original.sku_key].add("REFUND_QUANTITY_EXCEEDS_LINE")
                    unknown_refund.add(original.sku_key)
    source_complete = not global_blocks
    sku_keys = sorted(
        set(products)
        | set(inventories)
        | set(included)
        | set(excluded)
        | set(review)
        | {key for key, quality in blocks.items() if quality}
    )
    evaluated = []
    for key in sku_keys:
        item = inventories.get(key)
        product = products.get(key)
        if item is None:
            blocks[key].add("UNKNOWN_STOCK")
        if product is not None and not product.active:
            blocks[key].add("INACTIVE_PRODUCT")
        blocks[key].update(global_blocks | unscoped_quality)
        quantity_complete = source_complete and key not in unknown_refund
        if not quantity_complete:
            warnings[key].add(
                "UNKNOWN_REFUND_QUANTITY" if key in unknown_refund else "SOURCE_INCOMPLETE"
            )
        metrics = evaluate_inventory(
            sku_key=key,
            gross_units=gross[key] if source_complete else None,
            available_stock=item.available_stock if item else None,
            inbound_units=item.inbound_units if item else None,
            parameters=params,
            hard_blocks=tuple(sorted(blocks[key])),
        )
        evaluated.append((key, metrics, quantity_complete))
    candidate_count = sum(metrics.can_form_suggestion for _, metrics, _ in evaluated)
    scope_required = candidate_count > MAX_CANDIDATES
    facts: list[InventoryFact] = []
    for key, metrics, quantity_complete in evaluated:
        if scope_required and metrics.can_form_suggestion:
            metrics = replace(
                metrics,
                suggested_units=None,
                can_form_suggestion=False,
                hard_blocks=tuple(sorted((*metrics.hard_blocks, "SCOPE_TOO_LARGE"))),
            )
        item = inventories.get(key)
        product = products.get(key)
        pool = product.stock_pool_key if product else (item.stock_pool_key if item else None)
        flags_for_key = tuple(sorted(set(metrics.hard_blocks) | warnings[key]))
        facts.append(
            InventoryFact.model_validate(
                {
                    "sku_key": key,
                    "stock_pool_key": pool,
                    "sku_label": product.sku_label if product else None,
                    "active": product.active if product else None,
                    "gross_units": gross[key] if source_complete else None,
                    "stock_reason": item.stock_reason if item else "not_observed",
                    "inventory_observed_at": item.observed_at if item else None,
                    "source_version": item.source_version if item else None,
                    "known_gross_units": gross[key],
                    "demand_complete": source_complete,
                    "known_refunded_units": known_refunds[key],
                    "quantity_complete": quantity_complete,
                    "refunded_units": known_refunds[key] if quantity_complete else None,
                    "net_units": gross[key] - known_refunds[key] if quantity_complete else None,
                    "quantity_reason": None
                    if quantity_complete
                    else (
                        "UNKNOWN_REFUND_QUANTITY" if key in unknown_refund else "SOURCE_INCOMPLETE"
                    ),
                    "currency": data.source.currency,
                    "inbound_reason": item.inbound_reason if item else "not_observed",
                    "quality_flags": flags_for_key,
                    "included_order_ids": tuple(sorted(included[key])),
                    "excluded_order_ids": tuple(sorted(excluded[key])),
                    "review_order_ids": tuple(sorted(review[key])),
                    "open_item_ids": tuple(sorted(open_ids[key])),
                    **evaluation_fields(metrics, params),
                }
            )
        )
    # 输入指纹包含原始标准DTO/来源证据，数组按内容排序，不受调用方排列影响。
    normalized = data.model_dump(mode="json")
    normalized["window"] = window.model_dump(mode="json")
    for refund in normalized["refunds"]:
        refund["lines"] = sorted(refund["lines"], key=canonical_bytes)
    for field in ("products", "order_lines", "refunds", "inventories", "open_items", "warnings"):
        normalized[field] = sorted(normalized[field], key=canonical_bytes)
    body: dict[str, Any] = {
        "source": data.source,
        "now": data.now,
        "window": window,
        "source_complete": source_complete,
        "complete": source_complete
        and not unscoped_quality
        and not any(
            set(f.hard_blocks) - {"SCOPE_TOO_LARGE", "OPEN_WORK_ITEM", "INACTIVE_PRODUCT"}
            for f in facts
        ),
        "requires_review": bool(unscoped_quality)
        or any(
            f.hard_blocks or f.required_assumptions or f.risk in {"manual_check", "quality_blocked"}
            for f in facts
        ),
        "L": params.L,
        "R": params.R,
        "S": params.S,
        "warnings": tuple(
            sorted(set(flags) | global_blocks | {flag for f in facts for flag in f.quality_flags})
        ),
        "items": tuple(facts),
        "candidate_count": candidate_count,
        "scope_required": scope_required,
        "input_hash": facts_hash(normalized),
    }
    canonical_body = {
        **body,
        "source": data.source.model_dump(mode="json"),
        "window": window.model_dump(mode="json"),
        "now": data.now.isoformat().replace("+00:00", "Z"),
        "items": [f.model_dump(mode="json", exclude={"display"}) for f in facts],
        "schema_version": "inventory-analysis-v1",
        "rule_version": "inventory-rule-v1",
        "parameter_mode": "demo_assumption",
        "canonical_version": "canonical-facts-v1",
        "analysis_only": True,
        "execution_available": False,
    }
    return InventoryReport.model_validate({**body, "facts_hash": facts_hash(canonical_body)})
