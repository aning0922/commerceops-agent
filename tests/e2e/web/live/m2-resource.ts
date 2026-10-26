// Narrow consumer of the reviewed M2 private files; no resource creation or DB access.
import { constants, closeSync, fstatSync, fsyncSync, lstatSync, openSync, readFileSync, readSync, realpathSync, writeFileSync } from "node:fs";
import { resolve, join } from "node:path";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import sourceTemplate from "../../../../docs/contracts/p5-m2-live-source.example.json";
import restoredTemplate from "../../../../docs/contracts/p5-m2-live-restored.example.json";
import { ownedEndpoints, assertOwnedBuild, assertOwnedListener, readOwnedListener } from "../owned-listeners";
export type Phase = "source_ready" | "restored_pending_verified";
export type FileRef = {
    file: string;
    sha256: string;
};
type RF = typeof restoredTemplate.files;
export type M2Window = Omit<RF["window.json"], "phase" | "original_expires_at" | "target_database"> & {
    phase: Phase;
    original_expires_at: string | null;
    target_database: RF["window.json"]["target_database"] | null;
};
export type M2Facts = Omit<RF["m2-facts.private.json"], "canonical_source" | "restore_binding"> & {
    canonical_source: RF["m2-facts.private.json"]["canonical_source"] | null;
    restore_binding: RF["m2-facts.private.json"]["restore_binding"] | null;
};
export type M2Source = RF["m2-source.private.json"];
export type M2Account = RF["web-accounts.json"]["operator"];
export type GoldFact = {
    logical_key: string;
    sku_key: string;
    stock_pool_key: string;
    gross_units: number;
    net_units: number;
    known_refunded_units: number;
    D: {
        numerator: string;
        denominator: string;
    };
    A: number;
    T: number;
    trigger: {
        numerator: string;
        denominator: string;
    };
    suggested_units: number;
    risk: string;
    pool_allocation: string;
    inbound_units: null;
    effective_inbound_units: number;
    inbound_reason: string;
    required_assumptions: string[];
    hard_blocks: string[];
    suggestion_mode: string;
};
export type Golden = {
    schema_version: string;
    rule_version: string;
    shop_id: string;
    business_now: string;
    window: {
        start: string;
        end: string;
    };
    parameters: {
        L: number;
        R: number;
        S: number;
    };
    facts: GoldFact[];
    total_quantity: number;
};
export function fail(code = "M2_INPUT_REJECTED"): never { throw new Error(code); }
export function requireM2(value: unknown, code?: string): asserts value {
    if (!value)
        fail(code);
}
export function utf8(bytes: Buffer): string {
    const text = bytes.toString("utf8");
    requireM2(Buffer.from(text, "utf8").equals(bytes));
    return text;
}
export const digest = (bytes: string | Buffer) => createHash("sha256").update(bytes).digest("hex");
const plain = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
const nonempty = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const sha = (value: unknown, length: number) => typeof value === "string" && new RegExp(`^[a-f0-9]{${length}}$`).test(value) && !/^0+$/.test(value);
const uuid = (value: unknown) => typeof value === "string" && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(value);
export function utc(value: unknown): number {
    requireM2(typeof value === "string" && /(?:Z|[+]00:00)$/.test(value));
    const time = Date.parse(value as string);
    requireM2(Number.isFinite(time));
    return time;
}
// Keep duplicate object keys observable as rejection, including escaped key aliases.
export function privateJson(text: string): unknown {
    try {
        const result: unknown = JSON.parse(text);
        let at = 0;
        const space = () => {
            while (/\s/.test(text[at] ?? "") && at < text.length)
                at++;
        };
        const string = () => {
            const match = /^"(?:[^"\\\u0000-\u001f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"/.exec(text.slice(at));
            if (!match)
                fail();
            at += match[0].length;
            return JSON.parse(match[0]) as string;
        };
        const value = () => {
            space();
            if (text[at] === '"') {
                string();
                return;
            }
            if (text[at] === "{") {
                at++;
                space();
                const keys = new Set<string>();
                if (text[at] === "}") {
                    at++;
                    return;
                }
                for (;;) {
                    space();
                    const key = string();
                    requireM2(!keys.has(key));
                    keys.add(key);
                    space();
                    requireM2(text[at++] === ":");
                    value();
                    space();
                    const end = text[at++];
                    if (end === "}")
                        return;
                    requireM2(end === ",");
                }
            }
            if (text[at] === "[") {
                at++;
                space();
                if (text[at] === "]") {
                    at++;
                    return;
                }
                for (;;) {
                    value();
                    space();
                    const end = text[at++];
                    if (end === "]")
                        return;
                    requireM2(end === ",");
                }
            }
            while (at < text.length && !/[\s,\]}]/.test(text[at]))
                at++;
        };
        value();
        space();
        requireM2(at === text.length);
        return result;
    }
    catch {
        return fail();
    }
}
// Examples define the reviewed closed key sets, never live values or evidence.
export function exactShape(value: unknown, example: unknown): boolean {
    if (example === null)
        return value === null;
    if (Array.isArray(example))
        return Array.isArray(value) && value.length === example.length && value.every((item) => example.some((sample) => exactShape(item, sample)));
    if (plain(example))
        return plain(value) && Object.keys(value).sort().join("\0") === Object.keys(example).sort().join("\0") && Object.keys(example).every((key) => exactShape(value[key], example[key]));
    return typeof value === typeof example && (typeof value === "number" ? Number.isSafeInteger(value) : typeof value === "string" ? nonempty(value) : true);
}
export function admission(window: M2Window, phase: Phase, now: number, starting = false, expires?: string) {
    requireM2(window.phase === phase && window.cleanup_reserve_seconds === 180 && window.consumer_cap_seconds === 240);
    const start = utc(window.started_at_utc), stop = utc(window.stop_at_utc), cs = utc(window.consumer_started_at_utc), ce = utc(window.consumer_stop_at_utc);
    requireM2(start <= cs && cs <= now && now < ce && ce <= cs + 240000 && stop - start <= 3600000 && ce <= stop - 180000, "M2_DEADLINE");
    if (starting)
        requireM2(stop - now >= 420000, "M2_DEADLINE");
    if (phase === "source_ready")
        requireM2(window.original_expires_at === null);
    else {
        const expiry = utc(expires ?? window.original_expires_at);
        requireM2(expiry === utc(window.original_expires_at) && ce <= expiry - 60000 && (!starting || expiry - now >= 300000), "M2_DEADLINE");
    }
}
export function mutationAdmission(window: M2Window, now: number, apiExpiry?: string) {
    admission(window, window.phase, now);
    requireM2(utc(window.consumer_stop_at_utc) - now >= 60000, "M2_DEADLINE");
    // Root ruling: the first source Create has no approval yet. Never interpret null as expiry.
    if (window.phase === "restored_pending_verified")
        requireM2(apiExpiry && utc(apiExpiry) === utc(window.original_expires_at) && utc(apiExpiry) - now >= 60000, "M2_DEADLINE");
}
export class M2Files {
    constructor(readonly directory: string) {
        try {
            const info = lstatSync(directory);
            requireM2(info.isDirectory() && !info.isSymbolicLink() && info.uid === process.getuid?.() && (info.mode & 0o777) === 0o700 && realpathSync(directory) === resolve(directory));
        }
        catch {
            fail();
        }
    }
    name(file: string) { requireM2(/^[a-z0-9][a-z0-9.-]*$/.test(file) && !file.includes("..")); return join(this.directory, file); }
    bytes(file: string): Buffer {
        let fd: number | undefined;
        try {
            fd = openSync(this.name(file), constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
            const info = fstatSync(fd);
            requireM2(info.isFile() && info.uid === process.getuid?.() && (info.mode & 0o777) === 0o600 && info.size <= 4 * 1024 * 1024);
            const buffer = Buffer.alloc(info.size + 1);
            let offset = 0;
            while (offset < buffer.length) {
                const count = readSync(fd, buffer, offset, buffer.length - offset, null);
                if (count === 0)
                    break;
                offset += count;
            }
            requireM2(offset === info.size && fstatSync(fd).size === info.size);
            return buffer.subarray(0, offset);
        }
        catch {
            return fail();
        }
        finally {
            if (fd !== undefined)
                closeSync(fd);
        }
    }
    json(file: string) { return privateJson(utf8(this.bytes(file))); }
    ref(ref: FileRef) { requireM2(exactShape(ref, { file: "x", sha256: "x" }) && sha(ref.sha256, 64)); const bytes = this.bytes(ref.file); requireM2(digest(bytes) === ref.sha256); return privateJson(utf8(bytes)); }
    write(file: string, value: unknown, allowed: readonly string[], raw = false): FileRef {
        requireM2(allowed.includes(file));
        let fd: number | undefined;
        try {
            fd = openSync(this.name(file), constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
            const bytes = raw ? String(value) : JSON.stringify(value, null, 2) + "\n";
            writeFileSync(fd, bytes);
            fsyncSync(fd);
            const parent = openSync(this.directory, constants.O_RDONLY | constants.O_DIRECTORY);
            try {
                fsyncSync(parent);
            }
            finally {
                closeSync(parent);
            }
            requireM2(digest(this.bytes(file)) === digest(bytes));
            return { file, sha256: digest(bytes) };
        }
        catch {
            return fail("M2_OUTPUT_REJECTED");
        }
        finally {
            if (fd !== undefined)
                closeSync(fd);
        }
    }
}
export function validateInputs(input: Record<string, unknown>, phase: Phase, now: number) {
    const template = phase === "source_ready" ? sourceTemplate.files : restoredTemplate.files;
    for (const name of ["window.json", "web-accounts.json", "m2-source.private.json", "m2-facts.private.json", "consumer.private.json"] as const)
        requireM2(exactShape(input[name], template[name]));
    const w = input["window.json"] as M2Window, a = input["web-accounts.json"] as RF["web-accounts.json"], s = input["m2-source.private.json"] as M2Source, f = input["m2-facts.private.json"] as M2Facts, c = input["consumer.private.json"] as RF["consumer.private.json"];
    requireM2(w.owner === "phase5-M2-live" && w.batch === "p5-m2-live" && w.stop_owner === "A" && uuid(w.run_id) && sha(w.source_sha, 40) && sha(w.source_tree, 40) && nonempty(w.build_id));
    for (const name of Object.keys(template).filter((n) => !n.endsWith("results.safe.json"))) {
        const value = input[name] as Record<string, unknown>;
        requireM2(value.schema_version === (template[name as keyof typeof template] as {
            schema_version: string;
        }).schema_version && ["run_id", "source_sha", "source_tree"].every((key) => value[key] === (w as unknown as Record<string, unknown>)[key]));
    }
    requireM2(uuid(w.organization_id) && uuid(w.shop_id) && w.api_origin !== w.web_origin && w.worker_pid > 0 && w.api_pid > 0 && w.web_pid > 0 && new Set([w.worker_pid, w.api_pid, w.web_pid]).size === 3);
    requireM2(w.active_database === (phase === "source_ready" ? "source" : "restored"));
    if (w.target_database)
        requireM2(["project", "database", "volume"].every((key) => w.source_database[key as keyof typeof w.source_database] !== w.target_database![key as keyof typeof w.source_database]));
    requireM2(a.operator.expected_principal_id !== a.approver.expected_principal_id);
    for (const role of ["operator", "approver"] as const) {
        const account = a[role];
        requireM2(uuid(account.expected_principal_id) && account.expected_role === role && account.expected_organization_id === w.organization_id && account.expected_shop_id === w.shop_id);
    }
    requireM2(s.organization_id === w.organization_id && s.shop_id === w.shop_id && uuid(s.binding_id) && s.source_kind === "woocommerce_test" && s.profile === "positive-v1" && s.timezone === "Asia/Shanghai" && s.currency === "CNY" && sha(s.registration_digest, 64) && s.parameters.L === 3 && s.parameters.R === 7 && s.parameters.S === 2);
    const localDay = new Intl.DateTimeFormat("en-CA", { timeZone: s.timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
    requireM2(/^\d{4}-\d{2}-\d{2}$/.test(s.anchor_day) && s.anchor_day <= localDay && utc(s.business_now) === Date.parse(s.anchor_day + "T00:00:00+08:00") && utc(s.window.end) === utc(s.business_now) && utc(s.window.end) - utc(s.window.start) === 7 * 86400000);
    requireM2(s.expected_ref.file === "expected.private.json" && s.golden_ref.file === "analysis-golden.private.json" && s.seed_result_ref.file === "seed-result.private.json");
    // Root's reviewed correction: Playwright grep includes the filename in its full title.
    const fixedArgv = [...template["consumer.private.json"].argv];
    fixedArgv[fixedArgv.length - 1] = fixedArgv.at(-1)!.replace(/^\^/, "");
    requireM2(c.phase === phase && c.cwd === "frontend" && c.retries === 0 && c.cap_seconds === 240 && c.business_revalidation_seconds === 20 && c.exit_and_evidence_reserve_seconds === 40 && c.mutation_reserve_seconds === 60 && c.restored_min_ttl_at_start_seconds === 300 && JSON.stringify(c.argv) === JSON.stringify(fixedArgv) && JSON.stringify(c.allowed_output_files) === JSON.stringify(template["consumer.private.json"].allowed_output_files));
    if (phase === "restored_pending_verified") {
        requireM2(f.canonical_source && f.restore_binding);
        const original = f.canonical_source;
        for (const key of ["create_request_key", "task_id", "source_task_id", "report_id", "snapshot_id", "plan_id", "approval_id"] as const)
            requireM2(uuid(original[key]));
        requireM2(sha(original.facts_hash, 64) && sha(original.plan_hash, 64) && original.plan_version > 0 && original.required_assumption_keys.length === 4 && new Set(original.required_assumption_keys).size === 4);
        requireM2(original.organization_id === w.organization_id && original.shop_id === w.shop_id && original.source_binding_id === s.binding_id && original.source_config_version === s.source_config_version && utc(original.expires_at) === utc(w.original_expires_at) && f.restore_binding.schema_revision === "0018_p5_commerce_sources");
        requireM2(utc(f.restore_binding.source_writers_stopped_at_utc) <= utc(f.restore_binding.source_pg_stopped_at_utc) && utc(f.restore_binding.source_pg_stopped_at_utc) <= utc(f.restore_binding.target_verified_at_utc) && utc(f.restore_binding.target_verified_at_utc) <= now && sha(f.restore_binding.dump_sha256, 64));
    }
    admission(w, phase, now, true);
    return { window: w, accounts: a, source: s, facts: f, consumer: c };
}
export function loadM2(phase: Phase) {
    requireM2(process.env.COMMERCEOPS_WEB_BATCH === "p5-m2-live");
    const root = resolve(__dirname, "../../../.."), files = new M2Files(process.env.COMMERCEOPS_B02_PRIVATE_DIR ?? "");
    const names = ["window.json", "web-accounts.json", "m2-source.private.json", "m2-facts.private.json", "consumer.private.json"];
    const input = validateInputs(Object.fromEntries(names.map((n) => [n, files.json(n)])), phase, Date.now());
    const git = (ref: string) => execFileSync("git", ["rev-parse", ref], { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"], timeout: 3000 }).trim();
    const verifySource = () => {
        requireM2(git("HEAD") === input.window.source_sha && git("HEAD^{tree}") === input.window.source_tree && process.cwd() === join(root, "frontend"));
        const dirty = execFileSync("git", ["status", "--porcelain", "--untracked-files=normal"], { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"], timeout: 3000 });
        requireM2(!dirty.trim(), "M2_INPUT_CHANGED");
        assertOwnedBuild(input.window.build_id, readFileSync(join(root, "frontend/.next/BUILD_ID"), "utf8"));
    };
    const verifyLive = () => {
        verifySource();
        for (const endpoint of ownedEndpoints(input.window, process.env.COMMERCEOPS_LIVE_WEB_URL))
            assertOwnedListener(readOwnedListener(endpoint.port), endpoint.pid);
    };
    verifyLive();
    for (const name of input.consumer.allowed_output_files) {
        try {
            lstatSync(files.name(name));
            fail("M2_OUTPUT_EXISTS");
        }
        catch (error) {
            if ((error as NodeJS.ErrnoException).code !== "ENOENT")
                throw error;
        }
    }
    files.ref(input.window.resource_registration_ref);
    if (input.facts.canonical_source && input.facts.restore_binding) {
        for (const [key, ref] of Object.entries(input.facts.canonical_source))
            if (key.endsWith("_ref"))
                files.ref(ref as FileRef);
        files.ref(input.facts.restore_binding.restore_receipt_ref);
    }
    return { ...input, root, files, verifySource, verifyLive };
}
export function loadGolden(files: M2Files, source: M2Source): Golden {
    const gold = files.ref(source.golden_ref) as Golden;
    const expected = files.ref(source.expected_ref) as {
        schema_version: string;
        shop_id: string;
        business_now: string;
        window: {
            start: string;
            end: string;
        };
        expected: {
            products: {
                product_id: string;
                variant_id: string | null;
                sku_key: string;
                stock_pool_key: string;
            }[];
        };
    };
    const seed = files.ref(source.seed_result_ref) as {
        mapping: {
            products: Record<string, number>;
        };
    };
    requireM2(source.golden_schema_version === "woo-positive-golden-v1" && source.expected_schema_version === "woo-local-expectations-v1" && gold.schema_version === source.golden_schema_version && gold.rule_version === "inventory-rule-v1" && expected.schema_version === source.expected_schema_version);
    for (const value of [gold, expected])
        requireM2(value.shop_id === source.shop_id && utc(value.business_now) === utc(source.business_now) && utc(value.window.start) === utc(source.window.start) && utc(value.window.end) === utc(source.window.end));
    const quantities: Record<string, number> = { simple_a: 100, simple_b: 40, independent_red: 60, independent_blue: 19 };
    requireM2(Array.isArray(gold.facts) && gold.facts.length === 4 && gold.total_quantity === 219 && gold.parameters.L === 3 && gold.parameters.R === 7 && gold.parameters.S === 2 && expected.expected.products.length === 4);
    requireM2(new Set(source.sku_map.map((v) => v.logical_key)).size === 4 && new Set(source.sku_map.map((v) => v.sku_key)).size === 4 && new Set(source.sku_map.map((v) => v.stock_pool_key)).size === 4 && new Set(gold.facts.map((v) => v.logical_key)).size === 4);
    for (const row of source.sku_map) {
        requireM2(Object.hasOwn(quantities, row.logical_key) && /^[1-9][0-9]*$/.test(row.product_id));
        const variation = row.logical_key.startsWith("independent_");
        requireM2(variation ? typeof row.variant_id === "string" && /^[1-9][0-9]*$/.test(row.variant_id) && String(seed.mapping.products.independent_parent) === row.product_id && String(seed.mapping.products[row.logical_key]) === row.variant_id : row.variant_id === null && String(seed.mapping.products[row.logical_key]) === row.product_id);
        const sku = `sku/${source.shop_id}/${row.product_id}/${variation ? "v/" + row.variant_id : "p"}`;
        const pool = `pool/${source.shop_id}/${row.variant_id ?? row.product_id}`;
        requireM2(row.sku_key === sku && row.stock_pool_key === pool);
        const fact = gold.facts.find((v) => v.logical_key === row.logical_key);
        requireM2(fact && fact.sku_key === sku && fact.stock_pool_key === pool && fact.suggested_units === quantities[row.logical_key] && fact.inbound_units === null && fact.effective_inbound_units === 0 && fact.hard_blocks.length === 0 && fact.required_assumptions.length === 1 && fact.required_assumptions[0] === "inbound_unknown_zero:" + sku);
        requireM2(expected.expected.products.filter((v) => v.sku_key === sku && v.stock_pool_key === pool && v.product_id === row.product_id && v.variant_id === row.variant_id).length === 1);
    }
    return gold;
}
