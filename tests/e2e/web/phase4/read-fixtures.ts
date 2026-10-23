// Fixed A03 read DTO samples, explicitly Fake; no API, provider, platform or SDK invocation.
import type { DTO } from "../../../../frontend/lib/p3-present";
import {
  offlineEnvelope,
  offlineId,
  offlineSenderGates,
} from "../../../../frontend/lib/b04-offline-source";
export function readGates(mode: string): DTO["SenderGate"][] {
  const active = mode === "c2_history" || mode === "c2_current";
  const reason = active
    ? "CONTROLLED_WINDOW_ACTIVE"
    : mode === "c2_expired"
      ? "WINDOW_EXPIRED"
      : mode === "c2_worker"
        ? "WORKER_NOT_READY"
        : "DISABLED_BY_CONFIGURATION";
  return [
    offlineSenderGates()[0],
    {
      destination_alias: "Base",
      sender_enabled: active,
      reason_code: reason,
      verification_mode: "offline_fake",
      as_of: offlineEnvelope.server_time,
      worker_ready: active ? true : mode === "c2_worker" ? false : null,
    },
  ];
}
export function readSync(mode: string): DTO["SyncRead"] {
  const historical = mode === "c2_history" || mode === "c2_stale";
  const failed = mode === "c2_stale";
  const synced = (historical && !failed) || mode === "c2_current";
  const row: DTO["Projection"] = {
    aggregate_id: offlineId(1),
    outbox_id: offlineId(601),
    destination_alias: "Base",
    projection_version: historical ? 1 : 2,
    target_version: 2,
    observed_version: failed ? 3 : synced ? (historical ? 1 : 2) : null,
    complete_unique_verified: synced,
    is_current_version: !historical,
    outbox_status: failed ? "dead" : synced ? "sent" : "unknown",
    state: failed ? "failed" : synced ? "synced" : "unknown",
    source_mode: "controlled_stub",
    attempts: 2,
    verification_mode: "offline_fake",
    as_of: offlineEnvelope.server_time,
    error_code: failed
      ? "BASE_VERSION_STALE"
      : synced
        ? null
        : "BASE_ACK_UNPROVEN",
  };
  return {
    state: row.state,
    sender_enabled: false,
    sender_gates: readGates(mode),
    projections:
      mode === "c2_current"
        ? [
            {
              ...row,
              outbox_id: offlineId(600),
              projection_version: 1,
              observed_version: 1,
              is_current_version: false,
            },
            row,
          ]
        : [row],
  };
}
export function readEvents(
  task: DTO["TaskRead"],
  mode = "c2_events",
): DTO["EventsRead"] {
  const root = task.task.task_id,
    source = task.source!.source_task_id;
  const records: readonly [
    string,
    string,
    string,
    DTO["Event"]["channel"],
    string,
    DTO["ToolFact"]["category"],
    DTO["EventReference"]["kind"],
    string,
  ][] = [
    [
      root,
      "workflow_created",
      "T1",
      "web",
      "replenishment.create_workflow",
      "deterministic",
      "task",
      root,
    ],
    [
      source,
      "analysis_report_saved",
      "analysis",
      "worker",
      "inventory.persist_report",
      "deterministic",
      "report",
      task.source!.report_id,
    ],
    [
      root,
      "approval_decided",
      "T3",
      "feishu",
      "replenishment.record_decision",
      "deterministic",
      "approval",
      offlineId(605),
    ],
    [
      root,
      "base_projection_checked",
      "projection",
      "worker",
      "feishu.base.project",
      "sdk_adapter",
      "projection",
      offlineId(601),
    ],
  ];
  return {
    ...offlineEnvelope,
    next_cursor: null,
    as_of: offlineEnvelope.server_time,
    items: records.map(
      ([id, action, step, channel, name, category, kind, ref], index) => ({
        event_id: offlineId(700 + index),
        record_trace_id: offlineId(800 + index),
        occurred_at: offlineEnvelope.server_time,
        action,
        step,
        channel,
        task_id: mode === "c2_bad_trace" && index === 1 ? offlineId(999) : id,
        relation: id === root ? "task" : "source",
        duration_ms: null,
        result_ref: ref,
        safe_summary: "明确离线读取事实示例；不是实际SDK或模型结果",
        recovery: null,
        tool: {
          category,
          name,
          selected_by_model: false,
          sdk_method: null,
          verification_mode: category === "sdk_adapter" ? "offline_fake" : null,
        },
        references: [
          { kind: "task", id },
          { kind, id: ref },
        ],
        safe_code: category === "sdk_adapter" ? "BASE_COMPLETE_VERIFIED" : null,
      }),
    ),
  };
}
