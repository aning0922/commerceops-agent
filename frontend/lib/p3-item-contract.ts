// Pure B04 preparation against the existing frozen schemas. No runtime operation activation.
import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import schemas from "./p3-read-schema.generated.json";
import type { DTO } from "./p3-present";
const ajv = new Ajv2020({
  strict: false,
  coerceTypes: false,
  useDefaults: false,
  removeAdditional: false,
});
addFormats(ajv);
ajv.addKeyword({
  keyword: "ge",
  type: "number",
  schemaType: "number",
  validate: (bound: number, value: number) => value >= bound,
});
const names = [
  "ItemRead",
  "ItemList",
  "ExecutionRead",
  "ResolveReceipt",
  "RequestRead",
  "SessionRead",
  "Error",
] as const;
type Name = (typeof names)[number];
const validators = new Map(
  names.map((name) => [
    name,
    ajv.compile({
      $ref: `#/components/schemas/${name}`,
      components: schemas.components,
    }),
  ]),
);
const safeNumbers = (value: unknown): boolean =>
  typeof value === "number"
    ? Number.isSafeInteger(value)
    : Array.isArray(value)
      ? value.every(safeNumbers)
      : value !== null && typeof value === "object"
        ? Object.values(value).every(safeNumbers)
        : true;
export function validItemDTO(name: Name, value: unknown): boolean {
  return safeNumbers(value) && validators.get(name)?.(value) === true;
}
export function normalizedReason(raw: string): string | null {
  // Python 3.12 str.strip whitespace, fixed for T6; FEFF is preserved.
  // No NFC/NFKC or internal whitespace normalization.
  const reason = raw
    .replace(
      /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/u,
      "",
    )
    .replace(
      /[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/u,
      "",
    );
  return reason.length > 0 && Array.from(reason).length <= 1000 ? reason : null;
}
export function itemConsistent(read: DTO["ItemRead"]): boolean {
  const r = read.resolution,
    item = read.item;
  return (
    validItemDTO("ItemRead", read) &&
    (item.state === "open"
      ? r === null
      : r !== null &&
        r.after_version === item.version &&
        r.after_version === r.before_version + 1 &&
        (r.action === "complete"
          ? item.state === "completed"
          : item.state === "closed"))
  );
}
export function canResolve(read: DTO["ItemRead"]): boolean {
  return (
    itemConsistent(read) &&
    read.can_resolve &&
    read.item.state === "open" &&
    !read.disabled_reasons.length
  );
}
export function resolveReceiptBound(
  read: DTO["ItemRead"],
  input: DTO["ResolveInput"],
  receipt: DTO["ResolveReceipt"],
  original?: DTO["ResolveReceipt"],
): boolean {
  const item = receipt.item,
    r = receipt.resolution,
    before = read.item;
  const { request_key: expectedKey } = input;
  const { request_key: receiptKey } = receipt;
  const { request_key: resolutionKey } = r;
  const { stock_pool_key: originalPool, sku_key: originalSku } = before;
  const { stock_pool_key: returnedPool, sku_key: returnedSku } = item;
  return (
    validItemDTO("ResolveReceipt", receipt) &&
    receiptKey === expectedKey &&
    resolutionKey === expectedKey &&
    item.item_id === before.item_id &&
    item.shop_id === before.shop_id &&
    returnedSku === originalSku &&
    returnedPool === originalPool &&
    item.quantity === before.quantity &&
    r.action === input.action &&
    r.reason === input.reason &&
    r.before_version === input.expected_version &&
    r.after_version === input.expected_version + 1 &&
    item.version === r.after_version &&
    item.state === (input.action === "complete" ? "completed" : "closed") &&
    (!original ||
      (r.resolution_id === original.resolution.resolution_id &&
        r.resolved_by === original.resolution.resolved_by &&
        r.resolved_at === original.resolution.resolved_at &&
        r.resolution_payload_hash ===
          original.resolution.resolution_payload_hash))
  );
}
