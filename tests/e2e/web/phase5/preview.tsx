// Test-only memory component page. No product route, identity, API or database.
import React from "react";
import { createRoot } from "react-dom/client";
import { BusinessSourceNotice, LiveReport } from "../../../../frontend/components/live-readviews";
import { sourceReport } from "./source-fixtures";
import { fixtureClient } from "../phase4/fixtures";
const root = createRoot(document.getElementById("p5-root")!);
const client = fixtureClient("not_ready", () => {}, [], { release() {}, revoke() {} });
import type {} from "./test-control";
window.__p5Render = (mode) => {
  const kind = mode === "mock" ? "mock" : "woocommerce_test";
  root.render(
    <main>
      <p>展示层合成测试 · 注入冻结 DTO，无真实会话、API、PG 或 Woo 请求。</p>
      <div className="mock-banner" data-test-banner>
        <BusinessSourceNotice fixtureMode={mode === "offline"} kind={mode === "missing" ? null : kind} />
      </div>
      {mode !== "missing" && <LiveReport key={mode} read={sourceReport(kind, mode === "partial")}
        client={client} config={null} />}
    </main>,
  );
};
window.__p5Render("woo");
