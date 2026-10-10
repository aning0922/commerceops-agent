import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import schema from "./p3-read-schema.generated.json";
import { P3Client } from "./p3-transport";
import type { FetchTransport } from "./p3-transport";
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
export const verifyReadResponse = (
  method: string,
  path: string,
  status: number,
  value: unknown,
): boolean => {
  const operation = operations.find(
    (x) => x.method === method && x.match.test(path),
  );
  return (
    safeNumbers(value) && operation?.validators.get(status)?.(value) === true
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
  | "prepareDecision"
  | "execution"
  | "items"
  | "item"
  | "prepareResolve"
>;
export function readTransport(transport: FetchTransport): FetchTransport {
  return (url, init) => {
    if (
      !operations.some(
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
