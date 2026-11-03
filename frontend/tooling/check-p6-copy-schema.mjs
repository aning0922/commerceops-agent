import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
const contents = await readFile(new URL("../lib/p6-copy-openapi.generated.json", import.meta.url));
if (createHash("sha256").update(contents).digest("hex") !== "db0445643a4878ee95940e87491985ddd5b84b92315b337e70c6f17309b3cb54") throw new Error("Copy OpenAPI differs from frozen b9fe309");
console.log("Copy OpenAPI matches frozen b9fe309");
