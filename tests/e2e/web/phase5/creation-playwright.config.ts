import { resolve } from "node:path";
import { defineConfig } from "../../../../frontend/node_modules/@playwright/test";
export default defineConfig({
  testDir: ".", testMatch: "creation-ui.spec.ts", workers: 1, retries: 0,
  timeout: 30000, globalTimeout: 180000,
  use: { browserName: "chromium", headless: true, trace: "off", screenshot: "off" },
  outputDir: resolve(__dirname, "../../../../runtime/m2-web-creation/test-results"),
  reporter: [["list"], ["json", { outputFile: resolve(__dirname, "../../../../runtime/m2-web-creation/ui-results.json") }]],
});
