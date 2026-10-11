import type { components } from "./p3-types.generated";
export type DTO = components["schemas"];
export const stateText: Record<string, string> = {
  queued: "排队中",
  analyzing: "分析中",
  awaiting_approval: "待审批",
  executing: "执行中",
  completed: "已完成",
  open: "待跟进",
  closed: "已关闭",
  rejected: "已拒绝",
  expired: "已过期",
  needs_reapproval: "需要重新审批",
  failed: "失败",
  needs_attention: "需人工核实",
  pending: "待处理",
  approved: "批准已记录",
  superseded: "已被新版本替代",
  current: "当前冻结版本",
  invalidated: "已失效",
  executed: "已执行",
  not_requested: "未请求同步",
  synced: "已同步",
  sync_pending: "等待同步",
  sync_failed: "同步失败",
  sync_unknown: "同步结果未知",
  unknown: "结果未知",
  report_ready: "报告已生成",
  no_action: "无需内部项",
  items_created: "内部项已创建",
  running: "运行中",
  stopped: "已停止",
  risk: "补货风险",
  stockout: "缺货",
  normal: "正常",
  no_recent_demand: "近期无需求",
  manual_check: "需人工核对",
  quality_blocked: "数据硬阻断",
  estimate: "规则建议",
  assumption_draft: "假设草案",
  blocked: "不可执行",
  not_needed: "无需建议",
};
const statusTones: Record<
  string,
  "success" | "warning" | "danger" | "info" | "neutral"
> = {
  queued: "info",
  analyzing: "info",
  executing: "info",
  running: "info",
  awaiting_approval: "warning",
  needs_reapproval: "warning",
  needs_attention: "warning",
  pending: "warning",
  open: "warning",
  unknown: "warning",
  sync_unknown: "warning",
  sync_pending: "info",
  risk: "warning",
  assumption_draft: "warning",
  manual_check: "warning",
  failed: "danger",
  sync_failed: "danger",
  stockout: "danger",
  quality_blocked: "danger",
  completed: "success",
  approved: "success",
  synced: "success",
  executed: "success",
  normal: "success",
  report_ready: "success",
  items_created: "success",
};
export function statusView(value: string) {
  const key = Object.hasOwn(stateText, value)
    ? value
    : Object.keys(stateText).find((key) => stateText[key] === value);
  return {
    text: key ? stateText[key] : "状态未识别",
    tone: key ? (statusTones[key] ?? "neutral") : "neutral",
    known: key !== undefined,
  };
}
export const label = (state: string) => stateText[state] ?? state;
export const utc = (value: string | null) => value ?? "未知";
export function localTime(value: string | null, zone: string | null): string {
  if (value === null) return "未知";
  if (!zone) return `${value}（时区未知）`;
  try {
    return (
      new Intl.DateTimeFormat("zh-CN", {
        timeZone: zone,
        dateStyle: "short",
        timeStyle: "medium",
        hour12: false,
      }).format(new Date(value)) + ` · ${zone}`
    );
  } catch {
    return `${value}（时区未知）`;
  }
}
export function planComplete(plan: DTO["Plan"]): boolean {
  return (
    plan.disclosure_complete &&
    plan.items.every(
      ({
        fact,
        sku_key: sku,
        stock_pool_key: pool,
        raw_inbound_units: raw,
        effective_inbound_units: effective,
        quantity,
      }) =>
        sku === fact.sku_key &&
        pool === fact.stock_pool_key &&
        raw === fact.inbound_units &&
        effective === fact.effective_inbound_units &&
        quantity === fact.suggested_units,
    ) &&
    plan.items.length === plan.item_count &&
    new Set(plan.items.map((x) => x.sku_key)).size === plan.items.length &&
    plan.items.reduce((sum, x) => sum + BigInt(x.quantity), 0n) ===
      BigInt(plan.total_units)
  );
}
export function reportBound(
  report: DTO["ReportRead"],
  taskId: string,
  specified?: string,
): boolean {
  return (
    report.task_id === taskId &&
    (!specified || specified === report.source.report_id) &&
    report.source.facts_hash === report.facts.facts_hash
  );
}

export function explanationBound(
  report: DTO["ReportRead"],
  read: DTO["ExplanationRead"],
): boolean {
  const record = read.explanation;
  const result = record.result;
  const refs = report.source;
  const bound = (value: DTO["P2ExplanationExplanationRefs"]) =>
    value.report_id === refs.report_id &&
    value.snapshot_id === refs.snapshot_id;
  const skus = new Map(
    report.facts.items.map((fact) => [fact.sku_key, fact.risk]),
  );
  return (
    reportBound(report, report.task_id) &&
    read.task_id === report.task_id &&
    read.report_id === refs.report_id &&
    record.task_id === refs.source_task_id &&
    result.facts_hash === refs.facts_hash &&
    bound(result.reference_ids) &&
    new Set(result.lines.map((line) => line.sku_key)).size ===
      result.lines.length &&
    result.lines.every(
      (line) =>
        skus.get(line.sku_key) === line.reason &&
        line.facts_hash === refs.facts_hash &&
        bound(line.reference_ids),
    )
  );
}

export function parameterClarification(
  shop: string,
  shops: readonly string[],
  values: readonly string[],
): string | null {
  if (!shops.includes(shop)) return "请明确选择当前 operator 已授权的店铺。";
  const names = ["L", "R", "S"];
  const missing = names.filter((_, index) => !values[index]?.trim());
  if (missing.length)
    return `缺少结构化参数 ${missing.join("、")}；请填写后重新确认。`;
  const invalid = names.filter(
    (_, index) =>
      !/^(0|[1-9][0-9]*)$/.test(values[index]) || Number(values[index]) > 365,
  );
  if (invalid.length)
    return `${invalid.join("、")} 必须为 0–365 的整数；不猜测或自动补参。`;
  return null;
}

export function newCycleEligibility(
  task: DTO["TaskRead"] | null,
  canCreate: boolean,
  operatorShops: readonly string[],
  report?: DTO["ReportRead"],
): { allowed: boolean; reason: string } {
  if (!task)
    return { allowed: false, reason: "尚未取得当前任务与服务端新周期资格。" };
  if (
    report &&
    (!reportBound(report, task.task.task_id) ||
      !task.source ||
      task.source.source_task_id !== report.source.source_task_id ||
      task.source.report_id !== report.source.report_id ||
      task.source.snapshot_id !== report.source.snapshot_id ||
      task.source.facts_hash !== report.source.facts_hash)
  )
    return {
      allowed: false,
      reason: "当前报告与任务冻结来源不一致，不能开启新周期。",
    };
  if (!canCreate || !operatorShops.includes(task.task.shop_id))
    return {
      allowed: false,
      reason: "当前身份没有此店铺的 operator 创建资格。",
    };
  if (task.task.state !== "completed")
    return {
      allowed: false,
      reason: "当前任务尚未完成；待审批、执行中或未知结果不能原地重算。",
    };
  if (!task.actions.can_start_new_cycle)
    return { allowed: false, reason: "服务端未允许从此已完成任务开启新周期。" };
  return {
    allowed: true,
    reason: "可打开新周期草稿；原任务、报告、批准和执行保持原记录。",
  };
}
