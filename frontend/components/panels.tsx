"use client";
import { useState } from "react";
import type { ItemFact, MockView } from "../lib/view-model";
import { Card, Disabled, Modal, Notice } from "./ui";
export function Panels({
  panel,
  close,
  view,
  item,
  open,
}: {
  panel: string;
  close: () => void;
  view: MockView;
  item?: ItemFact;
  open: (panel: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [preview, setPreview] = useState(false);
  const [draft, setDraft] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [explanationState, setExplanationState] = useState<
    "template" | "loading" | "error"
  >("template");
  const resolve = panel === "complete" || panel === "close";
  const newDraft = panel === "draft";
  const title = resolve
    ? panel === "complete"
      ? "记录内部跟进完成"
      : "关闭内部工作项"
    : newDraft
      ? "新建库存分析"
      : panel === "provenance"
        ? "数据口径与来源"
        : panel === "explanation"
          ? "解释本报告"
          : panel === "account"
            ? "当前账号"
            : panel === "receipt"
              ? "原审批记录 · Mock"
              : "重新分析影响预览";
  const exit = () => {
    if (newDraft && draft.trim() && !discard) setDiscard(true);
    else close();
  };
  return (
    <Modal
      title={title}
      close={exit}
      drawer={newDraft || panel === "explanation"}
      closeControl={newDraft ? "B45" : resolve ? "B28" : "B22"}
    >
      <p className="muted">离线 Mock 样例 · 未连接业务服务</p>
      {resolve && (
        <>
          <Card title="单项版本摘要">
            <p>
              {item?.name} · {item?.id} · 当前版本 v{item?.version}
            </p>
            <p>仅记录内部跟进结果，不修改库存或采购；终态不可重开。</p>
          </Card>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setAttempted(true);
              setPreview(Boolean(reason.trim()));
            }}
          >
            <label htmlFor="resolve-reason">原因（必填）</label>
            <textarea
              id="resolve-reason"
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                setPreview(false);
              }}
              aria-invalid={attempted && !reason.trim()}
              aria-describedby="reason-error"
            />
            <p id="reason-error" className="error-text" aria-live="polite">
              {attempted && !reason.trim() ? "请填写完成或关闭原因。" : ""}
            </p>
            <button type="submit">检查原因（本地）</button>
            {preview && (
              <Notice title="本地原因校验完成">
                原因尚未提交；未生成请求键或业务回执。
              </Notice>
            )}
            <Disabled
              control={panel === "complete" ? "B07" : "B08"}
              reason="正式 resolve 合同/API 待独审；Mock 不改变内部项。"
            >
              {panel === "complete" ? "标记内部跟进完成" : "关闭内部工作项"}
            </Disabled>
            <button type="button" data-control="B28" onClick={close}>
              取消
            </button>
          </form>
        </>
      )}
      {newDraft && (
        <>
          <p>
            草稿尚无 task_id，不占用 Worker，不继承旧批准、假设确认、nonce
            或请求键。
          </p>
          <label htmlFor="draft-request">分析请求</label>
          <textarea
            id="draft-request"
            placeholder="例如：检查最近七天销量与库存，找出缺货风险。"
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setReviewed(false);
              setDiscard(false);
            }}
          />
          <button
            data-control="B35"
            disabled={!draft.trim()}
            onClick={() => setReviewed(true)}
          >
            确认本地草稿参数
          </button>
          {reviewed && (
            <Notice title="本地草稿待确认">
              {draft}
              <p>
                自然语言预解析/候选来源尚未接入；未猜选 SKU 或生成真实参数。
              </p>
            </Notice>
          )}
          <Disabled
            control="B01"
            reason="新任务合同/API 待独审；Mock 不创建任务或自动送审。"
          >
            创建分析并按规则送审
          </Disabled>
          {discard && (
            <Notice title="草稿尚未提交">
              关闭会丢弃本地输入。
              <button data-control="B45" onClick={close}>
                确认丢弃并关闭
              </button>
              <button onClick={() => setDiscard(false)}>继续编辑</button>
            </Notice>
          )}
        </>
      )}
      {panel === "provenance" && (
        <>
          <Card title="冻结快照">
            <p>
              {view.reportId} / v{view.version} · {view.snapshotId}
            </p>
            <p>
              数据源 MockCommerce；销量为 7
              日件数；退款冲减及范围由冻结报告确定。
            </p>
          </Card>
          <Card title="规则口径">
            <p>
              Q = max(0, ceil(日均需求 × (L + R + S)) − 可用库存 −
              已知在途)。此面板仅披露公式，不计算权威数量。
            </p>
            <p>
              Mock 参数 L3 / R7 / S2。负库存保留；原始未知为
              null；未知库存硬阻断。
            </p>
          </Card>
          <details data-control="B43">
            <summary>时间、新鲜度与版本</summary>
            <p>
              Asia/Shanghai ·
              expires_at：未知；部署新鲜度：未知。未连接服务器配置时不以
              24h/15min 作产品承诺。
            </p>
          </details>
        </>
      )}
      {panel === "explanation" && (
        <>
          <Card title="固定报告上下文">
            <p>
              {view.reportId} / v{view.version} · {view.snapshotId}
            </p>
            <p>
              只使用本报告冻结事实、规则、风险与来源；解释不能改变事实或审批。
            </p>
          </Card>
          <label htmlFor="explanation-fixture">
            离线解释状态样例（非业务请求）
          </label>
          <select
            id="explanation-fixture"
            value={explanationState}
            onChange={(e) =>
              setExplanationState(
                e.target.value as "template" | "loading" | "error",
              )
            }
          >
            <option value="template">模板降级</option>
            <option value="loading">加载中</option>
            <option value="error">读取失败</option>
          </select>
          <Notice
            title={
              explanationState === "template"
                ? "模板说明 · 预生成样例"
                : explanationState === "loading"
                  ? "正在读取解释 · Mock"
                  : "解释暂时无法读取"
            }
            tone="info"
          >
            {explanationState === "template"
              ? "未知在途按 0 估算存在重复补货风险。依据：本报告 SKU 行及冻结口径；不查询实时数据，不接 RAG。"
              : explanationState === "error"
                ? "解释失败不等于报告失败；冻结报告仍保持原版本。"
                : "无网络调用，不产生事实或审批副作用。"}
          </Notice>
          <label htmlFor="explanation-question">针对本报告提问</label>
          <textarea
            id="explanation-question"
            disabled
            placeholder="为什么需要单独确认未知在途？"
          />
          <Disabled
            control="B32"
            reason="报告解释传输合同待独审；无动态查数或写操作。"
          >
            发送报告问题
          </Disabled>
        </>
      )}
      {panel === "reanalysis" && (
        <>
          <Card title="当前冻结版本">
            <p>report v{view.version} · 原计划与审批事实不变。</p>
          </Card>
          <Card title="版本与重新授权影响">
            <p>
              新分析需新的不可变计划与审批。旧批准、未知在途确认与 execution
              不能继承；执行中/结果未知时先核实原请求。
            </p>
          </Card>
          <Disabled
            control="B36"
            reason="BC03 重算/重新发起协议尚未批准，保留禁用。"
          >
            重新分析
          </Disabled>
        </>
      )}
      {panel === "account" && (
        <>
          <p>
            {view.name} · {view.role} · 固定服务端 Mock 样例
          </p>
          <p>
            账号菜单不支持角色切换。正式身份与逐角色 scope
            必须由服务端会话取得。
          </p>
          <a className="button" data-control="B12" href="/login">
            返回登录壳
          </a>
          <small>未建立真实会话，因此此操作仅导航。</small>
        </>
      )}
      {panel === "receipt" && (
        <>
          <Notice
            title={
              view.state === "unknown"
                ? "审批结果未知 · 先核实"
                : view.state === "conflict"
                  ? "决定冲突 · 读取原决定"
                  : view.state === "duplicate"
                    ? "重复请求 · 查看既有决定"
                    : "审批仍待处理（Mock）"
            }
          >
            批准记录、内部项创建与同步投影是独立事实。unknown
            不能猜测成功，不换键改 payload 重发。
          </Notice>
          <p>固定 Mock 记录；此回读未向服务器发出请求。</p>
        </>
      )}
    </Modal>
  );
}
