"use client";
import { CreateTaskDialog, DecisionActions } from "./live-actions";
import { ExecutionFacts, ItemListFacts, ItemDetails } from "./item-views";
import { itemConsistent } from "../lib/p3-item-contract";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { createReadClient } from "../lib/p3-live-client";
import type { A01ReadClient } from "../lib/p3-live-client";
import { P3Failure } from "../lib/p3-transport";
import type { DTO } from "../lib/p3-present";
import {
  label,
  localTime,
  reportBound,
  newCycleEligibility,
} from "../lib/p3-present";
import { Card, Disabled, Modal, Notice, Status } from "./ui";
import {
  LiveReport,
  PlanDetails,
  Source,
  Sync,
  VersionList,
  writePending,
} from "./live-readviews";
type Query = { version?: string; report_id?: string; operation?: string };
type PageData =
  | { kind: "tasks"; read: DTO["TaskList"] }
  | {
      kind: "task";
      read: DTO["TaskRead"];
      execution: DTO["ExecutionRead"] | null;
    }
  | {
      kind: "report";
      read: DTO["ReportRead"];
      versions: DTO["PlanList"];
      task: DTO["TaskRead"];
    }
  | { kind: "plans"; read: DTO["PlanList"]; taskId: string }
  | { kind: "plan"; read: DTO["PlanRead"] }
  | { kind: "approvals"; read: DTO["ApprovalList"] }
  | { kind: "approval"; read: DTO["ApprovalRead"] }
  | {
      kind: "events";
      read: DTO["EventsRead"];
      taskId: string;
      execution: DTO["ExecutionRead"] | null;
    }
  | { kind: "receipt"; read: DTO["RequestRead"] }
  | { kind: "operations"; read: DTO["OperationsRead"] }
  | { kind: "items"; read: DTO["ItemList"] }
  | { kind: "item"; read: DTO["ItemRead"] };
const uuid = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const taskRoute = new RegExp(
  `^/tasks/(${uuid})(?:/(report|events|plans)(?:/([1-9][0-9]*))?)?$`,
  "i",
);
const approvalRoute = new RegExp(`^/approvals/(${uuid})$`, "i");
const receiptRoute = new RegExp(`^/requests/(${uuid})$`, "i");
const itemRoute = new RegExp(`^/replenishment-items/(${uuid})$`, "i");
const uuidOnly = new RegExp(`^${uuid}$`, "i");
const titleOf = (path: string) =>
  path.endsWith("/report")
    ? "库存分析报告"
    : path.endsWith("/events")
      ? "Agent 执行轨迹"
      : path.includes("/plans")
        ? "冻结计划版本"
        : path.startsWith("/requests")
          ? "原请求回执"
          : path === "/tasks"
            ? "任务中心"
            : path.startsWith("/tasks/")
              ? "任务概览与结果"
              : path === "/approvals"
                ? "审批"
                : path.startsWith("/approvals/")
                  ? "审批详情"
                  : path === "/admin/operations"
                    ? "管理配置与异常说明"
                    : path.startsWith("/replenishment-items/")
                      ? "内部工作项详情"
                      : path === "/replenishment-items"
                        ? "内部补货"
                        : "访问限制与会话过期";
const messageOf = (error: unknown) =>
  error instanceof P3Failure ? error.message : "暂时无法安全读取。";
export function LiveConsole({
  path,
  query,
  origin,
  localHttp,
  fixtureMode = false,
  fixtureClient,
}: {
  path: string;
  query: Query;
  origin: string | null;
  localHttp: boolean;
  // Only the server-gated explicit Mock wrapper supplies this in-memory adapter.
  fixtureMode?: boolean;
  fixtureClient?: (invalidate: () => void) => A01ReadClient;
}) {
  const router = useRouter();
  const epoch = useRef(0);
  const heldWrite = useRef(false);
  const holdWrite = useCallback((held: boolean) => {
    heldWrite.current = held;
  }, []);
  const [session, setSession] = useState<DTO["SessionRead"] | null>(null);
  const [checking, setChecking] = useState(true);
  const [data, setData] = useState<{ path: string; value: PageData } | null>(
    null,
  );
  const [config, setConfig] = useState<DTO["ConfigRead"] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [panel, setPanel] = useState("");
  const [cursor, setCursor] = useState<string | undefined>();
  const [previous, setPrevious] = useState<(string | undefined)[]>([]);
  const [state, setState] = useState("");
  const [approvalView, setApprovalView] = useState<
    "visible" | "mine" | "history"
  >("visible");
  const [reload, setReload] = useState(0);
  const invalidate = useCallback(() => {
    heldWrite.current = false;
    epoch.current++;
    setSession(null);
    setData(null);
    setConfig(null);
    setPanel("");
    setChecking(false);
    setError(
      fixtureMode
        ? "离线401示例：身份、业务缓存与预备操作已清除。"
        : "会话已失效或授权已变更，请重新登录。",
    );
  }, [fixtureMode]);
  const client = useMemo(
    () =>
      fixtureMode && fixtureClient
        ? fixtureClient(invalidate)
        : origin
          ? createReadClient(origin, localHttp, invalidate)
          : null,
    [origin, localHttp, invalidate, fixtureMode, fixtureClient],
  );
  useEffect(() => {
    if (!client) {
      setChecking(false);
      setError("服务入口配置不可用。");
      return;
    }
    let active = true;
    const stamp = ++epoch.current;
    void client
      .session()
      .then((result) => {
        if (active && epoch.current === stamp) {
          setSession(result);
          setError("");
        }
      })
      .catch((error) => {
        if (active && epoch.current === stamp) setError(messageOf(error));
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
      epoch.current++;
    };
  }, [client]);
  useEffect(() => {
    setData(null);
    setConfig(null);
    setPanel("");
    setCursor(undefined);
    setPrevious([]);
    setState("");
    setApprovalView("visible");
  }, [path]);
  const capabilities = session?.principal.capabilities;
  useEffect(() => {
    if (!client || !session) return;
    if (path === "/" || path === "/login") {
      router.replace(session.principal.capabilities.home_path);
      return;
    }
    if (path === "/access") {
      setData(null);
      return;
    }
    let active = true;
    const stamp = ++epoch.current;
    setData(null);
    setConfig(null);
    setError("");
    const accept = () => active && epoch.current === stamp;
    async function load() {
      const cap = session!.principal.capabilities;
      let page: PageData;
      let shop: string | null = null;
      if (path === "/admin/operations") {
        if (!cap.can_read_operations) throw new P3Failure("ACCESS_DENIED");
        page = { kind: "operations", read: await client!.operations() };
      } else if (path === "/tasks") {
        if (!cap.can_read_tasks) throw new P3Failure("ACCESS_DENIED");
        page = {
          kind: "tasks",
          read: await client!.tasks({
            limit: 20,
            cursor,
            state: state ? (state as DTO["TaskSummary"]["state"]) : undefined,
          }),
        };
        shop =
          page.read.items[0]?.shop_id ??
          session!.principal.role_shop_grants.find(
            (x) => x.role === "operator" || x.role === "approver",
          )?.shop_id ??
          null;
      } else if (path === "/approvals") {
        if (!cap.can_read_approvals) throw new P3Failure("ACCESS_DENIED");
        page = {
          kind: "approvals",
          read: await client!.approvals({
            limit: 20,
            cursor,
            view: approvalView,
            state: state
              ? (state as DTO["ApprovalSummary"]["status"])
              : undefined,
          }),
        };
      } else if (path === "/replenishment-items") {
        if (!cap.can_read_tasks) throw new P3Failure("ACCESS_DENIED");
        const read = await client!.items({
          limit: 20,
          cursor,
          state: state ? (state as DTO["ItemSummary"]["state"]) : undefined,
        });
        page = { kind: "items", read };
        shop = read.items[0]?.shop_id ?? null;
      } else if (itemRoute.test(path)) {
        if (!cap.can_read_tasks) throw new P3Failure("ACCESS_DENIED");
        const id = path.match(itemRoute)![1];
        const read = await client!.item(id);
        if (read.item.item_id !== id || !itemConsistent(read))
          throw new P3Failure("INVALID_RESPONSE");
        page = { kind: "item", read };
        shop = read.item.shop_id;
      } else if (taskRoute.test(path)) {
        if (!cap.can_read_tasks) throw new P3Failure("ACCESS_DENIED");
        const [, id, section, version] = path.match(taskRoute)!;
        const task = await client!.task(id);
        if (task.task.task_id !== id) throw new P3Failure("INVALID_RESPONSE");
        shop = task.task.shop_id;
        let execution: DTO["ExecutionRead"] | null = null;
        if ((!section || section === "events") && task.execution_id) {
          execution = await client!.execution(id);
          if (
            execution.task_id !== id ||
            execution.execution_id !== task.execution_id
          )
            throw new P3Failure("INVALID_RESPONSE");
        }
        if (!section) page = { kind: "task", read: task, execution };
        else if (section === "report" && !version) {
          if (
            query.version !== undefined ||
            (query.report_id !== undefined && !uuidOnly.test(query.report_id))
          )
            throw new P3Failure("RESOURCE_NOT_FOUND");
          const report = await client!.report(id, query.report_id);
          if (!reportBound(report, id, query.report_id))
            throw new P3Failure("INVALID_RESPONSE");
          const versions = await client!.plans(id, { limit: 20, cursor });
          page = { kind: "report", read: report, versions, task };
        } else if (section === "events" && !version)
          page = {
            kind: "events",
            read: await client!.events(id, { limit: 20, cursor }),
            taskId: id,
            execution,
          };
        else if (section === "plans" && !version)
          page = {
            kind: "plans",
            read: await client!.plans(id, { limit: 20, cursor }),
            taskId: id,
          };
        else if (section === "plans" && version) {
          const plan = await client!.plan(id, Number(version));
          if (
            plan.plan.task_id !== id ||
            plan.plan.plan_version !== Number(version)
          )
            throw new P3Failure("INVALID_RESPONSE");
          page = { kind: "plan", read: plan };
        } else throw new P3Failure("RESOURCE_NOT_FOUND");
      } else if (approvalRoute.test(path)) {
        if (!cap.can_read_approvals) throw new P3Failure("ACCESS_DENIED");
        const id = path.match(approvalRoute)![1];
        const read = await client!.approval(id);
        if (
          read.approval.approval_id !== id ||
          read.approval.plan_id !== read.plan.plan_id ||
          read.approval.task_id !== read.plan.task_id ||
          read.approval.plan_hash !== read.plan.plan_hash ||
          read.approval.plan_version !== read.plan.plan_version
        )
          throw new P3Failure("INVALID_RESPONSE");
        const task = await client!.task(read.approval.task_id);
        shop = task.task.shop_id;
        page = { kind: "approval", read };
      } else if (receiptRoute.test(path)) {
        if (!cap.can_read_tasks) throw new P3Failure("ACCESS_DENIED");
        const id = path.match(receiptRoute)![1];
        const operation = query.operation;
        if (
          operation !== "create_task" &&
          operation !== "decision" &&
          operation !== "resolve"
        )
          throw new P3Failure("RESOURCE_NOT_FOUND");
        const receipt = await client!.requestReceipt(id, operation);
        if (
          receipt.request_key !== id ||
          receipt.receipt.operation !== operation
        )
          throw new P3Failure("INVALID_RESPONSE");
        page = { kind: "receipt", read: receipt };
      } else throw new P3Failure("RESOURCE_NOT_FOUND");
      const currentConfig = shop ? await client!.config(shop) : null;
      if (currentConfig && currentConfig.shop_id !== shop)
        throw new P3Failure("INVALID_RESPONSE");
      if (accept()) {
        setConfig(currentConfig);
        setData({ path, value: page });
      }
    }
    void load().catch((error) => {
      if (!accept()) return;
      setData(null);
      setConfig(null);
      setError(messageOf(error));
      if (
        error instanceof P3Failure &&
        ["ACCESS_DENIED", "RESOURCE_NOT_FOUND", "INVALID_REQUEST"].includes(
          error.code,
        )
      )
        router.replace("/access");
    });
    return () => {
      active = false;
      epoch.current++;
    };
  }, [
    client,
    session,
    path,
    query.report_id,
    query.version,
    query.operation,
    cursor,
    state,
    approvalView,
    reload,
    router,
  ]);
  // Revalidate on focus/visibility and explicit refresh; every API read rechecks DB identity.
  async function refresh() {
    if (!client) return;
    if (heldWrite.current) {
      // Still recheck current identity, while retaining the in-memory original write.
      // A 401/403 invalidates everything through the client's existing callback.
      try {
        const current = await client.session();
        if (
          current.principal.principal_id !== session?.principal.principal_id ||
          current.principal.organization_id !==
            session?.principal.organization_id ||
          current.principal.auth_version !== session?.principal.auth_version
        )
          client.clearSession();
      } catch (error) {
        setError(messageOf(error));
      }
      return;
    }
    setData(null);
    setConfig(null);
    setPanel("");
    const stamp = ++epoch.current;
    try {
      const s = await client.session();
      if (epoch.current === stamp) {
        setSession(s);
        setReload((x) => x + 1);
        setError("");
      }
    } catch (error) {
      if (epoch.current === stamp) setError(messageOf(error));
    }
  }
  useEffect(() => {
    const focus = () => {
      if (document.visibilityState === "visible" && session) void refresh();
    };
    window.addEventListener("focus", focus);
    document.addEventListener("visibilitychange", focus);
    return () => {
      window.removeEventListener("focus", focus);
      document.removeEventListener("visibilitychange", focus);
    };
  }, [client, session]);
  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!client || busy) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const login = String(values.get("login") ?? "");
    let password = String(values.get("password") ?? "");
    (form.elements.namedItem("password") as HTMLInputElement).value = "";
    setBusy(true);
    setError("");
    try {
      await client.bootstrap();
      const stamp = epoch.current;
      const result = await client.login({
        schema_version: "p3-web-v1",
        login,
        password,
      });
      password = "";
      if (epoch.current === stamp) {
        setSession(result);
        setError("");
        router.replace(result.principal.capabilities.home_path);
      }
    } catch (error) {
      setError(messageOf(error));
    } finally {
      password = "";
      setBusy(false);
    }
  }
  async function logout() {
    if (!client || busy) return;
    setData(null);
    setConfig(null);
    setPanel("");
    setBusy(true);
    try {
      await client.logout();
    } catch {
      setError("退出请求结果待核实；本地业务内容已清除，请重新核实会话。");
    } finally {
      setBusy(false);
      setSession(null);
      router.replace("/login");
    }
  }
  const page = data?.path === path ? data.value : null;
  const title = titleOf(path);
  function filter(value: string) {
    setData(null);
    setState(value);
    setCursor(undefined);
    setPrevious([]);
  }
  function next(nextCursor: string) {
    setData(null);
    setPrevious((x) => [...x, cursor]);
    setCursor(nextCursor);
  }
  const nextCursor =
    page && "read" in page && "next_cursor" in page.read
      ? page.read.next_cursor
      : page?.kind === "report"
        ? page.versions.next_cursor
        : null;
  const zone =
    config?.config.shop_timezone ?? session?.config.shop_timezone ?? null;
  if (!client)
    return (
      <div className="login-main">
        <Card title="服务入口不可用">
          <p>
            真实模式未配置有效入口，页面已关闭业务访问。没有Mock身份或样例回退。
          </p>
        </Card>
      </div>
    );
  if (!session)
    if (fixtureMode)
      return (
        <div data-source-mode="b04-offline">
          <main id="main">
            <Notice title="安全状态">
              {error || "正在读取固定离线合同示例。"}
            </Notice>
            <p>
              明确离线 Mock · 无真实身份/API/数据库，不显示已清除的业务对象。
            </p>
          </main>
        </div>
      );
  if (!session)
    return (
      <div className="login-layout">
        <aside className="login-intro">
          <strong className="brand-title">CommerceOps</strong>
          <h1>
            核对事实
            <br />
            跟进内部工作项
          </h1>
          <p>身份与范围由服务端当前授权决定。</p>
          <small>无真实采购或库存修改</small>
        </aside>
        <main className="login-main">
          <Card title="登录运营工作台">
            <Notice
              title={`真实服务端会话 · ${localHttp ? "local_http" : "https"}`}
            >
              业务来源为本阶段自有Mock数据；权限以真实会话为准，无身份选择器。
            </Notice>
            {checking ? (
              <p role="status">正在核实会话</p>
            ) : (
              <form onSubmit={(event) => void login(event)} autoComplete="off">
                <label htmlFor="live-login">账号</label>
                <input
                  id="live-login"
                  name="login"
                  autoComplete="username"
                  maxLength={100}
                  required
                  disabled={busy}
                />
                <label htmlFor="live-password">密码</label>
                <input
                  id="live-password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  disabled={busy}
                />
                <p role="alert" className="error-text">
                  {error}
                </p>
                <button className="primary" data-control="B11" disabled={busy}>
                  {busy ? "正在登录" : "登录"}
                </button>
              </form>
            )}
          </Card>
        </main>
      </div>
    );
  return (
    <div
      className="app-shell"
      data-source-mode={fixtureMode ? "b04-offline" : "live-session"}
    >
      <a className="skip-link" href="#main">
        跳到主要内容
      </a>
      <aside className="sidebar">
        <a className="brand" href={capabilities!.home_path}>
          <span className="logo">C</span>
          <span>
            <strong>CommerceOps</strong>
            <small>运营协作工作台</small>
          </span>
        </a>
        <p className="nav-caption">当前授权工作区</p>
        <nav aria-label="工作区导航">
          {capabilities!.can_read_tasks && (
            <a
              href="/tasks"
              data-control="B39"
              aria-current={path.startsWith("/tasks") ? "page" : undefined}
            >
              任务中心
            </a>
          )}
          {capabilities!.can_read_approvals && (
            <a
              href="/approvals"
              data-control="B40"
              aria-current={path.startsWith("/approvals") ? "page" : undefined}
            >
              审批
            </a>
          )}
          {capabilities!.can_read_tasks && (
            <a href="/replenishment-items" data-control="B41">
              内部补货
            </a>
          )}
          {capabilities!.can_read_operations && (
            <a href="/admin/operations" data-control="B30">
              运维说明
            </a>
          )}
        </nav>
        <p className="sidebar-note">仅内部工作项 · 无采购入库</p>
        <footer>
          <strong>{fixtureMode ? "注入会话示例" : "当前真实会话"}</strong>
          <p>自有Mock业务来源 · 内部协作</p>
        </footer>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>工作区 / {title}</span>
          <div className="account">
            <span className="environment">
              {session.config.transport_mode} · 业务Mock
            </span>
            <button data-control="B44" onClick={() => setPanel("account")}>
              <span className="avatar">
                {session.principal.display_name.charAt(0)}
              </span>
              <span>
                {session.principal.display_name}
                <small>
                  {fixtureMode
                    ? "离线合同 · 无真实身份"
                    : "服务端授权 · session"}
                </small>
              </span>
            </button>
          </div>
        </header>
        <main id="main">
          <div className="mock-banner">
            {fixtureMode
              ? "明确离线 Mock · 注入合同响应；没有登录会话、API连接或数据库写入，示例不是真实Gate。"
              : "当前会话已认证 · 本阶段业务来源为Mock · 创建、审批与内部跟进已接入。"}{" "}
            {writePending}
          </div>
          <div className="page-heading">
            <div>
              <h1>{title}</h1>
              <p>以当前服务端授权与冻结事实为准。</p>
            </div>
            <button data-control="B42" onClick={() => void refresh()}>
              刷新会话与当前页
            </button>
          </div>
          {error && <Notice title="读取未完成">{error}</Notice>}
          {path === "/access" ? (
            <Card title="无法访问此页面">
              <p>
                页面不可访问或当前身份没有权限。此提示不披露对象是否存在、编号、SKU或计数。
              </p>
              <a
                className="button"
                data-control="B31"
                href={capabilities!.home_path}
              >
                返回有权首页
              </a>
            </Card>
          ) : !page ? (
            <Card>
              <p role="status">正在读取当前授权记录</p>
            </Card>
          ) : (
            <>
              {page.kind === "tasks" && (
                <>
                  <div className="metrics">
                    <Card>
                      <p>当前筛选总数</p>
                      <strong className="metric">{page.read.total}</strong>
                    </Card>
                    <Card>
                      <p>当前筛选待审批</p>
                      <strong className="metric">
                        {page.read.counts.awaiting_approval}
                      </strong>
                    </Card>
                    <Card>
                      <p>读取时点</p>
                      <small>{localTime(page.read.as_of, zone)}</small>
                    </Card>
                  </div>
                  <Card title="任务列表">
                    <div className="toolbar">
                      <label>
                        状态
                        <select
                          value={state}
                          onChange={(event) => filter(event.target.value)}
                        >
                          <option value="">全部</option>
                          {[
                            "queued",
                            "analyzing",
                            "awaiting_approval",
                            "completed",
                            "failed",
                            "needs_attention",
                          ].map((x) => (
                            <option key={x} value={x}>
                              {label(x)}
                            </option>
                          ))}
                        </select>
                      </label>
                      {capabilities!.can_create_task && (
                        <button
                          data-control="B10"
                          onClick={() => setPanel("create")}
                        >
                          创建正式任务
                        </button>
                      )}
                    </div>
                    <div className="list-table">
                      {page.read.items.map((x) => (
                        <div className="list-row" key={x.task_id}>
                          <div>
                            <strong>
                              {x.kind === "inventory_analysis_only"
                                ? "库存分析（analysis_only）"
                                : "内部补货工作流"}
                            </strong>
                            <small>
                              {x.task_id} · 店铺 {x.shop_id}
                            </small>
                          </div>
                          <Status value={label(x.state)} />
                          <span>{localTime(x.updated_at, zone)}</span>
                          <span>同步：{label(x.sync.state)}</span>
                          <a
                            className="button"
                            data-control="B13"
                            href={`/tasks/${x.task_id}`}
                          >
                            查看任务
                          </a>
                        </div>
                      ))}
                    </div>
                    {!page.read.items.length && (
                      <p>当前授权与筛选下暂无任务。</p>
                    )}
                  </Card>
                </>
              )}
              {page.kind === "task" && (
                <>
                  <Card title="任务事实">
                    <p data-task-id={page.read.task.task_id}>
                      {page.read.task.task_id}
                    </p>
                    <Status value={label(page.read.task.state)} />
                    <p>
                      {page.read.task.kind} · {page.read.task.workflow_version}
                    </p>
                    <p>
                      outcome：
                      {page.read.task.outcome
                        ? label(page.read.task.outcome)
                        : "未知"}{" "}
                      · failure：{page.read.failure_code ?? "无"}
                    </p>
                    <p>更新：{localTime(page.read.task.updated_at, zone)}</p>
                    {page.read.source ? (
                      <Source source={page.read.source} />
                    ) : (
                      <p>尚无冻结来源，不能预生成报告。</p>
                    )}
                  </Card>
                  <Card title="来源与记录">
                    <div className="actions">
                      {page.read.source && (
                        <a
                          className="button"
                          data-control="B14"
                          href={`/tasks/${page.read.task.task_id}/report?report_id=${page.read.source.report_id}`}
                        >
                          读取冻结报告
                        </a>
                      )}
                      <a
                        className="button"
                        href={`/tasks/${page.read.task.task_id}/plans`}
                      >
                        冻结版本
                      </a>
                      <a
                        className="button"
                        data-control="B16"
                        href={`/tasks/${page.read.task.task_id}/events`}
                      >
                        执行轨迹
                      </a>
                      {page.read.approval_id && (
                        <a
                          className="button"
                          data-control="B15"
                          href={`/approvals/${page.read.approval_id}`}
                        >
                          读取审批
                        </a>
                      )}
                    </div>
                    <p>
                      任务状态、永久执行回执与各内部项跟进状态分别呈现；不推断采购或入库。
                    </p>
                    {page.read.actions.can_start_new_cycle && (
                      <button
                        data-control="B46"
                        onClick={() => setPanel("create")}
                      >
                        开启新周期
                      </button>
                    )}
                  </Card>
                  {page.execution && (
                    <ExecutionFacts
                      read={page.execution}
                      taskId={page.read.task.task_id}
                    />
                  )}
                  {!page.execution && (
                    <Notice title="尚无可见执行回执">
                      仅展示任务已报告事实，不推断内部项创建或执行成功。
                    </Notice>
                  )}
                  <Card title="协作同步">
                    <Sync sync={page.read.task.sync} />
                  </Card>
                </>
              )}
              {page.kind === "report" && (
                <>
                  <LiveReport
                    key={page.read.source.report_id}
                    read={page.read}
                    config={config}
                    client={client!}
                    cycle={{
                      ...newCycleEligibility(
                        page.task,
                        capabilities!.can_create_task,
                        session.principal.role_shop_grants
                          .filter((x) => x.role === "operator")
                          .map((x) => x.shop_id),
                      ),
                      openDraft: () => setPanel("create-new-cycle"),
                    }}
                  />
                  {capabilities!.can_create_task &&
                    page.read.source.source_complete &&
                    page.read.facts.complete && (
                      <button
                        data-control="B01"
                        onClick={() => setPanel("create-source")}
                      >
                        从此冻结报告创建正式补货任务
                      </button>
                    )}
                  <VersionList
                    list={page.versions}
                    taskId={page.read.task_id}
                  />
                </>
              )}
              {page.kind === "plans" && (
                <VersionList list={page.read} taskId={page.taskId} />
              )}
              {page.kind === "plan" && (
                <>
                  <PlanDetails plan={page.read.plan} historical />
                  <Card>
                    <p>
                      can_decide：{String(page.read.can_decide)} · disabled：
                      {page.read.disabled_reasons.join("、") ||
                        "无服务端禁用原因"}
                    </p>
                  </Card>
                </>
              )}
              {page.kind === "approvals" && (
                <Card title="审批列表">
                  <div className="toolbar">
                    <label>
                      视图
                      <select
                        value={approvalView}
                        onChange={(event) => {
                          setData(null);
                          setCursor(undefined);
                          setPrevious([]);
                          setApprovalView(
                            event.target.value as typeof approvalView,
                          );
                        }}
                      >
                        <option value="visible">当前可读</option>
                        <option value="mine">当前可决定</option>
                        <option value="history">历史</option>
                      </select>
                    </label>
                    <label>
                      状态
                      <select
                        value={state}
                        onChange={(event) => filter(event.target.value)}
                      >
                        <option value="">全部</option>
                        {[
                          "pending",
                          "approved",
                          "rejected",
                          "expired",
                          "superseded",
                        ].map((x) => (
                          <option key={x} value={x}>
                            {label(x)}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <p>
                    当前筛选总数 {page.read.total} · pending{" "}
                    {page.read.counts.pending} · as_of{" "}
                    {localTime(page.read.as_of, zone)}
                  </p>
                  {page.read.items.map((x) => (
                    <div className="list-row" key={x.approval_id}>
                      <div>
                        <strong>{x.approval_id}</strong>
                        <small>
                          task {x.task_id} · v{x.plan_version}
                        </small>
                      </div>
                      <Status value={label(x.status)} />
                      <span>
                        {x.item_count} 项 / {x.total_units} 件
                      </span>
                      <span>ready_at：{x.ready_at ?? "未就绪"}</span>
                      <a
                        className="button"
                        data-control="B15"
                        href={`/approvals/${x.approval_id}`}
                      >
                        读取完整计划
                      </a>
                    </div>
                  ))}
                  {!page.read.items.length && <p>当前授权与筛选下暂无审批。</p>}
                </Card>
              )}
              {page.kind === "approval" && (
                <>
                  <Card title="读取时审批事实">
                    <p>
                      {page.read.approval.approval_id} · v
                      {page.read.approval.plan_version}
                    </p>
                    <Status value={label(page.read.approval.status)} />
                    <p>
                      ready_at：{page.read.approval.ready_at ?? "未就绪"} ·
                      can_decide：{String(page.read.approval.can_decide)}
                    </p>
                    <p>
                      disabled：
                      {page.read.disabled_reasons.join("、") ||
                        "无服务端禁用原因"}
                    </p>
                    {page.read.decision ? (
                      <p>
                        原决定：{page.read.decision.action} ·{" "}
                        {page.read.decision.decided_at} ·{" "}
                        {page.read.decision.decided_by}
                      </p>
                    ) : (
                      <p>尚无决定记录；不推断批准或执行。</p>
                    )}
                  </Card>
                  <PlanDetails
                    plan={page.read.plan}
                    decisionSlot={
                      <DecisionActions
                        key={`${page.read.plan.plan_id}:${page.read.plan.plan_version}:${page.read.plan.plan_hash}`}
                        read={page.read}
                        client={client!}
                        refresh={() => void refresh()}
                        onHoldChange={holdWrite}
                      />
                    }
                  />
                  <a
                    className="button"
                    href={`/tasks/${page.read.plan.task_id}/plans/${page.read.plan.plan_version}`}
                  >
                    读取指定冻结版本
                  </a>
                </>
              )}
              {page.kind === "events" && (
                <>
                  <Card title="实际已发生轨迹">
                    <p>
                      as_of：{localTime(page.read.as_of, zone)} ·
                      无内部思维链或原始checkpoint。
                    </p>
                    <ol className="timeline">
                      {page.read.items.map((x) => (
                        <li key={x.event_id}>
                          <strong>{x.action}</strong>
                          <small>
                            {localTime(x.occurred_at, zone)} · step{" "}
                            {x.step ?? "未知"} · duration{" "}
                            {x.duration_ms ?? "未知"}ms
                          </small>
                          <p>{x.safe_summary}</p>
                          <p>result_ref：{x.result_ref ?? "无"}</p>
                          {x.recovery && (
                            <p>
                              恢复事实仅来自持久记录：
                              {x.recovery.code}
                            </p>
                          )}
                        </li>
                      ))}
                    </ol>
                    {!page.read.items.length && (
                      <p>暂无可读事件，不虚构恢复完成。</p>
                    )}
                    <Disabled control="B32" reason="无重启或手动重试端点。">
                      手动重试
                    </Disabled>
                  </Card>
                  {page.execution && (
                    <ExecutionFacts
                      read={page.execution}
                      taskId={page.taskId}
                    />
                  )}
                </>
              )}
              {page.kind === "receipt" && (
                <Card title="原请求持久回执">
                  <p>
                    key：{page.read.request_key} · 状态：{page.read.status} ·
                    operation：{page.read.receipt.operation}
                  </p>
                  <p>仅回读当前有权原回执，不自动换键、创建或执行。</p>
                  {page.read.receipt.operation === "resolve" && (
                    <>
                      <p>
                        item {page.read.receipt.result.item.item_id} ·{" "}
                        {page.read.receipt.result.item.state} · v
                        {page.read.receipt.result.item.version}
                      </p>
                      <p>
                        原动作 {page.read.receipt.result.resolution.action} ·
                        原因 {page.read.receipt.result.resolution.reason}
                      </p>
                      <p>
                        原处理人{" "}
                        {page.read.receipt.result.resolution.resolved_by} ·{" "}
                        {page.read.receipt.result.resolution.resolved_at}
                      </p>
                      <p>
                        原版本 v
                        {page.read.receipt.result.resolution.before_version} → v
                        {page.read.receipt.result.resolution.after_version} ·
                        hash{" "}
                        {
                          page.read.receipt.result.resolution
                            .resolution_payload_hash
                        }
                      </p>
                      <Sync sync={page.read.receipt.result.item.sync} />
                    </>
                  )}
                </Card>
              )}
              {page.kind === "operations" && (
                <Card title="脱敏运维摘要">
                  <p>
                    配置版本：{page.read.config_version} ·{" "}
                    {page.read.transport_mode}
                  </p>
                  <p>
                    Worker：{label(page.read.worker_state)}（unknown不猜测运行）
                    · 全局Graph并发：{page.read.graph_concurrency_limit}
                  </p>
                  <p>
                    sender：禁用 · recovery_scan：
                    {page.read.recovery_scan_seconds ?? "未知"}秒
                  </p>
                  <p>
                    审批TTL：{page.read.approval_ttl_seconds ?? "未知"}秒 ·
                    新鲜度：{page.read.revalidation_max_age_seconds ?? "未知"}秒
                  </p>
                  <p>服务端时间：{page.read.server_time}</p>
                  <Disabled
                    control="B34"
                    reason="配置为服务端事实，无修改端点。"
                  >
                    修改配置
                  </Disabled>
                </Card>
              )}
              {page.kind === "items" && (
                <ItemListFacts
                  read={page.read}
                  state={state || "all"}
                  onFilter={(value) => filter(value === "all" ? "" : value)}
                />
              )}
              {page.kind === "item" && (
                <ItemDetails
                  key={page.read.item.item_id}
                  read={page.read}
                  client={client!}
                  onHoldChange={holdWrite}
                />
              )}
              {(previous.length > 0 || nextCursor) && (
                <div className="actions">
                  {previous.length > 0 && (
                    <button
                      onClick={() => {
                        setData(null);
                        setCursor(previous[previous.length - 1]);
                        setPrevious((x) => x.slice(0, -1));
                      }}
                    >
                      上一页
                    </button>
                  )}
                  {nextCursor && (
                    <button onClick={() => next(nextCursor)}>下一页</button>
                  )}
                </div>
              )}
              {config && (
                <Card title="本次实际配置">
                  <p>
                    当前店铺：{config.shop_id} · {config.config.config_version}
                  </p>
                  <p>
                    审批TTL：{config.config.approval_ttl_seconds ?? "未知"}秒 ·
                    新鲜度上限：
                    {config.config.revalidation_max_age_seconds ?? "未知"}秒 ·
                    最大计划：{config.config.max_plan_items ?? "未知"}项
                  </p>
                  <p>
                    服务端时间：
                    {localTime(
                      config.server_time,
                      config.config.shop_timezone,
                    )}{" "}
                    · 读取时事实，不以浏览器时间裁定审批。
                  </p>
                </Card>
              )}
            </>
          )}
          {(panel === "create" ||
            panel === "create-source" ||
            panel === "create-new-cycle") &&
            capabilities!.can_create_task && (
              <CreateTaskDialog
                client={client!}
                shops={session.principal.role_shop_grants
                  .filter(
                    (x) =>
                      x.role === "operator" &&
                      (panel !== "create-new-cycle" ||
                        (page?.kind === "report" &&
                          x.shop_id === page.task.task.shop_id)),
                  )
                  .map((x) => x.shop_id)}
                source={
                  panel === "create-source" && page?.kind === "report"
                    ? page.read.source
                    : undefined
                }
                close={() => setPanel("")}
                onHoldChange={holdWrite}
              />
            )}
          {panel === "account" && (
            <Modal title="当前账号与授权范围" close={() => setPanel("")}>
              <p>
                {session.principal.display_name} ·{" "}
                {fixtureMode
                  ? "离线注入合同对象，无真实身份"
                  : "身份来自服务端session"}
              </p>
              <p>auth_version：{session.principal.auth_version}</p>
              {session.principal.role_shop_grants.map((x) => (
                <p key={`${x.role}:${x.shop_id}`}>
                  {x.role} → 店铺 {x.shop_id}
                </p>
              ))}
              <p>
                逐角色店铺范围分别绑定，不能把跨店operator与approver拼成决定权限。
              </p>
              <p>
                会话绝对期限：{session.absolute_expires_at} · 空闲期限：
                {session.idle_expires_at}
              </p>
              <p>
                实值：绝对 {session.config.session_absolute_seconds}秒 / 空闲{" "}
                {session.config.session_idle_seconds}秒
              </p>
              <button
                data-control="B12"
                disabled={busy}
                onClick={() => void logout()}
              >
                退出登录
              </button>
            </Modal>
          )}
          <p className="page-foot">
            内部协作 · 冻结M1样式 · Phase4飞书/生产未接入
          </p>
        </main>
      </div>
    </div>
  );
}
