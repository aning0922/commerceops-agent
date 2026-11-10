// UI_FIXTURE only: Chromium engine page zoom via chrome.tabs, in a disposable profile.
import { chromium } from "@playwright/test";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { resolve, join } from "node:path";
import completed from "./daily-read.fixture.json" with { type: "json" };

const origin = process.env.COMMERCEOPS_M3_UI_FIXTURE_URL;
if (!origin || !/^http:\/\/127\.0\.0\.1:[0-9]+$/.test(origin)) throw new Error("Owned loopback fixture origin required");
const root = resolve("runtime");
await mkdir(root, { recursive: true });
const owned = await mkdtemp(join(root, "m3-page-zoom-"));
const extension = join(owned, "extension");
const profile = join(owned, "profile");
const screenshots = resolve("runtime", "m3-actual-browser-page-zoom-ui-fixture");
await mkdir(extension);
await mkdir(screenshots, { recursive: true });
await writeFile(join(extension, "manifest.json"), JSON.stringify({
  manifest_version: 3, name: "M3 owned page zoom probe", version: "0.0.1",
  permissions: ["tabs"], host_permissions: [`${origin}/*`],
  background: { service_worker: "worker.js" },
}));
await writeFile(join(extension, "worker.js"), "chrome.runtime.onInstalled.addListener(() => {});\n");
const id = completed.daily.task_id;
const sender = { destination_alias: "IM", sender_enabled: false, reason_code: "NOT_CONFIGURED", verification_mode: null,
  as_of: "2026-11-03T04:02:00Z", worker_ready: null };
const session = {
  schema_version: "p3-web-v1", identity_mode: "session", server_time: "2026-11-03T04:02:00Z",
  trace_id: "00000000-0000-4000-8000-000000000099", csrf_token: "c".repeat(43),
  principal: { principal_id: "00000000-0000-4000-8000-000000000105",
    organization_id: "00000000-0000-4000-8000-000000000109", display_name: "测试运营员", auth_version: 1,
    linked_channels: ["web"], role_shop_grants: [{ role: "operator", shop_id: completed.daily.shop_id }],
    capabilities: { can_create_task: false, can_read_tasks: true, can_read_approvals: false,
      can_resolve_items: false, can_read_operations: false, home_path: "/tasks" } },
  absolute_expires_at: "2026-11-04T04:02:00Z", idle_expires_at: "2026-11-03T04:32:00Z",
  config: { config_version: "ui-fixture-v1", shop_timezone: "Asia/Taipei", approval_ttl_seconds: 1800,
    revalidation_max_age_seconds: 450, max_plan_items: 20, recovery_scan_seconds: 10,
    session_absolute_seconds: 28800, session_idle_seconds: 1800, transport_mode: "local_http",
    source_mode: "mock", model_requests_enabled: false, external_sender_enabled: false,
    sender_gates: [sender, { ...sender, destination_alias: "Base" }] },
};
const json = (body) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
let context;
const results = [];
try {
  context = await chromium.launchPersistentContext(profile, {
    channel: "chromium", headless: true, viewport: { width: 1440, height: 1000 },
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
  });
  let worker = context.serviceWorkers()[0];
  if (!worker) worker = await context.waitForEvent("serviceworker", { timeout: 10000 });
  const page = await context.newPage();
  await page.route("**/api/v1/**", route => route.abort());
  await page.route("**/api/v1/auth/session", route => route.fulfill(json(session)));
  await page.route("**/api/v1/daily-reports/*", route => route.fulfill(json(completed)));
  await page.goto(`${origin}/daily-reports/${id}`);
  await page.getByRole("heading", { name: "经营日报" }).waitFor();
  for (const width of [1440, 1280, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await worker.evaluate(async (url) => {
      const [tab] = await chrome.tabs.query({ url: `${url}/*` });
      if (!tab?.id) throw new Error("Owned report tab not found");
      await chrome.tabs.setZoom(tab.id, 1);
    }, origin);
    await page.waitForFunction(() => devicePixelRatio === 1, null, { timeout: 3000 });
    const before = await page.evaluate(() => ({ innerWidth, devicePixelRatio, scale: visualViewport?.scale }));
    const zoom = await worker.evaluate(async (url) => {
      const [tab] = await chrome.tabs.query({ url: `${url}/*` });
      if (!tab?.id) throw new Error("Owned report tab not found");
      await chrome.tabs.setZoomSettings(tab.id, { mode: "automatic", scope: "per-tab" });
      await chrome.tabs.setZoom(tab.id, 2);
      return { value: await chrome.tabs.getZoom(tab.id), settings: await chrome.tabs.getZoomSettings(tab.id) };
    }, origin);
    await page.waitForFunction(() => devicePixelRatio === 2, null, { timeout: 3000 });
    const after = await page.evaluate(() => ({ innerWidth, devicePixelRatio, scale: visualViewport?.scale,
      documentWidth: document.documentElement.scrollWidth,
      clippedControls: [...document.querySelectorAll(".app-shell button, .app-shell h1, .app-shell h2, .app-shell .brand")]
        .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && (r.right > innerWidth + 1 || r.left < -1); })
        .map(el => ({ tag: el.tagName, text: el.textContent?.trim().slice(0, 50) })),
      clippedElements: [...document.querySelectorAll(".app-shell *")]
        .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && (r.right > innerWidth + 1 || r.left < -1); })
        .slice(0, 12).map(el => ({ tag: el.tagName, text: el.textContent?.trim().slice(0, 32) })),
    }));
    if (zoom.value !== 2 || after.innerWidth >= before.innerWidth || after.devicePixelRatio <= before.devicePixelRatio ||
        after.documentWidth > after.innerWidth || after.clippedElements.length) throw new Error(`Engine zoom/reflow mismatch at ${width}: ${JSON.stringify({ before, zoom, after })}`);
    await page.getByRole("button", { name: "查看来源与证据引用" }).click();
    const dialog = page.getByRole("dialog", { name: "来源与证据引用" });
    if (!await dialog.isVisible() || !await dialog.evaluate(el => el.scrollWidth <= el.clientWidth))
      throw new Error(`Drawer overflow at ${width}`);
    await dialog.getByRole("button", { name: "关闭来源与证据引用" }).focus();
    await page.keyboard.press("Shift+Tab");
    if (!await dialog.getByText("报告绑定与版本").evaluate(el => el === document.activeElement))
      throw new Error(`Drawer reverse focus trap failed at ${width}`);
    await page.keyboard.press("Tab");
    if (!await dialog.getByRole("button", { name: "关闭来源与证据引用" }).evaluate(el => el === document.activeElement))
      throw new Error(`Drawer forward focus trap failed at ${width}`);
    await page.keyboard.press("Escape");
    if (!await page.getByRole("button", { name: "查看来源与证据引用" }).evaluate(el => el === document.activeElement))
      throw new Error(`Drawer return focus failed at ${width}`);
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({ path: join(screenshots, `ui-fixture-tabs-api-zoom200-${width}.png`), fullPage: true, scale: "device" });
    const cdp = await context.newCDPSession(page);
    const captured = await cdp.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    await writeFile(join(screenshots, `ui-fixture-tabs-api-zoom200-${width}-viewport.png`), Buffer.from(captured.data, "base64"));
    results.push({ width, before, zoom, after, screenshot: `ui-fixture-tabs-api-zoom200-${width}.png`,
      viewportScreenshot: `ui-fixture-tabs-api-zoom200-${width}-viewport.png` });
  }
  const receipt = { kind: "UI_FIXTURE", method: "actual_browser_page_zoom_via_tabs_api", source: process.env.COMMERCEOPS_M3_SOURCE_SHA,
    chromium: context.browser()?.version(), origin, results };
  await writeFile(join(screenshots, "receipt.json"), JSON.stringify(receipt, null, 2) + "\n");
  console.log(JSON.stringify(receipt));
} finally {
  await context?.close();
  await rm(owned, { recursive: true, force: true });
}
