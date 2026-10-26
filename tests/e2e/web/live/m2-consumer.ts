import type { Browser, BrowserContext, Page, TestInfo, Response as PWResponse } from "../../../../frontend/node_modules/@playwright/test";
import { verifyReadResponse } from "../../../../frontend/lib/p3-live-client";
import { validWooCreateInput } from "../../../../frontend/lib/p5-commerce-source";
import { validN01Response, n01MatchesInput } from "../../../../frontend/lib/p4-n01";
import type { WooN01Response } from "../../../../frontend/lib/p4-n01";
import type { DTO } from "../../../../frontend/lib/p3-present";
import { planComplete } from "../../../../frontend/lib/p3-present";
import { admission, digest, fail, loadGolden, loadM2, mutationAdmission, privateJson, requireM2, utc, utf8 } from "./m2-resource";
import type { FileRef, Phase, Golden } from "./m2-resource";
type Runtime = ReturnType<typeof loadM2>;
import { isDeepStrictEqual } from "node:util";
type Receipt = DTO["CreateTaskReceipt"] | DTO["DecisionReceipt"];
type Check = {
    name: string;
    outcome: "passed" | "failed" | "not_run";
};
const same = isDeepStrictEqual;
const safeErrorCodes = new Set(["M2_AUTH_INVALID", "M2_BINDING", "M2_CONSUMER_FAILED", "M2_CONTEXT_CLOSE_FAILED", "M2_DEADLINE", "M2_EXECUTION_REJECTED", "M2_EXTRA_WRITE", "M2_GOLD_MISMATCH", "M2_INPUT_CHANGED", "M2_INPUT_REJECTED", "M2_OUTPUT_EXISTS", "M2_OUTPUT_REJECTED", "M2_REQUEST_REJECTED", "M2_RESPONSE_REJECTED", "M2_WRITE_REJECTED", "M2_WRITE_UNKNOWN"]);
const sameSet = (a: readonly string[], b: readonly string[]) => a.length === b.length && new Set(a).size === a.length && [...a].sort().join("\0") === [...b].sort().join("\0");
export function classifyM2Post(operation: "create_task" | "decision", input: Record<string, unknown>, path: string, status: number | null, value: unknown) {
    if (status === null || !verifyReadResponse("POST", path, status, value))
        return { outcome: "unknown" as const, value: null, result: null };
    if (status >= 500)
        return { outcome: "unknown" as const, value, result: null };
    if (status >= 400)
        return { outcome: "rejected" as const, value, result: null };
    const result = value as Receipt;
    let bound = result.request_key === input.request_key && (operation === "decision" ? "decision_id" in result : !("decision_id" in result));
    if (operation === "decision" && "decision_id" in result)
        bound = bound && ["approval_id", "plan_id", "plan_version", "plan_hash", "action"].every((key) => (result as unknown as Record<string, unknown>)[key] === input[key]) && Array.isArray(input.acknowledged_assumption_keys) && sameSet(result.acknowledged_assumption_keys, input.acknowledged_assumption_keys);
    return { outcome: bound ? "confirmed" as const : "unknown" as const, value, result: bound ? result : null };
}
export function sameDecision(replay: DTO["DecisionReceipt"], original: DTO["DecisionReceipt"]) {
    const { trace_id: _a, server_time: _b, duplicate: _c, ...business } = replay;
    const { trace_id: _d, server_time: _e, duplicate: _f, ...expected } = original;
    return same(business, expected);
}
const keysFor = (gold: Golden) => gold.facts.flatMap((f) => f.required_assumptions).sort();
function bindPlan(plan: DTO["Plan"], report: DTO["ReportRead"], gold: Golden, version: string) {
    requireM2(planComplete(plan) && plan.rule_version === gold.rule_version && plan.currency === "CNY" && plan.hard_blocks.length === 0 && same(plan.parameters, { source_mode: "woocommerce_test", source_config_version: version, L: 3, R: 7, S: 2 }) && plan.required_assumptions.every((a) => a.estimated_units === 0 && a.key === "inbound_unknown_zero:" + a.sku_key) && plan.task_id === report.task_id && plan.source.report_id === report.source.report_id && plan.source.snapshot_id === report.source.snapshot_id && plan.source.facts_hash === report.facts.facts_hash && plan.total_units === 219 && plan.item_count === 4 && sameSet(plan.required_assumptions.map((x) => x.key), keysFor(gold)), "M2_BINDING");
    for (const fact of gold.facts) {
        const item = plan.items.find((x) => x.sku_key === fact.sku_key);
        requireM2(item && item.stock_pool_key === fact.stock_pool_key && item.quantity === fact.suggested_units && item.raw_inbound_units === null && item.effective_inbound_units === 0, "M2_GOLD_MISMATCH");
    }
}
export function bindReport(report: DTO["ReportRead"], gold: Golden, runtime: Pick<Runtime, "source">) {
    const facts = report.facts, source = runtime.source;
    requireM2(report.source.facts_hash === facts.facts_hash && report.source.source_complete && facts.complete && facts.source_complete && facts.requires_review && facts.rule_version === gold.rule_version && facts.items.length === 4 && facts.candidate_count === 4 && !facts.scope_required && facts.source.shop_id === source.shop_id && facts.source.currency === "CNY" && facts.source.timezone === source.timezone && facts.source.provenance.source_kind === "woocommerce_test" && utc(facts.window.start) === utc(source.window.start) && utc(facts.window.end) === utc(source.window.end) && facts.L === 3 && facts.R === 7 && facts.S === 2, "M2_GOLD_MISMATCH");
    requireM2(new Set(facts.items.map((f) => f.sku_key)).size === 4);
    for (const expected of gold.facts) {
        const fact = facts.items.find((v) => v.sku_key === expected.sku_key);
        requireM2(fact, "M2_GOLD_MISMATCH");
        for (const key of ["stock_pool_key", "gross_units", "net_units", "known_refunded_units", "D", "A", "T", "trigger", "risk", "suggested_units", "inbound_units", "effective_inbound_units", "inbound_reason", "suggestion_mode"] as const)
            requireM2(same(fact[key], expected[key]), "M2_GOLD_MISMATCH");
        requireM2(fact.hard_blocks.length === 0 && sameSet(fact.required_assumptions, expected.required_assumptions), "M2_GOLD_MISMATCH");
    }
}
// Browser API CORS preflight is read-only. Only the explicitly gated page route
// may bypass this scope for the one original business POST.
export class M2BrowserScope {
    private logins = 0;
    private preflights = 0;
    constructor(private api: string, private web: string, private phase: Phase, private role: "operator" | "approver") { }
    admit(method: string, target: string) {
        const url = new URL(target), api = url.origin === this.api, web = url.origin === this.web;
        if ((api || web) && method === "GET")
            return true;
        if (api && method === "OPTIONS")
            return true;
        if (api && method === "POST" && url.pathname === "/api/v1/auth/login" && this.logins++ === 0)
            return true;
        if (api && method === "POST" && this.phase === "source_ready" && this.role === "operator" && url.pathname === "/api/v1/tasks/preflight" && this.preflights++ === 0)
            return true;
        return false;
    }
}
export async function runM2(browser: Browser, info: TestInfo, phase: Phase) {
    const r = loadM2(phase), gold = loadGolden(r.files, r.source), contexts: BrowserContext[] = [], artifacts: FileRef[] = [];
    const names = phase === "source_ready" ? ["admission", "operator_identity", "woo_n01", "explicit_create", "source_gold", "pending_approval_readonly"] : ["admission", "operator_identity", "restored_binding", "explicit_decision", "ten_original_byte_replays", "execution_readback"];
    const checks: Check[] = names.map((name) => ({ name, outcome: "not_run" }));
    const inputs = ["window.json", "web-accounts.json", "m2-source.private.json", "m2-facts.private.json", "consumer.private.json"].map((name) => ({ name, sha: digest(r.files.bytes(name)) }));
    const prefix = phase === "source_ready" ? "source" : "restored", started = new Date().toISOString();
    let outcome: "passed" | "failed" | "unknown" = "failed", errorCode: string | null = null, unknown = false, forbiddenRequest = false;
    info.setTimeout(Math.max(1, Math.min(239000, utc(r.window.consumer_stop_at_utc) - Date.now() - 1000)));
    const check = (name: string) => { const item = checks.find((c) => c.name === name); requireM2(item && item.outcome === "not_run"); item.outcome = "passed"; };
    const artifact = (file: string) => { const ref = artifacts.find((a) => a.file === file); requireM2(ref, "M2_OUTPUT_REJECTED"); return ref; };
    const write = (file: string, value: unknown, raw = false) => { const ref = r.files.write(file, value, r.consumer.allowed_output_files, raw); artifacts.push(ref); return ref; };
    const immutableRefs = [r.window.resource_registration_ref, r.source.expected_ref, r.source.golden_ref, r.source.seed_result_ref,
        ...Object.entries(r.facts.canonical_source ?? {}).filter(([key]) => key.endsWith("_ref")).map(([, ref]) => ref as FileRef),
        ...(r.facts.restore_binding ? [r.facts.restore_binding.restore_receipt_ref] : [])];
    const guard = () => {
        requireM2(!forbiddenRequest, "M2_EXTRA_WRITE");
        r.verifySource();
        admission(r.window, phase, Date.now());
        for (const input of inputs)
            requireM2(digest(r.files.bytes(input.name)) === input.sha, "M2_INPUT_CHANGED");
        for (const ref of immutableRefs)
            r.files.ref(ref);
    };
    const read = async <T>(page: Page, path: string): Promise<T> => {
        guard();
        const response = await page.request.get(r.window.api_origin + path, { timeout: Math.min(10000, utc(r.window.consumer_stop_at_utc) - Date.now()), maxRedirects: 0 });
        requireM2(response.status() !== 401 && response.status() !== 403, "M2_AUTH_INVALID");
        requireM2(response.headers()["content-type"]?.toLowerCase().startsWith("application/json"), "M2_RESPONSE_REJECTED");
        const bytes = await response.body();
        requireM2(bytes.length <= 2 * 1024 * 1024, "M2_RESPONSE_REJECTED");
        const body = privateJson(utf8(bytes));
        requireM2(verifyReadResponse("GET", new URL(path, r.window.api_origin).pathname, response.status(), body) && response.ok(), "M2_RESPONSE_REJECTED");
        guard();
        return body as T;
    };
    const contextFor = async (role: "operator" | "approver") => {
        guard();
        const account = r.accounts[role];
        const context = await browser.newContext({ baseURL: r.window.web_origin, viewport: { width: 1440, height: 1000 }, serviceWorkers: "block" });
        contexts.push(context);
        context.setDefaultTimeout(15000);
        context.setDefaultNavigationTimeout(15000);
        const scope = new M2BrowserScope(r.window.api_origin, r.window.web_origin, phase, role);
        await context.route("**/*", async (route) => {
            const request = route.request();
            if (scope.admit(request.method(), request.url())) {
                await route.continue();
                return;
            }
            forbiddenRequest = true;
            await route.abort();
        });
        const page = await context.newPage();
        await page.goto("/login");
        try {
            await page.locator("#live-login").evaluate((el, value) => { (el as HTMLInputElement).value = value; }, account.login);
            await page.locator("#live-password").evaluate((el, value) => { (el as HTMLInputElement).value = value; }, account.password);
            await page.getByRole("button", { name: "登录", exact: true }).click();
        }
        finally {
            await page.locator("#live-password").evaluateAll((els) => els.forEach((el) => { (el as HTMLInputElement).value = ""; })).catch(() => { });
        }
        await page.locator('[data-source-mode="live-session"]').waitFor();
        const session = await read<DTO["SessionRead"]>(page, "/api/v1/auth/session");
        requireM2(session.principal.principal_id === account.expected_principal_id && session.principal.organization_id === account.expected_organization_id && session.principal.linked_channels.includes("web") && session.principal.role_shop_grants.length === 1 && session.principal.capabilities.can_create_task === (role === "operator") && session.principal.capabilities.can_read_approvals === (role === "approver") && session.principal.role_shop_grants.some((g) => g.role === account.expected_role && g.shop_id === account.expected_shop_id) && utc(session.absolute_expires_at) > utc(session.server_time) && utc(session.idle_expires_at) > utc(session.server_time), "M2_AUTH_INVALID");
        return page;
    };
    const receipt = async (response: PWResponse | null, operation: "create_task" | "decision", input: Record<string, unknown>, path: string, file: string) => {
        let status: number | null = null, value: unknown = null;
        try {
            if (response) {
                status = response.status();
                const bytes = await response.body();
                requireM2(bytes.length <= 2 * 1024 * 1024 && response.headers()["content-type"]?.toLowerCase().startsWith("application/json"));
                value = privateJson(utf8(bytes));
            }
        }
        catch {
            value = null;
        }
        const classified = classifyM2Post(operation, input, path, status, value);
        write(file, { schema_version: "p5-m2-receipt-v1", run_id: r.window.run_id, phase, operation, request_key: input.request_key, via: "post", http_status: status, outcome: classified.outcome, response: classified.value, error_code: classified.outcome === "confirmed" ? null : classified.outcome === "rejected" ? "M2_WRITE_REJECTED" : "M2_WRITE_UNKNOWN" });
        return { result: classified.result, rejected: classified.outcome === "rejected" };
    };
    const unknownLookup = async (page: Page, operation: "create_task" | "decision", key: string) => {
        unknown = true;
        const path = `/api/v1/requests/${key}?operation=${operation}`;
        // Exactly one original-key read. Never recover by issuing another POST.
        let status: number | null = null, value: unknown = null, confirmed = false;
        try {
            guard();
            const response = await page.request.get(r.window.api_origin + path, { timeout: Math.min(10000, utc(r.window.consumer_stop_at_utc) - Date.now()), maxRedirects: 0 });
            status = response.status();
            const bytes = await response.body();
            requireM2(bytes.length <= 2 * 1024 * 1024 && response.headers()["content-type"]?.toLowerCase().startsWith("application/json"));
            value = privateJson(utf8(bytes));
            const valid = verifyReadResponse("GET", `/api/v1/requests/${key}`, status, value);
            const record = value as DTO["RequestRead"];
            confirmed = response.ok() && valid && record.request_key === key && record.receipt.operation === operation && record.receipt.result.request_key === key;
            if (!valid)
                value = null;
        }
        catch {
            confirmed = false;
        }
        write(`${prefix}-${operation === "create_task" ? "create" : "decision"}-lookup.private.json`, { schema_version: "p5-m2-receipt-v1", run_id: r.window.run_id, phase, operation, request_key: key, via: "lookup", http_status: status, outcome: confirmed ? "confirmed" : "unknown", response: value, error_code: confirmed ? null : "M2_WRITE_UNKNOWN" });
        fail("M2_WRITE_UNKNOWN");
    };
    const actualWrite = async (page: Page, operation: "create_task" | "decision", path: string, click: () => Promise<void>, expiry?: string) => {
        let original: Record<string, unknown> | null = null, raw = "", admitted = false, routeError = false;
        await page.route(r.window.api_origin + path, async (route) => {
            if (route.request().method() !== "POST") {
                await route.continue();
                return;
            }
            try {
                requireM2(!admitted, "M2_EXTRA_WRITE");
                guard();
                r.verifyLive();
                mutationAdmission(r.window, Date.now(), expiry);
                const bytes = route.request().postDataBuffer();
                requireM2(bytes && bytes.length <= 16384 && Buffer.from(bytes.toString("utf8"), "utf8").equals(bytes), "M2_REQUEST_REJECTED");
                raw = bytes.toString("utf8");
                const input = privateJson(raw) as Record<string, unknown>;
                if (operation === "create_task")
                    requireM2(validWooCreateInput(input) && input.shop_id === r.window.shop_id && (input.parameters as {
                        source_config_version: string;
                    }).source_config_version === r.source.source_config_version && same(input.parameters, { source_mode: "woocommerce_test", source_config_version: r.source.source_config_version, L: 3, R: 7, S: 2 }), "M2_REQUEST_REJECTED");
                else {
                    const canonical = r.facts.canonical_source!;
                    requireM2(Object.keys(input).sort().join() === ["schema_version", "request_key", "approval_id", "plan_id", "plan_version", "plan_hash", "action", "acknowledged_assumption_keys", "nonce"].sort().join() && input.schema_version === "p3-web-v1" && input.approval_id === canonical.approval_id && input.plan_id === canonical.plan_id && input.plan_version === canonical.plan_version && input.plan_hash === canonical.plan_hash && input.action === "approve_with_assumptions" && Array.isArray(input.acknowledged_assumption_keys) && sameSet(input.acknowledged_assumption_keys, keysFor(gold)) && typeof input.nonce === "string" && /^[A-Za-z0-9_-]{43}$/.test(input.nonce), "M2_REQUEST_REJECTED");
                }
                requireM2(typeof input.request_key === "string" && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(input.request_key));
                write(`${prefix}-${operation === "create_task" ? "create" : "decision"}-request.private.json`, raw, true);
                original = input;
                admitted = true;
                await route.continue();
            }
            catch {
                routeError = true;
                await route.abort().catch(() => { });
            }
        });
        const awaited = page.waitForResponse((response) => response.url() === r.window.api_origin + path && response.request().method() === "POST", { timeout: Math.min(15000, utc(r.window.consumer_stop_at_utc) - Date.now()) }).catch(() => null);
        try {
            await click().catch(() => { });
            const response = await awaited;
            requireM2(admitted && original, "M2_REQUEST_REJECTED");
            const input = original as Record<string, unknown>, key = input.request_key as string;
            const posted = await receipt(routeError ? null : response, operation, input, path, `${prefix}-${operation === "create_task" ? "create" : "decision"}-receipt.private.json`);
            if (posted.rejected)
                fail("M2_WRITE_REJECTED");
            if (!posted.result)
                await unknownLookup(page, operation, key);
            return { result: posted.result!, input, raw };
        }
        finally {
            await page.unroute(r.window.api_origin + path);
        }
    };
    try {
        if (r.facts.canonical_source) {
            const canonical = r.facts.canonical_source;
            const observed = r.files.ref(canonical.source_observed_ref) as Record<string, unknown>;
            for (const key of ["organization_id", "shop_id", "create_request_key", "task_id", "source_task_id", "report_id", "snapshot_id", "facts_hash", "plan_id", "plan_version", "plan_hash", "approval_id", "expires_at"] as const)
                requireM2(key === "expires_at" ? utc(observed[key]) === utc(canonical[key]) : observed[key] === canonical[key], "M2_BINDING");
            requireM2(observed.schema_version === "p5-m2-source-observed-v1" && observed.operator_principal_id === r.accounts.operator.expected_principal_id && observed.approver_principal_id === r.accounts.approver.expected_principal_id && observed.run_id === r.window.run_id && observed.source_sha === r.window.source_sha && observed.source_tree === r.window.source_tree && Array.isArray(observed.required_assumption_keys) && sameSet(observed.required_assumption_keys, canonical.required_assumption_keys), "M2_BINDING");
            const original = r.files.ref(canonical.source_create_request_ref) as DTO["CreateNewCycle"];
            requireM2(validWooCreateInput(original) && original.request_key === canonical.create_request_key && original.shop_id === r.window.shop_id && original.parameters.source_mode === "woocommerce_test" && original.parameters.source_config_version === r.source.source_config_version && original.parameters.L === 3 && original.parameters.R === 7 && original.parameters.S === 2, "M2_BINDING");
            const oldApproval = r.files.ref(canonical.source_approval_read_ref) as DTO["ApprovalRead"];
            requireM2(verifyReadResponse("GET", `/api/v1/approvals/${canonical.approval_id}`, 200, oldApproval) && oldApproval.approval.status === "pending" && oldApproval.nonce !== null && oldApproval.approval.approval_id === canonical.approval_id && oldApproval.approval.task_id === canonical.task_id && oldApproval.approval.plan_id === canonical.plan_id && oldApproval.approval.plan_version === canonical.plan_version && oldApproval.approval.plan_hash === canonical.plan_hash && utc(oldApproval.approval.expires_at) === utc(canonical.expires_at), "M2_BINDING");
            const saved = r.files.ref(canonical.source_create_receipt_ref) as {
                schema_version: string;
                run_id: string;
                phase: string;
                via: string;
                response: DTO["CreateTaskReceipt"];
                outcome: string;
                operation: string;
                request_key: string;
                http_status: number;
            };
            requireM2(saved.schema_version === "p5-m2-receipt-v1" && saved.run_id === r.window.run_id && saved.phase === "source_ready" && saved.via === "post" && saved.outcome === "confirmed" && saved.operation === "create_task" && saved.request_key === canonical.create_request_key && verifyReadResponse("POST", "/api/v1/tasks", saved.http_status, saved.response) && saved.response.task_id === canonical.task_id && saved.response.source_task_id === canonical.source_task_id && saved.response.request_key === canonical.create_request_key, "M2_BINDING");
        }
        check("admission");
        const operator = await contextFor("operator");
        check("operator_identity");
        if (phase === "source_ready") {
            const config = await read<DTO["ConfigRead"]>(operator, `/api/v1/config?shop_id=${r.source.shop_id}`);
            requireM2(config.shop_id === r.source.shop_id && config.config.approval_ttl_seconds === 900 && config.config.source_mode === "woocommerce_test" && config.config.commerce_source?.creation_enabled === true && config.config.commerce_source.source_config_version === r.source.source_config_version);
            await operator.goto("/tasks");
            await operator.locator('[data-control="B10"]').click();
            await operator.getByLabel("当前operator店铺").selectOption(r.source.shop_id);
            await operator.getByRole("button", { name: "使用自然语言请求草稿", exact: true }).click();
            const text = "分析库存 L=3 R=7 S=2";
            await operator.getByLabel("自然语言请求草稿", { exact: true }).fill(text);
            const pending = operator.waitForResponse((response) => response.url() === r.window.api_origin + "/api/v1/tasks/preflight" && response.request().method() === "POST");
            await operator.getByRole("button", { name: "检查草稿与参数", exact: true }).click();
            const response = await pending, preflightBytes = await response.body();
            requireM2(preflightBytes.length <= 2 * 1024 * 1024 && response.headers()["content-type"]?.toLowerCase().startsWith("application/json"));
            const preflight = privateJson(utf8(preflightBytes)) as WooN01Response;
            requireM2(validN01Response(response.status(), preflight) && n01MatchesInput(preflight, { schema_version: "p3-web-v1", source_mode: "woocommerce_test", shop_id: r.source.shop_id, source_config_version: r.source.source_config_version, text }) && preflight.preflight.status === "ready" && utc(preflight.preflight.window.start) === utc(r.source.window.start) && utc(preflight.preflight.window.end) === utc(r.source.window.end));
            await operator.getByRole("heading", { name: "草稿参数与来源", exact: true }).waitFor();
            check("woo_n01");
            requireM2(await operator.locator('dialog [data-control="B01"]').isDisabled());
            await operator.locator('[data-control="B35"]').click();
            await operator.locator('dialog [data-control="B01"]').click();
            const created = await actualWrite(operator, "create_task", "/api/v1/tasks", () => operator.getByRole("button", { name: "明确提交本次请求", exact: true }).click());
            check("explicit_create");
            const original = created.result as DTO["CreateTaskReceipt"];
            let task = await read<DTO["TaskRead"]>(operator, `/api/v1/tasks/${original.task_id}`);
            while (task.task.state === "queued" || task.task.state === "analyzing") {
                guard();
                await operator.waitForTimeout(500);
                task = await read(operator, `/api/v1/tasks/${original.task_id}`);
            }
            requireM2(task.task.task_id === original.task_id && task.task.shop_id === r.window.shop_id && task.task.state === "awaiting_approval" && task.source?.source_task_id === original.source_task_id && task.approval_id && task.current_plan_id, "M2_BINDING");
            const report = await read<DTO["ReportRead"]>(operator, `/api/v1/tasks/${original.task_id}/report`);
            requireM2(report.task_id === original.task_id && report.source.source_task_id === original.source_task_id, "M2_BINDING");
            const plans = await read<DTO["PlanList"]>(operator, `/api/v1/tasks/${original.task_id}/plans`);
            requireM2(plans.current_plan_version !== null);
            const plan = await read<DTO["PlanRead"]>(operator, `/api/v1/tasks/${original.task_id}/plans/${plans.current_plan_version}`);
            bindReport(report, gold, r);
            bindPlan(plan.plan, report, gold, r.source.source_config_version);
            requireM2(task.current_plan_id === plan.plan.plan_id && task.source?.facts_hash === report.source.facts_hash);
            check("source_gold");
            await operator.goto(`/tasks/${original.task_id}/report`);
            await operator.locator(".fact-row").nth(3).waitFor();
            requireM2(await operator.locator(".fact-row").count() === 4 && (await operator.locator("main").innerText()).includes("Woo 测试店（只读）"));
            const approver = await contextFor("approver"), approval = await read<DTO["ApprovalRead"]>(approver, `/api/v1/approvals/${task.approval_id}`);
            requireM2(approval.approval.status === "pending" && approval.approval.can_decide && approval.approval.plan_id === plan.plan.plan_id && approval.approval.plan_hash === plan.plan.plan_hash && approval.approval.plan_version === plan.plan.plan_version && approval.approval.task_id === original.task_id && approval.nonce !== null && utc(approval.approval.expires_at) > utc(approval.server_time));
            bindPlan(approval.plan, report, gold, r.source.source_config_version);
            check("pending_approval_readonly");
            const taskRef = write("source-task-read.private.json", task), reportRef = write("source-report-read.private.json", report), planRef = write("source-plan-read.private.json", plan), approvalRef = write("source-approval-read.private.json", approval);
            write("source-observed.private.json", { schema_version: "p5-m2-source-observed-v1", run_id: r.window.run_id, source_sha: r.window.source_sha, source_tree: r.window.source_tree, observed_at_utc: new Date().toISOString(), organization_id: r.window.organization_id, shop_id: r.window.shop_id, operator_principal_id: r.accounts.operator.expected_principal_id, approver_principal_id: r.accounts.approver.expected_principal_id, create_request_key: original.request_key, task_id: original.task_id, source_task_id: original.source_task_id, report_id: report.source.report_id, snapshot_id: report.source.snapshot_id, facts_hash: report.source.facts_hash, plan_id: plan.plan.plan_id, plan_version: plan.plan.plan_version, plan_hash: plan.plan.plan_hash, approval_id: task.approval_id, expires_at: approval.approval.expires_at, required_assumption_keys: keysFor(gold), create_request_ref: artifact("source-create-request.private.json"), create_receipt_ref: artifact("source-create-receipt.private.json"), task_read_ref: taskRef, report_read_ref: reportRef, plan_read_ref: planRef, approval_read_ref: approvalRef });
        }
        else {
            const canonical = r.facts.canonical_source!;
            const task = await read<DTO["TaskRead"]>(operator, `/api/v1/tasks/${canonical.task_id}`), report = await read<DTO["ReportRead"]>(operator, `/api/v1/tasks/${canonical.task_id}/report`), plan = await read<DTO["PlanRead"]>(operator, `/api/v1/tasks/${canonical.task_id}/plans/${canonical.plan_version}`);
            requireM2(task.task.task_id === canonical.task_id && report.task_id === canonical.task_id && task.task.state === "awaiting_approval" && task.task.shop_id === r.window.shop_id && task.approval_id === canonical.approval_id && task.current_plan_id === canonical.plan_id && report.source.report_id === canonical.report_id && report.source.snapshot_id === canonical.snapshot_id && report.source.facts_hash === canonical.facts_hash && report.source.source_task_id === canonical.source_task_id && plan.plan.plan_id === canonical.plan_id && plan.plan.plan_hash === canonical.plan_hash && plan.plan.plan_version === canonical.plan_version && utc(plan.plan.expires_at) === utc(canonical.expires_at));
            bindReport(report, gold, r);
            bindPlan(plan.plan, report, gold, r.source.source_config_version);
            write("restored-before-task-read.private.json", task);
            write("restored-before-report-read.private.json", report);
            write("restored-before-plan-read.private.json", plan);
            const approver = await contextFor("approver");
            let approval = await read<DTO["ApprovalRead"]>(approver, `/api/v1/approvals/${canonical.approval_id}`);
            requireM2(approval.approval.task_id === canonical.task_id && approval.approval.status === "pending" && approval.approval.can_decide && utc(approval.approval.expires_at) === utc(canonical.expires_at) && approval.approval.plan_hash === canonical.plan_hash && approval.approval.plan_version === canonical.plan_version && sameSet(canonical.required_assumption_keys, keysFor(gold)));
            bindPlan(approval.plan, report, gold, r.source.source_config_version);
            const before = write("restored-before-approval-read.private.json", approval);
            check("restored_binding");
            await approver.goto(`/approvals/${canonical.approval_id}`);
            await approver.getByRole("table", { name: "完整审批清单" }).locator(".fact-row").nth(3).waitFor();
            requireM2(await approver.locator(".fact-row").count() === 4 && await approver.locator('input[type="checkbox"]:checked').count() === 0 && await approver.locator('[data-control="B02"]').isDisabled() && await approver.locator('input[type="checkbox"]').count() === 4);
            for (const key of keysFor(gold)) {
                const choices = await approver.locator("label.assumption-option").all();
                const matches = [];
                for (const choice of choices)
                    if ((await choice.innerText()).trim().startsWith(key + " · "))
                        matches.push(choice);
                requireM2(matches.length === 1, "M2_BINDING");
                await matches[0].getByRole("checkbox").check();
            }
            await approver.locator('[data-control="B04"]').click();
            await approver.getByRole("button", { name: "确认并准备原请求", exact: true }).click();
            approval = await read(approver, `/api/v1/approvals/${canonical.approval_id}`);
            mutationAdmission(r.window, Date.now(), approval.approval.expires_at);
            const path = `/api/v1/approvals/${canonical.approval_id}/decision`, decision = await actualWrite(approver, "decision", path, () => approver.getByRole("button", { name: "明确提交本次请求", exact: true }).click(), approval.approval.expires_at);
            const accepted = decision.result as DTO["DecisionReceipt"];
            requireM2(accepted.decided_by === r.accounts.approver.expected_principal_id && accepted.task_id === canonical.task_id && accepted.approval_id === canonical.approval_id && accepted.plan_id === canonical.plan_id && accepted.plan_version === canonical.plan_version && accepted.plan_hash === canonical.plan_hash && accepted.action === "approve_with_assumptions" && sameSet(accepted.acknowledged_assumption_keys, keysFor(gold)), "M2_BINDING");
            check("explicit_decision");
            const replays: FileRef[] = [];
            for (let index = 1; index <= 10; index++) {
                const current = await read<DTO["ApprovalRead"]>(approver, `/api/v1/approvals/${canonical.approval_id}`);
                guard();
                r.verifyLive();
                mutationAdmission(r.window, Date.now(), current.approval.expires_at);
                const session = await read<DTO["SessionRead"]>(approver, "/api/v1/auth/session");
                const originalBytes = r.files.bytes("restored-decision-request.private.json").toString("utf8");
                requireM2(originalBytes === decision.raw, "M2_INPUT_CHANGED");
                const response = await approver.request.post(r.window.api_origin + path, { data: originalBytes, headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token, Origin: r.window.web_origin }, timeout: 10000, maxRedirects: 0 }).catch(() => null);
                const file = `restored-replay-${String(index).padStart(2, "0")}.private.json`;
                let body: unknown = null;
                try {
                    const bytes = response ? await response.body() : null;
                    requireM2(bytes === null || bytes.length <= 2 * 1024 * 1024);
                    body = bytes && response?.headers()["content-type"]?.toLowerCase().startsWith("application/json") ? privateJson(utf8(bytes)) : null;
                }
                catch {
                    body = null;
                }
                const classified = classifyM2Post("decision", decision.input, path, response?.status() ?? null, body);
                const replay = classified.result as DTO["DecisionReceipt"] | null;
                const ok = classified.outcome === "confirmed" && replay !== null && replay.duplicate === true && sameDecision(replay, accepted);
                const rejected = classified.outcome === "rejected";
                replays.push(write(file, { schema_version: "p5-m2-receipt-v1", run_id: r.window.run_id, phase, operation: "decision", request_key: accepted.request_key, via: "post", http_status: response?.status() ?? null, outcome: ok ? "confirmed" : rejected ? "rejected" : "unknown", response: classified.value, error_code: ok ? null : rejected ? "M2_WRITE_REJECTED" : "M2_WRITE_UNKNOWN" }));
                if (rejected)
                    fail("M2_WRITE_REJECTED");
                if (!ok)
                    await unknownLookup(approver, "decision", accepted.request_key);
            }
            check("ten_original_byte_replays");
            let after = await read<DTO["TaskRead"]>(approver, `/api/v1/tasks/${canonical.task_id}`);
            while (["awaiting_approval", "executing"].includes(after.task.state)) {
                guard();
                await approver.waitForTimeout(500);
                after = await read(approver, `/api/v1/tasks/${canonical.task_id}`);
            }
            requireM2(after.task.state === "completed" && after.execution_id && after.visible_item_ids.length === 4 && new Set(after.visible_item_ids).size === 4, "M2_EXECUTION_REJECTED");
            const execution = await read<DTO["ExecutionRead"]>(approver, `/api/v1/tasks/${canonical.task_id}/execution`);
            requireM2(execution.execution_id === after.execution_id && execution.task_id === canonical.task_id && execution.plan_id === canonical.plan_id && execution.approval_id === canonical.approval_id && execution.status === "completed" && sameSet(execution.item_ids, after.visible_item_ids));
            const items: DTO["ItemSummary"][] = [];
            for (const id of execution.item_ids) {
                const item = await read<DTO["ItemRead"]>(approver, `/api/v1/replenishment-items/${id}`);
                const expected = gold.facts.find((f) => f.sku_key === item.item.sku_key);
                requireM2(expected && item.item.item_id === id && item.item.shop_id === r.window.shop_id && item.item.stock_pool_key === expected.stock_pool_key && item.item.quantity === expected.suggested_units && item.item.state === "open", "M2_EXECUTION_REJECTED");
                items.push(item.item);
            }
            requireM2(new Set(items.map((i) => i.sku_key)).size === 4 && items.reduce((n, i) => n + i.quantity, 0) === 219);
            await approver.goto(`/tasks/${canonical.task_id}`);
            await approver.locator(`[data-task-id="${canonical.task_id}"]`).waitFor();
            await approver.getByText("Worker 执行回执", { exact: true }).waitFor();
            requireM2(await approver.locator('[data-control="B25"]').count() === 4, "M2_EXECUTION_REJECTED");
            check("execution_readback");
            const afterRef = write("restored-after-task-read.private.json", after), executionRef = write("restored-execution-read.private.json", execution);
            write("restored-observed.private.json", { schema_version: "p5-m2-restored-observed-v1", run_id: r.window.run_id, source_sha: r.window.source_sha, source_tree: r.window.source_tree, observed_at_utc: new Date().toISOString(), organization_id: r.window.organization_id, shop_id: r.window.shop_id, task_id: canonical.task_id, source_task_id: canonical.source_task_id, report_id: canonical.report_id, snapshot_id: canonical.snapshot_id, facts_hash: canonical.facts_hash, plan_id: canonical.plan_id, plan_version: canonical.plan_version, plan_hash: canonical.plan_hash, approval_id: canonical.approval_id, expires_at: canonical.expires_at, decision_request_key: accepted.request_key, execution_id: execution.execution_id, item_ids: execution.item_ids, total_quantity: 219, decision_request_ref: artifact("restored-decision-request.private.json"), decision_receipt_ref: artifact("restored-decision-receipt.private.json"), before_approval_read_ref: before, after_task_read_ref: afterRef, execution_read_ref: executionRef, replay_receipt_refs: replays });
        }
        guard();
        requireM2(checks.every((check) => check.outcome === "passed"), "M2_CONSUMER_FAILED");
        outcome = "passed";
    }
    catch (error) {
        outcome = unknown ? "unknown" : "failed";
        const interrupted = checks.find((c) => c.outcome === "not_run");
        if (interrupted)
            interrupted.outcome = "failed";
        errorCode = error instanceof Error && safeErrorCodes.has(error.message) ? error.message : "M2_CONSUMER_FAILED";
    }
    finally {
        for (const context of contexts) {
            for (const page of context.pages())
                await page.goto("about:blank", { timeout: 2000 }).catch(() => { });
            await context.close().catch(() => { outcome = unknown ? "unknown" : "failed"; errorCode = "M2_CONTEXT_CLOSE_FAILED"; });
        }
        r.files.write(`${prefix}-results.safe.json`, { schema_version: "p5-m2-consumer-result-v1", run_id: r.window.run_id, source_sha: r.window.source_sha, source_tree: r.window.source_tree, phase, logical_outcome: outcome, started_at_utc: started, finished_at_utc: new Date().toISOString(), checks, artifact_refs: artifacts, error_code: errorCode }, r.consumer.allowed_output_files);
    }
    requireM2(outcome === "passed", errorCode ?? "M2_CONSUMER_FAILED");
}
