"use client";
import type { MockView, SkuFact } from "../lib/view-model";
import { Card, Notice, Status } from "./ui";
export function FactList({
  facts,
  approval = false,
}: {
  facts: SkuFact[];
  approval?: boolean;
}) {
  return (
    <div
      className="fact-list"
      role="table"
      aria-label={approval ? "完整审批清单" : "SKU 分析"}
    >
      <div className="fact-head" role="row">
        <span role="columnheader">商品 / SKU</span>
        <span role="columnheader">风险</span>
        <span role="columnheader">7 日需求（件）</span>
        <span role="columnheader">可用库存</span>
        <span role="columnheader">在途（件）</span>
        <span role="columnheader">建议（件）</span>
        <span role="columnheader">执行资格 / 数据说明</span>
      </div>
      {facts.map((x) => (
        <div
          className={`fact-row ${x.inbound === null ? "draft-row" : ""}`}
          role="row"
          key={x.key}
          id={x.key}
        >
          <div role="cell" className="sku">
            <strong>{x.name}</strong>
            <small>{x.key}</small>
          </div>
          <div role="cell">
            <span className="mobile-label">风险</span>
            <Status value={x.risk} />
          </div>
          <div role="cell" className="number">
            <span className="mobile-label">7 日需求</span>
            {x.demand}
          </div>
          <div role="cell" className="number">
            <span className="mobile-label">库存</span>
            {x.inventory ?? "未知"}
          </div>
          <div
            role="cell"
            className={`number ${x.inbound === null ? "amber-text" : ""}`}
          >
            <span className="mobile-label">在途</span>
            {x.inbound ?? "未知"}
          </div>
          <div role="cell" className="number">
            <span className="mobile-label">建议</span>
            {x.suggested ?? "—"}
          </div>
          <div role="cell">
            <details data-control="B43">
              <summary>{x.explanation}</summary>
              <p>
                冻结事实：{x.key}；库存 {x.inventory ?? "未知"}，原始在途{" "}
                {x.inbound ?? "null（未知）"}。
                {x.inbound === null
                  ? "按 0 估算仅为本版本草案，必须完整显式确认；硬质量错误不可豁免。"
                  : "仅以此指定快照为来源。"}
              </p>
            </details>
          </div>
        </div>
      ))}
    </div>
  );
}
export function FrozenReport({
  view,
  open,
}: {
  view: MockView;
  open: (panel: string) => void;
}) {
  const proposed = view.facts.filter((x) => view.planKeys.includes(x.key));
  return (
    <>
      {view.historical && (
        <Notice title="历史冻结版本 · 只读">
          旧批准与假设确认不可复用。当前展示 report v{view.version}
          ，切回当前版本不改变历史。
        </Notice>
      )}
      <div className="metrics">
        <Card>
          <p>需关注 SKU</p>
          <strong className="metric">
            {
              view.facts.filter(
                (x) => x.risk === "缺货" || x.risk === "补货风险",
              ).length
            }
          </strong>
          <small>来自冻结 Mock 报告</small>
        </Card>
        <Card>
          <p>建议内部工作项</p>
          <strong className="metric teal-text">{proposed.length} 项</strong>
          <small>含假设草案 · 全量披露</small>
        </Card>
        <Card>
          <p>需核对的数据</p>
          <strong className="metric amber-text">
            {
              view.facts.filter(
                (x) => x.inventory === null || x.inbound === null,
              ).length
            }{" "}
            项
          </strong>
          <small>未知与阻断独立显示</small>
        </Card>
      </div>
      <Notice title="在途未知不等于零">
        在途未知按 0
        估算仅为草案；可能重复补货，执行前必须由有权审批人显式确认本版本完整集合。
      </Notice>
      <Card title="SKU 分析">
        <p className="muted">
          全部 {view.facts.length} 个 SKU · 件数口径 · 筛选不会改变审批范围
        </p>
        <FactList facts={view.facts} />
      </Card>
      <Card>
        <div className="toolbar">
          <div>
            <strong>MockCommerce · 快照 {view.snapshotId} · rule v1</strong>
            <p>
              销量：10/02 00:00 – 10/09 00:00（不含）· Asia/Shanghai |
              库存观测：10/09 16:30（Mock）
            </p>
          </div>
          <button data-control="B18" onClick={() => open("provenance")}>
            数据口径
          </button>
        </div>
      </Card>
      <Notice title="智能分析摘要 · 模板样例" tone="info">
        解释只引用此 report v{view.version}{" "}
        的已有事实，数量由冻结报告给出。未调用付费模型。
      </Notice>
      <div className="actions">
        <button data-control="B19" onClick={() => open("explanation")}>
          解释本报告
        </button>
        <button data-control="B06" onClick={() => open("reanalysis")}>
          重新分析影响预览
        </button>
        {view.historyAvailable && (
          <a
            className="button"
            data-control="B33"
            href={`/tasks/${view.taskId}/report?version=${view.historical ? "2" : "1"}`}
          >
            {view.historical ? "返回当前版本" : "查看历史版本 v1"}
          </a>
        )}
      </div>
    </>
  );
}
