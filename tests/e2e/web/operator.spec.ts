import { test, expect } from "../../../frontend/tooling/web-test";
import {
  noOverflow,
  noBusinessRequests,
  screenshot,
  safeAccess,
} from "./helpers";
test("冻结布局、导航、刷新、筛选和全量报告", async ({ page }) => {
  const requests = await noBusinessRequests(page);
  await page.goto("/tasks");
  await expect(
    page.getByRole("heading", { name: "任务中心", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".mock-banner")).toContainText("离线 Mock");
  await screenshot(page, "tasks-1440");
  await noOverflow(page);
  await page.getByRole("searchbox").fill("不存在");
  await expect(page.getByText("没有符合当前筛选的 Mock 任务。")).toBeVisible();
  await page.getByRole("searchbox").clear();
  await page.locator("[data-control=B14]").first().click();
  await expect(
    page.getByRole("heading", { name: "任务概览与结果" }),
  ).toBeVisible();
  await page.locator(".tabs [data-control=B15]").click();
  await expect(
    page.getByRole("heading", { name: "库存分析报告" }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "SKU 分析" }).getByRole("row"),
  ).toHaveCount(7);
  await expect(page.locator("#SKU-F")).toContainText("硬阻断");
  await expect(page.locator("#SKU-B")).toContainText("未知");
  await page.reload();
  await expect(page.locator("#SKU-C")).toContainText("-3");
  await screenshot(page, "report-1440");
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await noOverflow(page);
    await expect(page.locator("#SKU-F")).toBeVisible();
    await screenshot(page, `report-${width}`);
  }
  await page.locator("[data-control=B33]").click();
  await expect(page.getByText("历史冻结版本 · 只读")).toBeVisible();
  await expect(page).toHaveURL(/version=1/);
  await page.reload();
  await expect(page.getByText("历史冻结版本 · 只读")).toBeVisible();
  await page.locator("[data-control=B19]").click();
  await expect(page.getByRole("dialog")).toContainText("/ v1");
  await page.getByRole("button", { name: "关闭解释本报告" }).click();
  await page.locator("[data-control=B33]").click();
  await page.locator("[data-control=B19]").click();
  await expect(page.getByRole("dialog")).toContainText("/ v2");
  await page.getByLabel("离线解释状态样例（非业务请求）").selectOption("error");
  await expect(page.getByText("解释暂时无法读取")).toBeVisible();
  await page
    .getByLabel("离线解释状态样例（非业务请求）")
    .selectOption("loading");
  await expect(page.getByText("正在读取解释 · Mock")).toBeVisible();
  await page.keyboard.press("Escape");
  expect(requests).toEqual([]);
});
test("Dialog键盘隔离、Esc返回焦点与关闭脏草稿", async ({ page }) => {
  await page.goto("/tasks/INV-DEMO-008/report");
  const trigger = page.locator("[data-control=B18]");
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    expect(
      await page.evaluate(
        () => document.activeElement?.closest("dialog") !== null,
      ),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await trigger.focus();
  await page.keyboard.press("Space");
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await page.goto("/tasks");
  await page.locator("[data-control=B10]").first().click();
  await page.getByLabel("分析请求").fill("检查最近七天销量与库存");
  await page.locator("[data-control=B35]").click();
  await expect(page.getByText("本地草稿待确认")).toBeVisible();
  await expect(page.locator("[data-control=B01]")).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(page.getByText("草稿尚未提交", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "确认丢弃并关闭" }).click();
  await expect(dialog).not.toBeVisible();
  await page.locator("[data-control=B10]").first().click();
  await expect(page.getByLabel("分析请求")).toHaveValue("");
  await page.keyboard.press("Escape");
});
test("completed新周期空草稿、轨迹与内部状态分离", async ({ page }) => {
  await page.goto("/tasks/INV-DEMO-007");
  await expect(page.locator("[data-control=B25]")).toHaveCount(0);
  await expect(page.locator(".tabs [data-control=B17]")).toBeDisabled();
  await page.locator("[data-control=B46]").click();
  await expect(page.getByLabel("分析请求")).toHaveValue("");
  await expect(page.getByRole("dialog")).toContainText("不继承旧批准");
  await page.keyboard.press("Escape");
  await expect(
    page.getByText(
      "源业务任务已完成（固定 Mock）。下一周期必须重新分析和审批。",
    ),
  ).toBeVisible();
  await page.goto("/tasks/INV-DEMO-007/report");
  await expect(
    page.getByRole("table", { name: "SKU 分析" }).getByRole("row"),
  ).toHaveCount(3);
  await page.locator("[data-control=B19]").click();
  await expect(page.getByRole("dialog")).toContainText("REPORT-DEMO-007");
  await expect(page.getByRole("dialog")).not.toContainText("REPORT-DEMO-008");
  await page.keyboard.press("Escape");
  await page.goto("/tasks/INV-DEMO-008/events");
  await expect(page.locator("[data-control=B09]")).toHaveCount(0);
  await page.getByText("节点 / Tool / 时间与 Token").click();
  await expect(page.getByText(/Token、费用、Checkpoint/)).toBeVisible();
  await screenshot(page, "events-1440");
  await page.goto("/replenishment-items/RI-DEMO-002");
  await expect(page.getByText("同步失败", { exact: true })).toBeVisible();
  await expect(page.getByText("待跟进", { exact: true })).toBeVisible();
  await expect(page.locator("[data-control=B26]")).toHaveCount(0);
  await page.goto("/tasks/not-authorized");
  await safeAccess(page);
});
test("登录壳不建立模拟身份、200%等效布局范围", async ({ page }) => {
  const requests = await noBusinessRequests(page);
  await page.goto("/login");
  await expect(page.locator("[data-control=B11]")).toBeDisabled();
  await expect(page.getByLabel("密码")).toBeDisabled();
  await expect(page.getByRole("combobox")).toHaveCount(0);
  await screenshot(page, "login-1440");
  // 1440 desktop at 200% browser zoom has a 720 CSS-pixel layout viewport.
  // This checks equivalent CSS viewport reflow, not manual browser zoom or human QA.
  await page.setViewportSize({ width: 720, height: 500 });
  await page.goto("/tasks/INV-DEMO-008/report");
  await noOverflow(page);
  await expect(page.locator("#SKU-F")).toBeVisible();
  await screenshot(page, "report-zoom-equivalent-720");
  expect(requests).toEqual([]);
});

test("无效版本不回落最新、未生成报告不展示预生成事实", async ({ page }) => {
  await page.goto("/tasks/INV-DEMO-008/report?version=999");
  await safeAccess(page);
  await expect(page).toHaveURL(/\/access$/);
  await page.goto("/tasks/INV-DEMO-006/report");
  await expect(
    page.getByRole("heading", { name: "报告尚未生成", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#SKU-A")).toHaveCount(0);
});
