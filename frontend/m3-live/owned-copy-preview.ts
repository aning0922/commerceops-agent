import { validCreate } from "../lib/p6-copy-client";
import type { CreateCopy } from "../lib/p6-copy-client";
import type { Seed } from "./owned-m3-input";

// A preview is not authority: every source and reviewer field must equal the private owned seed.
export function validOwnedCopyPreview(value: unknown, expected: Seed["copy"]): value is { kind: "create"; input: CreateCopy } {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const wrapper = value as { kind?: unknown; input?: unknown };
  if (Object.keys(wrapper).sort().join(",") !== "input,kind" || wrapper.kind !== "create" || !wrapper.input || typeof wrapper.input !== "object" || Array.isArray(wrapper.input)) return false;
  const input = wrapper.input as CreateCopy;
  return input.schema_version === "p6-copy-web-v1" && validCreate(input) && input.shop_id === expected.shop_id &&
    input.registry_id === expected.registry_id && input.registry_digest === expected.registry_digest &&
    input.product_source_id === expected.product_source_id && input.query_ref === expected.query_ref && input.reviewer_id === expected.reviewer_id;
}
