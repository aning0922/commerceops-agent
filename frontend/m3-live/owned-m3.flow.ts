// Explicit new-owned live window only. No response fulfillment, retry, or service startup.
import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { validDailyRead } from "../lib/m3-read-client";
import { validEvidence, validQuestion } from "../lib/p6-daily-s3-read";
import { validInquiryRead } from "../lib/p6-inquiry-client";
import { validCandidate } from "../lib/p6-copy-client";
import { loadOwned, uuid } from "./owned-m3-input";
import { validOwnedCopyPreview } from "./owned-copy-preview";
import { get, go, noOverflow, post, response, session } from "./owned-m3-harness";
import type { Session } from "./owned-m3-harness";
const { window: w, seed: seed, stop, record, verify, close } = loadOwned();
test.afterEach(async ({}, info) => { record({ event: "test_finished", title: info.title, status: info.status }); });
test.afterAll(async () => { close(); });
const q = (value: Record<string,string>) => `?${new URLSearchParams(value)}`;
async function fixedPreview(page: Page): Promise<Record<string, any>> { const text = await page.locator("pre").last().textContent(); if (!text) throw new Error("Missing fixed preview"); return JSON.parse(text); }
function exactPreview(s: Session, path: string, value: unknown) { post(s, path, body => { try { return JSON.stringify(JSON.parse(body ?? "")) === JSON.stringify(value); } catch { return false; } }); }
async function receipt(s: Session, path: string, search: string) { get(s, path, search); const pending = response(s.page, w.api_origin, path); await s.page.getByRole("button", { name: "读取原请求回执" }).click(); const r = await pending; expect(r.status()).toBe(200); const value = await r.json();
  const message = path.includes("/review-receipts/") ? "已读取原决定回执。" : path.includes("/copy/candidate-requests/") ? "已读取原候选；查询引用由服务端核验，回执未返回原引用。" : "已核对原请求回执；受理不代表报告或追问已完成。";
  await expect(s.page.getByText(message)).toBeVisible(); return value; }

test("owned daily creation, original receipts, template question and evidence pages", async ({ browser }) => {
 const s = await session(browser, w, stop, seed.owner, seed.organization_id, [seed.daily_shop_id, seed.inquiry_shop_id], record, verify);
 try {
  await go(s, "/daily-reports"); await s.page.locator('select').first().selectOption(seed.daily_shop_id); const cp = "/api/v1/daily-capabilities", cq = q({ shop_id: seed.daily_shop_id }); get(s, cp, cq, 2);
  const capResponse = response(s.page, w.api_origin, cp); await s.page.getByRole("button", { name: "读取当前店铺能力" }).click(); const cap = await (await capResponse).json(); expect(cap.capabilities.shop_id).toBe(seed.daily_shop_id); expect(cap.capabilities.enabled).toBe(true); expect(cap.capabilities.source.timezone).toBe(seed.daily.timezone); await s.page.locator('input[name="day"]').fill(seed.daily.day);
  await s.page.getByRole("button", { name: "预览固定请求" }).click(); const input = await fixedPreview(s.page);
  expect(input.shop_id).toBe(seed.daily_shop_id); expect(input.business_day).toBe(seed.daily.day); expect(input.source_config_version).toBe(seed.daily.source_version); expect(uuid.test(input.request_key)).toBe(true); await noOverflow(s.page);
  const createPath = "/api/v1/daily-reports"; record({ event: "before_post", operation: "daily_report.create", input }); exactPreview(s, createPath, input); const accepted = s.dropNext(createPath); await s.page.getByRole("button", { name: "确认提交一次" }).click(); const acceptedStatus = await accepted; record({ event: "response_dropped", operation: "daily_report.create", status: acceptedStatus }); expect(acceptedStatus).toBe(202); await expect(s.page.getByText("提交结果待核实；只可查询原请求。")).toBeVisible();
  const rr = await receipt(s, `${createPath}/requests/${input.request_key}`, cq); expect(rr.receipt.request_key).toBe(input.request_key); expect(rr.receipt.operation).toBe("daily_report.create"); expect(rr.receipt.business_day).toBe(seed.daily.day);
  record({ event: "receipt", operation: "daily_report.create", receipt: rr.receipt }); const task = rr.receipt.task_id; expect(uuid.test(task)).toBe(true); const web = `/daily-reports/${task}`, path = `/api/v1/daily-reports/${task}`;
  let report: any = null;
  for (let i = 0; i < seed.max_poll; i++) { get(s, path); const next = response(s.page, w.api_origin, path); await go(s, web); const r = await next; const raw: unknown = await r.json(); if (!validDailyRead(raw, task)) throw new Error("Daily DTO rejected"); if (raw.daily.state === "completed") { report = raw.daily.report; break; } await s.page.waitForTimeout(1000); }
  if (!report) throw new Error("Daily not completed within bounded polls"); expect(report.evidence_count).toBeGreaterThanOrEqual(seed.daily.minimum_evidence);
  get(s, cp, cq, 2); await s.page.getByRole("button", { name: "读取当前店铺能力" }).first().click();
  await s.page.locator('select[name="kind"]').selectOption("metric_evidence"); await s.page.locator('input[name="target"]').fill(seed.daily.metric_key);
  await s.page.getByRole("button", { name: "预览固定请求" }).click(); const question = await fixedPreview(s.page); expect(question.report_id).toBe(report.report_id); expect(question.snapshot_id).toBe(report.snapshot_id); expect(question.facts_hash).toBe(report.facts_hash);
  const questionPath = `${path}/questions`; record({ event: "before_post", operation: "daily_question.create", parent_task_id: task, input: question }); exactPreview(s, questionPath, question); const qr = s.dropNext(questionPath); await s.page.getByRole("button", { name: "确认提交一次" }).click(); const questionStatus = await qr; record({ event: "response_dropped", operation: "daily_question.create", status: questionStatus }); expect(questionStatus).toBe(202); await expect(s.page.getByText("提交结果待核实；只可查询原请求。")).toBeVisible();
  const questionReceipt = await receipt(s, `${questionPath}/requests/${question.request_key}`, q({ shop_id: seed.daily_shop_id, report_id: report.report_id })); expect(questionReceipt.receipt.operation).toBe("daily_question.create"); expect(questionReceipt.receipt.parent_task_id).toBe(task); expect(questionReceipt.receipt.question.kind).toBe("metric_evidence");
  record({ event: "receipt", operation: "daily_question.create", receipt: questionReceipt.receipt }); const questionId = questionReceipt.receipt.task_id; expect(uuid.test(questionId)).toBe(true); await s.page.getByRole("button", { name: "完成本次回执核对" }).click();
  const binding = { task, report: report.report_id, snapshot: report.snapshot_id, contentHash: report.content_hash, factsHash: report.facts_hash, evidenceCount: report.evidence_count };
  const evidencePath = `${path}/evidence`, first = q({report_id: report.report_id}); get(s, evidencePath, first); const ep = response(s.page, w.api_origin, evidencePath); await s.page.getByRole("button", { name: "读取报告证据" }).click(); const firstEvidence: unknown = await (await ep).json(); if (!validEvidence(firstEvidence, binding)) throw new Error("Evidence binding rejected"); let ev = firstEvidence.evidence; let count = ev.citations.length; const seen = new Set(ev.citations.map((x: any) => x.citation_id)); const cursors = new Set<string>();
  while (ev.next_cursor) { if (cursors.has(ev.next_cursor) || cursors.size >= report.evidence_count) throw new Error("Repeated or excessive evidence cursor"); cursors.add(ev.next_cursor); const search = q({report_id: report.report_id, cursor: ev.next_cursor}); get(s, evidencePath, search); const next = response(s.page, w.api_origin, evidencePath); await s.page.getByRole("button", { name: "读取下一页证据" }).click(); const pageEvidence: unknown = await (await next).json(); if (!validEvidence(pageEvidence, binding)) throw new Error("Evidence page rejected"); ev = pageEvidence.evidence; for (const c of ev.citations) { expect(seen.has(c.citation_id)).toBe(false); seen.add(c.citation_id); count++; } if (count > report.evidence_count) throw new Error("Evidence exceeded bound"); }
  expect(count).toBe(report.evidence_count); expect(count).toBeGreaterThan(50);
  const questionGet = `${questionPath}/${questionId}`; await s.page.locator('input[name="question_id"]').fill(questionId);
  let result: any = null; for (let i = 0; i < seed.max_poll; i++) { get(s, questionGet); const next = response(s.page, w.api_origin, questionGet); await s.page.getByRole("button", { name: "读取已有追问" }).click(); const wire: unknown = await (await next).json(); if (!validQuestion(wire, binding, questionId)) throw new Error("Question binding rejected"); result = wire.question; if (result.state === "completed") break; await s.page.waitForTimeout(1000); }
  expect(result?.state).toBe("completed"); expect(result.answer.report_id).toBe(report.report_id); await expect(s.page.getByText("本报告模板解释 · 未调用模型。")).toBeVisible(); await noOverflow(s.page); expect(s.guard.posts(createPath)).toBe(1); expect(s.guard.posts(questionPath)).toBe(1);
 } finally { await s.context.close(); }
});

test("owned inquiry uses actual fixture facts and reads original key and task", async ({ browser }) => {
 const s = await session(browser, w, stop, seed.owner, seed.organization_id, [seed.daily_shop_id, seed.inquiry_shop_id], record, verify);
 try {
  await go(s, "/inquiries"); await s.page.locator('select[name="shop"]').selectOption(seed.inquiry_shop_id); await s.page.locator('textarea[name="question"]').fill(seed.inquiry.question);
  const path = "/api/v1/readonly-inquiries"; let original = "";
  post(s, path, body => { try { const x = JSON.parse(body ?? ""); if (Object.keys(x).sort().join(",") !== "context_report_id,question,request_key,schema_version,shop_id" || x.schema_version !== "p6-inquiry-web-v1" || x.shop_id !== seed.inquiry_shop_id || x.question !== seed.inquiry.question || x.context_report_id !== null || !uuid.test(x.request_key)) return false; original = x.request_key; record({ event: "before_post", operation: "inquiry.create", input: x }); return true; } catch { return false; } });
  const created = s.dropNext(path); await s.page.getByRole("button", { name: "提交查询" }).click(); const inquiryStatus = await created; record({ event: "response_dropped", operation: "inquiry.create", status: inquiryStatus }); expect(inquiryStatus).toBe(202); expect(original).not.toBe(""); await expect(s.page.getByText("提交结果待核实，请查询原请求回执。")).toBeVisible();
  const byKey = `${path}/requests/${original}`; let result: any = null;
  for (let i = 0; i < seed.max_poll; i++) { get(s, byKey); const next = response(s.page, w.api_origin, byKey); await s.page.getByRole("button", { name: "读取原请求结果" }).click(); const body: unknown = await (await next).json(); if (!validInquiryRead(body)) throw new Error("Inquiry DTO rejected"); if (body.state === "completed" || body.state === "failed") { result = body; break; } await s.page.waitForTimeout(1000); }
  if (!result || result.state !== "completed" || result.result?.status !== "complete") throw new Error("Inquiry did not complete with facts");
  record({ event: "receipt", operation: "inquiry.create", request_key: original, task_id: result.task_id, state: result.state }); expect(result.request_key).toBe(original); expect(uuid.test(result.task_id)).toBe(true);
  expect(result.result.results.flatMap((x: any) => x.facts).some((x: any) => x.sku_key === seed.inquiry.sku && x.value === seed.inquiry.expected_value)).toBe(true);
  await expect(s.page.getByText(seed.inquiry.sku, { exact: false }).first()).toBeVisible(); await expect(s.page.getByText(seed.inquiry.expected_value, { exact: false }).first()).toBeVisible();
  const taskPath = `${path}/${result.task_id}`; get(s, taskPath); const fetched = await s.page.evaluate(async ({ origin, endpoint }) => { const r = await fetch(origin + endpoint, { credentials: "include", cache: "no-store" }); return { status: r.status, body: await r.json() }; }, { origin: w.api_origin, endpoint: taskPath });
  expect(fetched.status).toBe(200); if (!validInquiryRead(fetched.body)) throw new Error("Inquiry task DTO rejected"); expect(fetched.body.request_key).toBe(original); await noOverflow(s.page); expect(s.guard.posts(path)).toBe(1);
 } finally { await s.context.close(); }
});

async function checkCopy(s: Session) { s.guard.allowCopyProbe(); await s.page.getByRole("button", { name: "检查服务是否可用" }).click(); await expect(s.page.getByRole("button", { name: "预览候选请求" }).or(s.page.getByRole("button", { name: "读取候选或内部草稿" })).first()).toBeVisible(); }
const copyKeys = new Set<string>();
async function createCopy(s: Session) {
 const page = s.page, copy = seed.copy;
 await page.locator('select[name="shop"]').selectOption(seed.copy.shop_id); await page.locator('input[name="registry"]').fill(copy.registry_id); await page.locator('input[name="digest"]').fill(copy.registry_digest); await page.locator('input[name="product"]').fill(copy.product_source_id); await page.locator('input[name="query"]').fill(copy.query_ref); await page.locator('input[name="reviewer"]').fill(copy.reviewer_id);
 await page.getByRole("button", { name: "预览候选请求" }).click(); const fixed = await fixedPreview(page); if (!validOwnedCopyPreview(fixed, copy)) throw new Error("Copy preview does not match owned seed and schema"); if (copyKeys.has(fixed.input.request_key)) throw new Error("Copy request key reused"); copyKeys.add(fixed.input.request_key); await noOverflow(page);
 s.guard.allowCopyProbe(); record({ event: "before_post", operation: "copy.create", input: fixed.input }); const path = "/api/v1/copy/candidates"; const frozen = JSON.stringify(fixed.input);
 post(s, path, body => { try { const input: unknown = JSON.parse(body ?? ""); return JSON.stringify(input) === frozen && validOwnedCopyPreview({ kind: "create", input }, copy); } catch { return false; } }); const created = s.dropNext(path); await page.getByRole("button", { name: "确认提交一次" }).click(); const status = await created; record({ event: "response_dropped", operation: "copy.create", status }); expect(status).toBe(202); await expect(page.getByText("结果待核实；请只查询原请求键。")).toBeVisible();
 const keyPath = `/api/v1/copy/candidate-requests/${fixed.input.request_key}`; const body = await receipt(s, keyPath, ""); if (!validCandidate(body)) throw new Error("Copy candidate DTO rejected"); expect(body.data.candidate.owner_id).toBe(seed.owner.principal_id); expect(body.data.candidate.reviewer_id).toBe(copy.reviewer_id); expect(body.data.candidate.retrieval.scope.shop_id).toBe(seed.copy.shop_id); expect(body.data.candidate.retrieval.scope.organization_id).toBe(seed.organization_id); expect(body.data.state).toBe("awaiting_review"); record({ event: "receipt", operation: "copy.create", request_key: fixed.input.request_key, candidate_id: body.data.candidate.candidate_id, candidate_hash: body.data.candidate.candidate_hash });
 await page.getByRole("button", { name: "完成原回执核对" }).click(); return body.data.candidate.candidate_id;
}
async function readCopy(s: Session, id: string) { const path = `/api/v1/copy/candidates/${id}`; get(s, path); const next = response(s.page, w.api_origin, path); await s.page.locator('input[name="candidate"]').fill(id); await s.page.getByRole("button", { name: "读取候选或内部草稿" }).click(); const r = await next; expect(r.status()).toBe(200); const data: unknown = await r.json(); if (!validCandidate(data) || data.data.candidate.candidate_id !== id) throw new Error("Copy candidate binding rejected"); return data.data; }
async function reviewCopy(s: Session, id: string, action: "approve" | "reject") {
 const current = await readCopy(s, id); expect(current.candidate.reviewer_id).toBe(seed.reviewer.principal_id); expect(current.state).toBe("awaiting_review");
 await s.page.locator('select[name="action"]').selectOption(action); await s.page.locator('textarea[name="reason"]').fill("核对合成来源及候选内容"); await s.page.getByRole("button", { name: "预览审核决定" }).click();
 const preview = await fixedPreview(s.page); expect(preview.candidate).toBe(id); expect(preview.input.candidate_hash).toBe(current.candidate.candidate_hash); expect(preview.input.action).toBe(action); await noOverflow(s.page);
 s.guard.allowCopyProbe(); record({ event: "before_post", operation: "copy.review", candidate_id: id, input: preview.input }); get(s, `/api/v1/copy/candidates/${id}`); const path = `/api/v1/copy/candidates/${id}/review`; exactPreview(s, path, preview.input); const sent = s.dropNext(path); await s.page.getByRole("button", { name: "确认提交一次" }).click(); const status = await sent; record({ event: "response_dropped", operation: "copy.review", status }); expect(status).toBe(200); await expect(s.page.getByText("结果待核实；请只查询原请求键。")).toBeVisible(); expect(s.guard.posts(path)).toBe(1);
 const rp = `/api/v1/copy/candidates/${id}/review-receipts/${preview.input.request_key}`; const got = await receipt(s, rp, q({ candidate_hash: current.candidate.candidate_hash })); expect(got.data.request_key).toBe(preview.input.request_key); expect(got.data.candidate_id).toBe(id); expect(got.data.candidate_hash).toBe(current.candidate.candidate_hash); expect(got.data.state).toBe(action === "approve" ? "saved" : "rejected"); expect(got.data.publication_allowed).toBe(false);
 record({ event: "receipt", operation: "copy.review", receipt: got.data }); if (action === "approve") expect(uuid.test(got.data.draft_id)).toBe(true); else expect(got.data.draft_id).toBeNull(); await s.page.getByRole("button", { name: "完成原回执核对" }).click(); return got.data;
}

test("owned copy candidates are reviewed by assigned approver and stored internally", async ({ browser }) => {
 const owner = await session(browser, w, stop, seed.owner, seed.organization_id, [seed.daily_shop_id, seed.inquiry_shop_id], record, verify); let reviewer: Session | undefined, unassigned: Session | undefined, outside: Session | undefined;
 try {
  await go(owner, "/copy"); await checkCopy(owner); const approved = await createCopy(owner); const rejected = await createCopy(owner); expect(approved).not.toBe(rejected);
  unassigned = await session(browser, w, stop, seed.unassigned, seed.organization_id, [seed.daily_shop_id, seed.inquiry_shop_id], record, verify); await go(unassigned, "/copy"); await checkCopy(unassigned);
  outside = await session(browser, w, stop, seed.outside, seed.organization_id, [seed.daily_shop_id, seed.inquiry_shop_id], record, verify); await go(outside, "/copy"); await checkCopy(outside);
  for (const denied of [unassigned, outside]) { const path = `/api/v1/copy/candidates/${approved}`; get(denied, path); const next = response(denied.page, w.api_origin, path); await denied.page.locator('input[name="candidate"]').fill(approved); await denied.page.getByRole("button", { name: "读取候选或内部草稿" }).click(); expect((await next).status()).toBe(404); await expect(denied.page.getByRole("button", { name: "预览审核决定" })).toHaveCount(0); }
  reviewer = await session(browser, w, stop, seed.reviewer, seed.organization_id, [seed.daily_shop_id, seed.inquiry_shop_id], record, verify); await go(reviewer, "/copy"); await checkCopy(reviewer);
  const saved = await reviewCopy(reviewer, approved, "approve"); await reviewCopy(reviewer, rejected, "reject");
  const draft = await readCopy(owner, approved); expect(draft.state).toBe("saved"); expect(draft.draft_id).toBe(saved.draft_id); expect(owner.guard.posts("/api/v1/copy/candidates")).toBe(2); await expect(owner.page.getByRole("heading", { name: "内部草稿" })).toBeVisible(); await noOverflow(owner.page);
 } finally { await outside?.context.close(); await unassigned?.context.close(); await reviewer?.context.close(); await owner.context.close(); }
});
