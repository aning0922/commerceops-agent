// Only the separate N01 contract; never rewrite the frozen P3 22 operations.
import { readFile, writeFile } from "node:fs/promises";
const root = new URL("../../", import.meta.url);
const spec = JSON.parse(
  await readFile(new URL("docs/contracts/p4-n01-openapi.json", root), "utf8"),
);
const operation = spec.paths["/api/v1/tasks/preflight"].post;
const output = JSON.stringify({
  components: spec.components,
  input: operation.requestBody.content["application/json"].schema,
  responses: Object.fromEntries(
    Object.entries(operation.responses).map(([status, response]) => [
      status,
      response.content["application/json"].schema,
    ]),
  ),
}, null, 2) + "\n";
const destination = new URL("frontend/lib/p4-n01-schema.generated.json", root);
if (process.argv.includes("--check")) {
  if (await readFile(destination, "utf8") !== output)
    throw new Error("N01 schema differs; regenerate explicitly");
} else await writeFile(destination, output);
console.log("N01 preflight schema: 1 separate operation");
