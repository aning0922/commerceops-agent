// Deterministic DTO fixtures and injected responses, exclusively for explicit B04 Mock preview/tests.
// No fetch, browser identity, server writes, persistence, provider, or authoritative hash algorithm.
import type { DTO } from "./p3-present";
import { P3Client } from "./p3-transport";
import type { FetchTransport } from "./p3-transport";
import { validItemDTO } from "./p3-item-contract";
export const offlineId = (number: number) =>
  `00000000-0000-4000-8000-${number.toString(16).padStart(12, "0")}`;
export const offlineEnvelope = {
  schema_version: "p3-web-v1",
  identity_mode: "session",
  server_time: "2026-10-11T01:00:00Z",
  trace_id: offlineId(99),
} as const;
export const offlineScenarios = [
  "ready",
  "unknown",
  "missing",
  "conflict",
  "state_conflict",
  "bad_receipt",
  "revoked",
  "not_found",
  "terminal",
  "readonly",
] as const;
export type OfflineScenario = (typeof offlineScenarios)[number];
export function offlineSync(
  state: DTO["SyncRead"]["state"],
  number = 1,
): DTO["SyncRead"] {
  return {
    state,
    sender_enabled: false,
    projections: [
      {
        aggregate_id: offlineId(number),
        projection_version: 1,
        outbox_status:
          state === "failed"
            ? "dead"
            : state === "unknown"
              ? "unknown"
              : "pending",
        state,
        source_mode: "controlled_stub",
        as_of: offlineEnvelope.server_time,
        error_code: state === "failed" ? "CONTROLLED_SYNC_FAILURE" : null,
      },
    ],
  };
}
export function offlineItem(number = 1): DTO["ItemRead"] {
  return {
    ...offlineEnvelope,
    item: {
      item_id: offlineId(number),
      shop_id: offlineId(101),
      sku_key: `sku/离线长中文商品完整披露用于窄屏验证/${number}`,
      stock_pool_key: `pool/offline/${number}`,
      quantity: 100,
      state: "open",
      version: 1,
      created_at: offlineEnvelope.server_time,
      updated_at: offlineEnvelope.server_time,
      sync: offlineSync(number === 20 ? "unknown" : "failed", number),
    },
    resolution: null,
    visible_source_task_id: offlineId(102),
    visible_plan_id: offlineId(103),
    can_resolve: true,
    disabled_reasons: [],
  };
}
export function offlineReceipt(
  read: DTO["ItemRead"],
  input: DTO["ResolveInput"],
): DTO["ResolveReceipt"] {
  return {
    ...offlineEnvelope,
    request_key: input.request_key,
    item: {
      ...read.item,
      state: input.action === "complete" ? "completed" : "closed",
      version: input.expected_version + 1,
    },
    resolution: {
      resolution_id: offlineId(104),
      request_key: input.request_key,
      action: input.action,
      reason: input.reason,
      resolved_by: offlineId(105),
      resolved_at: offlineEnvelope.server_time,
      before_version: input.expected_version,
      after_version: input.expected_version + 1,
      resolution_payload_hash: "b".repeat(64),
    },
    duplicate: false,
  };
}
export function offlineItemList(): DTO["ItemList"] {
  return {
    ...offlineEnvelope,
    items: Array.from({ length: 20 }, (_, n) => offlineItem(n + 1).item),
    total: 20,
    counts: { open: 20, completed: 0, closed: 0 },
    as_of: offlineEnvelope.server_time,
    next_cursor: null,
  };
}
export function offlineExecution(): DTO["ExecutionRead"] {
  return {
    ...offlineEnvelope,
    execution_id: offlineId(106),
    task_id: offlineId(102),
    plan_id: offlineId(103),
    approval_id: offlineId(107),
    operation_key: "offline-execution",
    request_hash: "a".repeat(64),
    revalidation_snapshot_id: offlineId(108),
    status: "completed",
    item_ids: offlineItemList().items.map((x) => x.item_id),
    completed_at: offlineEnvelope.server_time,
    error_code: null,
    sync: offlineSync("failed", 106),
  };
}
export function offlineSession(): DTO["SessionRead"] {
  return {
    ...offlineEnvelope,
    csrf_token: "c".repeat(43),
    principal: {
      principal_id: offlineId(105),
      organization_id: offlineId(109),
      display_name: "离线DTO示例",
      auth_version: 1,
      role_shop_grants: [{ role: "operator", shop_id: offlineId(101) }],
      capabilities: {
        can_create_task: true,
        can_read_tasks: true,
        can_read_approvals: false,
        can_resolve_items: true,
        can_read_operations: false,
        home_path: "/tasks",
      },
    },
    absolute_expires_at: "2026-10-11T09:00:00Z",
    idle_expires_at: "2026-10-11T01:30:00Z",
    config: {
      config_version: "offline-components-v1",
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
    },
  };
}
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const failure = (code: DTO["ErrorDetail"]["code"], status: number) =>
  response(
    {
      schema_version: "p3-web-v1",
      server_time: null,
      trace_id: offlineId(99),
      error: {
        code,
        safe_message: "固定离线错误",
        retryable: false,
        receipt: null,
      },
    },
    status,
  );
export function createOfflineItemClient(
  scenario: OfflineScenario,
  invalidate: () => void,
  observer?: (method: string, path: string, body: string | undefined) => void,
  itemNumber = 1,
): P3Client {
  if (!Number.isInteger(itemNumber) || itemNumber < 1 || itemNumber > 20)
    throw new Error("Fixed offline item required");
  let item = offlineItem(itemNumber),
    firstPost = true;
  const receipts = new Map<
    string,
    { body: string; receipt: DTO["ResolveReceipt"] }
  >();
  if (scenario === "terminal") {
    const receipt = offlineReceipt(item, {
      schema_version: "p3-web-v1",
      request_key: offlineId(110),
      action: "close",
      reason: "固定离线关闭记录",
      expected_version: 1,
    });
    item = {
      ...item,
      item: receipt.item,
      resolution: receipt.resolution,
      can_resolve: false,
      disabled_reasons: ["ITEM_STATE_CONFLICT"],
    };
  }
  if (scenario === "readonly")
    item = {
      ...item,
      can_resolve: false,
      visible_source_task_id: null,
      visible_plan_id: null,
      disabled_reasons: ["ACCESS_DENIED"],
    };
  const transport: FetchTransport = async (url, init) => {
    observer?.(
      init.method!,
      url.pathname,
      typeof init.body === "string" ? init.body : undefined,
    );
    if (url.pathname === "/api/v1/auth/session")
      return response(offlineSession());
    if (url.pathname === "/api/v1/replenishment-items")
      return response(offlineItemList());
    if (url.pathname === `/api/v1/tasks/${offlineId(102)}/execution`)
      return response(offlineExecution());
    if (url.pathname === `/api/v1/replenishment-items/${offlineId(itemNumber)}`)
      return scenario === "not_found"
        ? failure("RESOURCE_NOT_FOUND", 404)
        : response(item);
    if (url.pathname.startsWith("/api/v1/requests/")) {
      const key = url.pathname.split("/").pop()!,
        stored = receipts.get(key);
      if (!stored || url.searchParams.get("operation") !== "resolve")
        return failure("RESOURCE_NOT_FOUND", 404);
      return response({
        ...offlineEnvelope,
        request_key: key,
        status: "succeeded",
        receipt: { operation: "resolve", result: stored.receipt },
      });
    }
    if (
      url.pathname ===
        `/api/v1/replenishment-items/${offlineId(itemNumber)}/resolve` &&
      init.method === "POST"
    ) {
      if (scenario === "revoked") return failure("SESSION_INVALID", 401);
      if (scenario === "conflict") return failure("ITEM_VERSION_CONFLICT", 409);
      if (scenario === "state_conflict")
        return failure("ITEM_STATE_CONFLICT", 409);
      if (scenario === "missing")
        throw new Error("Controlled offline unavailable outcome");
      const body = String(init.body),
        input: DTO["ResolveInput"] = JSON.parse(body),
        stored = receipts.get(input.request_key);
      if (stored)
        return stored.body !== body
          ? failure("IDEMPOTENCY_CONFLICT", 409)
          : response({ ...stored.receipt, duplicate: true });
      const receipt = offlineReceipt(item, input);
      receipts.set(input.request_key, { body, receipt });
      item = {
        ...item,
        item: receipt.item,
        resolution: receipt.resolution,
        can_resolve: false,
        disabled_reasons: ["ITEM_STATE_CONFLICT"],
      };
      if (scenario === "unknown" && firstPost) {
        firstPost = false;
        throw new Error("Controlled offline ACK loss after fixture update");
      }
      if (scenario === "bad_receipt")
        return response({
          ...receipt,
          item: { ...receipt.item, item_id: offlineId(200) },
        });
      return response(receipt);
    }
    return failure("RESOURCE_NOT_FOUND", 404);
  };
  return new P3Client({
    origin: "https://offline.invalid",
    transport,
    onSessionInvalidated: invalidate,
    verifyResponse: (method, path, status, value) => {
      if (status >= 400) return validItemDTO("Error", value);
      const name =
        path === "/api/v1/auth/session"
          ? "SessionRead"
          : path === "/api/v1/replenishment-items"
            ? "ItemList"
            : path.endsWith("/execution")
              ? "ExecutionRead"
              : path.endsWith("/resolve")
                ? "ResolveReceipt"
                : path.startsWith("/api/v1/requests/")
                  ? "RequestRead"
                  : "ItemRead";
      return validItemDTO(name, value);
    },
  });
}
