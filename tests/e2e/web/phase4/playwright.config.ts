import { defineConfig } from "../../../../frontend/node_modules/@playwright/test";
import { resolve } from "node:path";
const batch = process.env.COMMERCEOPS_WEB_BATCH === "p4-c14-template" ? "p4-c14-template" : process.env.COMMERCEOPS_WEB_BATCH === "p4-c09-reviewfix"
  ? "p4-c09-reviewfix"
  : process.env.COMMERCEOPS_WEB_BATCH === "p4-c09" ? "p4-c09" : "p4-c1";
export default defineConfig({
  testDir: ".",
  testMatch: "ui.spec.ts",
  workers: 1,
  retries: 0,
  timeout: 30000,
  globalTimeout: 30 * 60 * 1000,
  outputDir: batch === "p4-c14-template" ? resolve(__dirname, "../../../../runtime/p4-c14-template/ui-test-results") : `../../../../frontend/test-results/${batch}`,
  use: {
    headless: true,
    trace: "off",
    video: "off",
    screenshot: "off",
    browserName: "chromium",
    viewport: { width: 1440, height: 1000 },
  },
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile: resolve(
          __dirname,
          batch === "p4-c14-template" ? "../../../../runtime/p4-c14-template/ui/ui-results.json" : `../../../../frontend/evidence/${batch}/ui-results.json`,
        ),
      },
    ],
  ],
});
