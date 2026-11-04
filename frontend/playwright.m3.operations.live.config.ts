import { defineConfig } from "@playwright/test";
if (!process.env.COMMERCEOPS_M3_LIVE_WEB_URL || !process.env.COMMERCEOPS_M3_PRIVATE_DIR) throw new Error("Explicit owned M3 window and private directory required");
export default defineConfig({ testDir: "./m3-live", testMatch: "owned-m3.flow.ts", workers: 1, retries: 0, maxFailures: 1, timeout: 180000, globalTimeout: 600000, reporter: "list", outputDir: `${process.env.COMMERCEOPS_M3_PRIVATE_DIR}/playwright-operations`, use: { browserName: "chromium", headless: true, serviceWorkers: "block", trace: "off", video: "off", screenshot: "off" } });
