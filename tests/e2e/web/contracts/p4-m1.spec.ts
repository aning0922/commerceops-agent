import { test, expect } from "../../../../frontend/tooling/web-test";
import {
  explanationBound,
  newCycleEligibility,
  parameterClarification,
} from "../../../../frontend/lib/p3-present";
import { report, explanation, task } from "../phase4/fixtures";
import { verifyReadResponse } from "../../../../frontend/lib/p3-live-client";
type Mutable<T> = T extends readonly (infer U)[]
  ? Mutable<U>[]
  : T extends object
    ? { -readonly [K in keyof T]: Mutable<T[K]> }
    : T;
test("P4 cache合同保留旧DTO：report/snapshot/hash/sourceTask/SKU风险绑定，不假造模型", () => {
  const value = explanation();
  expect(
    verifyReadResponse(
      "GET",
      `/api/v1/tasks/${report.task_id}/explanation`,
      200,
      value,
    ),
  ).toBe(true);
  expect(explanationBound(report, value)).toBe(true);
  for (const edit of [
    (v: Mutable<typeof value>) => {
      v.report_id = "00000000-0000-4000-8000-000000000999";
    },
    (v: Mutable<typeof value>) => {
      v.explanation.task_id = report.task_id;
    },
    (v: Mutable<typeof value>) => {
      v.explanation.result.reference_ids.snapshot_id = report.task_id;
    },
    (v: Mutable<typeof value>) => {
      v.explanation.result.facts_hash = "f".repeat(64);
    },
    (v: Mutable<typeof value>) => {
      v.explanation.result.lines[0].reference_ids = {
        ...v.explanation.result.reference_ids,
        report_id: report.task_id,
      };
    },
    (v: Mutable<typeof value>) => {
      v.explanation.result.lines[0].reason = "normal";
    },
    (v: Mutable<typeof value>) => {
      v.explanation.result.lines.push(v.explanation.result.lines[0]);
    },
  ]) {
    const changed = structuredClone(value) as Mutable<typeof value>;
    edit(changed);
    expect(explanationBound(report, changed)).toBe(false);
  }
  expect(explanationBound(report, explanation("template"))).toBe(true);
  expect(explanationBound(report, explanation("nullable"))).toBe(true);
});
test("P4新周期只用完成/服务端资格/当前operator店铺；不把recompute变可用", () => {
  const current = task(),
    shops = [current.task.shop_id];
  expect(newCycleEligibility(current, true, shops).allowed).toBe(true);
  expect(newCycleEligibility(null, true, shops).allowed).toBe(false);
  expect(newCycleEligibility(current, false, shops).allowed).toBe(false);
  expect(newCycleEligibility(current, true, []).allowed).toBe(false);
  for (const state of [
    "awaiting_approval",
    "executing",
    "needs_attention",
    "needs_reapproval",
  ] as const)
    expect(
      newCycleEligibility(
        { ...current, task: { ...current.task, state } },
        true,
        shops,
      ).allowed,
    ).toBe(false);
  expect(
    newCycleEligibility(
      {
        ...current,
        actions: { ...current.actions, can_start_new_cycle: false },
      },
      true,
      shops,
    ).allowed,
  ).toBe(false);
  expect(current.actions.can_recompute).toBe(false);
});
test("P4结构化澄清必须指出缺参/整数边界；完整确认前无自动提交", () => {
  expect(parameterClarification("shop", ["shop"], ["3", "7", "2"])).toBe(null);
  expect(parameterClarification("shop", ["shop"], ["", "7", ""])).toContain(
    "L、S",
  );
  for (const v of ["-1", "366", "1.1", " 3 ", "未知"])
    expect(parameterClarification("shop", ["shop"], [v, "7", "2"])).toContain(
      "L 必须",
    );
  expect(parameterClarification("other", ["shop"], ["3", "7", "2"])).toContain(
    "授权",
  );
});
