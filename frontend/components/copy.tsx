"use client";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { A01ReadClient } from "../lib/p3-live-client";
import { CopyFailure, mayReview, validCreate, validReview } from "../lib/p6-copy-client";
import type { Candidate, CreateCopy, Decision, ReviewCopy } from "../lib/p6-copy-client";
import { Card, Notice } from "./ui";

type Pending = { kind: "create"; input: CreateCopy } | { kind: "review"; candidate: string; input: ReviewCopy };
export function Copy({ client, principal, operators, approvers, current }: { client: A01ReadClient; principal: string; operators: readonly string[]; approvers: readonly string[]; current: () => boolean }) {
  const active = useRef(false), epoch = useRef(0), locked = useRef(false), running = useRef(false);
  const [verifiedReceipt, setVerifiedReceipt] = useState(false);
  const [available, setAvailable] = useState(false), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [item, setItem] = useState<Candidate | null>(null), [preview, setPreview] = useState<Pending | null>(null), [held, setHeld] = useState<Pending | null>(null), [decision, setDecision] = useState<Decision | null>(null);
  const storage = `commerceops-copy-pending-v1:${principal}`;
  useEffect(() => { active.current = true; try { const raw = sessionStorage.getItem(storage); if (raw) { const x = JSON.parse(raw) as Pending; if (x.kind === "create" && validCreate(x.input) || x.kind === "review" && validReview(x.input) && /^[0-9a-f-]{36}$/.test(x.candidate)) { setHeld(x); locked.current = true; } else { locked.current = true; setMessage("原请求无法安全解析，写入已停用。"); } } } catch { locked.current = true; setMessage("原请求无法安全解析，写入已停用。"); }
    return () => { active.current = false; epoch.current++; }; }, [storage]);
  const good = (n: number) => active.current && epoch.current === n && current();
  function api(n: number) { if (!client.copyAccess) throw new CopyFailure("DENIED"); return client.copyAccess(() => good(n)); }
  async function check() { if (busy || running.current) return; running.current = true; const n = ++epoch.current; setBusy(true); setMessage("");
    try { const ok = await api(n).probe(crypto.randomUUID()); if (good(n)) { setAvailable(ok); if (!ok) setMessage("接口未确认可用。"); } }
    catch { if (good(n)) { setAvailable(false); setMessage("接口未确认可用，请稍后重试。"); } }
    finally { running.current = false; if (good(n)) setBusy(false); } }
  function prepareCreate(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!available || locked.current || !operators.length) return; const f = new FormData(event.currentTarget);
    const input: CreateCopy = { schema_version: "p6-copy-web-v1", shop_id: String(f.get("shop")), registry_id: String(f.get("registry")).trim().toLowerCase(), registry_digest: String(f.get("digest")).trim(), product_source_id: String(f.get("product")).trim().toLowerCase(), query_ref: String(f.get("query")).trim(), reviewer_id: String(f.get("reviewer")).trim().toLowerCase(), request_key: crypto.randomUUID() };
    if (!operators.includes(input.shop_id) || !validCreate(input)) { setMessage("请核对店铺、来源、查询引用和审核人。"); return; } setPreview({ kind: "create", input }); setMessage(""); }
  async function read(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!available || busy || running.current) return; const id = String(new FormData(event.currentTarget).get("candidate") ?? "").trim().toLowerCase(); running.current = true; const n = ++epoch.current; setBusy(true); setItem(null); setMessage("");
    try { const x = await api(n).read(id); if (good(n)) setItem(x); } catch (e) { if (good(n)) setMessage(e instanceof CopyFailure ? e.message : "无法读取候选。"); } finally { running.current = false; if (good(n)) setBusy(false); } }
  function prepareReview(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!item || locked.current || !mayReview(item, principal, approvers)) return;
    const f = new FormData(event.currentTarget); const input: ReviewCopy = { schema_version: "p6-copy-web-v1", candidate_version: "v1", candidate_hash: item.candidate.candidate_hash, request_key: crypto.randomUUID(), action: String(f.get("action")) as "approve" | "reject", reason: String(f.get("reason") ?? "") };
    if (!validReview(input)) { setMessage("请选择决定并填写原因。"); return; } setPreview({ kind: "review", candidate: item.candidate.candidate_id, input }); setMessage(""); }
  async function send() { if (!preview || busy || locked.current || running.current) return; running.current = true; const n = ++epoch.current; setBusy(true); setMessage("");
    try { const a = api(n); if (!await a.probe(crypto.randomUUID())) throw new CopyFailure("UNAVAILABLE");
      if (preview.kind === "create" && !operators.includes(preview.input.shop_id)) throw new CopyFailure("DENIED");
      if (preview.kind === "review") { const fresh = await a.read(preview.candidate); if (!mayReview(fresh, principal, approvers) || fresh.candidate.candidate_hash !== preview.input.candidate_hash) throw new CopyFailure("INVALID"); }
      if (!good(n)) return;
      sessionStorage.setItem(storage, JSON.stringify(preview)); setVerifiedReceipt(false); setItem(null); setDecision(null); locked.current = true; setHeld(preview); setPreview(null);
      if (preview.kind === "create") await a.create(preview.input); else await a.review(preview.candidate, preview.input);
      if (good(n)) setMessage("请求已发送，请查询原键回执核对结果。");
    } catch (e) { if (good(n)) setMessage(e instanceof CopyFailure ? e.message : "结果待核实；请查询原请求键。"); } finally { running.current = false; if (good(n)) setBusy(false); } }
  async function lookup() { if (!held || busy || running.current) return; running.current = true; const n = ++epoch.current; setBusy(true); setMessage("");
    try { const a = api(n); if (held.kind === "create") { const d = await a.candidateReceipt(held.input); if (good(n)) { if (d && d.candidate.owner_id !== principal) throw new CopyFailure("INVALID"); setItem(d); setVerifiedReceipt(d !== null); setMessage(d ? "已读取原候选；查询引用由服务端核验，回执未返回原引用。" : "原请求仍为 UNKNOWN；请稍后只读续查。"); } }
      else { const d = await a.reviewReceipt(held.candidate, held.input); if (good(n)) { setDecision(d); setVerifiedReceipt(d.state !== "UNKNOWN"); setMessage(d.state === "UNKNOWN" ? "原决定仍为 UNKNOWN；请稍后只读续查。" : "已读取原决定回执。"); } }
    } catch (e) { if (good(n)) setMessage(e instanceof CopyFailure ? e.message : "原请求暂不可读取。"); } finally { running.current = false; if (good(n)) setBusy(false); } }
  const resolved = verifiedReceipt && (held?.kind === "create" ? item !== null : !!decision && decision.state !== "UNKNOWN");
  function clear() { if (!resolved) return; sessionStorage.removeItem(storage); locked.current = false; setHeld(null); setDecision(null); setVerifiedReceipt(false); setMessage(""); }
  const canReview = item && mayReview(item, principal, approvers);
  return <><Notice title="内部文案候选" tone="info">使用服务器登记的合成向量与确定性模板；不调用模型、不外发。草稿仅供内部使用。</Notice><Card>
    {!available && !held && <button disabled={busy} onClick={() => void check()}>检查服务是否可用</button>}
    {!held && locked.current && <p>保留的原请求无法安全解析，写入已停用。</p>}
    {held ? <><p>原请求键：<span className="daily-id">{held.input.request_key}</span>；未核实前仅查询原键，不重发。</p><button disabled={busy} onClick={() => void lookup()}>读取原请求回执</button>{decision && <p>决定状态：{decision.state}{decision.draft_id && ` · 内部草稿 ${decision.draft_id}`}</p>}{resolved && <button onClick={clear}>完成原回执核对</button>}</> : available && !locked.current && <>
      {operators.length > 0 && !preview && <form onSubmit={prepareCreate}><h3>创建内部候选</h3><label>店铺<select name="shop">{operators.map(x => <option key={x}>{x}</option>)}</select></label><label>知识库 registry UUID<input name="registry" required /></label><label>registry 摘要<input name="digest" required /></label><label>商品来源 UUID<input name="product" required /></label><label>服务器登记的 query_ref<input name="query" required /></label><label>指派审核人 UUID<input name="reviewer" required /></label><button disabled={busy}>预览候选请求</button></form>}
      {!preview && <form onSubmit={e => void read(e)}><label>候选编号<input name="candidate" required /></label><button disabled={busy}>读取候选或内部草稿</button></form>}
      {preview && <><p>固定请求：确认前核对原键与全部参数。</p><pre className="daily-id">{JSON.stringify(preview, null, 2)}</pre><button disabled={busy} onClick={() => void send()}>确认提交一次</button><button onClick={() => setPreview(null)}>返回修改</button></>}
    </>}
  </Card>{item && <Card title={item.state === "saved" ? "内部草稿" : "候选详情"}><p>状态：{item.state} · 来源当前{item.source_current ? "有效" : "不可用"} · 候选 {item.candidate.candidate_id}</p><p>模板结果，合成向量；服务端核验来源，前端没有独立重放向量检索。</p><p className="daily-id">{item.candidate.text}</p><p>摘要：{item.candidate.candidate_hash} · 截止：{item.candidate.expires_at}</p>{item.draft_id && <p>内部草稿编号：{item.draft_id}</p>}<ul>{item.candidate.claims.map(c => <li key={c.claim_id}>{c.kind}: {c.text}<details><summary>查看来源</summary>{c.product && <p>商品证据 {c.product.evidence_id} · SKU {c.product.snapshot.sku} · 来源版本 {c.product.snapshot.source_version}</p>}{c.sop && <p>资料 {c.sop.chunk.document.title} · 版本 {c.sop.chunk.document.document_version} · 段落 {c.sop.chunk.section} · 证据 {c.sop.evidence_id}</p>}</details></li>)}</ul>
    {canReview && !held && !preview && <form onSubmit={prepareReview}><label>审核决定<select name="action"><option value="approve">批准并保存内部草稿</option><option value="reject">拒绝</option></select></label><label>审核原因<textarea name="reason" required maxLength={500} /></label><button disabled={busy}>预览审核决定</button></form>}</Card>}
    {message && <Notice title="文案操作状态" tone="info">{message}</Notice>}</>;
}
