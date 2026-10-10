// B04-only native zoom proof on the registered live API/Next window.
import { chromium } from "@playwright/test";
import {
  readFileSync,
  writeFileSync,
  mkdtempSync,
  mkdirSync,
  chmodSync,
  rmSync,
} from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve, join } from "node:path";
import { tmpdir } from "node:os";
import {
  ownedEndpoints,
  assertOwnedListener,
  assertOwnedBuild,
} from "../../tests/e2e/web/owned-listeners.ts";
const root = resolve(import.meta.dirname, "../..");
const directory = process.env.COMMERCEOPS_B02_PRIVATE_DIR;
if (!directory) throw new Error("Explicit owned B04 directory required");
const read = (name) => JSON.parse(readFileSync(join(directory, name), "utf8"));
const window = read("window.json"),
  accounts = read("web-accounts.json"),
  facts = read("b04-facts.json");
const verify = () => {
  const registeredOwner = window.owner_uid === undefined
    ? window.owner === "phase3-B-WTa266"
    : ["phase3-B-WTa266", "phase3-WebReviewer", "phase3-WebCI"].includes(window.owner)
      && window.owner_uid === process.getuid()
      && window.checkout === root
      && window.private_directory === resolve(directory);
  if (
    !registeredOwner ||
    !window.project.startsWith("p3b04-") ||
    Date.now() >= Date.parse(window.stop_at_utc)
  )
    throw new Error("Owned B04 window expired or mismatched");
  for (const e of ownedEndpoints(window, process.env.COMMERCEOPS_LIVE_WEB_URL))
    assertOwnedListener(
      execFileSync("lsof", ["-nP", `-iTCP:${e.port}`, "-sTCP:LISTEN", "-t"], {
        encoding: "utf8",
      }),
      e.pid,
    );
  assertOwnedBuild(
    window.build_id,
    readFileSync(join(root, "frontend/.next/BUILD_ID"), "utf8"),
  );
};
verify();
const scratch = mkdtempSync(join(tmpdir(), "commerceops-b04-zoom-"));
chmodSync(scratch, 0o700);
const extension = join(scratch, "extension");
mkdirSync(extension, { mode: 0o700 });
for (const [name, value] of [
  [
    "manifest.json",
    JSON.stringify({
      manifest_version: 3,
      name: "Owned B04 zoom proof",
      version: "1.0",
      background: { service_worker: "worker.js" },
    }),
  ],
  ["worker.js", "chrome.runtime.onInstalled.addListener(() => {});"],
])
  writeFileSync(join(extension, name), value, { mode: 0o600 });
let context;
let stage = "launch";
let before, after, actual;
try {
  context = await chromium.launchPersistentContext(join(scratch, "profile"), {
    headless: true,
    channel: "chromium",
    viewport: null,
    args: [
      `--disable-extensions-except=${extension}`,
      `--load-extension=${extension}`,
      "--window-size=1440,1100",
    ],
  });
  const worker =
    context.serviceWorkers()[0] ??
    (await context.waitForEvent("serviceworker"));
  stage = "create background tab";
  const opened = context.waitForEvent("page");
  const target = await worker.evaluate(async (url) => {
    const tab = await chrome.tabs.create({ url, active: false });
    return { id: tab.id };
  }, window.web_origin + "/login");
  const page = await opened;
  stage = "login";
  await page.locator("#live-login").waitFor();
  await page
    .locator("#live-login")
    .evaluate((el, value) => (el.value = value), accounts.operator.login);
  await page
    .locator("#live-password")
    .evaluate((el, value) => (el.value = value), accounts.operator.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.locator('[data-source-mode="live-session"]').waitFor();
  stage = "owned plan read";
  await page.goto(
    window.web_origin + "/tasks/" + facts.completed_task + "/plans/1",
  );
  await page
    .getByRole("table", { name: "完整审批清单" })
    .locator(".fact-row")
    .last()
    .waitFor();
  await page.evaluate(() => document.fonts.ready);
  if (
    (await page.locator(".fact-row").count()) !== 20 ||
    (await page.locator('input[type="password"]').count())
  )
    throw new Error("Complete safe live page required");
  const metrics = () =>
    page.evaluate(() => ({
      innerWidth,
      outerWidth,
      dpr: devicePixelRatio,
      visualScale: visualViewport.scale,
      scrollWidth: document.documentElement.scrollWidth,
      skuRows: document.querySelectorAll(".fact-row").length,
    }));
  before = await metrics();
  stage = "native zoom";
  await worker.evaluate(async (id) => {
    await chrome.tabs.setZoomSettings(id, {
      mode: "automatic",
      scope: "per-tab",
    });
    await chrome.tabs.setZoom(id, 2);
  }, target.id);
  await page.waitForFunction((dpr) => devicePixelRatio > dpr * 1.9, before.dpr);
  after = await metrics();
  actual = await worker.evaluate((id) => chrome.tabs.getZoom(id), target.id);
  if (
    actual !== 2 ||
    Math.abs(after.innerWidth / before.innerWidth - 0.5) > 0.02 ||
    after.visualScale !== 1 ||
    after.scrollWidth > after.innerWidth + 1 ||
    after.skuRows !== 20
  )
    throw new Error("Actual zoom/reflow proof failed");
  stage = "safe capture";
  const cdp = await context.newCDPSession(page);
  for (const [name, index] of [
    ["head", 0],
    ["tail", 19],
  ]) {
    await page.locator(".fact-row").nth(index).scrollIntoViewIfNeeded();
    const shot = await cdp.send("Page.captureScreenshot", {
      format: "png",
      fromSurface: true,
      captureBeyondViewport: false,
    });
    writeFileSync(
      join(root, "frontend/evidence/b04-live/actual-zoom-200-" + name + ".png"),
      Buffer.from(shot.data, "base64"),
    );
  }
  verify();
  const result = {
    time_utc: new Date().toISOString(),
    method:
      "temporary permission-free MV3 chrome.tabs.setZoom(2); headless Chromium on real session/API; no CSS or device emulation",
    user_profile_used: false,
    permissions: [],
    project: window.project,
    web_pid: window.web_pid,
    api_pid: window.api_pid,
    build_id: window.build_id,
    before,
    after,
    getZoom: actual,
    result: "passed",
  };
  writeFileSync(
    join(root, "frontend/evidence/b04-live/actual-zoom.json"),
    JSON.stringify(result, null, 2) + "\n",
  );
  console.log(JSON.stringify(result));
} catch (error) {
  const failure = {
    stage,
    category: error.name,
    result: "failed",
    before,
    after,
    getZoom: actual,
    user_profile_used: false,
    headless: true,
  };
  writeFileSync(
    join(root, "frontend/evidence/b04-live/zoom-background-diagnostic.json"),
    JSON.stringify(failure, null, 2) + "\n",
  );
  console.log(JSON.stringify(failure));
  process.exitCode = 1;
} finally {
  await context?.close();
  rmSync(scratch, { recursive: true, force: true });
}
