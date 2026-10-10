import { defineConfig } from "@playwright/test";
// Own resources are started separately after private window registration.
if (
  !process.env.COMMERCEOPS_LIVE_WEB_URL ||
  !process.env.COMMERCEOPS_B02_PRIVATE_DIR
)
  throw new Error("Explicit B02 owned live window required");
export default defineConfig({
  testMatch:
    process.env.COMMERCEOPS_WEB_BATCH === "b03"
      ? "write.spec.ts"
      : "read.spec.ts",
  testDir: "../tests/e2e/web/live",
  workers: 1,
  retries: 0,
  timeout: 45000,
  use: {
    baseURL: process.env.COMMERCEOPS_LIVE_WEB_URL,
    trace: "off",
    video: "off",
    screenshot: "off",
    browserName: "chromium",
    headless: true,
    viewport: { width: 1440, height: 1000 },
  },
  reporter: "./tooling/live-reporter.ts",
  outputDir: `${process.env.COMMERCEOPS_B02_PRIVATE_DIR}/pw-private`,
});
