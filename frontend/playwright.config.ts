import { defineConfig } from "@playwright/test";
const cases = [
  { name: "operator", role: "operator", state: "ready", port: 3410 },
  { name: "approver", role: "approver", state: "ready", port: 3411 },
  { name: "admin", role: "admin", state: "ready", port: 3412 },
  { name: "unknown", role: "approver", state: "unknown", port: 3413 },
  { name: "expired", role: "operator", state: "expired", port: 3414 },
  { name: "unavailable", role: "operator", state: "ready", port: 3415 },
];
export default defineConfig({
  testDir: "../tests/e2e/web",
  timeout: 30000,
  fullyParallel: false,
  workers: 2,
  retries: 0,
  outputDir: "test-results",
  reporter: [
    ["list"],
    ["json", { outputFile: "evidence/b01/playwright-results.json" }],
  ],
  use: {
    browserName: "chromium",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: cases.map((x) => ({
    name: x.name,
    testMatch: `${x.name}.spec.ts`,
    use: { baseURL: `http://127.0.0.1:${x.port}` },
  })),
  webServer: cases.map((x) => ({
    command: `npm run start -- --port ${x.port}`,
    url: `http://127.0.0.1:${x.port}/login`,
    reuseExistingServer: false,
    timeout: 60000,
    env: {
      NEXT_TELEMETRY_DISABLED: "1",
      COMMERCEOPS_UI_MODE: x.name === "unavailable" ? "disabled" : "mock",
      COMMERCEOPS_MOCK_ROLE: x.role,
      COMMERCEOPS_MOCK_STATE: x.state,
      COMMERCEOPS_MOCK_CAPACITY: x.role === "approver" ? "20" : "6",
    },
  })),
});
