"use client";
import { useEffect, useRef, useState } from "react";
import type { DTO } from "../lib/p3-present";
import { label } from "../lib/p3-present";
import { syncMeaning } from "../lib/p4-read-facts";
import { P3Failure, PreparedWrite } from "../lib/p3-transport";
import type { P3Client } from "../lib/p3-transport";
import {
  canResolve,
  itemConsistent,
  normalizedReason,
  resolveReceiptBound,
  validItemDTO,
} from "../lib/p3-item-contract";
import { Sync } from "./live-readviews";
import { Card, Disabled, Modal, Notice, Status } from "./ui";
export type ItemClient = Pick<
  P3Client,
  "item" | "prepareResolve" | "requestReceipt"
>;
const safeError = (error: unknown) =>
  error instanceof P3Failure
    ? error.code === "ITEM_VERSION_CONFLICT"
      ? "工作项版本已改变，请读取当前项及原回执；不会自动换键。"
      : error.code === "ITEM_STATE_CONFLICT"
        ? "工作项已进入终态或当前不可处理，请核实当前项及原回执。"
        : error.message
    : "结果待核实，请保留原请求。";
export function ExecutionFacts({
  read,
  taskId,
}: {
  read: DTO["ExecutionRead"];
  taskId: string;
}) {
  if (
    !validItemDTO("ExecutionRead", read) ||
    read.task_id !== taskId ||
    new Set(read.item_ids).size !== read.item_ids.length
  )
    return (
      <Notice title="执行事实暂时不可安全读取">不补猜执行或内部项结果。</Notice>
    );
  return (
    <>
      <Notice title="Worker 执行回执">
        执行仅由 Worker
        完成；任务完成与每个内部项跟进完成分别记账。仅内部工作项，不表示采购、入库或库存修改。
      </Notice>
      <Card title="执行事实">
        <Status value={read.status} />
        <p>
          task：{read.task_id} · execution：{read.execution_id}
        </p>
        <p>
          计划：{read.plan_id} · 审批：{read.approval_id}
        </p>
        <p>复核快照：{read.revalidation_snapshot_id}</p>
        <p>
          operation：{read.operation_key} · hash：{read.request_hash}
        </p>
        <p>
          完成时间：{read.completed_at ?? "未报告"} · 错误：
          {read.error_code ?? "无"}
        </p>
        <p>
          此回执列出 {read.item_ids.length} 项；不推断这些工作项已跟进完成。
        </p>
        <div className="list-table">
          {read.item_ids.map((id) => (
            <article className="list-row" key={id}>
              <p>{id}</p>
              <a
                className="button"
                href={`/replenishment-items/${id}`}
                data-control="B25"
              >
                查看内部项
              </a>
            </article>
          ))}
        </div>
      </Card>
      <Card title="执行同步 · 独立投影事实">
        <Sync sync={read.sync} />
        <p>同步异常不撤销已经提交的业务结果。</p>
      </Card>
      <Disabled
        control="B32"
        reason="执行与恢复由 Worker 合同控制，无手动执行或重试操作。"
      >
        手动恢复未开放
      </Disabled>
    </>
  );
}
export function ItemListFacts({
  read,
  state,
  onFilter,
}: {
  read: DTO["ItemList"];
  state?: string;
  onFilter?: (state: string) => void;
}) {
  const [localFilter, setFilter] = useState("all");
  const filter = state ?? localFilter;
  if (
    !validItemDTO("ItemList", read) ||
    new Set(read.items.map((x) => x.item_id)).size !== read.items.length ||
    read.items.length > read.total
  )
    return (
      <Notice title="内部项暂时不可安全读取">不显示部分响应或补猜统计。</Notice>
    );
  const items = onFilter
    ? read.items
    : read.items.filter((x) => filter === "all" || x.state === filter);
  return (
    <>
      <Notice title="内部跟进清单">
        仅内部工作项，不是采购或入库；业务状态与同步状态分别呈现。
      </Notice>
      <div className="stats">
        <Card>
          <p>待跟进</p>
          <strong className="metric">{read.counts.open}</strong>
        </Card>
        <Card>
          <p>已完成</p>
          <strong className="metric">{read.counts.completed}</strong>
        </Card>
        <Card>
          <p>已关闭</p>
          <strong className="metric">{read.counts.closed}</strong>
        </Card>
      </div>
      <Card title="内部工作项">
        <label>
          {onFilter ? "当前授权范围状态筛选" : "本页状态筛选"}
          <select
            data-control="B24"
            value={filter}
            onChange={(e) =>
              onFilter ? onFilter(e.target.value) : setFilter(e.target.value)
            }
          >
            {["all", "open", "completed", "closed"].map((x) => (
              <option key={x} value={x}>
                {x === "all" ? "全部" : label(x)}
              </option>
            ))}
          </select>
        </label>
        <p>
          本页 {read.items.length} 项 · 服务端总计 {read.total} · 截至{" "}
          {read.as_of}
        </p>
        <div className="list-table" aria-label="完整本页内部项">
          {items.map((item) => (
            <article className="list-row" key={item.item_id}>
              <div>
                <strong>{item.sku_key}</strong>
                <small>
                  {item.item_id} · v{item.version}
                </small>
              </div>
              <strong>{item.quantity} 件</strong>
              <Status value={item.state} />
              <span>{syncMeaning(item.sync)}</span>
              <a
                className="button"
                href={`/replenishment-items/${item.item_id}`}
                data-control="B25"
              >
                查看工作项
              </a>
            </article>
          ))}
        </div>
        {items.length === 0 && <p>本页筛选下暂无记录。</p>}
        {read.next_cursor && <p>仍有后续页，当前页不代表完整范围。</p>}
      </Card>
    </>
  );
}
export function ItemDetails({
  read,
  client,
  onHoldChange,
}: {
  read: DTO["ItemRead"];
  client: ItemClient;
  onHoldChange?: (held: boolean) => void;
}) {
  const [receipt, setReceipt] = useState<DTO["ResolveReceipt"] | null>(null);
  const [action, setAction] = useState<DTO["ResolveInput"]["action"] | null>(
    null,
  );
  const summary = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (receipt && action === null) summary.current?.focus();
  }, [receipt, action]);
  useEffect(() => {
    onHoldChange?.(action !== null);
    return () => onHoldChange?.(false);
  }, [action, onHoldChange]);
  if (!itemConsistent(read))
    return (
      <Notice title="内部项事实暂时不可安全读取">
        版本或跟进记录绑定不全，不能准备操作。
      </Notice>
    );
  const item = receipt?.item ?? read.item,
    resolution = receipt?.resolution ?? read.resolution;
  return (
    <>
      <div ref={summary} tabIndex={-1} data-item-summary>
        <Card title={receipt ? "原回执中的内部项事实" : "读取时内部项事实"}>
          <p>
            {item.item_id} · {item.sku_key}
          </p>
          <p>
            pool：{item.stock_pool_key} · {item.quantity} 件
          </p>
          <Status value={item.state} />
          <p>
            当前版本 v{item.version}；内部跟进完成不等于采购、入库或库存修改。
          </p>
        </Card>
      </div>
      <Card title="来源与可见范围">
        {read.visible_source_task_id ? (
          <a
            className="button"
            data-control="B37"
            href={`/tasks/${read.visible_source_task_id}`}
          >
            查看可见来源任务
          </a>
        ) : (
          <p>来源任务受当前查看权限制。</p>
        )}
        <p>来源计划：{read.visible_plan_id ?? "受当前查看权限制"}</p>
      </Card>
      <Card title="跟进记录">
        {resolution ? (
          <>
            <p>
              原动作 {resolution.action} · 原因：{resolution.reason}
            </p>
            <p>
              原处理人 {resolution.resolved_by} · {resolution.resolved_at}
            </p>
            <p>
              版本 v{resolution.before_version} → v{resolution.after_version} ·
              hash {resolution.resolution_payload_hash}
            </p>
          </>
        ) : (
          <p>尚无完成或关闭记录。</p>
        )}
      </Card>
      <Card title="同步 · 独立投影事实">
        <Sync sync={item.sync} />
        <p>业务终态成立不代表同步成功；同步异常不重开工作项。</p>
      </Card>
      {canResolve(read) && !receipt && (
        <div className="actions">
          <button
            className="primary"
            data-control="B26"
            onClick={() => setAction("complete")}
          >
            记录内部跟进完成
          </button>
          <button data-control="B27" onClick={() => setAction("close")}>
            关闭内部工作项
          </button>
        </div>
      )}
      {item.state !== "open" ? (
        <Notice title="终态只读">
          不能重新打开、生成新的同项操作或手动重发同步。
        </Notice>
      ) : (
        !canResolve(read) && (
          <Notice title="当前不能处理内部项">
            {read.disabled_reasons.join("、") || "服务端当前未允许处理此项。"}
          </Notice>
        )
      )}
      <Disabled control="B34" reason="复制交接未开放。">
        复制安全编号
      </Disabled>
      {action && (
        <ResolveDialog
          read={read}
          action={action}
          client={client}
          onReceipt={setReceipt}
          close={() => setAction(null)}
        />
      )}
    </>
  );
}
function ResolveDialog({
  read,
  action,
  client,
  onReceipt,
  close,
}: {
  read: DTO["ItemRead"];
  action: DTO["ResolveInput"]["action"];
  client: ItemClient;
  onReceipt: (receipt: DTO["ResolveReceipt"]) => void;
  close: () => void;
}) {
  const [reason, setReason] = useState(""),
    [attempted, setAttempted] = useState(false),
    [discard, setDiscard] = useState(false);
  const [problem, setProblem] = useState(""),
    [phase, setPhase] = useState<
      "draft" | "ready" | "pending" | "unknown" | "settled"
    >("draft");
  const [prepared, setPrepared] = useState<{
    before: DTO["ItemRead"];
    input: DTO["ResolveInput"];
    write: PreparedWrite<DTO["ResolveReceipt"]>;
  } | null>(null);
  const [receipt, setReceipt] = useState<DTO["ResolveReceipt"] | null>(null);
  const alive = useRef(true),
    busy = useRef(false),
    original = useRef<DTO["ResolveReceipt"] | undefined>(undefined),
    sendButton = useRef<HTMLButtonElement>(null);
  useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );
  useEffect(() => {
    if (prepared) sendButton.current?.focus();
  }, [prepared]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    if (phase === "unknown" || phase === "pending")
      window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [phase]);
  const validReason = normalizedReason(reason);
  function requestClose() {
    if (phase === "pending" || phase === "unknown") {
      setProblem("请先核实原回执，关闭会丢失内存原请求；不表示撤销操作。");
      return;
    }
    if (phase === "settled" || reason.length === 0) {
      close();
      return;
    }
    if (!discard) {
      setDiscard(true);
      return;
    }
    close();
  }
  async function prepare() {
    if (busy.current || prepared) return;
    setAttempted(true);
    if (validReason === null) return;
    busy.current = true;
    setPhase("pending");
    setProblem("");
    try {
      const current = await client.item(read.item.item_id);
      if (
        !itemConsistent(current) ||
        current.item.item_id !== read.item.item_id
      )
        throw new P3Failure("INVALID_RESPONSE");
      if (current.item.version !== read.item.version)
        throw new P3Failure("ITEM_VERSION_CONFLICT");
      if (!canResolve(current)) throw new P3Failure("ITEM_STATE_CONFLICT");
      const input: DTO["ResolveInput"] = {
        schema_version: "p3-web-v1",
        request_key: crypto.randomUUID(),
        action,
        reason: validReason,
        expected_version: current.item.version,
      };
      const write = client.prepareResolve(current.item.item_id, input);
      if (alive.current) {
        setPrepared({ before: current, input, write });
        setDiscard(false);
        setPhase("ready");
      }
    } catch (error) {
      if (alive.current) {
        setProblem(safeError(error));
        setPhase("draft");
      }
    } finally {
      busy.current = false;
    }
  }
  function accept(value: DTO["ResolveReceipt"]) {
    if (
      !prepared ||
      !resolveReceiptBound(
        prepared.before,
        prepared.input,
        value,
        original.current,
      )
    )
      throw new P3Failure("WRITE_RESULT_UNKNOWN");
    if (alive.current) {
      original.current ??= value;
      setReceipt(value);
      setPhase("settled");
      setProblem("");
      onReceipt(value);
    }
  }
  async function send() {
    if (!prepared || busy.current) return;
    busy.current = true;
    setPhase("pending");
    setProblem("");
    try {
      accept(await prepared.write.send());
    } catch (error) {
      if (alive.current) {
        setProblem(safeError(error));
        setPhase(
          !(error instanceof P3Failure) || error.code === "WRITE_RESULT_UNKNOWN"
            ? "unknown"
            : "ready",
        );
      }
    } finally {
      busy.current = false;
    }
  }
  async function readOriginal() {
    if (!prepared || busy.current) return;
    busy.current = true;
    try {
      const value = await client.requestReceipt(
        prepared.write.requestKey,
        "resolve",
      );
      if (
        !validItemDTO("RequestRead", value) ||
        value.request_key !== prepared.write.requestKey ||
        value.receipt.operation !== "resolve"
      )
        throw new P3Failure("WRITE_RESULT_UNKNOWN");
      accept(value.receipt.result);
    } catch (error) {
      if (alive.current)
        setProblem(
          error instanceof P3Failure && error.code === "RESOURCE_NOT_FOUND"
            ? "原键暂无可见回执，仍待核实；不证明提交失败。"
            : safeError(error),
        );
    } finally {
      busy.current = false;
    }
  }
  return (
    <Modal
      title={action === "complete" ? "记录内部跟进完成" : "关闭内部工作项"}
      close={requestClose}
      closeControl="B28"
    >
      <p>仅单项内部跟进，终态不能重开；不修改库存、采购或入库。</p>
      <p>
        item：{read.item.item_id} · 原版本 v{read.item.version} · action{" "}
        {action}
      </p>
      {!prepared ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void prepare();
          }}
        >
          <label htmlFor="resolve-reason">原因（trim 后1–1000字符）</label>
          <textarea
            id="resolve-reason"
            value={reason}
            disabled={phase === "pending"}
            onChange={(event) => {
              setReason(event.target.value);
              setAttempted(false);
              setDiscard(false);
            }}
            aria-invalid={attempted && validReason === null}
            aria-describedby="reason-error"
          />
          <p className="error-text" id="reason-error" aria-live="polite">
            {attempted && validReason === null
              ? "请填写1–1000字符的非空原因。"
              : ""}
          </p>
          <button type="submit" disabled={phase === "pending"}>
            确认原因并准备原请求
          </button>
        </form>
      ) : (
        <Card title="本次原请求">
          <p>原键：{prepared.write.requestKey}</p>
          <p>
            原因：{prepared.input.reason} · expected_version{" "}
            {prepared.input.expected_version}
          </p>
          <p>仅本次原键/原字节，不自动提交、不换键、不发送相反动作。</p>
          <div className="actions">
            <button
              ref={sendButton}
              data-control={action === "complete" ? "B07" : "B08"}
              data-action="resolve-original"
              disabled={phase === "pending"}
              onClick={() => void send()}
            >
              {phase === "pending"
                ? "正在核实"
                : receipt || phase === "unknown"
                  ? "显式同键重投原请求"
                  : "明确提交本次内部项操作"}
            </button>
            <button
              data-action="resolve-receipt"
              disabled={phase === "pending"}
              onClick={() => void readOriginal()}
            >
              读取原请求回执
            </button>
          </div>
        </Card>
      )}
      {problem && (
        <Notice
          title={phase === "unknown" ? "内部项提交待核实" : "操作尚未完成"}
        >
          {problem}
        </Notice>
      )}
      {receipt && (
        <Notice title="内部跟进已记录">
          <p>
            原 resolution：{receipt.resolution.resolution_id} · 原处理人{" "}
            {receipt.resolution.resolved_by} · {receipt.resolution.resolved_at}
          </p>
          <p>
            state {receipt.item.state} · v{receipt.item.version} · duplicate{" "}
            {String(receipt.duplicate)}
          </p>
          <p>
            原语义 hash：{receipt.resolution.resolution_payload_hash}；同步{" "}
            {receipt.item.sync.state === "synced"
              ? syncMeaning(receipt.item.sync)
              : label(receipt.item.sync.state)}
            。不表示采购或入库成功。
          </p>
        </Notice>
      )}
      {discard && (
        <Notice title="确认丢弃未提交草稿">
          再次关闭将丢弃本次原因及尚未发送的预备请求。
        </Notice>
      )}
    </Modal>
  );
}
