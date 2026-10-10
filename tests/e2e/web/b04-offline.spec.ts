import { test, expect } from "../../../frontend/tooling/web-test";
import type { Page } from "../../../frontend/tooling/web-test";
import { offlineId } from "../../../frontend/lib/b04-offline-source";
import { resolve } from "node:path";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import {
  readOwnedListener,
  assertOwnedMockProcess,
  assertOwnedBuild,
  assertOwnedListener,
} from "./owned-listeners";
const evidence = resolve(__dirname, "../../../frontend/evidence/b04-linux-fix");
test.beforeAll(() => {
  const output = readOwnedListener(3490).trim().split(/\s+/);
  if (!output.length || new Set(output).size !== 1)
    throw new Error("Exclusive owned Mock listener required");
  const pid = Number(output[0]);
  assertOwnedListener(output.join("\n"), pid);
  const uid = assertOwnedMockProcess(
    pid,
    resolve(__dirname, "../../../frontend"),
    Number(process.env.COMMERCEOPS_B04_MOCK_LAUNCH_PID),
  );
  expect(() =>
    assertOwnedMockProcess(
      pid,
      resolve(__dirname, "../../.."),
      Number(process.env.COMMERCEOPS_B04_MOCK_LAUNCH_PID),
    ),
  ).toThrow();
  expect(() =>
    assertOwnedMockProcess(
      pid,
      resolve(__dirname, "../../../frontend"),
      process.pid,
    ),
  ).toThrow();
  const build = readFileSync(
    resolve(__dirname, "../../../frontend/.next/BUILD_ID"),
    "utf8",
  ).trim();
  assertOwnedBuild(process.env.COMMERCEOPS_B04_MOCK_BUILD_ID, build);
  mkdirSync(evidence, { recursive: true });
  writeFileSync(
    resolve(evidence, "mock-service.json"),
    JSON.stringify(
      {
        owner: "phase3-owned-b04-mock",
        uid,
        launcher_pid: Number(process.env.COMMERCEOPS_B04_MOCK_LAUNCH_PID),
        platform: process.platform,
        architecture: process.arch,
        checkout: resolve(__dirname, "../../.."),
        port: 3490,
        pid,
        started_observed_utc: new Date().toISOString(),
        build_id: build,
        source_mode: "mock",
        backend_API_PG_Worker: "not_started",
        headless: true,
        wrong_checkout_rejected: true,
        wrong_launcher_rejected: true,
      },
      null,
      2,
    ),
  );
});
const detail = `/replenishment-items/${offlineId(1)}`;
const forbidden = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const records: string[] = [];
  forbidden.set(page, records);
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (
      url.origin !== "http://127.0.0.1:3490" ||
      request.method() !== "GET" ||
      url.pathname.startsWith("/api/")
    )
      records.push("unexpected network operation");
  });
});
test.afterEach(async ({ page }) => {
  expect(forbidden.get(page)).toEqual([]);
});
async function prepare(
  page: Page,
  scenario = "ready",
  action = "B26",
  reason = "  明确内部跟进原因  ",
) {
  await page.goto(detail + "?scenario=" + scenario);
  await expect(page.locator('[data-source-mode="b04-offline"]')).toBeVisible();
  await page.locator(`[data-control="${action}"]`).click();
  await page.locator("#resolve-reason").fill(reason);
  await page.getByRole("button", { name: "确认原因并准备原请求" }).click();
  await expect(page.locator('[data-action="resolve-original"]')).toBeFocused();
}
test("明确Mock20项/390完整披露；execution completed仍不能推断项跟进或sync成功", async ({
  page,
}) => {
  await page.goto("/replenishment-items");
  await expect(page.locator(".list-row")).toHaveCount(20);
  await expect(page.getByRole("main")).toContainText("明确离线 Mock");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(page.locator(".list-row")).toHaveCount(20);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({
    path: resolve(evidence, "items-390.png"),
    fullPage: true,
  });
  await page
    .locator(".list-row")
    .last()
    .getByRole("link", { name: "查看工作项" })
    .click();
  await expect(page.getByRole("main")).toContainText("pool/offline/20");
  await expect(page.locator('[data-control="B26"]')).toBeEnabled();
  await page.goto(`/tasks/${offlineId(102)}/events`);
  await expect(page.getByRole("main")).toContainText(
    "不推断这些工作项已跟进完成",
  );
  await expect(page.locator(".list-row")).toHaveCount(20);
  await expect(page.getByRole("main")).toContainText("协作同步：失败");
  await expect(
    page.getByRole("button", { name: "手动恢复未开放" }),
  ).toBeDisabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("原因pristine/空白/1001字符，Tab/ShiftTab/Enter/Space/Esc与终态回执/无重开", async ({
  page,
}) => {
  await page.goto(detail);
  await page.locator('[data-control="B26"]').focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.locator("#reason-error")).toBeEmpty();
  await page.keyboard.press("Tab");
  await expect(page.locator("#resolve-reason")).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(
    page.getByRole("button", { name: "关闭记录内部跟进完成" }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.locator('[data-control="B26"]')).toBeFocused();
  await page.keyboard.press("Space");
  await page.getByRole("button", { name: "确认原因并准备原请求" }).click();
  await expect(page.locator("#reason-error")).toContainText("1–1000");
  await page.locator("#resolve-reason").fill("😀".repeat(1001));
  await page.getByRole("button", { name: "确认原因并准备原请求" }).click();
  await expect(page.locator('[data-action="resolve-original"]')).toHaveCount(0);
  await page.locator("#resolve-reason").fill("\u001f跟进已完成\u0085");
  await page.getByRole("button", { name: "确认原因并准备原请求" }).click();
  await expect(page.locator('[data-action="resolve-original"]')).toBeFocused();
  await expect(page.getByRole("dialog")).toContainText("原因：跟进已完成");
  await page.keyboard.press("Enter");
  await expect(page.getByText("内部跟进已记录", { exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("state completed · v2");
  await expect(page.getByRole("dialog")).toContainText("同步 失败");
  await page.keyboard.press("Escape");
  await expect(page.getByText("终态只读", { exact: true })).toBeVisible();
  await expect(page.locator("[data-item-summary]")).toBeFocused();
  await expect(page.locator('[data-control="B26"]')).toHaveCount(0);
  await expect(page.locator('[data-control="B27"]')).toHaveCount(0);
  await page.screenshot({
    path: resolve(evidence, "resolve-receipt-1440.png"),
    fullPage: true,
  });
});
test("关闭原因保留FEFF/组合字符，dirty关闭需显式丢弃；terminal/readonly无入口", async ({
  page,
}) => {
  await page.goto(detail);
  await page.locator('[data-control="B27"]').click();
  await page.locator("#resolve-reason").fill("\ufeffe\u0301\ufeff");
  await page.keyboard.press("Escape");
  await expect(
    page.getByText("确认丢弃未提交草稿", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "确认原因并准备原请求" }).click();
  await expect(page.locator('[data-action="resolve-original"]')).toBeFocused();
  await page.keyboard.press("Space");
  await expect(page.getByText("内部跟进已记录", { exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("state closed · v2");
  for (const scenario of ["terminal", "readonly"]) {
    await page.goto(detail + "?scenario=" + scenario);
    await expect(page.locator('[data-control="B26"]')).toHaveCount(0);
    await expect(page.locator('[data-control="B27"]')).toHaveCount(0);
  }
});
test("注入ACK unknown仅原键恢复，不自动提交/新键，GET回执后显式同键回放", async ({
  page,
}) => {
  await prepare(page, "unknown");
  const key = await page
    .getByRole("dialog")
    .locator("p")
    .filter({ hasText: "原键：" })
    .innerText();
  await page.keyboard.press("Enter");
  await expect(
    page.getByText("内部项提交待核实", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("dialog")).toContainText(key);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.locator('[data-action="resolve-receipt"]').click();
  await expect(page.getByText("内部跟进已记录", { exact: true })).toBeVisible();
  await page.locator('[data-action="resolve-original"]').click();
  await expect(page.getByRole("dialog")).toContainText("duplicate true");
  await expect(page.getByRole("dialog")).toContainText(key);
});
test("unknown原键404仍待核实；409版本/终态与损坏绑定分别呈现", async ({
  page,
}) => {
  await prepare(page, "missing");
  await page.locator('[data-action="resolve-original"]').click();
  await expect(
    page.getByText("内部项提交待核实", { exact: true }),
  ).toBeVisible();
  await page.locator('[data-action="resolve-receipt"]').click();
  await expect(page.getByRole("dialog")).toContainText("不证明提交失败");
  for (const scenario of ["conflict", "state_conflict", "bad_receipt"]) {
    await page.goto("about:blank");
    await prepare(page, scenario);
    await page.locator('[data-action="resolve-original"]').click();
    await expect(page.getByRole("dialog")).toContainText(
      scenario === "conflict"
        ? "工作项版本已改变"
        : scenario === "state_conflict"
          ? "工作项已进入终态"
          : "提交结果待核实",
    );
    await expect(page.locator("#resolve-reason")).toHaveCount(0);
  }
});
test("注入401清预备请求/身份/业务缓存；404同安全状态", async ({ page }) => {
  await prepare(page, "revoked");
  await page.locator('[data-action="resolve-original"]').click();
  await expect(page.getByRole("main")).toContainText(
    "身份、业务缓存与预备操作已清除",
  );
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("main")).not.toContainText(offlineId(1));
  await page.goto(detail + "?scenario=not_found");
  await expect(page).toHaveURL(/\/access$/);
  await expect(page.getByRole("main")).toContainText("页面不可访问");
  await expect(page.locator('[data-control="B26"]')).toHaveCount(0);
});
test("新联动范围filter与隐藏来源：当前can_resolve可用不借旧task/plan权限", async ({
  page,
}) => {
  await page.goto("/replenishment-items");
  await page.locator('[data-control="B24"]').selectOption("closed");
  await expect(page.locator(".list-row")).toHaveCount(0);
  await expect(page.getByRole("main")).toContainText("服务端总计 0");
  await page.locator('[data-control="B24"]').selectOption("all");
  await expect(page.locator(".list-row")).toHaveCount(20);
  await prepare(page, "hidden_source");
  await expect(page.getByRole("main")).not.toContainText(offlineId(103));
  await expect(page.locator('[data-control="B37"]')).toHaveCount(0);
  await page.locator('[data-action="resolve-original"]').click();
  await expect(page.getByText("内部跟进已记录", { exact: true })).toBeVisible();
});
test("预备后200会话身份变更仍清原操作，不把旧项交给新principal", async ({
  page,
}) => {
  await prepare(page, "auth_changed");
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("main")).toContainText(
    "身份、业务缓存与预备操作已清除",
  );
  await expect(page.locator('[data-action="resolve-original"]')).toHaveCount(0);
  await expect(page.getByRole("main")).not.toContainText(offlineId(1));
});
