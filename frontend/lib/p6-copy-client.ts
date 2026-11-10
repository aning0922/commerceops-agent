import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import spec from "./p6-copy-openapi.generated.json" with { type: "json" };
import type { components } from "./p6-copy-types.generated";
import type { FetchTransport } from "./p3-transport";
type DTO = components["schemas"];
export type CreateCopy = DTO["CreateCopy"];
export type ReviewCopy = DTO["ReviewCopy"];
export type Candidate = DTO["CandidateResponse"]["data"];
export type Decision = DTO["DecisionResponse"]["data"] | DTO["UnknownDecisionResponse"]["data"];
const defs = JSON.parse(JSON.stringify(spec.components.schemas).replaceAll("#/components/schemas/", "#/$defs/"));
const ajv = new Ajv2020({ strict: true, coerceTypes: false, useDefaults: false, removeAdditional: false }); addFormats(ajv);
const v: Record<string, (value: unknown) => boolean> = Object.fromEntries(["CreateCopy", "ReviewCopy", "CandidateResponse", "UnknownCandidateResponse", "DecisionResponse", "UnknownDecisionResponse"].map(n => [n, ajv.compile({ ...defs[n], $defs: defs })]));
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const numbers = (x: unknown): boolean => typeof x === "number" ? Number.isFinite(x) && (!Number.isInteger(x) || Number.isSafeInteger(x)) : Array.isArray(x) ? x.every(numbers) : x !== null && typeof x === "object" ? Object.values(x).every(numbers) : true;
export function validCandidate(value: unknown): value is DTO["CandidateResponse"] {
  if (!numbers(value) || !v.CandidateResponse(value)) return false;
  const d = (value as DTO["CandidateResponse"]).data, c = d.candidate;
  const scope = c.retrieval.scope;
  if (c.claims.length !== c.retrieval.hits.length + 1 || c.claims[0].kind !== "product_title" ||
      JSON.stringify(c.claims[0].product) !== JSON.stringify(c.product) ||
      c.product.snapshot.scope.shop_id !== scope.shop_id || c.product.snapshot.scope.organization_id !== scope.organization_id ||
      c.claims.slice(1).some((x, i) => x.kind !== "sop_excerpt" || JSON.stringify(x.sop) !== JSON.stringify(c.retrieval.hits[i]))) return false;
  return d.publication_allowed === false && c.publication_allowed === false && c.narrative_mode === "template" && c.model_evidence_mode === "not_used" && c.retrieval.evidence_mode === "synthetic_vector" && c.retrieval.reason === "OK" && c.claims.map(x => x.text).join("\n") === c.text && c.claims.every(x => x.kind === "product_title" ? x.product !== null && x.sop === null && x.product.text === x.product.snapshot.title && x.text === "商品名称：" + x.product.text : x.sop !== null && x.product === null && x.text === "SOP 操作说明：" + x.sop.chunk.text && Array.from(x.sop.chunk.document.body).slice(x.sop.chunk.start, x.sop.chunk.end).join("") === x.sop.chunk.text) && (d.state !== "awaiting_review" || d.source_current) && (d.state !== "source_unavailable" || !d.source_current) && (d.state === "saved") === (d.draft_id !== null);
}
export function mayReview(item: Candidate, principal: string, approvers: readonly string[]): boolean {
  return item.state === "awaiting_review" && item.source_current && item.candidate.reviewer_id === principal && approvers.includes(item.candidate.retrieval.scope.shop_id);
}
export function validCreate(input: CreateCopy): boolean { return !!v.CreateCopy(input) && [input.shop_id, input.registry_id, input.product_source_id, input.reviewer_id, input.request_key].every(x => uuid.test(x)); }
export function validReview(input: ReviewCopy): boolean { return !!v.ReviewCopy(input) && uuid.test(input.request_key) && !!input.reason.trim(); }
export class CopyFailure extends Error { constructor(readonly code: "UNKNOWN" | "UNAVAILABLE" | "INVALID" | "DENIED" | "STALE") { super(({ UNKNOWN: "结果待核实；请只查询原请求键。", UNAVAILABLE: "读取不可用；无法据此断定原请求未提交。", INVALID: "请求或响应无法安全核对。", DENIED: "会话或权限已变化。", STALE: "页面或会话已变化。" })[code]); } }
const attempted = new Set<string>();
export function copyApi(options: { origin: URL; transport: FetchTransport; csrf: () => string | null; current: () => boolean; invalidate: () => void }) {
  async function request(method: "GET" | "POST", path: string, body?: string): Promise<{ status: number; data: unknown }> {
    if (!options.current()) throw new CopyFailure("STALE");
    const headers = new Headers(); if (method === "POST") { const token = options.csrf(); if (!token) throw new CopyFailure("DENIED"); headers.set("content-type", "application/json"); headers.set("X-CSRF-Token", token); }
    let r: Response; try { r = await options.transport(new URL(path, options.origin), { method, headers, credentials: "include", cache: "no-store", redirect: "error", ...(body ? { body } : {}) }); } catch { throw new CopyFailure(method === "POST" ? "UNKNOWN" : "UNAVAILABLE"); }
    if (!options.current()) throw new CopyFailure(method === "POST" ? "UNKNOWN" : "STALE");
    if (r.status === 401 || r.status === 403) { options.invalidate(); throw new CopyFailure("DENIED"); }
    if (![200, 202].includes(r.status) || !r.headers.get("content-type")?.toLowerCase().match(/^application\/json(?:\s*;|$)/)) throw new CopyFailure(method === "POST" ? "UNKNOWN" : "UNAVAILABLE");
    let data: unknown; try { data = await r.json(); } catch { throw new CopyFailure(method === "POST" ? "UNKNOWN" : "UNAVAILABLE"); }
    if (!options.current()) throw new CopyFailure(method === "POST" ? "UNKNOWN" : "STALE");
    return { status: r.status, data };
  }
  function candidate(data: unknown, status: number, key?: string): Candidate | null {
    if (v.UnknownCandidateResponse(data)) { const x = data as DTO["UnknownCandidateResponse"]; if (status !== 202 || !key || x.data.request_key !== key) throw new CopyFailure("INVALID"); return null; }
    if (!validCandidate(data) || ![200, 202].includes(status)) throw new CopyFailure("INVALID"); return data.data;
  }
  function decision(data: unknown, status: number, id: string, input: ReviewCopy): Decision {
    if (!(status === 200 && v.DecisionResponse(data) || status === 202 && v.UnknownDecisionResponse(data))) throw new CopyFailure("INVALID");
    const d = (data as DTO["DecisionResponse"] | DTO["UnknownDecisionResponse"]).data;
    if (d.candidate_id !== id || d.candidate_hash !== input.candidate_hash || d.request_key !== input.request_key || d.state === "saved" && input.action !== "approve" || d.state === "rejected" && input.action !== "reject") throw new CopyFailure("INVALID");
    return d;
  }
  return {
    async probe(key: string): Promise<boolean> { if (!uuid.test(key)) throw new CopyFailure("INVALID"); const { status, data } = await request("GET", `/api/v1/copy/candidate-requests/${key}`); return status === 202 && !!v.UnknownCandidateResponse(data) && (data as DTO["UnknownCandidateResponse"]).data.request_key === key; },
    async create(input: CreateCopy): Promise<void> { if (!validCreate(input)) throw new CopyFailure("INVALID"); const key = `create:${input.request_key}`; if (attempted.has(key)) throw new CopyFailure("UNKNOWN"); attempted.add(key); const x = await request("POST", "/api/v1/copy/candidates", JSON.stringify(input)); if (x.status !== 202) throw new CopyFailure("UNKNOWN"); candidate(x.data, x.status, input.request_key); },
    async candidateReceipt(input: CreateCopy): Promise<Candidate | null> { if (!validCreate(input)) throw new CopyFailure("INVALID"); const x = await request("GET", `/api/v1/copy/candidate-requests/${input.request_key}`); const d = candidate(x.data, x.status, input.request_key); if (d && x.status !== 200) throw new CopyFailure("INVALID"); if (d && (d.candidate.retrieval.scope.shop_id !== input.shop_id || d.candidate.retrieval.registry_id !== input.registry_id || d.candidate.retrieval.registry_digest !== input.registry_digest || d.candidate.product_source_id !== input.product_source_id || d.candidate.reviewer_id !== input.reviewer_id)) throw new CopyFailure("INVALID"); return d; },
    async read(id: string): Promise<Candidate> { if (!uuid.test(id)) throw new CopyFailure("INVALID"); const x = await request("GET", `/api/v1/copy/candidates/${id}`); const d = candidate(x.data, x.status); if (x.status !== 200 || !d || d.candidate.candidate_id !== id) throw new CopyFailure("INVALID"); return d; },
    async review(id: string, input: ReviewCopy): Promise<void> { if (!uuid.test(id) || !validReview(input)) throw new CopyFailure("INVALID"); const key = `review:${input.request_key}`; if (attempted.has(key)) throw new CopyFailure("UNKNOWN"); attempted.add(key); const x = await request("POST", `/api/v1/copy/candidates/${id}/review`, JSON.stringify(input)); decision(x.data, x.status, id, input); },
    async reviewReceipt(id: string, input: ReviewCopy): Promise<Decision> { if (!uuid.test(id) || !validReview(input)) throw new CopyFailure("INVALID"); const q = new URLSearchParams({ candidate_hash: input.candidate_hash }); const x = await request("GET", `/api/v1/copy/candidates/${id}/review-receipts/${input.request_key}?${q}`); return decision(x.data, x.status, id, input); },
  };
}
