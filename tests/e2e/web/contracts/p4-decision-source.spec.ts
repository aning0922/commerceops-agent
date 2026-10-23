import { test, expect } from "../../../../frontend/tooling/web-test";
import { P3Client } from "../../../../frontend/lib/p3-transport";
import {
  readTransport,
  verifyReadResponse,
} from "../../../../frontend/lib/p3-live-client";
import {
  offlineEnvelope,
  offlineId,
  offlineSession,
} from "../../../../frontend/lib/b04-offline-source";
import type { DTO } from "../../../../frontend/lib/p3-present";

// Fixed offline receipts only; no Feishu authentication, provider or network.
const input: DTO["DecisionInput"] = {
  schema_version: "p3-web-v1",
  request_key: offlineId(401),
  approval_id: offlineId(402),
  plan_id: offlineId(403),
  plan_version: 1,
  plan_hash: "f".repeat(64),
  action: "approve",
  acknowledged_assumption_keys: [],
  nonce: "n".repeat(43),
};
const receipt = (
  decision_source: DTO["DecisionReceipt"]["decision_source"],
): DTO["DecisionReceipt"] => ({
  ...offlineEnvelope,
  request_key: input.request_key,
  decision_id: offlineId(404),
  task_id: offlineId(405),
  approval_id: input.approval_id,
  plan_id: input.plan_id,
  plan_version: input.plan_version,
  plan_hash: input.plan_hash,
  decision_payload_hash: "e".repeat(64),
  action: input.action,
  acknowledged_assumption_keys: [],
  approval_status: "approved",
  decided_by: offlineSession().principal.principal_id,
  decided_at: offlineEnvelope.server_time,
  decision_source,
  reason_code: null,
  resume_state: "queued",
  duplicate: false,
});
const response = (value: unknown) =>
  new Response(JSON.stringify(value), {
    headers: { "Content-Type": "application/json" },
  });
function client(value: unknown, writes: string[]) {
  return new P3Client({
    origin: "https://test.invalid",
    verifyResponse: verifyReadResponse,
    transport: readTransport(async (_url, init) => {
      if (init.method === "GET") return response(offlineSession());
      writes.push(String(init.body));
      return response(value);
    }),
  });
}
test("P4 A01审定来源web/feishu经严格P3Client消费；请求不接受客户端来源/actor", async () => {
  for (const source of ["web", "feishu"] as const) {
    const writes: string[] = [],
      current = client(receipt(source), writes);
    await current.session();
    const untrusted = {
      ...input,
      decision_source: "feishu",
      actor: offlineId(999),
      role: "admin",
    };
    expect(await current.prepareDecision(untrusted).send()).toEqual(
      receipt(source),
    );
    expect(JSON.parse(writes[0])).toEqual(input);
    expect(writes).toHaveLength(1);
  }
});
test("P4来源扩展仍拒绝未知/bool/缺字段/额外actor/假身份/坏绑定类型，不自动重投", async () => {
  const valid = receipt("feishu"),
    { decision_source: _source, ...missing } = valid;
  for (const value of [
    { ...valid, decision_source: "other" },
    { ...valid, decision_source: true },
    missing,
    { ...valid, actor: offlineId(999) },
    { ...valid, identity_mode: "mock" },
    { ...valid, plan_version: true },
    { ...valid, plan_hash: "bad" },
  ]) {
    const writes: string[] = [],
      current = client(value, writes);
    await current.session();
    await expect(current.prepareDecision(input).send()).rejects.toMatchObject({
      code: "WRITE_RESULT_UNKNOWN",
    });
    expect(writes).toHaveLength(1);
  }
});
