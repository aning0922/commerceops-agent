import type { Page } from "../../../frontend/node_modules/@playwright/test";
import { expect } from "../../../frontend/tooling/web-test";
export async function noOverflow(page: Page) {
  const size = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(size.scroll).toBeLessThanOrEqual(size.client + 1);
}
export async function noBusinessRequests(page: Page) {
  const unexpected: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (
      !["127.0.0.1", "localhost"].includes(url.hostname) ||
      request.method() !== "GET" ||
      /\/api\//.test(url.pathname)
    )
      unexpected.push(`${request.method()} ${url.pathname}`);
  });
  return unexpected;
}
export async function screenshot(page: Page, name: string) {
  await page.screenshot({ path: `evidence/b01/${name}.png`, fullPage: true });
}
export async function safeAccess(page: Page) {
  await expect(
    page.getByRole("heading", { name: "无法访问此页面" }),
  ).toBeVisible();
  const html = await page.content();
  for (const secret of [
    "SKU-A",
    "RI-DEMO-001",
    "近 7 天销量与库存分析",
    "REPORT-DEMO-008",
  ])
    expect(html).not.toContain(secret);
}
