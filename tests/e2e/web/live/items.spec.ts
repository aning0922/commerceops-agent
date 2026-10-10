// B04 live suite preparation. It must be run only after Root authorizes a newly
// registered owned PG/API/Next window; this file does not create any services.
import { test, expect } from "../../../../frontend/tooling/web-test";
import type {
  BrowserContext,
  Page,
} from "../../../../frontend/tooling/web-test";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import {
  ownedEndpoints,
  assertOwnedListener,
  assertOwnedBuild,
} from "../owned-listeners";
const root = resolve(__dirname, "../../../..");
const directory = process.env.COMMERCEOPS_B02_PRIVATE_DIR;
if (!directory || process.env.COMMERCEOPS_WEB_BATCH !== "b04")
  throw new Error("Explicit authorized B04 owned window required");
const read = (name: string) =>
  JSON.parse(readFileSync(resolve(directory!, name), "utf8"));
const windowInfo = read("window.json"),
  accounts = read("web-accounts.json");
// The new window's own seeder records resources; never read an old author's fixture.
const facts = read("b04-facts.json");
for (const endpoint of ownedEndpoints(
  windowInfo,
  process.env.COMMERCEOPS_LIVE_WEB_URL,
))
  assertOwnedListener(
    execFileSync(
      "lsof",
      ["-nP", `-iTCP:${endpoint.port}`, "-sTCP:LISTEN", "-t"],
      { encoding: "utf8" },
    ),
    endpoint.pid,
  );
assertOwnedBuild(
  windowInfo.build_id,
  readFileSync(resolve(root, "frontend/.next/BUILD_ID"), "utf8"),
);
if (Date.now() >= Date.parse(windowInfo.stop_at_utc))
  throw new Error("Owned B04 window expired");
const contexts = new Map<string, BrowserContext>();
test.beforeAll(async ({ browser }) => {
  test.setTimeout(330000);
  const ready = JSON.parse(
    execFileSync(
      resolve(root, ".venv/bin/python"),
      [resolve(root, "tests/e2e/web/live_ready.py"), directory!],
      {
        cwd: root,
        env: { ...process.env, PYTHONPATH: root },
        encoding: "utf8",
      },
    ),
  );
  if (Date.now() + ready.wait_ms >= Date.parse(windowInfo.stop_at_utc))
    throw new Error("Owned window insufficient for natural login rate wait");
  if (ready.wait_ms)
    await new Promise((resolve) => setTimeout(resolve, ready.wait_ms));
  for (const role of ["operator", "approver", "admin", "late_approver"]) {
    const context = await browser.newContext();
    contexts.set(role, context);
    const page = await context.newPage();
    await page.goto(windowInfo.web_origin + "/login");
    await page
      .locator("#live-login")
      .evaluate(
        (el, value) => ((el as HTMLInputElement).value = value),
        accounts[role].login,
      );
    await page
      .locator("#live-password")
      .evaluate(
        (el, value) => ((el as HTMLInputElement).value = value),
        accounts[role].password,
      );
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await expect(
      page.locator('[data-source-mode="live-session"]'),
    ).toBeVisible();
    await page.goto("about:blank");
    await page.close();
  }
});
test.afterAll(async () => {
  for (const context of contexts.values()) await context.close();
});
async function withPage(role: string, work: (page: Page) => Promise<void>) {
  const page = await contexts.get(role)!.newPage();
  try {
    await work(page);
  } finally {
    await page.goto("about:blank");
    await page.close();
  }
}
test("真实永久执行与item状态/sync独立，20项分页与末项详情", async () => {
  await withPage("approver", async (page) => {
    await page.goto(windowInfo.web_origin + "/tasks/" + facts.completed_task);
    await expect(page.getByRole("main")).toContainText("Worker 执行回执");
    await expect(page.getByRole("main")).toContainText(
      "不推断这些工作项已跟进完成",
    );
    await page.goto(windowInfo.web_origin + "/replenishment-items");
    await expect(page.locator(".list-row")).toHaveCount(20);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page
      .locator(".list-row")
      .last()
      .getByRole("link", { name: "查看工作项" })
      .click();
    await expect(page.getByRole("main")).toContainText("读取时内部项事实");
  });
});
test("真实T6 Unicode原因/原键回放：一次版本推进与原receipt，终态无重开", async () => {
  await withPage("approver", async (page) => {
    await page.goto(
      windowInfo.web_origin + "/replenishment-items/" + facts.resolve_item,
    );
    await page.locator('[data-control="B26"]').focus();
    await page.keyboard.press("Enter");
    await page
      .locator("#resolve-reason")
      .fill("\u001f内部跟进 e\u0301\ufeff\u0085");
    await page.getByRole("button", { name: "确认原因并准备原请求" }).click();
    await expect(
      page.locator('[data-action="resolve-original"]'),
    ).toBeFocused();
    await page.keyboard.press("Space");
    await expect(
      page.getByText("内部跟进已记录", { exact: true }),
    ).toBeVisible();
    for (let n = 0; n < 9; n++) {
      await page.locator('[data-action="resolve-original"]').click();
      await expect(
        page.locator('[data-action="resolve-original"]'),
      ).toBeEnabled();
    }
    await page.locator('[data-action="resolve-receipt"]').click();
    await expect(page.getByRole("dialog")).toContainText("v2");
    await page.keyboard.press("Escape");
    await expect(page.getByText("终态只读", { exact: true })).toBeVisible();
    await expect(page.locator('[data-control="B26"]')).toHaveCount(0);
    await page.reload();
    await expect(page.locator('[data-control="B27"]')).toHaveCount(0);
  });
});
test("真实迟来同店approver可处理而来源隐藏；operator/admin不借审批/业务权", async () => {
  await withPage("late_approver", async (page) => {
    await page.goto(
      windowInfo.web_origin +
        "/replenishment-items/" +
        facts.hidden_source_item,
    );
    await expect(page.locator('[data-control="B37"]')).toHaveCount(0);
    await expect(page.locator('[data-control="B27"]')).toBeEnabled();
    await page.locator('[data-control="B27"]').click();
    await page
      .locator("#resolve-reason")
      .fill("仅内部关闭，来源按当前查看权受限");
    await page.getByRole("button", { name: "确认原因并准备原请求" }).click();
    await page.locator('[data-action="resolve-original"]').click();
    await expect(
      page.getByText("内部跟进已记录", { exact: true }),
    ).toBeVisible();
  });
  await withPage("operator", async (page) => {
    await page.goto(
      windowInfo.web_origin + "/replenishment-items/" + facts.operator_item,
    );
    await expect(page.locator('[data-control="B26"]')).toHaveCount(0);
  });
  await withPage("admin", async (page) => {
    await page.goto(windowInfo.web_origin + "/replenishment-items");
    await expect(page).toHaveURL(/\/access$/);
    await expect(page.locator(".list-row")).toHaveCount(0);
  });
});
// Concurrent decisions/resolutions, controlled ACK loss/revocation, new-cycle and
// native200 probes will be bound to fresh recorded resources at window dispatch.
// Their real execution and PG counts remain not_run at this code-only freeze.
