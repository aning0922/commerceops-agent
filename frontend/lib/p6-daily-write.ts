import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import spec from "./p6-daily-s3-openapi.generated.json" with { type: "json" };
import type { components } from "./p6-daily-s3-types.generated";
import type { FetchTransport } from "./p3-transport";

type DTO = components["schemas"];
export type DailyInput = DTO["CreateDailyInput"];
export type QuestionInput = DTO["QuestionInput"];
export type Prepared = { kind: "report"; input: DailyInput } | { kind: "question"; shop: string; parent: string; input: QuestionInput };
export type Receipt = DTO["CreationReceiptRead"]["receipt"];
const defs = JSON.parse(JSON.stringify(spec.components.schemas).replaceAll("#/components/schemas/", "#/$defs/"));
const ajv = new Ajv2020({ strict: true, coerceTypes: false, useDefaults: false, removeAdditional: false });
addFormats(ajv);
const valid = Object.fromEntries(["CreateDailyInput", "QuestionInput", "AcceptanceRead", "CreationReceiptRead"].map(name => [name, ajv.compile({ ...defs[name], $defs: defs })]));
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function canonical(value: unknown): string {
  if (value === null || typeof value === "string" || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number" && Number.isSafeInteger(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`;
  throw new Error("invalid canonical value");
}
export async function requestHash(p: Prepared): Promise<string> {
  const value = p.kind === "report" ? { shop: p.input.shop_id, day: p.input.business_day, source_version: p.input.source_config_version, rule_version: "daily-rules-v1" } : p.input;
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical(value)));
  return Array.from(new Uint8Array(digest), x => x.toString(16).padStart(2, "0")).join("");
}
export function validatePrepared(p: Prepared): boolean {
  if (!p || (p.kind !== "report" && p.kind !== "question") || !p.input || !uuid.test(p.input.request_key)) return false;
  if (p.kind === "report") return !!valid.CreateDailyInput(p.input) && uuid.test(p.input.shop_id) && p.input.source_config_version.length > 0;
  if (!valid.QuestionInput(p.input) || !uuid.test(p.shop) || !uuid.test(p.parent)) return false;
  const q = p.input.question;
  return q.kind === "data_quality" ? q.metric_key === null && q.finding_id === null : q.kind === "finding_reason" ? q.metric_key === null && q.finding_id !== null : q.metric_key !== null && q.finding_id === null;
}
export class DailyWriteFailure extends Error {
  constructor(readonly code: "UNKNOWN" | "UNAVAILABLE" | "DENIED" | "INVALID" | "STALE") {
    super(({ UNKNOWN: "提交结果待核实；只可查询原请求。", UNAVAILABLE: "原请求暂不可读取；404 不证明未提交，请稍后只读续查。", DENIED: "会话或权限已变化，请重新登录后查询原请求。", INVALID: "请求或回执与冻结内容不一致。", STALE: "页面或会话已变化。" })[code]);
  }
}
const attempts = new Set<string>();
export function dailyWriteApi(options: { origin: URL; transport: FetchTransport; csrf: () => string | null; current: () => boolean; invalidate: () => void }) {
  async function request(method: "GET" | "POST", path: string, body?: string): Promise<unknown> {
    if (!options.current()) throw new DailyWriteFailure("STALE");
    const headers = new Headers();
    if (method === "POST") { const token = options.csrf(); if (!token) throw new DailyWriteFailure("DENIED"); headers.set("content-type", "application/json"); headers.set("X-CSRF-Token", token); }
    let response: Response;
    try { response = await options.transport(new URL(path, options.origin), { method, headers, credentials: "include", cache: "no-store", redirect: "error", ...(body ? { body } : {}) }); }
    catch { throw new DailyWriteFailure(method === "POST" ? "UNKNOWN" : "UNAVAILABLE"); }
    if (!options.current()) throw new DailyWriteFailure(method === "POST" ? "UNKNOWN" : "STALE");
    if (response.status === 401 || response.status === 403) { options.invalidate(); throw new DailyWriteFailure("DENIED"); }
    if (response.status !== (method === "POST" ? 202 : 200) || !response.headers.get("content-type")?.toLowerCase().match(/^application\/json(?:\s*;|$)/)) throw new DailyWriteFailure(method === "POST" ? "UNKNOWN" : "UNAVAILABLE");
    let data: unknown; try { data = await response.json(); } catch { throw new DailyWriteFailure(method === "POST" ? "UNKNOWN" : "UNAVAILABLE"); }
    if (!options.current()) throw new DailyWriteFailure(method === "POST" ? "UNKNOWN" : "STALE");
    return data;
  }
  return {
    async send(p: Prepared): Promise<void> {
      if (!validatePrepared(p)) throw new DailyWriteFailure("INVALID");
      const attempt = `${p.kind}:${p.input.request_key}`;
      if (attempts.has(attempt)) throw new DailyWriteFailure("UNKNOWN");
      attempts.add(attempt);
      const path = p.kind === "report" ? "/api/v1/daily-reports" : `/api/v1/daily-reports/${p.parent}/questions`;
      const data = await request("POST", path, JSON.stringify(p.input));
      if (!valid.AcceptanceRead(data)) throw new DailyWriteFailure("UNKNOWN");
      // An acceptance only contains an ID; the original-key receipt binds the full request.
    },
    async receipt(p: Prepared): Promise<Receipt> {
      if (!validatePrepared(p)) throw new DailyWriteFailure("INVALID");
      const q = new URLSearchParams({ shop_id: p.kind === "report" ? p.input.shop_id : p.shop });
      if (p.kind === "question") q.set("report_id", p.input.report_id);
      const path = p.kind === "report" ? `/api/v1/daily-reports/requests/${p.input.request_key}` : `/api/v1/daily-reports/${p.parent}/questions/requests/${p.input.request_key}`;
      const data = await request("GET", `${path}?${q}`);
      if (!valid.CreationReceiptRead(data)) throw new DailyWriteFailure("INVALID");
      const r = (data as DTO["CreationReceiptRead"]).receipt;
      const hash = await requestHash(p);
      if (!options.current()) throw new DailyWriteFailure("STALE");
      if (r.request_key !== p.input.request_key || r.shop_id !== (p.kind === "report" ? p.input.shop_id : p.shop) || r.request_hash !== hash) throw new DailyWriteFailure("INVALID");
      if (p.kind === "report") {
        if (r.operation !== "daily_report.create" || r.source_config_version !== p.input.source_config_version || p.input.business_day !== null && r.business_day !== p.input.business_day) throw new DailyWriteFailure("INVALID");
      } else if (r.operation !== "daily_question.create" || r.parent_task_id !== p.parent || r.report_id !== p.input.report_id || r.snapshot_id !== p.input.snapshot_id || r.content_hash !== p.input.content_hash || r.facts_hash !== p.input.facts_hash || canonical(r.question) !== canonical(p.input.question)) throw new DailyWriteFailure("INVALID");
      return r;
    },
  };
}
