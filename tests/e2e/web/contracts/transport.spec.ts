import { test, expect } from "../../../../frontend/tooling/web-test";
import { P3Client, P3Failure } from "../../../../frontend/lib/p3-transport";
import type { components } from "../../../../frontend/lib/p3-types.generated";
type DTO = components["schemas"];
const id = "00000000-0000-4000-8000-000000000001";
const other = "00000000-0000-4000-8000-000000000002";
const envelope = {
  schema_version: "p3-web-v1",
  identity_mode: "session",
  server_time: "2026-10-10T12:00:00Z",
  trace_id: id,
};
const offlinePassword = () => "p".repeat(16); // Low-entropy deterministic test value, not a provisioned account.
const token = () => "c".repeat(43); // Generated low-entropy offline placeholder, no actual credential.
const session = () => ({
  ...envelope,
  csrf_token: token(),
  principal: { principal_id: id },
});
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
test("显式transport与loopback模式、无bootstrap禁止POST", async () => {
  let calls = 0;
  const transport = async () => {
    calls++;
    return response(session());
  };
  expect(
    () => new P3Client({ origin: "http://127.0.0.1:3999", transport }),
  ).toThrow();
  expect(
    () =>
      new P3Client({
        origin: "http://external.invalid",
        localHttp: true,
        transport,
      }),
  ).toThrow();
  const client = new P3Client({
    origin: "http://127.0.0.1:3999",
    localHttp: true,
    transport,
  });
  await expect(
    client.login({
      schema_version: "p3-web-v1",
      login: "fixture",
      password: offlinePassword(),
    }),
  ).rejects.toMatchObject({ code: "CSRF_NOT_READY" });
  expect(calls).toBe(0);
});
test("Cookie/CSRF/JSON不伪造actor-role，原请求字节保持且unknown无自动重投", async () => {
  const writes: { url: string; init: RequestInit }[] = [];
  let fail = true;
  const client = new P3Client({
    origin: "https://test.invalid",
    transport: async (url, init) => {
      if (init.method === "GET") return response(session());
      writes.push({ url: url.href, init });
      if (fail) throw new Error("raw transport data must not surface");
      return response({ ...envelope, duplicate: true });
    },
  });
  await client.session();
  const input = {
    schema_version: "p3-web-v1",
    request_key: id,
    approval_id: id,
    plan_id: id,
    plan_version: 1,
    plan_hash: "f".repeat(64),
    action: "approve_with_assumptions",
    acknowledged_assumption_keys: ["inbound:SKU-B"],
    nonce: "n".repeat(43),
    actor: other,
    role: "admin",
    approved: true,
  } as const;
  const prepared = client.prepareDecision(input);
  await expect(prepared.send()).rejects.toMatchObject({
    code: "WRITE_RESULT_UNKNOWN",
  });
  expect(writes).toHaveLength(1);
  fail = false;
  await prepared.send();
  expect(writes).toHaveLength(2);
  expect(writes[0].init.body).toBe(writes[1].init.body);
  const body = JSON.parse(String(writes[0].init.body));
  expect(body.request_key).toBe(id);
  expect(body.acknowledged_assumption_keys).toEqual(["inbound:SKU-B"]);
  expect(body).not.toHaveProperty("actor");
  expect(body).not.toHaveProperty("role");
  expect(body).not.toHaveProperty("approved");
  const headers = new Headers(writes[0].init.headers);
  expect(headers.get("X-CSRF-Token")).toBe(token());
  expect(headers.has("Origin")).toBe(false);
  expect(headers.has("X-Actor")).toBe(false);
  expect(writes[0].init).toMatchObject({
    credentials: "include",
    cache: "no-store",
    redirect: "error",
  });
  expect(JSON.stringify(prepared)).not.toContain("nonce");
});
test("401即使envelope坏也清csrf/缓存，错误不回显原输入/未知code", async () => {
  let invalidated = 0;
  let denied = false;
  const client = new P3Client({
    origin: "https://test.invalid",
    onSessionInvalidated: () => invalidated++,
    transport: async () =>
      denied
        ? response({ raw: "sensitive-placeholder" }, 401)
        : response(session()),
  });
  await client.session();
  denied = true;
  await expect(client.task(id)).rejects.toMatchObject({
    code: "INVALID_RESPONSE",
    status: 401,
  });
  expect(invalidated).toBeGreaterThan(0);
  expect(() =>
    client.prepareResolve(id, {
      schema_version: "p3-web-v1",
      request_key: id,
      action: "close",
      reason: "offline",
      expected_version: 1,
    }),
  ).toThrow(P3Failure);
  const hostile = new P3Client({
    origin: "https://test.invalid",
    transport: async () =>
      response(
        {
          ...envelope,
          error: {
            code: "sensitive-placeholder",
            safe_message: "sensitive-placeholder",
          },
        },
        409,
      ),
  });
  try {
    await hostile.task(id);
    throw new Error("expected rejection");
  } catch (error) {
    expect(error).toBeInstanceOf(P3Failure);
    expect(String(error)).not.toContain("sensitive-placeholder");
    expect((error as P3Failure).code).toBe("INVALID_RESPONSE");
  }
});
test("固定report绑定/operation回读，无404隐式创建或换键", async () => {
  const calls: URL[] = [];
  const client = new P3Client({
    origin: "https://test.invalid",
    transport: async (url) => {
      calls.push(url);
      return response(
        {
          ...envelope,
          error: {
            code: "RESOURCE_NOT_FOUND",
            safe_message: "ignored",
            retryable: false,
            receipt: null,
          },
        },
        404,
      );
    },
  });
  await expect(client.report(id, other)).rejects.toMatchObject({
    code: "RESOURCE_NOT_FOUND",
  });
  expect(calls[0].searchParams.get("report_id")).toBe(other);
  await expect(client.requestReceipt(id, "resolve")).rejects.toMatchObject({
    code: "RESOURCE_NOT_FOUND",
  });
  expect(calls[1].pathname).toBe(`/api/v1/requests/${id}`);
  expect(calls[1].searchParams.get("operation")).toBe("resolve");
  expect(calls).toHaveLength(2);
});
test("preparedResolve不受输入修改影响，变更principal不能重放旧用户请求", async () => {
  let principal = id;
  const bodies: string[] = [];
  const client = new P3Client({
    origin: "https://test.invalid",
    transport: async (_url, init) => {
      if (init.method === "GET")
        return response({
          ...session(),
          principal: { principal_id: principal },
        });
      bodies.push(String(init.body));
      return response(envelope);
    },
  });
  await client.session();
  const input: DTO["ResolveInput"] = {
    schema_version: "p3-web-v1",
    request_key: id,
    action: "complete",
    reason: "原原因",
    expected_version: 1,
  };
  const prepared = client.prepareResolve(id, input);
  (input as { reason: string }).reason = "改后原因";
  await prepared.send();
  expect(JSON.parse(bodies[0]).reason).toBe("原原因");
  principal = other;
  await client.session();
  await expect(prepared.send()).rejects.toMatchObject({
    code: "SESSION_INVALID",
  });
  expect(bodies).toHaveLength(1);
});

test("损坏成功响应/网关失败/503均保留原写请求unknown，绝不自动补投", async () => {
  for (const kind of [
    "bad-json",
    "bad-envelope",
    "wrong-identity",
    "gateway",
    "unavailable",
  ]) {
    let writes = 0;
    const client = new P3Client({
      origin: "https://test.invalid",
      transport: async (_url, init) => {
        if (init.method === "GET") return response(session());
        writes++;
        if (kind === "bad-json")
          return new Response("{", {
            headers: { "Content-Type": "application/json" },
          });
        if (kind === "bad-envelope")
          return response({ ...envelope, server_time: "unknown" });
        if (kind === "wrong-identity")
          return response({ ...envelope, identity_mode: "mock" });
        if (kind === "gateway") return new Response("gateway", { status: 502 });
        return response(
          { ...envelope, error: { code: "SERVICE_UNAVAILABLE" } },
          503,
        );
      },
    });
    await client.session();
    const prepared = client.prepareResolve(id, {
      schema_version: "p3-web-v1",
      request_key: id,
      action: "close",
      reason: "offline",
      expected_version: 1,
    });
    await expect(prepared.send()).rejects.toMatchObject({
      code: "WRITE_RESULT_UNKNOWN",
    });
    expect(writes).toBe(1);
    expect(prepared.requestKey).toBe(id);
  }
});

test("17个GET使用冻结路由、分页与版本参数，不产生额外写入", async () => {
  const calls: string[] = [];
  const client = new P3Client({
    origin: "https://test.invalid",
    transport: async (url, init) => {
      expect(init.method).toBe("GET");
      calls.push(url.pathname + url.search);
      return response(session());
    },
  });
  await client.bootstrap();
  await client.session();
  await client.config(id);
  await client.operations();
  await client.tasks({ limit: 20, state: "completed" });
  await client.task(id);
  await client.report(id, other);
  await client.explanation(id, other);
  await client.plans(id, { limit: 20, cursor: "offline-cursor" });
  await client.plan(id, 2);
  await client.events(id);
  await client.execution(id);
  await client.approvals({ view: "mine", state: "pending" });
  await client.approval(id);
  await client.items({ state: "open" });
  await client.item(id);
  await client.requestReceipt(id, "decision");
  expect(calls).toEqual([
    "/api/v1/auth/csrf",
    "/api/v1/auth/session",
    `/api/v1/config?shop_id=${id}`,
    "/api/v1/admin/operations",
    "/api/v1/tasks?limit=20&state=completed",
    `/api/v1/tasks/${id}`,
    `/api/v1/tasks/${id}/report?report_id=${other}`,
    `/api/v1/tasks/${id}/explanation?report_id=${other}`,
    `/api/v1/tasks/${id}/plans?limit=20&cursor=offline-cursor`,
    `/api/v1/tasks/${id}/plans/2`,
    `/api/v1/tasks/${id}/events`,
    `/api/v1/tasks/${id}/execution`,
    "/api/v1/approvals?view=mine&state=pending",
    `/api/v1/approvals/${id}`,
    "/api/v1/replenishment-items?state=open",
    `/api/v1/replenishment-items/${id}`,
    `/api/v1/requests/${id}?operation=decision`,
  ]);
  expect(() => client.task("..")).toThrow(P3Failure);
  expect(() => client.plan(id, 0)).toThrow(P3Failure);
  expect(calls).toHaveLength(17);
});

test("匿名bootstrap不授业务权；login白名单、logout故障仍清会话", async () => {
  const calls: { path: string; init: RequestInit }[] = [];
  const client = new P3Client({
    origin: "https://test.invalid",
    transport: async (url, init) => {
      calls.push({ path: url.pathname, init });
      if (url.pathname.endsWith("/csrf"))
        return response({
          ...envelope,
          identity_mode: "anonymous_bootstrap",
          csrf_token: token(),
          bootstrap_expires_at: "2026-10-10T12:05:00Z",
        });
      if (url.pathname.endsWith("/logout"))
        throw new Error("offline disconnect");
      return response(session());
    },
  });
  await client.bootstrap();
  const input = {
    schema_version: "p3-web-v1",
    request_key: id,
    action: "close",
    reason: "offline",
    expected_version: 1,
  } as const;
  expect(() => client.prepareResolve(id, input)).toThrow(P3Failure);
  await client.login({
    schema_version: "p3-web-v1",
    login: "fixture",
    password: offlinePassword(),
    role: "admin",
  } as DTO["LoginInput"]);
  expect(JSON.parse(String(calls[1].init.body))).toEqual({
    schema_version: "p3-web-v1",
    login: "fixture",
    password: offlinePassword(),
  });
  await expect(client.logout()).rejects.toMatchObject({
    code: "SERVICE_UNAVAILABLE",
  });
  expect(() => client.prepareResolve(id, input)).toThrow(P3Failure);
});

test("创建任务两种input严格保留各自来源，额外actor/nonce/计划不传输", async () => {
  const bodies: unknown[] = [];
  const client = new P3Client({
    origin: "https://test.invalid",
    transport: async (_url, init) => {
      if (init.method === "GET") return response(session());
      bodies.push(JSON.parse(String(init.body)));
      return response(envelope);
    },
  });
  await client.session();
  const fromReport = {
    schema_version: "p3-web-v1",
    mode: "from_report",
    request_key: id,
    source_task_id: id,
    source_report_id: other,
    snapshot_id: id,
    facts_hash: "f".repeat(64),
    actor: other,
    nonce: "old",
    plan_version: 7,
  } as const;
  await client.prepareTask(fromReport).send();
  expect(bodies[0]).toEqual({
    schema_version: "p3-web-v1",
    mode: "from_report",
    request_key: id,
    source_task_id: id,
    source_report_id: other,
    snapshot_id: id,
    facts_hash: "f".repeat(64),
  });
  const newCycle = {
    schema_version: "p3-web-v1",
    mode: "new_cycle",
    request_key: other,
    shop_id: id,
    parameters: {
      source_mode: "mock",
      dataset_version: "inventory-v1",
      fixture_case: "baseline",
      L: 7,
      R: 3,
      S: 1,
      nonce: "old",
    },
    plan_version: 7,
  } as const;
  await client.prepareTask(newCycle).send();
  expect(bodies[1]).toEqual({
    schema_version: "p3-web-v1",
    mode: "new_cycle",
    request_key: other,
    shop_id: id,
    parameters: {
      source_mode: "mock",
      dataset_version: "inventory-v1",
      fixture_case: "baseline",
      L: 7,
      R: 3,
      S: 1,
    },
  });
});
