"use client";
import { useEffect, useRef, useState } from "react";
import type { A01ReadClient } from "../lib/p3-live-client";
import type { DTO } from "../lib/p3-present";
import { decisionGate, exactAcknowledgements } from "../lib/p3-decision-gate";
import { parameterClarification } from "../lib/p3-present";
import { P3Failure, PreparedWrite } from "../lib/p3-transport";
import { Card, Modal, Notice } from "./ui";
type Receipt = DTO["CreateTaskReceipt"] | DTO["DecisionReceipt"];
const safeError = (error: unknown) =>
  error instanceof P3Failure ? error.message : "提交结果待核实，请保留原请求。";
function Submission({
  prepared,
  client,
  onResult,
  onState,
  validate,
}: {
  prepared: PreparedWrite<Receipt>;
  client: A01ReadClient;
  onResult: (result: Receipt) => void;
  onState?: (phase: "ready" | "pending" | "unknown" | "settled") => void;
  validate?: (result: Receipt) => boolean;
}) {
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [result, setResult] = useState<Receipt | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const alive = useRef(true);
  const sending = useRef(false);
  useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    if (uncertain || busy) window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [uncertain, busy]);
  const accept = (receipt: Receipt) => {
    if (validate && !validate(receipt))
      throw new P3Failure("WRITE_RESULT_UNKNOWN");
    if (receipt.request_key !== prepared.requestKey)
      throw new P3Failure("WRITE_RESULT_UNKNOWN");
    if (prepared.operation === "decision" && !("decision_id" in receipt))
      throw new P3Failure("WRITE_RESULT_UNKNOWN");
    if (prepared.operation === "create_task" && "decision_id" in receipt)
      throw new P3Failure("WRITE_RESULT_UNKNOWN");
    if (alive.current) {
      setResult(receipt);
      setUncertain(false);
      setMessage("");
      onState?.("settled");
      onResult(receipt);
    }
  };
  async function send() {
    if (sending.current) return;
    sending.current = true;
    onState?.("pending");
    setBusy(true);
    setMessage("");
    try {
      accept(await prepared.send());
    } catch (error) {
      if (alive.current) {
        setMessage(safeError(error));
        setUncertain(
          !(error instanceof P3Failure) ||
            error.code === "WRITE_RESULT_UNKNOWN",
        );
        onState?.(
          !(error instanceof P3Failure) || error.code === "WRITE_RESULT_UNKNOWN"
            ? "unknown"
            : "settled",
        );
      }
    } finally {
      sending.current = false;
      if (alive.current) setBusy(false);
    }
  }
  async function read() {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    try {
      const receipt = await client.requestReceipt(
        prepared.requestKey,
        prepared.operation,
      );
      if (receipt.receipt.operation !== prepared.operation)
        throw new P3Failure("INVALID_RESPONSE");
      if (receipt.receipt.operation === "resolve")
        throw new P3Failure("INVALID_RESPONSE");
      accept(receipt.receipt.result);
    } catch (error) {
      if (alive.current) {
        setMessage(
          error instanceof P3Failure && error.code === "RESOURCE_NOT_FOUND"
            ? "原键暂无可见回执，仍待核实；不证明提交失败。"
            : safeError(error),
        );
      }
    } finally {
      sending.current = false;
      if (alive.current) setBusy(false);
    }
  }
  return (
    <Card title="本次原请求">
      <p>原请求键：{prepared.requestKey}</p>
      <p>仅保留本次原键/原字节；不自动提交、不换键或发送相反动作。</p>
      {message && (
        <Notice title={uncertain ? "提交结果待核实" : "请求未完成"}>
          {message}
        </Notice>
      )}
      {result &&
        ("decision_id" in result ? (
          <Notice title="原审批意见已记录 · 不推断执行状态">
            <p>
              原决定：{result.decision_id} · {result.action} ·{" "}
              {result.decided_by} · {result.decided_at}
            </p>
            <p>
              原计划 v{result.plan_version} · hash {result.plan_hash} · resume{" "}
              {result.resume_state} · duplicate {String(result.duplicate)}
            </p>
            <p>
              假设集合：{result.acknowledged_assumption_keys.join("、") || "无"}
              。这不是执行、采购或入库成功。
            </p>
          </Notice>
        ) : (
          <Notice title="正式任务创建回执">
            <p>
              新 task：{result.task_id} · 源分析 task：{result.source_task_id}
            </p>
            <p>
              状态 {result.state} · duplicate {String(result.duplicate)}
              ；不能推断计划或执行完成。
            </p>
            <a className="button" href={`/tasks/${result.task_id}`}>
              查看本次任务
            </a>
          </Notice>
        ))}
      <div className="actions">
        <button
          className="primary"
          data-action="send-original"
          disabled={busy}
          onClick={() => void send()}
        >
          {busy
            ? "正在核实"
            : result || uncertain
              ? "显式同键重投原请求"
              : "明确提交本次请求"}
        </button>
        <button
          data-action="read-original"
          disabled={busy}
          onClick={() => void read()}
        >
          读取原请求回执
        </button>
      </div>
    </Card>
  );
}
export function DecisionActions({
  read,
  client,
  refresh,
  onHoldChange,
}: {
  read: DTO["ApprovalRead"];
  client: A01ReadClient;
  refresh: () => void;
  onHoldChange?: (held: boolean) => void;
}) {
  const [intent, setIntent] = useState<{
    action: DTO["DecisionInput"]["action"];
    keys: readonly string[];
  } | null>(null);
  const [selected, setSelected] = useState<string[]>([]),
    [action, setAction] = useState<DTO["DecisionInput"]["action"] | null>(null);
  const [prepared, setPrepared] = useState<PreparedWrite<Receipt> | null>(null),
    [problem, setProblem] = useState(""),
    [busy, setBusy] = useState(false);
  const [submissionPhase, setSubmissionPhase] = useState("ready");
  useEffect(() => {
    onHoldChange?.(
      action !== null || (prepared !== null && submissionPhase !== "settled"),
    );
    return () => onHoldChange?.(false);
  }, [action, prepared, submissionPhase, onHoldChange]);
  const start = useRef(performance.now()),
    [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const timer = setInterval(
      () => setElapsed(performance.now() - start.current),
      1000,
    );
    return () => clearInterval(timer);
  }, []);
  const allowed = decisionGate(read, Date.parse(read.server_time) + elapsed);
  const assumptions = read.plan.required_assumptions;
  async function confirm() {
    if (!action || busy || prepared) return;
    setBusy(true);
    setProblem("");
    try {
      const current = await client.approval(read.approval.approval_id);
      if (
        current.plan.plan_id !== read.plan.plan_id ||
        current.plan.plan_version !== read.plan.plan_version ||
        current.plan.plan_hash !== read.plan.plan_hash
      )
        throw new P3Failure("APPROVAL_SUPERSEDED");
      if (!decisionGate(current, Date.parse(current.server_time)))
        throw new P3Failure("NOT_READY");
      const keys = action === "approve_with_assumptions" ? selected : [];
      if (
        action === "approve_with_assumptions" &&
        !exactAcknowledgements(current, keys)
      )
        throw new P3Failure("ASSUMPTION_SET_MISMATCH");
      if (action === "approve" && current.plan.required_assumptions.length)
        throw new P3Failure("ASSUMPTION_ACK_REQUIRED");
      setIntent({ action, keys: [...keys] });
      setPrepared(
        client.prepareDecision({
          schema_version: "p3-web-v1",
          request_key: crypto.randomUUID(),
          approval_id: current.approval.approval_id,
          plan_id: current.plan.plan_id,
          plan_version: current.plan.plan_version,
          plan_hash: current.plan.plan_hash,
          action,
          acknowledged_assumption_keys: keys,
          nonce: current.nonce!,
        }),
      );
      setAction(null);
    } catch (error) {
      setProblem(safeError(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Notice
        title={
          prepared
            ? "原请求恢复与回执"
            : allowed
              ? "本版本可记录审批意见"
              : "本版本决定禁用"
        }
      >
        以当前服务端可决定状态、版本与完整披露为准；倒计时仅参考，服务端取得锁后再次裁定期限。执行前数据复核由Worker执行。
      </Notice>
      {!prepared && (
        <>
          {assumptions.length > 0 && (
            <Card title="本版本完整假设确认">
              <p>
                原始在途未知不等于零；按0估算可能重复补货。普通批准不能替代逐项确认，不默认勾选。
              </p>
              {assumptions.map((x) => (
                <label className="assumption-option" key={x.key}>
                  <input
                    type="checkbox"
                    checked={selected.includes(x.key)}
                    disabled={!allowed}
                    onChange={(event) =>
                      setSelected((keys) =>
                        event.target.checked
                          ? [...keys, x.key]
                          : keys.filter((key) => key !== x.key),
                      )
                    }
                  />
                  <span>
                    {x.key} · {x.sku_key} · 仅本版本估算{x.estimated_units}件
                  </span>
                </label>
              ))}
            </Card>
          )}
          <div className="decision-actions">
            {(
              [
                [
                  "approve",
                  "B02",
                  "批准本版本",
                  !allowed || assumptions.length > 0,
                ],
                ["reject", "B03", "拒绝本版本", !allowed],
                [
                  "approve_with_assumptions",
                  "B04",
                  "确认完整假设并批准",
                  !allowed ||
                    !assumptions.length ||
                    !exactAcknowledgements(read, selected),
                ],
                [
                  "reject_assumptions",
                  "B05",
                  "拒绝假设",
                  !allowed || !assumptions.length,
                ],
              ] as const
            ).map(([value, control, text, disabled]) => (
              <button
                key={value}
                data-control={control}
                disabled={disabled}
                onClick={() => setAction(value)}
              >
                {text}
              </button>
            ))}
          </div>
        </>
      )}
      {problem && (
        <Notice title="意见尚未准备">
          {problem}
          <button onClick={refresh}>读取当前冻结版本</button>
        </Notice>
      )}
      {action && (
        <Modal
          title="确认本版本审批意见"
          close={() => {
            if (!busy) setAction(null);
          }}
        >
          <p>
            action：{action} · v{read.plan.plan_version} ·{" "}
            {read.plan.item_count} 项 / {read.plan.total_units} 件
          </p>
          <p>本版本hash：{read.plan.plan_hash}</p>
          <p>
            此次精确假设集合：
            {action === "approve_with_assumptions" ? selected.join("、") : "无"}
          </p>
          <p>
            只准备此原请求；下一步明确提交才发送。不会批准其他版本或保证执行成功。
          </p>
          <button disabled={busy} onClick={() => void confirm()}>
            确认并准备原请求
          </button>
        </Modal>
      )}
      {prepared && (
        <Submission
          prepared={prepared}
          client={client}
          onState={setSubmissionPhase}
          validate={(result) =>
            "decision_id" in result &&
            result.plan_id === read.plan.plan_id &&
            result.task_id === read.plan.task_id &&
            result.plan_version === read.plan.plan_version &&
            result.plan_hash === read.plan.plan_hash &&
            result.action === intent?.action &&
            JSON.stringify([...result.acknowledged_assumption_keys].sort()) ===
              JSON.stringify([...(intent?.keys ?? [])].sort())
          }
          onResult={() => {}}
        />
      )}
    </>
  );
}
export function CreateTaskDialog({
  client,
  shops,
  source,
  close,
  onHoldChange,
}: {
  client: A01ReadClient;
  shops: readonly string[];
  source?: DTO["SourceBinding"];
  close: () => void;
  onHoldChange?: (held: boolean) => void;
}) {
  useEffect(() => {
    onHoldChange?.(true);
    return () => onHoldChange?.(false);
  }, [onHoldChange]);
  const [phase, setPhase] = useState<
    "ready" | "pending" | "unknown" | "settled"
  >("ready");
  const [mode, setMode] = useState<"from_report" | "new_cycle">(
    source ? "from_report" : "new_cycle",
  );
  const [shop, setShop] = useState(shops[0] ?? ""),
    [L, setL] = useState("3"),
    [R, setR] = useState("7"),
    [S, setS] = useState("2"),
    [caseName, setCase] = useState("baseline");
  const [confirmed, setConfirmed] = useState(false),
    [prepared, setPrepared] = useState<PreparedWrite<Receipt> | null>(null),
    [problem, setProblem] = useState(""),
    [discard, setDiscard] = useState(false);
  const valid =
    [L, R, S].every((x) => /^(0|[1-9][0-9]*)$/.test(x) && Number(x) <= 365) &&
    shops.includes(shop);
  const clarification = parameterClarification(shop, shops, [L, R, S]);
  function prepare() {
    setProblem("");
    try {
      const key = crypto.randomUUID();
      if (mode === "from_report" && source)
        setPrepared(
          client.prepareTask({
            schema_version: "p3-web-v1",
            mode: "from_report",
            request_key: key,
            source_task_id: source.source_task_id,
            source_report_id: source.report_id,
            snapshot_id: source.snapshot_id,
            facts_hash: source.facts_hash,
          }),
        );
      else {
        if (!valid || !confirmed) throw new P3Failure("INVALID_REQUEST");
        setPrepared(
          client.prepareTask({
            schema_version: "p3-web-v1",
            mode: "new_cycle",
            request_key: key,
            shop_id: shop,
            parameters: {
              source_mode: "mock",
              dataset_version: "inventory-v1",
              fixture_case: caseName,
              L: Number(L),
              R: Number(R),
              S: Number(S),
            },
          }),
        );
      }
    } catch (error) {
      setProblem(safeError(error));
    }
  }
  function requestClose() {
    if (phase === "pending" || phase === "unknown") {
      setProblem(
        "原请求已准备；请先核实原回执。关闭会丢失内存原字节，不会自动撤销任务。",
      );
      return;
    }
    if (phase === "settled") {
      close();
      return;
    }
    if (!discard) {
      setDiscard(true);
      return;
    }
    close();
  }
  return (
    <Modal title="创建正式补货任务" drawer close={requestClose}>
      <p>
        仅本阶段Mock业务；显式创建新任务，不恢复源completed，不继承旧approval/hash/nonce/请求键/确认集合。
      </p>
      {!prepared && (
        <>
          {source && (
            <label>
              来源方式
              <select
                value={mode}
                onChange={(event) => {
                  setMode(event.target.value as typeof mode);
                  setConfirmed(false);
                }}
              >
                <option value="from_report">指定可信冻结报告</option>
                <option value="new_cycle">新周期重新采集</option>
              </select>
            </label>
          )}
          {mode === "from_report" && source ? (
            <>
              <p>
                源task/report/snapshot：{source.source_task_id}/
                {source.report_id}/{source.snapshot_id}
              </p>
              <p>源facts_hash：{source.facts_hash}</p>
            </>
          ) : (
            <>
              <label>
                当前operator店铺
                <select
                  value={shop}
                  onChange={(event) => {
                    setShop(event.target.value);
                    setConfirmed(false);
                  }}
                >
                  {shops.map((id) => (
                    <option key={id}>{id}</option>
                  ))}
                </select>
              </label>
              <label>
                Mock案例
                <select
                  value={caseName}
                  onChange={(event) => {
                    setCase(event.target.value);
                    setConfirmed(false);
                  }}
                >
                  {[
                    "baseline",
                    "known_inbound",
                    "unknown_inbound",
                    "unknown_stock",
                    "normal",
                    "no_demand",
                  ].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
              {(
                [
                  ["L", L, setL],
                  ["R", R, setR],
                  ["S", S, setS],
                ] as const
              ).map(([name, value, set]) => (
                <label key={name}>
                  {name}（0–365整数）
                  <input
                    inputMode="numeric"
                    value={value}
                    onChange={(event) => {
                      set(event.target.value);
                      setConfirmed(false);
                    }}
                  />
                </label>
              ))}
              <button
                data-control="B35"
                disabled={!valid}
                onClick={() => setConfirmed(true)}
              >
                确认结构化参数
              </button>
              {!confirmed && (
                <Notice
                  title={clarification ? "参数需要澄清" : "参数尚未明确确认"}
                >
                  <p role="status">
                    {clarification ??
                      "请核对 Mock 案例和 L/R/S，明确确认结构化参数。"}
                  </p>
                  <p>
                    此时未创建任务或报告。完整参数的明确提交是新请求，不自动续答或恢复旧任务。
                  </p>
                </Notice>
              )}
              {confirmed && (
                <Notice title="参数已明确确认">
                  {caseName} · L/R/S={L}/{R}/{S}；无自然语言猜参或模型预解析。
                </Notice>
              )}
            </>
          )}
          <button
            className="primary"
            data-control="B01"
            disabled={mode === "new_cycle" && (!valid || !confirmed)}
            onClick={prepare}
          >
            准备本次正式任务请求
          </button>
        </>
      )}
      {problem && <Notice title="原请求提示">{problem}</Notice>}
      {prepared && (
        <Submission
          prepared={prepared}
          client={client}
          onState={setPhase}
          onResult={() => {}}
        />
      )}
      {discard && phase === "ready" && (
        <Notice title="草稿尚未提交">
          <button data-control="B45" onClick={close}>
            确认丢弃并关闭
          </button>
          <button onClick={() => setDiscard(false)}>继续编辑</button>
        </Notice>
      )}
    </Modal>
  );
}
