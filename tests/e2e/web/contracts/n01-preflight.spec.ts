import { test, expect } from "../../../../frontend/tooling/web-test";
import {
  validN01Input, validN01Response, n01MatchesInput, n01CandidateText,
} from "../../../../frontend/lib/p4-n01";
import type { N01Input, N01Response } from "../../../../frontend/lib/p4-n01";
import { P3Client } from "../../../../frontend/lib/p3-transport";
import { readTransport, verifyReadResponse } from "../../../../frontend/lib/p3-live-client";
const input: N01Input = {
  schema_version: "p3-web-v1",
  shop_id: "00000000-0000-4000-8000-000000000001",
  fixture_case: "baseline",
  text: "分析库存 L=3 R=7 S=2",
};
function ready(): N01Response {
  return {
    schema_version: "p3-web-v1", identity_mode: "session",
    server_time: "2026-10-11T00:00:00Z",
    trace_id: "00000000-0000-4000-8000-000000000002",
    preflight: {
      schema_version: "p4-n01-web-v1", status: "ready", reason: "EXPLICIT_PARAMETERS",
      shop_id: input.shop_id,
      source: { source_mode: "mock", dataset_version: "inventory-v1", fixture_case: "baseline", evidence_mode: "not_used" },
      window: { kind: "last_seven_complete_days", start: "2026-10-03T16:00:00Z", end: "2026-10-10T16:00:00Z", timezone: "Asia/Shanghai", as_of: "2026-10-11T00:00:00Z", source: "mock_fixture" },
      scope: { kind: "all_fixture_products", shop_id: input.shop_id, source: "selected_shop" },
      candidates: [
        { name: "L", value: 3, source: "explicit_text", start: 5, end: 8 },
        { name: "R", value: 7, source: "explicit_text", start: 9, end: 12 },
        { name: "S", value: 2, source: "explicit_text", start: 13, end: 16 },
      ],
      missing: [],
      draft: { source_mode: "mock", dataset_version: "inventory-v1", fixture_case: "baseline", L: 3, R: 7, S: 2 },
      requires_confirmation: true, execution_available: false,
    },
  };
}
test("N01 严格输入和闭合ready绑定；不接actor/request_key或默认补字段", () => {
  expect(validN01Input(input)).toBe(true);
  expect(validN01Input({ ...input, request_key: input.shop_id } as N01Input)).toBe(false);
  expect(validN01Input({ ...input, text: "😀".repeat(2001) })).toBe(false);
  const read = ready();
  expect(validN01Response(200, read)).toBe(true);
  expect(n01MatchesInput(read, input)).toBe(true);
  expect(n01MatchesInput(read, { ...input, fixture_case: "unknown_in_transit" })).toBe(false);
  delete (read.preflight as Partial<N01Response["preflight"]>).requires_confirmation;
  expect(validN01Response(200, read)).toBe(false);
});
test("N01 不接受假ready/越界/重复/异shop/可执行候选", () => {
  for (const mutate of [
    (p: N01Response["preflight"]) => { p.candidates[0].value = 366; },
    (p: N01Response["preflight"]) => { p.candidates[1].name = "L"; },
    (p: N01Response["preflight"]) => { p.scope.shop_id = "00000000-0000-4000-8000-000000000099"; },
    (p: N01Response["preflight"]) => { p.reason = "INVALID_PARAMETERS"; },
    (p: N01Response["preflight"]) => { p.draft = { ...p.draft!, L: 5 }; },
    (p: N01Response["preflight"]) => { p.window.as_of = "2026-10-11T08:00:00+08:00"; },
  ]) {
    const read = ready(); mutate(read.preflight);
    expect(validN01Response(200, read)).toBe(false);
  }
  const read = ready();
  expect(validN01Response(200, { ...read, preflight: { ...read.preflight, execution_available: true } })).toBe(false);
});
test("N01 clarify缺项与invalid/unsupported分开；demo不成为ready", () => {
  const read = ready(), p = read.preflight;
  p.status = "clarify"; p.reason = "MISSING_PARAMETERS"; p.draft = null;
  p.missing = ["R", "S"];
  p.candidates.slice(1).forEach((c) => { c.source = "demo_assumption"; c.start = null; c.end = null; });
  expect(validN01Response(200, read)).toBe(true);
  p.status = "ready";
  expect(validN01Response(200, read)).toBe(false);
  p.status = "clarify"; p.reason = "INVALID_PARAMETERS";
  expect(validN01Response(200, read)).toBe(false);
  p.missing = ["L", "R", "S"];
  p.candidates.forEach((c) => { c.source = "demo_assumption"; c.start = null; c.end = null; });
  expect(validN01Response(200, read)).toBe(true);
  p.status = "unsupported"; p.reason = "UNSUPPORTED_TEXT";
  expect(validN01Response(200, read)).toBe(true);
});
test("N01 Unicode来源用code point半开位置，不按UTF16误读或越界", () => {
  const text = "😀 L=3", candidate = ready().preflight.candidates[0];
  candidate.start = 2; candidate.end = 5;
  expect(n01CandidateText(text, candidate)).toBe("L=3");
  const read = ready(); read.preflight.candidates[0].end = 2001;
  expect(n01MatchesInput(read, input)).toBe(false);
});
test("N01 精确POST白名单/CSRF原输入只读transport；无session/多字段不发送", async () => {
  const calls: { path: string; method: string; body?: string; csrf: string | null }[] = [];
  const client = new P3Client({ origin: "http://127.0.0.1:3999", localHttp: true,
    transport: readTransport(async (url, init) => {
      calls.push({ path: url.pathname, method: init.method!, body: init.body as string | undefined, csrf: new Headers(init.headers).get("X-CSRF-Token") });
      return new Response(JSON.stringify(init.method === "GET"
        ? { ...ready(), csrf_token: "c".repeat(43), principal: { principal_id: input.shop_id } }
        : ready()), { headers: { "Content-Type": "application/json" } });
    }),
  });
  await expect(client.preflight(input)).rejects.toMatchObject({ code: "CSRF_NOT_READY" });
  expect(calls).toHaveLength(0);
  await client.session();
  await expect(client.preflight({ ...input, actor: "ignored" } as N01Input)).rejects.toMatchObject({ code: "INVALID_REQUEST" });
  expect(calls).toHaveLength(1);
  expect(await client.preflight(input)).toEqual(ready());
  expect(calls[1]).toEqual({ path: "/api/v1/tasks/preflight", method: "POST", body: JSON.stringify(input), csrf: "c".repeat(43) });
  expect(verifyReadResponse("POST", "/api/v1/tasks/preflight", 200, ready())).toBe(true);
  expect(verifyReadResponse("GET", "/api/v1/tasks/preflight", 200, ready())).toBe(false);
});
test("N01 预解析503为安全读取失败，401使缓存失效，不冒业务提交unknown", async () => {
  let status = 503, cleared = 0;
  const client = new P3Client({ origin: "http://127.0.0.1:3999", localHttp: true, onSessionInvalidated: () => { cleared++; },
    transport: async (_url, init) => new Response(JSON.stringify(init.method === "GET"
      ? { ...ready(), csrf_token: "c".repeat(43), principal: { principal_id: input.shop_id } }
      : { schema_version: "p3-web-v1", server_time: ready().server_time, trace_id: ready().trace_id, error: { code: status === 401 ? "SESSION_INVALID" : "SERVICE_UNAVAILABLE" } }),
    { status: init.method === "GET" ? 200 : status, headers: { "Content-Type": "application/json" } }),
  });
  await client.session();
  await expect(client.preflight(input)).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
  status = 401;
  await expect(client.preflight(input)).rejects.toMatchObject({ code: "SESSION_INVALID" });
  expect(cleared).toBe(1);
  await expect(client.preflight(input)).rejects.toMatchObject({ code: "CSRF_NOT_READY" });
});
