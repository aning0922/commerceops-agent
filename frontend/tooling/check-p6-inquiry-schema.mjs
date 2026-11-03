import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
const frozen = await readFile(new URL("../lib/p6-inquiry-openapi.generated.json", import.meta.url));
if (createHash("sha256").update(frozen).digest("hex") !== "9e9a7e093d4cccfde5634226d7076003a9f124c54643d76bd1466aea1b017ed5")
  throw new Error("Inquiry frozen OpenAPI differs from candidate e2e50f5");
try {
  const source = await readFile(new URL("../../backend/src/commerceops/assets/p6-inquiry-web-v1.openapi.json", import.meta.url));
  if (!source.equals(frozen)) throw new Error("Inquiry backend OpenAPI changed; synchronize after review");
} catch (error) { if (error?.code !== "ENOENT") throw error; }
console.log("Inquiry candidate OpenAPI: pinned asset verified");
