import { test, expect } from "@playwright/test";
import { readDaily, validDailyRead } from "../lib/m3-read-client";
import type { DailyFailure } from "../lib/m3-read-client";
import completed from "./daily-read.fixture.json" with { type: "json" };
const id = "00000000-0000-4000-8000-000000000001";
const pending = {
  schema_version: "p3-web-v1", identity_mode: "session", trace_id: id,
  server_time: "2026-11-03T08:00:00Z",
  daily: {
    schema_version: "p6-m3-web-v1", task_id: id, shop_id: id,
    kind: "daily_report", workflow_version: "p6-daily-report-v1",
    created_at: "2026-11-03T07:00:00Z", updated_at: "2026-11-03T07:30:00Z",
    question_creation_enabled: false,
    question_kinds: ["metric_definition", "metric_evidence", "finding_reason", "data_quality"],
    schedule_enabled: false, delivery_enabled: false,
    state: "queued", failure_code: null, report: null,
  },
};
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status, headers: { "Content-Type": "application/json" },
});
test("冻结日报合同只接受当前任务、明确状态与完整字段", () => {
  expect(validDailyRead(pending, id)).toBe(true);
  expect(validDailyRead(pending, "00000000-0000-4000-8000-000000000002")).toBe(false);
  expect(validDailyRead({ ...pending, daily: { ...pending.daily, report: { complete: true } } }, id)).toBe(false);
  expect(validDailyRead({ ...pending, daily: { ...pending.daily, question_creation_enabled: true } }, id)).toBe(false);
  expect(validDailyRead({ ...pending, daily: { ...pending.daily, metrics: { paid_order_count: 0 } } }, id)).toBe(false);
  expect(validDailyRead({ ...pending, daily: { ...pending.daily, updated_at: "2026-11-04T00:00:00Z" } }, id)).toBe(false);
});
test("后端真实Read DTO样本保留原值、展示值及完整性绑定", () => {
  const taskId = completed.daily.task_id;
  expect(validDailyRead(completed, taskId)).toBe(true);
  expect(validDailyRead({ ...completed, daily: { ...completed.daily, report: { ...completed.daily.report, display: [] } } }, taskId)).toBe(false);
  expect(validDailyRead({ ...completed, daily: { ...completed.daily, report: { ...completed.daily.report, metrics: null } } }, taskId)).toBe(false);
  expect(validDailyRead({ ...completed, daily: { ...completed.daily, report: { ...completed.daily.report, display:
    completed.daily.report.display.map((item) => item.metric_key === "paid_order_total" ? { ...item, value: "999.99" } : item) } } }, taskId)).toBe(false);
  expect(validDailyRead(completed, id)).toBe(false);
});
test("只读请求带会话且不缓存；撤权先清除身份，响应不回填", async () => {
  let invalidated = 0;
  await expect(readDaily("http://127.0.0.1:8000", id, () => invalidated++, async (url, init) => {
    expect(url.pathname).toBe(`/api/v1/daily-reports/${id}`);
    expect(init).toMatchObject({ method: "GET", credentials: "include", cache: "no-store", redirect: "error" });
    return json({}, 403);
  })).rejects.toMatchObject({ code: "ACCESS_DENIED" });
  expect(invalidated).toBe(1);
  await expect(readDaily("http://127.0.0.1:8000", id, () => invalidated++, async () => json(pending)))
    .resolves.toMatchObject({ daily: { task_id: id, state: "queued" } });
  expect(invalidated).toBe(1);
});
test("无权详情与错误形状使用固定安全错误", async () => {
  await expect(readDaily("http://127.0.0.1:8000", id, () => {}, async () => json({}, 404)))
    .rejects.toMatchObject({ code: "RESOURCE_NOT_FOUND" } satisfies Partial<DailyFailure>);
  await expect(readDaily("http://127.0.0.1:8000", id, () => {}, async () => json({ ...pending, actor: id })))
    .rejects.toMatchObject({ code: "INVALID_RESPONSE" } satisfies Partial<DailyFailure>);
  await expect(readDaily("http://127.0.0.1:8000", id, () => {}, async () => json({}, 503)))
    .rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" } satisfies Partial<DailyFailure>);
});
