import {
  ownedEndpoints,
  assertOwnedListener,
  assertOwnedBuild,
  readOwnedListener,
} from "../owned-listeners";
import { test, expect } from "../../../../frontend/tooling/web-test";
import { readFileSync, statSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import type { Page } from "../../../../frontend/tooling/web-test";
import { verifyReadResponse } from "../../../../frontend/lib/p3-live-client";
import { explanationBound } from "../../../../frontend/lib/p3-present";
import type { DTO } from "../../../../frontend/lib/p3-present";
const directory = process.env.COMMERCEOPS_B02_PRIVATE_DIR!;
const privateRead = (name: string) => {
  const path = resolve(directory, name);
  if ((statSync(path).mode & 0o777) !== 0o600)
    throw new Error("Private test input permission invalid");
  return JSON.parse(readFileSync(path, "utf8"));
};
const windowInfo = privateRead("window.json");
const accounts = privateRead("web-accounts.json");
const facts = privateRead("web-facts.json");
const root = resolve(__dirname, "../../../..");
const listeners = ownedEndpoints(
  windowInfo,
  process.env.COMMERCEOPS_LIVE_WEB_URL,
);
assertOwnedBuild(
  windowInfo.build_id,
  readFileSync(resolve(root, "frontend/.next/BUILD_ID"), "utf8"),
);
const API = windowInfo.api_origin;
if (
  Date.now() >= Date.parse(windowInfo.stop_at_utc) ||
  windowInfo.web_origin !== process.env.COMMERCEOPS_LIVE_WEB_URL
)
  throw new Error("Owned window mismatch/expired");
for (const { port, pid } of listeners) {
  const listening = readOwnedListener(port);
  assertOwnedListener(listening, pid);
}
test.beforeAll(async () => {
  test.setTimeout(330000);
  const readiness = JSON.parse(
    execFileSync(
      resolve(root, ".venv/bin/python"),
      [resolve(root, "tests/e2e/web/live_ready.py"), directory],
      {
        cwd: root,
        env: { ...process.env, PYTHONPATH: `${resolve(root, "backend/src")}:${root}` },
        stdio: ["ignore", "pipe", "ignore"],
      },
    ).toString(),
  );
  if (
    readiness.wait_ms > 300001 ||
    Date.now() + readiness.wait_ms >= Date.parse(windowInfo.stop_at_utc)
  )
    throw new Error("Owned login window unavailable within deadline");
  if (readiness.wait_ms > 0)
    await new Promise((resolve) => setTimeout(resolve, readiness.wait_ms));
});
// Playwright error-context DOM capture occurs at context close after afterEach.
// Only an empty owned page may reach that capture; explicit safe PNGs are saved earlier.
test.afterEach(async ({ page }) => {
  await page.goto("about:blank").catch(() => {});
});
async function login(page: Page, role: string) {
  await page.goto("/login");
  await expect(
    page.getByRole("button", { name: "登录", exact: true }),
  ).toBeVisible();
  // No fill(secret) call log, raw trace, HAR or password screenshot.
  try {
    await page
      .locator("#live-login")
      .evaluate(
        (element, value) => ((element as HTMLInputElement).value = value),
        accounts[role].login,
      );
    await page
      .locator("#live-password")
      .evaluate(
        (element, value) => ((element as HTMLInputElement).value = value),
        accounts[role].password,
      );
    await page.getByRole("button", { name: "登录", exact: true }).click();
  } finally {
    await page
      .locator("#live-password")
      .evaluateAll((elements) =>
        elements.forEach((el) => ((el as HTMLInputElement).value = "")),
      );
  }
  await expect(page.locator('[data-source-mode="live-session"]')).toBeVisible();
}
const apiWrites = (page: Page) => {
  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.url().startsWith(API) && request.method() === "POST")
      writes.push(new URL(request.url()).pathname);
  });
  return writes;
};
async function safeScreenshot(page: Page, name: string) {
  await page.evaluate(() => document.fonts.ready);
  expect(await page.locator('input[type="password"]').count()).toBe(0);
  await page.screenshot({
    path: resolve(root, `frontend/evidence/b04-live/read/${name}.png`),
    fullPage: true,
  });
}
async function readStatus(page: Page, path: string) {
  return page.evaluate(
    async ({ api, path }) => {
      const result = await fetch(api + path, {
        credentials: "include",
        cache: "no-store",
      });
      const body = await result.json();
      return {
        status: result.status,
        code: body.error?.code ?? null,
        keys: Object.keys(body).sort(),
      };
    },
    { api: API, path },
  );
}
async function originalTemplate(page: Page) {
  const path = `/api/v1/tasks/${facts.task}/explanation`;
  const response = page.waitForResponse((r) =>
    r.url() === `${API}${path}?report_id=${facts.report}` && r.request().method() === "GET",
  );
  const trigger = page.locator('[data-control="B19"]');
  await trigger.focus();
  await page.keyboard.press("Enter");
  const actual = await response;
  expect(actual.status()).toBe(200);
  const value = await actual.json() as DTO["ExplanationRead"];
  expect(verifyReadResponse("GET", path, 200, value)).toBe(true);
  expect(value).toMatchObject({
    task_id: facts.task, report_id: facts.report,
    explanation: {
      schema_version: "p4-p3-template-read-v1", task_id: facts.task,
      source_task_id: facts.source_task, source_kind: "p2_original",
      observation_id: null, report_id: facts.report, snapshot_id: facts.snapshot,
      facts_hash: facts.facts_hash, analysis_only: true, execution_available: false,
      result: { narrative_mode: "template", metadata: { evidence_mode: "not_used" } },
    },
  });
  expect(value.explanation).not.toHaveProperty("child_task_id");
  const metadata = value.explanation.result.metadata;
  for (const key of ["provider", "requested_model", "returned_model", "request_id", "usage",
    "latency_ms", "pricing_version", "cost_estimate"] as const) expect(metadata[key]).toBeNull();
  const reportResponse = await page.request.get(`${API}/api/v1/tasks/${facts.task}/report?report_id=${facts.report}`);
  expect(reportResponse.status()).toBe(200);
  const report = await reportResponse.json() as DTO["ReportRead"];
  expect(explanationBound(report, value)).toBe(true);
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("P3 模板");
  await expect(dialog).toContainText("P2 原始报告");
  await expect(dialog).toContainText("observation：无重观测");
  await expect(dialog).toContainText("input_tokens：未报告");
  await expect(dialog).not.toContainText("子 task：");
  await expect(dialog.locator("article.list-row")).toHaveCount(20);
  for (const ref of [facts.task, facts.source_task, facts.report, facts.snapshot, facts.facts_hash])
    await expect(dialog).toContainText(ref);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
}

test("operator真实登录、22记录分页、报告刷新/20SKU/null与实际配置", async ({
  page,
}) => {
  const writes = apiWrites(page);
  await login(page, "operator");
  await expect(
    page.getByRole("heading", { name: "任务中心", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".metric").first()).toHaveText("22");
  await expect(page.locator(".list-row")).toHaveCount(20);
  await page.getByRole("button", { name: "下一页", exact: true }).click();
  await expect(page.locator(".list-row")).toHaveCount(2);
  await page.getByRole("button", { name: "上一页", exact: true }).click();
  await expect(page.locator(".list-row")).toHaveCount(20);
  await page.goto(`/tasks/${facts.task}`);
  await expect(page.locator("[data-task-id]")).toHaveText(facts.task);
  await expect(page.getByText("协作同步：")).toContainText("等待");
  await page.getByRole("link", { name: "读取冻结报告", exact: true }).click();
  await expect(
    page.getByRole("table", { name: "SKU 分析" }).getByRole("row"),
  ).toHaveCount(21);
  await expect(page.getByRole("main")).toContainText("null（未知）");
  await expect(page.getByRole("main")).toContainText("1800秒");
  await expect(page.getByRole("main")).toContainText("450秒");
  await expect(page.getByRole("main")).toContainText(facts.report); // Version list/source modal carry fixed binding.
  await page.getByRole("button", { name: "数据口径", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(facts.report);
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "数据口径", exact: true }),
  ).toBeFocused();
  await page
    .getByRole("button", { name: "刷新会话与当前页", exact: true })
    .click();
  await expect(
    page.getByRole("table", { name: "SKU 分析" }).getByRole("row"),
  ).toHaveCount(21);
  await safeScreenshot(page, "report-1440");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("table", { name: "SKU 分析" }).getByRole("row"),
  ).toHaveCount(20);
  await safeScreenshot(page, "report-390");
  await originalTemplate(page);
  expect(writes).toEqual(["/api/v1/auth/login"]);
});

test("approver完整计划无默认确认、指定版本只读、缺缓存解释、events无虚构恢复", async ({
  page,
}) => {
  const writes = apiWrites(page);
  await login(page, "approver");
  await page.goto("/approvals");
  await expect(page.locator(".list-row")).toHaveCount(11);
  await page.goto(`/approvals/${facts.approval}`);
  await expect(
    page.getByRole("table", { name: "完整审批清单" }).getByRole("row"),
  ).toHaveCount(21);
  await expect(page.getByRole("main")).toContainText("实际渲染 20 项");
  await expect(page.getByRole("main")).toContainText("null（未知）");
  for (const id of ["B02", "B04"])
    await expect(page.locator(`[data-control="${id}"]`)).toBeDisabled();
  for (const id of ["B03", "B05"])
    await expect(page.locator(`[data-control="${id}"]`)).toBeEnabled();
  expect(await page.locator('input[type="checkbox"]:checked').count()).toBe(0);
  await page.getByRole("link", { name: "读取指定冻结版本" }).click();
  await expect(page.getByRole("main")).toContainText("指定冻结版本 · 只读");
  await expect(
    page.getByRole("table", { name: "完整审批清单" }).getByRole("row"),
  ).toHaveCount(21);
  await page.goto(`/tasks/${facts.task}/report?report_id=${facts.report}`);
  await originalTemplate(page);
  await page.goto(`/tasks/${facts.task}/events`);
  await expect(page.locator(".timeline li")).not.toHaveCount(0);
  await expect(page.locator('[data-control="B32"]')).toBeDisabled();
  expect(writes).toEqual(["/api/v1/auth/login"]);
});

test("admin-only安全落点，无业务导航/编号/计数与强制深链", async ({ page }) => {
  const business: string[] = [];
  page.on("request", (r) => {
    if (
      r.url().startsWith(API + "/api/v1/tasks") ||
      r.url().startsWith(API + "/api/v1/approvals")
    )
      business.push(new URL(r.url()).pathname);
  });
  await login(page, "admin");
  await expect(
    page.getByRole("heading", { name: "管理配置与异常说明" }),
  ).toBeVisible();
  await expect(page.getByRole("main")).toContainText("1800秒");
  await expect(page.getByRole("main")).toContainText("结果未知");
  await expect(page.locator('[data-control="B39"]')).toHaveCount(0);
  await expect(page.locator('[data-control="B40"]')).toHaveCount(0);
  await safeScreenshot(page, "admin-1440");
  await page.goto(`/tasks/${facts.task}`);
  await expect(page).toHaveURL(/\/access$/);
  await expect(page.locator("body")).not.toContainText(facts.task);
  await expect(page.locator("body")).not.toContainText(facts.shop_a);
  expect(business).toEqual([]);
});

test("另一operator同店非本人404与不存在一致，URL actor/role无授权", async ({
  page,
}) => {
  await login(page, "foreign");
  await expect(page.getByRole("main")).toContainText(
    "当前授权与筛选下暂无任务",
  );
  const hidden = await readStatus(page, `/api/v1/tasks/${facts.task}`);
  const missing = await readStatus(
    page,
    "/api/v1/tasks/00000000-0000-4000-8000-000000000003",
  );
  expect(hidden).toEqual(missing);
  expect(hidden.status).toBe(404);
  await page.goto(`/tasks/${facts.task}?actor=${facts.operator}&role=operator`);
  await expect(page).toHaveURL(/\/access$/);
  await expect(page.locator("body")).not.toContainText(facts.task);
});

test("跨店兼任范围逐角色绑定，不拼operator-A/approver-B", async ({ page }) => {
  await login(page, "dual");
  await page.locator('[data-control="B44"]').click();
  await expect(page.getByRole("dialog")).toContainText(
    `operator → 店铺 ${facts.shop_a}`,
  );
  await expect(page.getByRole("dialog")).toContainText(
    `approver → 店铺 ${facts.shop_b}`,
  );
  await page.keyboard.press("Escape");
  const read = await readStatus(page, `/api/v1/approvals/${facts.approval}`);
  expect(read.status).toBe(404);
  await page.goto("/approvals");
  await expect(page.getByRole("main")).toContainText(
    "当前授权与筛选下暂无审批",
  );
});

test("原request_key只读回执、缺CSRF拒绝、真实logout清Cookie", async ({
  page,
}) => {
  const writes = apiWrites(page);
  await login(page, "operator");
  await page.goto(`/requests/${facts.request}?operation=create_task`);
  await expect(page.getByRole("main")).toContainText("原请求持久回执");
  await expect(page.getByRole("main")).toContainText(facts.request);
  const denied = await page.evaluate(async (api) => {
    const response = await fetch(api + "/api/v1/auth/logout", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ schema_version: "p3-web-v1" }),
    });
    return response.status;
  }, API);
  expect(denied).toBe(403);
  await page.locator('[data-control="B44"]').click();
  await page.locator('[data-control="B12"]').click();
  await expect(
    page.getByRole("button", { name: "登录", exact: true }),
  ).toBeVisible();
  const result = await readStatus(page, "/api/v1/auth/session");
  expect(result.status).toBe(401);
  await page.goto("/tasks");
  await expect(
    page.getByRole("button", { name: "登录", exact: true }),
  ).toBeVisible();
  await expect(page.locator("body")).not.toContainText(facts.task);
  expect(writes).toEqual([
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/logout",
  ]);
});

test("当前scope撤销真实401，刷新后清业务缓存/身份且无Mock回退", async ({
  page,
}) => {
  await login(page, "operator");
  await page.goto(`/tasks/${facts.task}`);
  await expect(page.locator("[data-task-id]")).toHaveText(facts.task);
  execFileSync(
    resolve(root, ".venv/bin/python"),
    [resolve(root, "tests/e2e/web/live_revoke.py"), directory, facts.operator],
    {
      cwd: root,
      env: { ...process.env, PYTHONPATH: `${resolve(root, "backend/src")}:${root}` },
      stdio: ["ignore", "pipe", "ignore"],
    },
  );
  await page.getByRole("button", { name: "刷新会话与当前页" }).click();
  await expect(
    page.getByRole("button", { name: "登录", exact: true }),
  ).toBeVisible();
  await expect(page.locator("body")).not.toContainText(facts.task);
  await expect(page.locator("body")).not.toContainText(facts.report);
  await expect(page.locator("[data-mock-source]")).toHaveCount(0);
  const result = await readStatus(page, "/api/v1/auth/session");
  expect(result.status).toBe(401);
});
