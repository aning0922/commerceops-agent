import { readFile, writeFile } from "node:fs/promises";
const root = new URL("../../", import.meta.url);
const source = new URL("docs/contracts/p6-daily-read-v1.schema.json", root);
const destination = new URL("frontend/lib/m3-read-schema.generated.json", root);
const value = await readFile(source, "utf8");
if (process.argv.includes("--check")) {
  if (await readFile(destination, "utf8") !== value)
    throw new Error("M3 reviewed daily schema differs");
} else await writeFile(destination, value);
console.log("M3 daily read schema matches reviewed asset");
