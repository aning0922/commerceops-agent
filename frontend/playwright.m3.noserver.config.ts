import { defineConfig } from "@playwright/test";

// Node-only contracts. Owned UI_FIXTURE/live suites have separate resource gates.
export default defineConfig({
  testDir: "./m3-tests",
  testMatch: [
    "daily-read.spec.ts",
    "daily-s3-read.spec.ts",
    "daily-write.spec.ts",
    "live-network-guard.spec.ts",
    "p6-inquiry.spec.ts",
    "copy.spec.ts",
    "operations-collection.spec.ts",
  ],
  forbidOnly: true,
  workers: 1,
  retries: 0,
  timeout: 10000,
  globalTimeout: 60000,
  reporter: "json",
  outputDir: "../.audit/m3-noserver-results",
});
