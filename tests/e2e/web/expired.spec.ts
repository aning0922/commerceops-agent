import { test, expect } from "../../../frontend/tooling/web-test";
import { screenshot } from "./helpers";
test("过期深链不返回旧数据或计数", async ({ page }) => {
  await page.goto("/tasks/INV-DEMO-008/report");
  await expect(page.getByRole("heading", { name: "会话已过期" })).toBeVisible();
  const content = await page.content();
  for (const text of ["SKU-A", "SKU-B", "RI-DEMO-001", "近 7 天销量与库存分析"])
    expect(content).not.toContain(text);
  await expect(page.locator("nav a")).toHaveCount(0);
  await screenshot(page, "expired");
});
