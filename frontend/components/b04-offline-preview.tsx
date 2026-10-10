"use client";
import { useEffect, useRef, useState } from "react";
import { createOfflineItemClient, offlineId } from "../lib/b04-offline-source";
import type { OfflineScenario } from "../lib/b04-offline-source";
import type { DTO } from "../lib/p3-present";
import { P3Failure } from "../lib/p3-transport";
import { ItemDetails, ItemListFacts, ExecutionFacts } from "./item-views";
import { Notice } from "./ui";
export function B04OfflinePreview({
  path,
  scenario,
  role,
}: {
  path: string;
  scenario: OfflineScenario;
  role: string;
}) {
  const selected = Array.from(
    { length: 20 },
    (_, n) => `/replenishment-items/${offlineId(n + 1)}`,
  ).indexOf(path);
  const [item, setItem] = useState<DTO["ItemRead"] | null>(null),
    [list, setList] = useState<DTO["ItemList"] | null>(null),
    [execution, setExecution] = useState<DTO["ExecutionRead"] | null>(null),
    [failure, setFailure] = useState("");
  const active = useRef(true);
  const [client] = useState(() =>
    createOfflineItemClient(
      scenario,
      () => {
        if (!active.current) return;
        setItem(null);
        setList(null);
        setExecution(null);
        setFailure("离线401示例：身份、业务缓存与预备操作已清除。");
      },
      undefined,
      Math.max(1, selected + 1),
    ),
  );
  useEffect(() => {
    active.current = true;
    let alive = true;
    const load = async () => {
      await client.session();
      if (path === "/replenishment-items") {
        const value = await client.items();
        if (alive) setList(value);
      } else if (selected >= 0) {
        const value = await client.item(offlineId(selected + 1));
        if (alive)
          setItem(
            role === "operator"
              ? value
              : {
                  ...value,
                  can_resolve: false,
                  disabled_reasons: ["ACCESS_DENIED"],
                },
          );
      } else if (path === `/tasks/${offlineId(102)}/events`) {
        const value = await client.execution(offlineId(102));
        if (alive) setExecution(value);
      } else throw new P3Failure("RESOURCE_NOT_FOUND");
    };
    void load().catch(() => {
      if (alive) {
        setItem(null);
        setList(null);
        setExecution(null);
        setFailure("页面不可访问或暂时无法安全读取。离线示例不代表真实鉴权。");
      }
    });
    return () => {
      alive = false;
      active.current = false;
      client.clearSession();
    };
  }, [client, path, role, selected]);
  return (
    <div className="app-shell" data-source-mode="b04-offline">
      <a className="skip-link" href="#main">
        跳到主要内容
      </a>
      <aside className="sidebar">
        <a className="brand" href="/replenishment-items">
          <span className="brand-mark">C</span>
          <span>
            CommerceOps<small>运营协作工作台</small>
          </span>
        </a>
        <nav>
          <a href="/replenishment-items">内部补货</a>
          <a href={`/tasks/${offlineId(102)}/events`}>操作轨迹</a>
        </nav>
        <p className="sidebar-note">离线组件准备 · 无业务服务</p>
      </aside>
      <div className="workspace">
        <header className="topbar">冻结 M1 · B04 离线准备</header>
        <main id="main">
          <Notice title="明确离线 Mock · 注入合同响应">
            没有登录会话、API连接或数据库写入；示例结果不是真实业务Gate。只有内部工作项，非采购入库。
          </Notice>
          <h1>
            {execution
              ? "操作轨迹与执行事实"
              : item
                ? "内部工作项详情"
                : "内部工作项"}
          </h1>
          {failure ? (
            <Notice title="安全状态">{failure}</Notice>
          ) : item ? (
            <ItemDetails key={item.item.item_id} read={item} client={client} />
          ) : list ? (
            <ItemListFacts read={list} />
          ) : execution ? (
            <ExecutionFacts read={execution} taskId={offlineId(102)} />
          ) : (
            <p role="status">正在准备离线组件</p>
          )}
        </main>
      </div>
    </div>
  );
}
