import { test, expect } from "../../../../frontend/tooling/web-test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import {
  normalizedReason,
  canResolve,
  itemConsistent,
  resolveReceiptBound,
  validItemDTO,
} from "../../../../frontend/lib/p3-item-contract";
import {
  createOfflineItemClient,
  offlineItem,
  offlineItemList,
  offlineExecution,
  offlineReceipt,
  offlineId,
} from "../../../../frontend/lib/b04-offline-source";
import type { DTO } from "../../../../frontend/lib/p3-present";
const input = (): DTO["ResolveInput"] => ({
  schema_version: "p3-web-v1",
  request_key: offlineId(500),
  action: "complete",
  reason: "明确内部跟进原因",
  expected_version: 1,
});
test("B04纯DTO拒绝缺字段/假身份/额外actor/unsafe数和错误tag，20项原样无填充", () => {
  const list = offlineItemList();
  expect(validItemDTO("ItemList", list)).toBe(true);
  expect(list.items).toHaveLength(20);
  expect(validItemDTO("ExecutionRead", offlineExecution())).toBe(true);
  const read = offlineItem();
  for (const bad of [
    { ...read, identity_mode: "mock" },
    { ...read, actor: offlineId(9) },
    { ...read, item: { ...read.item, version: true } },
    { ...read, item: { ...read.item, quantity: Number.MAX_SAFE_INTEGER + 1 } },
    { ...read, server_time: "tomorrow" },
  ])
    expect(validItemDTO("ItemRead", bad)).toBe(false);
  expect(validItemDTO("ItemRead", { item: read.item })).toBe(false);
  expect(read.item.state).toBe("open");
});
test("T6局部strip按Python3.12精确对照，FEFF保留/001C–1F和0085移除，不归一组合Unicode", () => {
  const values = [
    "\u001c\u001d\u001e\u001f原因\u0085",
    "\ufeff",
    "\ufeff原 因\ufeff",
    "\u3000e\u0301\u200a",
    "😀".repeat(1000),
    "😀".repeat(1001),
    "\u0085\u001f",
    "  内部\n空白  ",
  ];
  const result = JSON.parse(
    execFileSync(
      resolve(__dirname, "../../../../.venv/bin/python"),
      [
        "-c",
        "import json,sys; assert sys.version_info[:2]==(3,12); v=json.load(sys.stdin); print(json.dumps([s.strip() if 1<=len(s.strip())<=1000 else None for s in v],ensure_ascii=False))",
      ],
      { input: JSON.stringify(values), encoding: "utf8" },
    ),
  );
  expect(values.map(normalizedReason)).toEqual(result);
  expect(normalizedReason(" e\u0301 ")).toBe("e\u0301");
  expect(normalizedReason("\ufeff")).toBe("\ufeff");
});
test("can_resolve与open/版本/记录绑定才可准备，sync_failed不取消内部业务权限", () => {
  const read = offlineItem();
  expect(canResolve(read)).toBe(true);
  expect(read.item.sync.state).toBe("failed");
  expect(canResolve({ ...read, can_resolve: false })).toBe(false);
  expect(canResolve({ ...read, disabled_reasons: ["ACCESS_DENIED"] })).toBe(
    false,
  );
  expect(
    canResolve({ ...read, item: { ...read.item, state: "completed" } }),
  ).toBe(false);
  const receipt = offlineReceipt(read, input());
  const terminal = {
    ...read,
    item: receipt.item,
    resolution: receipt.resolution,
    can_resolve: true,
  };
  expect(itemConsistent(terminal)).toBe(true);
  expect(canResolve(terminal)).toBe(false);
  expect(
    itemConsistent({
      ...terminal,
      resolution: { ...receipt.resolution, after_version: 4 },
    }),
  ).toBe(false);
});
test("resolve回执必须原item/key/action/原因与版本，回放原actor/time/digest不可漂移", () => {
  const read = offlineItem(),
    request = input(),
    receipt = offlineReceipt(read, request);
  expect(resolveReceiptBound(read, request, receipt)).toBe(true);
  for (const bad of [
    { ...receipt, request_key: offlineId(8) },
    { ...receipt, item: { ...receipt.item, item_id: offlineId(8) } },
    { ...receipt, item: { ...receipt.item, state: "open" as const } },
    { ...receipt, resolution: { ...receipt.resolution, reason: "different" } },
    { ...receipt, resolution: { ...receipt.resolution, before_version: 2 } },
    { ...receipt, resolution: { ...receipt.resolution, after_version: 3 } },
  ])
    expect(resolveReceiptBound(read, request, bad)).toBe(false);
  expect(
    resolveReceiptBound(
      read,
      request,
      { ...receipt, duplicate: true },
      receipt,
    ),
  ).toBe(true);
  for (const change of [
    { resolved_by: offlineId(8) },
    { resolved_at: "2026-10-11T02:00:00Z" },
    { resolution_payload_hash: "c".repeat(64) },
  ])
    expect(
      resolveReceiptBound(
        read,
        request,
        { ...receipt, resolution: { ...receipt.resolution, ...change } },
        receipt,
      ),
    ).toBe(false);
});
test("注入unknown无自动重投，原键GET恢复、十次同字节请求/原receipt版本与digest固定", async () => {
  const bodies: string[] = [];
  const client = createOfflineItemClient(
    "unknown",
    () => {},
    (method, path, body) => {
      if (method === "POST") bodies.push(body!);
    },
  );
  await client.session();
  const request = input(),
    prepared = client.prepareResolve(offlineId(1), request);
  await expect(prepared.send()).rejects.toMatchObject({
    code: "WRITE_RESULT_UNKNOWN",
  });
  expect(bodies).toHaveLength(1);
  const receipt = await client.requestReceipt(request.request_key, "resolve");
  expect(receipt.receipt.operation).toBe("resolve");
  expect(bodies).toHaveLength(1);
  for (let n = 0; n < 9; n++)
    expect((await prepared.send()).duplicate).toBe(true);
  expect(new Set(bodies).size).toBe(1);
  expect(bodies).toHaveLength(10);
  expect(JSON.stringify(prepared)).not.toContain("reason");
  expect((await client.item(offlineId(1))).item.version).toBe(2);
});
test("注入同键异动作冲突及401清预备操作，404只安全待核实，不新键", async () => {
  const client = createOfflineItemClient("ready", () => {});
  await client.session();
  await client.prepareResolve(offlineId(1), input()).send();
  await expect(
    client.prepareResolve(offlineId(1), { ...input(), action: "close" }).send(),
  ).rejects.toMatchObject({ code: "IDEMPOTENCY_CONFLICT" });
  let invalidated = 0;
  const revoked = createOfflineItemClient("revoked", () => invalidated++);
  await revoked.session();
  const old = revoked.prepareResolve(offlineId(1), input());
  await expect(old.send()).rejects.toMatchObject({
    status: 401,
    code: "SESSION_INVALID",
  });
  expect(invalidated).toBe(1);
  await expect(old.send()).rejects.toMatchObject({ code: "SESSION_INVALID" });
  const missing = createOfflineItemClient("missing", () => {});
  await missing.session();
  await expect(
    missing.prepareResolve(offlineId(1), input()).send(),
  ).rejects.toMatchObject({ code: "WRITE_RESULT_UNKNOWN" });
  await expect(
    missing.requestReceipt(input().request_key, "resolve"),
  ).rejects.toMatchObject({ code: "RESOURCE_NOT_FOUND", status: 404 });
});
