// B04 live suite preparation. It must be run only after Root authorizes a newly
// registered owned PG/API/Next window; this file does not create any services.
import { test, expect } from "../../../../frontend/tooling/web-test";
import type {
  BrowserContext,
  Page,
} from "../../../../frontend/tooling/web-test";
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { verifyReadResponse } from "../../../../frontend/lib/p3-live-client";
import { explanationBound } from "../../../../frontend/lib/p3-present";
import type { DTO } from "../../../../frontend/lib/p3-present";
import {
  ownedEndpoints,
  assertOwnedListener,
  assertOwnedBuild,
  readOwnedListener,
} from "../owned-listeners";
const root = resolve(__dirname, "../../../..");
const directory = process.env.COMMERCEOPS_B02_PRIVATE_DIR;
if (!directory || process.env.COMMERCEOPS_WEB_BATCH !== "b04")
  throw new Error("Explicit authorized B04 owned window required");
const read = (name: string) =>
  JSON.parse(readFileSync(resolve(directory!, name), "utf8"));
const windowInfo = read("window.json"),
  accounts = read("web-accounts.json");
// The new window's own seeder records resources; never read an old author's fixture.
const facts = read("b04-facts.json");
for (const endpoint of ownedEndpoints(
  windowInfo,
  process.env.COMMERCEOPS_LIVE_WEB_URL,
))
  assertOwnedListener(readOwnedListener(endpoint.port), endpoint.pid);
assertOwnedBuild(
  windowInfo.build_id,
  readFileSync(resolve(root, "frontend/.next/BUILD_ID"), "utf8"),
);
if (Date.now() >= Date.parse(windowInfo.stop_at_utc))
  throw new Error("Owned B04 window expired");
const contexts = new Map<string, BrowserContext>();
test.beforeAll(async ({ browser }) => {
  test.setTimeout(330000);
  const ready = JSON.parse(
    execFileSync(
      resolve(root, ".venv/bin/python"),
      [resolve(root, "tests/e2e/web/live_ready.py"), directory!],
      {
        cwd: root,
        env: { ...process.env, PYTHONPATH: `${resolve(root, "backend/src")}:${root}` },
        encoding: "utf8",
      },
    ),
  );
  if (Date.now() + ready.wait_ms >= Date.parse(windowInfo.stop_at_utc))
    throw new Error("Owned window insufficient for natural login rate wait");
  if (ready.wait_ms)
    await new Promise((resolve) => setTimeout(resolve, ready.wait_ms));
  for (const role of process.env.COMMERCEOPS_B04_SCOPE === "read_tail"
    ? ["operator", "admin", "late_approver", "dual"]
    : ["operator", "approver", "admin", "late_approver", "dual"]) {
    const context = await browser.newContext();
    contexts.set(role, context);
    const page = await context.newPage();
    await page.goto(windowInfo.web_origin + "/login");
    await page
      .locator("#live-login")
      .evaluate(
        (el, value) => ((el as HTMLInputElement).value = value),
        accounts[role].login,
      );
    await page
      .locator("#live-password")
      .evaluate(
        (el, value) => ((el as HTMLInputElement).value = value),
        accounts[role].password,
      );
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await expect(
      page.locator('[data-source-mode="live-session"]'),
    ).toBeVisible();
    await page.goto("about:blank");
    await page.close();
  }
});
test.afterAll(async () => {
  for (const context of contexts.values()) await context.close();
});
async function withPage(role: string, work: (page: Page) => Promise<void>) {
  const page = await contexts.get(role)!.newPage();
  try {
    await work(page);
  } finally {
    await page.goto("about:blank");
    await page.close();
  }
}
test("真实永久执行与item状态/sync独立，20项分页与末项详情", async () => {
  await withPage("approver", async (page) => {
    await page.goto(windowInfo.web_origin + "/tasks/" + facts.completed_task);
    await expect(page.getByRole("main")).toContainText("Worker 执行回执");
    await expect(page.getByRole("main")).toContainText(
      "不推断这些工作项已跟进完成",
    );
    await page.goto(windowInfo.web_origin + "/replenishment-items");
    await expect(page.locator(".list-row")).toHaveCount(20);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page
      .locator(".list-row")
      .last()
      .getByRole("link", { name: "查看工作项" })
      .click();
    await expect(page.getByRole("main")).toContainText("读取时内部项事实");
  });
});
test("真实T6 Unicode原因/原键回放：一次版本推进与原receipt，终态无重开", async () => {
  await withPage("approver", async (page) => {
    await page.goto(
      windowInfo.web_origin + "/replenishment-items/" + facts.resolve_item,
    );
    await page.locator('[data-control="B26"]').focus();
    await page.keyboard.press("Enter");
    await page
      .locator("#resolve-reason")
      .fill("\u001f内部跟进 e\u0301\ufeff\u0085");
    await page.getByRole("button", { name: "确认原因并准备原请求" }).click();
    await expect(
      page.locator('[data-action="resolve-original"]'),
    ).toBeFocused();
    await page.keyboard.press("Space");
    await expect(
      page.getByText("内部跟进已记录", { exact: true }),
    ).toBeVisible();
    await page.getByText("原请求技术详情与受控恢复", { exact: true }).focus();
    await page.keyboard.press("Enter");
    for (let n = 0; n < 9; n++) {
      await page.locator('[data-action="resolve-original"]').click();
      await expect(
        page.locator('[data-action="resolve-original"]'),
      ).toBeEnabled();
    }
    await page.locator('[data-action="resolve-receipt"]').click();
    await expect(page.getByRole("dialog")).toContainText("v2");
    await page.keyboard.press("Escape");
    await expect(page.getByText("终态只读", { exact: true })).toBeVisible();
    await expect(page.locator('[data-control="B26"]')).toHaveCount(0);
    await page.reload();
    await expect(page.locator('[data-control="B27"]')).toHaveCount(0);
  });
});
test("真实迟来同店approver可处理而来源隐藏；operator/admin不借审批/业务权", async () => {
  await withPage("late_approver", async (page) => {
    await page.goto(
      windowInfo.web_origin +
        "/replenishment-items/" +
        facts.hidden_source_item,
    );
    await expect(page.locator('[data-control="B37"]')).toHaveCount(0);
    await expect(page.locator('[data-control="B27"]')).toBeEnabled();
    await page.locator('[data-control="B27"]').click();
    await page
      .locator("#resolve-reason")
      .fill("仅内部关闭，来源按当前查看权受限");
    await page.getByRole("button", { name: "确认原因并准备原请求" }).click();
    await page.locator('[data-action="resolve-original"]').click();
    await expect(
      page.getByText("内部跟进已记录", { exact: true }),
    ).toBeVisible();
  });
  await withPage("operator", async (page) => {
    await page.goto(
      windowInfo.web_origin + "/replenishment-items/" + facts.operator_item,
    );
    await expect(page.locator('[data-control="B26"]')).toHaveCount(0);
  });
  await withPage("admin", async (page) => {
    await page.goto(windowInfo.web_origin + "/replenishment-items");
    await expect(page).toHaveURL(/\/access$/);
    await expect(page.locator(".list-row")).toHaveCount(0);
  });
});
// Concurrent decisions/resolutions, controlled ACK loss/revocation, new-cycle and
// native200 probes will be bound to fresh recorded resources at window dispatch.
// Their real execution and PG counts remain not_run at this code-only freeze.

test("实际T6 commit后受控丢ACK：原GET/同字节恢复，focus不丢原操作", async () => {
  await withPage("approver", async (page) => {
    const endpoint =
      windowInfo.api_origin +
      "/api/v1/replenishment-items/" +
      facts.unknown_item +
      "/resolve";
    const bodies: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url() === endpoint)
        bodies.push(
          createHash("sha256").update(request.postData()!).digest("hex"),
        );
    });
    await page.route(endpoint, async (route) => {
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      await route.abort("failed");
    });
    await page.goto(
      windowInfo.web_origin + "/replenishment-items/" + facts.unknown_item,
    );
    await page.locator('[data-control="B27"]').click();
    await page.locator("#resolve-reason").fill("受控ACK丢失原请求关闭");
    await page.getByRole("button", { name: "确认原因并准备原请求" }).click();
    await page.locator('[data-action="resolve-original"]').click();
    await expect(
      page.getByText("内部项提交待核实", { exact: true }),
    ).toBeVisible();
    await page.getByText("原请求技术详情与受控恢复", { exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(page.locator('[data-action="resolve-original"]')).toBeDisabled();
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(
      page.locator('[data-action="resolve-original"]'),
    ).toBeVisible();
    expect(bodies).toHaveLength(1);
    await page.unrouteAll();
    await page.locator('[data-action="resolve-receipt"]').click();
    await expect(
      page.getByText("内部跟进已记录", { exact: true }),
    ).toBeVisible();
    expect(bodies).toHaveLength(1);
    await page.locator('[data-action="resolve-original"]').click();
    await expect(page.getByRole("dialog")).toContainText("duplicate true");
    expect(bodies).toHaveLength(2);
    expect(new Set(bodies).size).toBe(1);
    writeFileSync(
      resolve(root, "frontend/evidence/b04-live/ack.json"),
      JSON.stringify(
        {
          actual_posts: bodies.length,
          distinct_original_byte_digests: new Set(bodies).size,
          digest: bodies[0],
          fault: "controlled ACK abort after real commit",
          automatic_repost: 0,
        },
        null,
        2,
      ),
    );
  });
});
test("两当前approver同时complete/close只有一赢家，不产生第二版本或相反动作", async () => {
  const first = await contexts.get("approver")!.newPage(),
    second = await contexts.get("late_approver")!.newPage();
  try {
    for (const [page, action] of [
      [first, "B26"],
      [second, "B27"],
    ] as const) {
      await page.goto(
        windowInfo.web_origin + "/replenishment-items/" + facts.concurrent_item,
      );
      await page.locator(`[data-control="${action}"]`).click();
      await page.locator("#resolve-reason").fill("两个真实当前权限主体竞态");
      await page.getByRole("button", { name: "确认原因并准备原请求" }).click();
      await expect(
        page.locator('[data-action="resolve-original"]'),
      ).toBeVisible();
    }
    await Promise.all([
      first.locator('[data-action="resolve-original"]').click(),
      second.locator('[data-action="resolve-original"]').click(),
    ]);
    await expect
      .poll(
        async () =>
          Number(
            await first
              .getByText("内部跟进已记录", { exact: true })
              .isVisible(),
          ) +
          Number(
            await second
              .getByText("内部跟进已记录", { exact: true })
              .isVisible(),
          ),
      )
      .toBe(1);
    const loser = (await first
      .getByText("内部跟进已记录", { exact: true })
      .isVisible())
      ? second
      : first;
    await expect(loser.getByRole("dialog")).toContainText(
      /工作项版本已改变|工作项已进入终态/,
    );
  } finally {
    await first.goto("about:blank");
    await second.goto("about:blank");
    await first.close();
    await second.close();
  }
});
test("指定旧版本只读/范围兼任不拼权限；缓存GET不新增模型，newcycle独立请求", async () => {
  await withPage("operator", async (page) => {
    await page.goto(
      windowInfo.web_origin + "/tasks/" + facts.completed_task + "/plans/1",
    );
    await expect(page.locator('[data-control="B02"]')).toBeDisabled();
    await expect(page.locator('input[type="checkbox"]:checked')).toHaveCount(0);
  });
  await withPage("dual", async (page) => {
    await page.goto(
      windowInfo.web_origin + "/replenishment-items/" + facts.operator_item,
    );
    await expect(page).toHaveURL(/\/access$/);
  });
  await withPage("operator", async (page) => {
    const writes: string[] = [];
    page.on("request", (r) => {
      if (r.url().startsWith(windowInfo.api_origin) && r.method() === "POST")
        writes.push(new URL(r.url()).pathname);
    });
    await page.goto(
      windowInfo.web_origin +
        "/tasks/" +
        facts.source_task +
        "/report?report_id=" +
        facts.report,
    );
    const legacyResponse = page.waitForResponse((r) =>
      new URL(r.url()).pathname === `/api/v1/tasks/${facts.source_task}/explanation` &&
        r.request().method() === "GET",
    );
    await page.locator('[data-control="B19"]').click();
    const legacy = await legacyResponse;
    expect(legacy.status()).toBe(200);
    const legacyRead = await legacy.json() as DTO["ExplanationRead"];
    expect(verifyReadResponse("GET", `/api/v1/tasks/${facts.source_task}/explanation`, 200, legacyRead)).toBe(true);
    expect(legacyRead.explanation.schema_version).toBe("p204-read-v1");
    expect(legacyRead.explanation).toHaveProperty("child_task_id");
    await expect(page.getByRole("dialog")).toContainText("已有解释记录");
    await expect(page.getByRole("dialog")).toContainText("子 task：");
    await page.keyboard.press("Escape");
    const refs = facts.observation;
    const path = `/api/v1/tasks/${facts.completed_task}/explanation`;
    await page.goto(`${windowInfo.web_origin}/tasks/${facts.completed_task}/report?report_id=${refs.report_id}`);
    const currentResponse = page.waitForResponse((r) =>
      r.url() === `${windowInfo.api_origin}${path}?report_id=${refs.report_id}` &&
        r.request().method() === "GET",
    );
    await page.locator('[data-control="B19"]').click();
    const current = await currentResponse;
    expect(current.status()).toBe(200);
    const value = await current.json() as DTO["ExplanationRead"];
    expect(verifyReadResponse("GET", path, 200, value)).toBe(true);
    expect(value).toMatchObject({
      task_id: facts.completed_task, report_id: refs.report_id,
      explanation: {
        schema_version: "p4-p3-template-read-v1", task_id: facts.completed_task,
        source_task_id: refs.source_task_id, source_kind: "p3_observation",
        observation_id: refs.id, snapshot_id: refs.id, report_id: refs.report_id,
        facts_hash: refs.facts_hash,
        result: { narrative_mode: "template", metadata: { evidence_mode: "not_used" } },
      },
    });
    expect(value.explanation).not.toHaveProperty("child_task_id");
    for (const key of ["provider", "requested_model", "returned_model", "request_id", "usage",
      "latency_ms", "pricing_version", "cost_estimate"] as const)
      expect(value.explanation.result.metadata[key]).toBeNull();
    const reportResponse = await page.request.get(`${windowInfo.api_origin}/api/v1/tasks/${facts.completed_task}/report?report_id=${refs.report_id}`);
    expect(reportResponse.status()).toBe(200);
    expect(explanationBound(await reportResponse.json() as DTO["ReportRead"], value)).toBe(true);
    await expect(page.getByRole("dialog")).toContainText("P3 重观测");
    await expect(page.getByRole("dialog")).not.toContainText("子 task：");
    await expect(page.getByRole("dialog").locator("article.list-row")).toHaveCount(20);
    for (const ref of [facts.completed_task, refs.source_task_id, refs.id, refs.report_id, refs.facts_hash])
      await expect(page.getByRole("dialog")).toContainText(ref);
    await page.keyboard.press("Escape");
    expect(writes).toEqual([]);
    await page.goto(windowInfo.web_origin + "/tasks/" + facts.completed_task);
    await page.locator('[data-control="B46"]').click();
    await page.getByRole("button", { name: "确认结构化参数" }).click();
    await page.getByRole("button", { name: "准备本次正式任务请求" }).click();
    await page.locator('[data-action="send-original"]').click();
    await expect(
      page.getByText("正式任务创建回执", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("dialog")).not.toContainText(facts.approval);
  });
});
test("预备后真实撤权401清缓存/原操作，无新增item决定", async () => {
  await withPage("approver", async (page) => {
    await page.goto(
      windowInfo.web_origin + "/replenishment-items/" + facts.revoke_item,
    );
    await page.locator('[data-control="B26"]').click();
    await page.locator("#resolve-reason").fill("撤权前准备不得产生业务");
    await page.getByRole("button", { name: "确认原因并准备原请求" }).click();
    await expect(
      page.locator('[data-action="resolve-original"]'),
    ).toBeVisible();
    execFileSync(
      resolve(root, ".venv/bin/python"),
      [resolve(root, "tests/e2e/web/live_item_revoke.py"), directory!],
      { cwd: root, env: { ...process.env, PYTHONPATH: `${resolve(root, "backend/src")}:${root}` } },
    );
    await page.locator('[data-action="resolve-original"]').click();
    await expect(page.locator("#live-login")).toBeVisible();
    await expect(page.locator('[data-action="resolve-original"]')).toHaveCount(
      0,
    );
    await expect(page.getByRole("main")).not.toContainText(facts.revoke_item);
  });
});
