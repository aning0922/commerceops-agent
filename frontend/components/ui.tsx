"use client";
import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import { stateText, statusView } from "../lib/p3-present";
export const labels = stateText;
export function Status({ value }: { value: string }) {
  const view = statusView(value);
  return (
    <>
      <span className={`status ${view.tone}`}>{view.text}</span>
      {!view.known && <small className="status-raw">原状态：{value}</small>}
    </>
  );
}
export function Notice({
  title,
  children,
  tone = "warning",
}: {
  title: string;
  children?: ReactNode;
  tone?: string;
}) {
  return (
    <div
      className={`notice ${tone}`}
      role={tone === "danger" ? "alert" : "status"}
    >
      <strong>{title}</strong>
      {children && <div>{children}</div>}
    </div>
  );
}
export function Card({
  title,
  children,
}: {
  title?: string;
  children: ReactNode;
}) {
  return (
    <section className="card">
      {title && <h2>{title}</h2>}
      {children}
    </section>
  );
}
export function Disabled({
  control,
  children,
  reason,
}: {
  control: string;
  children: ReactNode;
  reason: string;
}) {
  const id = useId();
  return (
    <div className="disabled-control">
      <button data-control={control} disabled aria-describedby={id}>
        {children}
      </button>
      <small id={id}>{reason}</small>
    </div>
  );
}
export function Modal({
  title,
  children,
  close,
  drawer = false,
  closeControl = "B22",
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  drawer?: boolean;
  closeControl?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const heading = useId();
  useEffect(() => {
    const dialog = ref.current;
    const trigger = document.activeElement as HTMLElement | null;
    dialog?.showModal();
    return () => {
      dialog?.close();
      trigger?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={drawer ? "drawer" : "modal"}
      aria-labelledby={heading}
      onKeyDown={(e) => {
        if (e.key !== "Tab") return;
        const nodes = Array.from(
          ref.current?.querySelectorAll<HTMLElement>(
            'button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), summary, [tabindex="0"]',
          ) ?? [],
        ).filter((x) => x.getClientRects().length > 0);
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (
          (e.shiftKey && document.activeElement === first) ||
          (!e.shiftKey && document.activeElement === last)
        ) {
          e.preventDefault();
          (e.shiftKey ? last : first)?.focus();
        }
      }}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <div className="dialog-head">
        <h2 id={heading}>{title}</h2>
        <button
          data-control={closeControl}
          aria-label={`关闭${title}`}
          onClick={close}
          autoFocus
        >
          关闭
        </button>
      </div>
      <div className="dialog-content">{children}</div>
    </dialog>
  );
}
export function ReadState({
  state,
  reload,
}: {
  state: string;
  reload: () => void;
}) {
  return (
    <Card>
      <h2>
        {state === "loading"
          ? "正在读取"
          : state === "empty"
            ? "暂无记录"
            : "暂时无法读取"}
      </h2>
      <p>
        {state === "loading"
          ? "Mock 加载样例；等待不会产生业务操作。"
          : state === "empty"
            ? "此 Mock 范围暂无记录。"
            : "读取失败不等于分析或审批失败；请核实已有结果。"}
      </p>
      <button data-control="B42" onClick={reload}>
        重读当前区域（Mock）
      </button>
    </Card>
  );
}
