import { test, expect } from "@playwright/test";
import { dailyWriteApi, requestHash, validatePrepared } from "../lib/p6-daily-write";
import type { Prepared } from "../lib/p6-daily-write";
const id = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12,"0")}`;
const report: Prepared = { kind: "report", input: { schema_version: "p6-m3-web-v1", shop_id: id(2), source_config_version: "来源甲", request_key: id(1), business_day: null } };
const question: Prepared = { kind: "question", shop: id(2), parent: id(4), input: { schema_version: "p6-daily-question-v1", request_key: id(1), report_id: id(5), snapshot_id: id(6), content_hash: "b".repeat(64), facts_hash: "c".repeat(64), question: { kind: "data_quality", metric_key: null, finding_id: null } } };
const json = (x: unknown, status = 200) => new Response(JSON.stringify(x), { status, headers: { "content-type": "application/json" } });
function result(p: Prepared, hash: string) {
 const common = { schema_version: "p6-m3-web-v1", lookup_status: "accepted", request_key: p.input.request_key, shop_id: p.kind === "report" ? p.input.shop_id : p.shop, task_id: id(3), state: "queued", failure_code: null, request_hash: hash };
 const r = p.kind === "report" ? { ...common, operation: "daily_report.create", source_config_version: p.input.source_config_version, business_day: "2026-11-02" } : { ...common, operation: "daily_question.create", parent_task_id: p.parent, report_id: p.input.report_id, snapshot_id: p.input.snapshot_id, content_hash: p.input.content_hash, facts_hash: p.input.facts_hash, question: p.input.question };
 return { schema_version: "p3-web-v1", identity_mode: "session", server_time: "2026-11-03T05:00:00Z", trace_id: id(7), receipt: r };
}
test("frozen canonical hash vectors preserve null, UTF-8 and question binding", async () => {
 expect(validatePrepared(report)).toBe(true); expect(validatePrepared(question)).toBe(true);
 expect(await requestHash(report)).toBe("cfecefc5819fa58207d432275202914c41fb93c5305bd5c753cc0b66cd3ae0f8");
 expect(await requestHash(question)).toBe("271fe3bfedc06801342a6ec57aa700e3fd3ebb37a925e776c5adbdc930b8bb8f");
 expect(validatePrepared({ ...question, input: { ...question.input, question: { kind: "data_quality", metric_key: "paid_order_count", finding_id: null } } })).toBe(false);
});
test("unknown POST is one attempt and original key GET does not turn 404 into failure", async () => {
 const calls: string[] = []; let read = false;
 const api = dailyWriteApi({ origin: new URL("http://localhost:9000"), csrf: () => "token", current: () => true, invalidate: () => {}, transport: async (url, init) => { calls.push(`${init.method} ${url.pathname}${url.search}`); if (init.method === "POST") throw Error("dropped"); return read ? json(result(report, await requestHash(report))) : json({},404); } });
 await expect(api.send(report)).rejects.toMatchObject({ code: "UNKNOWN" }); await expect(api.send(report)).rejects.toMatchObject({ code: "UNKNOWN" });
 await expect(api.receipt(report)).rejects.toMatchObject({ code: "UNAVAILABLE" }); read = true; expect((await api.receipt(report)).operation).toBe("daily_report.create");
 expect(calls.filter(x => x.startsWith("POST")).length).toBe(1); expect(calls[1]).toBe(`GET /api/v1/daily-reports/requests/${id(1)}?shop_id=${id(2)}`);
});
test("question receipt is tied to original parent, report, question and hash", async () => {
 let value = result(question, await requestHash(question));
 const api = dailyWriteApi({ origin: new URL("http://localhost:9000"), csrf: () => "token", current: () => true, invalidate: () => {}, transport: async (url, init) => { expect(init.method).toBe("GET"); expect(url.pathname).toBe(`/api/v1/daily-reports/${id(4)}/questions/requests/${id(1)}`); expect(url.searchParams.get("report_id")).toBe(id(5)); return json(value); } });
 expect((await api.receipt(question)).operation).toBe("daily_question.create"); value = { ...value, receipt: { ...value.receipt, snapshot_id: id(8) } }; await expect(api.receipt(question)).rejects.toMatchObject({ code: "INVALID" });
});
test("stale session response cannot clear the new session", async () => {
 let current = true, cleared = 0, finish!: (r: Response) => void;
 const api = dailyWriteApi({ origin: new URL("http://localhost:9000"), csrf: () => "token", current: () => current, invalidate: () => cleared++, transport: () => new Promise(resolve => { finish = resolve; }) });
 const pending = api.receipt(report); current = false; finish(json({},403)); await expect(pending).rejects.toMatchObject({ code: "STALE" }); expect(cleared).toBe(0);
});
