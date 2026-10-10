import { test, expect } from "../../../frontend/tooling/web-test";
test("未明确启用Mock时fail closed，任何角色env不授业务读", async ({ page }) => {
  await page.goto("/tasks");
  await expect(
    page.getByRole("heading", { name: "无法访问此页面" }),
  ).toBeVisible();
  await expect(page.locator("nav a")).toHaveCount(0);
  expect(await page.content()).not.toContain("SKU-A");
  await page.goto("/login");
  await expect(
    page.getByText("服务端会话尚未接入", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "查看固定离线 Mock 样例" }),
  ).toHaveCount(0);
});
