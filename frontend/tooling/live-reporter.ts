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
      process.env.COMMERCEOPS_WEB_BATCH === "b03"
        ? "evidence/b03"
        : "evidence/b02-read",
    );
    mkdirSync(directory, { recursive: true });
    writeFileSync(
      resolve(directory, "live-results.json"),
      JSON.stringify(
        {
          status: result.status,
          duration_ms: result.duration,
          trace: "off",
          video: "off",
          automatic_screenshot: "off",
          source_mode: "mock",
          identity_mode: "session",
          tests: this.results,
        },
        null,
        2,
      ) + "\n",
    );
  }
}
