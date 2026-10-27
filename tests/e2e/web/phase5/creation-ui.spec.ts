import type {} from "./test-control";
import { test, expect } from "../../../../frontend/tooling/web-test";
import type { Page } from "../../../../frontend/tooling/web-test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import cases from "../phase4/n01.fixture.json";
const root = resolve(__dirname, "../../../..");
const evidence = resolve(root, "runtime/m2-web-creation");
let bundle: string;
test.beforeAll(() => {
  execFileSync(process.execPath, [resolve(__dirname, "build-preview.mjs"), "--creation"], { cwd: root, timeout: 45000 });
  bundle = readFileSync(resolve(root, ".audit/p5-creation-preview/bundle.js"), "utf8");
  mkdirSync(evidence, { recursive: true, mode: 0o700 });
});
async function start(page: Page, kind = "woo", mode = "success", fromReport = false, operator = true) {
  await page.route("**/*", (route) => route.abort());
  await page.setContent('<html><body><div id="p5-root"></div></body></html>');
  await page.addStyleTag({ content: readFileSync(resolve(root, "frontend/app/globals.css"), "utf8") });
  // about:blank has no secure-origin randomUUID; the memory-only harness injects
  // one fixed synthetic UUID. Product browsers use their native secure-context API.
  await page.evaluate(() => Object.defineProperty(window.crypto, "randomUUID", {
    value: () => "00000000-0000-4000-8000-000000000320",
  }));
  await page.addScriptTag({ content: bundle });
  await page.evaluate(async ({ kind, mode, fromReport, operator }) => window.__p5CreateStart(kind, mode, fromReport, operator), { kind, mode, fromReport, operator });
  await expect(page.getByRole("dialog")).toBeVisible();
}
const writes = (page: Page) => page.evaluate(() => window.__p5CreateCalls().filter((c) => c.path === "/api/v1/tasks"));
async function confirm(page: Page) {
  await expect(page.getByRole("button", { name: "确认结构化参数", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "确认结构化参数", exact: true }).click();
  await page.getByRole("button", { name: "准备本次正式任务请求", exact: true }).click();
}
for (const width of [1440, 390]) test(`Woo readonly N01→人工确认→显式T1；来源版本和键盘布局 ${width}`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 });
  await start(page);
  await expect(page.getByRole("dialog")).toContainText("Woo 测试店 · 来源版本 synthetic-woo-config-v1");
  await expect(page.getByRole("combobox", { name: "Mock案例", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "使用自然语言请求草稿" }).click();
  await page.getByLabel("自然语言请求草稿", { exact: true }).fill(cases.cases[0].text);
  await page.getByRole("button", { name: "检查草稿与参数", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toContainText("已识别明确参数，仍待你确认");
  await expect(page.getByRole("dialog")).toContainText("服务端可信来源配置");
  expect(await writes(page)).toHaveLength(0);
  await expect(page.getByRole("button", { name: "准备本次正式任务请求" })).toBeDisabled();
  await confirm(page);
  expect(await writes(page)).toHaveLength(0);
  await page.getByRole("button", { name: "明确提交本次请求", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("正式任务创建回执");
  const calls = await writes(page);
  expect(calls).toHaveLength(1);
  expect(JSON.parse(calls[0].body!).parameters).toEqual({ source_mode: "woocommerce_test", source_config_version: "synthetic-woo-config-v1", L: 3, R: 7, S: 2 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  await page.screenshot({ path: resolve(evidence, `woo-create-${width}.png`), fullPage: true });
});
test("Woo missing parameters stay blank until manual clarification; changed source invalidates only unsent draft", async ({ page }) => {
  await start(page);
  await page.getByRole("button", { name: "使用自然语言请求草稿" }).click();
  const sample = cases.cases.find((row) => row.result.reason === "MISSING_PARAMETERS")!;
  await page.getByLabel("自然语言请求草稿", { exact: true }).fill(sample.text);
  await page.getByRole("button", { name: "检查草稿与参数", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("请补齐明确参数后再确认");
  for (const name of sample.result.missing) {
    await expect(page.getByLabel(`${name}（0–365整数）`, { exact: true })).toHaveValue("");
    await page.getByLabel(`${name}（0–365整数）`, { exact: true }).fill("4");
  }
  await page.getByRole("button", { name: "确认结构化参数", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("参数已明确确认");
  await page.evaluate(() => window.__p5CreateUpdate("woo", "synthetic-woo-config-v2"));
  await page.getByRole("button", { name: "重新核实店铺来源" }).click();
  await expect(page.getByRole("dialog")).toContainText("来源版本 synthetic-woo-config-v2");
  await expect(page.getByRole("button", { name: "准备本次正式任务请求" })).toBeDisabled();
  await expect(page.getByRole("dialog")).not.toContainText("参数已明确确认");
  expect(await writes(page)).toHaveLength(0);
});
for (const kind of ["disabled", "missing"]) test(`${kind} Woo source cannot create or fall back Mock`, async ({ page }) => {
  await start(page, kind);
  await expect(page.getByRole("button", { name: "确认结构化参数", exact: true })).toBeDisabled();
  await expect(page.getByRole("combobox", { name: "Mock案例", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "使用自然语言请求草稿" }).click();
  await page.getByLabel("自然语言请求草稿", { exact: true }).fill(cases.cases[0].text);
  await expect(page.getByRole("button", { name: "检查草稿与参数", exact: true })).toBeDisabled();
  expect(await writes(page)).toHaveLength(0);
});
test("operator shop is required even with enabled capability", async ({ page }) => {
  await start(page, "woo", "success", false, false);
  await expect(page.getByRole("dialog")).toContainText("没有该店铺的operator创建资格");
  await expect(page.getByRole("button", { name: "确认结构化参数", exact: true })).toBeDisabled();
  expect(await page.evaluate(() => window.__p5CreateCalls().filter((c) => c.path === "/api/v1/config"))).toHaveLength(0);
});
test("pending and UNKNOWN survive source rerender; original-key read and explicit replay preserve bytes", async ({ page }) => {
  await start(page, "woo", "pending");
  await confirm(page);
  // A prepared but unsent request is already immutable, too.
  await page.evaluate(() => window.__p5CreateUpdate("woo", "synthetic-woo-config-v2"));
  expect(await page.evaluate(() => window.__p5CreateCalls().filter((c) => c.path === "/api/v1/config"))).toHaveLength(1);
  expect(await writes(page)).toHaveLength(0);
  await page.getByRole("button", { name: "明确提交本次请求", exact: true }).click();
  await page.evaluate(() => window.__p5CreateUpdate("disabled"));
  await expect(page.getByRole("dialog")).toContainText("正在提交");
  expect(await writes(page)).toHaveLength(1);
  await page.evaluate(() => window.__p5CreateRelease());
  await expect(page.getByRole("dialog")).toContainText("提交结果待核实");
  await page.getByRole("button", { name: "关闭创建正式补货任务", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "读取原请求回执", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("原键暂无可见回执，仍待核实");
  expect(await writes(page)).toHaveLength(1);
  await page.evaluate(() => { window.__p5CreateUpdate("woo", "synthetic-woo-config-v2"); window.__p5CreateWriteMode("success"); });
  await page.getByText("原请求技术详情与受控恢复", { exact: true }).click();
  await page.getByRole("button", { name: "显式同键重投原请求", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("正式任务创建回执");
  const calls = await writes(page);
  expect(calls).toHaveLength(2);
  expect(calls[1].body).toBe(calls[0].body);
  expect(JSON.parse(calls[1].body!).parameters.source_config_version).toBe("synthetic-woo-config-v1");
  expect(await page.evaluate(() => window.__p5CreateCalls().filter((c) => c.path.endsWith("/login")))).toHaveLength(0);
});
test("late N01 result cannot restore confirmation after source refresh", async ({ page }) => {
  await start(page, "woo", "late_preflight");
  await page.getByRole("button", { name: "使用自然语言请求草稿" }).click();
  await page.getByLabel("自然语言请求草稿", { exact: true }).fill(cases.cases[0].text);
  await page.getByRole("button", { name: "检查草稿与参数", exact: true }).click();
  await page.evaluate(() => window.__p5CreateUpdate("woo", "synthetic-woo-config-v2"));
  await page.getByRole("button", { name: "重新核实店铺来源" }).click();
  await expect(page.getByRole("dialog")).toContainText("来源版本 synthetic-woo-config-v2");
  await page.evaluate(() => window.__p5CreateRelease());
  await expect(page.getByRole("dialog")).not.toContainText("已识别明确参数，仍待你确认");
  await expect(page.getByRole("button", { name: "确认结构化参数", exact: true })).toBeDisabled();
  expect(await writes(page)).toHaveLength(0);
});
test("legacy confirmed scoped Mock retains cases/N01 and from_report keeps original references", async ({ page }) => {
  await start(page, "mock");
  await expect(page.getByRole("combobox", { name: "Mock案例", exact: true })).toBeVisible();
  expect(await page.getByRole("combobox", { name: "Mock案例", exact: true }).locator("option").allTextContents()).toEqual(["baseline", "known_inbound", "unknown_inbound", "unknown_stock", "normal", "no_demand"]);
  await page.getByRole("button", { name: "使用自然语言请求草稿" }).click();
  await page.getByLabel("自然语言请求草稿", { exact: true }).fill(cases.cases[0].text);
  await page.getByRole("button", { name: "检查草稿与参数", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Mock / inventory-v1 / baseline");
  await confirm(page);
  await page.getByRole("button", { name: "明确提交本次请求", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("正式任务创建回执");
  expect(JSON.parse((await writes(page))[0].body!).parameters.source_mode).toBe("mock");
  await page.reload();
  await start(page, "woo", "success", true);
  await page.getByRole("button", { name: "准备本次正式任务请求" }).click();
  await page.getByRole("button", { name: "明确提交本次请求", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("正式任务创建回执");
  const body = JSON.parse((await writes(page))[0].body!);
  expect(body.mode).toBe("from_report");
  expect(Object.keys(body).sort()).toEqual(["schema_version", "mode", "request_key", "source_task_id", "source_report_id", "snapshot_id", "facts_hash"].sort());
  expect(await page.evaluate(() => window.__p5CreateCalls().filter((c) => c.path === "/api/v1/config"))).toHaveLength(0);
});
