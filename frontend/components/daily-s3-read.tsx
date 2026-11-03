"use client";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { DailyRead } from "../lib/m3-types.generated";
import { appendCitationPage, dailyS3ReadApi, S3ReadFailure } from "../lib/p6-daily-s3-read";
import type { DailyCapability, DailyEvidence, DailyQuestion, ReportBinding } from "../lib/p6-daily-s3-read";
import { Card, Notice } from "./ui";

type Citation = DailyEvidence["citations"][number];
const kindText: Record<string, string> = { order: "订单", order_line: "订单明细", refund: "退款", coverage: "采集范围", rule: "规则", metric: "报告指标" };
function CitationList({ values }: { values: readonly Citation[] }) {
  return <ul className="inquiry-facts">{values.map(item => <li key={item.citation_id}>
    {kindText[item.entity_kind]} · {item.entity_ref}
    <details><summary>查看脱敏依据</summary><p className="daily-id">{item.field_path}：{item.value ?? "未报告"}</p></details>
  </li>)}</ul>;
}
export function DailyS3Read({ read, origin, invalidate, parentCurrent }: { read: DailyRead; origin: string; invalidate: () => void; parentCurrent: () => boolean }) {
  const report = read.daily.report;
  const active = useRef(false), epoch = useRef(0), busyRef = useRef(false);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [capability, setCapability] = useState<DailyCapability | null>(null);
  const [evidence, setEvidence] = useState<DailyEvidence | null>(null), [evidenceItems, setEvidenceItems] = useState<readonly Citation[]>([]);
  const [question, setQuestion] = useState<DailyQuestion | null>(null), [questionItems, setQuestionItems] = useState<readonly Citation[]>([]);
  useEffect(() => { active.current = true; return () => { active.current = false; epoch.current++; }; }, [read.daily.task_id, report?.report_id, report?.snapshot_id, report?.facts_hash]);
  if (!report || !read.daily.question_creation_enabled) return null;
  const binding: ReportBinding = { task: read.daily.task_id, report: report.report_id, snapshot: report.snapshot_id,
    contentHash: report.content_hash, factsHash: report.facts_hash, evidenceCount: report.evidence_count };
  async function run<T>(action: (api: ReturnType<typeof dailyS3ReadApi>) => Promise<T>, apply: (value: T) => void) {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setMessage("");
    const stamp = ++epoch.current, current = () => parentCurrent() && active.current && epoch.current === stamp;
    try {
      const value = await action(dailyS3ReadApi({ origin, current, invalidate }));
      if (current()) apply(value);
    } catch (error) { if (current()) setMessage(error instanceof S3ReadFailure ? error.message : "读取未完成。"); }
    finally { if (current()) { busyRef.current = false; setBusy(false); } }
  }
  const loadEvidence = (cursor: string | null) => void run(api => api.evidence(binding, cursor), value => {
    const old = cursor ? evidenceItems : [];
    if (cursor && (!evidence || evidence.next_cursor !== cursor || evidence.total_evidence_count !== value.total_evidence_count))
      throw new S3ReadFailure("INVALID_RESPONSE");
    const combined = appendCitationPage(old, value.citations, value.total_evidence_count, cursor, value.next_cursor);
    setEvidence(value); setEvidenceItems(combined);
  });
  const loadQuestion = (id: string, cursor: string | null) => void run(api => api.question(binding, id, cursor), value => {
    const old = cursor ? questionItems : [];
    if (cursor && (!question || question.next_cursor !== cursor || question.question_id !== id ||
          JSON.stringify(question.answer) !== JSON.stringify(value.answer) || question.total_evidence_count !== value.total_evidence_count))
      throw new S3ReadFailure("INVALID_RESPONSE");
    const combined = appendCitationPage(old, value.citations, value.total_evidence_count, cursor, value.next_cursor);
    setQuestion(value); setQuestionItems(combined);
  });
  function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = String(new FormData(event.currentTarget).get("question_id") ?? "").trim();
    setQuestion(null); setQuestionItems([]); loadQuestion(id, null);
  }
  return <Card title="本报告的证据与已有追问">
    <p>此页面可读取本报告的证据和已受理的模板追问；暂不支持在此创建日报或提交新追问。</p>
    <button disabled={busy} onClick={() => void run(api => api.capabilities(read.daily.shop_id), setCapability)}>读取当前店铺来源状态</button>
    {capability && <p>{capability.enabled ? "当前店铺的受控来源可用。" : "当前店铺的受控来源不可用。"}</p>}
    <div className="actions"><button disabled={busy} onClick={() => { setEvidence(null); setEvidenceItems([]); loadEvidence(null); }}>读取报告证据</button></div>
    {evidence && <section><h3>报告证据</h3><p>已读取 {evidenceItems.length} / {evidence.total_evidence_count} 条。</p>
      <CitationList values={evidenceItems} />
      {evidence.next_cursor && <button disabled={busy} onClick={() => loadEvidence(evidence.next_cursor)}>读取下一页证据</button>}
    </section>}
    <form onSubmit={submitQuestion}><label>已有追问编号<input name="question_id" required /></label><button disabled={busy}>读取已有追问</button></form>
    {question && <section><h3>已有追问</h3>
      {question.answer ? <><p>本报告模板解释 · 未调用模型。</p><p>{question.answer.summary}</p>
        <p>已读取 {questionItems.length} / {question.total_evidence_count} 条依据。</p><CitationList values={questionItems} />
        {question.next_cursor && <button disabled={busy} onClick={() => loadQuestion(question.question_id, question.next_cursor)}>读取下一页追问依据</button>}</> :
        <p>{question.state === "queued" || question.state === "analyzing" ? "追问正在处理，尚无结果。" : "当前没有可展示的追问结果。"}</p>}
    </section>}
    {message && <Notice title="读取状态" tone="warning">{message}</Notice>}
  </Card>;
}
