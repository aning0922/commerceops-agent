import { defineConfig } from "@playwright/test";
// The actual API/credentials are supplied only in the Root-approved live window.
export default defineConfig({
  testDir: "../tests/e2e/web/live",
  workers: 1,
  retries: 0,
  use: {
    baseURL: process.env.COMMERCEOPS_LIVE_WEB_URL,
    trace: "off",
    video: "off",
    // Explicit sanitized captures belong to reviewed live tests; no automatic
    // screenshot may preserve login inputs or transient session capabilities.
    screenshot: "off",
  },
  reporter: "list",
  outputDir: "test-results/live-safe",
});
