// B02-only proof helpers; no process creation/termination or default service ports.
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
