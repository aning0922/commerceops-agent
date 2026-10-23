import { test, expect } from "../../../../frontend/tooling/web-test";
import { verifyReadResponse } from "../../../../frontend/lib/p3-live-client";
import {
  eventsBound,
  projectionMeaning,
  syncMeaning,
} from "../../../../frontend/lib/p4-read-facts";
import {
  offlineEnvelope,
  offlineId,
  offlineSession,
} from "../../../../frontend/lib/b04-offline-source";
import { fixtureClient, task } from "../phase4/fixtures";
import { readGates, readSync, readEvents } from "../phase4/read-fixtures";

test("A03原22操作严格新字段：当前identity aliases/真实与Fake gate/跨字段一致，不带平台定位", () => {
  const session = offlineSession();
  expect(verifyReadResponse("GET", "/api/v1/auth/session", 200, session)).toBe(
    true,
  );
  const { linked_channels: _linked, ...missing } = session.principal;
  expect(
    verifyReadResponse("GET", "/api/v1/auth/session", 200, {
      ...session,
      principal: missing,
    }),
  ).toBe(false);
  expect(
    verifyReadResponse("GET", "/api/v1/auth/session", 200, {
      ...session,
      principal: { ...session.principal, open_id: "private-placeholder" },
    }),
  ).toBe(false);
  const gate = {
    ...readGates("c2_current")[1],
    verification_mode: "controlled_sdk" as const,
  };
  const config = {
    ...offlineEnvelope,
    shop_id: offlineId(101),
    config: {
      ...session.config,
      sender_gates: [gate],
      external_sender_enabled: true,
    },
  };
  expect(verifyReadResponse("GET", "/api/v1/config", 200, config)).toBe(true);
  const fake = {
    ...config,
    config: {
      ...config.config,
      sender_gates: readGates("c2_current"),
      external_sender_enabled: false,
    },
  };
  expect(verifyReadResponse("GET", "/api/v1/config", 200, fake)).toBe(true);
  for (const extra of [
    { ...fake.config, external_sender_enabled: true },
    { ...config.config, sender_gates: [{ ...gate, sender_enabled: false }] },
    { ...config.config, sender_gates: [{ ...gate, verification_mode: null }] },
    { ...config.config, sender_gates: [{ ...gate, worker_backend_pid: 99 }] },
  ])
    expect(
      verifyReadResponse("GET", "/api/v1/config", 200, {
        ...config,
        config: extra,
      }),
    ).toBe(false);
});

test("A03历史v1核实不冒当前v2/Fake不冒平台；unknown/stale/null保留且投影字段严格", () => {
  const current = task(),
    history = readSync("c2_history");
  const read = { ...current, task: { ...current.task, sync: history } };
  expect(
    verifyReadResponse(
      "GET",
      `/api/v1/tasks/${current.task.task_id}`,
      200,
      read,
    ),
  ).toBe(true);
  expect(syncMeaning(history)).toContain("当前目标版本尚未核实");
  expect(projectionMeaning(history.projections[0])).toContain(
    "不能证明当前目标 v2 已同步",
  );
  expect(syncMeaning(readSync("c2_current"))).toContain("离线 Fake");
  expect(syncMeaning(readSync("c2_unknown"))).toContain("未知");
  expect(projectionMeaning(readSync("c2_stale").projections[0])).toContain(
    "历史投影",
  );
  for (const changed of [
    { ...history.projections[0], is_current_version: true },
    { ...history.projections[0], observed_version: null },
    { ...history.projections[0], observed_version: 2 },
    { ...history.projections[0], attempts: true },
    { ...history.projections[0], attempts: -1 },
    ...[
      "record_id",
      "external_id",
      "target_key",
      "client_token",
      "app_token",
      "open_id",
      "worker_backend_pid",
    ].map((key) => ({
      ...history.projections[0],
      [key]: "private-placeholder",
    })),
  ])
    expect(
      verifyReadResponse("GET", `/api/v1/tasks/${current.task.task_id}`, 200, {
        ...read,
        task: { ...read.task, sync: { ...history, projections: [changed] } },
      }),
    ).toBe(false);
});

test("A03trace绑定当前task/精确source/ref；SDK adapter/method/model类分开不伪工具链", () => {
  const current = task(),
    events = readEvents(current);
  const path = `/api/v1/tasks/${current.task.task_id}/events`;
  expect(verifyReadResponse("GET", path, 200, events)).toBe(true);
  expect(eventsBound(events, current)).toBe(true);
  expect(eventsBound(readEvents(current, "c2_bad_trace"), current)).toBe(false);
  const last = events.items[3];
  for (const tool of [
    { ...last.tool!, selected_by_model: true },
    { ...last.tool!, sdk_method: "bitable.v1.app_table_record.list" },
    { ...last.tool!, category: "sdk_method", sdk_method: null },
    { ...last.tool!, sdk_method: "arbitrary-private-method" },
  ])
    expect(
      verifyReadResponse("GET", path, 200, {
        ...events,
        items: [{ ...last, tool }],
      }),
    ).toBe(false);
  expect(
    verifyReadResponse("GET", path, 200, {
      ...events,
      items: [{ ...last, record_id: "private-placeholder" }],
    }),
  ).toBe(false);
  expect(
    eventsBound(
      { ...events, items: [{ ...last, result_ref: offlineId(999) }] },
      current,
    ),
  ).toBe(false);
});

test("A03新read DTO经实际P3Client消费仍只有GET，P4缓存NOT_READY无新模型", async () => {
  const calls: { method: string; path: string; body?: string }[] = [],
    hold = { release: () => {} };
  const client = fixtureClient("c2_events", () => {}, calls, hold);
  const session = await client.session();
  expect(session.principal.linked_channels).toEqual(["web", "feishu"]);
  const current = await client.task(task().task.task_id);
  const events = await client.events(current.task.task_id);
  expect(eventsBound(events, current)).toBe(true);
  expect(
    (await client.config(current.task.shop_id)).config.sender_gates,
  ).toHaveLength(2);
  await expect(
    client.explanation(current.task.task_id, current.source!.report_id),
  ).rejects.toMatchObject({ code: "NOT_READY" });
  expect(calls.every((call) => call.method === "GET")).toBe(true);
});
