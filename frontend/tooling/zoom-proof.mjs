// A bounded localhost-only proof using a disposable profile and permission-free MV3 worker.
// Chrome tabs.setZoom is real page zoom, distinct from CSS zoom/device metrics/pinch.
import { chromium } from "@playwright/test";
import { mkdtemp, writeFile, mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
const evidence = fileURLToPath(new URL("../evidence/b01/", import.meta.url));
const scratch = await mkdtemp(join(tmpdir(), "commerceops-b01-zoom-"));
const extension = join(scratch, "extension");
await mkdir(extension);
await writeFile(
  join(extension, "manifest.json"),
  JSON.stringify({
    manifest_version: 3,
    name: "Local CommerceOps zoom proof",
    version: "1.0",
    background: { service_worker: "worker.js" },
  }),
);
await writeFile(
  join(extension, "worker.js"),
  "chrome.runtime.onInstalled.addListener(() => {});",
);
const context = await chromium.launchPersistentContext(
  join(scratch, "profile"),
  {
    headless: false,
    channel: "chromium",
    viewport: null,
    args: [
      `--disable-extensions-except=${extension}`,
      `--load-extension=${extension}`,
      "--window-size=1440,1100",
    ],
  },
);
try {
  const worker =
    context.serviceWorkers()[0] ??
    (await context.waitForEvent("serviceworker"));
  const opened = context.waitForEvent("page");
  const target = await worker.evaluate(async () => {
    const tab = await chrome.tabs.create({
      url: "http://127.0.0.1:3430/approvals/APR-DEMO-008",
    });
    await chrome.windows.update(tab.windowId, { width: 1440, height: 1100 });
    return { id: tab.id };
  });
  const page = await opened;
  await page.waitForLoadState("networkidle");
  const metrics = () =>
    page.evaluate(() => ({
      innerWidth,
      outerWidth,
      innerHeight,
      dpr: devicePixelRatio,
      visualScale: visualViewport.scale,
      scrollWidth: document.documentElement.scrollWidth,
      rows: document.querySelectorAll("[role=row]").length,
    }));
  const before = await metrics();
  await worker.evaluate(async (id) => {
    await chrome.tabs.setZoomSettings(id, {
      mode: "automatic",
      scope: "per-tab",
    });
    await chrome.tabs.setZoom(id, 2);
  }, target.id);
  await page.waitForFunction(
    (base) => devicePixelRatio > base * 1.9,
    before.dpr,
  );
  const after = await metrics();
  const actual = await worker.evaluate(
    (id) => chrome.tabs.getZoom(id),
    target.id,
  );
  if (
    actual !== 2 ||
    Math.abs(after.innerWidth / before.innerWidth - 0.5) > 0.02 ||
    after.visualScale !== 1 ||
    after.scrollWidth > after.innerWidth + 1 ||
    after.rows !== 21
  )
    throw new Error("Real zoom or complete reflow proof did not hold");
  // Playwright's default viewport clip is incorrect after native page zoom on this host.
  // Capture the browser surface without a CSS clip, preserving the real zoomed viewport.
  const cdp = await context.newCDPSession(page);
  const layout = await cdp.send("Page.getLayoutMetrics");
  const capture = async (name) => {
    const shot = await cdp.send("Page.captureScreenshot", {
      format: "png",
      fromSurface: true,
      captureBeyondViewport: false,
    });
    await writeFile(join(evidence, name), Buffer.from(shot.data, "base64"));
  };
  await capture("actual-zoom-200-head.png");
  await page.locator("#SKU-20").scrollIntoViewIfNeeded();
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  await capture("actual-zoom-200-tail.png");
  await page.locator("[data-control=B23]").scrollIntoViewIfNeeded();
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  await capture("actual-zoom-200-actions.png");
  await writeFile(
    join(evidence, "actual-zoom.json"),
    JSON.stringify(
      {
        time_utc: new Date().toISOString(),
        method:
          "permission-free temporary MV3 chrome.tabs.setZoom(2), headed Chromium; no CSS/device-metrics/pinch emulation",
        user_profile_used: false,
        permissions: [],
        before,
        after,
        getZoom: actual,
        capture_method: "CDP Page.captureScreenshot without CSS clip",
        layout,
        complete_sku_count: 20,
        result: "passed",
      },
      null,
      2,
    ) + "\n",
  );
  console.log(
    JSON.stringify({ before, after, getZoom: actual, result: "passed" }),
  );
} finally {
  await context.close();
  await rm(scratch, { recursive: true, force: true });
}
