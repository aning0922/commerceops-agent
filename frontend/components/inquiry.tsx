"use client";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { A01ReadClient } from "../lib/p3-live-client";
import { InquiryFailure, inquiryBoundToRequest } from "../lib/p6-inquiry-client";
import type { InquiryBinding, InquiryRead } from "../lib/p6-inquiry-client";
import { Card, Notice } from "./ui";

type Held = InquiryBinding;
const statusText: Record<string, string> = {
  complete: "查询已完成", clarify: "需要进一步明确查询对象", unsupported: "当前查询方式不支持此问题",
  insufficient_evidence: "现有证据不足", invalid_response: "查询结果无法安全展示",
  source_incomplete: "来源数据不完整", access_denied: "当前权限不足", budget_exceeded: "查询已停止",
  timeout: "查询未在规定时间内完成", tool_denied: "当前查询范围不支持此操作",
};
const metricText: Record<string, string> = { available_stock: "可用库存", inbound_units: "在途数量",
  sold_units: "销量", order_net: "订单净额", order_average: "订单均值", refund_cohort: "退款" };
export function Inquiry({ client, enabled, shops, holdWrite }: {
  client: A01ReadClient; enabled: boolean; shops: readonly string[]; holdWrite: (held: boolean) => void;
}) {
  const generation = useRef(0), active = useRef(false), locked = useRef(false);
  const [disabledByService, setDisabledByService] = useState(false);
  const [busy, setBusy] = useState(false), [held, setHeld] = useState<Held | null>(null);
  const [read, setRead] = useState<InquiryRead | null>(null), [message, setMessage] = useState("");
  useEffect(() => { active.current = true; return () => { active.current = false; generation.current++; holdWrite(false); }; }, [holdWrite]);
  const makeAccess = (stamp: number) => {
    if (!client.inquiryAccess) throw new InquiryFailure("SESSION_INVALID");
    return client.inquiryAccess(() => active.current && generation.current === stamp);
  };
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!enabled || disabledByService || busy || locked.current) return;
    const form = new FormData(event.currentTarget), shop = String(form.get("shop") ?? ""), question = String(form.get("question") ?? "");
    const report = String(form.get("context_report_id") ?? "").trim();
    if (!shops.includes(shop) || !question.trim()) { setMessage("请选择店铺并输入问题。"); return; }
    const stamp = ++generation.current, key = crypto.randomUUID();
    let access: ReturnType<NonNullable<A01ReadClient["inquiryAccess"]>>;
    try { access = makeAccess(stamp); } catch { setMessage("会话已变化，请重新登录。"); return; }
    let prepared: ReturnType<typeof access.prepare>;
    try { prepared = access.prepare({ schema_version: "p6-inquiry-web-v1", shop_id: shop, question,
      context_report_id: report || null, request_key: key }); }
    catch { setMessage("请核对问题长度、店铺和分析报告编号。"); return; }
    locked.current = true; holdWrite(true); setHeld({ key, shop, receipt: null, contextReport: report || null }); setRead(null); setBusy(true); setMessage("");
    try {
      const receipt = await prepared.send();
      if (!active.current || generation.current !== stamp) return;
      setHeld({ key, shop, receipt, contextReport: report || null }); setMessage(receipt.duplicate ? "已找到原查询，请读取当前结果。" : "已受理查询，请读取当前结果。");
    } catch (error) {
      if (active.current && generation.current === stamp) {
        if (error instanceof InquiryFailure && ["DISABLED", "INVALID_REQUEST"].includes(error.code)) {
          locked.current = false; holdWrite(false); setHeld(null);
          if (error.code === "DISABLED") setDisabledByService(true);
        }
        setMessage(error instanceof InquiryFailure ? error.message : "提交结果待核实，请查询原请求回执。");
      }
    } finally { if (active.current && generation.current === stamp) setBusy(false); }
  }
  async function recover(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!enabled || disabledByService || busy || locked.current) return;
    const key = String(new FormData(event.currentTarget).get("request_key") ?? "").trim();
    const stamp = ++generation.current; setBusy(true); setRead(null); setMessage("");
    try {
      const value = await makeAccess(stamp).read("request", key);
      if (!active.current || generation.current !== stamp) return;
      locked.current = true; holdWrite(true); setHeld({ key, shop: value.shop_id, receipt: value }); setRead(value);
      setMessage("已读取原请求记录。");
    } catch (error) { if (active.current && generation.current === stamp) setMessage(error instanceof InquiryFailure ? error.message : "暂时无法读取原记录。"); }
    finally { if (active.current && generation.current === stamp) setBusy(false); }
  }
  async function lookup() {
    if (!held || busy) return;
    const stamp = ++generation.current; setBusy(true); setRead(null); setMessage("");
    try {
      const value = await makeAccess(stamp).read("request", held.key);
      if (!inquiryBoundToRequest(value, held))
        throw new InquiryFailure("INVALID_RESPONSE");
      if (!active.current || generation.current !== stamp) return;
      setRead(value); setHeld({ ...held, receipt: value });
      setMessage(value.state === "queued" || value.state === "analyzing" ? "查询正在处理，请稍后读取原记录。" : "已读取当前记录。");
    } catch (error) { if (active.current && generation.current === stamp) setMessage(error instanceof InquiryFailure ? error.message : "暂时无法读取原记录。"); }
    finally { if (active.current && generation.current === stamp) setBusy(false); }
  }
  function newQuery() { generation.current++; locked.current = false; holdWrite(false); setHeld(null); setRead(null); setMessage(""); }
  const result = read?.result;
  const visibleFacts = result?.results.flatMap(item => item.facts).filter(fact => result.evidence_refs.includes(fact.evidence_id)) ?? [];
  return <>
    <Notice title="只读查询" tone="info">本地演示数据 / 离线模型替身；仅支持“库存 商品名或SKU”“销量 商品名或SKU”。查询不会修改订单或库存。</Notice>
    {!enabled || disabledByService ? <Card><p>查询当前未启用。</p></Card> : !shops.length ? <Card><p>当前没有可选的运营店铺，请联系管理员核实权限。</p></Card> :
      <Card title="提出问题">
        {!held ? <><form onSubmit={event => void submit(event)}>
          <label>店铺<select name="shop" required>{shops.map(shop => <option key={shop} value={shop}>{shop}</option>)}</select></label>
          <label>问题<textarea name="question" maxLength={2000} required rows={4} /></label>
          <label>分析报告编号（可选）<input name="context_report_id" placeholder="仅已有分析报告，不支持日报" /></label>
          <p>报告关联仅支持当前有权的既有分析报告；日报不能作为此处的报告上下文。</p>
          <button type="submit" disabled={busy}>提交查询</button>
        </form><form onSubmit={event => void recover(event)}>
          <label>已有请求编号<input name="request_key" required /></label>
          <button type="submit" disabled={busy}>读取已有请求</button>
        </form></> : <>
          <p>已保留本次请求；提交结果不明时可读取同一请求回执。</p>
          <details><summary>原请求编号</summary><p className="daily-id">{held.key}</p></details>
          <button onClick={() => void lookup()} disabled={busy}>读取原请求结果</button>
          {read && ["completed", "failed"].includes(read.state) && <button onClick={newQuery} disabled={busy}>开始新查询</button>}
        </>}
      </Card>}
    {message && <Notice title="查询状态" tone="info">{message}</Notice>}
    {read && <Card title="当前查询结果">
      <p>{read.data_label} · 来源窗口：{read.source_domain.start} 至 {read.source_domain.end}（结束不含）</p>
      {!result ? <p>{read.state === "queued" || read.state === "analyzing" ? "正在查询，尚无结果。" : "当前没有可展示的结果。"}</p> : <>
        <p>{statusText[result.status]}</p>
        {result.status === "complete" && <ul className="inquiry-facts">{visibleFacts.map((fact, index) => <li key={`${fact.evidence_id}-answer-${index}`}>
          商品 {fact.sku_key} · {metricText[fact.metric]}：{fact.value ?? "未报告"} {fact.unit}{fact.currency ? ` ${fact.currency}` : ""}
        </li>)}</ul>}
        {result.status === "clarify" && result.clarification_options.length > 0 && <ul className="inquiry-facts">{result.clarification_options.map(item => <li key={item.sku_key}>{item.label ?? item.sku_key}</li>)}</ul>}
        {visibleFacts.length > 0 && <details><summary>查看依据与时间</summary><ul className="inquiry-facts">{visibleFacts.map((fact, index) => <li key={`${fact.evidence_id}-${index}`}>
          商品 {fact.sku_key} · {metricText[fact.metric]}：{fact.value ?? "未报告"} {fact.unit}{fact.currency ? ` ${fact.currency}` : ""}；观测时间 {fact.as_of}
          {fact.window && <>；窗口 {fact.window.start} 至 {fact.window.end}（结束不含）</>}
        </li>)}</ul></details>}
      </>}
    </Card>}
  </>;
}
