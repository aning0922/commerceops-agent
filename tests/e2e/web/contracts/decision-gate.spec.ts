import { test, expect } from "../../../../frontend/tooling/web-test";
import {
  decisionGate,
  exactAcknowledgements,
} from "../../../../frontend/lib/p3-decision-gate";
import type { DTO } from "../../../../frontend/lib/p3-present";
const clock = Date.parse("2026-10-10T16:00:00Z");
function read(unknown = false): DTO["ApprovalRead"] {
  const fact = {
    sku_key: "sku-a",
    stock_pool_key: "pool-a",
    suggested_units: 100,
    inbound_units: unknown ? null : 0,
    effective_inbound_units: 0,
    hard_blocks: [],
  };
  const plan = {
    plan_id: "p",
    task_id: "t",
    plan_version: 1,
    plan_hash: "f".repeat(64),
    status: "current",
    expires_at: "2026-10-10T17:00:00Z",
    item_count: 1,
    total_units: 100,
    disclosure_complete: true,
    hard_blocks: [],
    items: [
      {
        sku_key: "sku-a",
        stock_pool_key: "pool-a",
        quantity: 100,
        raw_inbound_units: unknown ? null : 0,
        effective_inbound_units: 0,
        fact,
      },
    ],
    required_assumptions: unknown
      ? [
          {
            key: "inbound_unknown_zero:sku-a",
            sku_key: "sku-a",
            type: "inbound_unknown_zero",
            estimated_units: 0,
            disclosure_version: "inbound-unknown-zero-v1",
          },
        ]
      : [],
  };
  return {
    server_time: "2026-10-10T16:00:00Z",
    plan,
    approval: {
      plan_id: "p",
      task_id: "t",
      plan_version: 1,
      plan_hash: "f".repeat(64),
      status: "pending",
      can_decide: true,
      expires_at: plan.expires_at,
    },
    nonce: "n".repeat(43),
  } as unknown as DTO["ApprovalRead"];
}
test("只能当前/服务器可决定/完整绑定版本与有效nonce期限，角色名称不授权", () => {
  expect(decisionGate(read(), clock)).toBe(true);
  for (const change of [
    { can_decide: false },
    { status: "superseded" },
    { status: "expired" },
    { plan_version: 2 },
    { plan_hash: "a".repeat(64) },
    { task_id: "other" },
  ])
    expect(
      decisionGate(
        {
          ...read(),
          approval: { ...read().approval, ...change },
        } as DTO["ApprovalRead"],
        clock,
      ),
    ).toBe(false);
  expect(decisionGate({ ...read(), nonce: null }, clock)).toBe(false);
  expect(decisionGate(read(), Date.parse(read().approval.expires_at))).toBe(
    false,
  );
  expect(decisionGate(read(), NaN)).toBe(false);
});
test("完整未知raw-null集合不默认确认、不漏多重复或假设指向不同SKU", () => {
  const r = read(true);
  expect(decisionGate(r, clock)).toBe(true);
  expect(exactAcknowledgements(r, [])).toBe(false);
  expect(exactAcknowledgements(r, [r.plan.required_assumptions[0].key])).toBe(
    true,
  );
  expect(
    exactAcknowledgements(r, [r.plan.required_assumptions[0].key, "extra"]),
  ).toBe(false);
  expect(
    exactAcknowledgements(r, [
      r.plan.required_assumptions[0].key,
      r.plan.required_assumptions[0].key,
    ]),
  ).toBe(false);
  expect(
    decisionGate(
      { ...r, plan: { ...r.plan, required_assumptions: [] } },
      clock,
    ),
  ).toBe(false);
});
test("全20项计数/数量/硬阻断与current状态，不以同Q或部分response启用", () => {
  const r = read();
  expect(
    decisionGate(
      { ...r, plan: { ...r.plan, disclosure_complete: false } },
      clock,
    ),
  ).toBe(false);
  expect(
    decisionGate(
      { ...r, plan: { ...r.plan, hard_blocks: ["UNKNOWN_STOCK"] } },
      clock,
    ),
  ).toBe(false);
  expect(
    decisionGate({ ...r, plan: { ...r.plan, item_count: 20 } }, clock),
  ).toBe(false);
  expect(
    decisionGate({ ...r, plan: { ...r.plan, status: "superseded" } }, clock),
  ).toBe(false);
});
