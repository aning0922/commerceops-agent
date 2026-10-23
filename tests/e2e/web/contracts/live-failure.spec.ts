import { test, expect } from "../../../../frontend/tooling/web-test";
import LiveReporter, { liveFailurePolicy, safeLiveError, safeLiveLocation, safeLivePhase, validLiveFailureDiagnostic } from "../../../../frontend/tooling/live-reporter";
import type { TestCase, TestResult, TestError, FullResult } from "../../../../frontend/node_modules/@playwright/test/reporter";
import { mkdtempSync, readFileSync, existsSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
const root = resolve(__dirname, "../../../..");
const policy = liveFailurePolicy();
const canary = "offline_private_canary_" + "z".repeat(20);
function fixture(stage: "read" | "write" | "items" | "n01", status: TestResult["status"] = "failed") {
  const definition = policy.cases.get(stage)![0];
  const item = { title: definition.test, location: { file: resolve(root, definition.file), line: definition.line, column: 1 } } as TestCase;
  const error = { message: `Error: expect(locator).toHaveText(expected) failed\n${canary}`, stack: canary, snippet: canary, value: canary, cause: { message: canary }, location: item.location };
  const result = { status, duration: 123, error, errors: [error], steps: [] } as unknown as TestResult;
  return { item, result };
}
async function ownedReporter(batch: string, body: (reporter: LiveReporter, directory: string) => void) {
  const directory = mkdtempSync(resolve(tmpdir(), "c10-safe-reporter-"));
  const cwd = process.cwd(), old = process.env.COMMERCEOPS_WEB_BATCH, oldPrivate = process.env.COMMERCEOPS_B02_PRIVATE_DIR, oldLog = console.log;
  try {
    process.chdir(directory); process.env.COMMERCEOPS_WEB_BATCH = batch; process.env.COMMERCEOPS_B02_PRIVATE_DIR = directory;
    console.log = () => {}; // Synthetic callbacks must not look like actual API results in CI logs.
    body(new LiveReporter(), directory);
  } finally {
    process.chdir(cwd);
    if (old === undefined) delete process.env.COMMERCEOPS_WEB_BATCH; else process.env.COMMERCEOPS_WEB_BATCH = old;
    if (oldPrivate === undefined) delete process.env.COMMERCEOPS_B02_PRIVATE_DIR; else process.env.COMMERCEOPS_B02_PRIVATE_DIR = oldPrivate;
    console.log = oldLog;
    rmSync(directory, { recursive: true, force: true });
  }
}
test("C10 固定源码30用例/四stage完整；仅安全分类，不读stack/snippet/value/cause", () => {
  expect([...policy.cases.values()].map((cases) => cases.length)).toEqual([7, 10, 7, 6]);
  const error = { message: `Error: expect(locator).toHaveText(expected) failed\n${canary}` } as TestError;
  for (const key of ["stack", "snippet", "value", "cause"])
    Object.defineProperty(error, key, { get: () => { throw new Error("forbidden raw access"); } });
  const safe = safeLiveError(error, "failed", policy);
  expect(safe).toEqual({ category: "ASSERTION_FAILURE", matcher: "toHaveText", location: null });
  expect(JSON.stringify(safe)).not.toContain(canary);
  expect(safeLiveError({ message: canary }, "timedOut", policy).category).toBe("TEST_TIMEOUT");
  expect(safeLiveError({ message: `SyntaxError: ${canary}` }, "failed", policy).category).toBe("PREPARATION_ERROR");
  expect(safeLiveError({ message: canary }, "failed", policy).category).toBe("UNKNOWN");
});
test("C10 错误位置只认tracked test/frontend代码及实际有效行，不回显任意路径", () => {
  const { item } = fixture("n01");
  expect(safeLiveLocation(item.location, policy)).toEqual({ file: "tests/e2e/web/live/n01.spec.ts", line: item.location.line });
  for (const location of [
    { file: `/private/${canary}`, line: 1, column: 1 },
    { ...item.location, line: -1 }, { ...item.location, line: 100001 },
    { file: resolve(root, "frontend/.env"), line: 1, column: 1 },
  ]) expect(safeLiveLocation(location, policy)).toBeNull();
});
test("C10 body分母和hook/unknown分开，未观察不得预设六例执行", () => {
  expect(safeLivePhase({ status: "failed", steps: [] })).toEqual({ phase: "unknown", body_observed: null });
  expect(safeLivePhase({ status: "failed", steps: [{ category: "hook", title: "Before Hooks", error: { message: canary } }] } as TestResult)).toEqual({ phase: "before_hooks", body_observed: false });
  expect(safeLivePhase({ status: "failed", steps: [{ category: "expect", title: canary }] } as TestResult)).toEqual({ phase: "test_body", body_observed: true });
});
for (const [batch, stage, path] of [
  ["b04-read", "read", "evidence/b04-live/read"],
  ["b04-write", "write", "evidence/b04-live/write"],
  ["b04", "items", "evidence/b04-live"],
  ["p4-c09-n01", "n01", "evidence/p4-c09/n01"],
] as const) test(`C10 ${stage}失败sidecar闭合落盘，无秘密且原report字段不扩展`, async () => {
  await ownedReporter(batch, (reporter, dir) => {
    const { item, result } = fixture(stage);
    reporter.onTestEnd(item, result);
    reporter.onError({ message: canary, stack: canary, location: { file: canary, line: 1, column: 1 } });
    reporter.onEnd({ status: "failed", duration: 222 } as FullResult);
    const sidecar = resolve(dir, path, "failure-diagnostic.safe.json"), raw = readFileSync(sidecar, "utf8"), data = JSON.parse(raw);
    expect(raw).not.toContain(canary);
    expect(validLiveFailureDiagnostic(data, policy)).toBe(true);
    expect(data.reported_count).toBe(1); expect(data.actual_body_count).toBeNull();
    expect(data.unreported_count).toBe(data.expected_count - 1);
    expect(data.tests[0].error.category).toBe("ASSERTION_FAILURE");
    expect(statSync(sidecar).mode & 0o777).toBe(0o600);
    const legacy = JSON.parse(readFileSync(resolve(dir, path, "live-results.json"), "utf8"));
    expect(Object.keys(legacy).sort()).toEqual(["status", "duration_ms", "trace", "video", "automatic_screenshot", "source_mode", "commerce_source_mode", "identity_mode", "tests"].sort());
    for (const mutate of [
      (v: typeof data) => { v.tests[0].test = canary; },
      (v: typeof data) => { v.tests[0].error.location = { file: `frontend/${canary}.ts`, line: 1 }; },
      (v: typeof data) => { v.counts.failed = 99; },
      (v: typeof data) => { v.actual_body_count = 6; },
      (v: typeof data) => { v.tests[0].error.message = canary; },
    ]) { const bad = structuredClone(data); mutate(bad); expect(validLiveFailureDiagnostic(bad, policy)).toBe(false); }
  });
});
test("C10 unknown title/重复结果拒绝；不落原字符串，不使缺失分母成为零", async () => {
  await ownedReporter("p4-c09-n01", (reporter, dir) => {
    const { item, result } = fixture("n01");
    reporter.onTestEnd({ ...item, title: canary } as TestCase, result);
    reporter.onTestEnd(item, result); reporter.onTestEnd(item, result);
    reporter.onEnd({ status: "failed", duration: 222 } as FullResult);
    const raw = readFileSync(resolve(dir, "evidence/p4-c09/n01/failure-diagnostic.safe.json"), "utf8"), data = JSON.parse(raw);
    expect(raw).not.toContain(canary); expect(data.rejected_result_count).toBe(2);
    expect(data.reported_count).toBe(1); expect(data.actual_body_count).toBeNull();
  });
});
test("C10 正常success原report合同保持且不生成failure样本", async () => {
  await ownedReporter("p4-c09-n01", (reporter, dir) => {
    for (const definition of policy.cases.get("n01")!) {
      reporter.onTestEnd({ title: definition.test, location: { file: resolve(root, definition.file), line: definition.line, column: 1 } } as TestCase, { status: "passed", duration: 1, steps: [], errors: [] } as unknown as TestResult);
    }
    reporter.onEnd({ status: "passed", duration: 10 } as FullResult);
    const path = resolve(dir, "evidence/p4-c09/n01");
    const report = JSON.parse(readFileSync(resolve(path, "live-results.json"), "utf8"));
    expect(report.tests).toHaveLength(6); expect(report.tests.every((r: { status: string }) => r.status === "passed")).toBe(true);
    expect(existsSync(resolve(path, "failure-diagnostic.safe.json"))).toBe(false);
  });
});
test("C10 clean passed不能冒失败产物；异常passed只诊断不签Gate且global错误有界", async () => {
  await ownedReporter("p4-c09-n01", (reporter, dir) => {
    for (const definition of policy.cases.get("n01")!) {
      reporter.onTestEnd({ title: definition.test, location: { file: resolve(root, definition.file), line: definition.line, column: 1 } } as TestCase, { status: "passed", duration: 1, steps: [], errors: [] } as unknown as TestResult);
    }
    for (let i = 0; i < 20; i++) reporter.onError({ message: canary, stack: canary });
    reporter.onEnd({ status: "passed", duration: 10 } as FullResult);
    const raw = readFileSync(resolve(dir, "evidence/p4-c09/n01/failure-diagnostic.safe.json"), "utf8"), data = JSON.parse(raw);
    expect(raw).not.toContain(canary); expect(data.status).toBe("passed");
    expect(data.global_error_count).toBe(20); expect(data.global_errors).toHaveLength(16);
    expect(validLiveFailureDiagnostic(data, policy)).toBe(true);
    data.global_error_count = 0; data.global_errors = [];
    expect(validLiveFailureDiagnostic(data, policy)).toBe(false);
  });
});
for (const [batch, path] of [["b02", "evidence/b02-read"], ["b03", "evidence/b03"]] as const)
  test(`C10 ${batch}非目标历史success行为不受新白名单/sidecar影响`, async () => {
    await ownedReporter(batch, (reporter, dir) => {
      expect(reporter.policy).toBeNull();
      reporter.onTestEnd({ title: "历史专用源码用例", location: { file: resolve(root, "tests/e2e/web/live/read.spec.ts"), line: 10, column: 1 } } as TestCase, { status: "passed", duration: 1, errors: [], steps: [] } as unknown as TestResult);
      reporter.onEnd({ status: "passed", duration: 1 } as FullResult);
      const report = JSON.parse(readFileSync(resolve(dir, path, "live-results.json"), "utf8"));
      expect(report.tests[0]).toEqual({ test: "历史专用源码用例", status: "passed", duration_ms: 1, location: "e2e/web/live/read.spec.ts:10" });
      expect(existsSync(resolve(dir, path, "failure-diagnostic.safe.json"))).toBe(false);
    });
  });
test("C10 target非法FullResult metadata拒绝，不先写含任意字符串的旧报告", async () => {
  await ownedReporter("p4-c09-n01", (reporter, dir) => {
    expect(() => reporter.onEnd({ status: canary, duration: 1 } as unknown as FullResult)).toThrow("Invalid live result metadata");
    expect(() => reporter.onEnd({ status: "failed", duration: Number.NaN } as FullResult)).toThrow("Invalid live result metadata");
    expect(existsSync(resolve(dir, "evidence/p4-c09/n01/live-results.json"))).toBe(false);
    expect(existsSync(resolve(dir, "evidence/p4-c09/n01/failure-diagnostic.safe.json"))).toBe(false);
  });
});
