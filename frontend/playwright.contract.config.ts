import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "../tests/e2e/web/contracts",
  testMatch: "**/*.spec.ts",
  workers: 1,
  retries: 0,
  use: { trace: "off" },
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile:
          process.env.COMMERCEOPS_WEB_BATCH === "p4-c09"
            ? "evidence/p4-c09/contract-results.json"
            : "evidence/b04-wiring/contract-results.json",
      },
    ],
  ],
});
