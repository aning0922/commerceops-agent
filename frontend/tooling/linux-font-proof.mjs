import { startOwnedMock, verifyOwnedMock, frontend } from "./owned-mock.mjs";
import { spawn } from "node:child_process";
// Run only in the owned official Playwright Linux container, against our Mock server.
import { chromium } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
const evidence = fileURLToPath(new URL("../evidence/b01/", import.meta.url));
const arg = (name) =>
  process.argv.includes(name)
    ? process.argv[process.argv.indexOf(name) + 1]
    : undefined;
if (!process.argv.includes("--container-client")) {
  const owned = await startOwnedMock(arg("--base-url"));
  try {
    const mapped = `http://host.docker.internal:${owned.origin.port}`;
    const child = spawn(
      "docker",
      [
        "run",
        "--rm",
        "--name",
        "commerceops-b01-linux-font-owned",
        "--shm-size=256m",
        "-v",
        `${frontend}:/work:ro`,
        "-v",
        `${evidence}:/work/evidence/b01`,
        "-w",
        "/work",
        "mcr.microsoft.com/playwright:v1.64.0-noble",
        "node",
        "tooling/linux-font-proof.mjs",
        "--container-client",
        "--base-url",
        mapped,
        "--service",
        owned.serviceId,
        "--build",
        owned.buildId,
        "--owner-pid",
        String(owned.pid),
      ],
      { stdio: "inherit" },
    );
    const code = await new Promise((resolve) => child.once("exit", resolve));
    if (code !== 0) throw new Error("Owned Linux proof did not pass");
  } finally {
    await owned.close();
  }
  process.exit(0);
}
const target = new URL(arg("--base-url") ?? "");
if (
  process.platform !== "linux" ||
  target.protocol !== "http:" ||
  target.hostname !== "host.docker.internal" ||
  !target.port ||
  target.pathname !== "/" ||
  target.search ||
  target.hash ||
  !arg("--service") ||
  !arg("--build") ||
  !arg("--owner-pid")
)
  throw new Error("Only explicit owned-container mapping is allowed");
const owned = { serviceId: arg("--service"), buildId: arg("--build") };
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
  await page.goto(new URL("/approvals/APR-DEMO-008", target).href);
  const sourceBefore = await verifyOwnedMock(page, owned);
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
  const sourceAfter = await verifyOwnedMock(page, owned);
  const result = {
    sourceBefore,
    sourceAfter,
    owned_server_pid: Number(arg("--owner-pid")),
    base_url: target.origin,
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
