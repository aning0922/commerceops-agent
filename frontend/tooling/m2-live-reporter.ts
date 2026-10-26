// M2 emits its closed safe result from the consumer. Never print raw Playwright errors/steps.
import type { Reporter, TestCase, TestResult, FullResult } from "@playwright/test/reporter";
export default class M2Reporter implements Reporter {
    onTestEnd(test: TestCase, result: TestResult) {
        const title = ["M2 source", "M2 restored"].includes(test.title) ? test.title : "M2 rejected case";
        const status = ["passed", "failed", "timedOut", "skipped", "interrupted"].includes(result.status) ? result.status : "failed";
        console.log(`${title}: ${status}`);
    }
    onError() { console.log("M2 consumer error; raw details withheld."); }
    onEnd(result: FullResult) { console.log(result.status === "passed" ? "M2 consumer finished." : "M2 consumer did not pass."); }
}
