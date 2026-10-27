// Synthetic presentation DTOs only: no new Woo/API/PG or authoritative business proof.
import { report } from "../phase4/fixtures";
import type { DTO } from "../../../../frontend/lib/p3-present";

export function sourceReport(
  kind: "mock" | "woocommerce_test" = "woocommerce_test",
  incomplete = false,
): DTO["ReportRead"] {
  const items = report.facts.items.slice(0, 5).map((fact, index) => ({
    ...fact,
    sku_label: ["展示样例·未知库存", "展示样例·共享变体红", "展示样例·共享变体蓝", "展示样例·零库存", "展示样例·负库存"][index],
    A: index === 0 ? null : index < 3 ? 15 : index === 3 ? 0 : -3,
    stock_pool_key: index === 1 || index === 2 ? "pool/demo/shared-display" : fact.stock_pool_key,
    stock_reason: index === 0 ? "STOCK_NOT_MANAGED" : null,
    inbound_units: null,
    inbound_reason: "WOOCOMMERCE_INBOUND_UNAVAILABLE",
    effective_inbound_units: 0,
    quality_flags: (index === 0 ? ["UNKNOWN_STOCK"] : index < 3 ? ["SHARED_POOL_UNRESOLVED"] : []) as DTO["P2Quality"][],
    hard_blocks: index === 0 ? ["UNKNOWN_STOCK"] : index < 3 ? ["SHARED_POOL_UNRESOLVED"] : [],
    required_assumptions: index >= 3 ? ["INBOUND_UNKNOWN"] : [],
    suggested_units: index < 3 ? null : fact.suggested_units,
    suggestion_mode: (index < 3 ? "blocked" : "assumption_draft") as DTO["P2InventoryFact"]["suggestion_mode"],
    risk: (index < 3 ? "manual_check" : fact.risk) as DTO["P2InventoryFact"]["risk"],
    can_form_suggestion: index >= 3,
  }));
  return {
    ...report,
    source: { ...report.source, source_complete: !incomplete },
    facts: {
      ...report.facts, items, candidate_count: items.length,
      complete: !incomplete, source_complete: !incomplete, requires_review: true,
      warnings: incomplete ? ["PARTIAL_FAILURE"] : [],
      source: {
        ...report.facts.source,
        provenance: {
          ...report.facts.source.provenance,
          source_kind: kind,
          fixture_version: kind === "mock" ? "presentation-only-v1" : null,
          quality_flags: ["UNKNOWN_STOCK", "SHARED_POOL_UNRESOLVED"],
        },
      },
    },
  };
}
