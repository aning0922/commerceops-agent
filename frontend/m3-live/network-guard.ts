// Narrow network allowlist for an explicitly registered owned UI/API window.
export function allowedOwnedRequest(
  input: string, method: string, webOrigin: string, apiOrigin: string, taskId: string,
): boolean {
  let url: URL;
  try { url = new URL(input); } catch { return false; }
  if (url.username || url.password || url.hash || !["http:", "https:"].includes(url.protocol)) return false;
  const dailyPath = `/api/v1/daily-reports/${taskId}`;
  if (method === "POST") return url.origin === apiOrigin && url.pathname === "/api/v1/auth/login" && !url.search;
  if (method !== "GET") return false;
  if (url.pathname.startsWith("/api/") || url.origin === apiOrigin && apiOrigin !== webOrigin) {
    return url.origin === apiOrigin && ["/api/v1/auth/csrf", "/api/v1/auth/session", "/api/v1/tasks", "/api/v1/config", dailyPath].includes(url.pathname);
  }
  return url.origin === webOrigin && (
    ["/login", "/tasks", "/access", `/daily-reports/${taskId}`, "/favicon.ico"].includes(url.pathname) ||
    url.pathname.startsWith("/_next/static/")
  );
}
