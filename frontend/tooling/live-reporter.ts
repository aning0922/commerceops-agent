// Dedicated live result whitelist. Never copies TestError/stdout/body/steps.
import type {
  Reporter,
  TestCase,
  TestResult,
  FullResult,
} from "@playwright/test/reporter";
import { writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
export default class LiveReporter implements Reporter {
  results: {
    test: string;
    status: string;
    duration_ms: number;
    location: string;
  }[] = [];
  onTestEnd(test: TestCase, result: TestResult) {
    const row = {
      test: test.title,
      status: result.status,
      duration_ms: result.duration,
      location: `${test.location.file.split("/tests/").pop()}:${test.location.line}`,
    };
    this.results.push(row);
    console.log(`${row.status}: ${row.test} (${row.duration_ms}ms)`);
  }
  onError() {
    console.log("Live runner failed; raw error withheld.");
  }
  onEnd(result: FullResult) {
    const directory = resolve(
      process.env.COMMERCEOPS_WEB_BATCH === "b04-read"
        ? "evidence/b04-live/read"
        : process.env.COMMERCEOPS_WEB_BATCH === "b04-write"
          ? "evidence/b04-live/write"
          : process.env.COMMERCEOPS_WEB_BATCH === "b04"
            ? "evidence/b04-live"
            : process.env.COMMERCEOPS_WEB_BATCH === "b03"
              ? "evidence/b03"
              : "evidence/b02-read",
    );
    mkdirSync(directory, { recursive: true });
    const report =
      JSON.stringify(
        {
          status: result.status,
          duration_ms: result.duration,
          trace: "off",
          video: "off",
          automatic_screenshot: "off",
          source_mode: "live-api",
          commerce_source_mode: "mock-fixture",
          identity_mode: "session",
          tests: this.results,
        },
        null,
        2,
      ) + "\n";
    writeFileSync(resolve(directory, "live-results.json"), report);
    if (process.env.COMMERCEOPS_WEB_BATCH === "b04-read") {
      const privateDirectory = process.env.COMMERCEOPS_B02_PRIVATE_DIR;
      if (!privateDirectory)
        throw new Error("Owned read reporter directory required");
      // Same structured whitelist, exclusively created in this new owned window.
      writeFileSync(
        resolve(privateDirectory, "read-live-results.json"),
        report,
        {
          mode: 0o600,
          flag: "wx",
        },
      );
    }
  }
}
