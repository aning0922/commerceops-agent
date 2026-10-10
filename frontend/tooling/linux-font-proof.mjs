// Run only in the owned official Playwright Linux container, against our Mock server.
import { chromium } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
const evidence = fileURLToPath(new URL("../evidence/b01/", import.meta.url));
const browser = await chromium.launch();
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const requests = [];
  page.on("request", (req) => {
    const u = new URL(req.url());
    if (
      u.hostname !== "host.docker.internal" ||
      req.method() !== "GET" ||
      u.pathname.startsWith("/api/")
    )
      requests.push(`${req.method()} ${u.pathname}`);
  });
  await page.goto("http://host.docker.internal:3430/approvals/APR-DEMO-008");
  await page.evaluate(() => document.fonts.ready);
  const client = await page.context().newCDPSession(page);
  await client.send("DOM.enable");
  await client.send("CSS.enable");
  const { root } = await client.send("DOM.getDocument");
  const { nodeId } = await client.send("DOM.querySelector", {
    nodeId: root.nodeId,
    selector: "h1",
  });
  const { fonts } = await client.send("CSS.getPlatformFontsForNode", {
    nodeId,
  });
  if (
    !fonts.some((f) => f.isCustomFont && f.familyName.includes("Noto Sans SC"))
  )
    throw new Error("H1 Chinese is not rendered using the bundled CJK font");
  const metrics = await page.evaluate(() => ({
    width: innerWidth,
    scroll: document.documentElement.scrollWidth,
    rows: document.querySelectorAll("[role=row]").length,
    font: getComputedStyle(document.body).fontFamily,
  }));
  if (metrics.rows !== 21 || metrics.scroll > metrics.width + 1)
    throw new Error("Incomplete disclosure/overflow");
  await page.screenshot({ path: join(evidence, "linux-font-1440.png") });
  await page.setViewportSize({ width: 390, height: 900 });
  await page.locator("#SKU-20").scrollIntoViewIfNeeded();
  await page.evaluate(() => document.fonts.ready);
  const narrow = await page.evaluate(() => ({
    width: innerWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  if (narrow.scroll > 390 || requests.length)
    throw new Error("Narrow layout or network boundary failure");
  await page.screenshot({ path: join(evidence, "linux-font-390-tail.png") });
  const result = {
    time_utc: new Date().toISOString(),
    platform: process.platform,
    architecture: process.arch,
    node: process.versions.node,
    browser: browser.version(),
    fonts,
    metrics,
    narrow,
    unexpectedRequests: requests,
    result: "passed",
    scope:
      "Linux real browser CJK rendering + full Mock disclosure; no real business API/PG",
  };
  await writeFile(
    join(evidence, "linux-font.json"),
    JSON.stringify(result, null, 2) + "\n",
  );
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
