import { test, expect } from "@playwright/test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DailyReport } from "../components/daily-report";
import { validDailyRead } from "../lib/m3-read-client";
import { appendCitationPage, dailyS3ReadApi, validEvidence, validQuestion } from "../lib/p6-daily-s3-read";
import type { DailyRead } from "../lib/m3-types.generated";
import fixture from "./daily-s3.fixture.json" with { type: "json" };

if (!validDailyRead(fixture.daily, fixture.daily.daily.task_id) || !fixture.daily.daily.report) throw new Error("Frozen S3 daily fixture must validate");
const read: DailyRead = fixture.daily;
const report = read.daily.report!;
const binding = { task: read.daily.task_id, report: report.report_id, snapshot: report.snapshot_id,
  contentHash: report.content_hash, factsHash: report.facts_hash, evidenceCount: report.evidence_count };
const evidenceFixture: unknown = fixture.evidence;
if (!validEvidence(evidenceFixture, binding)) throw new Error("Frozen evidence fixture must validate");
const questionId = fixture.question.question.question_id;
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });

test("frozen S3 daily, evidence and template question bind one report", () => {
  expect(validDailyRead(fixture.daily, fixture.daily.daily.task_id)).toBe(true);
  expect(validEvidence(fixture.evidence, binding)).toBe(true);
  expect(validQuestion(fixture.question, binding, questionId)).toBe(true);
  expect(validEvidence({ ...fixture.evidence, evidence: { ...fixture.evidence.evidence, facts_hash: "a".repeat(64) } }, binding)).toBe(false);
  expect(validEvidence({ ...fixture.evidence, evidence: { ...fixture.evidence.evidence, total_evidence_count: 0 } }, binding)).toBe(false);
  expect(validQuestion(fixture.question, binding, read.daily.task_id)).toBe(false);
  expect(validQuestion({ ...fixture.question, question: { ...fixture.question.question, answer: { ...fixture.question.question.answer,
    snapshot_id: read.daily.task_id } } }, binding, questionId)).toBe(false);
  expect(validQuestion({ ...fixture.question, question: { ...fixture.question.question, citations: fixture.evidence.evidence.citations.slice(0, 1) } }, binding, questionId)).toBe(false);
});
test("cursor pages preserve complete unique citations and reject replay or missing tail", () => {
  const citations = evidenceFixture.evidence.citations, total = citations.length;
  const first = appendCitationPage([], citations.slice(0, 1), total, null, "next");
  expect(appendCitationPage(first, citations.slice(1), total, "next", null)).toHaveLength(total);
  expect(() => appendCitationPage(first, citations.slice(0, 1), total, "next", null)).toThrow();
  expect(() => appendCitationPage(first, [], total, "next", null)).toThrow();
  expect(() => appendCitationPage(first, citations.slice(1, 2), total, "next", "next")).toThrow();
});
test("S3 reads use authenticated GET and capability is bound to the requested shop", async () => {
  const calls: string[] = [];
  const api = dailyS3ReadApi({ origin: "http://127.0.0.1:9000", current: () => true, invalidate: () => {},
    transport: async (url, init) => { calls.push(`${init.method} ${url.pathname}${url.search}`);
      expect(init).toMatchObject({ method: "GET", credentials: "include", cache: "no-store", redirect: "error" });
      if (url.pathname.endsWith("daily-capabilities")) return json(fixture.capabilities);
      if (url.pathname.endsWith("evidence")) return json(fixture.evidence);
      return json(fixture.question);
    } });
  expect((await api.capabilities(read.daily.shop_id)).enabled).toBe(true);
  expect((await api.evidence(binding, null)).report_id).toBe(binding.report);
  expect((await api.question(binding, questionId, null)).question_id).toBe(questionId);
  expect(calls.every(call => call.startsWith("GET "))).toBe(true);
  await expect(api.capabilities(read.daily.task_id)).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
});
test("late 403 cannot invalidate the new page, current 403 clears it", async () => {
  let current = true, cleared = 0, finish!: (response: Response) => void;
  const api = dailyS3ReadApi({ origin: "http://127.0.0.1:9000", current: () => current, invalidate: () => cleared++,
    transport: () => new Promise(resolve => { finish = resolve; }) });
  const old = api.evidence(binding, null); current = false; finish(json({}, 403));
  await expect(old).rejects.toMatchObject({ code: "STALE" }); expect(cleared).toBe(0);
  current = true; const fresh = api.evidence(binding, null); finish(json({}, 403));
  await expect(fresh).rejects.toMatchObject({ code: "DENIED" }); expect(cleared).toBe(1);
});
test("read-only S3 UI separates unknown fake delivery and hides unsupported writes", () => {
  const html = renderToStaticMarkup(createElement(DailyReport, { read, origin: "http://127.0.0.1:9000", invalidate: () => {}, parentCurrent: () => true }));
  expect(html).toContain("模拟投递结果待核实");
  expect(html).toContain("不代表实际群消息发送或已读");
  expect(html).toContain("读取报告证据");
  expect(html).toContain("读取已有追问");
  expect(html).not.toContain(">提交追问</button>");
  expect(html).not.toContain(">创建日报</button>");
  const disabled = { ...read, daily: { ...read.daily, question_creation_enabled: false } } as DailyRead;
  const off = renderToStaticMarkup(createElement(DailyReport, { read: disabled, origin: "http://127.0.0.1:9000", invalidate: () => {}, parentCurrent: () => true }));
  expect(off).not.toContain("读取报告证据");
  expect(off).not.toContain("读取已有追问");
});
