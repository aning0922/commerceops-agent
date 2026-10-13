import { test as base, expect } from "../../../../frontend/tooling/web-test";
import type { Page, BrowserContext } from "../../../../frontend/tooling/web-test";
import type { components } from "../../../../frontend/lib/p3-types.generated";
import { verifyReadResponse } from "../../../../frontend/lib/p3-live-client";
import { readFileSync, statSync, writeFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { ownedEndpoints, assertOwnedBuild, assertOwnedListener, readOwnedListener } from "../owned-listeners";
const root = resolve(__dirname, "../../../.."), dir = process.env.COMMERCEOPS_B02_PRIVATE_DIR!;
const read = (name: string) => {
  const path = resolve(dir, name);
  if ((statSync(path).mode & 0o777) !== 0o600) throw new Error("private C09 input required");
  return JSON.parse(readFileSync(path, "utf8"));
};
const owned = read("window.json"), accounts = read("web-accounts.json"), facts = read("web-facts.json");
const API: string = owned.api_origin, path = "/api/v1/tasks/preflight";
if (owned.owner !== "phase4-C09-Web" || Date.now() >= Date.parse(owned.stop_at_utc)) throw new Error("C09 owned deadline required");
for (const endpoint of ownedEndpoints(owned, process.env.COMMERCEOPS_LIVE_WEB_URL))
  assertOwnedListener(readOwnedListener(endpoint.port), endpoint.pid);
assertOwnedBuild(owned.build_id, readFileSync(resolve(root, "frontend/.next/BUILD_ID"), "utf8"));
type Role = "operator" | "admin";
type Session = components["schemas"]["SessionRead"];
type Browser = NonNullable<ReturnType<BrowserContext["browser"]>>;
type RoleState = {
  state: Awaited<ReturnType<BrowserContext["storageState"]>>;
  identity: string;
  organization: string;
  home: Session["principal"]["capabilities"]["home_path"];
};
// Only this worker's memory holds authentication state; never save or log it.
const roleStates = new Map<Role, RoleState>();
const test = base.extend({
  page: async ({ browser }, use) => {
    const context = await browser.newContext(contextOptions("operator"));
    let page: Page | undefined;
    try {
      page = await context.newPage();
      await use(page);
    } finally {
      try {
        if (page) {
          await page.goto("about:blank").catch(() => {});
          await page.close();
        }
      } finally { await context.close(); }
    }
  },
});
const contextOptions = (role: Role) => {
  const initial = roleStates.get(role);
  if (!initial) throw new Error("N01 authenticated role setup required");
  return { baseURL: owned.web_origin as string, viewport: { width: 1440, height: 1000 }, storageState: initial.state };
};
async function currentSession(page: Page, role: Role): Promise<Session> {
  const stop = Date.parse(owned.stop_at_utc);
  if (!Number.isFinite(stop) || Date.now() >= stop) throw new Error("N01 owned session window expired");
  const response = await page.evaluate(async (api) => {
    const result = await fetch(api + "/api/v1/auth/session", { credentials: "include", cache: "no-store" });
    return { status: result.status, value: await result.json() as unknown };
  }, API);
  if (Date.now() >= stop || response.status !== 200 || !verifyReadResponse("GET", "/api/v1/auth/session", response.status, response.value))
    throw new Error("N01 current session response rejected");
  const session = response.value as Session;
  const principal = session.principal;
  const server = Date.parse(session.server_time);
  const expires = [session.absolute_expires_at, session.idle_expires_at].map(Date.parse);
  const grants = principal.role_shop_grants;
  const expectedShops = [facts.shop, facts.shop_b].sort();
  const operatorShops = grants.filter((grant) => grant.role === "operator").map((grant) => grant.shop_id).sort();
  if (!Number.isFinite(server) || server >= stop || expires.some((value) => !Number.isFinite(value) || value <= server) ||
      principal.principal_id !== accounts[role].principal || !principal.linked_channels.includes("web") ||
      (role === "operator" && (!principal.capabilities.can_create_task || grants.length !== 2 || JSON.stringify(operatorShops) !== JSON.stringify(expectedShops))) ||
      (role === "admin" && (principal.capabilities.can_create_task || principal.capabilities.can_read_tasks || grants.length !== 0)) ||
      [...roleStates.values()].some((initial) => initial.organization !== principal.organization_id))
    throw new Error("N01 current role or store scope rejected");
  return session;
}
function sessionIdentity(session: Session): string {
  const p = session.principal;
  return JSON.stringify({
    principal: p.principal_id, organization: p.organization_id, auth_version: p.auth_version,
    grants: [...p.role_shop_grants].sort((a, b) => `${a.role}:${a.shop_id}`.localeCompare(`${b.role}:${b.shop_id}`)),
    capabilities: p.capabilities, linked_channels: [...p.linked_channels].sort(),
  });
}
async function initializeRole(browser: Browser, role: Role) {
  if (roleStates.has(role)) throw new Error("N01 role already authenticated");
  const context = await browser.newContext({ baseURL: owned.web_origin, viewport: { width: 1440, height: 1000 } });
  try {
    const page = await context.newPage();
    await initialLogin(page, role);
    await page.waitForURL((url) => url.origin === owned.web_origin && url.pathname !== "/login");
    const session = await currentSession(page, role);
    roleStates.set(role, { state: await context.storageState(), identity: sessionIdentity(session), organization: session.principal.organization_id, home: session.principal.capabilities.home_path });
  } finally { await context.close(); }
}
type Snapshot = Record<string, { count: number; sha256: string }>;
const probe = (action: "snapshot" | "revoke"): Snapshot => {
  const output = execFileSync(resolve(root, ".venv/bin/python"), [resolve(root, "tests/e2e/web/c09_fixture.py"), dir, action], {
    cwd: root, env: { ...process.env, PYTHONPATH: `${root}/backend/src:${root}` }, stdio: ["ignore", "pipe", "ignore"], timeout: 15000,
  }).toString();
  return action === "snapshot" ? JSON.parse(output) : {};
};
let before: Snapshot;
const evidence: { test: string; business_unchanged: boolean; explicit_pair_only: boolean }[] = [];
test.beforeAll(async ({ browser }) => {
  await initializeRole(browser, "operator");
  await initializeRole(browser, "admin");
});
test.beforeEach(async ({ page }) => { before = probe("snapshot"); await login(page); });
test.afterEach(async ({ page }, info) => {
  try {
    const after = probe("snapshot");
    const positive = info.title.includes("显式唯一创建");
    const unchanged = JSON.stringify(after) === JSON.stringify(before);
    const pairOnly = positive && [
      ["business.business_tasks", 2], ["business.jobs", 2], ["business.web_requests", 1],
      ["business.approvals", 0], ["business.executions", 0], ["business.replenishment_items", 0],
      ["business.outbox", 0], ["business.p4_sdk_calls", 0], ["business.model_calls", 0],
    ].every(([key, delta]) => after[String(key)].count === before[String(key)].count + Number(delta));
    evidence.push({ test: info.title, business_unchanged: unchanged, explicit_pair_only: pairOnly });
    expect(positive ? pairOnly : unchanged).toBe(true);
  } finally { await page.goto("about:blank").catch(() => {}); }
});
test.afterAll(() => {
  roleStates.clear();
  const destination = resolve(root, "frontend/evidence/p4-c09/n01"); mkdirSync(destination, { recursive: true });
  writeFileSync(resolve(destination, "pg-invariants.safe.json"), JSON.stringify({ source: "actual owned PostgreSQL", worker: "not_started", sdk_provider: "not_started", tests: evidence }, null, 2));
});
async function initialLogin(page: Page, role: Role) {
  await page.goto("/login");
  await expect(page.locator("#live-login")).toBeVisible();
  try {
    await page.locator("#live-login").evaluate((el, value) => { (el as HTMLInputElement).value = value; }, accounts[role].login);
    await page.locator("#live-password").evaluate((el, value) => { (el as HTMLInputElement).value = value; }, accounts[role].password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
  } finally {
    await page.locator("#live-password").evaluateAll((els) => els.forEach((el) => { (el as HTMLInputElement).value = ""; }));
  }
  await expect(page.locator('[data-source-mode="live-session"]')).toBeVisible();
}
async function login(page: Page, role: Role = "operator") {
  const initial = roleStates.get(role);
  if (!initial) throw new Error("N01 authenticated role unavailable");
  await page.goto(initial.home);
  const current = await currentSession(page, role);
  if (sessionIdentity(current) !== initial.identity)
    throw new Error("N01 original session identity changed");
  await expect(page.locator('[data-source-mode="live-session"]')).toBeVisible();
}
async function draft(page: Page, text: string) {
  await login(page);
  await page.locator('[data-control="B10"]').click();
  await page.getByLabel("当前operator店铺").selectOption(facts.shop);
  await page.getByRole("button", { name: "使用自然语言请求草稿", exact: true }).click();
  await page.getByLabel("自然语言请求草稿").fill(text);
}
async function parse(page: Page) {
  await page.getByRole("button", { name: "检查草稿与参数", exact: true }).click();
  await expect(page.getByRole("heading", { name: "草稿参数与来源", exact: true })).toBeVisible();
}
function creates(page: Page) {
  const posts: string[] = [];
  page.on("request", (req) => { if (req.url() === API + "/api/v1/tasks" && req.method() === "POST") posts.push(req.postData()!); });
  return posts;
}
async function checkedPost(page: Page, payload: unknown, csrf = true) {
  return page.evaluate(async ({ api, payload, csrf }) => {
    const session = await fetch(api + "/api/v1/auth/session", { credentials: "include", cache: "no-store" }).then((r) => r.json());
    const result = await fetch(api + "/api/v1/tasks/preflight", {
      method: "POST", credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json", ...(csrf ? { "X-CSRF-Token": session.csrf_token } : {}) }, body: JSON.stringify(payload),
    });
    const value = await result.json(); return { status: result.status, code: value.error?.code ?? null };
  }, { api: API, payload, csrf });
}
test("N01 actual ready来源/冻结window/390键盘；解析取消零业务增量", async ({ page }) => {
  const posts = creates(page);
  await draft(page, "请分析库存 全店 最近七个完整自然日 L=3天 R=7天 S=2天。");
  await parse(page);
  await expect(page.getByRole("dialog")).toContainText("模型未使用");
  await expect(page.getByRole("dialog")).toContainText("R 是复查周期");
  await expect(page.getByLabel("L（0–365整数）", { exact: true })).toHaveValue("3");
  await expect(page.locator('dialog [data-control="B01"]')).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator('[data-control="B35"]').focus(); await page.keyboard.press("Enter");
  await expect(page.locator('dialog [data-control="B01"]')).toBeEnabled();
  await page.keyboard.press("Escape"); await page.locator('[data-control="B45"]').click();
  await expect(page.getByRole("dialog")).toHaveCount(0); expect(posts).toEqual([]);
});
test("N01 两原PRD句/MISSING人工缺项非demo，编辑撤确认，准备取消仍零增量", async ({ page }) => {
  const posts = creates(page);
  await draft(page, "分析最近七天的商品销量和库存情况，找出可能缺货的商品，生成补货建议。");
  for (const text of [
    "分析最近七天的商品销量和库存情况，找出可能缺货的商品，生成补货建议。",
    "分析最近七天的销量和库存，找出缺货风险并生成补货建议",
    "分析库存 L=4",
  ]) {
    await page.getByLabel("自然语言请求草稿").fill(text); await parse(page);
    await expect(page.getByRole("dialog")).toContainText("请补齐明确参数后再确认");
    await expect(page.getByLabel("R（0–365整数）", { exact: true })).toHaveValue("");
    await expect(page.getByLabel("S（0–365整数）", { exact: true })).toHaveValue("");
    await expect(page.locator('[data-control="B35"]')).toBeDisabled();
  }
  await expect(page.getByLabel("L（0–365整数）", { exact: true })).toHaveValue("4");
  await expect(page.getByLabel("L（0–365整数）", { exact: true })).toBeDisabled();
  await page.getByLabel("R（0–365整数）", { exact: true }).fill("7");
  await page.getByLabel("S（0–365整数）", { exact: true }).fill("2");
  await page.locator('[data-control="B35"]').click();
  await page.getByLabel("R（0–365整数）", { exact: true }).fill("8");
  await expect(page.locator('dialog [data-control="B01"]')).toBeDisabled();
  await page.locator('[data-control="B35"]').click(); await page.locator('dialog [data-control="B01"]').click();
  await expect(page.locator('[data-action="send-original"]')).toBeVisible(); expect(posts).toEqual([]);
  await page.keyboard.press("Escape"); await page.locator('[data-control="B45"]').click();
});
test("N01 invalid/unsupported不静默ready；修原句或明确取消，CSRF/异店实际拒绝", async ({ page }) => {
  const posts = creates(page);
  await draft(page, "分析库存 L=3/4 R=7 S=2");
  for (const text of ["分析库存 L=3/4 R=7 S=2", "分析库存 L=3 R=7 S=2 再退款", "只分析 SKU-A 最近三天 L=3 R=7 S=2"]) {
    await page.getByLabel("自然语言请求草稿").fill(text); await parse(page);
    await expect(page.locator('[data-control="B35"]')).toBeDisabled();
    await expect(page.locator('dialog [data-control="B01"]')).toBeDisabled();
  }
  const input = { schema_version: "p3-web-v1", shop_id: facts.shop, fixture_case: "baseline", text: "分析库存 L=3 R=7 S=2" };
  expect(await checkedPost(page, input, false)).toEqual({ status: 403, code: "CSRF_INVALID" });
  // 403 clears the transport on a product call; this direct negative probe has no product access.
  expect(await checkedPost(page, { ...input, shop_id: "00000000-0000-4000-8000-000000000099" })).toEqual({ status: 404, code: "RESOURCE_NOT_FOUND" });
  await page.getByRole("button", { name: "取消原句并改用结构化草稿", exact: true }).click();
  await expect(page.getByLabel("自然语言请求草稿")).toHaveCount(0);
  await expect(page.locator('[data-control="B35"]')).toBeDisabled(); expect(posts).toEqual([]);
});
test("N01 actual迟到解析不复活旧原句/店铺/fixture；参数编辑清候选及确认", async ({ page }) => {
  await draft(page, "分析库存 L=3 R=7 S=2");
  let release!: () => void, arrived!: () => void;
  const held = new Promise<void>((r) => { release = r; }), called = new Promise<void>((r) => { arrived = r; });
  let handler: Promise<void> | undefined;
  await page.route(API + path, (route) => {
    handler = (async () => {
      const response = await route.fetch();
      arrived();
      await held;
      await route.fulfill({ response });
    })();
    return handler;
  });
  try {
    await page.getByRole("button", { name: "检查草稿与参数", exact: true }).click(); await called;
    await page.getByLabel("自然语言请求草稿").fill("分析库存 L=4 R=7 S=2"); release();
    if (!handler) throw new Error("N01 held parse handler did not start");
    await handler;
    await page.unroute(API + path);
    await expect(page.getByRole("heading", { name: "草稿参数与来源", exact: true })).toHaveCount(0);
    await expect(page.locator('[data-control="B35"]')).toBeDisabled();
    await parse(page); await page.locator('[data-control="B35"]').click();
    await page.getByLabel("当前operator店铺").selectOption(facts.shop_b);
    await expect(page.locator('dialog [data-control="B01"]')).toBeDisabled();
    await page.getByLabel("当前operator店铺").selectOption(facts.shop); await parse(page);
    await page.getByLabel("Mock案例").selectOption("known_inbound");
    await expect(page.getByRole("heading", { name: "草稿参数与来源", exact: true })).toHaveCount(0);
    await page.getByLabel("Mock案例").selectOption("baseline"); await parse(page);
    await page.getByLabel("L（0–365整数）", { exact: true }).fill("5");
    await expect(page.locator('[data-control="B35"]')).toBeDisabled();
  } finally {
    release();
    try { if (handler) await handler; }
    finally { await page.unroute(API + path); }
  }
});
test("N01 显式唯一创建实际一pair，受控ACKunknown原键读取/同字节去重及真实409", async ({ page }) => {
  const posts = creates(page);
  await draft(page, "分析库存 L=3 R=7 S=2"); await parse(page);
  await page.locator('[data-control="B35"]').click(); await page.locator('dialog [data-control="B01"]').click();
  expect(posts).toHaveLength(0);
  await page.route(API + "/api/v1/tasks", async (route) => { await route.fetch(); await route.abort("failed"); }, { times: 1 });
  await page.locator('[data-action="send-original"]').click();
  await expect(page.getByText("提交结果待核实", { exact: true })).toBeVisible();
  await page.getByText("原请求技术详情与受控恢复", { exact: true }).click();
  await expect(page.locator('[data-action="send-original"]')).toBeDisabled();
  await page.locator('[data-action="read-original"]').click();
  await expect(page.getByRole("link", { name: "查看本次任务", exact: true })).toBeFocused();
  const committed = probe("snapshot");
  await page.locator('[data-action="send-original"]').click();
  await page.getByText("原创建回执技术详情", { exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("duplicate true");
  expect(posts).toHaveLength(2); expect(posts[0]).toBe(posts[1]);
  expect(probe("snapshot")).toEqual(committed);
  const wire = JSON.parse(posts[0]);
  const conflict = await page.evaluate(async ({ api, wire }) => {
    const session = await fetch(api + "/api/v1/auth/session", { credentials: "include" }).then((r) => r.json());
    const response = await fetch(api + "/api/v1/tasks", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token }, body: JSON.stringify({ ...wire, parameters: { ...wire.parameters, L: 4 } }) });
    const value = await response.json(); return { status: response.status, code: value.error?.code };
  }, { api: API, wire });
  expect(conflict).toEqual({ status: 409, code: "IDEMPOTENCY_CONFLICT" });
  expect(probe("snapshot")).toEqual(committed);
});
test("N01 actual无operator403；迟到响应遇真实撤权401清身份/草稿/业务缓存", async ({ page, browser }) => {
  const adminContext = await browser.newContext(contextOptions("admin"));
  try {
    const adminPage = await adminContext.newPage();
    await login(adminPage, "admin");
    await expect(adminPage.locator('[data-control="B10"]')).toHaveCount(0);
    expect(await checkedPost(adminPage, { schema_version: "p3-web-v1", shop_id: facts.shop, fixture_case: "baseline", text: "分析库存 L=3 R=7 S=2" })).toEqual({ status: 403, code: "ACCESS_DENIED" });
    await adminPage.goto("about:blank"); await adminContext.clearCookies();
  } finally { await adminContext.close(); }
  await draft(page, "分析库存 L=3 R=7 S=2");
  let release!: () => void, arrived!: () => void;
  const held = new Promise<void>((r) => { release = r; }), called = new Promise<void>((r) => { arrived = r; });
  let handler: Promise<void> | undefined;
  await page.route(API + path, (route) => {
    handler = (async () => {
      const response = await route.fetch();
      arrived();
      await held;
      await route.fulfill({ response });
    })();
    return handler;
  });
  try {
    await page.getByRole("button", { name: "检查草稿与参数", exact: true }).click(); await called;
    probe("revoke"); before = probe("snapshot");
    const response = await page.evaluate(async (api) => (await fetch(api + "/api/v1/auth/session", { credentials: "include", cache: "no-store" })).status, API);
    expect(response).toBe(401);
    await page.bringToFront();
    await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("visible");
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(page.getByRole("main")).toContainText(/会话已(?:失效|过期)或授权已变更，请重新登录。/);
    await expect(page.locator('[data-source-mode="live-session"]')).toHaveCount(0);
    await expect(page.locator("#live-login")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByLabel("自然语言请求草稿")).toHaveCount(0);
    await expect(page.locator(".list-row, .fact-row")).toHaveCount(0);
    release();
    if (!handler) throw new Error("N01 held revoked parse handler did not start");
    await handler;
    await page.unroute(API + path);
    await expect(page.getByRole("main")).toContainText(/会话已(?:失效|过期)或授权已变更，请重新登录。/);
    await expect(page.locator('[data-source-mode="live-session"]')).toHaveCount(0);
    await expect(page.locator("#live-login")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByLabel("自然语言请求草稿")).toHaveCount(0);
    await expect(page.locator(".list-row, .fact-row")).toHaveCount(0);
  } finally {
    release();
    try { if (handler) await handler; }
    finally { await page.unroute(API + path); }
  }
});
