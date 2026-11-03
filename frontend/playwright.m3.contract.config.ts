import { defineConfig } from "@playwright/test";
export default defineConfig({ testDir: "./m3-tests", testMatch: "*.spec.ts", workers: 1, retries: 0, reporter: "list",
  use: { baseURL: process.env.COMMERCEOPS_M3_UI_FIXTURE_URL, browserName: "chromium", headless: true },
});
