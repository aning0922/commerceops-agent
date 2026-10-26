// Browser-only injected transport. Never starts an API/service or sends network requests.
import React from "react";
import { createRoot } from "react-dom/client";
import { CreateTaskDialog } from "../../../../frontend/components/live-actions";
import { P3Client } from "../../../../frontend/lib/p3-transport";
import { verifyReadResponse } from "../../../../frontend/lib/p3-live-client";
import { offlineEnvelope, offlineId } from "../../../../frontend/lib/b04-offline-source";
import { fixtureClient, report } from "../phase4/fixtures";
import { wooConfig, wooN01, response, operatorSession, shop, version } from "./creation-fixtures";
import type { DTO } from "../../../../frontend/lib/p3-present";
import type {} from "./test-control";
const root = createRoot(document.getElementById("p5-root")!);
window.__p5CreateStart = async (kind = "woo", mode = "success", fromReport = false, operator = true) => {
  const calls: { method: string; path: string; body?: string }[] = [];
  let sourceKind = kind, sourceVersion = version, writeMode = mode;
  let release = () => {};
  let saved: DTO["CreateTaskReceipt"] | null = null;
  const failure = () => response({ schema_version: "p3-web-v1", trace_id: offlineId(99), server_time: null,
    error: { code: "RESOURCE_NOT_FOUND", safe_message: "synthetic unavailable", retryable: false, receipt: null } }, 404);
  const legacy = fixtureClient("not_ready", () => {}, calls, { release() {} });
  const client = kind === "mock" ? legacy : new P3Client({ origin: "https://offline.invalid", verifyResponse: verifyReadResponse,
    transport: async (url, init) => {
      calls.push({ method: init.method!, path: url.pathname, ...(init.body ? { body: String(init.body) } : {}) });
      if (url.pathname.endsWith("/session")) return response(operatorSession());
      if (url.pathname === "/api/v1/config") return response(wooConfig(sourceKind, sourceVersion));
      if (url.pathname.endsWith("/preflight")) {
        const result = wooN01(JSON.parse(String(init.body)));
        if (mode === "late_preflight") await new Promise<void>((resolve) => { release = resolve; });
        return response(result);
      }
      if (url.pathname === "/api/v1/tasks" && init.method === "POST") {
        const input = JSON.parse(String(init.body));
        saved = { ...offlineEnvelope, request_key: input.request_key, task_id: offlineId(301),
          source_task_id: offlineId(302), state: "queued", duplicate: saved !== null };
        if (writeMode === "pending") await new Promise<void>((resolve) => { release = resolve; });
        if (writeMode === "unknown" || writeMode === "pending") throw new Error("synthetic ACK loss");
        return response(saved, 202);
      }
      if (url.pathname.startsWith("/api/v1/requests/")) return writeMode === "success" && saved
        ? response({ ...offlineEnvelope, request_key: saved.request_key, status: "succeeded", receipt: { operation: "create_task", result: saved } }) : failure();
      return failure();
    } });
  await client.session();
  const shops = operator ? [shop] : [];
  const render = () => root.render(<main>
    <p>合成组件测试 · 不代表真实API、PG或Woo验收。</p>
    <CreateTaskDialog client={client} shops={shops} source={fromReport ? report.source : undefined}
      close={() => root.render(<p>测试草稿已关闭</p>)} />
  </main>);
  window.__p5CreateCalls = () => structuredClone(calls);
  window.__p5CreateUpdate = (nextKind, nextVersion = version) => { sourceKind = nextKind; sourceVersion = nextVersion; render(); };
  window.__p5CreateRelease = () => release();
  window.__p5CreateWriteMode = (next) => { writeMode = next; };
  render();
};
