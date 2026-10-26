import { resolve } from "node:path";
import { defineConfig } from "../../../../frontend/node_modules/@playwright/test";
export default defineConfig({
  testDir: ".", testMatch: "source-ui.spec.ts", workers: 1, retries: 0,
  timeout: 30000, globalTimeout: 120000,
  use: { browserName: "chromium", headless: true, trace: "off", screenshot: "off" },
  outputDir: "../../../../runtime/m2-web-source/test-results",
  reporter: [["list"], ["json", { outputFile: resolve(__dirname, "../../../../runtime/m2-web-source/ui-results.json") }]],
});
