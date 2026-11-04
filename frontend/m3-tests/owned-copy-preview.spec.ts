import { test, expect } from "@playwright/test";
import { validOwnedCopyPreview } from "../m3-live/owned-copy-preview";
import { BoundedNetwork } from "../m3-live/bounded-network";
const id = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12,"0")}`;
const seed = { shop_id: id(1), registry_id: id(2), registry_digest: "a".repeat(64), product_source_id: id(3), query_ref: "synthetic@v1", reviewer_id: id(4) };
const preview = { kind: "create", input: { schema_version: "p6-copy-web-v1", ...seed, request_key: id(5) } };
test("copy preview requires every exact private seed field and frozen schema", () => {
 expect(validOwnedCopyPreview(preview, seed)).toBe(true);
 for (const field of ["shop_id", "registry_id", "product_source_id", "reviewer_id"] as const) expect(validOwnedCopyPreview({ ...preview, input: { ...preview.input, [field]: id(9) } }, seed)).toBe(false);
 expect(validOwnedCopyPreview({ ...preview, input: { ...preview.input, registry_digest: "b".repeat(64) } }, seed)).toBe(false);
 expect(validOwnedCopyPreview({ ...preview, input: { ...preview.input, query_ref: "different@v1" } }, seed)).toBe(false);
 expect(validOwnedCopyPreview({ ...preview, input: { ...preview.input, request_key: "invalid" } }, seed)).toBe(false);
 expect(validOwnedCopyPreview({ ...preview, input: { ...preview.input, schema_version: "other" } }, seed)).toBe(false);
 const { schema_version: _schema, ...missing } = preview.input;
 expect(validOwnedCopyPreview({ kind: "create", input: missing }, seed)).toBe(false);
 expect(validOwnedCopyPreview({ ...preview, input: { ...preview.input, extra: true } }, seed)).toBe(false);
 expect(validOwnedCopyPreview({ ...preview, extra: true }, seed)).toBe(false);
});
test("a preview cannot authorize a POST whose body differs from the seed", () => {
 const guard = new BoundedNetwork("http://127.0.0.1:8888", "http://127.0.0.1:9999", 1000, 100);
 const fixed = JSON.stringify(preview.input);
 guard.allow({ method: "POST", pathname: "/api/v1/copy/candidates", search: "", remaining: 1,
  body: raw => { try { const input: unknown = JSON.parse(raw ?? ""); return JSON.stringify(input) === fixed && validOwnedCopyPreview({ kind: "create", input }, seed); } catch { return false; } } });
 const request = { url: "http://127.0.0.1:9999/api/v1/copy/candidates", method: "POST", body: JSON.stringify({ ...preview.input, product_source_id: id(9) }) };
 expect(guard.accept(request, 1)).toBe(false);
 expect(guard.accept({ ...request, body: fixed }, 1)).toBe(true);
 expect(guard.accept({ ...request, body: fixed }, 1)).toBe(false);
});
