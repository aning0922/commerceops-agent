import { redirect } from "next/navigation";
import { Console } from "../../components/console";
import { mockView } from "../../lib/mock-source";
export const dynamic = "force-dynamic";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ path?: string[] }>;
  searchParams: Promise<{ version?: string }>;
}) {
  const path = "/" + ((await params).path ?? []).join("/");
  const query = await searchParams;
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
    selectedView.facts = view.facts.filter((x) =>
      ["SKU-A", "SKU-B"].includes(x.key),
    );
    selectedView.planKeys = selectedView.facts
      .filter((x) => view.planKeys.includes(x.key))
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
