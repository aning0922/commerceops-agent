// Offline boundaries only. No API/PG/Woo/browser identity or execution claim.
import { test, expect } from "../../../../frontend/tooling/web-test";
import { chmodSync, mkdtempSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
import sourceTemplate from "../../../../docs/contracts/p5-m2-live-source.example.json";
import restoredTemplate from "../../../../docs/contracts/p5-m2-live-restored.example.json";
import { admission, mutationAdmission, privateJson, exactShape, validateInputs, M2Files, digest, loadGolden, utf8 } from "../live/m2-resource";
import type { M2Window, Phase } from "../live/m2-resource";
import { bindReport, sameDecision, M2BrowserScope, classifyM2Post, validM2Session, sourceApprovalReadiness } from "../live/m2-consumer";
import { sourceReport } from "../phase5/source-fixtures";
import type { DTO } from "../../../../frontend/lib/p3-present";
import { offlineSession } from "../../../../frontend/lib/b04-offline-source";
import { verifyReadResponse } from "../../../../frontend/lib/p3-live-client";
import M2Reporter from "../../../../frontend/tooling/m2-live-reporter";
import type { TestCase, TestResult } from "../../../../frontend/node_modules/@playwright/test/reporter";
const now = Date.parse("2026-10-26T12:00:00Z"), date = (offset: number) => new Date(now + offset * 1000).toISOString();
function inputs(phase: Phase = "source_ready") {
    const files = structuredClone(phase === "source_ready" ? sourceTemplate.files : restoredTemplate.files) as Record<string, unknown>;
    const window = files["window.json"] as M2Window;
    window.source_sha = "a".repeat(40);
    window.source_tree = "b".repeat(40);
    window.build_id = "synthetic-build";
    window.started_at_utc = date(-60);
    window.stop_at_utc = date(3540);
    window.consumer_started_at_utc = date(-1);
    window.consumer_stop_at_utc = date(239);
    window.original_expires_at = phase === "source_ready" ? null : date(600);
    for (const value of Object.values(files))
        if (value !== window && value && typeof value === "object")
            Object.assign(value, { source_sha: window.source_sha, source_tree: window.source_tree });
    const source = files["m2-source.private.json"] as typeof sourceTemplate.files["m2-source.private.json"];
    source.anchor_day = "2026-10-26";
    source.business_now = "2026-10-25T16:00:00Z";
    source.window = { start: "2026-10-18T16:00:00Z", end: source.business_now };
    source.registration_digest = "c".repeat(64);
    const accounts = files["web-accounts.json"] as typeof sourceTemplate.files["web-accounts.json"];
    accounts.operator.password = "offline-only-placeholder";
    accounts.approver.password = "offline-only-placeholder";
    if (phase !== "source_ready") {
        const facts = files["m2-facts.private.json"] as typeof restoredTemplate.files["m2-facts.private.json"];
        facts.canonical_source.expires_at = date(600);
        facts.canonical_source.plan_hash = "d".repeat(64);
        facts.canonical_source.facts_hash = "e".repeat(64);
        Object.assign(facts.restore_binding, { source_writers_stopped_at_utc: date(-40), source_pg_stopped_at_utc: date(-30), target_verified_at_utc: date(-10), dump_sha256: "f".repeat(64) });
    }
    const consumer = files["consumer.private.json"] as typeof sourceTemplate.files["consumer.private.json"];
    consumer.argv[consumer.argv.length - 1] = consumer.argv.at(-1)!.replace(/^\^/, "");
    return files;
}
test("M2 reviewed templates are rejected as runtime; closed phase inputs admit only current exact bindings", () => {
    expect(() => validateInputs(sourceTemplate.files, "source_ready", now)).toThrow();
    expect(() => validateInputs(restoredTemplate.files, "restored_pending_verified", now)).toThrow();
    expect(validateInputs(inputs(), "source_ready", now).window.original_expires_at).toBe(null);
    expect(validateInputs(inputs("restored_pending_verified"), "restored_pending_verified", now).facts.canonical_source).not.toBe(null);
    for (const [file, mutate] of [
        ["window.json", (v: Record<string, unknown>) => { v.api_pid = "90001"; }],
        ["window.json", (v: Record<string, unknown>) => { v.extra = true; }],
        ["window.json", (v: Record<string, unknown>) => { v.phase = "restored_pending_verified"; }],
        ["consumer.private.json", (v: Record<string, unknown>) => { v.argv = ["sh", "-c", "arbitrary"]; }],
        ["consumer.private.json", (v: Record<string, unknown>) => { v.allowed_output_files = ["../other"]; }],
        ["m2-facts.private.json", (v: Record<string, unknown>) => { v.canonical_source = {}; }],
        ["m2-source.private.json", (v: Record<string, unknown>) => { v.source_sha = "9".repeat(40); }],
    ] as const) {
        const value = inputs();
        mutate(value[file] as Record<string, unknown>);
        expect(() => validateInputs(value, "source_ready", now)).toThrow();
    }
    const source = inputs();
    const a = source["web-accounts.json"] as typeof sourceTemplate.files["web-accounts.json"];
    a.approver.expected_principal_id = a.operator.expected_principal_id;
    expect(() => validateInputs(source, "source_ready", now)).toThrow();
});
test("M2 source null expiry is not expired; all real writes retain 60s and restored original expiry cannot drift", () => {
    const s = validateInputs(inputs(), "source_ready", now).window;
    expect(() => mutationAdmission(s, now)).not.toThrow();
    expect(() => mutationAdmission(s, now + 180000)).toThrow();
    expect(() => admission(s, "restored_pending_verified", now)).toThrow();
    const r = validateInputs(inputs("restored_pending_verified"), "restored_pending_verified", now).window;
    expect(() => mutationAdmission(r, now, date(600))).not.toThrow();
    expect(() => mutationAdmission(r, now, date(601))).toThrow();
    r.original_expires_at = date(299);
    expect(() => admission(r, "restored_pending_verified", now, true)).toThrow();
    const short = { ...s, stop_at_utc: date(419) };
    expect(() => admission(short, "source_ready", now, true)).toThrow();
});
test("M2 strict JSON rejects duplicate escaped aliases, extra keys and coercion without disclosing raw values", () => {
    for (const raw of ['{"a":1,"a":2}', '{"a":1,"\\u0061":2}', '{"a":{"b":1,"b":2}}', '{"a":NaN}'])
        expect(() => privateJson(raw)).toThrow("M2_INPUT_REJECTED");
    expect(() => utf8(Buffer.from([0xc3, 0x28]))).toThrow();
    expect(privateJson('{"a":[1,{"b":"text"}],"c":null}')).toEqual({ a: [1, { b: "text" }], c: null });
    expect(exactShape({ a: 1, extra: 2 }, { a: 1 })).toBe(false);
    expect(exactShape({ a: true }, { a: 1 })).toBe(false);
});
function privateDirectory() { const dir = realpathSync(mkdtempSync(join(tmpdir(), "m2-consumer-offline-"))); chmodSync(dir, 0o700); return dir; }
test("M2 protected FD reads refuse symlink/FIFO/mode/path pollution; wx originals survive collisions", () => {
    const dir = privateDirectory();
    try {
        const files = new M2Files(dir), original = '{"original":"synthetic"}';
        const ref = files.write("original.private.json", original, ["original.private.json"], true);
        expect(files.ref(ref)).toEqual({ original: "synthetic" });
        expect(() => files.write("original.private.json", "replacement", ["original.private.json"], true)).toThrow("M2_OUTPUT_REJECTED");
        expect(files.bytes(ref.file).toString()).toBe(original);
        expect(() => files.name("../escape")).toThrow();
        symlinkSync(files.name(ref.file), join(dir, "link.private.json"));
        expect(() => files.bytes("link.private.json")).toThrow();
        chmodSync(files.name(ref.file), 0o644);
        expect(() => files.bytes(ref.file)).toThrow();
        chmodSync(files.name(ref.file), 0o600);
        execFileSync("mkfifo", ["-m", "600", join(dir, "fifo.private.json")], { timeout: 1000 });
        const start = performance.now();
        expect(() => files.bytes("fifo.private.json")).toThrow();
        expect(performance.now() - start).toBeLessThanOrEqual(2000);
        expect(() => files.ref({ ...ref, sha256: "a".repeat(64) })).toThrow();
    }
    finally {
        rmSync(dir, { recursive: true });
    }
});
function oracleFixture() {
    const source = validateInputs(inputs(), "source_ready", now).source;
    const stocks = [20, 8, 0, 5], daily = [10, 4, 5, 2], quantities = [100, 40, 60, 19];
    const gold = { schema_version: "woo-positive-golden-v1", rule_version: "inventory-rule-v1", shop_id: source.shop_id, business_now: source.business_now, window: source.window, parameters: source.parameters, total_quantity: 219,
        facts: source.sku_map.map((row, i) => ({ ...row, gross_units: daily[i] * 7, net_units: daily[i] * 7, known_refunded_units: 0, D: { numerator: String(daily[i]), denominator: "1" }, A: stocks[i], T: daily[i] * 12, trigger: { numerator: String(daily[i] * 5), denominator: "1" }, suggested_units: quantities[i], risk: i === 2 ? "stockout" : "risk", pool_allocation: "exact", inbound_units: null, effective_inbound_units: 0, inbound_reason: "WOOCOMMERCE_INBOUND_UNAVAILABLE", required_assumptions: ["inbound_unknown_zero:" + row.sku_key], hard_blocks: [], suggestion_mode: "assumption_draft" })) };
    const expected = { schema_version: "woo-local-expectations-v1", shop_id: source.shop_id, business_now: source.business_now, window: source.window, expected: { products: source.sku_map } };
    const seed = { mapping: { products: { simple_a: 101, simple_b: 102, independent_parent: 103, independent_red: 104, independent_blue: 105 } } };
    return { source, gold, expected, seed };
}
test("M2 gold binds original seed mapping/EXPECTED by logical key, independent of row order; switched SKU/quantity rejected", () => {
    const dir = privateDirectory();
    try {
        const { source, gold, expected, seed } = oracleFixture(), files = new M2Files(dir);
        const fixture = (name: string, value: unknown) => { const bytes = JSON.stringify(value); writeFileSync(join(dir, name), bytes, { mode: 0o600 }); return { file: name, sha256: digest(bytes) }; };
        source.golden_ref = fixture("analysis-golden.private.json", { ...gold, facts: [...gold.facts].reverse() });
        source.expected_ref = fixture("expected.private.json", expected);
        source.seed_result_ref = fixture("seed-result.private.json", seed);
        source.sku_map.reverse();
        expect(loadGolden(files, source).facts.length).toBe(4);
        source.sku_map[0].sku_key = source.sku_map[1].sku_key;
        expect(() => loadGolden(files, source)).toThrow();
    }
    finally {
        rmSync(dir, { recursive: true });
    }
});
test("M2 report binding retains unknown inbound and checks every mapped fact, not count or total alone", () => {
    const { source, gold } = oracleFixture();
    const report = sourceReport("woocommerce_test");
    const first = report.facts.items[0];
    const items = gold.facts.map((g) => ({ ...first, ...g }));
    const read = { ...report, facts: { ...report.facts, source: { ...report.facts.source, shop_id: source.shop_id }, window: { ...report.facts.window, ...source.window }, items, candidate_count: 4 } } as DTO["ReportRead"];
    expect(() => bindReport(read, gold, { source })).not.toThrow();
    const bad = structuredClone(read);
    (bad.facts.items[0] as {
        inbound_units: number | null;
    }).inbound_units = 0;
    expect(() => bindReport(bad, gold, { source })).toThrow();
    const altered = structuredClone(read);
    (altered.facts.items[0] as {
        suggested_units: number;
    }).suggested_units += 1;
    (altered.facts.items[1] as {
        suggested_units: number;
    }).suggested_units -= 1;
    expect(() => bindReport(altered, gold, { source })).toThrow();
});
function decisionReceipt(): DTO["DecisionReceipt"] {
    const id = "00000000-0000-4000-8000-000000000001";
    return { schema_version: "p3-web-v1", identity_mode: "session", request_key: id, decision_id: id,
        task_id: id, approval_id: id, plan_id: id, plan_version: 1, plan_hash: "a".repeat(64),
        action: "approve_with_assumptions", acknowledged_assumption_keys: ["inbound_unknown_zero:synthetic"],
        approval_status: "approved", decided_by: id, decided_at: date(-1), decision_source: "web", reason_code: null,
        decision_payload_hash: "b".repeat(64), server_time: date(0), trace_id: id, resume_state: "queued", duplicate: false };
}
test("M2 original-byte replay allows queued to consumed without claiming execution completed", () => {
    const original = decisionReceipt();
    expect(sameDecision({ ...original, server_time: date(1), trace_id: "00000000-0000-4000-8000-000000000002", duplicate: true, resume_state: "consumed" }, original)).toBe(true);
    for (const before of ["waiting_checkpoint", "queued", "consumed"] as const)
        for (const after of ["waiting_checkpoint", "queued", "consumed"] as const) {
            const rank = { waiting_checkpoint: 0, queued: 1, consumed: 2 };
            expect(sameDecision({ ...original, duplicate: true, resume_state: after }, { ...original, resume_state: before })).toBe(rank[after] >= rank[before]);
        }
});
test("M2 replay rejects invalid resume states, regressions and nonduplicate receipts", () => {
    const original = decisionReceipt(), replay = { ...original, duplicate: true };
    for (const state of ["completed", "unknown", "", null]) {
        expect(sameDecision({ ...replay, resume_state: state } as unknown as DTO["DecisionReceipt"], original)).toBe(false);
        expect(sameDecision(replay, { ...original, resume_state: state } as unknown as DTO["DecisionReceipt"])).toBe(false);
    }
    expect(sameDecision({ ...replay, duplicate: false, resume_state: "consumed" }, original)).toBe(false);
    // Every replay is compared with the previous confirmed receipt, so a later
    // queued response after observed consumed cannot regress to the first receipt.
    expect(sameDecision(replay, { ...replay, resume_state: "consumed" })).toBe(false);
});
test("M2 replay preserves every stable identity, plan, action, acknowledgement and receipt field", () => {
    const original = decisionReceipt(), replay = { ...original, duplicate: true, resume_state: "consumed" as const };
    const dynamic = new Set(["server_time", "trace_id", "duplicate", "resume_state"]);
    for (const field of Object.keys(original).filter((field) => !dynamic.has(field)))
        expect(sameDecision({ ...replay, [field]: "changed" } as unknown as DTO["DecisionReceipt"], original), field).toBe(false);
});
test("M2 reporter never copies error/title/stdout/steps or private values into its safe console", () => {
    const reporter = new M2Reporter(), lines: string[] = [], old = console.log;
    try {
        console.log = (line) => { lines.push(String(line)); };
        reporter.onTestEnd({ title: "private-input" } as TestCase, { status: "failed", error: { message: "private-input" }, stdout: ["private-input"] } as TestResult);
        reporter.onError();
    }
    finally {
        console.log = old;
    }
    expect(lines.join()).not.toContain("private-input");
});
test("M2 fixed --grep source/restored each selects one case without reading inputs or starting resources", () => {
    const root = resolve(__dirname, "../../../.."), cli = join(root, "frontend/node_modules/playwright/cli.js");
    for (const phase of ["source", "restored"]) {
        const output = execFileSync(process.execPath, [cli, "test", "--config", "playwright.live.config.ts", "--list", "--grep", `M2 ${phase}$`, "--reporter=list"], { cwd: join(root, "frontend"), timeout: 15000, env: { ...process.env, COMMERCEOPS_WEB_BATCH: "p5-m2-live", COMMERCEOPS_B02_PRIVATE_DIR: "/not-a-runtime-input", COMMERCEOPS_LIVE_WEB_URL: "http://127.0.0.1:3999" }, stdio: ["ignore", "pipe", "ignore"] }).toString();
        expect(output).toContain(`M2 ${phase}`);
        expect(output).toContain("Total: 1 test in 1 file");
    }
});
test("M2 browser scope allows CORS setup, rejects unarmed business writes, extra login/preflight and external targets", () => {
    const api = "http://127.0.0.1:3999", web = "http://127.0.0.1:3998";
    const source = new M2BrowserScope(api, web, "source_ready", "operator");
    expect(source.admit("OPTIONS", api + "/api/v1/auth/login")).toBe(true);
    expect(source.admit("GET", web + "/login")).toBe(true);
    expect(source.admit("POST", api + "/api/v1/auth/login")).toBe(true);
    expect(source.admit("POST", api + "/api/v1/auth/login")).toBe(false);
    expect(source.admit("POST", api + "/api/v1/tasks/preflight")).toBe(true);
    expect(source.admit("POST", api + "/api/v1/tasks/preflight")).toBe(false);
    expect(source.admit("POST", api + "/api/v1/tasks")).toBe(false);
    expect(source.admit("GET", "https://external.invalid/")).toBe(false);
    expect(new M2BrowserScope(api, web, "source_ready", "approver").admit("POST", api + "/api/v1/tasks/preflight")).toBe(false);
    expect(new M2BrowserScope(api, web, "restored_pending_verified", "approver").admit("POST", api + "/api/v1/approvals/id/decision")).toBe(false);
});
test("M2 post classification separates definitive rejection from UNKNOWN; malformed or foreign-key success never confirms", () => {
    const key = "00000000-0000-4000-8000-000000000001";
    const input = { request_key: key };
    const body = { schema_version: "p3-web-v1", identity_mode: "session", server_time: "2026-10-26T00:00:00Z", trace_id: key, request_key: key, task_id: key, source_task_id: key, state: "queued", duplicate: false };
    expect(classifyM2Post("create_task", input, "/api/v1/tasks", 202, body).outcome).toBe("confirmed");
    expect(classifyM2Post("create_task", input, "/api/v1/tasks", 202, { ...body, request_key: "00000000-0000-4000-8000-000000000002" }).outcome).toBe("unknown");
    expect(classifyM2Post("create_task", input, "/api/v1/tasks", 202, { ...body, extra: "untrusted" }).value).toBe(null);
    const error = { schema_version: "p3-web-v1", server_time: null, trace_id: key, error: { code: "IDEMPOTENCY_CONFLICT", safe_message: "offline", retryable: false, receipt: null } };
    expect(classifyM2Post("create_task", input, "/api/v1/tasks", 409, error).outcome).toBe("rejected");
    expect(classifyM2Post("create_task", input, "/api/v1/tasks", null, null).outcome).toBe("unknown");
});
test("M2 frozen server business-read shape accepts both roles; creation, scope and expiry remain constrained", () => {
    // Direct projection of committed web_sessions._read: both business roles can
    // read tasks/approvals. No PG execution or can_decide claim is made here.
    for (const role of ["operator", "approver"] as const) {
        const account = sourceTemplate.files["web-accounts.json"][role];
        const base = offlineSession();
        const session: DTO["SessionRead"] = { ...base, principal: { ...base.principal,
                principal_id: account.expected_principal_id,
                organization_id: account.expected_organization_id,
                role_shop_grants: [{ role, shop_id: account.expected_shop_id }],
                capabilities: { can_create_task: role === "operator", can_read_tasks: true,
                    can_read_approvals: true, can_resolve_items: false, can_read_operations: false, home_path: "/tasks" },
            } };
        expect(verifyReadResponse("GET", "/api/v1/auth/session", 200, session)).toBe(true);
        expect(validM2Session(session, account, role)).toBe(true);
        expect(validM2Session({ ...session, principal: { ...session.principal, capabilities: { ...session.principal.capabilities, can_read_approvals: false } } }, account, role)).toBe(false);
        expect(validM2Session({ ...session, principal: { ...session.principal, capabilities: { ...session.principal.capabilities, can_create_task: role !== "operator" } } }, account, role)).toBe(false);
        expect(validM2Session({ ...session, principal: { ...session.principal, role_shop_grants: [{ role, shop_id: "00000000-0000-4000-8000-000000000099" }] } }, account, role)).toBe(false);
        expect(validM2Session({ ...session, principal: { ...session.principal, principal_id: "00000000-0000-4000-8000-000000000099" } }, account, role)).toBe(false);
        expect(validM2Session({ ...session, idle_expires_at: session.server_time }, account, role)).toBe(false);
    }
});
test("M2 source pending readiness waits only on current bound nonexpired objects, then exits on ready or rejection", () => {
    // Minimal typed domain fixture for readiness only; complete remote DTO shape
    // remains enforced by the production read() before this predicate is called.
    const expiry = date(600), plan = { plan_id: "plan", task_id: "task", plan_version: 1,
        plan_hash: "hash", status: "current", expires_at: expiry, disclosure_complete: true,
        items: [], item_count: 0, total_units: 0, hard_blocks: [], required_assumptions: [] } as unknown as DTO["Plan"];
    const task = { task: { state: "awaiting_approval", task_id: "task" }, current_plan_id: "plan", approval_id: "approval" } as unknown as DTO["TaskRead"];
    const pending = { server_time: date(0), plan, decision: null, nonce: "n".repeat(43), disabled_reasons: [],
        approval: { approval_id: "approval", task_id: "task", plan_id: "plan", plan_version: 1,
            plan_hash: "hash", status: "pending", expires_at: expiry, ready_at: null, can_decide: true } } as unknown as DTO["ApprovalRead"];
    const ready = { ...pending, approval: { ...pending.approval, ready_at: date(-1) } };
    expect([pending, ready].map((read) => sourceApprovalReadiness(read, task, plan, now + 240000, now))).toEqual(["wait", "ready"]);
    expect(() => sourceApprovalReadiness({ ...pending, nonce: null, disabled_reasons: ["NOT_DECIDABLE"],
        approval: { ...pending.approval, can_decide: false } }, task, plan, now + 240000, now)).toThrow("M2_AUTH_INVALID");
    for (const bad of [
        { ...pending, approval: { ...pending.approval, status: "expired" as const } },
        { ...pending, approval: { ...pending.approval, plan_hash: "different" } },
        { ...ready, approval: { ...ready.approval, can_decide: false } },
        { ...pending, approval: { ...pending.approval, can_decide: false } },
        { ...pending, nonce: null },
        { ...pending, disabled_reasons: ["ACCESS_DENIED"] },
        { ...pending, approval: { ...pending.approval, expires_at: date(-1) } },
    ])
        expect(() => sourceApprovalReadiness(bad, task, plan, now + 240000, now)).toThrow();
    expect(() => sourceApprovalReadiness(pending, task, plan, now + 59999, now)).toThrow("M2_DEADLINE");
    expect(() => sourceApprovalReadiness(pending, { ...task, task: { ...task.task, state: "rejected" } }, plan, now + 240000, now)).toThrow();
});
