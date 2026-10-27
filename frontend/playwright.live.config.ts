import { defineConfig } from "@playwright/test";
const m2 = process.env.COMMERCEOPS_WEB_BATCH === "p5-m2-live";
// Own resources are started separately after private window registration.
if (
  !process.env.COMMERCEOPS_LIVE_WEB_URL ||
  !process.env.COMMERCEOPS_B02_PRIVATE_DIR
)
  throw new Error("Explicit B02 owned live window required");
export default defineConfig({
  testMatch: m2 ? "m2.spec.ts" :
    process.env.COMMERCEOPS_WEB_BATCH === "p4-c09-n01"
      ? "n01.spec.ts"
      : process.env.COMMERCEOPS_WEB_BATCH === "b04"
      ? "items.spec.ts"
      : ["b03", "b04-write"].includes(process.env.COMMERCEOPS_WEB_BATCH ?? "")
        ? "write.spec.ts"
        : "read.spec.ts",
  testDir: "../tests/e2e/web/live",
  workers: 1,
  retries: 0,
  timeout: m2 ? 240000 : 45000,
  globalTimeout: m2 ? 240000 : 30 * 60 * 1000,
  use: {
    baseURL: process.env.COMMERCEOPS_LIVE_WEB_URL,
    trace: "off",
    video: "off",
    screenshot: "off",
    browserName: "chromium",
    headless: true,
    viewport: { width: 1440, height: 1000 },
  },
  reporter: m2 ? "./tooling/m2-live-reporter.ts" : "./tooling/live-reporter.ts",
  // No automatic media; M2 business artifacts are exclusively the private allowlist.
  outputDir: m2 ? "../.audit/m2-live-pw" : `${process.env.COMMERCEOPS_B02_PRIVATE_DIR}/pw-private`,
});
