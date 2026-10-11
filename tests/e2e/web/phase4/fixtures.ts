// Explicit in-memory DTOs for the two P4 UI additions, no fetch or backend/provider.
import facts from "./report.fixture.json";
import n01 from "./n01.fixture.json";
import type { DTO } from "../../../../frontend/lib/p3-present";
import {
  offlineEnvelope,
  offlineId,
  offlineTask,
  offlineSession,
  offlineItemList,
  offlineItem,
  offlineReceipt,
} from "../../../../frontend/lib/b04-offline-source";
import { readGates, readSync, readEvents } from "./read-fixtures";
import { P3Client } from "../../../../frontend/lib/p3-transport";
import {
  readTransport,
  verifyReadResponse,
} from "../../../../frontend/lib/p3-live-client";
export const report: DTO["ReportRead"] = {
  ...offlineEnvelope,
  task_id: offlineId(102),
  facts: facts as DTO["P2InventoryReport"],
  source: {
    source_task_id: offlineId(201),
    report_id: offlineId(202),
    snapshot_id: offlineId(203),
    facts_hash: facts.facts_hash,
    collected_at: facts.now,
    collection_started_at: facts.now,
    source_complete: true,
    consistency: "observational",
  },
};
export function task(): DTO["TaskRead"] {
  const value = offlineTask();
  return {
    ...value,
    source: report.source,
    execution_id: null,
    current_plan_id: null,
    approval_id: null,
    visible_item_ids: [],
    actions: { ...value.actions, can_start_new_cycle: true },
  };
}
export function explanation(mode = "actual"): DTO["ExplanationRead"] {
  const refs = {
    report_id: report.source.report_id,
    snapshot_id: report.source.snapshot_id,
  };
  const nullable = mode === "nullable" || mode === "template";
  return {
    ...offlineEnvelope,
    task_id: report.task_id,
    report_id: refs.report_id,
    explanation: {
      schema_version: "p204-read-v1",
      analysis_only: true,
      execution_available: false,
      identity_mode: "simulated",
      task_id: report.source.source_task_id,
      explanation_id: offlineId(204),
      child_task_id: offlineId(205),
      result: {
        facts_hash: facts.facts_hash,
        narrative_mode: mode === "template" ? "template" : "model_selected",
        binding_mode: "caller_references",
        summary: "明确离线缓存示例摘要，不是本次模型结果",
        reference_ids: refs,
        lines: report.facts.items.map((fact) => ({
          sku_key: fact.sku_key,
          reason: fact.risk,
          text: "原缓存引用此冻结事实",
          facts_hash: facts.facts_hash,
          reference_ids: refs,
        })),
        metadata: {
          content: null,
          error_code: mode === "template" ? "NO_PROVIDER" : null,
          evidence_mode:
            mode === "template"
              ? "not_used"
              : mode === "nullable"
                ? "offline_stub"
                : "actual_provider",
          provider: nullable ? null : "deepseek",
          requested_model: nullable ? null : "deepseek-flash",
          returned_model: nullable ? null : "deepseek-flash",
          prompt_version: "inventory-explanation-v1",
          request_id: nullable ? null : offlineId(206),
          usage: nullable
            ? null
            : { input_tokens: 100, output_tokens: 20, total_tokens: 120 },
          latency_ms: nullable ? null : 0,
          pricing_version: nullable ? null : "ds-v41-peak-20261010",
          cost_estimate: nullable ? null : "0",
          stop_required: false,
        },
      },
    },
  };
}
export function fixtureClient(
  mode: string,
  invalidate: () => void,
  calls: { method: string; path: string; body?: string }[],
  hold: { release: () => void; revoke?: () => void },
) {
  let savedCreate: DTO["CreateTaskReceipt"] | null = null;
  const response = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  const failure = (code: DTO["ErrorDetail"]["code"], status: number) =>
    response(
      {
        schema_version: offlineEnvelope.schema_version,
        trace_id: offlineEnvelope.trace_id,
        server_time: null,
        error: {
          code,
          safe_message: "固定离线错误",
          retryable: false,
          receipt: null,
        },
      },
      status,
    );
  const client = new P3Client({
    origin: "https://offline.invalid",
    verifyResponse: verifyReadResponse,
    onSessionInvalidated: invalidate,
    transport: readTransport(async (url, init) => {
      calls.push({
        method: init.method!,
        path: url.pathname,
        ...(init.body ? { body: String(init.body) } : {}),
      });
      if (url.pathname === "/api/v1/auth/session") {
        const base = offlineSession();
        const noRole = mode === "no_role";
        return response({
          ...base,
          principal: {
            ...base.principal,
            linked_channels: mode.startsWith("c2_")
              ? ["web", "feishu"]
              : base.principal.linked_channels,
            role_shop_grants:
              mode === "c2_admin" || mode === "c2_admin_deep"
                ? [{ role: "admin", shop_id: offlineId(101) }]
                : mode === "other_shop" || mode === "multi_shop"
                  ? [
                      { role: "operator", shop_id: offlineId(303) },
                      {
                        role: mode === "other_shop" ? "approver" : "operator",
                        shop_id: offlineId(101),
                      },
                    ]
                  : [
                      {
                        role: noRole ? "approver" : "operator",
                        shop_id: offlineId(101),
                      },
                    ],
            capabilities: {
              ...base.principal.capabilities,
              can_create_task:
                !noRole && mode !== "c2_admin" && mode !== "c2_admin_deep",
              can_read_tasks: mode !== "c2_admin" && mode !== "c2_admin_deep",
              can_read_operations:
                mode === "c2_admin" || mode === "c2_admin_deep",
              home_path:
                mode === "c2_admin" || mode === "c2_admin_deep"
                  ? "/admin/operations"
                  : base.principal.capabilities.home_path,
              can_read_approvals: false,
              can_resolve_items: false,
            },
          },
          config: mode.startsWith("c2_")
            ? { ...base.config, sender_gates: readGates(mode) }
            : base.config,
        });
      }
      if (url.pathname === `/api/v1/tasks/${report.task_id}`) {
        if (mode === "c09_read_failed")
          return failure("SERVICE_UNAVAILABLE", 503);
        if (mode === "late_task")
          await new Promise<void>((resolve) => {
            hold.release = resolve;
          });
        let value = task();
        if (mode.startsWith("c2_"))
          value = { ...value, task: { ...value.task, sync: readSync(mode) } };
        if (mode === "pending")
          value = {
            ...value,
            task: { ...value.task, state: "awaiting_approval" },
          };
        if (mode === "disabled")
          value = {
            ...value,
            actions: { ...value.actions, can_start_new_cycle: false },
          };
        return response(value);
      }
      if (url.pathname.endsWith("/report")) return response(report);
      if (url.pathname.endsWith("/events"))
        return response(readEvents(task(), mode));
      if (url.pathname.endsWith("/plans"))
        return response({
          ...offlineEnvelope,
          items: [],
          current_plan_version: null,
          total: 0,
          as_of: offlineEnvelope.server_time,
          next_cursor: null,
        });
      if (url.pathname === "/api/v1/config")
        return response({
          ...offlineEnvelope,
          shop_id: offlineId(101),
          config: mode.startsWith("c2_")
            ? { ...offlineSession().config, sender_gates: readGates(mode) }
            : offlineSession().config,
        });
      if (url.pathname === "/api/v1/admin/operations")
        return response({
          ...offlineEnvelope,
          config_version: "c2-fake",
          transport_mode: "local_http",
          worker_state: "unknown",
          graph_concurrency_limit: 1,
          external_sender_enabled: false,
          recovery_scan_seconds: 10,
          approval_ttl_seconds: 1800,
          revalidation_max_age_seconds: 450,
          sender_gates: readGates(mode),
        });
      if (url.pathname === "/api/v1/replenishment-items") {
        const list = offlineItemList();
        return response({
          ...list,
          items: list.items.map((item) => ({
            ...item,
            sync: {
              ...readSync("c2_unknown"),
              projections: readSync("c2_unknown").projections.map(
                (projection, index) => ({
                  ...projection,
                  aggregate_id: item.item_id,
                  outbox_id: offlineId(
                    1000 + Number.parseInt(item.item_id.slice(-12), 16) + index,
                  ),
                }),
              ),
            },
          })),
        });
      }
      if (url.pathname === `/api/v1/replenishment-items/${offlineId(1)}`) {
        const item = offlineItem(),
          receipt = offlineReceipt(item, {
            schema_version: "p3-web-v1",
            request_key: offlineId(901),
            action: "close",
            reason: "明确离线终态示例",
            expected_version: 1,
          });
        return response({
          ...item,
          item: { ...receipt.item, sync: readSync("c2_stale") },
          resolution: receipt.resolution,
          can_resolve: false,
          disabled_reasons: ["ITEM_TERMINAL"],
        });
      }
      if (url.pathname.endsWith("/explanation")) {
        if (mode.startsWith("c2_")) return failure("NOT_READY", 409);
        if (mode === "delayed")
          await new Promise<void>((resolve) => {
            hold.release = resolve;
          });
        if (mode === "not_ready") return failure("NOT_READY", 409);
        if (mode === "revoked") return failure("SESSION_INVALID", 401);
        let value = explanation(mode);
        if (mode === "bad_refs")
          value = {
            ...value,
            explanation: {
              ...value.explanation,
              result: {
                ...value.explanation.result,
                reference_ids: {
                  ...value.explanation.result.reference_ids,
                  snapshot_id: offlineId(999),
                },
              },
            },
          };
        return response(value);
      }
      if (url.pathname === "/api/v1/tasks/preflight" && init.method === "POST") {
        const input = JSON.parse(String(init.body));
        const sample = n01.cases.find((c) => c.text === input.text);
        if (!sample || input.shop_id !== offlineId(101) || input.fixture_case !== "baseline")
          return failure("INVALID_REQUEST", 422);
        if (mode === "n01_late")
          await new Promise<void>((resolve) => { hold.release = resolve; });
        const result = structuredClone(sample.result);
        if (mode === "n01_badspan" && result.draft) {
          result.candidates[0].value = 7;
          result.candidates[0].start = 11;
          result.candidates[0].end = 12;
          result.draft.L = 7;
        }
        return response({ ...offlineEnvelope, preflight: result });
      }
      if (url.pathname === "/api/v1/tasks" && init.method === "POST") {
        const input = JSON.parse(String(init.body));
        const receipt: DTO["CreateTaskReceipt"] = {
          ...offlineEnvelope,
          request_key: input.request_key,
          task_id: offlineId(301),
          source_task_id: offlineId(302),
          state: "queued",
          duplicate: savedCreate !== null,
        };
        const first = savedCreate === null;
        savedCreate = receipt;
        if (mode === "c09_conflict")
          return failure("IDEMPOTENCY_CONFLICT", 409);
        if (mode === "c09_unknown" && first)
          throw new Error("offline ACK fault");
        return response(receipt, 202);
      }
      if (url.pathname.startsWith("/api/v1/requests/") && savedCreate)
        return response({
          ...offlineEnvelope,
          request_key: savedCreate.request_key,
          status: "succeeded",
          receipt: { operation: "create_task", result: savedCreate },
        });
      return failure("RESOURCE_NOT_FOUND", 404);
    }),
  });
  hold.revoke = () => client.clearSession();
  return client;
}
