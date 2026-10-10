import { test, expect } from "../../../frontend/tooling/web-test";
import { noBusinessRequests } from "./helpers";
test("unknown先核实原回执，无换键/重发/猜测成功", async ({ page }) => {
  const requests = await noBusinessRequests(page);
  await page.goto("/approvals/APR-DEMO-008");
  await expect(page.getByText("审批结果未知", { exact: true })).toBeVisible();
  await expect(page.locator("[data-control=B03]")).toBeDisabled();
  await page.locator("[data-control=B23]").click();
  await expect(page.getByRole("dialog")).toContainText("不换键改 payload 重发");
  await expect(page.getByRole("button", { name: /重试|重新发送/ })).toHaveCount(
    0,
  );
  expect(requests).toEqual([]);
});
