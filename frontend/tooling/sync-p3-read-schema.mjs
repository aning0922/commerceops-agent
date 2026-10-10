// Copies the reviewed A03 business freeze's full 22 response operations; no server imports.
import { readFile, writeFile } from "node:fs/promises";
const root = new URL("../../", import.meta.url);
const spec = JSON.parse(
  await readFile(new URL("docs/contracts/p3-openapi.json", root), "utf8"),
);
const allowed = [
  ["get", "/api/v1/auth/csrf"],
  ["post", "/api/v1/auth/login"],
  ["get", "/api/v1/auth/session"],
  ["post", "/api/v1/auth/logout"],
  ["get", "/api/v1/config"],
  ["get", "/api/v1/admin/operations"],
  ["get", "/api/v1/tasks"],
  ["post", "/api/v1/tasks"],
  ["get", "/api/v1/tasks/{task_id}"],
  ["get", "/api/v1/tasks/{task_id}/report"],
  ["get", "/api/v1/tasks/{task_id}/explanation"],
  ["get", "/api/v1/tasks/{task_id}/plans"],
  ["get", "/api/v1/tasks/{task_id}/plans/{plan_version}"],
  ["get", "/api/v1/tasks/{task_id}/events"],
  ["get", "/api/v1/tasks/{task_id}/execution"],
  ["get", "/api/v1/approvals"],
  ["get", "/api/v1/approvals/{approval_id}"],
  ["post", "/api/v1/approvals/{approval_id}/decision"],
  ["get", "/api/v1/requests/{request_key}"],
  ["get", "/api/v1/replenishment-items"],
  ["get", "/api/v1/replenishment-items/{item_id}"],
  ["post", "/api/v1/replenishment-items/{item_id}/resolve"],
];
const operations = allowed.map(([method, path]) => ({
  method: method.toUpperCase(),
  path,
  responses: Object.fromEntries(
    Object.entries(spec.paths[path][method].responses).map(([status, v]) => [
      status,
      v.content["application/json"].schema,
    ]),
  ),
}));
const output =
  JSON.stringify({ components: spec.components, operations }, null, 2) + "\n";
const destination = new URL("frontend/lib/p3-read-schema.generated.json", root);
if (process.argv.includes("--check")) {
  if ((await readFile(destination, "utf8")) !== output)
    throw new Error("Frozen read schema differs; regenerate explicitly");
} else await writeFile(destination, output);
console.log(`Frozen A03 business schema: ${operations.length} operations`);
