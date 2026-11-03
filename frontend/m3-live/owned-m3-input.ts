// Private seed values are parsed only inside the explicitly registered live window.
import { closeSync, constants, fsyncSync, lstatSync, openSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { assertOwnedBuild, assertOwnedListener, ownedEndpoints, readOwnedListener } from "../../tests/e2e/web/owned-listeners";
export type Account = { login: string; password: string; home_path: "/tasks" | "/access"; principal_id: string; shop_roles: Record<string, ("operator" | "approver")[]> };
export type Seed = { organization_id: string; daily_shop_id: string; inquiry_shop_id: string; owner: Account; reviewer: Account; unassigned: Account; outside: Account; daily: { day: string; timezone: "Asia/Taipei"; source_version: string; metric_key: string; minimum_evidence: number }; inquiry: { question: string; sku: string; expected_value: string }; copy: { shop_id: string; registry_id: string; registry_digest: string; product_source_id: string; query_ref: string; reviewer_id: string }; max_poll: number; acknowledge_lost_response: true };
export type Window = { source_sha: string; build_id: string; web_origin: string; api_origin: string; web_pid: number; api_pid: number; stop_at_utc: string };
export const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export function validRoleMap(value: unknown, shops: string[]): value is Record<string, ("operator" | "approver")[]> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const roles = value as Record<string, unknown>;
  return Object.keys(roles).sort().join(",") === [...shops].sort().join(",") && shops.every(shop => {
    const items = roles[shop]; return Array.isArray(items) && items.every(x => x === "operator" || x === "approver") && new Set(items).size === items.length;
  });
}
export function validShopScopes(s: Seed): boolean {
  if (!s || !s.copy || !uuid.test(s.daily_shop_id) || !uuid.test(s.inquiry_shop_id) || s.daily_shop_id === s.inquiry_shop_id || s.copy.shop_id !== s.inquiry_shop_id) return false;
  const shops = [s.daily_shop_id, s.inquiry_shop_id];
  if (![s.owner, s.reviewer, s.unassigned, s.outside].every(a => a && validRoleMap(a.shop_roles, shops))) return false;
  return s.owner.shop_roles[s.daily_shop_id].includes("operator") && s.owner.shop_roles[s.inquiry_shop_id].includes("operator") &&
    s.reviewer.shop_roles[s.copy.shop_id].includes("approver") && s.unassigned.shop_roles[s.copy.shop_id].includes("approver") &&
    s.outside.home_path === "/tasks" && s.outside.shop_roles[s.daily_shop_id].includes("operator") && s.outside.shop_roles[s.copy.shop_id].length === 0;
}
export function loadOwned(): { window: Window; seed: Seed; directory: string; stop: number; record: (event: object) => void; verify: () => void; close: () => void } {
  const directory = resolve(process.env.COMMERCEOPS_M3_PRIVATE_DIR ?? "");
  const dir = lstatSync(directory); if (!dir.isDirectory() || dir.isSymbolicLink() || (dir.mode & 0o777) !== 0o700 || dir.uid !== process.getuid?.()) throw new Error("Private directory must be owned 0700");
  function read(name: string): unknown { const path = resolve(directory, name), stat = lstatSync(path); if (!stat.isFile() || stat.isSymbolicLink() || (stat.mode & 0o777) !== 0o600 || stat.uid !== process.getuid?.()) throw new Error("Private input must be owned 0600"); return JSON.parse(readFileSync(path, "utf8")); }
  const w = read("window.json") as Window, s = read("m3-browser-seed.json") as Seed;
  const root = resolve(import.meta.dirname, "../..");
  const listeners = ownedEndpoints(w, process.env.COMMERCEOPS_M3_LIVE_WEB_URL);
  if (w.web_origin === w.api_origin || w.web_pid === w.api_pid) throw new Error("Distinct owned Web and API listeners required");
  assertOwnedBuild(w.build_id, readFileSync(resolve(root, "frontend/.next/BUILD_ID"), "utf8"));
  const head = execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
  const stop = Date.parse(w.stop_at_utc);
  if (head !== w.source_sha || !Number.isFinite(stop) || Date.now() + 120000 >= stop) throw new Error("Owned source or window mismatch");
  for (const { port, pid } of listeners) assertOwnedListener(readOwnedListener(port), pid);
  const account = (a: Account) => !!a && typeof a.login === "string" && !!a.login && typeof a.password === "string" && !!a.password && uuid.test(a.principal_id) && ["/tasks", "/access"].includes(a.home_path) && validRoleMap(a.shop_roles, [s.daily_shop_id, s.inquiry_shop_id]);
  if (!s || s.acknowledge_lost_response !== true || !uuid.test(s.organization_id) || !validShopScopes(s) || !account(s.owner) || !account(s.reviewer) || !account(s.unassigned) || !account(s.outside) || new Set([s.owner.principal_id, s.reviewer.principal_id, s.unassigned.principal_id, s.outside.principal_id]).size !== 4 || !s.daily || s.daily.timezone !== "Asia/Taipei" || !/^\d{4}-\d{2}-\d{2}$/.test(s.daily.day) || typeof s.daily.source_version !== "string" || !s.daily.source_version || typeof s.daily.metric_key !== "string" || !s.daily.metric_key || !Number.isSafeInteger(s.daily.minimum_evidence) || s.daily.minimum_evidence < 51 || !s.inquiry || ![s.inquiry.question, s.inquiry.sku, s.inquiry.expected_value].every(x => typeof x === "string" && !!x) || !s.copy || ![s.copy.registry_id, s.copy.product_source_id, s.copy.reviewer_id].every(x => uuid.test(x)) || s.copy.reviewer_id !== s.reviewer.principal_id || !/^[a-f0-9]{64}$/.test(s.copy.registry_digest) || typeof s.copy.query_ref !== "string" || !s.copy.query_ref || !Number.isSafeInteger(s.max_poll) || s.max_poll < 1 || s.max_poll > 30) throw new Error("Private synthetic seed incomplete");
  const verify = () => {
    if (Date.now() + 90000 >= stop || execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim() !== w.source_sha || execFileSync("git", ["status", "--porcelain=v1", "--untracked-files=normal"], { cwd: root, encoding: "utf8" }).trim() !== "") throw new Error("Owned window or source changed");
    assertOwnedBuild(w.build_id, readFileSync(resolve(root, "frontend/.next/BUILD_ID"), "utf8"));
    for (const { port, pid } of listeners) assertOwnedListener(readOwnedListener(port), pid);
  };
  verify();
  const ledger = openSync(resolve(directory, "m3-operations-ledger.jsonl"), constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  const record = (event: object) => { writeFileSync(ledger, JSON.stringify({ at: new Date().toISOString(), ...event }) + "\n", { encoding: "utf8" }); fsyncSync(ledger); };
  record({ event: "window_bound", source_sha: w.source_sha, build_id: w.build_id });
  return { window: w, seed: s, directory, stop, record, verify, close: () => closeSync(ledger) };
}
