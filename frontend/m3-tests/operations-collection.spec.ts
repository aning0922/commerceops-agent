import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

test("live operations collection neither reads private inputs nor creates or modifies the ledger", () => {
  const temporary = mkdtempSync(resolve(tmpdir(), "m3-collection-"));
  const cwd = resolve(import.meta.dirname, "..");
  const cli = resolve(cwd, "node_modules/@playwright/test/cli.js");
  try {
    for (const mode of ["empty", "existing"]) {
      const directory = resolve(temporary, mode); mkdirSync(directory, { mode: 0o700 });
      const ledger = resolve(directory, "m3-operations-ledger.jsonl");
      if (mode === "existing") writeFileSync(ledger, "preserve-original\n", { mode: 0o600 });
      // No window/seed files, listeners, .next build, browser, or real private directory.
      const output = execFileSync(process.execPath, [cli, "test", "--config", "playwright.m3.operations.live.config.ts", "--list"], {
        cwd, encoding: "utf8", timeout: 20000,
        env: { ...process.env, COMMERCEOPS_M3_LIVE_WEB_URL: "http://127.0.0.1:59999", COMMERCEOPS_M3_PRIVATE_DIR: directory },
      });
      expect(output).toContain("3 tests");
      if (mode === "existing") { expect(readdirSync(directory)).toEqual(["m3-operations-ledger.jsonl"]); expect(readFileSync(ledger, "utf8")).toBe("preserve-original\n"); }
      else expect(readdirSync(directory)).toEqual([]);
    }
  } finally { rmSync(temporary, { recursive: true, force: true }); }
});
