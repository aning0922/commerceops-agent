import { defineConfig } from "@playwright/test";
export default defineConfig({ testDir: "./m3-tests", testMatch: "*.spec.ts", workers: 1, retries: 0, reporter: "list" });
