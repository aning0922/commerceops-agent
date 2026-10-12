// Dedicated live result whitelist. Never copies TestError/stdout/body/steps.
import type {
  Reporter,
  TestCase,
  TestResult,
  FullResult,
  TestError,
} from "@playwright/test/reporter";
import { writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { resolve, relative } from "node:path";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import failureSchema from "./live-failure.schema.json" with { type: "json" };
const root = execFileSync("git", ["rev-parse", "--show-toplevel"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
const stages = ["read", "write", "items", "n01"] as const;
const statuses = ["passed", "failed", "timedOut", "skipped", "interrupted"] as const;
const matchers = ["toBe", "toEqual", "toMatchObject", "toHaveText", "toContainText", "toBeVisible", "toBeHidden", "toBeEnabled", "toBeDisabled", "toHaveValue", "toHaveCount", "toBeFocused", "toHaveAttribute", "toHaveURL", "toHaveLength", "toHaveProperty", "toContain", "toBeTruthy", "toBeFalsy", "toBeGreaterThan", "toBeLessThanOrEqual"] as const;
type Stage = typeof stages[number];
type CaseDefinition = { test: string; file: string; line: number };
const batchStage = (): Stage => process.env.COMMERCEOPS_WEB_BATCH === "p4-c09-n01" ? "n01"
  : ["b03", "b04-write"].includes(process.env.COMMERCEOPS_WEB_BATCH ?? "") ? "write"
    : process.env.COMMERCEOPS_WEB_BATCH === "b04" ? "items" : "read";
const duration = (value: number) => Number.isFinite(value) && value >= 0 && value <= Number.MAX_SAFE_INTEGER ? value : null;

// Policy comes only from this checkout's fixed four specs and tracked code,
// never from error strings, arbitrary test titles, stack traces or paths.
export function liveFailurePolicy() {
  const cases = new Map<Stage, CaseDefinition[]>();
  const code = new Map<string, number>();
  for (const stage of stages) {
    const file = `tests/e2e/web/live/${stage}.spec.ts`;
    const source = readFileSync(resolve(root, file), "utf8");
    const definitions = [...source.matchAll(/^test\("([^"\n]+)",/gm)].map((match) => ({
      test: match[1], file, line: source.slice(0, match.index).split("\n").length,
    }));
    if (!definitions.length || new Set(definitions.map((c) => c.test)).size !== definitions.length)
      throw new Error("Invalid fixed live case policy");
    cases.set(stage, definitions);
  }
  const files = execFileSync("git", ["ls-files", "frontend", "tests/e2e/web"], { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).split("\n");
  for (const file of files) {
    if (/^(frontend\/|tests\/e2e\/web\/)[A-Za-z0-9_./-]+\.(?:tsx?|py)$/.test(file) && !file.split("/").includes(".."))
      code.set(file, readFileSync(resolve(root, file), "utf8").split("\n").length);
  }
  return { cases, code };
}
type Policy = ReturnType<typeof liveFailurePolicy>;
const ajv = new Ajv2020({ strict: false, coerceTypes: false, useDefaults: false, removeAdditional: false });
addFormats(ajv);
const failureShape = ajv.compile(failureSchema);
export function validLiveFailureDiagnostic(value: unknown, policy: Policy): boolean {
  if (!failureShape(value)) return false;
  const data = value as {
    stage: Stage; expected_count: number; reported_count: number; actual_body_count: number | null;
    unreported_count: number; counts: Record<string, number>; rejected_result_count: number;
    global_error_count: number; global_errors: ReturnType<typeof safeLiveError>[];
    tests: LiveReporter["diagnostics"]; source_sha256: string; status: string;
  };
  const definitions = policy.cases.get(data.stage)!;
  if ((data.status === "passed" && data.rejected_result_count === 0 && data.global_error_count === 0) ||
      data.expected_count !== definitions.length || data.reported_count !== data.tests.length ||
      data.unreported_count !== definitions.length - data.tests.length ||
      new Set(data.tests.map((r) => r.test)).size !== data.tests.length ||
      data.global_errors.length !== Math.min(16, data.global_error_count)) return false;
  for (const row of data.tests) {
    const definition = definitions.find((c) => c.test === row.test);
    if (!definition || row.location !== `${definition.file.replace(/^tests\//, "")}:${definition.line}` ||
        (row.status === "passed" && (row.error !== null || row.body_observed !== true))) return false;
  }
  for (const error of [...data.global_errors, ...data.tests.flatMap((r) => r.error ? [r.error] : [])]) {
    if (error.location && (!(policy.code.get(error.location.file)! >= error.location.line) || error.location.line < 1)) return false;
  }
  if (!statuses.every((s) => data.counts[s] === data.tests.filter((r) => r.status === s).length)) return false;
  const bodyCount = data.unreported_count || data.rejected_result_count || data.tests.some((r) => r.body_observed === null)
    ? null : data.tests.filter((r) => r.body_observed).length;
  return data.actual_body_count === bodyCount && data.source_sha256 === createHash("sha256").update(readFileSync(resolve(root, definitions[0].file))).digest("hex");
}
export function safeLiveLocation(location: TestError["location"], policy: Policy) {
  if (!location || typeof location.file !== "string" || !Number.isSafeInteger(location.line)) return null;
  const file = relative(root, resolve(location.file)).replaceAll("\\", "/");
  const lines = policy.code.get(file);
  return lines && location.line >= 1 && location.line <= lines ? { file, line: location.line } : null;
}
export function safeLiveError(error: TestError | undefined, status: string, policy: Policy) {
  // Read a bounded first line only to derive closed enums. Never serialize any
  // message, value, cause, stack, snippet, locator, expected or actual material.
  const first = typeof error?.message === "string" ? error.message.split("\n", 1)[0].slice(0, 512).replace(/\u001b\[[0-9;]*m/g, "") : "";
  const matcher = matchers.find((name) => first.includes(`.${name}(`)) ?? null;
  const category = status === "timedOut" ? "TEST_TIMEOUT"
    : /^Error: expect\(|^expect\(/.test(first) ? "ASSERTION_FAILURE"
      : /^(?:SyntaxError:|Error: Cannot find module)/.test(first) ? "PREPARATION_ERROR" : "UNKNOWN";
  return { category, matcher, location: safeLiveLocation(error?.location, policy) };
}
export function safeLivePhase(result: Pick<TestResult, "status" | "steps">) {
  const steps = Array.isArray(result.steps) ? result.steps : [];
  const body = steps.some((s) => ["expect", "pw:api", "test.step"].includes(s.category));
  const hook = steps.find((s) => s.category === "hook" && s.error);
  const phase = hook?.title === "Before Hooks" ? "before_hooks"
    : hook?.title === "After Hooks" ? "after_hooks" : body ? "test_body" : "unknown";
  return { phase, body_observed: result.status === "passed" || body ? true : phase === "before_hooks" ? false : null };
}
export default class LiveReporter implements Reporter {
  targeted = ["b04-read", "b04-write", "b04", "p4-c09-n01"].includes(process.env.COMMERCEOPS_WEB_BATCH ?? "");
  policy = this.targeted ? liveFailurePolicy() : null;
  stage = batchStage();
  rejected = 0;
  globalErrorCount = 0;
  globalErrors: ReturnType<typeof safeLiveError>[] = [];
  diagnostics: ({ test: string; status: string; duration_ms: number; location: string } & ReturnType<typeof safeLivePhase> & { error: ReturnType<typeof safeLiveError> | null })[] = [];
  results: {
    test: string;
    status: string;
    duration_ms: number;
    location: string;
  }[] = [];
  onTestEnd(test: TestCase, result: TestResult) {
    const definition = this.policy?.cases.get(this.stage)?.find((c) => c.test === test.title);
    const location = this.policy ? safeLiveLocation(test.location, this.policy) : null;
    if (this.policy && (!definition || location?.file !== definition.file || location.line !== definition.line || !statuses.includes(result.status) || duration(result.duration) === null || this.results.some((row) => row.test === definition.test))) {
      this.rejected++;
      console.log("Live reporter rejected an unrecognized result; details withheld.");
      return;
    }
    const row = {
      test: definition?.test ?? test.title,
      status: result.status,
      duration_ms: result.duration,
      location: definition ? `${definition.file.replace(/^tests\//, "")}:${definition.line}` : `${test.location.file.split("/tests/").pop()}:${test.location.line}`,
    };
    this.results.push(row);
    if (this.policy) this.diagnostics.push({ ...row, ...safeLivePhase(result), error: result.status === "passed" ? null : safeLiveError(result.error, result.status, this.policy) });
    console.log(`${row.status}: ${row.test} (${row.duration_ms}ms)`);
  }
  onError(error: TestError) {
    if (this.policy) {
      this.globalErrorCount++;
      if (this.globalErrors.length < 16) this.globalErrors.push(safeLiveError(error, "failed", this.policy));
    }
    console.log("Live runner failed; raw error withheld.");
  }
  onEnd(result: FullResult) {
    if (this.policy && (!["passed", "failed", "timedout", "interrupted"].includes(result.status) || duration(result.duration) === null))
      throw new Error("Invalid live result metadata");
    const directory = resolve(
      process.env.COMMERCEOPS_WEB_BATCH === "p4-c09-n01"
        ? "evidence/p4-c09/n01"
        : process.env.COMMERCEOPS_WEB_BATCH === "b04-read"
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
    if (this.policy && (result.status !== "passed" || this.rejected || this.globalErrors.length)) {
      const expected = this.policy.cases.get(this.stage)!;
      const unreported = expected.filter((c) => !this.results.some((row) => row.test === c.test)).length;
      const bodyCount = unreported || this.rejected || this.diagnostics.some((row) => row.body_observed === null) ? null : this.diagnostics.filter((row) => row.body_observed).length;
      const failure = {
        schema_version: "live-failure-v1", stage: this.stage, status: result.status,
        expected_count: expected.length, reported_count: this.results.length,
        actual_body_count: bodyCount, unreported_count: unreported,
        counts: Object.fromEntries(statuses.map((status) => [status, this.results.filter((r) => r.status === status).length])),
        duration_ms: duration(result.duration), captured_at_utc: new Date().toISOString(),
        rejected_result_count: this.rejected, global_error_count: this.globalErrorCount, global_errors: this.globalErrors, tests: this.diagnostics,
        source_sha256: createHash("sha256").update(readFileSync(resolve(root, expected[0].file))).digest("hex"),
        raw_error_material: "omitted", body_count_meaning: "observed framework body steps or pass; otherwise null",
      };
      if (!validLiveFailureDiagnostic(failure, this.policy)) throw new Error("Invalid safe live failure diagnostic");
      writeFileSync(resolve(directory, "failure-diagnostic.safe.json"), JSON.stringify(failure, null, 2) + "\n", { mode: 0o600 });
    }
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
