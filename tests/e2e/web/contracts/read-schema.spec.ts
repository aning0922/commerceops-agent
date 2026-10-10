import { planComplete } from "../../../../frontend/lib/p3-present";
import { test, expect } from "../../../../frontend/tooling/web-test";
import {
  verifyReadResponse,
  readTransport,
} from "../../../../frontend/lib/p3-live-client";
import {
  offlineItem,
  offlineItemList,
  offlineExecution,
  offlineReceipt,
  offlineId,
} from "../../../../frontend/lib/b04-offline-source";
const id = "00000000-0000-4000-8000-000000000001";
const base = {
  schema_version: "p3-web-v1",
  identity_mode: "session",
  server_time: "2026-10-10T12:00:00Z",
  trace_id: id,
};
const deployment = {
  config_version: "offline-v1",
  shop_timezone: "Asia/Shanghai",
  approval_ttl_seconds: 1800,
  revalidation_max_age_seconds: 450,
  max_plan_items: 20,
  recovery_scan_seconds: 10,
  session_absolute_seconds: 28800,
  session_idle_seconds: 1800,
  transport_mode: "local_http",
  source_mode: "mock",
  model_requests_enabled: false,
  external_sender_enabled: false,
};
const config = { ...base, shop_id: id, config: deployment };
test("完整冻结DTO校验：拒绝缺字段/额外actor/假身份/bool整数/unsafe数/坏时间，无coerce/default", () => {
  expect(verifyReadResponse("GET", "/api/v1/config", 200, config)).toBe(true);
  expect(verifyReadResponse("GET", "/api/v1/config", 200, { ...base })).toBe(
    false,
  );
  expect(
    verifyReadResponse("GET", "/api/v1/config", 200, { ...config, actor: id }),
  ).toBe(false);
  expect(
    verifyReadResponse("GET", "/api/v1/config", 200, {
      ...config,
      identity_mode: "mock",
    }),
  ).toBe(false);
  expect(
    verifyReadResponse("GET", "/api/v1/config", 200, {
      ...config,
      config: { ...deployment, max_plan_items: true },
    }),
  ).toBe(false);
  expect(
    verifyReadResponse("GET", "/api/v1/config", 200, {
      ...config,
      config: {
        ...deployment,
        session_absolute_seconds: Number.MAX_SAFE_INTEGER + 1,
      },
    }),
  ).toBe(false);
  expect(
    verifyReadResponse("GET", "/api/v1/config", 200, {
      ...config,
      server_time: "yesterday",
    }),
  ).toBe(false);
  expect(config).toEqual({ ...base, shop_id: id, config: deployment });
});
test("完整22操作DTO仍拒绝错误形状及错误envelope隐藏对象", () => {
  const error = {
    schema_version: "p3-web-v1",
    server_time: null,
    trace_id: id,
    error: {
      code: "RESOURCE_NOT_FOUND",
      safe_message: "固定错误",
      retryable: false,
      receipt: null,
    },
  };
  expect(verifyReadResponse("GET", `/api/v1/tasks/${id}`, 404, error)).toBe(
    true,
  );
  expect(
    verifyReadResponse("GET", `/api/v1/tasks/${id}`, 404, {
      ...error,
      task_id: id,
    }),
  ).toBe(false);
  expect(
    verifyReadResponse("GET", "/api/v1/replenishment-items", 200, config),
  ).toBe(false);
  expect(
    verifyReadResponse("GET", `/api/v1/tasks/${id}/execution`, 200, config),
  ).toBe(false);
  expect(
    verifyReadResponse("POST", `/api/v1/approvals/${id}/decision`, 200, config),
  ).toBe(false);
  expect(verifyReadResponse("POST", "/api/v1/tasks", 202, config)).toBe(false);
});

test("已审22操作放行，未知操作/方法仍before-send零请求；read/T1/T3保留", async () => {
  let calls = 0;
  const transport = readTransport(async () => {
    calls++;
    return new Response("{}");
  });
  for (const [method, path] of [
    ["POST", `/api/v1/tasks/${id}/execution`],
    ["DELETE", `/api/v1/replenishment-items/${id}`],
    ["GET", `/api/v1/replenishment-items/${id}/resolve`],
    ["POST", `/api/v1/approvals/${id}/retry`],
  ])
    await expect(
      transport(new URL("https://test.invalid" + path), { method }),
    ).rejects.toThrow("outside reviewed");
  expect(calls).toBe(0);
  for (const [method, path] of [
    ["POST", "/api/v1/auth/login"],
    ["GET", `/api/v1/tasks/${id}`],
    ["POST", "/api/v1/tasks"],
    ["POST", `/api/v1/approvals/${id}/decision`],
    ["GET", `/api/v1/tasks/${id}/execution`],
    ["GET", "/api/v1/replenishment-items"],
    ["GET", `/api/v1/replenishment-items/${id}`],
    ["POST", `/api/v1/replenishment-items/${id}/resolve`],
  ])
    await transport(new URL("https://test.invalid" + path), { method });
  expect(calls).toBe(8);
  expect(
    verifyReadResponse(
      "GET",
      `/api/v1/tasks/${offlineId(102)}/execution`,
      200,
      offlineExecution(),
    ),
  ).toBe(true);
  expect(
    verifyReadResponse(
      "GET",
      "/api/v1/replenishment-items",
      200,
      offlineItemList(),
    ),
  ).toBe(true);
  expect(
    verifyReadResponse(
      "GET",
      `/api/v1/replenishment-items/${offlineId(1)}`,
      200,
      offlineItem(),
    ),
  ).toBe(true);
  const receipt = offlineReceipt(offlineItem(), {
    schema_version: "p3-web-v1",
    request_key: offlineId(500),
    action: "close",
    reason: "离线原因",
    expected_version: 1,
  });
  expect(
    verifyReadResponse(
      "POST",
      `/api/v1/replenishment-items/${offlineId(1)}/resolve`,
      200,
      receipt,
    ),
  ).toBe(true);
  expect(
    verifyReadResponse(
      "GET",
      `/api/v1/replenishment-items/${offlineId(1)}`,
      200,
      { ...offlineItem(), actor: id },
    ),
  ).toBe(false);
});

test("披露绑定拒绝同数量但换SKU/在途/建议事实及重复条目，原合法20项保留", async () => {
  const items = Array.from({ length: 20 }, (_, n) => ({
    sku_key: `sku-${n}`,
    stock_pool_key: `pool-${n}`,
    quantity: 100,
    raw_inbound_units: n === 19 ? null : 0,
    effective_inbound_units: 0,
    fact: {
      sku_key: `sku-${n}`,
      stock_pool_key: `pool-${n}`,
      suggested_units: 100,
      inbound_units: n === 19 ? null : 0,
      effective_inbound_units: 0,
    },
  }));
  const plan = {
    disclosure_complete: true,
    item_count: 20,
    total_units: 2000,
    items,
  };
  type Plan = Parameters<typeof planComplete>[0];
  expect(planComplete(plan as unknown as Plan)).toBe(true);
  expect(
    planComplete({ ...plan, items: items.slice(1) } as unknown as Plan),
  ).toBe(false);
  expect(
    planComplete({
      ...plan,
      items: [items[0], ...items.slice(0, 19)],
    } as unknown as Plan),
  ).toBe(false);
  expect(
    planComplete({
      ...plan,
      items: items.map((x, n) =>
        n === 19 ? { ...x, raw_inbound_units: 0 } : x,
      ),
    } as unknown as Plan),
  ).toBe(false);
  expect(
    planComplete({
      ...plan,
      items: items.map((x, n) =>
        n === 19 ? { ...x, fact: { ...x.fact, sku_key: "other" } } : x,
      ),
    } as unknown as Plan),
  ).toBe(false);
});
