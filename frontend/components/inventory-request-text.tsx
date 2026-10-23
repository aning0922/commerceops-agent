"use client";
import { useId } from "react";
import type { N01Response } from "../lib/p4-n01";
import { n01CandidateText } from "../lib/p4-n01";
import { Card, Notice } from "./ui";

// M02 local input only. The parent supplies interpretation only after A's API is signed.
export function InventoryRequestText({
  text,
  onChange,
  interpret,
  busy = false,
}: {
  text: string;
  onChange: (text: string) => void;
  interpret?: () => void;
  busy?: boolean;
}) {
  const input = useId(),
    hint = useId();
  const count = [...text].length;
  return (
    <>
      <label htmlFor={input}>自然语言请求草稿</label>
      <textarea
        id={input}
        value={text}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={hint}
        aria-invalid={count > 2000}
        rows={3}
      />
      <p id={hint}>
        这还是提交前草稿。先检查受支持的范围和参数，再由你明确确认；不会自动创建任务或批准计划。
        {count}/2000 字符
      </p>
      <button
        type="button"
        disabled={!interpret || busy || !text.trim() || count > 2000}
        onClick={() => interpret?.()}
      >
        {busy ? "正在检查草稿" : "检查草稿与参数"}
      </button>
      {!interpret && <p>参数解释接口尚未接入，此组件不发送任何请求。</p>}
    </>
  );
}

export function InventoryCandidateReview({
  read,
  text,
}: {
  read: N01Response;
  text: string;
}) {
  const p = read.preflight;
  const titles = {
    EXPLICIT_PARAMETERS: "已识别明确参数，仍待你确认",
    MISSING_PARAMETERS: "请补齐明确参数后再确认",
    INVALID_PARAMETERS: "原句参数未通过校验，请修改原句重新检查",
    UNSUPPORTED_TEXT: "此原句超出当前支持范围",
  };
  return (
    <Card title="草稿参数与来源">
      <Notice title={titles[p.reason]} tone={p.status === "ready" ? "info" : "warning"}>
        {p.reason === "MISSING_PARAMETERS"
          ? `缺少明确参数：${p.missing.join("、")}。示例值不是已确认参数；请在下方明确填写全部参数并确认。`
          : p.status !== "ready"
            ? "不能用示例默认值忽略此原句。请修正后重新检查，或明确取消原句，另开结构化新周期。"
            : "预检查尚未创建任务、采集报告或批准计划。下一步核对来源、窗口、范围和完整参数。"}
      </Notice>
      <p>来源：Mock / inventory-v1 / {p.source.fixture_case}；模型未使用。</p>
      <p>范围：当前所选店铺的全部 fixture 商品，不支持选取部分 SKU。</p>
      <p>
        观察窗口：最近七个完整自然日，{p.window.start} 至 {p.window.end}
        （结束不包含）；时区 {p.window.timezone}；冻结来源时间 {p.window.as_of}。
      </p>
      <p>此窗口来自 Mock fixture，尚未采集。R 是复查周期，不是上述观察窗口。</p>
      <div>
        <table className="n01-candidates">
          <thead><tr><th>参数</th><th>候选天数</th><th>来源</th></tr></thead>
          <tbody>{p.candidates.map((c) => <tr key={c.name}>
            <th scope="row">{c.name}</th><td>{c.value}</td>
            <td>{c.source === "explicit_text"
              ? <>原句明确参数：{n01CandidateText(text, c)}</>
              : "演示示例，未确认"}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </Card>
  );
}
