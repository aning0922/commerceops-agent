import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import spec from "./p6-daily-s3-openapi.generated.json" with { type: "json" };
import type { components } from "./p6-daily-s3-types.generated";
import type { FetchTransport } from "./p3-transport";
type DTO = components["schemas"];
export type DailyEvidence = DTO["EvidenceView"];
export type DailyQuestion = DTO["QuestionView"];
export type DailyCapability = DTO["DailyCapabilities"];
export type ReportBinding = { task: string; report: string; snapshot: string; contentHash: string; factsHash: string; evidenceCount: number };
const defs = JSON.parse(JSON.stringify(spec.components.schemas).replaceAll("#/components/schemas/", "#/$defs/"));
const ajv = new Ajv2020({ strict: true, coerceTypes: false, useDefaults: false, removeAdditional: false });
addFormats(ajv);
const schemas = Object.fromEntries(["CapabilityRead", "EvidenceRead", "QuestionRead"].map(name => [name, ajv.compile({ ...defs[name], $defs: defs })]));
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();
const safeNumbers = (x: unknown): boolean => typeof x === "number" ? Number.isSafeInteger(x) : Array.isArray(x) ? x.every(safeNumbers) :
  x !== null && typeof x === "object" ? Object.values(x).every(safeNumbers) : true;
export class S3ReadFailure extends Error {
  constructor(readonly code: "INVALID_REQUEST" | "INVALID_RESPONSE" | "UNAVAILABLE" | "DENIED" | "STALE") {
    super(({ INVALID_REQUEST: "请核对记录编号。", INVALID_RESPONSE: "暂时无法安全展示当前记录。",
      UNAVAILABLE: "读取暂不可用，请稍后重新读取。", DENIED: "当前会话或权限已失效。", STALE: "页面或会话已变化。" })[code]);
  }
}
function boundPage(citations: readonly DTO["Citation"][], snapshot: string, total: number): boolean {
  return citations.length <= 50 && total >= citations.length && new Set(citations.map(c => c.citation_id)).size === citations.length &&
    citations.every(c => same(c.snapshot_id, snapshot));
}
export function appendCitationPage(previous: readonly DTO["Citation"][], page: readonly DTO["Citation"][], total: number,
  requestedCursor: string | null, nextCursor: string | null): readonly DTO["Citation"][] {
  if (page.some(item => previous.some(old => old.citation_id === item.citation_id)) || previous.length + page.length > total ||
      (nextCursor === null ? previous.length + page.length !== total :
        !page.length || nextCursor === requestedCursor || previous.length + page.length >= total)) throw new S3ReadFailure("INVALID_RESPONSE");
  return [...previous, ...page];
}
export function validEvidence(value: unknown, b: ReportBinding): value is DTO["EvidenceRead"] {
  if (!safeNumbers(value) || !schemas.EvidenceRead(value)) return false;
  const x = (value as DTO["EvidenceRead"]).evidence;
  return same(x.task_id, b.task) && same(x.report_id, b.report) && same(x.snapshot_id, b.snapshot) &&
    x.content_hash === b.contentHash && x.facts_hash === b.factsHash && x.total_evidence_count === b.evidenceCount &&
    boundPage(x.citations, b.snapshot, x.total_evidence_count);
}
export function validQuestion(value: unknown, b: ReportBinding, id: string): value is DTO["QuestionRead"] {
  if (!safeNumbers(value) || !schemas.QuestionRead(value)) return false;
  const q = (value as DTO["QuestionRead"]).question;
  if (!same(q.parent_task_id, b.task) || !same(q.question_id, id) ||
      (q.state === "completed") !== (q.answer !== null) || !boundPage(q.citations, b.snapshot, q.total_evidence_count)) return false;
  if (!q.answer) return q.citations.length === 0 && q.total_evidence_count === 0 && q.next_cursor === null;
  const a = q.answer;
  return same(a.report_id, b.report) && same(a.snapshot_id, b.snapshot) && a.content_hash === b.contentHash && a.facts_hash === b.factsHash &&
    a.narrative_mode === "template" && a.evidence_mode === "not_used" && a.model_requests_enabled === false && a.external_sender_enabled === false &&
    a.total_evidence_count === q.total_evidence_count && a.citation_ids.length === a.total_evidence_count &&
    new Set(a.citation_ids).size === a.citation_ids.length && q.citations.every(c => a.citation_ids.includes(c.citation_id));
}
export function dailyS3ReadApi(options: { origin: string; current: () => boolean; invalidate: () => void; transport?: FetchTransport }) {
  const origin = new URL(options.origin), transport = options.transport ?? ((url: URL, init: RequestInit) => fetch(url, init));
  async function get(path: string, query: Record<string, string>): Promise<unknown> {
    if (!options.current()) throw new S3ReadFailure("STALE");
    const url = new URL(path, origin);
    for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
    let response: Response;
    try { response = await transport(url, { method: "GET", credentials: "include", cache: "no-store", redirect: "error" }); }
    catch { throw new S3ReadFailure("UNAVAILABLE"); }
    if (!options.current()) throw new S3ReadFailure("STALE");
    if (response.status === 401 || response.status === 403) { options.invalidate(); throw new S3ReadFailure("DENIED"); }
    if (!response.ok) throw new S3ReadFailure("UNAVAILABLE");
    if (response.status !== 200 || !response.headers.get("content-type")?.toLowerCase().match(/^application\/json(?:\s*;|$)/)) throw new S3ReadFailure("INVALID_RESPONSE");
    let value: unknown; try { value = await response.json(); } catch { throw new S3ReadFailure("INVALID_RESPONSE"); }
    if (!options.current()) throw new S3ReadFailure("STALE");
    return value;
  }
  return {
    async capabilities(shop: string): Promise<DailyCapability> {
      if (!uuid.test(shop)) throw new S3ReadFailure("INVALID_REQUEST");
      const value = await get("/api/v1/daily-capabilities", { shop_id: shop });
      if (!safeNumbers(value) || !schemas.CapabilityRead(value)) throw new S3ReadFailure("INVALID_RESPONSE");
      const c = (value as DTO["CapabilityRead"]).capabilities;
      if (!same(c.shop_id, shop) || c.enabled !== (c.source !== null) || c.enabled !== (c.earliest_business_day !== null && c.metric_version !== null) ||
          c.model_requests_enabled !== false || c.external_sender_enabled !== false) throw new S3ReadFailure("INVALID_RESPONSE");
      return c;
    },
    async evidence(binding: ReportBinding, cursor: string | null): Promise<DailyEvidence> {
      if (![binding.task, binding.report, binding.snapshot].every(x => uuid.test(x)) || cursor !== null && (!cursor || cursor.length > 4096)) throw new S3ReadFailure("INVALID_REQUEST");
      const value = await get(`/api/v1/daily-reports/${binding.task}/evidence`, { report_id: binding.report, ...(cursor ? { cursor } : {}) });
      if (!validEvidence(value, binding)) throw new S3ReadFailure("INVALID_RESPONSE");
      return value.evidence;
    },
    async question(binding: ReportBinding, id: string, cursor: string | null): Promise<DailyQuestion> {
      if (![binding.task, binding.report, binding.snapshot, id].every(x => uuid.test(x)) || cursor !== null && (!cursor || cursor.length > 4096)) throw new S3ReadFailure("INVALID_REQUEST");
      const value = await get(`/api/v1/daily-reports/${binding.task}/questions/${id}`, cursor ? { cursor } : {});
      if (!validQuestion(value, binding, id)) throw new S3ReadFailure("INVALID_RESPONSE");
      return value.question;
    },
  };
}
