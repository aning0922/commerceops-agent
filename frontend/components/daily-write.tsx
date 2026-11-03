"use client";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { A01ReadClient } from "../lib/p3-live-client";
import type { DailyRead } from "../lib/m3-types.generated";
import { dailyS3ReadApi } from "../lib/p6-daily-s3-read";
import type { DailyCapability } from "../lib/p6-daily-s3-read";
import { DailyWriteFailure, validatePrepared } from "../lib/p6-daily-write";
import type { Prepared, Receipt } from "../lib/p6-daily-write";
import { Card, Notice } from "./ui";

type Props = { client: A01ReadClient; origin: string; shops: readonly string[]; principal: string; current: () => boolean; read?: DailyRead };
export function DailyWrite({ client, origin, shops, principal, current, read }: Props) {
  const active = useRef(false), generation = useRef(0), lock = useRef(false), sending = useRef(false);
  const [shop, setShop] = useState(read?.daily.shop_id ?? shops[0] ?? "");
  const [cap, setCap] = useState<DailyCapability | null>(null), [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Prepared | null>(null), [held, setHeld] = useState<Prepared | null>(null), [receipt, setReceipt] = useState<Receipt | null>(null), [message, setMessage] = useState("");
  const report = read?.daily.report;
  const storage = `commerceops-daily-pending-v1:${principal}:${read ? `question:${read.daily.task_id}` : "report"}`;
  useEffect(() => { active.current = true; try { const raw = sessionStorage.getItem(storage); if (raw) { const p = JSON.parse(raw) as Prepared; if (validatePrepared(p)) { setHeld(p); lock.current = true; } else { lock.current = true; setMessage("原请求记录无法安全读取，请保留本页并核对。"); }; } } catch { lock.current = true; setMessage("原请求记录无法安全读取。"); }
    return () => { active.current = false; generation.current++; }; }, [storage]);
  const isCurrent = (stamp: number) => active.current && generation.current === stamp && current();
  async function capability(stamp: number, selected: string) {
    if (!shops.includes(selected)) throw new DailyWriteFailure("DENIED");
    return dailyS3ReadApi({ origin, current: () => isCurrent(stamp), invalidate: () => client.clearSession() }).capabilities(selected);
  }
  async function loadCapability() {
    if (busy || held) return;
    const stamp = ++generation.current; setBusy(true); setCap(null); setPreview(null); setMessage("");
    try { const c = await capability(stamp, shop); if (isCurrent(stamp)) setCap(c); }
    catch { if (isCurrent(stamp)) setMessage("无法读取当前店铺能力；请稍后重试。"); }
    finally { if (isCurrent(stamp)) setBusy(false); }
  }
  function makePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!cap?.enabled || !cap.source || !shops.includes(shop) || lock.current) return;
    const form = new FormData(event.currentTarget); const key = crypto.randomUUID();
    let p: Prepared;
    if (!read || !report) p = { kind: "report", input: { schema_version: "p6-m3-web-v1", shop_id: shop, source_config_version: cap.source.source_config_version, request_key: key, business_day: String(form.get("day") ?? "") || null } };
    else {
      const kind = String(form.get("kind")) as "metric_definition" | "metric_evidence" | "finding_reason" | "data_quality";
      const target = String(form.get("target") ?? "").trim();
      if (!cap.question_kinds.includes(kind)) { setMessage("当前能力不支持所选模板。"); return; }
      p = { kind: "question", shop, parent: read.daily.task_id, input: { schema_version: "p6-daily-question-v1", request_key: key, report_id: report.report_id, snapshot_id: report.snapshot_id, content_hash: report.content_hash, facts_hash: report.facts_hash,
        question: { kind, metric_key: kind === "metric_definition" || kind === "metric_evidence" ? target as never : null, finding_id: kind === "finding_reason" ? target : null } } };
    }
    if (!validatePrepared(p)) { setMessage("请核对日期或模板目标。"); return; }
    setPreview(p); setMessage("");
  }
  async function send() {
    if (!preview || busy || lock.current || sending.current || !client.dailyWriteAccess) return;
    sending.current = true;
    const stamp = ++generation.current; setBusy(true); setMessage("");
    try {
      const latest = await capability(stamp, shop);
      if (!isCurrent(stamp)) return;
      if (!latest.enabled || !latest.source || !cap?.source || latest.source.source_config_version !== cap.source.source_config_version || preview.kind === "question" && !latest.question_kinds.includes(preview.input.question.kind)) throw new DailyWriteFailure("INVALID");
      const api = client.dailyWriteAccess(() => isCurrent(stamp));
      // Store before network: after reload or re-login only the original receipt can be read.
      sessionStorage.setItem(storage, JSON.stringify(preview)); lock.current = true; setHeld(preview); setPreview(null);
      await api.send(preview);
      if (isCurrent(stamp)) setMessage("已收到受理响应，请读取原请求回执核对绑定。");
    } catch (error) { if (isCurrent(stamp)) setMessage(error instanceof DailyWriteFailure ? error.message : "提交结果待核实；只可查询原请求。"); }
    finally { sending.current = false; if (isCurrent(stamp)) setBusy(false); }
  }
  async function lookup() {
    if (!held || busy || !client.dailyWriteAccess) return;
    const stamp = ++generation.current; setBusy(true); setMessage("");
    try { const r = await client.dailyWriteAccess(() => isCurrent(stamp)).receipt(held); if (isCurrent(stamp)) { setReceipt(r); setMessage("已核对原请求回执；受理不代表报告或追问已完成。"); } }
    catch (error) { if (isCurrent(stamp)) setMessage(error instanceof DailyWriteFailure ? error.message : "原请求暂不可读取。"); }
    finally { if (isCurrent(stamp)) setBusy(false); }
  }
  function finish() { if (!receipt) return; sessionStorage.removeItem(storage); lock.current = false; setHeld(null); setReceipt(null); setCap(null); setMessage(""); }
  if (read && !held && (!report || !read.daily.question_creation_enabled || !shops.includes(read.daily.shop_id))) return null;
  return <Card title={read ? "新建模板追问" : "创建经营日报"}>
    <p>{read ? "模板基于本报告，未调用模型，也不会外发。" : "来源仅限当前授权店铺的受控数据；调度由管理员通过受控 CLI 配置。"}</p>
    {!held && lock.current ? <p>本会话保留的请求无法安全解析，写入已停用。</p> : held ? <><p>保留原请求键：<span className="daily-id">{held.input.request_key}</span>。未核实前只查询原键，不重发。</p><button disabled={busy} onClick={() => void lookup()}>读取原请求回执</button>
      {receipt && <><p>原任务：{receipt.task_id} · 状态：{receipt.state}</p>{receipt.operation === "daily_report.create" && <a href={`/daily-reports/${receipt.task_id}`}>打开原日报</a>}{receipt.operation === "daily_question.create" && <p>追问编号：{receipt.task_id}；可在本报告的“已有追问”中读取。</p>}<button onClick={finish}>完成本次回执核对</button></>}</> : <>
      {!read && <label>店铺<select value={shop} onChange={e => { setShop(e.target.value); setCap(null); setPreview(null); }}>{shops.map(x => <option key={x} value={x}>{x}</option>)}</select></label>}
      <button disabled={busy || !shop} onClick={() => void loadCapability()}>读取当前店铺能力</button>
      {cap && !cap.enabled && <p>当前店铺来源不可用。</p>}
      {cap?.enabled && !preview && <form onSubmit={makePreview}>
        {!read ? <label>业务日期（留空由服务确定）<input name="day" type="date" min={cap.earliest_business_day ?? undefined} /></label> : <><label>模板<select name="kind">{cap.question_kinds.map(x => <option key={x} value={x}>{x}</option>)}</select></label><label>指标键或发现 ID（数据质量模板留空）<input name="target" /></label></>}
        <button disabled={busy}>预览固定请求</button></form>}
      {preview && <><p>请核对本次固定请求，提交后不能修改或以新键自动重发。</p><pre className="daily-id">{JSON.stringify(preview.input, null, 2)}</pre><button disabled={busy} onClick={() => void send()}>确认提交一次</button><button disabled={busy} onClick={() => setPreview(null)}>返回修改</button></>}
    </>}
    {message && <Notice title="日报操作状态" tone="info">{message}</Notice>}
  </Card>;
}
