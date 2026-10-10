import type { DTO } from "./p3-present";
import { planComplete } from "./p3-present";
export function decisionGate(
  read: DTO["ApprovalRead"],
  estimatedServerTime: number,
): boolean {
  const a = read.approval,
    p = read.plan;
  const expected = p.items
    .filter((x) => x.raw_inbound_units === null)
    .map((x) => x.sku_key)
    .sort();
  const disclosed = p.required_assumptions.map((x) => x.sku_key).sort();
  return (
    a.can_decide &&
    a.status === "pending" &&
    p.status === "current" &&
    a.plan_id === p.plan_id &&
    a.plan_version === p.plan_version &&
    a.plan_hash === p.plan_hash &&
    a.task_id === p.task_id &&
    planComplete(p) &&
    !p.hard_blocks.length &&
    p.items.every((x) => !x.fact.hard_blocks.length) &&
    typeof read.nonce === "string" &&
    /^[A-Za-z0-9_-]{43}$/.test(read.nonce) &&
    Number.isFinite(estimatedServerTime) &&
    Date.parse(a.expires_at) > estimatedServerTime &&
    Date.parse(p.expires_at) === Date.parse(a.expires_at) &&
    new Set(p.required_assumptions.map((x) => x.key)).size ===
      p.required_assumptions.length &&
    JSON.stringify(expected) === JSON.stringify(disclosed)
  );
}
export function exactAcknowledgements(
  read: DTO["ApprovalRead"],
  selected: readonly string[],
): boolean {
  const required = read.plan.required_assumptions.map((x) => x.key).sort();
  return (
    selected.length === new Set(selected).size &&
    JSON.stringify([...selected].sort()) === JSON.stringify(required)
  );
}
