import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "../tests/e2e/web",
  testMatch: "b04-offline.spec.ts",
  workers: 1,
  retries: 0,
  timeout: 30000,
  outputDir: "test-results/b04-offline",
  reporter: [
    ["list"],
    ["json", { outputFile: "evidence/b04-wiring/ui-results.json" }],
  ],
  use: {
    browserName: "chromium",
    headless: true,
    baseURL: "http://127.0.0.1:3490",
    viewport: { width: 1440, height: 1000 },
    trace: "off",
    video: "off",
    screenshot: "off",
  },
  webServer: {
    command: "npm run start -- --port 3490",
    url: "http://127.0.0.1:3490/replenishment-items",
    reuseExistingServer: false,
    timeout: 60000,
    env: {
      NEXT_TELEMETRY_DISABLED: "1",
      COMMERCEOPS_UI_MODE: "mock",
      COMMERCEOPS_MOCK_BATCH: "b04-wiring",
      COMMERCEOPS_API_ORIGIN: "",
      COMMERCEOPS_WEB_TRANSPORT: "",
      COMMERCEOPS_MOCK_ROLE: "operator",
    },
  },
});
