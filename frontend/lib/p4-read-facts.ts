// Semantic invariants of the frozen A03 read DTOs, after the generated schema has validated shape.
import type { DTO } from "./p3-present";

export const gateFactsValid = (gates: readonly DTO["SenderGate"][]) =>
  gates.every(
    (gate) =>
      gate.sender_enabled ===
        (gate.reason_code === "CONTROLLED_WINDOW_ACTIVE") &&
      (!gate.sender_enabled || gate.verification_mode !== null),
  );
const externalEnabled = (gates: readonly DTO["SenderGate"][]) =>
  gates.some(
    (gate) =>
      gate.sender_enabled && gate.verification_mode === "controlled_sdk",
  );
const configValid = (config: DTO["ConfigRead"]["config"]) =>
  gateFactsValid(config.sender_gates) &&
  config.external_sender_enabled === externalEnabled(config.sender_gates);
export const syncFactsValid = (sync: DTO["SyncRead"]) =>
  gateFactsValid(sync.sender_gates) &&
  sync.sender_enabled === externalEnabled(sync.sender_gates) &&
  sync.projections.every(
    (projection) =>
      projection.is_current_version ===
        (projection.projection_version === projection.target_version) &&
      (!projection.complete_unique_verified ||
        projection.observed_version === projection.projection_version),
  );
const toolValid = (tool: DTO["ToolFact"] | null) =>
  tool === null ||
  ((tool.category === "sdk_method") === (tool.sdk_method !== null) &&
    (tool.category === "model" || !tool.selected_by_model));

export function p4ReadFactsValid(
  method: string,
  path: string,
  value: unknown,
): boolean {
  if (
    method !== "GET" &&
    path !== "/api/v1/auth/login" &&
    path !== "/api/v1/replenishment-items/{item_id}/resolve"
  )
    return true;
  switch (path) {
    case "/api/v1/auth/session":
    case "/api/v1/auth/login":
      return configValid((value as DTO["SessionRead"]).config);
    case "/api/v1/config":
      return configValid((value as DTO["ConfigRead"]).config);
    case "/api/v1/admin/operations": {
      const read = value as DTO["OperationsRead"];
      return (
        gateFactsValid(read.sender_gates) &&
        read.external_sender_enabled === externalEnabled(read.sender_gates)
      );
    }
    case "/api/v1/tasks":
      return (value as DTO["TaskList"]).items.every((item) =>
        syncFactsValid(item.sync),
      );
    case "/api/v1/tasks/{task_id}":
      return syncFactsValid((value as DTO["TaskRead"]).task.sync);
    case "/api/v1/tasks/{task_id}/execution":
      return syncFactsValid((value as DTO["ExecutionRead"]).sync);
    case "/api/v1/replenishment-items":
      return (value as DTO["ItemList"]).items.every((item) =>
        syncFactsValid(item.sync),
      );
    case "/api/v1/replenishment-items/{item_id}":
      return syncFactsValid((value as DTO["ItemRead"]).item.sync);
    case "/api/v1/replenishment-items/{item_id}/resolve":
      return syncFactsValid((value as DTO["ResolveReceipt"]).item.sync);
    case "/api/v1/requests/{request_key}": {
      const result = (value as DTO["RequestRead"]).receipt;
      return (
        result.operation !== "resolve" ||
        syncFactsValid(result.result.item.sync)
      );
    }
    case "/api/v1/tasks/{task_id}/events":
      return (value as DTO["EventsRead"]).items.every((event) =>
        toolValid(event.tool),
      );
    default:
      return true;
  }
}

export function eventsBound(
  read: DTO["EventsRead"],
  task: DTO["TaskRead"],
): boolean {
  return read.items.every(
    (event) =>
      (event.relation === "task"
        ? event.task_id === task.task.task_id
        : task.source !== null &&
          event.task_id === task.source.source_task_id &&
          event.task_id !== task.task.task_id) &&
      event.references.some(
        (ref) => ref.kind === "task" && ref.id === event.task_id,
      ) &&
      event.references.every(
        (ref) => ref.kind !== "task" || ref.id === event.task_id,
      ) &&
      (event.result_ref === null ||
        event.references.some((ref) => ref.id === event.result_ref)),
  );
}

export function syncMeaning(sync: DTO["SyncRead"]): string {
  if (sync.state !== "synced")
    return {
      not_requested: "未请求同步",
      pending: "等待同步",
      failed: "同步失败",
      unknown: "同步结果未知",
    }[sync.state];
  const current = sync.projections.filter((item) => item.is_current_version);
  if (!current.length) return "当前目标版本尚未核实（原状态含历史同步）";
  if (
    current.some(
      (item) => item.state !== "synced" || !item.complete_unique_verified,
    )
  )
    return "已报告原同步状态；完整唯一版本核实未报告";
  return current.every((item) => item.verification_mode === "offline_fake")
    ? "当前版本离线 Fake 核实（非平台回执）"
    : "当前版本核实；请核对逐条验证模式";
}

export function projectionMeaning(item: DTO["Projection"]): string {
  if (!item.is_current_version)
    return `历史投影 v${item.projection_version}；不能证明当前目标 v${item.target_version} 已同步`;
  if (item.state === "synced" && item.complete_unique_verified)
    return item.verification_mode === "offline_fake"
      ? "当前版本离线 Fake 核实（非平台回执）"
      : "当前版本完整唯一核实（按记录验证模式）";
  if (item.state === "synced")
    return "原记录已报告同步；完整唯一版本核实未报告";
  return {
    not_requested: "未请求同步",
    pending: "等待同步",
    failed: "同步失败",
    unknown: "同步结果未知；保留原记录待核",
  }[item.state];
}
