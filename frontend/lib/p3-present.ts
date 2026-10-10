import type { components } from "./p3-types.generated";
export type DTO = components["schemas"];
export const stateText: Record<string, string> = {
  queued: "排队中",
  analyzing: "分析中",
  awaiting_approval: "待审批",
  executing: "执行中",
  completed: "已完成",
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
