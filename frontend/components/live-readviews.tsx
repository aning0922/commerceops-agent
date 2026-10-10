"use client";
import { useState } from "react";
import type { ReactNode } from "react";
import type { A01ReadClient } from "../lib/p3-live-client";
import type { DTO } from "../lib/p3-present";
import { label, localTime, planComplete } from "../lib/p3-present";
import { P3Failure } from "../lib/p3-transport";
import { Card, Disabled, Modal, Notice, Status } from "./ui";
export const writePending =
  "审批意见不代表执行成功；内部项跟进与同步分别记账，不表示采购入库。";
export function Sync({ sync }: { sync: DTO["SyncRead"] }) {
  return (
    <div>
      <strong>
        协作同步：{sync.state === "pending" ? "等待同步" : label(sync.state)}
      </strong>
      <p>
        sender：{sync.sender_enabled ? "启用" : "禁用"} ·
        业务状态与同步独立；待同步不表示已写外部平台。
      </p>
      {sync.projections.map((x) => (
        <p key={x.aggregate_id}>
          {x.outbox_status} · projection v{x.projection_version} ·{" "}
          {x.error_code ?? "无已知错误"} · {x.as_of ?? "时间未知"}
        </p>
      ))}
    </div>
  );
}
export function LiveFacts({
  facts,
  quantities,
}: {
  facts: readonly DTO["P2InventoryFact"][];
  quantities?: ReadonlyMap<string, number>;
}) {
  return (
    <div
      className="fact-list"
      role="table"
      aria-label={quantities ? "完整审批清单" : "SKU 分析"}
    >
      <div className="fact-head" role="row">
        {[
          "商品 / SKU",
          "风险",
          "日均需求（件）",
          "可用库存",
          "原始在途（件）",
          "建议（件）",
          "数据说明 / 执行资格",
        ].map((x) => (
          <span key={x} role="columnheader">
            {x}
          </span>
        ))}
      </div>
      {facts.map((x) => (
        <div
          className={`fact-row ${x.inbound_units === null ? "draft-row" : ""}`}
          role="row"
          key={x.sku_key}
        >
          <div className="sku" role="cell">
            <strong>{x.sku_label ?? "商品名称未知"}</strong>
            <small>{x.sku_key}</small>
          </div>
          <div role="cell">
            <span className="mobile-label">风险</span>
            <Status value={label(x.risk)} />
          </div>
          <div role="cell" className="number">
            <span className="mobile-label">日均需求</span>
            {x.display.D ?? "未知"}
            <small>
              {x.D
                ? `精确 ${x.D.numerator}/${x.D.denominator}`
                : "精确比值未知"}
            </small>
          </div>
          <div role="cell" className="number">
            <span className="mobile-label">库存</span>
            {x.A ?? "未知"}
          </div>
          <div role="cell" className="number">
            <span className="mobile-label">原始在途</span>
            {x.inbound_units ?? "null（未知）"}
            <small>估算有效值 {x.effective_inbound_units}</small>
          </div>
          <div role="cell" className="number">
            <span className="mobile-label">建议</span>
            {quantities?.get(x.sku_key) ?? x.suggested_units ?? "未知"}
            <small>{label(x.suggestion_mode)}</small>
          </div>
          <div role="cell">
            <details data-control="B43">
              <summary>
                {x.hard_blocks.length
                  ? "硬阻断 · 不可豁免"
                  : x.required_assumptions.length
                    ? "假设草案 · 需显式确认"
                    : "冻结事实说明"}
              </summary>
              <p>
                销量净件数 {x.net_units ?? "未知"}；库存观测{" "}
                {x.inventory_observed_at ?? "未知"}；source{" "}
                {x.source_version ?? "未知"}。
              </p>
              <p>
                硬阻断：{x.hard_blocks.join("、") || "无"}；质量：
                {x.quality_flags.join("、") || "无"}；假设：
                {x.required_assumptions.join("、") || "无"}。
              </p>
              <p>
                库存原因：{x.stock_reason ?? "无"}；在途原因：
                {x.inbound_reason ?? "无"}；完整销量：
                {x.demand_complete ? "是" : "否"}
                。报告为analysis_only，不授执行权。
              </p>
            </details>
          </div>
        </div>
      ))}
    </div>
  );
}
export function Source({ source }: { source: DTO["SourceBinding"] }) {
  return (
    <>
      <p>源 task：{source.source_task_id}</p>
      <p>
        报告：{source.report_id} · 快照：{source.snapshot_id}
      </p>
      <p>facts_hash：{source.facts_hash}</p>
      <p>
        采集开始：{source.collection_started_at}；观测完成：
        {source.collected_at}
      </p>
      <p>
        来源完整：{source.source_complete ? "是" : "否"} ·
        observational；未验证新鲜度不能默认为新鲜。
      </p>
    </>
  );
}
export function PlanDetails({
  plan,
  historical = false,
  decisionSlot,
}: {
  decisionSlot?: ReactNode;
  plan: DTO["Plan"];
  historical?: boolean;
}) {
  const complete = planComplete(plan);
  return (
    <>
      <Notice
        title={
          historical
            ? "指定冻结版本 · 只读"
            : decisionSlot
              ? "当前冻结计划"
              : "冻结计划 · 只读"
        }
      >
        v{plan.plan_version} · {label(plan.status)} · {writePending}{" "}
        旧批准与假设确认不能复用。
      </Notice>
      {!complete && (
        <Notice title="披露不完整 · 决定禁用">
          实际渲染数、完整标记或冻结数量不一致；不能把部分清单当完整计划。
        </Notice>
      )}
      <div className="metrics">
        <Card>
          <p>计划条目</p>
          <strong className="metric">{plan.item_count}</strong>
          <small>实际渲染 {plan.items.length} 项</small>
        </Card>
        <Card>
          <p>冻结建议</p>
          <strong className="metric">{plan.total_units} 件</strong>
        </Card>
        <Card>
          <p>本版本假设</p>
          <strong className="metric">{plan.required_assumptions.length}</strong>
          <small>未默认确认</small>
        </Card>
      </div>
      <Card title="完整计划清单">
        <LiveFacts
          facts={plan.items.map((x) => x.fact)}
          quantities={new Map(plan.items.map((x) => [x.sku_key, x.quantity]))}
        />
      </Card>
      <Card title="假设与硬阻断">
        <p>
          硬阻断：{plan.hard_blocks.join("、") || "无"}；质量：
          {plan.quality_flags.join("、") || "无"}。
        </p>
        {plan.required_assumptions.map((x) => (
          <p key={x.key}>
            {x.key} · {x.sku_key} · raw未知按{x.estimated_units}估算 ·{" "}
            {x.disclosure_version}
          </p>
        ))}
        <p>假设确认必须与本版本完整集合绑定；历史版本不提供决定入口。</p>
      </Card>
      <Card title="冻结来源与参数">
        <Source source={plan.source} />
        <p>
          plan：{plan.plan_id} · hash：{plan.plan_hash}
        </p>
        <p>
          规则：{plan.rule_version} · L/R/S：{plan.parameters.L}/
          {plan.parameters.R}/{plan.parameters.S} · 期限：{plan.expires_at} ·
          config：{plan.config_version}
        </p>
      </Card>
      {decisionSlot ?? (
        <div className="decision-actions">
          <Disabled control="B02" reason={writePending}>
            批准本版本
          </Disabled>
          <Disabled control="B03" reason={writePending}>
            拒绝本版本
          </Disabled>
          <Disabled control="B04" reason={writePending}>
            确认完整假设并批准
          </Disabled>
          <Disabled control="B05" reason={writePending}>
            拒绝假设
          </Disabled>
        </div>
      )}
    </>
  );
}
export function VersionList({
  list,
  taskId,
}: {
  list: DTO["PlanList"];
  taskId: string;
}) {
  return (
    <Card title="冻结版本">
      <p>
        共 {list.total} 个版本 · 当前v{list.current_plan_version ?? "未知"} ·
        as_of {list.as_of}
      </p>
      {list.items.map((x) => (
        <div className="list-row" key={x.plan_id}>
          <div>
            <strong>
              v{x.plan_version} · {label(x.status)}
            </strong>
            <small>{x.plan_id}</small>
          </div>
          <span>
            {x.item_count} 项 / {x.total_units} 件
          </span>
          <span>{x.expires_at}</span>
          <span>{x.plan_hash}</span>
          <a
            className="button"
            data-control="B33"
            href={`/tasks/${taskId}/plans/${x.plan_version}`}
          >
            读取此冻结版本
          </a>
        </div>
      ))}
      {!list.items.length && <p>暂无冻结计划。空列表不表示旧批准或完成。</p>}
    </Card>
  );
}
export function LiveReport({
  read,
  config,
  client,
}: {
  read: DTO["ReportRead"];
  config: DTO["ConfigRead"] | null;
  client: A01ReadClient;
}) {
  const [panel, setPanel] = useState("");
  const [explanation, setExplanation] = useState<DTO["ExplanationRead"] | null>(
    null,
  );
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const f = read.facts;
  const zone = config?.config.shop_timezone ?? null;
  async function explain() {
    setPanel("explanation");
    setLoading(true);
    setMessage("");
    setExplanation(null);
    try {
      const result = await client.explanation(
        read.task_id,
        read.source.report_id,
      );
      if (
        result.task_id !== read.task_id ||
        result.report_id !== read.source.report_id
      )
        throw new P3Failure("INVALID_RESPONSE");
      setExplanation(result);
    } catch (error) {
      setMessage(
        error instanceof P3Failure ? error.message : "暂时无法读取已有解释。",
      );
    } finally {
      setLoading(false);
    }
  }
  return (
    <>
      <Notice title="分析报告 · 冻结事实">
        完整：{f.complete ? "是" : "否"}；source_complete：
        {f.source_complete ? "是" : "否"}；候选 {f.candidate_count}
        ；scope_required：{f.scope_required ? "是" : "否"}。分析事实不授执行权。
      </Notice>
      <Card title="SKU 分析">
        <p>
          报告：{read.source.report_id} · 快照：{read.source.snapshot_id}
        </p>
        <p>全部 {f.items.length} 个 SKU · 确定性报告建议 · 未截断审批范围</p>
        <LiveFacts facts={f.items} />
      </Card>
      <Card>
        <p>
          销售窗口：{localTime(f.window.start, zone)} —{" "}
          {localTime(f.window.end, zone)}（不含结束）
        </p>
        <p>
          实际source timezone：{f.source.timezone} · L/R/S：{f.L}/{f.R}/{f.S}
        </p>
        <p>
          source_mode：{f.source.provenance.source_kind} · 风险：
          {f.warnings.join("、") || "无已知警告"}
        </p>
        <p>
          服务端时间：{localTime(read.server_time, zone)}；配置新鲜度上限：
          {config?.config.revalidation_max_age_seconds ?? "未知"}秒。
        </p>
        <button data-control="B18" onClick={() => setPanel("provenance")}>
          数据口径
        </button>
      </Card>
      <div className="actions">
        <button data-control="B19" onClick={() => void explain()}>
          读取本报告已有解释
        </button>
        <Disabled control="B36" reason="重算未授权，无对应接口。">
          重新分析
        </Disabled>
      </div>
      {panel === "provenance" && (
        <Modal title="数据口径" close={() => setPanel("")}>
          <Source source={read.source} />
          <p>公式、建议与精确比值来自冻结报告；UI不计算权威建议数量。</p>
          <p>
            报告事实 hash：{f.facts_hash}；输入 hash：{f.input_hash}
          </p>
        </Modal>
      )}
      {panel === "explanation" && (
        <Modal title="本报告已有解释" drawer close={() => setPanel("")}>
          <p>
            固定task/report：{read.task_id} / {read.source.report_id}
          </p>
          {loading ? (
            <p role="status">正在读取已有解释</p>
          ) : explanation ? (
            <>
              <Notice title="已有解释记录">
                仅引用此报告；不调用新的模型。
              </Notice>
              <p>{explanation.explanation.result.summary}</p>
            </>
          ) : (
            <Notice title="已有解释不可用或尚未就绪">
              {message} 未生成模板替代真实缓存，也未调用模型。
            </Notice>
          )}
        </Modal>
      )}
    </>
  );
}
