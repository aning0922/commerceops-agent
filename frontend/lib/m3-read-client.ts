import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import schema from "./p6-daily-s3-read-schema.generated.json" with { type: "json" };
import type { DailyRead } from "./m3-types.generated";
type FetchTransport = (url: URL, init: RequestInit) => Promise<Response>;
type DailyFailureCode = "INVALID_REQUEST" | "SERVICE_UNAVAILABLE" | "SESSION_INVALID" | "ACCESS_DENIED" | "RESOURCE_NOT_FOUND" | "INVALID_RESPONSE";
const messages: Record<DailyFailureCode, string> = {
  INVALID_REQUEST: "日报地址无效。", SERVICE_UNAVAILABLE: "服务暂时不可用，请重读当前记录。",
  SESSION_INVALID: "会话已过期或授权已变更，请重新登录。", ACCESS_DENIED: "当前身份无权访问。",
  RESOURCE_NOT_FOUND: "页面不可访问或当前身份没有权限。", INVALID_RESPONSE: "暂时无法安全读取日报。",
};
export class DailyFailure extends Error {
  constructor(readonly code: DailyFailureCode, readonly status: number | null = null) {
    super(messages[code]);
    this.name = "DailyFailure";
  }
}

const ajv = new Ajv2020({ strict: true, coerceTypes: false, useDefaults: false, removeAdditional: false });
addFormats(ajv);
const validate = ajv.compile(schema);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const safeNumbers = (value: unknown): boolean =>
  typeof value === "number" ? Number.isSafeInteger(value) :
  Array.isArray(value) ? value.every(safeNumbers) :
  value !== null && typeof value === "object" ? Object.values(value).every(safeNumbers) : true;
const displayMoney = (value: string | { numerator: string; denominator: string }, currency: string): string => {
  const digits = currency === "JPY" ? 0 : 2;
  let numerator: bigint, denominator: bigint;
  if (typeof value === "string") {
    const sign = value.startsWith("-") ? -1n : 1n;
    const [whole, fraction = ""] = value.replace("-", "").split(".");
    denominator = 10n ** BigInt(fraction.length);
    numerator = sign * (BigInt(whole) * denominator + BigInt(fraction || "0"));
  } else { numerator = BigInt(value.numerator); denominator = BigInt(value.denominator); }
  const scale = 10n ** BigInt(digits);
  const absolute = numerator < 0n ? -numerator : numerator;
  let quotient = absolute * scale / denominator;
  const remainder = absolute * scale % denominator;
  if (remainder * 2n > denominator || (remainder * 2n === denominator && quotient % 2n === 1n)) quotient++;
  const sign = numerator < 0n && quotient !== 0n ? "-" : "";
  return digits === 0 ? sign + quotient : `${sign}${quotient / scale}.${String(quotient % scale).padStart(digits, "0")}`;
};

export function validDailyRead(value: unknown, taskId: string): value is DailyRead {
  if (!uuid.test(taskId) || !safeNumbers(value) || !validate(value)) return false;
  const read = value as unknown as DailyRead;
  const daily = read.daily;
  if (daily.task_id.toLowerCase() !== taskId.toLowerCase() ||
      Date.parse(daily.updated_at) > Date.parse(read.server_time)) return false;
  const report = daily.report;
  if (!report) return daily.question_creation_enabled === false;
  try { new Intl.DateTimeFormat("zh-CN", { timeZone: report.source.timezone }); }
  catch { return false; }
  if (Date.parse(report.collected_at) > Date.parse(read.server_time) ||
      Date.parse(report.collection_started_at) > Date.parse(report.collected_at) ||
      Date.parse(report.window.start) >= Date.parse(report.window.end) ||
      new Set(report.display.map((x) => x.metric_key)).size !== report.display.length ||
      new Set(report.findings.map((x) => x.finding_id)).size !== report.findings.length) return false;
  if (report.complete) {
    if (report.quality_flags.length || report.findings.some((x) => x.severity === "blocking")) return false;
    const expected = Object.keys(report.metrics).filter((key) => key !== "status_counts" && key !== "average_reason");
    if (report.display.length !== expected.length ||
        report.display.some((item) => !expected.includes(item.metric_key))) return false;
    for (const item of report.display) {
      const raw = report.metrics[item.metric_key];
      if (item.metric_key === "average_paid_order_value") {
        if ((raw === null) !== (item.value === null)) return false;
        if (raw !== null && (typeof raw !== "object" || item.value !== displayMoney(raw, report.source.currency))) return false;
      } else if (item.metric_key.includes("count")) {
        if (item.value !== String(raw)) return false;
      } else if (item.metric_key === "orders_without_payment_timestamp") {
        if (item.value !== String(raw)) return false;
      } else if (item.value !== displayMoney(String(raw), report.source.currency)) return false;
    }
  } else if (!report.findings.some((x) => x.severity === "blocking")) return false;
  return true;
}

// The server owns authorization and seal validation. This client accepts only one reviewed GET.
export async function readDaily(
  origin: string,
  taskId: string,
  invalidate: () => void,
  transport: FetchTransport = (url, init) => fetch(url, init),
  isCurrent: () => boolean = () => true,
): Promise<DailyRead> {
  if (!uuid.test(taskId)) throw new DailyFailure("INVALID_REQUEST");
  const base = new URL(origin);
  const url = new URL(`/api/v1/daily-reports/${encodeURIComponent(taskId)}`, base);
  let response: Response;
  try {
    response = await transport(url, { method: "GET", credentials: "include", cache: "no-store", redirect: "error" });
  } catch {
    throw new DailyFailure("SERVICE_UNAVAILABLE");
  }
  if (response.status === 401 || response.status === 403) {
    if (isCurrent()) invalidate();
    throw new DailyFailure(response.status === 401 ? "SESSION_INVALID" : "ACCESS_DENIED", response.status);
  }
  if (response.status === 404) throw new DailyFailure("RESOURCE_NOT_FOUND", 404);
  if (response.status >= 500) throw new DailyFailure("SERVICE_UNAVAILABLE", response.status);
  if (!response.ok || !response.headers.get("Content-Type")?.toLowerCase().match(/^application\/json(?:\s*;|$)/))
    throw new DailyFailure("INVALID_RESPONSE", response.status);
  let value: unknown;
  try { value = await response.json(); } catch { throw new DailyFailure("INVALID_RESPONSE", response.status); }
  if (!validDailyRead(value, taskId)) throw new DailyFailure("INVALID_RESPONSE", response.status);
  return value;
}
