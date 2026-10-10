import { test, expect } from "../../../frontend/tooling/web-test";
import { noOverflow, screenshot, safeAccess } from "./helpers";
test("admin-only运维选中态、无业务导航、深链无对象泄漏", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "管理配置与异常说明" }),
  ).toBeVisible();
  await expect(page.locator("nav a")).toHaveCount(1);
  await expect(page.locator("nav [data-control=B30]")).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(
    page.getByText("期限与新鲜度：未知；不硬编码产品承诺。"),
  ).toBeVisible();
  await screenshot(page, "admin-1440");
  await page.setViewportSize({ width: 390, height: 844 });
  await noOverflow(page);
  for (const path of [
    "/tasks",
    "/tasks/INV-DEMO-008/report",
    "/approvals/APR-DEMO-008",
    "/replenishment-items/RI-DEMO-001",
  ]) {
    await page.goto(path);
    await safeAccess(page);
  }
  await page.locator("[data-control=B31]").click();
  await expect(
    page.getByRole("heading", { name: "管理配置与异常说明" }),
  ).toBeVisible();
});
