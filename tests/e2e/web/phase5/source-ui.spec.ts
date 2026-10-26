import type {} from "./test-control";
import { test, expect } from "../../../../frontend/tooling/web-test";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
const root = resolve(__dirname, "../../../..");
const evidence = resolve(root, "runtime/m2-web-source");
let bundle: string;
test.beforeAll(() => {
  execFileSync(process.execPath, [resolve(__dirname, "build-preview.mjs")], { cwd: root, timeout: 45000 });
  bundle = readFileSync(resolve(root, ".audit/p5-source-preview/bundle.js"), "utf8");
  mkdirSync(evidence, { recursive: true, mode: 0o700 });
});
for (const width of [1440, 390]) {
  test(`Woo冻结来源/库存未知/共享池/在途null完整披露 ${width}`, async ({ page }) => {
    const network: string[] = [];
    await page.route("**/*", (route) => { network.push(route.request().url()); return route.abort(); });
    await page.setViewportSize({ width, height: 1000 });
    await page.setContent('<html><body><div id="p5-root"></div></body></html>');
    await page.addStyleTag({ content: readFileSync(resolve(root, "frontend/app/globals.css"), "utf8") });
    await page.addScriptTag({ content: bundle });
    await expect(page.locator("[data-test-banner]")).toContainText("Woo 测试店（只读）");
    await expect(page.locator("main")).toContainText("来源采集完整：是");
    await expect(page.locator("main")).toContainText("采集完整不代表库存或在途已知");
    await expect(page.locator("main")).toContainText("库存未知");
    await expect(page.locator("main")).toContainText("不按变体重复分配");
    const rows = page.locator(".fact-row");
    await expect(rows).toHaveCount(5);
    await expect(rows.nth(0)).toContainText("未知");
    await expect(rows.nth(3).getByRole("cell").nth(3)).toContainText("0");
    await expect(rows.nth(4).getByRole("cell").nth(3)).toContainText("-3");
    for (let index = 0; index < 5; index++) {
      await expect(rows.nth(index)).toContainText("null（未知）");
      await expect(rows.nth(index)).toContainText("估算不代表已知在途");
      await rows.nth(index).locator("summary").click();
    }
    await expect(rows.nth(0)).toContainText("UNKNOWN_STOCK");
    await expect(rows.nth(1)).toContainText("SHARED_POOL_UNRESOLVED");
    await page.getByRole("button", { name: "数据口径", exact: true }).click();
    await expect(page.getByRole("dialog")).toContainText("Woo 测试店（只读）");
    await expect(page.getByRole("dialog")).toContainText("observational");
    await page.getByRole("button", { name: "关闭数据口径", exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({ path: resolve(evidence, `woo-source-${width}.png`), fullPage: true });
    expect(network).toEqual([]);
  });
}
test("部分采集不假完整；Mock预览和未报告来源不被会话/传输覆盖", async ({ page }) => {
  await page.setContent('<html><body><div id="p5-root"></div></body></html>');
  await page.addScriptTag({ content: bundle });
  await page.evaluate(() => window.__p5Render("partial"));
  await expect(page.locator("main")).toContainText("来源采集完整：否");
  await expect(page.locator("main")).toContainText("PARTIAL_FAILURE");
  await page.evaluate(() => window.__p5Render("mock"));
  await expect(page.locator("[data-test-banner]")).toContainText("Mock 样本");
  await expect(page.locator("main")).not.toContainText("Woo 测试店");
  await page.evaluate(() => window.__p5Render("offline"));
  await expect(page.locator("[data-test-banner]")).toContainText("明确离线 Mock · 注入合同响应");
  await page.evaluate(() => window.__p5Render("missing"));
  await expect(page.locator("[data-test-banner]")).toContainText("当前报告来源：未报告");
  await expect(page.locator("main")).not.toContainText("Woo 测试店");
});
