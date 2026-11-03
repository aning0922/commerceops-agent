import { test, expect } from "@playwright/test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Inquiry, InquiryResult } from "../components/inquiry";
import { inquiryApi, inquiryBoundToRequest, validInquiryRead } from "../lib/p6-inquiry-client";
import type { InquiryInput, InquiryRead } from "../lib/p6-inquiry-client";
import type { A01ReadClient } from "../lib/p3-live-client";
import failed from "./inquiry-failed.fixture.json" with { type: "json" };
import knownFailed from "./inquiry-failed-known-usage.fixture.json" with { type: "json" };

const id = "00000000-0000-4000-8000-000000000001", key = "00000000-0000-4000-8000-000000000002";
const binding = "a".repeat(64), domain = { start: "2026-11-01T00:00:00Z", end: "2026-11-02T00:00:00Z" };
const input: InquiryInput = { schema_version: "p6-inquiry-web-v1", shop_id: id, question: "库存 DEMO", context_report_id: null, request_key: key };
const receipt = { schema_version: "p6-inquiry-web-v1", identity_mode: "session", task_id: id, shop_id: id, request_key: key,
  state: "queued", duplicate: false, source_mode: "mock", source_binding: binding, source_domain: domain,
  evidence_mode: "offline_stub", server_time: "2026-11-03T00:00:00Z", trace_id: id };
const pending = { ...receipt, result: null, answer: null, data_label: "本地演示数据 / 离线模型替身" };
const fact = { evidence_id: "ref1", metric: "available_stock", sku_key: "sku1", window: null,
  as_of: "2026-11-02T00:00:00Z", quality_flags: [], value: "5", unit: "件", currency: null };
const finished = { ...pending, state: "completed", answer: "可用库存 5 件", result: {
  schema_version: "p6-inquiry-result-v1", status: "complete", model_calls: 2, tool_calls: 1, scanned_rows: 1,
  traces: [{ tool_call_id: "call1", name: "commerce.read_inventory", args_hash: "b".repeat(64) }],
  results: [{ tool_call_id: "call1", shop_id: id, source_binding: binding, snapshot_id: "snapshot1", report_id: null,
    as_of: "2026-11-02T00:00:00Z", complete: true, quality_flags: [], scanned_rows: 1,
    sku_keys: ["sku1"], products: [], facts: [fact], windows: [] }],
  evidence_refs: ["ref1"], claims: [{ kind: "fact", refs: ["ref1"] }], clarification_options: [],
  evidence_mode: "offline_stub", workflow_version: "p6-readonly-inquiry-v1" } };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
test("strict inquiry result binds task source trace claims and facts", () => {
  expect(validInquiryRead(pending)).toBe(true);
  expect(validInquiryRead(finished)).toBe(true);
  expect(validInquiryRead({ ...finished, result: { ...finished.result, evidence_refs: ["other"] } })).toBe(false);
  expect(validInquiryRead({ ...finished, result: { ...finished.result, claims: [] } })).toBe(false);
  expect(validInquiryRead({ ...finished, result: { ...finished.result, claims: [{ kind: "compare", refs: ["ref1"] }] } })).toBe(false);
  expect(validInquiryRead({ ...finished, result: { ...finished.result, results: [{ ...finished.result.results[0], source_binding: "c".repeat(64) }] } })).toBe(false);
  expect(validInquiryRead({ ...finished, result: { ...finished.result, results: [{ ...finished.result.results[0], complete: false }] } })).toBe(false);
  expect(validInquiryRead({ ...pending, actor: id })).toBe(false);
  for (const status of ["clarify", "insufficient_evidence", "source_incomplete"]) {
    expect(validInquiryRead({ ...pending, state: "completed", answer: "请核实", result: { ...finished.result,
      status, tool_calls: 0, traces: [], results: [], evidence_refs: [], claims: [], clarification_options: [] } })).toBe(true);
  }
});
test("18a failed DTO accepts safe failure and known nonzero usage without disclosing facts", () => {
  expect(validInquiryRead(failed)).toBe(true);
  const used = { ...failed, result: { ...failed.result, model_calls: 2, tool_calls: 1, scanned_rows: 7,
    traces: [{ tool_call_id: "call1", name: "commerce.read_inventory", args_hash: "b".repeat(64) }] } };
  expect(validInquiryRead(used)).toBe(true);
  if (!validInquiryRead(used)) throw new Error("Failed DTO fixture must validate");
  const html = renderToStaticMarkup(createElement(InquiryResult, { read: used }));
  expect(html).toContain("当前权限不足");
  expect(html).toContain("离线模型替身调用");
  expect(html).toContain("扫描记录");
  expect(html).not.toContain("查看依据与时间");
  expect(validInquiryRead({ ...failed, result: { ...failed.result, status: "complete" } })).toBe(false);
  expect(validInquiryRead({ ...failed, result: { ...failed.result, status: "clarify" } })).toBe(false);
  expect(validInquiryRead({ ...failed, result: { ...failed.result, results: finished.result.results } })).toBe(false);
  expect(validInquiryRead({ ...failed, result: { ...failed.result, evidence_refs: ["ref1"] } })).toBe(false);
  expect(validInquiryRead({ ...failed, result: { ...failed.result, claims: [{ kind: "fact", refs: ["ref1"] }] } })).toBe(false);
  expect(validInquiryRead({ ...failed, result: { ...failed.result, clarification_options: [{ sku_key: "sku1", label: "商品" }] } })).toBe(false);
});
test("e2e50f safe failure preserves current-attempt 3/2/3 usage and two traces", () => {
  expect(validInquiryRead(knownFailed)).toBe(true);
  if (!validInquiryRead(knownFailed) || !knownFailed.result) throw new Error("Frozen DTO fixture must validate");
  expect([knownFailed.result.model_calls, knownFailed.result.tool_calls, knownFailed.result.scanned_rows]).toEqual([3, 2, 3]);
  expect(knownFailed.result.traces).toHaveLength(2);
  expect(knownFailed.result.results).toEqual([]);
  expect(knownFailed.result.claims).toEqual([]);
  expect(knownFailed.result.evidence_refs).toEqual([]);
  expect(knownFailed.result.clarification_options).toEqual([]);
  const html = renderToStaticMarkup(createElement(InquiryResult, { read: knownFailed })).replaceAll("<!-- -->", "");
  expect(html).toContain("仅本次执行尝试的已知用量；此前尝试用量未知");
  expect(html).toContain("离线模型替身调用 3 次；工具调用 2 次；扫描记录 3 条");
  expect(html).not.toContain("查看依据与时间");
});
test("prepared request freezes key, shop and body against later mutation", async () => {
  const mutable = { ...input };
  let sent = "";
  const api = inquiryApi({ origin: new URL("http://127.0.0.1:9000"), csrf: () => "x".repeat(43), sessionCurrent: () => true,
    viewCurrent: () => true, invalidate: () => {}, transport: async (_url, init) => { sent = String(init.body); return json(receipt, 202); } });
  const prepared = api.prepare(mutable);
  mutable.request_key = id; mutable.question = "changed";
  expect((await prepared.send()).request_key).toBe(key);
  expect(JSON.parse(sent)).toMatchObject({ request_key: key, question: "库存 DEMO" });
});
test("result stays bound to original request, source window and selected report", () => {
  if (!validInquiryRead(finished)) throw new Error("Fixture must validate");
  expect(inquiryBoundToRequest(finished, { key, shop: id, receipt: finished, contextReport: null })).toBe(true);
  expect(inquiryBoundToRequest({ ...finished, source_domain: { ...domain, end: "2026-11-03T00:00:00Z" } },
    { key, shop: id, receipt: finished })).toBe(false);
  const typed: InquiryRead = finished;
  const withReport: InquiryRead = { ...typed, result: { ...typed.result!, results: typed.result!.results.map(result => ({ ...result, report_id: id })) } };
  expect(inquiryBoundToRequest(withReport, { key, shop: id, receipt: finished, contextReport: null })).toBe(false);
  expect(inquiryBoundToRequest(withReport, { key, shop: id, receipt: finished, contextReport: id })).toBe(true);
});
test("unknown submission keeps one key, never sends again and reads original receipt", async () => {
  const calls: { method: string; url: string; body: string | undefined }[] = [];
  const api = inquiryApi({ origin: new URL("http://127.0.0.1:9000"), csrf: () => "x".repeat(43), sessionCurrent: () => true,
    viewCurrent: () => true, invalidate: () => {}, transport: async (url, init) => {
      calls.push({ method: init.method!, url: url.pathname, body: init.body as string | undefined });
      if (init.method === "POST") throw new Error("lost response");
      return json(pending);
    } });
  const prepared = api.prepare(input);
  expect(calls).toHaveLength(0);
  await expect(prepared.send()).rejects.toMatchObject({ code: "UNKNOWN" });
  await expect(prepared.send()).rejects.toMatchObject({ code: "UNKNOWN" });
  expect((await api.read("request", key)).request_key).toBe(key);
  expect(calls.map(x => [x.method, x.url])).toEqual([["POST", "/api/v1/readonly-inquiries"], ["GET", `/api/v1/readonly-inquiries/requests/${key}`]]);
  expect(JSON.parse(calls[0].body!).request_key).toBe(key);
});
test("receipt mismatch and stale revocation cannot contaminate a new session", async () => {
  let valid = true, invalidations = 0, finish!: (value: Response) => void;
  const api = inquiryApi({ origin: new URL("http://127.0.0.1:9000"), csrf: () => "x".repeat(43),
    sessionCurrent: () => valid, viewCurrent: () => true, invalidate: () => invalidations++,
    transport: () => new Promise(resolve => { finish = resolve; }) });
  const late = api.read("request", key);
  valid = false; finish(json({}, 403));
  await expect(late).rejects.toMatchObject({ code: "STALE" });
  expect(invalidations).toBe(0);
  valid = true;
  const post = api.prepare(input).send();
  finish(json({ ...receipt, request_key: id }, 202));
  await expect(post).rejects.toMatchObject({ code: "UNKNOWN" });
  const current = api.read("request", key); finish(json({}, 401));
  await expect(current).rejects.toMatchObject({ code: "SESSION_INVALID" });
  expect(invalidations).toBe(1);
  const forbidden = api.read("request", key); finish(json({}, 403));
  await expect(forbidden).rejects.toMatchObject({ code: "DENIED" });
  expect(invalidations).toBe(2);
});
test("disabled service returns fixed disabled status without automatic retry", async () => {
  let calls = 0;
  const api = inquiryApi({ origin: new URL("http://127.0.0.1:9000"), csrf: () => "x".repeat(43), sessionCurrent: () => true,
    viewCurrent: () => true, invalidate: () => {}, transport: async () => { calls++; return json({
      schema_version: "p6-inquiry-web-v1", code: "INQUIRY_DISABLED",
      message: "无法处理此查询，请核对当前权限、输入或原请求回执。", trace_id: id }, 409); } });
  await expect(api.prepare(input).send()).rejects.toMatchObject({ code: "DISABLED" });
  expect(calls).toBe(1);
});
test("disabled candidate has no submit or receipt button", () => {
  const html = renderToStaticMarkup(createElement(Inquiry, { client: {} as A01ReadClient, enabled: false, shops: [id], holdWrite: () => {} }));
  expect(html).toContain("查询当前未启用");
  expect(html).not.toContain("提交查询");
  expect(html).not.toContain("读取已有请求");
});
test("explicitly enabled candidate exposes bounded question and recovery entry", () => {
  const html = renderToStaticMarkup(createElement(Inquiry, { client: {} as A01ReadClient, enabled: true, shops: [id], holdWrite: () => {} }));
  expect(html).toContain("提交查询");
  expect(html).toContain("读取已有请求");
  expect(html).toContain("日报不能作为此处的报告上下文");
});
