// Controlled Web proofs; readonly process/socket observation, no creation or termination.
import { execFileSync } from "node:child_process";
import { readFileSync, readlinkSync, readdirSync, statSync } from "node:fs";

export function linuxListenerInode(
  tcp: string,
  tcp6: string,
  port: number,
  uid: number,
): string {
  if (
    !Number.isSafeInteger(port) ||
    port < 1 ||
    port > 65535 ||
    !Number.isSafeInteger(uid) ||
    uid < 0
  )
    throw new Error("Invalid owned socket identity");
  const suffix = ":" + port.toString(16).toUpperCase().padStart(4, "0");
  const rows = [tcp, tcp6]
    .flatMap((table) =>
      table
        .split("\n")
        .slice(1)
        .map((line) => line.trim().split(/\s+/)),
    )
    .filter((row) => row[1]?.endsWith(suffix) && row[3] === "0A");
  if (
    rows.length !== 1 ||
    rows[0][1] !== "0100007F" + suffix ||
    rows[0][7] !== String(uid) ||
    !/^[1-9][0-9]*$/.test(rows[0][9] ?? "")
  )
    throw new Error("Exclusive current-user loopback socket required");
  return rows[0][9];
}

export function readOwnedListener(port: number): string {
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535)
    throw new Error("Invalid owned listener port");
  if (process.platform !== "linux")
    return execFileSync(
      "lsof",
      ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN", "-t"],
      { encoding: "utf8" },
    );
  const uid = process.getuid?.();
  if (uid === undefined) throw new Error("Current user identity required");
  const inode = linuxListenerInode(
    readFileSync("/proc/net/tcp", "utf8"),
    readFileSync("/proc/net/tcp6", "utf8"),
    port,
    uid,
  );
  const holders: string[] = [];
  for (const pid of readdirSync("/proc").filter((name) =>
    /^[1-9][0-9]*$/.test(name),
  )) {
    try {
      if (statSync(`/proc/${pid}`).uid !== uid) continue;
      if (
        readdirSync(`/proc/${pid}/fd`).some((fd) => {
          try {
            return (
              readlinkSync(`/proc/${pid}/fd/${fd}`) === `socket:[${inode}]`
            );
          } catch {
            return false;
          }
        })
      )
        holders.push(pid);
    } catch {
      /* A process may exit during this read-only observation. */
    }
  }
  if (holders.length !== 1)
    throw new Error("Unique owned socket process required");
  return holders[0] + "\n";
}

export function assertOwnedMockProcess(
  pid: number,
  cwd: string,
  launcher: number,
): number {
  if (
    ![pid, launcher].every((value) => Number.isSafeInteger(value) && value > 0)
  )
    throw new Error("Explicit Mock process ancestry required");
  const uid = process.getuid?.();
  if (uid === undefined) throw new Error("Current Mock user required");
  const processIdentity = (identifier: number) => {
    if (process.platform === "linux") {
      const stat = readFileSync(`/proc/${identifier}/stat`, "utf8");
      return {
        uid: statSync(`/proc/${identifier}`).uid,
        parent: Number(stat.slice(stat.lastIndexOf(")") + 2).split(/\s+/)[1]),
      };
    }
    const row = execFileSync(
      "ps",
      ["-o", "uid=,ppid=", "-p", String(identifier)],
      { encoding: "utf8" },
    )
      .trim()
      .split(/\s+/)
      .map(Number);
    return { uid: row[0], parent: row[1] };
  };
  const actualCwd =
    process.platform === "linux"
      ? readlinkSync(`/proc/${pid}/cwd`)
      : execFileSync("lsof", ["-a", "-p", String(pid), "-d", "cwd", "-Fn"], {
          encoding: "utf8",
        })
          .split("\n")
          .filter((line) => line.startsWith("n"))
          .map((line) => line.slice(1))
          .join("\n");
  if (actualCwd !== cwd || processIdentity(pid).uid !== uid)
    throw new Error("Current-user Mock checkout required");
  let current = pid;
  for (let hop = 0; hop < 64 && current > 0; hop++) {
    if (current === launcher) return uid;
    const identity = processIdentity(current);
    if (identity.uid !== uid || identity.parent === current) break;
    current = identity.parent;
  }
  throw new Error("Mock must descend from this Playwright launcher");
}
export function ownedLoopbackPort(value: unknown): number {
  if (typeof value !== "string")
    throw new Error("Invalid owned loopback origin");
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("Invalid owned loopback origin");
  }
  if (
    url.protocol !== "http:" ||
    url.hostname !== "127.0.0.1" ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash ||
    url.origin !== value ||
    !/^[1-9][0-9]{0,4}$/.test(url.port)
  )
    throw new Error("Invalid owned loopback origin");
  const port = Number(url.port);
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535)
    throw new Error("Invalid owned loopback port");
  return port;
}
export function ownedEndpoints(
  window: {
    web_origin: unknown;
    api_origin: unknown;
    web_pid: unknown;
    api_pid: unknown;
  },
  expectedWebOrigin: unknown,
) {
  const webPort = ownedLoopbackPort(window.web_origin);
  const apiPort = ownedLoopbackPort(window.api_origin);
  if (window.web_origin !== expectedWebOrigin)
    throw new Error("Owned web origin mismatch");
  const entries = [
    { port: webPort, pid: window.web_pid },
    { port: apiPort, pid: window.api_pid },
  ];
  for (const entry of entries)
    if (
      typeof entry.pid !== "number" ||
      !Number.isSafeInteger(entry.pid) ||
      entry.pid < 1
    )
      throw new Error("Invalid owned process identity");
  return entries as { port: number; pid: number }[];
}
export function assertOwnedListener(output: string, expectedPid: number): void {
  const lines = output.trim().split(/\s+/).filter(Boolean);
  if (
    !lines.length ||
    lines.some((line) => !/^[1-9][0-9]*$/.test(line)) ||
    new Set(lines).size !== 1 ||
    lines[0] !== String(expectedPid)
  )
    throw new Error("Owned listener mismatch");
}
export function assertOwnedBuild(declared: unknown, current: string): void {
  if (typeof declared !== "string" || !declared || declared !== current.trim())
    throw new Error("Owned source build mismatch");
}
