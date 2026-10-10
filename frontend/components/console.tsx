"use client";
import { useState } from "react";
import type { MockView } from "../lib/view-model";
import { Card, Disabled, Notice, ReadState, Status, labels } from "./ui";
import { FrozenReport, FactList } from "./report";
import { Panels } from "./panels";
export function Console({ path, view }: { path: string; view: MockView }) {
  const [panel, setPanel] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [announcement, announce] = useState("");
  const taskUrl = `/tasks/${view.taskId}`;
  const reportUrl = `${taskUrl}/report?version=${view.version}`;
  const approvalUrl = `/approvals/${view.approvalId}`;
  const item = view.items.find((x) => path === `/replenishment-items/${x.id}`);
  const reportReady = ["awaiting_approval", "completed"].includes(
    view.taskStatus,
  );
  const report = path.endsWith("/report");
  const events = path.endsWith("/events");
  const approval = path === approvalUrl;
  const task = path === taskUrl;
  const login = path === "/login";
  const access = path === "/access";
  const admin = path === "/admin/operations";
  const titles: Record<string, string> = {
    "/tasks": "任务中心",
    "/approvals": "审批",
    "/replenishment-items": "内部补货",
    "/access": "访问限制与会话过期",
    "/admin/operations": "管理配置与异常说明",
  };
  const title = report
    ? "库存分析报告"
    : events
      ? "Agent 执行轨迹"
      : approval
        ? "审批详情"
        : task
          ? "任务概览与结果"
          : (item?.name ?? titles[path] ?? "任务中心");
  const readFailed =
    ["loading", "empty", "error"].includes(view.state) && !access && !login;
  const selected = admin
    ? "/admin/operations"
    : path.startsWith("/approvals")
      ? "/approvals"
      : path.startsWith("/replenishment-items")
        ? "/replenishment-items"
        : "/tasks";
  const link = (href: string, text: string, control: string) => (
    <a className="button" data-control={control} href={href}>
      {text}
    </a>
  );
  if (login)
    return (
      <div className="login-layout">
        <aside className="login-intro">
          <strong className="brand-title">CommerceOps</strong>
          <h1>
            把运营判断
            <br />
            推进到可追溯的内部工作项
          </h1>
          <p>
            先核对事实，再记录审批。
            <br />
            业务结果、审批意见、协作同步分别呈现。
          </p>
          <small>仅内部工作项 · 无真实采购或库存变更</small>
        </aside>
        <main className="login-main">
          <Card title="登录运营工作台">
            <p>使用预置账号，角色与可见范围由当前授权决定。</p>
            <Notice
              title={
                view.mode === "mock"
                  ? "离线 Mock · 会话尚未接入"
                  : "服务端会话尚未接入"
              }
            >
              此登录壳不建立会话、不接收密码，也不授予业务权限。
            </Notice>
            <label htmlFor="account">账号</label>
            <input
              id="account"
              disabled
              autoComplete="username"
              placeholder="预置账号（待接入）"
            />
            <label htmlFor="password">密码</label>
            <input
              id="password"
              type="password"
              disabled
              autoComplete="current-password"
              placeholder="服务端会话合同待独审"
            />
            <Disabled
              control="B11"
              reason="BC01/05 会话/API 待独审；无身份替身。"
            >
              登录
            </Disabled>
            {view.mode === "mock" &&
              link(view.home, "查看固定离线 Mock 样例", "B31")}
          </Card>
        </main>
      </div>
    );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        跳到主要内容
      </a>
      <aside className="sidebar">
        <a href={view.home} className="brand">
          <span className="logo">C</span>
          <span>
            <strong>CommerceOps</strong>
            <small>运营协作工作台</small>
          </span>
        </a>
        <p className="nav-caption">{view.adminRead ? "授权运维" : "工作区"}</p>
        <nav aria-label="工作区导航">
          {view.businessRead && (
            <>
              {[
                ["/tasks", "任务中心", "B39"],
                ["/approvals", "审批", "B40"],
                ["/replenishment-items", "内部补货", "B41"],
              ].map(([href, text, control]) => (
                <a
                  key={href}
                  href={href}
                  data-control={control}
                  aria-current={selected === href ? "page" : undefined}
                >
                  {text}
                </a>
              ))}
            </>
          )}
          {view.adminRead && (
            <a
              data-control="B30"
              href="/admin/operations"
              aria-current={
                selected === "/admin/operations" ? "page" : undefined
              }
            >
              运维说明
            </a>
          )}
        </nav>
        <p className="sidebar-note">
          {view.adminRead
            ? "仅授权运维信息；业务内容须另行授权。"
            : "仅内部工作项 · 无采购入库"}
        </p>
        <footer>
          <strong>MockCommerce</strong>
          <p>
            {view.mode === "mock"
              ? "离线模拟数据 · 未连接业务服务"
              : "业务服务未接入"}
          </p>
        </footer>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>工作区 / {title}</span>
          <div className="account">
            <span className="environment">
              {view.mode === "mock" ? "演示店铺 · Mock" : "未接入"}
            </span>
            <button data-control="B44" onClick={() => setPanel("account")}>
              <span className="avatar">{view.name.charAt(0)}</span>
              <span>
                {view.name}
                <small>{view.role} · Mock</small>
              </span>
            </button>
          </div>
        </header>
        <main id="main">
          <div className="mock-banner">
            {view.mode === "mock"
              ? "离线 Mock 样例 · 不发送任何真实业务请求 · 未完成业务集成"
              : "业务与会话尚未接入 · 安全壳"}
          </div>
          <div className="page-heading">
            <div>
              <h1>{title}</h1>
              <p>
                {admin
                  ? "admin · 脱敏运维元信息 · BC01 / BC04 / BC05 / BC07 待接入"
                  : access
                    ? "请确认当前会话与授权范围。"
                    : path === "/tasks"
                      ? "用自然语言向 Agent 提问，分析库存风险并跟踪审批与内部跟进。"
                      : item
                        ? `${item.id} · ${item.sku} · 当前版本 v${item.version}`
                        : path === "/approvals"
                          ? "完整冻结计划 · 只展示固定 Mock 范围"
                          : path === "/replenishment-items"
                            ? "由批准计划创建的内部跟进项。完成或关闭不表示采购或入库。"
                            : `${view.taskId} · report v${view.version} · 预生成 Mock 示例`}
              </p>
            </div>
            {path === "/tasks" && view.canDraft && (
              <button
                className="primary"
                data-control="B10"
                onClick={() => setPanel("draft")}
              >
                向 Agent 提问
              </button>
            )}
            {item && <Status value={item.status} />}
          </div>
          <div aria-live="polite" className="announcement">
            {announcement}
          </div>
          {access ? (
            <Card
              title={
                view.state === "expired"
                  ? "会话已过期"
                  : view.state === "revoked"
                    ? "当前授权已撤销"
                    : "无法访问此页面"
              }
            >
              <p>
                页面不可访问或当前身份没有权限。此提示不披露对象是否存在、编号、SKU
                或计数。
              </p>
              <div className="actions">
                {link(
                  view.home === "/access" ? "/login" : view.home,
                  "返回有权首页",
                  "B31",
                )}
                {link("/login", "返回登录", "B11")}
              </div>
            </Card>
          ) : admin ? (
            <>
              {readFailed ? (
                <ReadState
                  state={view.state}
                  reload={() =>
                    announce("已重新展示固定 Mock 读取状态，未请求业务服务。")
                  }
                />
              ) : (
                <>
                  <Card title="运行约束">
                    <p>
                      单 Worker / 全局单
                      Graph（设计约束），运行健康状态尚未接入。
                    </p>
                    <p>
                      PostgreSQL 是业务权威；Checkpoint 不能替代副作用事务。
                    </p>
                  </Card>
                  <Card title="配置摘要 · 脱敏只读">
                    <p>
                      provider / model / rule
                      revision：未知。尚未读取实际部署配置。
                    </p>
                    <p>期限与新鲜度：未知；不硬编码产品承诺。</p>
                    <p>不显示密钥、原始回调、个人数据或业务计数。</p>
                  </Card>
                  <Card title="异常说明与既有恢复">
                    <details data-control="B43">
                      <summary>failed 与 unknown 的恢复边界</summary>
                      <p>
                        未知写入先核实原请求结果。内部项已创建时同步异常单独展示。仅展示已有恢复事实，无重试或重启操作。
                      </p>
                    </details>
                  </Card>
                  <Card title="权限边界">
                    <p>
                      admin 单角色不自动获得业务报告或审批权。兼任须逐角色在自身
                      scope 内授权，不能拼接动作权与对象范围。
                    </p>
                  </Card>
                  <button
                    data-control="B42"
                    onClick={() =>
                      announce("运维摘要尚未接入；未请求真实配置。")
                    }
                  >
                    重读当前区域（Mock）
                  </button>
                </>
              )}
            </>
          ) : readFailed ? (
            <ReadState
              state={view.state}
              reload={() =>
                announce("已重新展示固定 Mock 读取状态，未请求业务服务。")
              }
            />
          ) : (
            <>
              {path === "/tasks" && (
                <>
                  <div className="metrics four">
                    {[
                      ["全部任务", view.tasks.length],
                      [
                        "处理中",
                        view.tasks.filter((x) =>
                          ["queued", "analyzing"].includes(x.status),
                        ).length,
                      ],
                      [
                        "待审批",
                        view.tasks.filter(
                          (x) => x.status === "awaiting_approval",
                        ).length,
                      ],
                      [
                        "已完成",
                        view.tasks.filter((x) => x.status === "completed")
                          .length,
                      ],
                    ].map(([text, count]) => (
                      <Card key={text}>
                        <p>{text}</p>
                        <strong className="metric">{count}</strong>
                        <small>仅固定 Mock 范围</small>
                      </Card>
                    ))}
                  </div>
                  <Card>
                    <div className="toolbar">
                      <label className="search">
                        搜索任务
                        <input
                          data-control="B13"
                          type="search"
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                          placeholder="任务编号或请求关键词"
                        />
                      </label>
                      <label>
                        任务状态
                        <select
                          data-control="B13"
                          value={filter}
                          onChange={(e) => setFilter(e.target.value)}
                        >
                          <option value="all">全部状态</option>
                          {[
                            "queued",
                            "analyzing",
                            "awaiting_approval",
                            "completed",
                          ].map((x) => (
                            <option key={x} value={x}>
                              {labels[x]}
                            </option>
                          ))}
                        </select>
                      </label>
                      <span className="muted">固定离线样例 · 无后台查询</span>
                    </div>
                    <div className="list-table">
                      {view.tasks
                        .filter(
                          (x) =>
                            (filter === "all" || x.status === filter) &&
                            `${x.title} ${x.id}`.includes(search),
                        )
                        .map((x) => (
                          <article className="list-row" key={x.id}>
                            <div>
                              <strong>{x.title}</strong>
                              <small>
                                {x.id} · 10/02 – 10/08 · {x.scope}
                              </small>
                            </div>
                            <Status value={x.status} />
                            <span>MockCommerce</span>
                            <span>{x.updated}</span>
                            {link(`/tasks/${x.id}`, "查看任务 →", "B14")}
                          </article>
                        ))}
                      {!view.tasks.some(
                        (x) =>
                          (filter === "all" || x.status === filter) &&
                          `${x.title} ${x.id}`.includes(search),
                      ) && <p>没有符合当前筛选的 Mock 任务。</p>}
                    </div>
                    <p className="muted">
                      展示 {view.tasks.length} 条固定样例 · 无分页请求
                    </p>
                  </Card>
                  <Notice title="Agent 库存助手" tone="success">
                    例如：“检查最近七天销量与库存，找出缺货风险。”
                    {view.canDraft && (
                      <button
                        data-control="B10"
                        onClick={() => setPanel("draft")}
                      >
                        开始提问 →
                      </button>
                    )}
                  </Notice>
                </>
              )}
              {(task || report || events) && (
                <div className="tabs" aria-label="任务页面">
                  {link(taskUrl, "任务概览", "B29")}
                  {reportReady ? (
                    link(reportUrl, "分析报告", "B15")
                  ) : (
                    <Disabled
                      control="B15"
                      reason="报告尚未生成，固定 Mock 当前只有处理事实。"
                    >
                      分析报告
                    </Disabled>
                  )}
                  {link(`${taskUrl}/events`, "执行轨迹", "B16")}
                  {reportReady && view.approvalId ? (
                    link(approvalUrl, "查看审批", "B17")
                  ) : (
                    <Disabled control="B17" reason="当前任务尚无审批计划。">
                      查看审批
                    </Disabled>
                  )}
                </div>
              )}
              {report &&
                (reportReady ? (
                  <FrozenReport view={view} open={setPanel} />
                ) : (
                  <Card title="报告尚未生成">
                    <p>当前任务仍在处理，未提供冻结报告或审批范围。</p>
                  </Card>
                ))}
              {task && (
                <>
                  <Card title="业务状态">
                    <Status value={view.taskStatus} />
                    <p>
                      {view.taskStatus === "completed"
                        ? "源业务任务已完成（固定 Mock）。下一周期必须重新分析和审批。"
                        : view.taskStatus === "awaiting_approval"
                          ? "报告已生成，等待有权审批人对完整计划决定。"
                          : "当前任务尚在处理，未产生新的批准事实。"}
                    </p>
                  </Card>
                  <div className="metrics">
                    <Card title="报告">
                      <p>
                        {reportReady
                          ? `指定冻结版本 v${view.version} · Mock`
                          : "报告尚未生成"}
                      </p>
                      {reportReady ? (
                        link(reportUrl, "查看报告", "B15")
                      ) : (
                        <Disabled control="B15" reason="报告尚未生成。">
                          查看报告
                        </Disabled>
                      )}
                    </Card>
                    <Card title="审批与执行">
                      <p>
                        批准回执与内部项创建分别记录，不因批准自动宣称执行成功。
                      </p>
                      {reportReady && view.approvalId ? (
                        link(approvalUrl, "查看审批", "B17")
                      ) : (
                        <Disabled control="B17" reason="当前任务尚无审批计划。">
                          查看审批
                        </Disabled>
                      )}
                    </Card>
                    <Card title="协作同步">
                      <Status value="sync_failed" />
                      <p>同步异常不回滚已创建的内部项。</p>
                      {link(`${taskUrl}/events#sync`, "查看同步详情", "B38")}
                    </Card>
                  </div>
                  {reportReady && (
                    <Card title="关联内部项">
                      {view.items
                        .filter((x) => x.sourceTaskId === view.taskId)
                        .map((x) => (
                          <p key={x.id}>
                            {link(
                              `/replenishment-items/${x.id}`,
                              `${x.name} · ${labels[x.status]}`,
                              "B25",
                            )}
                          </p>
                        ))}
                    </Card>
                  )}
                  {view.canDraft && view.taskStatus === "completed" && (
                    <button
                      data-control="B46"
                      onClick={() => setPanel("draft")}
                    >
                      开始下一周期分析
                    </button>
                  )}
                  <Card title="飞书协作边界">
                    <p>
                      F01 真实卡片容量、身份与同版本完整披露留
                      Phase4；目前仅引导完整 Web 详情。
                    </p>
                    <Disabled
                      control="B47"
                      reason="F02 / BC02 任务关联、轮次、去重与续答未确认。"
                    >
                      回复指定任务澄清
                    </Disabled>
                  </Card>
                </>
              )}
              {path === "/approvals" && (
                <>
                  <Card>
                    <label>
                      审批状态
                      <select
                        data-control="B20"
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                      >
                        <option value="all">全部</option>
                        <option value="pending">待处理</option>
                        <option value="history">历史</option>
                      </select>
                    </label>
                    {filter !== "history" ? (
                      <article className="list-row">
                        <div>
                          <strong>近 7 天销量与库存分析</strong>
                          <small>{view.approvalId} · plan v2 · 固定 Mock</small>
                        </div>
                        <Status value="awaiting_approval" />
                        {link(approvalUrl, "查看完整计划", "B21")}
                      </article>
                    ) : (
                      <p>暂无历史审批样例。</p>
                    )}
                  </Card>
                  <p className="muted">
                    无列表一键批准、批量决定或预勾选；operator 只读。
                  </p>
                </>
              )}
              {approval && (
                <>
                  <div className="actions">
                    {link(taskUrl, "返回任务概览", "B29")}
                    {link(reportUrl, "查看来源报告", "B15")}
                  </div>
                  <p className="muted">
                    Mock 计划 v{view.version} · hash/nonce：未连接 ·
                    expires_at：未知
                  </p>
                  <Notice
                    title={`批准范围：${view.planKeys.length} 个 SKU · 全部冻结清单`}
                  >
                    仅创建内部补货工作项；不下单、不支付、不修改库存。
                    <p>
                      本版本未知在途完整集合：
                      {view.facts
                        .filter(
                          (x) =>
                            view.planKeys.includes(x.key) && x.inbound === null,
                        )
                        .map((x) => x.key)
                        .join("、") || "无"}
                      。按 0 估算可能重复补货。
                    </p>
                  </Notice>
                  <h2>
                    完整清单 · {view.planKeys.length} / {view.planKeys.length}{" "}
                    项
                  </h2>
                  <Card>
                    <FactList
                      approval
                      facts={view.facts.filter((x) =>
                        view.planKeys.includes(x.key),
                      )}
                    />
                  </Card>
                  {view.historical && (
                    <Notice title="历史版本只读">
                      不复用旧批准或假设确认。
                    </Notice>
                  )}
                  {["unknown", "conflict", "duplicate"].includes(
                    view.state,
                  ) && (
                    <Notice
                      title={
                        view.state === "unknown"
                          ? "审批结果未知"
                          : view.state === "conflict"
                            ? "决定冲突"
                            : "重复请求 · 既有决定"
                      }
                    >
                      先核实原请求/回执。不能更换请求键或修改 payload
                      重新发送；不猜测执行结果。
                    </Notice>
                  )}
                  <div className="decision-actions">
                    {view.canDecide ? (
                      <>
                        {view.facts.some(
                          (x) =>
                            view.planKeys.includes(x.key) && x.inbound === null,
                        ) ? (
                          <>
                            <Disabled
                              control="B03"
                              reason="明确 Mock；decision 合同/API 待独审，无真实审批。"
                            >
                              确认在途未知按 0 估算并批准本版本
                            </Disabled>
                            <Disabled
                              control="B04"
                              reason="明确 Mock；不会写审批决定。"
                            >
                              拒绝此假设并拒绝计划
                            </Disabled>
                          </>
                        ) : (
                          <>
                            <Disabled
                              control="B02"
                              reason="明确 Mock；decision 合同/API 待独审。"
                            >
                              批准创建内部补货任务
                            </Disabled>
                            <Disabled
                              control="B05"
                              reason="明确 Mock；不会写审批决定。"
                            >
                              拒绝计划
                            </Disabled>
                          </>
                        )}
                      </>
                    ) : (
                      <Notice title="当前固定 Mock 身份仅只读">
                        有权审批人由正式服务端逐次判定。
                      </Notice>
                    )}
                    <button
                      data-control="B23"
                      onClick={() => setPanel("receipt")}
                    >
                      核实审批结果（Mock）
                    </button>
                  </div>
                  <p className="muted">
                    未完整披露、历史、过期、撤权或质量阻断时无可执行批准；服务端身份/范围/版本/hash/nonce/完整集合待接入。
                  </p>
                </>
              )}
              {path === "/replenishment-items" && (
                <>
                  <div className="metrics">
                    {["open", "completed", "closed"].map((s) => (
                      <Card key={s}>
                        <p>{labels[s]}</p>
                        <strong className="metric">
                          {view.items.filter((x) => x.status === s).length}
                        </strong>
                      </Card>
                    ))}
                  </div>
                  <Card>
                    <label>
                      内部项状态
                      <select
                        data-control="B24"
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                      >
                        <option value="all">全部</option>
                        {["open", "completed", "closed"].map((s) => (
                          <option key={s} value={s}>
                            {labels[s]}
                          </option>
                        ))}
                      </select>
                    </label>
                    {view.items
                      .filter((x) => filter === "all" || x.status === filter)
                      .map((x) => (
                        <article className="list-row" key={x.id}>
                          <div>
                            <strong>{x.name}</strong>
                            <small>
                              {x.id} · {x.sku} · v{x.version}
                            </small>
                          </div>
                          <strong className="teal-text">{x.quantity} 件</strong>
                          <Status value={x.status} />
                          <Status value={x.sync} />
                          {link(
                            `/replenishment-items/${x.id}`,
                            "查看工作项",
                            "B25",
                          )}
                        </article>
                      ))}
                  </Card>
                  <p className="muted">
                    内部项与同步状态分别呈现；飞书失败不撤销内部项。
                  </p>
                </>
              )}
              {item && (
                <>
                  <div className="actions">
                    {link("/replenishment-items", "返回内部补货", "B41")}
                    {link(
                      `/tasks/${item.sourceTaskId}/report?version=${item.sourceReportVersion}`,
                      "查看来源报告",
                      "B37",
                    )}
                  </div>
                  <Card>
                    <div className="toolbar">
                      <div>
                        <p>内部跟进数量（件）</p>
                        <strong className="metric teal-text">
                          {item.quantity}
                        </strong>
                      </div>
                      <div>
                        <p>
                          来源计划 DEMO-PLAN-008 / v{item.sourceReportVersion} ·
                          预生成 Mock
                        </p>
                        <p>
                          审批记录、执行回执与内部项是独立事实，不表示采购或入库。
                        </p>
                      </div>
                    </div>
                  </Card>
                  <Notice title="飞书同步 · 独立投影事实" tone="info">
                    <Status value={item.sync} />
                    <p>
                      此项已创建（固定
                      Mock）；同步异常不回滚内部项，无外部重发动作。
                    </p>
                    {link(`${taskUrl}/events#sync`, "查看同步详情", "B38")}
                  </Notice>
                  <Card title="跟进记录">
                    <p>
                      {item.reason ??
                        "尚无完成或关闭原因；终态提交后记录身份、时间与原因。"}
                    </p>
                    <p>当前版本 v{item.version}；终态不重开。</p>
                  </Card>
                  {view.canResolve && item.status === "open" && (
                    <div className="actions">
                      <button
                        className="primary"
                        data-control="B26"
                        onClick={() => setPanel("complete")}
                      >
                        记录内部跟进完成
                      </button>
                      <button
                        data-control="B27"
                        onClick={() => setPanel("close")}
                      >
                        关闭内部工作项
                      </button>
                    </div>
                  )}
                  {item.status !== "open" && (
                    <Notice title="终态只读">
                      不能重新打开或重新生成内部项。
                    </Notice>
                  )}
                  <Disabled
                    control="B34"
                    reason="B34 复制交接仍未确认，沿用冻结禁用边界。"
                  >
                    复制安全编号
                  </Disabled>
                </>
              )}
              {events && (
                <>
                  <Card title="业务步骤">
                    <ol className="timeline">
                      <li>
                        <strong>已接收分析请求</strong>
                        <p>固定 Mock 请求 · 无真实队列或 Worker 执行。</p>
                      </li>
                      <li>
                        <strong>生成冻结报告与计划</strong>
                        <p>
                          report v{view.version} / {view.snapshotId} ·
                          在途未知仍保留 null。
                        </p>
                      </li>
                      <li>
                        <strong>等待完整披露与审批</strong>
                        <p>审批回执、执行回执与同步投影分别记录。</p>
                      </li>
                    </ol>
                  </Card>
                  <Card title="技术详情 · 脱敏事实">
                    <details data-control="B43">
                      <summary>节点 / Tool / 时间与 Token</summary>
                      <p>
                        Mock 样例；Token、费用、Checkpoint
                        及实际恢复时间均未知，不填 0，不展示模型思维链。
                      </p>
                    </details>
                    <details data-control="B43">
                      <summary>恢复与原执行回执</summary>
                      <p>
                        unknown 先核实原请求。业务提交与 checkpoint
                        不假定同一事务；没有通用恢复、重试或 Worker 重启按钮。
                      </p>
                    </details>
                    <Disabled
                      control="B34"
                      reason="安全技术编号复制合同尚未接入；无原始回调/SQL/秘密。"
                    >
                      复制安全技术编号
                    </Disabled>
                  </Card>
                  <section id="sync">
                    <Card title="协作同步">
                      <Status value="sync_failed" />
                      <p>
                        仅展示本地 Mock
                        失败状态；内部项事实不回滚，无飞书业务写入。
                      </p>
                    </Card>
                  </section>
                </>
              )}
            </>
          )}
          <p className="page-foot">
            {view.mode === "mock"
              ? "Mock 数据 · 当前固定样例身份 " +
                view.role +
                " · 未连接业务服务"
              : "会话与业务服务尚未接入"}
          </p>
        </main>
      </div>
      {panel && (
        <Panels
          key={`${panel}:${view.reportId}:${view.version}`}
          panel={panel}
          close={() => setPanel("")}
          view={view}
          item={item}
          open={setPanel}
        />
      )}
    </div>
  );
}
