import { redirect } from "next/navigation";
import { Console } from "../../components/console";
import { mockView } from "../../lib/mock-source";
import { LiveConsole } from "../../components/live-console";
import { B04OfflinePreview } from "../../components/b04-offline-preview";
import { offlineScenarios } from "../../lib/b04-offline-source";
export const dynamic = "force-dynamic";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ path?: string[] }>;
  searchParams: Promise<{
    version?: string;
    report_id?: string;
    operation?: string;
    scenario?: string;
  }>;
}) {
  const path = "/" + ((await params).path ?? []).join("/");
  const query = await searchParams;
  if (process.env.COMMERCEOPS_UI_MODE === "live") {
    const origin = process.env.COMMERCEOPS_API_ORIGIN;
    const localHttp = process.env.COMMERCEOPS_WEB_TRANSPORT === "local_http";
    let valid = false;
    try {
      const url = new URL(origin ?? "");
      valid =
        url.origin === origin &&
        !url.username &&
        !url.password &&
        (url.protocol === "https:" ||
          (localHttp &&
            url.protocol === "http:" &&
            ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)));
    } catch {
      /* Only public origin configuration is read; no .env/session/credentials. */
    }
    if (!valid)
      return (
        <LiveConsole
          path="/access"
          query={{}}
          origin={null}
          localHttp={localHttp}
        />
      );
    return (
      <LiveConsole
        path={path}
        query={query}
        origin={origin!}
        localHttp={localHttp}
      />
    );
  }
  if (
    process.env.COMMERCEOPS_UI_MODE === "mock" &&
    process.env.COMMERCEOPS_MOCK_BATCH === "b04" &&
    (process.env.COMMERCEOPS_MOCK_ROLE ?? "operator") === "operator"
  ) {
    const scenario =
      offlineScenarios.find((value) => value === query.scenario) ?? "ready";
    return (
      <B04OfflinePreview
        path={path}
        scenario={scenario}
        role={process.env.COMMERCEOPS_MOCK_ROLE ?? "operator"}
      />
    );
  }
  const requestedVersion = query.version;
  const validVersion =
    requestedVersion === undefined ||
    requestedVersion === "1" ||
    requestedVersion === "2";
  const view = mockView(
    typeof requestedVersion === "string" ? requestedVersion : undefined,
  );
  // Validate exact fixture IDs on the server before passing any business data to the client.
  const tasks = view.tasks.map((x) => x.id);
  const safe =
    [
      "/",
      "/login",
      "/access",
      "/tasks",
      "/approvals",
      "/replenishment-items",
      "/admin/operations",
    ].includes(path) ||
    tasks.some((id) =>
      [`/tasks/${id}`, `/tasks/${id}/report`, `/tasks/${id}/events`].includes(
        path,
      ),
    ) ||
    path === `/approvals/${view.approvalId}` ||
    view.items.some((x) => path === `/replenishment-items/${x.id}`);
  const businessPath =
    path.startsWith("/tasks") ||
    path.startsWith("/approvals") ||
    path.startsWith("/replenishment-items");
  const access =
    !safe ||
    !validVersion ||
    (businessPath && !view.businessRead) ||
    (path === "/admin/operations" && !view.adminRead);
  if (access && path !== "/access") redirect("/access");
  const resolved = path === "/" ? view.home : access ? "/access" : path;
  const task = view.tasks.find((x) => path.startsWith(`/tasks/${x.id}`));
  const selectedView = {
    ...view,
    taskId: task?.id ?? view.taskId,
    taskStatus: task?.status ?? view.taskStatus,
    reportId: task ? `REPORT-${task.id.slice(4)}` : view.reportId,
    snapshotId: task ? `DEMO-SNAPSHOT-${task.id.slice(-3)}` : view.snapshotId,
    approvalId: task && task.id !== "INV-DEMO-008" ? "" : view.approvalId,
  };
  if (task && ["queued", "analyzing"].includes(task.status)) {
    selectedView.facts = [];
    selectedView.planKeys = [];
    selectedView.items = [];
    selectedView.reportId = "";
    selectedView.snapshotId = "";
  }
  if (task?.id === "INV-DEMO-007") {
    if (requestedVersion !== undefined && requestedVersion !== "1")
      redirect("/access");
    selectedView.version = 1;
    selectedView.historical = false;
    selectedView.historyAvailable = false;
    selectedView.facts = view.completedFacts;
    selectedView.planKeys = selectedView.facts
      .filter((x) => x.suggested !== null && x.suggested > 0)
      .map((x) => x.key);
    selectedView.items = [];
  }
  const publicView =
    resolved === "/access" ||
    resolved === "/login" ||
    resolved === "/admin/operations"
      ? {
          ...selectedView,
          tasks: [],
          items: [],
          facts: [],
          completedFacts: [],
          historyAvailable: false,
          planKeys: [],
          taskId: "",
          approvalId: "",
          reportId: "",
          snapshotId: "",
          taskStatus: "",
          version: 0,
          historical: false,
        }
      : selectedView;
  return <Console path={resolved} view={publicView} />;
}
