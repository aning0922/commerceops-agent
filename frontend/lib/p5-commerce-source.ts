// UI eligibility is not authorization: the server rechecks the current binding on every write.
import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import schema from "./p5-read-schema.generated.json";
import type { DTO } from "./p3-present";
export type WooParameters = DTO["P5WooCreateParameters"];
export type SourceGate =
  | { allowed: true; kind: "mock"; version: null }
  | { allowed: true; kind: "woocommerce_test"; version: string }
  | { allowed: false; kind: "mock" | "woocommerce_test" | "unknown"; reason: string };
export function validCommerceCapability(config: DTO["DeploymentConfig"]): boolean {
  const source = config.commerce_source;
  if (!source) return true; // A scoped confirmed Mock response is checked separately at creation.
  return source.schema_version === "p5-commerce-source-v1" &&
    source.source_kind === config.source_mode &&
    (source.source_kind !== "mock" || source.source_config_version === null) &&
    (source.source_kind !== "woocommerce_test" || !source.creation_enabled ||
      (typeof source.source_config_version === "string" &&
       source.source_config_version.trim().length >= 1 && [...source.source_config_version].length <= 256));
}
export function commerceCreationGate(
  read: DTO["ConfigRead"] | null, shop: string, operatorShops: readonly string[],
): SourceGate {
  if (!operatorShops.includes(shop)) return { allowed: false, kind: "unknown", reason: "当前身份没有该店铺的operator创建资格。" };
  if (!read || read.shop_id !== shop) return { allowed: false, kind: "unknown", reason: "店铺来源尚未核实；不会猜测Mock或开放创建。" };
  const config = read.config, source = config.commerce_source;
  if (!validCommerceCapability(config)) return { allowed: false, kind: "unknown", reason: "来源能力与店铺配置不一致，创建已关闭。" };
  if (source) {
    if (!source.creation_enabled) return { allowed: false, kind: source.source_kind, reason: "当前店铺来源未启用创建；不会回退其他来源。" };
    if (source.source_kind === "woocommerce_test" && source.source_config_version)
      return { allowed: true, kind: "woocommerce_test", version: source.source_config_version };
    if (source.source_kind === "mock" && source.source_config_version === null)
      return { allowed: true, kind: "mock", version: null };
  } else if (config.source_mode === "mock") {
    return { allowed: true, kind: "mock", version: null }; // Explicit legacy Mock, this selected shop only.
  }
  return { allowed: false, kind: config.source_mode === "woocommerce_test" ? "woocommerce_test" : "unknown", reason: "来源能力缺失或无效，不能创建；不会回退Mock。" };
}
const ajv = new Ajv2020({ strict: false, coerceTypes: false, useDefaults: false, removeAdditional: false });
addFormats(ajv);
const create = schema.operations.find((operation) => operation.method === "POST" && operation.path === "/api/v1/tasks")!;
const validate = ajv.compile({ ...create.input, components: schema.components });
export const validWooCreateInput = (input: unknown): boolean =>
  input !== null && typeof input === "object" && "parameters" in input &&
  input.parameters !== null && typeof input.parameters === "object" &&
  "source_mode" in input.parameters && input.parameters.source_mode === "woocommerce_test" &&
  validate(input) === true;
