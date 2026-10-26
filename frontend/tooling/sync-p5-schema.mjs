// Overlay only reviewed P3/P4/P5 exports. Never rewrite the original frozen artifacts.
import { mkdir, readFile, writeFile } from "node:fs/promises";
const root = new URL("../../", import.meta.url);
const spec = { openapi: "3.1.0", info: { title: "Reviewed M2 Web", version: "p5-m2-v1" }, paths: {}, components: { schemas: {}, securitySchemes: {} } };
for (const name of ["p3-openapi.json", "p4-n01-openapi.json", "p5-m2-openapi.json"]) {
  const source = JSON.parse(await readFile(new URL("docs/contracts/" + name, root), "utf8"));
  for (const [path, methods] of Object.entries(source.paths))
    spec.paths[path] = { ...spec.paths[path], ...methods };
  for (const key of ["schemas", "securitySchemes"])
    Object.assign(spec.components[key], source.components[key] ?? {});
}
function refs(value) {
  if (value === null || typeof value !== "object") return;
  if (value.$ref) {
    let target = spec;
    for (const key of value.$ref.slice(2).split("/")) target = target?.[key];
    if (!target) throw new Error("Unresolved reviewed schema reference");
  }
  Object.values(value).forEach(refs);
}
refs(spec);
if (Object.keys(spec.paths).length !== 22 || Object.keys(spec.components.schemas).length !== 94)
  throw new Error("Reviewed P5 contract inventory differs");
const operations = [];
for (const [path, methods] of Object.entries(spec.paths)) {
  for (const [method, operation] of Object.entries(methods)) {
    if (!["get", "post"].includes(method)) throw new Error("Unreviewed Web method");
    operations.push({ method: method.toUpperCase(), path,
      ...(operation.requestBody ? { input: operation.requestBody.content["application/json"].schema } : {}),
      responses: Object.fromEntries(Object.entries(operation.responses).map(([status, response]) => [status, response.content["application/json"].schema])),
    });
  }
}
for (const [file, value] of [["p5-read-schema.generated.json", { components: spec.components, operations }]]) {
  const output = JSON.stringify(value, null, 2) + "\n";
  const destination = new URL("frontend/lib/" + file, root);
  if (process.argv.includes("--check")) {
    if (await readFile(destination, "utf8") !== output) throw new Error("P5 generated schema differs; regenerate explicitly");
  } else await writeFile(destination, output);
}
// The full merged OpenAPI is only an intermediate input for the existing TS generator.
if (process.argv.includes("--openapi")) {
  if (process.argv.includes("--check")) throw new Error("Choose check or explicit OpenAPI generation");
  await mkdir(new URL(".audit/", root), { recursive: true });
  await writeFile(new URL(".audit/p5-openapi.generated.json", root), JSON.stringify(spec, null, 2) + "\n");
}
console.log(`Reviewed P5: 22 paths, 94 schemas, ${operations.length} operations, zero dangling refs`);
