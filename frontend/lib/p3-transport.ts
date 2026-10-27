// Offline-tested transport for the reviewed p3-web-v1 contract. Not imported by B01 UI.
// The API enforces identity, role-bound scopes, eligibility, versions and idempotency.
import type { components } from "./p5-types.generated";
import type { N01Input, N01Response, WooN01Input, WooN01Response, AnyN01Input, AnyN01Response } from "./p4-n01";
import { validN01Input, validN01Response, n01MatchesInput } from "./p4-n01";
import { validWooCreateInput } from "./p5-commerce-source";
type DTO = components["schemas"];
export type P3FailureCode =
  | DTO["ErrorDetail"]["code"]
  | "INVALID_RESPONSE"
  | "WRITE_RESULT_UNKNOWN"
  | "CSRF_NOT_READY"
  | "COMMERCE_SOURCE_UNAVAILABLE";
const messages: Partial<Record<P3FailureCode, string>> = {
  SESSION_INVALID: "会话已过期或授权已变更，请重新登录。",
  COMMERCE_SOURCE_UNAVAILABLE: "当前店铺来源不可用，请核实来源配置；不会回退Mock或重发请求。",
  LOGIN_FAILED: "登录失败，请核对账号与密码。",
  ACCESS_DENIED: "当前身份无权访问。",
  RESOURCE_NOT_FOUND: "页面不可访问或当前身份没有权限。",
  CSRF_INVALID: "会话校验失败，请重新读取当前会话。",
  ORIGIN_DENIED: "当前入口无法执行此操作。",
  DECISION_CONFLICT: "决定发生冲突，请核实已有审批记录。",
  IDEMPOTENCY_CONFLICT: "请求内容与原请求不一致，请核实原回执。",
  APPROVAL_EXPIRED: "审批已过期，请查看冻结版本记录。",
  WRITE_RESULT_UNKNOWN: "提交结果待核实，请保留原请求并读取原回执。",
  CSRF_NOT_READY: "请先建立当前服务端会话。",
  INVALID_RESPONSE: "暂时无法安全读取服务响应。",
  SERVICE_UNAVAILABLE: "服务暂时不可用，请核实已有请求结果。",
  NOT_READY: "当前记录尚未就绪，请读取当前状态；不会自动提交业务请求。",
  PLAN_CHANGED: "复核后计划已改变，请读取并核对当前版本；旧意见不授权新版本。",
  APPROVAL_SUPERSEDED: "此审批已被新版本替代，请查看当前冻结版本。",
  ITEM_VERSION_CONFLICT:
    "工作项版本已改变，请读取当前项及原回执；不会自动换键。",
  ITEM_STATE_CONFLICT: "工作项已进入终态或当前不可处理，请核实当前项及原回执。",
  ASSUMPTION_ACK_REQUIRED: "本版本需要明确确认完整未知假设，普通批准不能替代。",
  ASSUMPTION_SET_MISMATCH: "确认集合与当前版本不一致，请重新核对完整假设。",
  DATA_INCOMPLETE: "当前数据不完整，不能据此准备执行。",
  SCOPE_REQUIRED: "请明确受支持的范围；系统不会截断清单或代选。",
  RATE_LIMITED: "当前请求受限，请稍后核实已有记录，不重复创建任务。",
  INVALID_REQUEST: "请求未通过校验，请核对输入或当前记录。",
};
const knownErrorCodes = new Set<string>([
  "COMMERCE_SOURCE_UNAVAILABLE",
  "INVALID_CURSOR",
  "INVALID_FILTER",
  "INVALID_JSON",
  "SESSION_INVALID",
  "LOGIN_FAILED",
  "ACCESS_DENIED",
  "CSRF_INVALID",
  "ORIGIN_DENIED",
  "RESOURCE_NOT_FOUND",
  "PLAN_CHANGED",
  "APPROVAL_SUPERSEDED",
  "DECISION_CONFLICT",
  "IDEMPOTENCY_CONFLICT",
  "ITEM_STATE_CONFLICT",
  "ITEM_VERSION_CONFLICT",
  "ASSUMPTION_ACK_REQUIRED",
  "ASSUMPTION_SET_MISMATCH",
  "DATA_INCOMPLETE",
  "SCOPE_REQUIRED",
  "NOT_READY",
  "APPROVAL_EXPIRED",
  "UNSUPPORTED_MEDIA_TYPE",
  "INVALID_REQUEST",
  "RATE_LIMITED",
  "SERVICE_UNAVAILABLE",
]);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const csrfValue = /^[A-Za-z0-9_-]{43}$/;
const utcTime = (value: unknown) =>
  typeof value === "string" &&
  /(Z|[+]00:00)$/.test(value) &&
  Number.isFinite(Date.parse(value));
export class P3Failure extends Error {
  readonly code: P3FailureCode;
  readonly status: number | null;
  readonly traceId: string | null;
  constructor(
    code: P3FailureCode,
    status: number | null = null,
    traceId: string | null = null,
  ) {
    super(messages[code] ?? "操作暂未完成，请查看当前记录。");
    this.name = "P3Failure";
    this.code = code;
    this.status = status;
    this.traceId = traceId;
  }
}
export type FetchTransport = (
  input: URL,
  init: RequestInit,
) => Promise<Response>;
const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const fields = (
  input: object,
  names: readonly string[],
): Record<string, unknown> =>
  Object.fromEntries(
    names.map((name) => [name, (input as Record<string, unknown>)[name]]),
  );
const segment = (id: string) => {
  if (!uuid.test(id)) throw new P3Failure("INVALID_REQUEST");
  return encodeURIComponent(id);
};
const protocol = "p3-web-v1" as const;
export type Operation = "create_task" | "decision" | "resolve";
// Private closure keeps original bytes and nonce out of public serialization/logging.
export class PreparedWrite<T> {
  readonly requestKey: string;
  readonly operation: Operation;
  #send: () => Promise<T>;
  constructor(
    requestKey: string,
    operation: Operation,
    send: () => Promise<T>,
  ) {
    this.requestKey = requestKey;
    this.operation = operation;
    this.#send = send;
  }
  async send(): Promise<T> {
    return this.#send();
  }
}
export class P3Client {
  #origin: URL;
  #transport: FetchTransport;
  #csrf: string | null = null;
  #principal: string | null = null;
  #invalidate: () => void;
  #verify:
    | ((method: string, path: string, status: number, data: unknown) => boolean)
    | undefined;
  constructor(options: {
    origin: string;
    transport: FetchTransport;
    localHttp?: boolean;
    onSessionInvalidated?: () => void;
    verifyResponse?: (
      method: string,
      path: string,
      status: number,
      data: unknown,
    ) => boolean;
  }) {
    const base = new URL(options.origin);
    if (
      base.username ||
      base.password ||
      base.pathname !== "/" ||
      base.search ||
      base.hash
    )
      throw new Error("Use an explicit API origin without credentials or path");
    const loopback = ["127.0.0.1", "localhost", "[::1]"].includes(
      base.hostname,
    );
    if (
      base.protocol !== "https:" &&
      !(base.protocol === "http:" && loopback && options.localHttp === true)
    )
      throw new Error("Use HTTPS or explicit local_http loopback");
    this.#origin = base;
    this.#transport = options.transport;
    this.#invalidate = options.onSessionInvalidated ?? (() => {});
    this.#verify = options.verifyResponse;
  }
  clearSession(): void {
    this.#csrf = null;
    this.#principal = null;
    this.#invalidate();
  }
  async #request<T>(
    method: "GET" | "POST",
    path: string,
    query: Record<string, string | number | undefined> = {},
    body?: string,
    write = false,
  ): Promise<T> {
    const url = new URL(path, this.#origin);
    for (const [key, value] of Object.entries(query))
      if (value !== undefined) url.searchParams.set(key, String(value));
    const headers = new Headers();
    if (method === "POST") {
      if (!this.#csrf) throw new P3Failure("CSRF_NOT_READY");
      headers.set("Content-Type", "application/json");
      headers.set("X-CSRF-Token", this.#csrf);
    }
    let response: Response;
    try {
      response = await this.#transport(url, {
        method,
        headers,
        credentials: "include",
        cache: "no-store",
        redirect: "error",
        ...(body === undefined ? {} : { body }),
      });
    } catch {
      throw new P3Failure(
        write ? "WRITE_RESULT_UNKNOWN" : "SERVICE_UNAVAILABLE",
      );
    }
    if (response.status === 401 || response.status === 403) this.clearSession();
    let data: unknown;
    try {
      if (
        !response.headers
          .get("Content-Type")
          ?.toLowerCase()
          .match(/^application\/json(?:\s*;|$)/)
      )
        throw new Error();
      data = await response.json();
    } catch {
      throw new P3Failure(
        write && (response.ok || response.status >= 500)
          ? "WRITE_RESULT_UNKNOWN"
          : "INVALID_RESPONSE",
        response.status,
      );
    }
    if (
      !object(data) ||
      data.schema_version !== protocol ||
      typeof data.trace_id !== "string" ||
      !uuid.test(data.trace_id) ||
      !(
        utcTime(data.server_time) ||
        (!response.ok && data.server_time === null)
      )
    )
      throw new P3Failure(
        write && (response.ok || response.status >= 500)
          ? "WRITE_RESULT_UNKNOWN"
          : "INVALID_RESPONSE",
        response.status,
      );
    if (this.#verify && !this.#verify(method, path, response.status, data))
      throw new P3Failure(
        write ? "WRITE_RESULT_UNKNOWN" : "INVALID_RESPONSE",
        response.status,
      );
    if (!response.ok) {
      if (write && response.status >= 500)
        throw new P3Failure(
          "WRITE_RESULT_UNKNOWN",
          response.status,
          data.trace_id,
        );
      const code =
        object(data.error) &&
        typeof data.error.code === "string" &&
        knownErrorCodes.has(data.error.code)
          ? (data.error.code as P3FailureCode)
          : "INVALID_RESPONSE";
      // Never surface server raw safe_message/input/body: local fixed messages only.
      throw new P3Failure(code, response.status, data.trace_id);
    }
    if (
      data.identity_mode !== "session" &&
      !(
        path === "/api/v1/auth/csrf" &&
        data.identity_mode === "anonymous_bootstrap"
      )
    )
      throw new P3Failure(
        write ? "WRITE_RESULT_UNKNOWN" : "INVALID_RESPONSE",
        response.status,
      );
    return data as T;
  }
  #acceptSession(data: DTO["SessionRead"]): DTO["SessionRead"] {
    if (
      typeof data.csrf_token !== "string" ||
      !csrfValue.test(data.csrf_token) ||
      !object(data.principal) ||
      typeof data.principal.principal_id !== "string" ||
      !uuid.test(data.principal.principal_id)
    ) {
      this.clearSession();
      throw new P3Failure("INVALID_RESPONSE");
    }
    this.#csrf = data.csrf_token;
    this.#principal = data.principal.principal_id;
    return data;
  }
  async bootstrap(): Promise<DTO["CsrfBootstrap"]> {
    const data = await this.#request<DTO["CsrfBootstrap"]>(
      "GET",
      "/api/v1/auth/csrf",
    );
    if (typeof data.csrf_token !== "string" || !csrfValue.test(data.csrf_token))
      throw new P3Failure("INVALID_RESPONSE");
    if (data.identity_mode === "anonymous_bootstrap") this.clearSession();
    this.#csrf = data.csrf_token;
    return data;
  }
  async login(input: DTO["LoginInput"]): Promise<DTO["SessionRead"]> {
    return this.#acceptSession(
      await this.#request(
        "POST",
        "/api/v1/auth/login",
        {},
        JSON.stringify(fields(input, ["schema_version", "login", "password"])),
      ),
    );
  }
  async session(): Promise<DTO["SessionRead"]> {
    return this.#acceptSession(
      await this.#request("GET", "/api/v1/auth/session"),
    );
  }
  async preflight(input: N01Input): Promise<N01Response>;
  async preflight(input: WooN01Input): Promise<WooN01Response>;
  async preflight(input: AnyN01Input): Promise<AnyN01Response>;
  async preflight(input: AnyN01Input): Promise<AnyN01Response> {
    if (!this.#principal || !this.#csrf) throw new P3Failure("CSRF_NOT_READY");
    if (!validN01Input(input)) throw new P3Failure("INVALID_REQUEST");
    const principal = this.#principal;
    const read = await this.#request<AnyN01Response>(
      "POST", "/api/v1/tasks/preflight", {},
      JSON.stringify(fields(input, "source_mode" in input
        ? ["schema_version", "source_mode", "shop_id", "source_config_version", "text"]
        : ["schema_version", "shop_id", "fixture_case", "text"])),
    );
    if (this.#principal !== principal || !validN01Response(200, read) || !n01MatchesInput(read, input))
      throw new P3Failure("INVALID_RESPONSE");
    return read;
  }
  async logout(): Promise<DTO["LogoutReceipt"]> {
    try {
      return await this.#request(
        "POST",
        "/api/v1/auth/logout",
        {},
        JSON.stringify({ schema_version: protocol }),
      );
    } finally {
      this.clearSession();
    }
  }
  #prepare<T>(
    operation: Operation,
    path: string,
    input: { readonly request_key: string },
    body: object,
  ): PreparedWrite<T> {
    if (!this.#principal || !this.#csrf) throw new P3Failure("CSRF_NOT_READY");
    const principal = this.#principal;
    const original = JSON.stringify(body);
    return new PreparedWrite(input.request_key, operation, () => {
      if (principal !== this.#principal) throw new P3Failure("SESSION_INVALID");
      return this.#request<T>("POST", path, {}, original, true);
    });
  }
  prepareTask(
    input: DTO["CreateTaskInput"],
  ): PreparedWrite<DTO["CreateTaskReceipt"]> {
    if (input.mode === "new_cycle" && input.parameters.source_mode !== "mock" &&
        (input.parameters.source_mode !== "woocommerce_test" || !validWooCreateInput(input)))
      throw new P3Failure("INVALID_REQUEST");
    const body =
      input.mode === "from_report"
        ? fields(input, [
            "schema_version",
            "mode",
            "request_key",
            "source_task_id",
            "source_report_id",
            "snapshot_id",
            "facts_hash",
          ])
        : {
            ...fields(input, [
              "schema_version",
              "mode",
              "request_key",
              "shop_id",
            ]),
            parameters: fields(input.parameters,
              input.parameters.source_mode === "woocommerce_test"
                ? ["source_mode", "source_config_version", "L", "R", "S"]
                : ["source_mode", "dataset_version", "fixture_case", "L", "R", "S"]),
          };
    return this.#prepare("create_task", "/api/v1/tasks", input, body);
  }
  prepareDecision(
    input: DTO["DecisionInput"],
  ): PreparedWrite<DTO["DecisionReceipt"]> {
    return this.#prepare(
      "decision",
      `/api/v1/approvals/${segment(input.approval_id)}/decision`,
      input,
      fields(input, [
        "schema_version",
        "request_key",
        "approval_id",
        "plan_id",
        "plan_version",
        "plan_hash",
        "action",
        "acknowledged_assumption_keys",
        "nonce",
      ]),
    );
  }
  prepareResolve(
    itemId: string,
    input: DTO["ResolveInput"],
  ): PreparedWrite<DTO["ResolveReceipt"]> {
    return this.#prepare(
      "resolve",
      `/api/v1/replenishment-items/${segment(itemId)}/resolve`,
      input,
      fields(input, [
        "schema_version",
        "request_key",
        "action",
        "reason",
        "expected_version",
      ]),
    );
  }
  config(shopId: string): Promise<DTO["ConfigRead"]> {
    return this.#request("GET", "/api/v1/config", { shop_id: shopId });
  }
  operations(): Promise<DTO["OperationsRead"]> {
    return this.#request("GET", "/api/v1/admin/operations");
  }
  tasks(
    query: {
      limit?: number;
      cursor?: string;
      state?: DTO["TaskSummary"]["state"];
    } = {},
  ): Promise<DTO["TaskList"]> {
    return this.#request("GET", "/api/v1/tasks", query);
  }
  task(id: string): Promise<DTO["TaskRead"]> {
    return this.#request("GET", `/api/v1/tasks/${segment(id)}`);
  }
  report(id: string, reportId?: string): Promise<DTO["ReportRead"]> {
    return this.#request("GET", `/api/v1/tasks/${segment(id)}/report`, {
      report_id: reportId,
    });
  }
  explanation(id: string, reportId: string): Promise<DTO["ExplanationRead"]> {
    return this.#request("GET", `/api/v1/tasks/${segment(id)}/explanation`, {
      report_id: reportId,
    });
  }
  plans(
    id: string,
    query: { limit?: number; cursor?: string } = {},
  ): Promise<DTO["PlanList"]> {
    return this.#request("GET", `/api/v1/tasks/${segment(id)}/plans`, query);
  }
  plan(id: string, version: number): Promise<DTO["PlanRead"]> {
    if (!Number.isSafeInteger(version) || version < 1)
      throw new P3Failure("INVALID_REQUEST");
    return this.#request(
      "GET",
      `/api/v1/tasks/${segment(id)}/plans/${version}`,
    );
  }
  events(
    id: string,
    query: { limit?: number; cursor?: string } = {},
  ): Promise<DTO["EventsRead"]> {
    return this.#request("GET", `/api/v1/tasks/${segment(id)}/events`, query);
  }
  execution(id: string): Promise<DTO["ExecutionRead"]> {
    return this.#request("GET", `/api/v1/tasks/${segment(id)}/execution`);
  }
  approvals(
    query: {
      limit?: number;
      cursor?: string;
      view?: "visible" | "mine" | "history";
      state?: DTO["ApprovalSummary"]["status"];
    } = {},
  ): Promise<DTO["ApprovalList"]> {
    return this.#request("GET", "/api/v1/approvals", query);
  }
  approval(id: string): Promise<DTO["ApprovalRead"]> {
    return this.#request("GET", `/api/v1/approvals/${segment(id)}`);
  }
  items(
    query: {
      limit?: number;
      cursor?: string;
      state?: DTO["ItemList"]["items"][number]["state"];
    } = {},
  ): Promise<DTO["ItemList"]> {
    return this.#request("GET", "/api/v1/replenishment-items", query);
  }
  item(id: string): Promise<DTO["ItemRead"]> {
    return this.#request("GET", `/api/v1/replenishment-items/${segment(id)}`);
  }
  requestReceipt(
    key: string,
    operation: Operation,
  ): Promise<DTO["RequestRead"]> {
    return this.#request("GET", `/api/v1/requests/${segment(key)}`, {
      operation,
    });
  }
}
