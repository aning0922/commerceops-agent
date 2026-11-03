import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import spec from "./p6-inquiry-openapi.generated.json" with { type: "json" };
import type { components } from "./p6-inquiry-types.generated";
import type { FetchTransport } from "./p3-transport";
type Schema = components["schemas"];
export type InquiryInput = Schema["CreateInquiry"];
export type InquiryReceipt = Schema["InquiryReceipt"];
export type InquiryRead = Schema["InquiryRead"];
export type InquiryBinding = { key: string; shop: string; receipt: InquiryReceipt | null; contextReport?: string | null };
const defs = JSON.parse(JSON.stringify(spec.components.schemas).replaceAll("#/components/schemas/", "#/$defs/"));
const ajv = new Ajv2020({ strict: true, coerceTypes: false, useDefaults: false, removeAdditional: false });
addFormats(ajv);
const validators = Object.fromEntries(["CreateInquiry", "InquiryReceipt", "InquiryRead", "InquiryError"].map(name =>
  [name, ajv.compile({ ...defs[name], $defs: defs })]));
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const safeNumbers = (value: unknown): boolean => typeof value === "number" ? Number.isSafeInteger(value) :
  Array.isArray(value) ? value.every(safeNumbers) : value !== null && typeof value === "object" ? Object.values(value).every(safeNumbers) : true;
const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();
const validEnvelope = (value: InquiryReceipt) => value.schema_version === "p6-inquiry-web-v1" &&
  value.identity_mode === "session" && value.source_mode === "mock" && value.evidence_mode === "offline_stub" &&
  Date.parse(value.source_domain.start) < Date.parse(value.source_domain.end);
export function validInquiryRead(value: unknown): value is InquiryRead {
  if (!safeNumbers(value) || !validators.InquiryRead(value)) return false;
  try {
    const read = value as InquiryRead;
    if (!validEnvelope(read) || read.data_label !== "本地演示数据 / 离线模型替身") return false;
    const result = read.result;
    if (!result) return read.answer === null && read.state !== "completed";
    if ((read.state !== "completed" && read.state !== "failed") || typeof read.answer !== "string" || result.evidence_mode !== "offline_stub" ||
        result.workflow_version !== "p6-readonly-inquiry-v1" || result.traces.length !== result.tool_calls ||
        new Set(result.traces.map(x => x.tool_call_id)).size !== result.traces.length) return false;
    if (read.state === "failed" && (result.status === "complete" || result.status === "clarify" ||
        result.results.length || result.evidence_refs.length || result.claims.length || result.clarification_options.length)) return false;
    const ids = new Set(result.traces.map(x => x.tool_call_id));
    const facts = result.results.flatMap(x => x.facts);
    const refs = new Set(facts.map(x => x.evidence_id));
    if (facts.some(f => facts.some(other => other.evidence_id === f.evidence_id && JSON.stringify(other) !== JSON.stringify(f))) ||
        new Set(result.evidence_refs).size !== result.evidence_refs.length ||
        result.results.some(x => !ids.has(x.tool_call_id) || x.shop_id !== read.shop_id || x.source_binding !== read.source_binding ||
          x.report_id !== null && typeof x.report_id !== "string" ||
          !x.complete || x.windows.some(w => Date.parse(w.start) >= Date.parse(w.end)) || x.products.some(p => !x.sku_keys.includes(p.sku_key)) ||
          x.facts.some(f => f.sku_key === null || !x.sku_keys.includes(f.sku_key) ||
            f.value !== null && !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(f.value) ||
            ["sold_units", "order_net", "order_average", "refund_cohort"].includes(f.metric) && (f.window === null || f.currency === null) ||
            f.window !== null && !x.windows.some(w => w.start === f.window!.start && w.end === f.window!.end)))) return false;
    if (result.status !== "complete" && (result.results.length || result.evidence_refs.length || result.claims.length)) return false;
    if (result.status !== "clarify" && result.clarification_options.length) return false;
    if (result.status === "complete") {
      const claimed = new Set(result.claims.flatMap(claim => claim.refs));
      if (!result.evidence_refs.length || result.evidence_refs.some(x => !refs.has(x) || !claimed.has(x)) ||
          [...claimed].some(x => !result.evidence_refs.includes(x))) return false;
      for (const claim of result.claims) {
        if (claim.refs.length !== (claim.kind === "fact" ? 1 : 2)) return false;
        if (claim.kind === "compare") {
          const first = facts.find(f => f.evidence_id === claim.refs[0]);
          const second = facts.find(f => f.evidence_id === claim.refs[1]);
          if (!first?.window || !second?.window || first.metric !== second.metric || first.sku_key !== second.sku_key ||
              first.currency !== second.currency || first.unit !== second.unit ||
              Math.min(Date.parse(first.window.end), Date.parse(second.window.end)) > Math.max(Date.parse(first.window.start), Date.parse(second.window.start))) return false;
        }
      }
    }
    return true;
  } catch { return false; }
}
export function inquiryBoundToRequest(value: InquiryRead, expected: InquiryBinding): boolean {
  if (!same(value.request_key, expected.key) || !same(value.shop_id, expected.shop)) return false;
  if (expected.receipt && (!same(value.task_id, expected.receipt.task_id) || value.source_binding !== expected.receipt.source_binding ||
      value.source_domain.start !== expected.receipt.source_domain.start || value.source_domain.end !== expected.receipt.source_domain.end)) return false;
  const contextReport = expected.contextReport;
  return contextReport === undefined || !value.result?.results.some(result =>
    result.report_id !== null && (contextReport === null || !same(result.report_id, contextReport)));
}
export class InquiryFailure extends Error {
  constructor(readonly code: "INVALID_REQUEST" | "INVALID_RESPONSE" | "SERVICE_UNAVAILABLE" | "UNKNOWN" | "SESSION_INVALID" | "DENIED" | "NOT_FOUND" | "CONFLICT" | "DISABLED" | "STALE") {
    super(({ INVALID_REQUEST: "请核对问题和店铺。", INVALID_RESPONSE: "暂时无法安全展示查询结果。",
      SERVICE_UNAVAILABLE: "查询服务暂不可用。", UNKNOWN: "提交结果待核实，请查询原请求回执。",
      SESSION_INVALID: "会话已失效。", DENIED: "当前身份无权访问。", NOT_FOUND: "记录不可访问或不存在。",
      CONFLICT: "请求与原记录冲突，请核对原回执。", DISABLED: "查询当前未启用。", STALE: "当前页面或会话已变化。" })[code]);
  }
}
export function inquiryApi(options: { origin: URL; transport: FetchTransport; csrf: () => string | null;
  sessionCurrent: () => boolean; viewCurrent: () => boolean; invalidate: () => void }) {
  const current = () => options.sessionCurrent() && options.viewCurrent();
  async function request(method: "GET" | "POST", path: string, body?: string): Promise<unknown> {
    if (!current()) throw new InquiryFailure("STALE");
    const headers = new Headers();
    if (method === "POST") {
      const csrf = options.csrf();
      if (!csrf) throw new InquiryFailure("SESSION_INVALID");
      headers.set("Content-Type", "application/json"); headers.set("X-CSRF-Token", csrf);
    }
    let response: Response;
    try { response = await options.transport(new URL(path, options.origin), { method, headers, credentials: "include", cache: "no-store", redirect: "error", ...(body === undefined ? {} : { body }) }); }
    catch { throw new InquiryFailure(method === "POST" ? "UNKNOWN" : "SERVICE_UNAVAILABLE"); }
    if (!current()) throw new InquiryFailure(method === "POST" ? "UNKNOWN" : "STALE");
    if (response.status === 401 || response.status === 403) { options.invalidate(); throw new InquiryFailure(response.status === 401 ? "SESSION_INVALID" : "DENIED"); }
    if (method === "POST" && response.status >= 500) throw new InquiryFailure("UNKNOWN");
    if (response.ok && response.status !== (method === "POST" ? 202 : 200)) throw new InquiryFailure(method === "POST" ? "UNKNOWN" : "INVALID_RESPONSE");
    if (!response.headers.get("content-type")?.toLowerCase().match(/^application\/json(?:\s*;|$)/)) throw new InquiryFailure(method === "POST" && response.ok ? "UNKNOWN" : "INVALID_RESPONSE");
    let value: unknown; try { value = await response.json(); } catch { throw new InquiryFailure(method === "POST" && response.ok ? "UNKNOWN" : "INVALID_RESPONSE"); }
    if (!current()) throw new InquiryFailure(method === "POST" ? "UNKNOWN" : "STALE");
    if (!response.ok) {
      if (!validators.InquiryError(value)) throw new InquiryFailure("INVALID_RESPONSE");
      const error = value as Schema["InquiryError"];
      if (error.schema_version !== "p6-inquiry-web-v1" || error.message !== "无法处理此查询，请核对当前权限、输入或原请求回执。") throw new InquiryFailure("INVALID_RESPONSE");
      if (error.code === "INQUIRY_DISABLED" && response.status === 409) throw new InquiryFailure("DISABLED");
      if (error.code === "IDEMPOTENCY_CONFLICT" && response.status === 409) throw new InquiryFailure("CONFLICT");
      if (error.code === "RESOURCE_NOT_FOUND" && response.status === 404) throw new InquiryFailure("NOT_FOUND");
      if (["INVALID_REQUEST", "INVALID_JSON", "UNSUPPORTED_MEDIA_TYPE"].includes(error.code) && [400, 415, 422].includes(response.status)) throw new InquiryFailure("INVALID_REQUEST");
      throw new InquiryFailure(method === "POST" ? "UNKNOWN" : "SERVICE_UNAVAILABLE");
    }
    return value;
  }
  return {
    prepare(input: InquiryInput) {
      if (!validators.CreateInquiry(input) || !input.question.trim()) throw new InquiryFailure("INVALID_REQUEST");
      const requestKey = input.request_key, shopId = input.shop_id;
      const frozen = JSON.stringify({ schema_version: input.schema_version, shop_id: input.shop_id, question: input.question,
        context_report_id: input.context_report_id, request_key: input.request_key });
      let attempted = false;
      return { requestKey, async send(): Promise<InquiryReceipt> {
        if (attempted) throw new InquiryFailure("UNKNOWN");
        attempted = true;
        const value = await request("POST", "/api/v1/readonly-inquiries", frozen);
        if (!safeNumbers(value) || !validators.InquiryReceipt(value) || !validEnvelope(value as InquiryReceipt) ||
            !same((value as InquiryReceipt).request_key, requestKey) || !same((value as InquiryReceipt).shop_id, shopId)) throw new InquiryFailure("UNKNOWN");
        return value as InquiryReceipt;
      } };
    },
    async read(kind: "task" | "request", id: string): Promise<InquiryRead> {
      if (!uuid.test(id)) throw new InquiryFailure("INVALID_REQUEST");
      const suffix = kind === "request" ? `/requests/${id}` : `/${id}`;
      const value = await request("GET", `/api/v1/readonly-inquiries${suffix}`);
      if (!validInquiryRead(value) || !same(kind === "task" ? value.task_id : value.request_key, id)) throw new InquiryFailure("INVALID_RESPONSE");
      return value;
    },
  };
}
