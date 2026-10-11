import { test, expect } from "../../../../frontend/tooling/web-test";
import type {
  Page,
  Frame,
} from "../../../../frontend/node_modules/@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { execFileSync, spawn } from "node:child_process";
import {
  assertOwnedListener,
  assertOwnedMockProcess,
  readOwnedListener,
} from "../owned-listeners";
import { report } from "./fixtures";
import type {} from "./test-control";
const root = resolve(__dirname, "../../../..");
const evidence = resolve(root, "frontend/evidence/p4-c1");
let owned: { pid: number; buildId: string; serviceId: string };
let server: ReturnType<typeof spawn>;
let bundle: string;
test.beforeAll(() => {
  execFileSync(
    process.execPath,
    [resolve(root, "tests/e2e/web/phase4/build-preview.mjs")],
    { cwd: root },
  );
  bundle = readFileSync(resolve(root, ".audit/p4-preview/bundle.js"), "utf8");
});
test.beforeAll(async () => {
  server = spawn(
    process.execPath,
    [resolve(root, "tests/e2e/web/phase4/mock-server.mjs")],
    { cwd: root, stdio: ["ignore", "pipe", "ignore"] },
  );
  owned = await new Promise((accept, reject) => {
    const timer = setTimeout(
      () => reject(new Error("Owned Mock did not register readiness")),
      15000,
    );
    server.once("exit", () => {
      clearTimeout(timer);
      reject(new Error("Owned Mock exited before registration"));
    });
    server.stdout!.once("data", (value) => {
      clearTimeout(timer);
      accept(JSON.parse(value.toString()));
    });
  });
  assertOwnedListener(readOwnedListener(3496), owned.pid!);
  const uid = assertOwnedMockProcess(
    owned.pid!,
    resolve(root, "frontend"),
    process.pid,
  );
  mkdirSync(evidence, { recursive: true });
  writeFileSync(
    resolve(evidence, "mock-resource.json"),
    JSON.stringify(
      {
        platform: process.platform,
        uid,
        pid: owned.pid,
        build_id: owned.buildId,
        port: 3496,
        checkout: root,
        started_utc: new Date().toISOString(),
        headless: true,
        source: "component memory Mock",
        actual_api_pg_worker_provider: "not_started",
      },
      null,
      2,
    ),
  );
});
test.afterAll(async () => {
  if (server && server.exitCode === null) {
    server.kill("SIGTERM");
    await new Promise<void>((accept, reject) => {
      const timer = setTimeout(() => {
        server.kill("SIGKILL");
        reject(new Error("Owned Mock cleanup timed out"));
      }, 15000);
      server.once("exit", () => {
        clearTimeout(timer);
        accept();
      });
    });
  }
  writeFileSync(
    resolve(evidence, "mock-stop.json"),
    JSON.stringify(
      {
        stopped_utc: new Date().toISOString(),
        owned_pid: owned?.pid,
        scope: "closed only this fixture's spawned Next",
        headless: true,
      },
      null,
      2,
    ),
  );
});
const unexpected = new WeakMap<Page, string[]>();
const errors = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const calls: string[] = [];
  unexpected.set(page, calls);
  const failures: string[] = [];
  errors.set(page, failures);
  page.on("pageerror", (error) => failures.push(error.message));
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (
      url.origin !== "http://127.0.0.1:3496" ||
      req.method() !== "GET" ||
      url.pathname.startsWith("/api/")
    )
      calls.push("unexpected network operation");
  });
});
test.afterEach(async ({ page }) => {
  expect(unexpected.get(page)).toEqual([]);
  await page.goto("about:blank");
});
async function open(page: Page, mode = "actual"): Promise<Frame> {
  await page.goto("http://127.0.0.1:3496/access");
  const actual = await page
    .locator(".app-shell")
    .evaluate((el) => ({
      source: el.getAttribute("data-mock-source"),
      service: el.getAttribute("data-mock-service"),
      build: el.getAttribute("data-mock-build"),
    }));
  expect(actual).toEqual({
    source: "commerceops-b01",
    service: owned.serviceId,
    build: owned.buildId,
  });
  const links = await page
    .locator('link[rel="stylesheet"]')
    .evaluateAll((nodes) =>
      nodes.map((node) => (node as HTMLLinkElement).href),
    );
  await page.evaluate((urls) => {
    const frame = document.createElement("iframe");
    frame.id = "p4-frame";
    frame.style.cssText = "width:100%;height:100vh;border:0;display:block";
    frame.srcdoc = `<!doctype html><html lang="zh-CN"><head>${urls.map((url) => `<link rel="stylesheet" href="${url}">`).join("")}</head><body><div id="p4-root"></div></body></html>`;
    document.body.replaceChildren(frame);
  }, links);
  const iframe = page.frameLocator("#p4-frame");
  await expect(iframe.locator("#p4-root")).toBeAttached();
  const frame = page.frames().find((item) => item !== page.mainFrame())!;
  // Focus this private headless iframe before the product's focus-refresh listeners mount.
  await frame.evaluate(() => {
    window.focus();
    document.body.tabIndex = -1;
    document.body.focus();
  });
  await frame.addScriptTag({ content: bundle });
  if (!(await frame.evaluate(() => Boolean(window.__p4))))
    throw new Error(
      "Test-only component mount failed: " + errors.get(page)?.join("; "),
    );
  if (mode !== "actual")
    await frame.evaluate((value) => window.__p4.render(value), mode);
  await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
  return frame;
}
test("缓存完整metadata/usage/refs仅原GET；0与null分开，390完整依据", async ({
  page,
}) => {
  const frame = await open(page);
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("历史实际 provider 记录");
  await expect(frame.locator("dialog")).toContainText("input_tokens：100");
  await expect(frame.locator("dialog")).toContainText("latency：0ms");
  await expect(frame.locator("dialog")).toContainText(
    "cost_estimate（服务端原值）：0",
  );
  await expect(frame.locator("dialog article.list-row")).toHaveCount(20);
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((call) => call.method !== "GET"),
    ),
  ).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await frame.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await frame
    .locator("dialog")
    .screenshot({ path: resolve(evidence, "cached-390.png") });
});
test("已有模板降级/离线stub明确标识，null不补0不发新模型", async ({ page }) => {
  const frame = await open(page, "template");
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("已有确定性模板");
  await expect(frame.locator("dialog")).toContainText("NO_PROVIDER");
  await expect(frame.locator("dialog")).toContainText("input_tokens：未报告");
  await frame.evaluate(() => window.__p4.render("nullable"));
  await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("离线 stub 记录");
  await expect(frame.locator("dialog")).toContainText("latency：未报告");
});
test("NOT_READY与异refs安全错误不伪造解释；撤权清cache", async ({ page }) => {
  const frame = await open(page, "not_ready");
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("NOT_READY");
  await expect(frame.locator("dialog")).not.toContainText("input_tokens：");
  await frame.evaluate(() => window.__p4.render("bad_refs"));
  await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("不可安全读取");
  await expect(frame.locator("dialog")).not.toContainText(
    "明确离线缓存示例摘要",
  );
  await frame.evaluate(() => window.__p4.render("revoked"));
  await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("main")).toContainText(
    "身份、业务缓存与预备操作已清除",
  );
  await expect(frame.locator("dialog")).toHaveCount(0);
});
test("关闭/卸载后的迟到缓存不能填回旧抽屉或跨record", async ({ page }) => {
  const frame = await open(page, "delayed");
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("正在读取已有解释");
  await frame.getByRole("button", { name: "关闭本报告已有解释" }).click();
  await frame.evaluate(() => window.__p4.release());
  await expect(frame.locator("dialog")).toHaveCount(0);
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("正在读取已有解释");
  await frame.evaluate(() => window.__p4.render("nullable"));
  await frame.evaluate(() => window.__p4.release());
  await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
  await expect(frame.locator("dialog")).toHaveCount(0);
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("离线 stub 记录");
  await expect(frame.locator("dialog")).not.toContainText(
    "历史实际 provider 记录",
  );
});
test("M05→空授权草稿：缺参有reason，无POST；确认+B01新key后才显式提交", async ({
  page,
}) => {
  const frame = await open(page);
  await frame.locator('[data-control="B36"]').click();
  await expect(frame.locator("dialog")).toContainText(
    "不修改当前任务或待审批计划",
  );
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((call) => call.method === "POST"),
    ),
  ).toEqual([]);
  await frame.locator('[data-control="B46"]').click();
  await expect(frame.locator("dialog")).toContainText("创建正式补货任务");
  await expect(frame.getByLabel("来源方式")).toHaveCount(0);
  await frame.getByLabel("L（0–365整数）").fill("");
  await expect(frame.locator("dialog")).toContainText("缺少结构化参数 L");
  await expect(frame.locator('dialog [data-control="B01"]')).toBeDisabled();
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((call) => call.method === "POST"),
    ),
  ).toEqual([]);
  await frame.getByLabel("L（0–365整数）").fill("4");
  await frame.getByLabel("R（0–365整数）").fill("8");
  await frame.getByLabel("S（0–365整数）").fill("1");
  await frame.locator('[data-control="B35"]').click();
  await frame.locator('dialog [data-control="B01"]').click();
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((call) => call.method === "POST"),
    ),
  ).toEqual([]);
  await frame.locator('[data-action="send-original"]').click();
  await expect(frame.locator("dialog")).toContainText("正式任务创建回执");
  const calls = await frame.evaluate(() =>
    window.__p4.calls.filter((call) => call.method === "POST"),
  );
  expect(calls).toHaveLength(1);
  const body = JSON.parse(calls[0].body!);
  expect(body.mode).toBe("new_cycle");
  expect(body.parameters).toMatchObject({ L: 4, R: 8, S: 1 });
  for (const key of [
    "source_task_id",
    "source_report_id",
    "snapshot_id",
    "facts_hash",
    "approval_id",
    "nonce",
    "acknowledged_assumption_keys",
  ])
    expect(body).not.toHaveProperty(key);
  expect(body.request_key).not.toBe(report.task_id);
});
test("待审批/无operator/服务端不允许时M05具体禁用，不原地重算", async ({
  page,
}) => {
  const frame = await open(page, "pending");
  await expect(frame.locator('[data-control="B36"]')).toBeDisabled();
  await expect(frame.locator("main")).toContainText("当前任务尚未完成");
  for (const mode of ["no_role", "disabled"]) {
    await frame.evaluate((value) => window.__p4.render(value), mode);
    await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
    await expect(frame.locator('[data-control="B36"]')).toBeDisabled();
  }
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((call) => call.method === "POST"),
    ),
  ).toEqual([]);
});
