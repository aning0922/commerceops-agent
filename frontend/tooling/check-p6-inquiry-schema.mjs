import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
const frozen = await readFile(new URL("../lib/p6-inquiry-openapi.generated.json", import.meta.url));
if (createHash("sha256").update(frozen).digest("hex") !== "63c88046c97953a6865b8e445d3d2c6fb8be4e8bad61a48d5f076dde31c10697")
  throw new Error("Inquiry frozen OpenAPI differs from reviewed candidate 1a78d5a");
try {
  const source = await readFile(new URL("../../backend/src/commerceops/assets/p6-inquiry-web-v1.openapi.json", import.meta.url));
  if (!source.equals(frozen)) throw new Error("Inquiry backend OpenAPI changed; synchronize after review");
} catch (error) { if (error?.code !== "ENOENT") throw error; }
console.log("Inquiry candidate OpenAPI: pinned asset verified");
