import { test, expect } from "../../../../frontend/tooling/web-test";
import { commerceCreationGate, validCommerceCapability, validWooCreateInput } from "../../../../frontend/lib/p5-commerce-source";
import { validN01Input, validN01Response, n01MatchesInput } from "../../../../frontend/lib/p4-n01";
import type { WooN01Input, WooN01Response } from "../../../../frontend/lib/p4-n01";
import { P3Client } from "../../../../frontend/lib/p3-transport";
import { verifyReadResponse } from "../../../../frontend/lib/p3-live-client";
import type { DTO } from "../../../../frontend/lib/p3-present";
import { offlineEnvelope, offlineId } from "../../../../frontend/lib/b04-offline-source";
import { wooConfig, wooInput, wooN01, operatorSession, response, shop, version } from "../phase5/creation-fixtures";
type Mutable<T> = { -readonly [P in keyof T]: Mutable<T[P]> };
const create = (): DTO["CreateNewCycle"] => ({ schema_version: "p3-web-v1", mode: "new_cycle",
  request_key: offlineId(800), shop_id: shop,
  parameters: { source_mode: "woocommerce_test", source_config_version: version, L: 3, R: 7, S: 2 } });
test("selected-shop capability requires operator, exact shop, enabled valid source; known Woo never falls back Mock", () => {
  expect(commerceCreationGate(wooConfig(), shop, [shop])).toEqual({ allowed: true, kind: "woocommerce_test", version });
  expect(commerceCreationGate(wooConfig("mock"), shop, [shop])).toEqual({ allowed: true, kind: "mock", version: null });
  for (const read of [null, wooConfig("disabled"), wooConfig("missing"), { ...wooConfig(), shop_id: offlineId(999) }])
    expect(commerceCreationGate(read, shop, [shop]).allowed).toBe(false);
  expect(commerceCreationGate(wooConfig(), shop, []).allowed).toBe(false);
  for (const mutate of [
    (c: Mutable<DTO["DeploymentConfig"]>) => { c.commerce_source!.source_kind = "mock"; },
    (c: Mutable<DTO["DeploymentConfig"]>) => { c.commerce_source!.source_config_version = " "; },
    (c: Mutable<DTO["DeploymentConfig"]>) => { c.commerce_source!.source_config_version = null; },
    (c: Mutable<DTO["DeploymentConfig"]>) => { (c as {source_mode: string}).source_mode = "unknown"; },
  ]) {
    const read = wooConfig(); mutate(read.config as Mutable<DTO["DeploymentConfig"]>);
    expect(commerceCreationGate(read, shop, [shop]).allowed).toBe(false);
    expect(verifyReadResponse("GET", "/api/v1/config", 200, read)).toBe(false);
  }
  expect(validCommerceCapability(wooConfig().config)).toBe(true);
});
test("Woo create contract rejects fixture/now/URL/private binding/extra top fields, coercion and missing version", () => {
  expect(validWooCreateInput(create())).toBe(true);
  for (const extra of [{ fixture_case: "baseline" }, { now: "2026-10-26T00:00:00Z" },
    { base_url: "https://offline.invalid" }, { binding: {} }, { L: "3" },
    { source_config_version: null }, { source_config_version: "" }, { R: 366 }, { S: -1 }]) {
    expect(validWooCreateInput({ ...create(), parameters: { ...create().parameters, ...extra } })).toBe(false);
  }
  expect(validWooCreateInput({ ...create(), actor: shop })).toBe(false);
  const input = create(); delete (input.parameters as {source_config_version?: string}).source_config_version;
  expect(validWooCreateInput(input)).toBe(false);
});
test("Woo N01 strict readonly DTO binds source version, selected shop, Unicode spans, candidates and configuration window", () => {
  const input = wooInput(), read = wooN01(input);
  expect(validN01Input(input)).toBe(true);
  expect(validN01Response(200, read)).toBe(true);
  expect(n01MatchesInput(read, input)).toBe(true);
  const reordered = wooN01(); reordered.preflight.candidates.reverse();
  expect(validN01Response(200, reordered)).toBe(true);
  expect(n01MatchesInput(reordered, input)).toBe(true);
  expect(n01MatchesInput(read, { ...input, source_config_version: "different" })).toBe(false);
  expect(n01MatchesInput(read, { ...input, shop_id: offlineId(999) })).toBe(false);
  for (const extra of [{ fixture_case: "baseline" }, { request_key: shop }, { now: "2026-10-26" }])
    expect(validN01Input({ ...input, ...extra } as WooN01Input)).toBe(false);
  expect(validN01Input({ ...input, text: "😀".repeat(2000) })).toBe(true);
  expect(validN01Input({ ...input, text: "😀".repeat(2001) })).toBe(false);
  for (const mutate of [
    (p: Mutable<WooN01Response["preflight"]>) => { p.draft!.source_config_version = "different"; },
    (p: Mutable<WooN01Response["preflight"]>) => { p.scope.shop_id = offlineId(999); },
    (p: Mutable<WooN01Response["preflight"]>) => { p.source.source_config_version = " "; },
    (p: Mutable<WooN01Response["preflight"]>) => { delete (p as Partial<typeof p>).requires_confirmation; },
    (p: Mutable<WooN01Response["preflight"]>) => { p.candidates[1].name = "L"; },
    (p: Mutable<WooN01Response["preflight"]>) => { p.window.as_of = p.window.start; },
  ]) {
    const changed = wooN01(); mutate(changed.preflight as Mutable<WooN01Response["preflight"]>);
    expect(validN01Response(200, changed)).toBe(false);
  }
});
test("Woo transport rejects malformed create before projection, preflight has zero T1; original bytes/key survive UNKNOWN", async () => {
  const calls: { method: string; path: string; body?: string }[] = [];
  let rejectWrite = true;
  const client = new P3Client({ origin: "https://offline.invalid", verifyResponse: verifyReadResponse,
    transport: async (url, init) => {
      calls.push({ method: init.method!, path: url.pathname, body: init.body as string | undefined });
      if (url.pathname.endsWith("/session")) return response(operatorSession());
      if (url.pathname.endsWith("/preflight")) return response(wooN01(JSON.parse(String(init.body))));
      if (rejectWrite) throw new Error("synthetic ACK loss");
      return response({ ...offlineEnvelope, request_key: offlineId(800), task_id: offlineId(301), source_task_id: offlineId(302), state: "queued", duplicate: true }, 202);
    } });
  await client.session();
  await client.preflight(wooInput());
  expect(calls.filter((c) => c.path === "/api/v1/tasks")).toHaveLength(0);
  expect(JSON.parse(calls[1].body!)).toEqual(wooInput());
  expect(() => client.prepareTask({ ...create(), parameters: { ...create().parameters, fixture_case: "baseline" } } as DTO["CreateTaskInput"])).toThrow();
  const input = create(), prepared = client.prepareTask(input);
  (input.parameters as {L:number}).L = 99;
  await expect(prepared.send()).rejects.toMatchObject({ code: "WRITE_RESULT_UNKNOWN" });
  expect(calls.filter((c) => c.path === "/api/v1/tasks")).toHaveLength(1);
  rejectWrite = false;
  await prepared.send(); // Explicit original-key recovery, never an automatic retry.
  const writes = calls.filter((c) => c.path === "/api/v1/tasks");
  expect(writes).toHaveLength(2);
  expect(writes[0].body).toBe(writes[1].body);
  expect(JSON.parse(writes[0].body!)).toEqual(create());
});
test("Woo response mismatch is readonly failure; source-unavailable error is safe and never implies T1 unknown", async () => {
  let unavailable = false;
  const client = new P3Client({ origin: "https://offline.invalid", verifyResponse: verifyReadResponse,
    transport: async (url) => url.pathname.endsWith("/session") ? response(operatorSession()) : unavailable
      ? response({ schema_version: "p3-web-v1", server_time: offlineEnvelope.server_time, trace_id: offlineEnvelope.trace_id, error: { code: "COMMERCE_SOURCE_UNAVAILABLE", safe_message: "private path must not display", retryable: false, receipt: null } }, 409)
      : response(wooN01({ ...wooInput(), source_config_version: "different" })) });
  await client.session();
  await expect(client.preflight(wooInput())).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  unavailable = true;
  await expect(client.preflight(wooInput())).rejects.toMatchObject({ code: "COMMERCE_SOURCE_UNAVAILABLE" });
});
