import { defineConfig } from "../../../../frontend/node_modules/@playwright/test";
import { resolve } from "node:path";
export default defineConfig({
  testDir: ".",
  testMatch: "ui.spec.ts",
  workers: 1,
  retries: 0,
  timeout: 30000,
  globalTimeout: 30 * 60 * 1000,
  outputDir:
    process.env.COMMERCEOPS_WEB_BATCH === "p4-c09"
      ? "../../../../frontend/test-results/p4-c09"
      : "../../../../frontend/test-results/p4-c1",
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
          `../../../../frontend/evidence/${process.env.COMMERCEOPS_WEB_BATCH === "p4-c09" ? "p4-c09" : "p4-c1"}/ui-results.json`,
        ),
      },
    ],
  ],
});
