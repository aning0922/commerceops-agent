import { test, expect } from "@playwright/test";
import completed from "./daily-read.fixture.json" with { type: "json" };
import empty from "./daily-empty.fixture.json" with { type: "json" };
import partial from "./daily-partial.fixture.json" with { type: "json" };

const id = completed.daily.task_id;
const sender = { destination_alias: "IM", sender_enabled: false, reason_code: "NOT_CONFIGURED",
  verification_mode: null, as_of: "2026-11-03T03:42:00Z", worker_ready: null };
const session = {
  schema_version: "p3-web-v1", identity_mode: "session", server_time: "2026-11-03T03:42:00Z",
  trace_id: "00000000-0000-4000-8000-000000000099", csrf_token: "c".repeat(43),
  principal: {
    principal_id: "00000000-0000-4000-8000-000000000105", organization_id: "00000000-0000-4000-8000-000000000109",
    display_name: "测试运营员", auth_version: 1, linked_channels: ["web"],
    role_shop_grants: [{ role: "operator", shop_id: completed.daily.shop_id }],
    capabilities: { can_create_task: false, can_read_tasks: true, can_read_approvals: false,
      can_resolve_items: false, can_read_operations: false, home_path: "/tasks" },
  },
  absolute_expires_at: "2026-11-04T03:42:00Z", idle_expires_at: "2026-11-03T04:12:00Z",
  config: { config_version: "ui-fixture-v1", shop_timezone: "Asia/Taipei", approval_ttl_seconds: 1800,
    revalidation_max_age_seconds: 450, max_plan_items: 20, recovery_scan_seconds: 10,
    session_absolute_seconds: 28800, session_idle_seconds: 1800, transport_mode: "local_http",
    source_mode: "mock", model_requests_enabled: false, external_sender_enabled: false,
    sender_gates: [sender, { ...sender, destination_alias: "Base" }] },
};
const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
async function setup(page: import("@playwright/test").Page, body: unknown) {
  await page.route("**/api/v1/**", route => route.abort());
  await page.route("**/api/v1/auth/session", route => route.fulfill(json(session)));
  await page.route("**/api/v1/daily-reports/*", route => route.fulfill(json(body)));
}

test.describe("UI_FIXTURE daily detail", () => {
  test.skip(!process.env.COMMERCEOPS_M3_UI_FIXTURE_URL, "Requires owned local Next fixture server");
  for (const width of [1440, 1280, 390]) {
    test(`complete ${width}px, browser scale and CSS zoom, drawer and keyboard`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 1000 });
      await setup(page, completed);
      await page.goto(`/daily-reports/${id}`);
      await expect(page.getByRole("heading", { name: "经营日报" })).toBeVisible();
      await expect(page.getByText("付款订单总额", { exact: true })).toBeVisible();
      await expect(page.getByText("原值：", { exact: false }).first()).toBeVisible();
      await expect(page.getByText("日报已生成。", { exact: false })).toBeVisible();
      await expect(page.getByRole("button", { name: /追问|推送|发送/ })).toHaveCount(0);
      const trigger = page.getByRole("button", { name: "查看来源与证据引用" });
      await trigger.focus();
      await page.keyboard.press("Enter");
      const dialog = page.getByRole("dialog", { name: "来源与证据引用" });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByText("事实摘要", { exact: false })).toBeHidden();
      await dialog.getByText("报告绑定与版本").click();
      await expect(dialog.getByText("事实摘要", { exact: false })).toBeVisible();
      await dialog.getByRole("button", { name: "关闭来源与证据引用" }).focus();
      await page.keyboard.press("Shift+Tab");
      await expect(dialog.getByText("报告绑定与版本")).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(dialog.getByRole("button", { name: "关闭来源与证据引用" })).toBeFocused();
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(trigger).toBeFocused();
      await page.screenshot({ path: info.outputPath(`ui-fixture-${width}.png`), fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const cdp = await page.context().newCDPSession(page);
      await cdp.send("Emulation.setPageScaleFactor", { pageScaleFactor: 2 });
      expect(await page.evaluate(() => visualViewport?.scale)).toBe(2);
      await page.screenshot({ path: info.outputPath(`ui-fixture-${width}-browser-scale200.png`), fullPage: true });
      await cdp.send("Emulation.setPageScaleFactor", { pageScaleFactor: 1 });
      await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: info.outputPath(`ui-fixture-${width}-css-zoom200.png`), fullPage: true });
    });
  }
  test("empty, partial null, failed, revocation", async ({ page }) => {
    let body: unknown = empty;
    let status = 200;
    await page.route("**/api/v1/**", route => route.abort());
    await page.route("**/api/v1/auth/session", route => route.fulfill(json(session)));
    await page.route("**/api/v1/daily-reports/*", route => route.fulfill(json(body, status)));
    await page.goto(`/daily-reports/${id}`);
    await expect(page.getByText("付款订单数", { exact: true })).toBeVisible();
    body = partial;
    await page.getByRole("button", { name: "刷新会话与当前页" }).click();
    await expect(page.getByText("指标未提供", { exact: false })).toBeVisible();
    expect(await page.getByText("付款订单总额", { exact: true }).count()).toBe(0);
    body = { ...completed, daily: { ...completed.daily, state: "failed", failure_code: "DAILY_SOURCE_UNAVAILABLE", report: null } };
    await page.getByRole("button", { name: "刷新会话与当前页" }).click();
    await expect(page.getByText("日报生成失败。", { exact: false })).toBeVisible();
    status = 403;
    await page.getByRole("button", { name: "刷新会话与当前页" }).click();
    await expect(page.getByRole("heading", { name: "登录运营工作台" })).toBeVisible();
    await expect(page.getByText("日报生成失败。", { exact: false })).toHaveCount(0);
  });
});
