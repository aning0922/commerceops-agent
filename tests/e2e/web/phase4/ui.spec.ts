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
const evidence = resolve(
  root,
  process.env.COMMERCEOPS_WEB_BATCH === "p4-c14-template" ? "runtime/p4-c14-template/ui" :
    `frontend/evidence/${process.env.COMMERCEOPS_WEB_BATCH === "p4-c09-reviewfix" ? "p4-c09-reviewfix" : process.env.COMMERCEOPS_WEB_BATCH === "p4-c09" ? "p4-c09" : "p4-c1"}`,
);
let owned: {
  pid: number;
  buildId: string;
  serviceId: string;
  startedUtc: string;
  expiresUtc: string;
};
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
        started_utc: owned.startedUtc,
        expires_utc: owned.expiresUtc,
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
  const actual = await page.locator(".app-shell").evaluate((el) => ({
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
  if (mode === "task_c09_read_failed")
    await expect(
      frame.getByRole("heading", { name: "本次读取失败", exact: true }),
    ).toBeVisible();
  else if (mode.startsWith("task_"))
    await expect(frame.locator("[data-task-id]")).toHaveAttribute(
      "data-task-id",
      report.task_id,
    );
  else if (mode === "c2_events")
    await expect(frame.locator(".timeline li")).toHaveCount(4);
  else if (mode === "c2_items")
    await expect(frame.locator(".list-table article.list-row")).toHaveCount(20);
  else if (mode === "c2_terminal")
    await expect(frame.locator("main")).toContainText("终态只读");
  else if (mode === "c2_admin")
    await expect(frame.locator("main")).toContainText("脱敏运维摘要");
  else await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
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
test("BC02 P3原始/重观测模板无子task或模型账单，20依据/390/键盘及旧P204兼容", async ({ page }) => {
  const frame = await open(page, "p3_original");
  await frame.locator('[data-control="B19"]').focus();
  await page.keyboard.press("Enter");
  const dialog = frame.locator("dialog");
  await expect(dialog).toContainText("P3 模板");
  await expect(dialog).toContainText("P2 原始报告");
  await expect(dialog).toContainText("observation：无重观测");
  await expect(dialog).toContainText("未使用模型");
  await expect(dialog).toContainText("input_tokens：未报告");
  await expect(dialog).toContainText("latency：未报告");
  await expect(dialog).not.toContainText("子 task：");
  await expect(dialog.locator("article.list-row")).toHaveCount(20);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await frame.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(frame.locator('[data-control="B19"]')).toBeFocused();
  await frame.evaluate(() => window.__p4.render("p3_observation"));
  await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
  await frame.locator('[data-control="B19"]').click();
  await expect(dialog).toContainText("P3 重观测");
  await expect(dialog.locator("article.list-row")).toHaveCount(20);
  expect(await frame.evaluate(() => window.__p4.calls.filter((x) => x.method !== "GET"))).toEqual([]);
  await frame.evaluate(() => window.__p4.render("actual"));
  await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
  await frame.locator('[data-control="B19"]').click();
  await expect(dialog).toContainText("子 task：");
  await expect(dialog).toContainText("历史实际 provider 记录");
});
test("BC02 P3异来源/不可用不得显示模板，迟到关闭与身份清理不复活缓存", async ({ page }) => {
  const frame = await open(page, "p3_bad_source");
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("不可安全读取");
  await expect(frame.locator("dialog")).not.toContainText("不可变模板示例");
  await frame.evaluate(() => window.__p4.render("p3_unavailable"));
  await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("服务暂时不可用");
  await frame.evaluate(() => window.__p4.render("p3_delayed"));
  await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("正在读取已有解释");
  await page.keyboard.press("Escape");
  await frame.evaluate(() => window.__p4.release());
  await expect(frame.locator("dialog")).toHaveCount(0);
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("正在读取已有解释");
  await frame.evaluate(() => window.__p4.render("p3_observation"));
  await frame.evaluate(() => window.__p4.release());
  await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
  await expect(frame.locator("dialog")).toHaveCount(0);
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("P3 重观测");
  await expect(frame.locator("dialog")).not.toContainText("P2 原始报告");
  await frame.evaluate(() => window.__p4.render("p3_delayed"));
  await expect(frame.locator("main")).toContainText("全部 20 个 SKU");
  await frame.locator('[data-control="B19"]').click();
  await expect(frame.locator("dialog")).toContainText("正在读取已有解释");
  await frame.evaluate(() => window.__p4.revoke());
  await frame.evaluate(() => window.__p4.release());
  await expect(frame.locator("main")).toContainText("身份、业务缓存与预备操作已清除");
  await expect(frame.locator("dialog")).toHaveCount(0);
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

test("任务详情B46与报告同资格：pending/跨店operator/禁用无草稿；完成后只源店新key明确提交", async ({
  page,
}) => {
  const frame = await open(page, "task_pending");
  for (const mode of ["task_pending", "task_other_shop", "task_disabled"]) {
    if (mode !== "task_pending") {
      await frame.evaluate((value) => window.__p4.render(value), mode);
      await expect(frame.locator("[data-task-id]")).toHaveAttribute(
        "data-task-id",
        report.task_id,
      );
    }
    await expect(frame.locator('[data-control="B46"]')).toBeDisabled();
    await expect(frame.locator("dialog")).toHaveCount(0);
    expect(
      await frame.evaluate(() =>
        window.__p4.calls.filter((call) => call.method === "POST"),
      ),
    ).toEqual([]);
  }
  await frame.evaluate(() => window.__p4.render("task_multi_shop"));
  await expect(frame.locator('[data-control="B46"]')).toBeEnabled();
  await frame.locator('[data-control="B46"]').click();
  await expect(frame.getByLabel("来源方式")).toHaveCount(0);
  await expect(frame.getByLabel("当前operator店铺")).toHaveValue(
    "00000000-0000-4000-8000-000000000065",
  );
  await expect(
    frame.getByLabel("当前operator店铺").locator("option"),
  ).toHaveCount(1);
  await expect(frame.locator('dialog [data-control="B01"]')).toBeDisabled();
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
  expect(body.shop_id).toBe("00000000-0000-4000-8000-000000000065");
  expect(body.request_key).not.toBe(report.task_id);
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
});

test("任务详情新草稿撤权即清；卸载后迟到的completed不能复活待审批资格", async ({
  page,
}) => {
  const frame = await open(page, "task_multi_shop");
  await frame.locator('[data-control="B46"]').click();
  await frame.locator('[data-control="B35"]').click();
  await frame.locator('dialog [data-control="B01"]').click();
  await frame.evaluate(() => window.__p4.revoke());
  await expect(frame.locator("dialog")).toHaveCount(0);
  await expect(frame.locator("main")).toContainText(
    "身份、业务缓存与预备操作已清除",
  );
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((call) => call.method === "POST"),
    ),
  ).toEqual([]);
  await frame.evaluate(() => window.__p4.render("task_late_task"));
  await expect(frame.locator("main")).toContainText("正在读取当前授权记录");
  await expect
    .poll(() =>
      frame.evaluate(
        () =>
          window.__p4.calls.filter(
            (call) =>
              call.path ===
              "/api/v1/tasks/00000000-0000-4000-8000-000000000066",
          ).length,
      ),
    )
    .toBe(1);
  await frame.evaluate(() => window.__p4.render("task_pending"));
  await expect(frame.locator('[data-control="B46"]')).toBeDisabled();
  await frame.evaluate(async () => {
    window.__p4.release();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  await expect(frame.locator('[data-control="B46"]')).toBeDisabled();
  await expect(frame.locator("main")).toContainText("当前任务尚未完成");
  await expect(frame.locator("dialog")).toHaveCount(0);
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((call) => call.method === "POST"),
    ),
  ).toEqual([]);
});

test("A03旧v1核实不称当前v2；Fake sender无平台启用/外链，390无横向溢出", async ({
  page,
}) => {
  const frame = await open(page, "task_c2_history");
  await expect(frame.locator("main")).toContainText("当前目标版本尚未核实");
  await expect(frame.locator("main")).toContainText(
    "不能证明当前目标 v2 已同步",
  );
  await expect(frame.locator("main")).toContainText(
    "Fake 发送资格；不代表真实平台启用",
  );
  await expect(frame.locator("main")).toContainText(
    "真实外部发送资格：当前禁用",
  );
  await expect(frame.locator("a[href^='http']")).toHaveCount(0);
  await frame.evaluate(() => window.__p4.render("task_c2_current"));
  await expect(frame.locator("main")).toContainText(
    "当前版本离线 Fake 核实（非平台回执）",
  );
  await expect(frame.locator("[data-projection-version]")).toHaveCount(2);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await frame.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 390, height: 4096 });
  await frame
    .locator("section.card")
    .filter({
      has: frame.getByRole("heading", { name: "协作同步", exact: true }),
    })
    .screenshot({ path: resolve(evidence, "c2-sync-390.png") });
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((call) => call.method !== "GET"),
    ),
  ).toEqual([]);
});

test("A03unknown/stale与业务终态分账；20内部项/390完整，terminal无处理入口", async ({
  page,
}) => {
  const frame = await open(page, "task_c2_unknown");
  await expect(frame.locator("main")).toContainText("协作同步：结果未知");
  await expect(frame.locator("main")).toContainText("BASE_ACK_UNPROVEN");
  await expect(frame.locator("main")).toContainText("已完成");
  await frame.evaluate(() => window.__p4.render("c2_items"));
  await expect(frame.locator(".list-table article.list-row")).toHaveCount(20);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await frame.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await frame.evaluate(() => window.__p4.render("c2_terminal"));
  await expect(frame.locator("main")).toContainText("终态只读");
  await expect(frame.locator("main")).toContainText("BASE_VERSION_STALE");
  await expect(frame.locator("main")).toContainText("观察版本 v3");
  await expect(frame.locator('[data-control="B26"]')).toHaveCount(0);
  await expect(frame.locator('[data-control="B27"]')).toHaveCount(0);
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((call) => call.method !== "GET"),
    ),
  ).toEqual([]);
});

test("A03trace精确source/ref/channel，adapter不冒SDK方法或模型选择；异源拒绝不泄漏", async ({
  page,
}) => {
  const frame = await open(page, "c2_events");
  await expect(frame.locator(".timeline li")).toHaveCount(4);
  await expect(frame.locator("main")).toContainText("精确来源任务");
  await expect(frame.locator("main")).toContainText("渠道：feishu");
  await expect(frame.locator("main")).toContainText("SDK adapter 操作");
  await expect(frame.locator("main")).toContainText(
    "未报告；不能从 adapter 操作推断 SDK 方法次数",
  );
  await expect(frame.locator("main")).toContainText("未记录模型动态选择");
  await expect(frame.locator("main")).toContainText("duration 未报告");
  await expect(frame.locator('[data-control="B32"]')).toBeDisabled();
  await expect(frame.locator("a[href^='http']")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await frame.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 390, height: 4096 });
  await frame
    .locator("section.card")
    .filter({
      has: frame.getByRole("heading", { name: "实际已发生轨迹", exact: true }),
    })
    .screenshot({ path: resolve(evidence, "c2-trace-390.png") });
  await frame.evaluate(() => window.__p4.render("c2_bad_trace"));
  await expect(frame.locator("main")).toContainText("读取未完成");
  await expect(frame.locator(".timeline li")).toHaveCount(0);
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((call) => call.method !== "GET"),
    ),
  ).toEqual([]);
});

test("A03currentidentity aliases/键盘与gate理由；admin无业务导航/跨role不拼权限，撤销清旧事实", async ({
  page,
}) => {
  const frame = await open(page, "task_c2_expired");
  await expect(frame.locator("main")).toContainText("受控窗口已过期");
  await frame.locator('[data-control="B44"]').focus();
  await page.keyboard.press("Enter");
  await expect(frame.locator("dialog")).toContainText(
    "当前身份关联渠道：web、feishu",
  );
  await expect(frame.locator("dialog")).not.toContainText("open_id");
  await page.keyboard.press("Escape");
  await expect(frame.locator("dialog")).toHaveCount(0);
  await frame.evaluate(() => window.__p4.render("task_c2_worker"));
  await expect(frame.locator("main")).toContainText("Worker 未就绪");
  await frame.evaluate(() => window.__p4.render("c2_admin"));
  await expect(frame.locator("main")).toContainText("脱敏运维摘要");
  await expect(frame.locator('[data-control="B39"]')).toHaveCount(0);
  await expect(frame.locator('[data-control="B40"]')).toHaveCount(0);
  await expect(frame.locator('[data-control="B41"]')).toHaveCount(0);
  await frame.evaluate(() => window.__p4.render("c2_admin_deep"));
  await expect(frame.locator("main")).toContainText("读取未完成");
  await expect(frame.locator("[data-task-id]")).toHaveCount(0);
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((call) => call.path.startsWith("/api/v1/tasks")),
    ),
  ).toEqual([]);
  await frame.evaluate(() => window.__p4.revoke());
  await expect(frame.locator("main")).toContainText(
    "身份、业务缓存与预备操作已清除",
  );
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((call) => call.method !== "GET"),
    ),
  ).toEqual([]);
});

test("C09 GET失败与loading互斥；重读不发业务POST", async ({ page }) => {
  const frame = await open(page, "task_c09_read_failed");
  await expect(
    frame.getByRole("heading", { name: "本次读取失败", exact: true }),
  ).toBeVisible();
  await expect(
    frame.getByText("正在读取当前授权记录", { exact: true }),
  ).toHaveCount(0);
  await expect(frame.locator("[data-task-id]")).toHaveCount(0);
  await frame.locator('[data-control="B42"]').click();
  await expect(
    frame.getByRole("heading", { name: "本次读取失败", exact: true }),
  ).toBeVisible();
  expect(
    await frame.evaluate(() =>
      window.__p4.calls.filter((x) => x.method === "POST"),
    ),
  ).toEqual([]);
});

test("C09 成功/unknown先原键核实，结果下一步为主；390键盘受控恢复不自动POST", async ({
  page,
}) => {
  const frame = await open(page, "task_c09_unknown");
  await frame.locator('[data-control="B46"]').click();
  await frame.locator('[data-control="B35"]').click();
  await frame.locator('dialog [data-control="B01"]').click();
  await frame.locator('[data-action="send-original"]').click();
  await expect(
    frame.getByText("提交结果待核实", { exact: true }),
  ).toBeVisible();
  await frame.getByText("原请求技术详情与受控恢复", { exact: true }).click();
  await expect(frame.locator('[data-action="send-original"]')).toBeDisabled();
  await frame.locator('[data-action="read-original"]').click();
  const next = frame.getByRole("link", { name: "查看本次任务", exact: true });
  await expect(next).toBeFocused();
  await expect(next).toHaveAttribute(
    "href",
    "/tasks/00000000-0000-4000-8000-00000000012d",
  );
  expect(
    await frame.evaluate(
      () => window.__p4.calls.filter((x) => x.method === "POST").length,
    ),
  ).toBe(1);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await frame.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await frame.locator('[data-action="send-original"]').click();
  const posts = await frame.evaluate(() =>
    window.__p4.calls.filter((x) => x.method === "POST"),
  );
  expect(posts).toHaveLength(2);
  expect(posts[0].body).toBe(posts[1].body);
});

test("C09 409冲突禁盲重提，中文completed保持success语义", async ({ page }) => {
  const frame = await open(page, "task_c09_conflict");
  await expect(
    frame.locator(".status.success").filter({ hasText: "已完成" }),
  ).toBeVisible();
  await frame.locator('[data-control="B46"]').click();
  await frame.locator('[data-control="B35"]').click();
  await frame.locator('dialog [data-control="B01"]').click();
  await frame.locator('[data-action="send-original"]').click();
  await expect(frame.locator("dialog")).toContainText("请求内容与原请求不一致");
  await frame.getByText("原请求技术详情与受控恢复", { exact: true }).click();
  await expect(frame.locator('[data-action="send-original"]')).toBeDisabled();
  await frame.locator('[data-action="read-original"]').click();
  await expect(frame.locator("dialog")).toContainText("不解除本次冲突或拒绝");
  await expect(
    frame.getByRole("link", { name: "查看本次任务", exact: true }),
  ).toHaveCount(0);
  await expect(frame.locator('[data-action="send-original"]')).toBeDisabled();
  expect(
    await frame.evaluate(
      () => window.__p4.calls.filter((x) => x.method === "POST").length,
    ),
  ).toBe(1);
});

async function natural(frame: Frame, text: string) {
  await frame.locator('[data-control="B46"]').click();
  await frame.getByRole("button", { name: "使用自然语言请求草稿", exact: true }).click();
  await frame.getByLabel("自然语言请求草稿").fill(text);
}
async function parseNatural(frame: Frame) {
  await frame.getByRole("button", { name: "检查草稿与参数", exact: true }).click();
  await expect(frame.getByRole("heading", { name: "草稿参数与来源", exact: true })).toBeVisible();
}
test("C09 N01离线闭合ready来源窗口，B35只确认/B01鲜键显式提交，390键盘", async ({ page }) => {
  const frame = await open(page, "task_n01");
  await natural(frame, "分析库存 L=3 R=7 S=2"); await parseNatural(frame);
  await expect(frame.getByRole("dialog")).toContainText("模型未使用");
  await expect(frame.getByRole("dialog")).toContainText("R 是复查周期");
  await expect(frame.locator('dialog [data-control="B01"]')).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await frame.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await frame.locator('[data-control="B35"]').focus(); await page.keyboard.press("Enter");
  await frame.locator('dialog [data-control="B01"]').click();
  expect(await frame.evaluate(() => window.__p4.calls.filter((c) => c.path === "/api/v1/tasks" && c.method === "POST"))).toEqual([]);
  await frame.locator('[data-action="send-original"]').click();
  await expect(frame.getByRole("link", { name: "查看本次任务", exact: true })).toBeFocused();
  const posts = await frame.evaluate(() => window.__p4.calls.filter((c) => c.path === "/api/v1/tasks" && c.method === "POST"));
  expect(posts).toHaveLength(1); const input = JSON.parse(posts[0].body!);
  expect(input.mode).toBe("new_cycle"); expect(input.parameters).toMatchObject({ L: 3, R: 7, S: 2 });
  expect(input).not.toHaveProperty("text"); expect(input).not.toHaveProperty("approval_id");
});
test("C09 N01 MISSING缺项留空，人工补齐撤旧确认，不把demo改ready", async ({ page }) => {
  const frame = await open(page, "task_n01");
  await natural(frame, "分析库存 L=4"); await parseNatural(frame);
  await expect(frame.getByLabel("L（0–365整数）", { exact: true })).toHaveValue("4");
  await expect(frame.getByLabel("L（0–365整数）", { exact: true })).toBeDisabled();
  for (const name of ["R", "S"])
    await expect(frame.getByLabel(`${name}（0–365整数）`, { exact: true })).toHaveValue("");
  await expect(frame.locator('[data-control="B35"]')).toBeDisabled();
  await frame.getByLabel("R（0–365整数）", { exact: true }).fill("7");
  await frame.getByLabel("S（0–365整数）", { exact: true }).fill("2");
  await frame.locator('[data-control="B35"]').click();
  await frame.getByLabel("R（0–365整数）", { exact: true }).fill("8");
  await expect(frame.locator('dialog [data-control="B01"]')).toBeDisabled();
  await expect(frame.getByRole("dialog")).toContainText("请补齐明确参数后再确认");
  await frame.locator('[data-control="B35"]').click(); await frame.locator('dialog [data-control="B01"]').click();
  expect(await frame.evaluate(() => window.__p4.calls.filter((c) => c.path === "/api/v1/tasks" && c.method === "POST"))).toEqual([]);
});
test("C09 N01 invalid/unsupported不能确认，显式取消才另开空结构化草稿", async ({ page }) => {
  const frame = await open(page, "task_n01");
  await natural(frame, "分析库存 L=3/4 R=7 S=2"); await parseNatural(frame);
  await expect(frame.getByRole("dialog")).toContainText("原句参数未通过校验");
  await expect(frame.locator('[data-control="B35"]')).toBeDisabled();
  await frame.getByLabel("自然语言请求草稿").fill("只分析 SKU-A 最近三天 L=3 R=7 S=2"); await parseNatural(frame);
  await expect(frame.getByRole("dialog")).toContainText("此原句超出当前支持范围");
  await expect(frame.locator('dialog [data-control="B01"]')).toBeDisabled();
  await frame.getByRole("button", { name: "取消原句并改用结构化草稿", exact: true }).click();
  await expect(frame.getByLabel("自然语言请求草稿")).toHaveCount(0);
  await expect(frame.getByLabel("L（0–365整数）", { exact: true })).toHaveValue("");
  await expect(frame.locator('[data-control="B35"]')).toBeDisabled();
});
test("C09 N01迟到解析不能覆盖修改原句或撤权后的旧草稿", async ({ page }) => {
  const frame = await open(page, "task_n01_late");
  await natural(frame, "分析库存 L=3 R=7 S=2");
  await frame.getByRole("button", { name: "检查草稿与参数", exact: true }).click();
  await expect.poll(() => frame.evaluate(() => window.__p4.calls.filter((c) => c.path === "/api/v1/tasks/preflight").length)).toBe(1);
  await frame.getByLabel("自然语言请求草稿").fill("分析库存 L=4");
  await frame.evaluate(() => window.__p4.release());
  await frame.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve(null)))));
  await expect(frame.getByRole("heading", { name: "草稿参数与来源", exact: true })).toHaveCount(0);
  await expect(frame.locator('[data-control="B35"]')).toBeDisabled();
  await frame.getByLabel("自然语言请求草稿").fill("分析库存 L=3 R=7 S=2");
  await frame.getByRole("button", { name: "检查草稿与参数", exact: true }).click();
  await expect.poll(() => frame.evaluate(() => window.__p4.calls.filter((c) => c.path === "/api/v1/tasks/preflight").length)).toBe(2);
  await frame.evaluate(() => { window.__p4.revoke(); window.__p4.release(); });
  await expect(frame.getByRole("main")).toContainText("身份、业务缓存与预备操作已清除");
  await expect(frame.getByRole("dialog")).toHaveCount(0);
});
test("C09 P1 shape合法/范围内异name scalar拒绝进入确认，不发创建", async ({ page }) => {
  const frame = await open(page, "task_n01_badspan");
  await natural(frame, "分析库存 L=3 R=7 S=2");
  await frame.getByRole("button", { name: "检查草稿与参数", exact: true }).click();
  await expect(frame.getByRole("dialog")).toContainText("暂时无法安全读取服务响应");
  await expect(frame.getByRole("heading", { name: "草稿参数与来源", exact: true })).toHaveCount(0);
  await expect(frame.locator('[data-control="B35"]')).toBeDisabled();
  await expect(frame.locator('dialog [data-control="B01"]')).toBeDisabled();
  expect(await frame.evaluate(() => window.__p4.calls.filter((c) => c.path === "/api/v1/tasks" && c.method === "POST"))).toEqual([]);
});
