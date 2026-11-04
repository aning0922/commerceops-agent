// Only a Root-registered owned window with synthetic data; no mock route fulfillment.
import { test, expect } from "@playwright/test";
import { readFileSync, statSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { assertOwnedBuild, assertOwnedListener, ownedEndpoints, readOwnedListener } from "../../tests/e2e/web/owned-listeners";
import { validDailyRead } from "../lib/m3-read-client";
import { allowedOwnedRequest } from "./network-guard";

const root = resolve(import.meta.dirname, "../..");
const directory = resolve(process.env.COMMERCEOPS_M3_PRIVATE_DIR!);
function privateRead(name: string) {
  const path = resolve(directory, name);
  if ((statSync(path).mode & 0o777) !== 0o600) throw new Error("Private input mode must be 0600");
  return JSON.parse(readFileSync(path, "utf8"));
}
const windowInfo = privateRead("window.json");
const account = privateRead("web-account.json");
const facts = privateRead("daily-facts.json");
const listeners = ownedEndpoints(windowInfo, process.env.COMMERCEOPS_M3_LIVE_WEB_URL);
assertOwnedBuild(windowInfo.build_id, readFileSync(resolve(root, "frontend/.next/BUILD_ID"), "utf8"));
const head = execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
if (windowInfo.source_sha !== head || Date.now() >= Date.parse(windowInfo.stop_at_utc) ||
    !Number.isFinite(Date.parse(windowInfo.stop_at_utc))) throw new Error("Owned source/window mismatch");
for (const { port, pid } of listeners) assertOwnedListener(readOwnedListener(port), pid);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
if (![facts.task_id, facts.report_id, facts.snapshot_id].every((value: unknown) => typeof value === "string" && uuid.test(value)) ||
    typeof facts.facts_hash !== "string" || !/^[a-f0-9]{64}$/.test(facts.facts_hash) ||
    typeof account.login !== "string" || typeof account.password !== "string") throw new Error("Invalid owned test inputs");

test.afterEach(async ({ page }) => { await page.goto("about:blank").catch(() => {}); });
test("owned daily read: session, exact DTO binding and visible facts", async ({ page, context }) => {
  if (Date.now() + 45000 + 90000 >= Date.parse(windowInfo.stop_at_utc))
    throw new Error("Insufficient owned window for test and cleanup reserve");
  const api = windowInfo.api_origin as string;
  await context.routeWebSocket(/.*/, socket => socket.close());
  await context.route("**/*", async (route) => {
    const request = route.request();
    if (allowedOwnedRequest(request.url(), request.method(), windowInfo.web_origin, api, facts.task_id)) await route.continue();
    else await route.abort();
  });
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "登录", exact: true })).toBeVisible();
  try {
    await page.locator("#live-login").evaluate((el, value) => ((el as HTMLInputElement).value = value), account.login);
    await page.locator("#live-password").evaluate((el, value) => ((el as HTMLInputElement).value = value), account.password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
  } finally {
    await page.locator("#live-password").evaluateAll(els => els.forEach(el => ((el as HTMLInputElement).value = "")));
  }
  await expect(page.locator('[data-source-mode="live-session"]')).toBeVisible();
  const path = `/api/v1/daily-reports/${facts.task_id}`;
  const responsePromise = page.waitForResponse(response => response.url() === api + path && response.request().method() === "GET");
  await page.goto(`/daily-reports/${facts.task_id}`);
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const body: unknown = await response.json();
  expect(validDailyRead(body, facts.task_id)).toBe(true);
  if (!validDailyRead(body, facts.task_id) || body.daily.state !== "completed") throw new Error("Expected completed owned daily report");
  expect(body.daily.report).toMatchObject({ report_id: facts.report_id, snapshot_id: facts.snapshot_id, facts_hash: facts.facts_hash, complete: true });
  await expect(page.getByRole("heading", { name: "经营日报" })).toBeVisible();
  await expect(page.getByText("付款订单总额", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("当日退款额", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("付款订单数", { exact: true }).first()).toBeVisible();
});
