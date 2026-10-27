import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import schema from "./p5-read-schema.generated.json";
import { P3Client } from "./p3-transport";
import type { FetchTransport } from "./p3-transport";
import { p4ReadFactsValid } from "./p4-read-facts";
import { validN01Response } from "./p4-n01";
import type { DTO } from "./p3-present";
const ajv = new Ajv2020({
  strict: false,
  allErrors: false,
  coerceTypes: false,
  useDefaults: false,
  removeAdditional: false,
});
addFormats(ajv);
// P2's frozen export uses ge metadata; enforce its bound without changing source schema.
ajv.addKeyword({
  keyword: "ge",
  type: "number",
  schemaType: "number",
  validate: (bound: number, value: number) => value >= bound,
});
ajv.addSchema({ $id: "p3-frozen-read", ...schema });
const operations = schema.operations.map((operation) => ({
  ...operation,
  match: new RegExp("^" + operation.path.replace(/\{[^}]+\}/g, "[^/]+") + "$"),
  validators: new Map(
    Object.entries(operation.responses).map(([status, response]) => [
      Number(status),
      ajv.compile({ ...response, components: schema.components }),
    ]),
  ),
}));
const safeNumbers = (value: unknown): boolean =>
  typeof value === "number"
    ? Number.isSafeInteger(value)
    : Array.isArray(value)
      ? value.every(safeNumbers)
      : value !== null && typeof value === "object"
        ? Object.values(value).every(safeNumbers)
        : true;
// JSON Schema does not export Pydantic's cross-field template validators.
const explanationReadValid = (
  read: DTO["ExplanationRead"],
  taskId: string,
): boolean => {
  if (read.task_id.toLowerCase() !== taskId.toLowerCase()) return false;
  const record = read.explanation;
  if (record.schema_version === "p204-read-v1") return true;
  if (record.schema_version !== "p4-p3-template-read-v1") return false;
  const result = record.result;
  const metadata = result.metadata;
  const bound = (refs: DTO["P2ExplanationExplanationRefs"]) =>
    refs.report_id === record.report_id && refs.snapshot_id === record.snapshot_id;
  return (
    record.analysis_only === true && record.execution_available === false &&
    record.identity_mode === "simulated" &&
    record.task_id === read.task_id && record.report_id === read.report_id &&
    result.narrative_mode === "template" && result.binding_mode === "caller_references" &&
    metadata.evidence_mode === "not_used" && metadata.stop_required === false &&
    [
      metadata.provider, metadata.requested_model, metadata.returned_model,
      metadata.request_id, metadata.usage, metadata.latency_ms,
      metadata.pricing_version, metadata.cost_estimate,
    ].every((value) => value === null) &&
    /(?:Z|[+]00:00)$/.test(record.created_at) &&
    ((record.source_kind === "p2_original" && record.observation_id === null) ||
      (record.source_kind === "p3_observation" && record.observation_id !== null &&
        record.snapshot_id === record.observation_id)) &&
    result.facts_hash === record.facts_hash && bound(result.reference_ids) &&
    new Set(result.lines.map((line) => line.sku_key)).size === result.lines.length &&
    result.lines.every((line) =>
      line.facts_hash === record.facts_hash && bound(line.reference_ids),
    )
  );
};
export const verifyReadResponse = (
  method: string,
  path: string,
  status: number,
  value: unknown,
): boolean => {
  if (method === "POST" && path === "/api/v1/tasks/preflight")
    return validN01Response(status, value);
  const operation = operations.find(
    (x) => x.method === method && x.match.test(path),
  );
  if (
    !safeNumbers(value) ||
    operation?.validators.get(status)?.(value) !== true
  )
    return false;
  return (
    status >= 400 ||
    (p4ReadFactsValid(operation.method, operation.path, value) &&
      (operation.path !== "/api/v1/tasks/{task_id}/explanation" ||
        explanationReadValid(value as DTO["ExplanationRead"], path.split("/")[4])))
  );
};
export type A01ReadClient = Pick<
  P3Client,
  | "bootstrap"
  | "login"
  | "session"
  | "logout"
  | "clearSession"
  | "config"
  | "operations"
  | "tasks"
  | "task"
  | "report"
  | "explanation"
  | "plans"
  | "plan"
  | "events"
  | "approvals"
  | "approval"
  | "requestReceipt"
  | "prepareTask"
  | "preflight"
  | "prepareDecision"
  | "execution"
  | "items"
  | "item"
  | "prepareResolve"
>;
export function readTransport(transport: FetchTransport): FetchTransport {
  return (url, init) => {
    if (
      !(init.method === "POST" && url.pathname === "/api/v1/tasks/preflight") && !operations.some(
        (operation) =>
          operation.method === init.method &&
          operation.match.test(url.pathname),
      )
    )
      return Promise.reject(
        new Error("Operation outside reviewed p3-web-v1 contract"),
      );
    return transport(url, init);
  };
}
export function createReadClient(
  origin: string,
  localHttp: boolean,
  invalidate: () => void,
): A01ReadClient {
  return new P3Client({
    origin,
    localHttp,
    transport: readTransport((url, init) => fetch(url, init)),
    verifyResponse: verifyReadResponse,
    onSessionInvalidated: invalidate,
  });
}
