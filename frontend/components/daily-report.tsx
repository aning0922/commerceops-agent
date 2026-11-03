"use client";
import { useState } from "react";
import type { DailyRead, MetricDisplay } from "../lib/m3-types.generated";
import { Card, Modal, Notice } from "./ui";

const metricNames: Record<MetricDisplay["metric_key"], string> = {
  created_order_count: "新建订单数", paid_order_count: "付款订单数",
  paid_product_net: "付款商品净额", paid_product_tax: "付款商品税额",
  paid_shipping_net: "付款运费净额", paid_shipping_tax: "付款运费税额",
  paid_fee_net: "付款费用净额", paid_fee_tax: "付款费用税额",
  paid_order_total: "付款订单总额", refund_count: "退款笔数",
  refunded_order_count: "发生退款的订单数", refund_amount: "退款金额",
  average_paid_order_value: "平均付款订单金额",
  orders_without_payment_timestamp: "缺少付款时间的订单数",
};
const money = new Set<MetricDisplay["metric_key"]>([
  "paid_product_net", "paid_product_tax", "paid_shipping_net", "paid_shipping_tax",
  "paid_fee_net", "paid_fee_tax", "paid_order_total", "refund_amount", "average_paid_order_value",
]);
const findingNames: Record<string, string> = {
  SOURCE_INCOMPLETE: "来源数据不完整", ORDER_AMOUNT_MISMATCH: "订单金额不一致",
  AGGREGATE_OUT_OF_RANGE: "汇总值超出范围", PAYMENT_TIMESTAMP_MISSING: "付款时间缺失",
  NO_RECORDED_PAYMENTS: "没有已记录的付款", LOW_PAID_TOTAL: "付款总额低于规则值",
  HIGH_REFUND_AMOUNT: "退款金额高于规则值", RULE_NOT_CONFIGURED: "规则未配置",
};
const severityNames: Record<string, string> = { info: "提示", warning: "警告", blocking: "阻断" };
const failureNames: Record<string, string> = {
  DAILY_SOURCE_INCOMPLETE: "来源数据不完整", DAILY_SOURCE_UNAVAILABLE: "来源暂不可用",
  DAILY_PERMISSION_INVALID: "当前权限不满足读取要求", DAILY_SOURCE_BINDING_CHANGED: "来源绑定已变化",
  DAILY_STORAGE_FAILURE: "报告保存未完成", DAILY_WORKFLOW_UNSAFE: "运行条件不满足",
};
const local = (time: string, zone: string) =>
  new Intl.DateTimeFormat("zh-CN", { timeZone: zone, dateStyle: "medium", timeStyle: "short" }).format(new Date(time));
const rawValue = (value: string | number | { numerator: string; denominator: string } | null) =>
  value === null ? "无（分母为零）" : typeof value === "object" ? `${value.numerator} / ${value.denominator}` : String(value);

export function DailyReport({ read }: { read: DailyRead }) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const daily = read.daily;
  const report = daily.report;
  const zone = report?.source.timezone;
  const source = report?.source.source_kind === "mock" ? "受控 Mock 数据" : "WooCommerce 测试店";
  return (
    <>
      <Notice title="日报生成状态">
        {daily.state === "completed" ? "日报已生成。" :
         daily.state === "needs_attention" ? "日报需要关注，部分事实可能不可用。" :
         daily.state === "failed" ? "日报生成失败。" :
         daily.state === "queued" ? "日报等待生成。" : "日报正在生成。"}
        {daily.failure_code && <> 原因：{failureNames[daily.failure_code]}。</>}
        推送记录尚不可读取；生成状态不代表已投递。
      </Notice>
      {!report ? (
        <Card title="日报事实"><p>当前没有可展示的封存日报。刷新只读取已有状态。</p></Card>
      ) : (
        <>
          <Card title={`${report.business_day} 日报`}>
            <p>{report.complete ? "数据完整" : "数据不完整"} · {source} · {report.source.currency}</p>
            <p>统计窗口：{local(report.window.start, zone!)} 至 {local(report.window.end, zone!)}（结束不含） · {zone}</p>
            <p>观测截至：{local(report.collected_at, zone!)}；服务端读取：{local(read.server_time, zone!)}</p>
            <p>来源范围：受控测试数据集。质量标记：{report.quality_flags.length ? report.quality_flags.join("、") : "无"}。</p>
          </Card>
          <Card title="指标与口径">
            {report.complete ? (
              <dl className="daily-metrics">
                {report.display.map((item) => (
                  <div key={item.metric_key}>
                    <dt>{metricNames[item.metric_key]}</dt>
                    <dd>{item.value === null ? "不可计算（付款订单数为零）" :
                      `${item.value}${money.has(item.metric_key) ? ` ${report.source.currency}` : ""}`}</dd>
                    <small>原值：{rawValue(report.metrics[item.metric_key])}</small>
                  </div>
                ))}
              </dl>
            ) : <p>来源不完整，指标未提供；缺失值不按零展示。</p>}
            {report.complete && <details><summary>按来源状态计数</summary><ul>
              {report.metrics.status_counts.map((row) => <li key={row.status}>{row.status}：{row.count}</li>)}
            </ul></details>}
            <p>付款、退款分别按本日报的业务日期及来源时间字段统计；精确口径以封存报告为准。</p>
          </Card>
          <Card title="异常与质量">
            {report.findings.length ? (
              <ul>{report.findings.map((finding) => (
                <li key={finding.finding_id}>
                  <strong>{findingNames[finding.code]}</strong> · {severityNames[finding.severity]}
                  {finding.metric_key && <> · {metricNames[finding.metric_key]}</>}
                  {finding.evidence_ids.length > 0 && <> · {finding.evidence_ids.length} 条证据引用</>}
                </li>
              ))}</ul>
            ) : <p>{report.complete ? "本次规则未报告异常。" : "没有可用的异常明细。"}</p>}
          </Card>
          <div className="actions"><button onClick={() => setEvidenceOpen(true)}>查看来源与证据引用</button></div>
          {evidenceOpen && (
            <Modal title="来源与证据引用" drawer close={() => setEvidenceOpen(false)}>
              <p>当前日报：{report.business_day}；{source}；共 {report.evidence_count} 条证据。</p>
              <p>此只读接口提供引用编号和数量，未提供证据正文。</p>
              {report.findings.map((finding) => (
                <section key={finding.finding_id}>
                  <h3>{findingNames[finding.code]}</h3>
                  <ul>{finding.evidence_ids.map((id) => <li className="daily-id" key={id}>{id}</li>)}</ul>
                </section>
              ))}
              <details><summary>报告绑定与版本</summary>
                <p className="daily-id">报告 {report.report_id} · 快照 {report.snapshot_id}</p>
                <p className="daily-id">事实摘要 {report.facts_hash} · 内容摘要 {report.content_hash}</p>
                <p className="daily-id">工作流版本：{daily.workflow_version}；来源配置版本：{report.source.source_config_version}</p>
              </details>
            </Modal>
          )}
        </>
      )}
    </>
  );
}
