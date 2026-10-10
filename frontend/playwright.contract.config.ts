import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "../tests/e2e/web/contracts",
  testMatch: "**/*.spec.ts",
  workers: 1,
  retries: 0,
  use: { trace: "off" },
  reporter: [
    ["list"],
    ["json", { outputFile: "evidence/b03/contract-results.json" }],
  ],
});
