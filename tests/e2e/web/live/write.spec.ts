import { test, expect } from "../../../../frontend/tooling/web-test";
import type {
  Page,
  BrowserContext,
} from "../../../../frontend/tooling/web-test";
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import {
  ownedEndpoints,
  assertOwnedListener,
  assertOwnedBuild,
} from "../owned-listeners";
const root = resolve(__dirname, "../../../.."),
  dir = process.env.COMMERCEOPS_B02_PRIVATE_DIR!;
const read = (file: string) =>
  JSON.parse(readFileSync(resolve(dir, file), "utf8"));
const windowInfo = read("window.json"),
  accounts = read("web-accounts.json"),
  facts = read("write-facts.json"),
  base = read("web-facts.json"),
  API = windowInfo.api_origin;
for (const endpoint of ownedEndpoints(
  windowInfo,
  process.env.COMMERCEOPS_LIVE_WEB_URL,
))
  assertOwnedListener(
    execFileSync(
      "lsof",
      ["-nP", `-iTCP:${endpoint.port}`, "-sTCP:LISTEN", "-t"],
      { encoding: "utf8" },
    ),
    endpoint.pid,
  );
assertOwnedBuild(
  windowInfo.build_id,
  readFileSync(resolve(root, "frontend/.next/BUILD_ID"), "utf8"),
);
if (Date.now() >= Date.parse(windowInfo.stop_at_utc))
  throw new Error("owned window expired");
const contexts = new Map<string, BrowserContext>();
test.beforeAll(async ({ browser }) => {
  const ready = JSON.parse(
    execFileSync(
      resolve(root, ".venv/bin/python"),
      [resolve(root, "tests/e2e/web/live_ready.py"), dir],
      { cwd: root, env: { ...process.env, PYTHONPATH: root } },
    ).toString(),
  );
  test.setTimeout(330000);
  if (ready.wait_ms)
    await new Promise((resolve) => setTimeout(resolve, ready.wait_ms));
  for (const role of ["operator", "approver", "admin", "dual"]) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    });
    contexts.set(role, context);
    const page = await context.newPage();
    await page.goto(windowInfo.web_origin + "/login");
    await expect(page.locator("#live-login")).toBeVisible();
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
  for (const c of contexts.values()) await c.close();
});
async function pageFor(role: string) {
  const page = await contexts.get(role)!.newPage();
  return page;
}
async function settle(page: Page) {
  await page.goto("about:blank");
  await page.close();
}
async function decision(page: Page, kind: string, action: string) {
  await page.goto(
    windowInfo.web_origin + "/approvals/" + facts.records[kind].approval,
  );
  await expect(page.locator('[data-control="' + action + '"]')).toBeEnabled();
  await page.locator('[data-control="' + action + '"]').click();
  await page.getByRole("button", { name: "确认并准备原请求" }).click();
  await page.locator('[data-action="send-original"]').click();
  await expect(
    page.getByText("意见已记录 · 执行待处理", { exact: true }),
  ).toBeVisible();
}
async function screenshot(page: Page, name: string) {
  expect(await page.locator('input[type="password"]').count()).toBe(0);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({
    path: resolve(root, "frontend/evidence/b03/" + name + ".png"),
    fullPage: true,
  });
}

test("普通批准/十次原字节回放，只有一决定/不显示执行成功", async () => {
  const page = await pageFor("approver");
  const digests: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/decision"))
      digests.push(
        createHash("sha256").update(request.postData()!).digest("hex"),
      );
  });
  try {
    await decision(page, "approve", "B02");
    for (let n = 0; n < 9; n++) {
      await page.locator('[data-action="send-original"]').click();
      await expect(page.locator('[data-action="send-original"]')).toBeEnabled();
    }
    await page.locator('[data-action="read-original"]').click();
    await expect(
      page.getByText("意见已记录 · 执行待处理", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("main")).toContainText("duplicate true");
    expect(digests).toHaveLength(10);
    expect(new Set(digests).size).toBe(1);
    writeFileSync(
      resolve(root, "frontend/evidence/b03/replay.json"),
      JSON.stringify(
        {
          posts: digests.length,
          distinct_original_byte_digests: new Set(digests).size,
          byte_digest: digests[0],
        },
        null,
        2,
      ),
    );
    await screenshot(page, "approve-receipt-1440");
  } finally {
    await settle(page);
  }
});
test("普通拒绝与完整两项假设拒绝，状态/同步独立", async () => {
  const page = await pageFor("approver");
  try {
    await decision(page, "reject", "B03");
    await expect(page.getByRole("main")).toContainText("reject");
    await decision(page, "decline", "B05");
    await expect(page.getByRole("main")).toContainText("reject_assumptions");
    await expect(page.getByRole("main")).toContainText(
      "不是执行、采购或入库成功",
    );
  } finally {
    await settle(page);
  }
});
test("20SKU联合一次完整确认，无默认勾选/普通批准禁用、键盘Escape及1280/390", async () => {
  const page = await pageFor("approver");
  try {
    await page.goto(
      windowInfo.web_origin + "/approvals/" + facts.records.combined20.approval,
    );
    await expect(
      page.getByRole("table", { name: "完整审批清单" }).locator(".fact-row"),
    ).toHaveCount(20);
    await expect(page.locator('[data-control="B02"]')).toBeDisabled();
    await expect(page.locator('[data-control="B04"]')).toBeDisabled();
    await expect(page.locator('input[type="checkbox"]:checked')).toHaveCount(0);
    await page.locator('input[type="checkbox"]').first().check();
    await page.locator('[data-control="B04"]').click();
    await expect(page.getByRole("dialog")).not.toContainText("nonce");
    await page.keyboard.press("Escape");
    await expect(page.locator('[data-control="B04"]')).toBeFocused();
    await page.setViewportSize({ width: 1280, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await screenshot(page, "assumptions-1280");
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(page.locator(".fact-row")).toHaveCount(20);
    await screenshot(page, "assumptions-390");
    await page.locator('[data-control="B04"]').click();
    await page.getByRole("button", { name: "确认并准备原请求" }).click();
    await page.locator('[data-action="send-original"]').click();
    await expect(
      page.getByText("意见已记录 · 执行待处理", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("main")).toContainText(
      "approve_with_assumptions",
    );
  } finally {
    await settle(page);
  }
});
test("真实API漏/多/重复假设及错误版本拒绝，不以UI替身当业务", async () => {
  const page = await pageFor("approver");
  try {
    await page.goto(
      windowInfo.web_origin +
        "/approvals/" +
        facts.records.second_combined.approval,
    );
    const statuses = await page.evaluate(
      async ({ api, id }) => {
        const s = await (
          await fetch(api + "/api/v1/auth/session", { credentials: "include" })
        ).json();
        const a = await (
          await fetch(api + "/api/v1/approvals/" + id, {
            credentials: "include",
          })
        ).json();
        const p = a.plan;
        const results = [];
        for (const keys of [
          [],
          ["unknown-extra"],
          [
            ...p.required_assumptions.map((x: { key: string }) => x.key),
            p.required_assumptions[0].key,
          ],
        ]) {
          const r = await fetch(api + "/api/v1/approvals/" + id + "/decision", {
            method: "POST",
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": s.csrf_token,
            },
            body: JSON.stringify({
              schema_version: "p3-web-v1",
              request_key: crypto.randomUUID(),
              approval_id: id,
              plan_id: p.plan_id,
              plan_version: p.plan_version,
              plan_hash: p.plan_hash,
              action: "approve_with_assumptions",
              acknowledged_assumption_keys: keys,
              nonce: a.nonce,
            }),
          });
          results.push({ status: r.status, code: (await r.json()).error.code });
        }
        const wrongVersion = await fetch(
          api + "/api/v1/approvals/" + id + "/decision",
          {
            method: "POST",
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": s.csrf_token,
            },
            body: JSON.stringify({
              schema_version: "p3-web-v1",
              request_key: crypto.randomUUID(),
              approval_id: id,
              plan_id: p.plan_id,
              plan_version: p.plan_version + 1,
              plan_hash: p.plan_hash,
              action: "approve_with_assumptions",
              acknowledged_assumption_keys: p.required_assumptions.map(
                (x: { key: string }) => x.key,
              ),
              nonce: a.nonce,
            }),
          },
        );
        results.push({
          status: wrongVersion.status,
          code: (await wrongVersion.json()).error.code,
        });
        return results;
      },
      { api: API, id: facts.records.second_combined.approval },
    );
    expect(statuses.every((x) => x.status === 409 || x.status === 422)).toBe(
      true,
    );
    await page.goto(
      windowInfo.web_origin +
        "/approvals/" +
        facts.records.second_combined.approval,
    );
    await expect(page.locator('[data-control="B04"]')).toBeDisabled();
    await expect(page.getByRole("main")).toContainText("尚无决定记录");
  } finally {
    await settle(page);
  }
});
test("真实决定冲突不产生相反意见，原键仍可回读", async () => {
  const page = await pageFor("approver");
  try {
    await page.goto(
      windowInfo.web_origin +
        "/approvals/" +
        facts.records.second_combined.approval,
    );
    const result = await page.evaluate(
      async ({ api, id }) => {
        const s = await (
          await fetch(api + "/api/v1/auth/session", { credentials: "include" })
        ).json();
        const a = await (
          await fetch(api + "/api/v1/approvals/" + id, {
            credentials: "include",
          })
        ).json();
        const p = a.plan;
        const body = {
          schema_version: "p3-web-v1",
          request_key: crypto.randomUUID(),
          approval_id: id,
          plan_id: p.plan_id,
          plan_version: p.plan_version,
          plan_hash: p.plan_hash,
          action: "reject_assumptions",
          acknowledged_assumption_keys: [],
          nonce: a.nonce,
        };
        const post = (payload: unknown) =>
          fetch(api + "/api/v1/approvals/" + id + "/decision", {
            method: "POST",
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": s.csrf_token,
            },
            body: JSON.stringify(payload),
          });
        const first = await post(body);
        const changed = await post({
          ...body,
          action: "approve_with_assumptions",
          acknowledged_assumption_keys: p.required_assumptions.map(
            (x: { key: string }) => x.key,
          ),
        });
        const opposite = await post({
          ...body,
          request_key: crypto.randomUUID(),
          action: "approve_with_assumptions",
          acknowledged_assumption_keys: p.required_assumptions.map(
            (x: { key: string }) => x.key,
          ),
        });
        const receipt = await fetch(
          api + "/api/v1/requests/" + body.request_key + "?operation=decision",
          { credentials: "include" },
        );
        return {
          first: first.status,
          changed: {
            status: changed.status,
            code: (await changed.json()).error.code,
          },
          opposite: {
            status: opposite.status,
            code: (await opposite.json()).error.code,
          },
          receipt: receipt.status,
        };
      },
      { api: API, id: facts.records.second_combined.approval },
    );
    expect(result).toEqual({
      first: 200,
      changed: { status: 409, code: "IDEMPOTENCY_CONFLICT" },
      opposite: { status: 409, code: "DECISION_CONFLICT" },
      receipt: 200,
    });
    writeFileSync(
      resolve(root, "frontend/evidence/b03/conflicts.json"),
      JSON.stringify(result, null, 2),
    );
  } finally {
    await settle(page);
  }
});
test("实际T3提交后丢ACK：unknown不自动POST，GET原键恢复，同键十次不换键", async () => {
  const page = await pageFor("approver");
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().includes("/decision")) posts++;
  });
  try {
    await page.route(
      API + "/api/v1/approvals/" + facts.records.unknown.approval + "/decision",
      async (route) => {
        const response = await route.fetch();
        expect(response.status()).toBe(200);
        await route.abort("failed");
      },
    );
    await page.goto(
      windowInfo.web_origin + "/approvals/" + facts.records.unknown.approval,
    );
    await page.locator('[data-control="B02"]').click();
    await page.getByRole("button", { name: "确认并准备原请求" }).click();
    await page.locator('[data-action="send-original"]').click();
    await expect(
      page.getByText("提交结果待核实", { exact: true }),
    ).toBeVisible();
    expect(posts).toBe(1);
    await page.unrouteAll();
    await page.locator('[data-action="read-original"]').click();
    await expect(
      page.getByText("意见已记录 · 执行待处理", { exact: true }),
    ).toBeVisible();
    expect(posts).toBe(1);
    await page.locator('[data-action="send-original"]').click();
    await expect(page.getByRole("main")).toContainText("duplicate true");
    expect(posts).toBe(2);
  } finally {
    await settle(page);
  }
});
test("operator可信P2报告创建新P3，不复活源completed；new_cycle明确参数新键", async () => {
  const page = await pageFor("operator");
  try {
    await page.goto(
      windowInfo.web_origin +
        "/tasks/" +
        facts.records.combined20.source_task +
        "/report?report_id=" +
        facts.records.combined20.report,
    );
    await page
      .getByRole("button", { name: "从此冻结报告创建正式补货任务" })
      .click();
    await page.getByRole("button", { name: "准备本次正式任务请求" }).click();
    await page.locator('[data-action="send-original"]').click();
    await expect(
      page.getByText("正式任务创建回执", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "关闭创建正式补货任务" }).click();
    await page.goto(windowInfo.web_origin + "/tasks");
    await page
      .getByRole("button", { name: "创建正式任务", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "准备本次正式任务请求" }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "确认结构化参数" }).click();
    await page.getByRole("button", { name: "准备本次正式任务请求" }).click();
    await page.locator('[data-action="send-original"]').click();
    await expect(
      page.getByText("正式任务创建回执", { exact: true }),
    ).toBeVisible();
  } finally {
    await settle(page);
  }
});
test("指定版本只读/真实expiry禁用，admin/跨店兼任不隐含决定权", async () => {
  const page = await pageFor("approver");
  try {
    await page.goto(
      windowInfo.web_origin +
        "/tasks/" +
        facts.records.second_combined.task +
        "/plans/1",
    );
    await expect(page.locator('[data-control="B04"]')).toBeDisabled();
    await page.goto(
      windowInfo.web_origin + "/approvals/" + facts.records.expiry.approval,
    );
    const wait = Math.max(
      0,
      Date.parse(facts.records.expiry.expires_at) - Date.now() + 1200,
    );
    test.setTimeout(90000);
    if (wait) await new Promise((resolve) => setTimeout(resolve, wait));
    await page.reload();
    await expect(page.locator('[data-control="B02"]')).toBeDisabled();
  } finally {
    await settle(page);
  }
  for (const role of ["admin", "dual"]) {
    const p = await pageFor(role);
    try {
      await p.goto(
        windowInfo.web_origin +
          "/approvals/" +
          facts.records.second_combined.approval,
      );
      await expect(p).toHaveURL(/\/access$/);
      await expect(p.locator('[data-control="B04"]')).toHaveCount(0);
    } finally {
      await settle(p);
    }
  }
});
test("受控PG superseded状态禁止旧版本决定；不宣称A03重观察", async () => {
  execFileSync(
    resolve(root, ".venv/bin/python"),
    [
      resolve(root, "tests/e2e/web/live_write_probe.py"),
      dir,
      "controlled-supersede",
    ],
    { cwd: root, env: { ...process.env, PYTHONPATH: root } },
  );
  const page = await pageFor("approver");
  try {
    await page.goto(
      windowInfo.web_origin + "/approvals/" + facts.records.supersede.approval,
    );
    await expect(page.locator('[data-control="B02"]')).toBeDisabled();
    await expect(page.locator('[data-control="B04"]')).toBeDisabled();
    await expect(page.locator('[data-action="send-original"]')).toHaveCount(0);
  } finally {
    await settle(page);
  }
});
test("预备决定后真实撤权：原提交401清业务缓存/确认，不换键", async () => {
  const page = await pageFor("approver");
  try {
    await page.goto(
      windowInfo.web_origin + "/approvals/" + facts.records.revocation.approval,
    );
    await page.locator('[data-control="B02"]').click();
    await page.getByRole("button", { name: "确认并准备原请求" }).click();
    await expect(page.locator('[data-action="send-original"]')).toBeVisible();
    execFileSync(
      resolve(root, ".venv/bin/python"),
      [
        resolve(root, "tests/e2e/web/live_write_probe.py"),
        dir,
        "revoke-approver",
      ],
      { cwd: root, env: { ...process.env, PYTHONPATH: root } },
    );
    await page.locator('[data-action="send-original"]').click();
    await expect(page.locator("#live-login")).toBeVisible();
    await expect(page.locator('[data-action="send-original"]')).toHaveCount(0);
    await expect(page.getByRole("main")).not.toContainText(
      facts.records.revocation.task,
    );
  } finally {
    await settle(page);
  }
});
