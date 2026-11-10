// Per-context, exact, consumable permissions. This module does not make requests.
export type RequestShape = { url: string; method: string; body: string | null };
export type Rule = { method: "GET" | "POST"; pathname: string; search: string; remaining: number; body?: (value: string | null) => boolean };
export class BoundedNetwork {
  private rules: Rule[] = [];
  private blocked = 0;
  private postCounts = new Map<string, number>();
  private probes = 0;
  private rsc = new Map<string, number>();
  constructor(private readonly webOrigin: string, private readonly apiOrigin: string, private readonly stopAt: number, private readonly reserveMs: number) {}
  allow(rule: Rule) {
    if (!Number.isSafeInteger(rule.remaining) || rule.remaining < 1 || rule.remaining > 100 || !rule.pathname.startsWith("/") || rule.pathname.includes("?") || rule.pathname.includes("#") || (rule.search && !rule.search.startsWith("?"))) throw new Error("Invalid bounded rule");
    this.rules.push({ ...rule });
  }
  allowRsc(pathname: string, count: number) { if (!["/tasks", "/access"].includes(pathname) || !Number.isSafeInteger(count) || count < 1 || count > 5) throw new Error("Invalid page permit"); this.rsc.set(pathname, count); }
  allowCopyProbe() { if (this.probes !== 0) throw new Error("Prior probe not consumed"); this.probes = 1; }
  accept(req: RequestShape, now = Date.now()): boolean {
    let u: URL; try { u = new URL(req.url); } catch { this.blocked++; return false; }
    if (req.method === "POST" && u.origin === this.apiOrigin && u.pathname.startsWith("/api/")) this.postCounts.set(u.pathname, (this.postCounts.get(u.pathname) ?? 0) + 1);
    if (now + this.reserveMs >= this.stopAt || u.username || u.password || u.hash || !["GET", "POST"].includes(req.method)) { this.blocked++; return false; }
    // Only immutable Next assets and the fixed favicon bypass consumable business rules.
    if (req.method === "GET" && u.origin === this.webOrigin && !u.search && (u.pathname.startsWith("/_next/static/") || u.pathname === "/favicon.ico")) return true;
    if (req.method === "GET" && u.origin === this.webOrigin && (this.rsc.get(u.pathname) ?? 0) > 0 && u.searchParams.size === 1 && /^[a-z0-9]{1,32}$/.test(u.searchParams.get("_rsc") ?? "")) { this.rsc.set(u.pathname, this.rsc.get(u.pathname)! - 1); return true; }
    const origin = u.pathname.startsWith("/api/") ? this.apiOrigin : this.webOrigin;
    if (u.origin !== origin) { this.blocked++; return false; }
    if (this.probes === 1 && req.method === "GET" && u.origin === this.apiOrigin && !u.search && /^\/api\/v1\/copy\/candidate-requests\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(u.pathname)) { this.probes = 0; return true; }
    const rule = this.rules.find(x => x.remaining > 0 && x.method === req.method && x.pathname === u.pathname && x.search === u.search && (!x.body || x.body(req.body)));
    if (!rule) { this.blocked++; return false; }
    rule.remaining--; return true;
  }
  get denied() { return this.blocked; }
  posts(path: string) { return this.postCounts.get(path) ?? 0; }
}
