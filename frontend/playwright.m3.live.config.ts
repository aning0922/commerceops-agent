import { defineConfig } from "@playwright/test";
if (!process.env.COMMERCEOPS_M3_LIVE_WEB_URL || !process.env.COMMERCEOPS_M3_PRIVATE_DIR)
  throw new Error("Explicit M3 owned live window and private directory required");
export default defineConfig({
  testDir: "./m3-live", testMatch: "*.spec.ts", workers: 1, retries: 0,
  timeout: 45000, globalTimeout: 180000, reporter: "list",
  outputDir: `${process.env.COMMERCEOPS_M3_PRIVATE_DIR}/playwright`,
  use: { baseURL: process.env.COMMERCEOPS_M3_LIVE_WEB_URL, browserName: "chromium", headless: true,
    viewport: { width: 1440, height: 1000 }, trace: "off", video: "off", screenshot: "off", serviceWorkers: "block" },
});
