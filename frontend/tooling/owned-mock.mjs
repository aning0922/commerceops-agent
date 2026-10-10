// Only for the two B01 local proofs. Never reuse or terminate an existing service.
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { randomUUID, createHash } from "node:crypto";
export const frontend = fileURLToPath(new URL("../", import.meta.url));
export async function startOwnedMock(supplied) {
  if (!supplied)
    throw new Error("Explicit --base-url loopback origin is required");
  const origin = new URL(supplied);
  if (
    origin.protocol !== "http:" ||
    origin.hostname !== "127.0.0.1" ||
    !origin.port ||
    origin.pathname !== "/" ||
    origin.search ||
    origin.hash ||
    origin.username ||
    origin.password
  )
    throw new Error("Use an explicit http://127.0.0.1:PORT origin");
  const buildId = (
    await readFile(join(frontend, ".next", "BUILD_ID"), "utf8")
  ).trim();
  const serviceId = randomUUID();
  const server = spawn(
    process.execPath,
    [
      join(frontend, "node_modules/next/dist/bin/next"),
      "start",
      "--hostname",
      "127.0.0.1",
      "--port",
      origin.port,
    ],
    {
      cwd: frontend,
      env: {
        ...process.env,
        COMMERCEOPS_UI_MODE: "mock",
        COMMERCEOPS_MOCK_ROLE: "approver",
        COMMERCEOPS_MOCK_CAPACITY: "20",
        COMMERCEOPS_MOCK_PROOF_ID: serviceId,
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  const close = async () => {
    if (server.exitCode === null) {
      server.kill("SIGTERM");
      await new Promise((resolve) => server.once("exit", resolve));
    }
  };
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("Owned Mock startup timed out")),
        10000,
      );
      server.once("error", () => {
        clearTimeout(timer);
        reject(new Error("Owned Mock startup failed"));
      });
      server.once("exit", () => {
        clearTimeout(timer);
        reject(
          new Error(
            "Owned Mock exited before readiness; occupied/unknown service rejected",
          ),
        );
      });
      server.stdout.on("data", (data) => {
        if (data.toString().includes("Ready")) {
          clearTimeout(timer);
          resolve();
        }
      });
    });
  } catch (error) {
    await close();
    throw error;
  }
  return {
    origin,
    serviceId,
    buildId,
    pid: server.pid,
    buildFingerprint: createHash("sha256").update(buildId).digest("hex"),
    close,
  };
}
export async function verifyOwnedMock(page, owned) {
  const actual = await page
    .locator(".app-shell")
    .evaluate((el) => ({
      source: el.getAttribute("data-mock-source"),
      service: el.getAttribute("data-mock-service"),
      build: el.getAttribute("data-mock-build"),
    }));
  if (
    actual.source !== "commerceops-b01" ||
    actual.service !== owned.serviceId ||
    actual.build !== owned.buildId
  )
    throw new Error("Mock/build ownership mismatch");
  return actual;
}
