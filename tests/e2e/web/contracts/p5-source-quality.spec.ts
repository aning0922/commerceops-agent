import { test, expect } from "../../../../frontend/tooling/web-test";
import { commerceSourceLabel, commerceQualitySummary } from "../../../../frontend/lib/p3-present";
import { verifyReadResponse } from "../../../../frontend/lib/p3-live-client";
import { sourceReport } from "../phase5/source-fixtures";

test("冻结commerce来源只识别Mock/Woo；不从会话、传输或P3重观测猜来源", () => {
  expect(commerceSourceLabel("mock")).toBe("Mock 样本");
  expect(commerceSourceLabel("woocommerce_test")).toBe("Woo 测试店（只读）");
  for (const absent of [null, undefined, "local_http", "session", "p2_original", "p3_observation", "production"])
    expect(commerceSourceLabel(absent)).toBe("未报告");
});
test("质量标志独立于采集complete；保留unknown/shared及所有既有安全码", () => {
  const flags = ["UNKNOWN_STOCK", "SHARED_POOL_UNRESOLVED", "PARTIAL_FAILURE"];
  const original = [...flags];
  const text = commerceQualitySummary([...flags, flags[0]]);
  expect(text).toContain("库存未知");
  expect(text).toContain("不按变体重复分配");
  expect(text).toContain("PARTIAL_FAILURE");
  expect(text.match(/UNKNOWN_STOCK/g)).toHaveLength(1);
  expect(flags).toEqual(original);
  expect(commerceQualitySummary([])).toBe("无已报告质量标志");
  expect(commerceQualitySummary(["unrecognized"])).toBe("未识别质量标志");
});
test("Mock/Woo展示样例通过冻结read解码；完整读齐仍保留unknown、null和硬阻断", () => {
  for (const kind of ["mock", "woocommerce_test"] as const) {
    for (const incomplete of [false, true]) {
      const read = sourceReport(kind, incomplete);
      const before = structuredClone(read);
      expect(verifyReadResponse("GET", `/api/v1/tasks/${read.task_id}/report`, 200, read)).toBe(true);
      expect(read.facts.source_complete).toBe(!incomplete);
      expect(read.facts.items[0].A).toBeNull();
      expect(read.facts.items[0].hard_blocks).toContain("UNKNOWN_STOCK");
      expect(read.facts.items[1].stock_pool_key).toBe(read.facts.items[2].stock_pool_key);
      expect(read.facts.items.every((fact) => fact.inbound_units === null && !fact.eligible_for_execution)).toBe(true);
      expect(read.facts.items[3].A).toBe(0);
      expect(read.facts.items[4].A).toBe(-3);
      expect(read).toEqual(before);
    }
  }
});
