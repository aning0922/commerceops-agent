import { expect } from "@playwright/test";
import type { Browser, BrowserContext, Page, Response } from "@playwright/test";
import { BoundedNetwork } from "./bounded-network";
import { dropActualResponse } from "./drop-response";
import { waitForOwnedHome } from "./owned-home-ready";
import type { Account, Window } from "./owned-m3-input";
export type Session = { context: BrowserContext; page: Page; guard: BoundedNetwork; dropNext: (path: string) => Promise<number> };
export async function session(browser: Browser, w: Window, stop: number, account: Account, organization: string, shops: readonly string[], record: (event: object) => void, verify: () => void): Promise<Session> {
  verify();
  const context = await browser.newContext({ baseURL: w.web_origin, viewport: { width: 390, height: 844 }, serviceWorkers: "block" });
  const remaining = stop - Date.now() - 90000;
  if (remaining <= 0) { await context.close(); throw new Error("Cleanup reserve reached"); }
  const deadline = setTimeout(() => { void context.close(); }, remaining);
  context.once("close", () => clearTimeout(deadline));
  const guard = new BoundedNetwork(w.web_origin, w.api_origin, stop, 90000);
  const get = (pathname: string, search = "", remaining = 10) => guard.allow({ method: "GET", pathname, search, remaining });
  get("/login"); get(account.home_path); guard.allowRsc(account.home_path, 5); for (const shop of shops) get("/api/v1/config", `?shop_id=${shop}`); get("/api/v1/auth/session"); get("/api/v1/auth/csrf");
  if (account.home_path === "/tasks") get("/api/v1/tasks", "?limit=20");
  guard.allow({ method: "POST", pathname: "/api/v1/auth/login", search: "", remaining: 1 });
  await context.routeWebSocket(/.*/, socket => socket.close());
  let drop: { path: string; resolve: (status: number) => void } | null = null;
  const dropNext = (path: string) => new Promise<number>((resolve, reject) => { if (drop || !path.startsWith("/api/v1/")) { reject(new Error("Invalid loss injection")); return; } drop = { path, resolve }; });
  await context.route("**/*", async route => {
    const request = route.request();
    let permitted = false;
    try { permitted = guard.accept({ url: request.url(), method: request.method(), body: request.postData() }); } catch { /* fail closed if the ledger or predicate fails */ }
    if (!permitted) { await route.abort(); return; }
    if (new URL(request.url()).origin === w.api_origin) {
      try { verify(); } catch {
        if (drop && request.method() === "POST" && new URL(request.url()).pathname === drop.path) { const armed = drop; drop = null; armed.resolve(0); }
        await route.abort(); return;
      }
    }
    if (drop && request.method() === "POST" && new URL(request.url()).pathname === drop.path) {
      const armed = drop; drop = null;
      // Exactly one real request. Suppress its real response to exercise UNKNOWN; never fulfill.
      try { record({ event: "forwarding_one_post", path: armed.path }); }
      catch { await route.abort("failed"); armed.resolve(0); return; }
      try { armed.resolve(await dropActualResponse(route, Math.max(1, Math.min(30000, stop - Date.now() - 90000)))); }
      catch { armed.resolve(0); }
      return;
    }
    await route.continue();
  });
  const page = await context.newPage(); await page.goto("/login");
  await page.locator("#live-login").evaluate((el, value) => { (el as HTMLInputElement).value = value; }, account.login);
  const loginResponse = response(page, w.api_origin, "/api/v1/auth/login", "POST");
  try { await page.locator("#live-password").evaluate((el, value) => { (el as HTMLInputElement).value = value; }, account.password); await page.getByRole("button", { name: "登录", exact: true }).click(); }
  finally { await page.locator("#live-password").evaluateAll(els => els.forEach(el => { (el as HTMLInputElement).value = ""; })).catch(() => {}); }
  const login = await loginResponse; if (login.status() !== 200) throw new Error("Owned login failed");
  const identity = await login.json();
  if (identity.principal?.principal_id !== account.principal_id || identity.principal?.organization_id !== organization || identity.principal?.capabilities?.home_path !== account.home_path || !Array.isArray(identity.principal?.role_shop_grants)) throw new Error("Owned principal mismatch");
  for (const shop of shops) {
    const roles = identity.principal.role_shop_grants.filter((g: { shop_id: string }) => g.shop_id === shop).map((g: { role: string }) => g.role).filter((x: string) => x === "operator" || x === "approver").sort();
    if (JSON.stringify(roles) !== JSON.stringify([...account.shop_roles[shop]].sort())) throw new Error("Owned shop roles mismatch");
  }
  await waitForOwnedHome(page, w.web_origin, account.home_path);
  return { context, page, guard, dropNext };
}
export function get(s: Session, pathname: string, search = "", count = 1) { s.guard.allow({ method: "GET", pathname, search, remaining: count }); }
export function post(s: Session, pathname: string, body: (value: string | null) => boolean) { s.guard.allow({ method: "POST", pathname, search: "", remaining: 1, body }); }
export async function go(s: Session, path: string) { get(s, path); await s.page.goto(path); }
export function response(page: Page, origin: string, pathname: string, method: "GET" | "POST" = "GET"): Promise<Response> { return page.waitForResponse(r => { const u = new URL(r.url()); return u.origin === origin && u.pathname === pathname && r.request().method() === method; }); }
export async function noOverflow(page: Page) {
  const sizes = await page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const clipped = [...document.querySelectorAll("button,input,select,textarea,pre")].some(el => {
      const node = el as HTMLElement, rect = node.getBoundingClientRect(), style = getComputedStyle(node);
      return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && (rect.left < 0 || rect.right > viewport + 1 || node.tagName === "PRE" && node.scrollWidth > node.clientWidth + 1);
    });
    return { page: document.documentElement.scrollWidth, viewport, clipped };
  });
  expect(sizes.page).toBeLessThanOrEqual(sizes.viewport); expect(sizes.clipped).toBe(false);
}
