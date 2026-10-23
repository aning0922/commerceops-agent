// Test-only component entry. Not imported by product routes or production builds.
import React, { useCallback } from "react";
import { createRoot } from "react-dom/client";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { LiveConsole } from "../../../../frontend/components/live-console";
import { report, fixtureClient } from "./fixtures";
import type {} from "./test-control";
const hold = { release: () => {}, revoke: () => {} };
const root = createRoot(document.getElementById("p4-root")!);
const router = {
  bfcacheId: "p4-offline-preview",
  back: () => {},
  forward: () => {},
  refresh: () => {},
  push: () => {},
  replace: () => {},
  prefetch: async () => {},
};
function Preview({ mode }: { mode: string }) {
  const taskView = mode.startsWith("task_");
  const scenario = taskView ? mode.slice(5) : mode;
  const factory = useCallback(
    (invalidate: () => void) =>
      fixtureClient(scenario, invalidate, window.__p4.calls, hold),
    [scenario],
  );
  return (
    <AppRouterContext.Provider value={router}>
      <p data-offline-proof>
        明确离线组件 Mock：memory
        API，无真实会话/数据库/provider。actual_provider 字段仅为固定历史样例。
      </p>
      <LiveConsole
        key={mode}
        path={
          mode === "c2_admin"
            ? "/admin/operations"
            : mode === "c2_items"
              ? "/replenishment-items"
              : mode === "c2_terminal"
                ? "/replenishment-items/00000000-0000-4000-8000-000000000001"
                : mode === "c2_admin_deep"
                  ? `/tasks/${report.task_id}`
                  : mode === "c2_events" || mode === "c2_bad_trace"
                    ? `/tasks/${report.task_id}/events`
                    : `/tasks/${report.task_id}${taskView ? "" : "/report"}`
        }
        query={{}}
        origin={null}
        localHttp={false}
        fixtureMode
        fixtureClient={factory}
      />
    </AppRouterContext.Provider>
  );
}
window.__p4 = {
  calls: [],
  render: (mode) => {
    window.__p4.calls.length = 0;
    root.render(<Preview key={mode} mode={mode} />);
  },
  release: () => hold.release(),
  revoke: () => hold.revoke(),
};
window.__p4.render("actual");
