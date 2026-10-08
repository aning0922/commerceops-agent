import { readFileSync } from "node:fs";
const manifest: { engines: { node: string; npm: string } } = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8")
);
if (process.versions.node !== manifest.engines.node) {
  throw new Error("Use the project Node toolchain from scripts/bootstrap_tools.py");
}
console.log(`Node ${process.versions.node}: project toolchain verified`);
