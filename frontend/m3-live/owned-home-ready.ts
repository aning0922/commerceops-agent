import type { Page } from "@playwright/test";
import type { Account } from "./owned-m3-input";

export function isOwnedHome(url: URL, origin: string, home: Account["home_path"]): boolean {
  return url.origin === origin && url.pathname === home && !url.username && !url.password && !url.search && !url.hash;
}

// Wait for the client-side login redirect and the actual home page, not the earlier session shell.
export async function waitForOwnedHome(page: Page, origin: string, home: Account["home_path"]): Promise<void> {
  try {
    await page.waitForURL(url => isOwnedHome(url, origin, home), { waitUntil: "commit" });
    await page.locator('[data-source-mode="live-session"]').waitFor({ state: "visible" });
    const main = page.locator("main#main");
    await main.getByRole("heading", { name: home === "/tasks" ? "任务中心" : "访问限制与会话过期", exact: true, level: 1 }).waitFor({ state: "visible" });
    await main.getByRole("heading", { name: home === "/tasks" ? "任务列表" : "无法访问此页面", exact: true, level: 2 }).waitFor({ state: "visible" });
    if (!isOwnedHome(new URL(page.url()), origin, home)) throw new Error("home changed");
  } catch {
    // Do not expose the current URL, query, response body or account in diagnostics.
    throw new Error("Owned login home navigation not ready");
  }
}
