import { test, expect } from "../../../frontend/tooling/web-test";
import { noOverflow, noBusinessRequests, screenshot } from "./helpers";
test("20SKU完整审批首末风险、窄屏无裁切、禁止真实决定", async ({ page }) => {
  const requests = await noBusinessRequests(page);
  await page.goto("/approvals/APR-DEMO-008");
  const table = page.getByRole("table", { name: "完整审批清单" });
  await expect(table.getByRole("row")).toHaveCount(21);
  await expect(page.locator("#SKU-01")).toContainText("未知");
  await expect(page.locator("#SKU-20")).toContainText("可能重复补货");
  await expect(page.getByText("完整清单 · 20 / 20 项")).toBeVisible();
  await expect(page.locator("[data-control=B03]")).toBeDisabled();
  await screenshot(page, "approval-20-1440");
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await noOverflow(page);
    await page.locator("#SKU-20").scrollIntoViewIfNeeded();
    await expect(page.locator("#SKU-20")).toBeVisible();
    await screenshot(page, `approval-20-${width}`);
  }
  await page.locator("[data-control=B23]").click();
  await expect(page.getByRole("dialog")).toContainText("审批仍待处理");
  await page.keyboard.press("Escape");
  expect(requests).toEqual([]);
});
test("原因pristine/必填错误/本地有效校验/焦点恢复、终态只读", async ({
  page,
}) => {
  const requests = await noBusinessRequests(page);
  await page.goto("/replenishment-items/RI-DEMO-001");
  const trigger = page.locator("[data-control=B26]");
  await trigger.click();
  await expect(page.locator("#reason-error")).toBeEmpty();
  await page.getByRole("button", { name: "检查原因（本地）" }).click();
  await expect(page.getByText("请填写完成或关闭原因。")).toBeVisible();
  await expect(page.getByLabel("原因（必填）")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  await page.getByLabel("原因（必填）").fill("供应商已联系，记录内部跟进。");
  await page.getByRole("button", { name: "检查原因（本地）" }).click();
  await expect(page.getByText("本地原因校验完成")).toBeVisible();
  await expect(page.locator("[data-control=B07]")).toBeDisabled();
  await screenshot(page, "reason-valid");
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await expect(page.getByText("待跟进", { exact: true })).toBeVisible();
  await page.locator("[data-control=B27]").click();
  await expect(page.locator("[data-control=B08]")).toBeDisabled();
  await page.keyboard.press("Escape");
  await page.goto("/replenishment-items/RI-DEMO-003");
  await expect(page.getByText("终态只读")).toBeVisible();
  await expect(page.locator("[data-control=B26]")).toHaveCount(0);
  expect(requests).toEqual([]);
});
