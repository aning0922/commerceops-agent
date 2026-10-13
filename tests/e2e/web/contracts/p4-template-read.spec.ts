import { test, expect } from "../../../../frontend/tooling/web-test";
import { verifyReadResponse } from "../../../../frontend/lib/p3-live-client";
import { explanationBound } from "../../../../frontend/lib/p3-present";
import type { DTO } from "../../../../frontend/lib/p3-present";
import { explanation, p3Explanation, report, fixtureClient } from "../phase4/fixtures";

const path = `/api/v1/tasks/${report.task_id}/explanation`;
function changed(value: unknown, keys: string[], replacement: unknown): DTO["ExplanationRead"] {
  const copy = structuredClone(value) as Record<string, unknown>;
  let target = copy;
  for (const key of keys.slice(0, -1)) target = target[key] as Record<string, unknown>;
  target[keys.at(-1)!] = replacement;
  return copy as unknown as DTO["ExplanationRead"];
}
test("BC02 P3模板两来源严格解码并绑定完整20SKU，旧P204三种metadata仍兼容", () => {
  for (const value of [p3Explanation(), p3Explanation("p3_observation"),
    explanation(), explanation("template"), explanation("nullable")]) {
    expect(verifyReadResponse("GET", path, 200, value)).toBe(true);
    expect(explanationBound(report, value)).toBe(true);
    expect(value.explanation.result.lines).toHaveLength(20);
  }
  expect(p3Explanation().explanation.result.metadata.usage).toBeNull();
  expect(p3Explanation().explanation).not.toHaveProperty("child_task_id");
});
test("BC02 P3严格union拒绝extra/假child/discriminator/模型与执行身份污染", () => {
  const value = p3Explanation();
  for (const [keys, replacement] of [
    [["actor"], "injected"],
    [["explanation", "child_task_id"], report.task_id],
    [["explanation", "schema_version"], "p204-read-v1"],
    [["explanation", "schema_version"], "unknown"],
    [["explanation", "schema_version"], undefined],
    [["explanation", "execution_available"], true],
    [["explanation", "analysis_only"], false],
    [["explanation", "identity_mode"], "session"],
    [["explanation", "source_kind"], "latest_task"],
    [["explanation", "result", "metadata", "provider"], "fake-provider"],
    [["explanation", "result", "metadata", "requested_model"], "fake-model"],
    [["explanation", "result", "metadata", "returned_model"], "fake-model"],
    [["explanation", "result", "metadata", "request_id"], report.task_id],
    [["explanation", "result", "metadata", "pricing_version"], "fake-pricing"],
    [["explanation", "result", "metadata", "cost_estimate"], "0"],
    [["explanation", "result", "metadata", "evidence_mode"], "actual_provider"],
    [["explanation", "result", "metadata", "latency_ms"], 0],
    [["explanation", "result", "metadata", "usage"], { input_tokens: 0, output_tokens: 0, total_tokens: 0 }],
  ] as [string[], unknown][]) {
    expect(verifyReadResponse("GET", path, 200, changed(value, keys, replacement))).toBe(false);
  }
  for (const [keys, replacement] of [
    [["explanation", "child_task_id"], null],
    [["explanation", "child_task_id"], true],
    [["explanation", "schema_version"], "p4-p3-template-read-v1"],
    [["explanation", "source_kind"], "p2_original"],
  ] as [string[], unknown][]) {
    expect(verifyReadResponse("GET", path, 200,
      changed(explanation("template"), keys, replacement))).toBe(false);
  }
});
test("BC02 P3跨字段约束拒绝observation/snapshot/report/hash/逐SKU污染及非UTC时间", () => {
  for (const [keys, replacement] of [
    [["explanation", "observation_id"], report.task_id],
    [["explanation", "source_kind"], "p3_observation"],
    [["explanation", "task_id"], report.source.source_task_id],
    [["explanation", "report_id"], report.task_id],
    [["explanation", "snapshot_id"], report.task_id],
    [["explanation", "facts_hash"], "f".repeat(64)],
    [["explanation", "result", "lines", "0", "facts_hash"], "e".repeat(64)],
    [["explanation", "result", "lines", "0", "reference_ids", "report_id"], report.task_id],
    [["explanation", "result", "lines", "0", "reference_ids", "snapshot_id"], report.task_id],
    [["explanation", "created_at"], "2026-10-10T10:00:00+01:00"],
  ] as [string[], unknown][]) {
    expect(verifyReadResponse("GET", path, 200, changed(p3Explanation(), keys, replacement))).toBe(false);
  }
  expect(verifyReadResponse("GET", path, 200,
    changed(p3Explanation("p3_observation"), ["explanation", "observation_id"], report.task_id))).toBe(false);
  expect(verifyReadResponse("GET", path, 200,
    changed(p3Explanation(), ["explanation", "result", "lines"],
      [p3Explanation().explanation.result.lines[0], p3Explanation().explanation.result.lines[0]]))).toBe(false);
});
test("BC02 当前请求task及报告完整集合绑定，新旧分支均拒绝缺SKU/异risk与跨报告", () => {
  for (const value of [p3Explanation(), explanation()]) {
    expect(verifyReadResponse("GET", `/api/v1/tasks/${report.source.source_task_id}/explanation`, 200, value)).toBe(false);
    for (const [keys, replacement] of [
      [["explanation", "result", "lines"], value.explanation.result.lines.slice(1)],
      [["explanation", "result", "lines", "0", "reason"], "normal"],
      [["report_id"], report.task_id],
    ] as [string[], unknown][]) {
      expect(explanationBound(report, changed(value, keys, replacement))).toBe(false);
    }
  }
  const sourceChanged = changed(p3Explanation(), ["explanation", "source_task_id"], report.task_id);
  expect(verifyReadResponse("GET", path, 200, sourceChanged)).toBe(true);
  expect(explanationBound(report, sourceChanged)).toBe(false);
  expect(explanationBound({ ...report, facts: { ...report.facts,
    items: [...report.facts.items, report.facts.items[0]],
  } }, p3Explanation())).toBe(false);
});
test("BC02 模板仅复用原GET，NOT_READY/unavailable不变成缓存，401清身份", async () => {
  for (const [mode, code] of [["not_ready", "NOT_READY"], ["p3_unavailable", "SERVICE_UNAVAILABLE"], ["revoked", "SESSION_INVALID"]]) {
    const calls: { method: string; path: string; body?: string }[] = [];
    let invalidated = 0;
    const client = fixtureClient(mode, () => invalidated++, calls, { release() {}, revoke() {} });
    await expect(client.explanation(report.task_id, report.source.report_id)).rejects.toMatchObject({ code });
    expect(calls).toEqual([{ method: "GET", path }]);
    expect(invalidated).toBe(mode === "revoked" ? 1 : 0);
  }
});
