"use strict";
// A fixed headless M1 consumer. The product creates its own key; no body/crypto patching.
process.umask(0o077);
const fs = require("node:fs"), path = require("node:path"), crypto = require("node:crypto");
const { execFileSync } = require("node:child_process");
const digest = (b) => crypto.createHash("sha256").update(b).digest("hex");
class Failure extends Error {
  constructor(code, dto = null) { super(code); this.code = code; this.dto = dto; }
}
const ensure = (ok, code) => { if (!ok) throw new Failure(code); };
const preparedInputInvalid = "PREPARED_INPUT_INVALID", originalRequired = "ORIGINAL_KEY_REQUIRED";
const uuid = (v) => typeof v === "string" && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(v);
const hash = (v) => typeof v === "string" && /^[0-9a-f]{64}$/.test(v);
function privateDirectory(p) {
  ensure(typeof p === "string" && path.isAbsolute(p) && fs.realpathSync(p) === p, "PRIVATE_PATH_INVALID");
  const s = fs.lstatSync(p);
  ensure(s.isDirectory() && !s.isSymbolicLink() && s.uid === process.getuid() && (s.mode & 0o777) === 0o700, "PRIVATE_PATH_INVALID");
}
function readPrivate(ref, root) {
  ensure(ref && typeof ref.path === "string" && hash(ref.sha256), "PRIVATE_REFERENCE_INVALID");
  ensure(path.isAbsolute(ref.path) && fs.realpathSync(ref.path) === ref.path &&
    ref.path.startsWith(root + path.sep), "PRIVATE_REFERENCE_INVALID");
  const fd = fs.openSync(ref.path, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
  try {
    const s = fs.fstatSync(fd);
    ensure(s.isFile() && s.uid === process.getuid() && (s.mode & 0o777) === 0o600 && s.size <= 1024 * 1024, "PRIVATE_REFERENCE_INVALID");
    const b = fs.readFileSync(fd); ensure(digest(b) === ref.sha256, "PRIVATE_HASH_MISMATCH");
    return JSON.parse(b.toString("utf8"));
  } finally { fs.closeSync(fd); }
}
function exclusiveJson(file, value) {
  const fd = fs.openSync(file, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY | fs.constants.O_NOFOLLOW, 0o600);
  try { fs.writeFileSync(fd, JSON.stringify(value)); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
}
function origin(value) {
  const u = new URL(value);
  ensure(u.protocol === "http:" && u.hostname === "127.0.0.1" && u.port &&
    u.origin === value && !u.username && !u.password, "ORIGIN_INVALID");
  return u.origin;
}
function dtoErrors(errors) {
  return (errors || []).slice(0, 8).map((e) => ({
    loc: e.instancePath.split("/").filter(Boolean).slice(0, 8).map((x) => /^[a-z_]{1,40}$/.test(x) ? x : "_field"),
    type: /^[a-zA-Z_]{1,40}$/.test(e.keyword) ? e.keyword : "validation_error",
  }));
}
function safeNumbers(value) {
  if (typeof value === "number") return Number.isSafeInteger(value);
  if (Array.isArray(value)) return value.every(safeNumbers);
  return value === null || typeof value !== "object" || Object.values(value).every(safeNumbers);
}
function responseValidator(schema, frontendModules) {
  const Ajv = require(path.join(frontendModules, "ajv/dist/2020.js"));
  const addFormats = require(path.join(frontendModules, "ajv-formats"));
  const ajv = new Ajv({ strict: false, allErrors: false, coerceTypes: false, useDefaults: false, removeAdditional: false });
  addFormats(ajv);
  ajv.addKeyword({ keyword: "ge", type: "number", schemaType: "number", validate: (bound, value) => value >= bound });
  const validators = new Map();
  return (method, endpoint, status, body) => {
    const op = schema.operations.find((o) => o.method.toUpperCase() === method &&
      new RegExp("^" + o.path.replace(/\{[^}]+\}/g, "[^/]+") + "$").test(endpoint));
    ensure(op && op.responses[String(status)], "DTO_OPERATION_INVALID");
    const key = method + op.path + status;
    if (!validators.has(key)) validators.set(key, ajv.compile({ ...op.responses[String(status)], components: schema.components }));
    const check = validators.get(key);
    ensure(safeNumbers(body), "DTO_NUMERIC_INVALID");
    if (!check(body)) throw new Failure("DTO_INVALID", dtoErrors(check.errors));
  };
}
function validateBrowserExecutable(chromium, toolchain) {
  ensure(typeof toolchain.browser_executable === "string" && path.isAbsolute(toolchain.browser_executable) &&
    fs.realpathSync(toolchain.browser_executable) === toolchain.browser_executable &&
    fs.statSync(toolchain.browser_executable).isFile() && hash(toolchain.browser_sha256) &&
    chromium.executablePath() === toolchain.browser_executable &&
    digest(fs.readFileSync(toolchain.browser_executable)) === toolchain.browser_sha256, "BROWSER_SOURCE_MISMATCH");
}
function loadBoundChromium(toolchain) {
  // The outer entry intentionally owns a private HOME. Bind only this child to
  // the already approved cache; never infer an executable from that HOME or install one.
  const corePackage = require.resolve("playwright-core/package.json", { paths: [toolchain.playwright_root] });
  ensure(JSON.parse(fs.readFileSync(corePackage)).version === toolchain.playwright_version,
    "PLAYWRIGHT_SOURCE_MISMATCH");
  const manifest = JSON.parse(fs.readFileSync(path.join(path.dirname(corePackage), "browsers.json")));
  const chromiumSource = manifest.browsers.find((b) => b.name === "chromium");
  ensure(chromiumSource && /^[0-9]{1,8}$/.test(chromiumSource.revision), "BROWSER_CACHE_SOURCE_INVALID");
  const executable = toolchain.browser_executable;
  ensure(typeof executable === "string" && path.isAbsolute(executable) &&
    fs.realpathSync(executable) === executable && fs.statSync(executable).isFile() &&
    hash(toolchain.browser_sha256) && digest(fs.readFileSync(executable)) === toolchain.browser_sha256,
    "BROWSER_SOURCE_MISMATCH");
  const expectedDirectory = "chromium-" + chromiumSource.revision;
  let directory = path.dirname(executable);
  while (path.basename(directory) !== expectedDirectory && path.dirname(directory) !== directory)
    directory = path.dirname(directory);
  ensure(path.basename(directory) === expectedDirectory, "BROWSER_CACHE_SOURCE_INVALID");
  const cacheRoot = path.dirname(directory);
  ensure(fs.realpathSync(cacheRoot) === cacheRoot && fs.statSync(cacheRoot).isDirectory(), "BROWSER_CACHE_SOURCE_INVALID");
  process.env.PLAYWRIGHT_BROWSERS_PATH = cacheRoot;
  const { chromium } = require(toolchain.playwright_root);
  validateBrowserExecutable(chromium, toolchain);
  return { chromium, source: { cache_root: cacheRoot, revision: chromiumSource.revision,
    registry_executable: chromium.executablePath(), explicit_executable: executable,
    private_home_preserved: true, install_or_fallback: false } };
}
async function launchBoundBrowser(chromium, toolchain, timeout) {
  validateBrowserExecutable(chromium, toolchain);
  return chromium.launch({ executablePath: toolchain.browser_executable, headless: true, timeout,
    args: ["--disable-background-networking", "--disable-component-update", "--no-default-browser-check"] });
}
async function browserProcessReceipt(browser, toolchain, timeout) {
  const session = await browser.newBrowserCDPSession();
  let timer;
  try {
    const value = await Promise.race([session.send("SystemInfo.getProcessInfo"),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Failure("BROWSER_PROCESS_TIMEOUT")), timeout); })]);
    const rows = value.processInfo.filter((p) => p.type === "browser");
    ensure(rows.length === 1 && Number.isSafeInteger(rows[0].id) && rows[0].id > 1 &&
      rows[0].id !== process.pid, "BROWSER_PROCESS_INVALID");
    const pid = rows[0].id;
    // Read only this newly launched browser's command path, never a process inventory/env.
    const observed = execFileSync("/bin/ps", ["-p", String(pid), "-o", "comm="], {
      encoding: "utf8", env: { LANG: "C" }, timeout: Math.min(timeout, 2000), maxBuffer: 4096 }).trim();
    ensure(path.isAbsolute(observed) && fs.realpathSync(observed) === toolchain.browser_executable &&
      digest(fs.readFileSync(observed)) === toolchain.browser_sha256, "BROWSER_PROCESS_BINARY_MISMATCH");
    return { pid, executable: observed, executable_sha256: toolchain.browser_sha256,
      ui_pid: process.pid, observation: "native browser CDP process ID plus owned PID ps comm path/hash" };
  } finally { clearTimeout(timer); }
}
function processAbsent(pid) {
  try { process.kill(pid, 0); return false; }
  catch (error) { return error.code === "ESRCH" ? true : null; }
}
async function execute(input) {
  ensure(input.contract === "p4-acceptance-preparation-v1" && ["t6", "page", "replay"].includes(input.stage), "INPUT_INVALID");
  ensure(uuid(input.item_id) && uuid(input.task_id) && hash(input.parent_handoff_sha256), "INPUT_INVALID");
  const caseCounts = { recover_single_item: 1, batch_twenty_items: 20 };
  ensure(Object.hasOwn(caseCounts, input.case_kind) && input.item_count === caseCounts[input.case_kind] &&
    typeof input.quantity_total === "string" && /^[1-9][0-9]{0,17}(\.[0-9]{1,6})?$/.test(input.quantity_total) &&
    (input.case_kind !== "batch_twenty_items" || input.quantity_total === "2000"), "CASE_CONTEXT_INVALID");
  ensure(typeof input.source_sha === "string" && /^[a-f0-9]{40}$/.test(input.source_sha), "INPUT_INVALID");
  ensure(typeof input.source_tree === "string" && /^[a-f0-9]{40}$/.test(input.source_tree), "INPUT_INVALID");
  privateDirectory(input.private_root); privateDirectory(input.output_directory);
  ensure(input.output_directory.startsWith(input.private_root + path.sep), "PRIVATE_PATH_INVALID");
  const api = origin(input.api_origin), web = origin(input.web_origin);
  ensure(api !== web, "ORIGIN_INVALID");
  const deadline = Date.parse(input.work_deadline_utc);
  ensure(Number.isFinite(deadline) && deadline > Date.now(), "WINDOW_CLOSED");
  const remaining = () => { const n = deadline - Date.now(); ensure(n > 0, "WINDOW_CLOSED"); return Math.min(n, 15000); };
  ensure(input.toolchain && process.version === input.toolchain.node_version &&
    digest(fs.readFileSync(process.execPath)) === input.toolchain.node_sha256, "NODE_SOURCE_MISMATCH");
  const pwRoot = input.toolchain.playwright_root;
  ensure(typeof pwRoot === "string" && fs.realpathSync(pwRoot) === pwRoot, "PLAYWRIGHT_SOURCE_MISMATCH");
  const packageBytes = fs.readFileSync(path.join(pwRoot, "package.json"));
  ensure(digest(packageBytes) === input.toolchain.playwright_package_sha256 &&
    JSON.parse(packageBytes).version === input.toolchain.playwright_version, "PLAYWRIGHT_SOURCE_MISMATCH");
  const { chromium, source: browserSource } = loadBoundChromium(input.toolchain);
  const schemaBytes = fs.readFileSync(input.toolchain.read_schema_path);
  ensure(digest(schemaBytes) === input.toolchain.read_schema_sha256, "DTO_SOURCE_MISMATCH");
  const schema = JSON.parse(schemaBytes);
  const validate = responseValidator(schema, input.toolchain.frontend_node_modules);
  const credential = readPrivate(input.credentials_ref, input.private_root);
  ensure(typeof credential.login === "string" && typeof credential.password === "string" &&
    credential.login.length > 0 && credential.password.length > 0, "CREDENTIAL_SHAPE_INVALID");
  const result = { contract: input.contract, stage: input.stage, source_sha: input.source_sha,
    source_tree: input.source_tree, run_id: input.run_id, project: input.project,
    item_id: input.item_id, task_id: input.task_id, business_posts: 0,
    case_kind: input.case_kind, item_count: input.item_count, quantity_total: input.quantity_total,
    external_origin_attempts: 0, original_key_gets: 0, screenshot: null, real_platform_pass: false };
  result.browser_source_binding = browserSource;
  let browser, context, page, routeFailure, prepared;
  const itemPath = "/api/v1/replenishment-items/" + input.item_id;
  const resolvePath = itemPath + "/resolve";
  const preparedFile = path.join(input.output_directory, "t6-native-request.json");
  try {
    browser = await launchBoundBrowser(chromium, input.toolchain, remaining());
    result.browser_process = await browserProcessReceipt(browser, input.toolchain, remaining());
    const startFile = path.join(input.output_directory, input.stage + "-browser-start.json");
    exclusiveJson(startFile, { stage: input.stage, run_id: input.run_id,
      parent_handoff_sha256: input.parent_handoff_sha256,
      browser_source_binding: browserSource, ...result.browser_process });
    result.browser_start_ref = { path: startFile, sha256: digest(fs.readFileSync(startFile)) };
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    page = await context.newPage(); page.setDefaultTimeout(remaining()); page.setDefaultNavigationTimeout(remaining());
    await context.route("**/*", async (route) => {
      try {
        const request = route.request(), u = new URL(request.url());
        if (![api, web].includes(u.origin)) { result.external_origin_attempts++; throw new Failure("EXTERNAL_ORIGIN_BLOCKED"); }
        ensure(["GET", "HEAD", "OPTIONS"].includes(request.method()) ||
          (request.method() === "POST" && u.origin === api &&
            (u.pathname === "/api/v1/auth/login" || (input.stage === "t6" && u.pathname === resolvePath))),
          "UNAPPROVED_METHOD_BLOCKED");
        if (request.method() === "POST" && u.origin === api && u.pathname !== "/api/v1/auth/login") {
          ensure(input.stage === "t6" && u.pathname === resolvePath && result.business_posts === 0, "EXTRA_BUSINESS_POST_BLOCKED");
          const bytes = request.postDataBuffer(), body = JSON.parse(bytes.toString("utf8"));
          ensure(Object.keys(body).sort().join(",") === ["action", "expected_version", "reason", "schema_version", "request_key"].sort().join(","), preparedInputInvalid);
          ensure(body.action === "close" && body.expected_version === 1 && body.reason === input.reason &&
            body.schema_version === "p3-web-v1" && uuid(body.request_key), "PREPARED_INPUT_INVALID");
          prepared = { contract: input.contract, parent_handoff_sha256: input.parent_handoff_sha256,
            source_sha: input.source_sha, source_tree: input.source_tree, run_id: input.run_id,
            project: input.project, task_id: input.task_id, item_id: input.item_id,
            case_kind: input.case_kind, item_count: input.item_count, quantity_total: input.quantity_total,
            request_key: body.request_key, body_sha256: digest(bytes), input: body };
          // Complete durable capture BEFORE continuing the exact original request, unchanged.
          exclusiveJson(preparedFile, prepared); result.business_posts++;
        }
        await route.continue();
      } catch (error) { routeFailure = error instanceof Failure ? error : new Failure("REQUEST_CAPTURE_FAILED"); await route.abort(); }
    });
    await page.goto(web + "/login");
    await page.locator("#live-login").fill(credential.login);
    await page.locator("#live-password").fill(credential.password);
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.locator('[data-source-mode="live-session"]').waitFor();
    await page.goto(web + "/replenishment-items/" + input.item_id);
    if (input.stage === "t6") {
      ensure(input.request_phase === "unprepared" && input.request_key === null && input.reason &&
        input.reason === input.reason.trim() && input.reason.includes("LAB"), "UNPREPARED_CONTEXT_INVALID");
      ensure(!fs.existsSync(preparedFile), "ORIGINAL_KEY_ALREADY_CAPTURED");
      await page.locator('[data-control="B27"]').waitFor();
      ensure(await page.locator('[data-control="B27"]').isEnabled(), "CLOSE_NOT_AUTHORIZED");
      await page.locator('[data-control="B27"]').click();
      await page.locator("#resolve-reason").fill(input.reason);
      await page.getByRole("button", { name: "确认原因并准备原请求", exact: true }).click();
      const response = page.waitForResponse((r) => r.request().method() === "POST" && r.url() === api + resolvePath, { timeout: remaining() }).then((r) => r, () => null);
      await page.locator('[data-action="resolve-original"]').click();
      const received = await response;
      if (routeFailure) throw routeFailure;
      ensure(received && received.status() === 200 && result.business_posts === 1 && prepared, "T6_HTTP_FAILED");
      const body = await received.json(); validate("POST", resolvePath, 200, body);
      ensure(body.request_key === prepared.request_key && body.item.item_id === input.item_id &&
        body.item.state === "closed" && body.item.version === 2 && body.duplicate === false, "T6_RESPONSE_BINDING_INVALID");
      result.typed_response = body; result.request_key = prepared.request_key;
      result.prepared_receipt = { path: preparedFile, sha256: digest(fs.readFileSync(preparedFile)) };
      await page.getByText("内部跟进已记录", { exact: true }).waitFor();
      await page.getByRole("link", { name: "查看工作项结果与同步", exact: true }).click();
    } else {
      ensure(uuid(input.request_key), originalRequired); result.request_key = input["request_key"];
    }
    const original = await page.evaluate(async ({ api, key }) => {
      const r = await fetch(api + "/api/v1/requests/" + key, { credentials: "include", cache: "no-store" });
      return { status: r.status, body: await r.json() };
    }, { api, key: result.request_key }); result.original_key_gets++;
    ensure(original.status === 200, "ORIGINAL_GET_FAILED");
    validate("GET", "/api/v1/requests/" + result.request_key, 200, original.body);
    ensure(original.body.receipt.operation === "resolve" &&
      original.body.receipt.result.request_key === result.request_key &&
      original.body.receipt.result.item.item_id === input.item_id, "ORIGINAL_GET_BINDING_INVALID");
    result.original_get = original.body;
    await page.getByText("当前版本 v2", { exact: false }).waitFor();
    ensure(await page.locator('[data-control="B27"]').count() === 0, "TERMINAL_ACTION_VISIBLE");
    if (input.screenshot_name) {
      ensure(["t6-closed-v2.png", "page-after-restart.png"].includes(input.screenshot_name), "SCREENSHOT_NAME_INVALID");
      ensure(await page.locator('input[type="password"]').count() === 0, "PASSWORD_IN_CAPTURE");
      await page.evaluate(() => { const d = document.createElement("div"); d.textContent = "LAB / synthetic Mock · native business checks · Fake external transport · no real platform";
        d.style.cssText = "position:fixed;bottom:8px;right:8px;z-index:2147483647;background:#123246;color:white;padding:10px;font:14px sans-serif;pointer-events:none"; document.body.appendChild(d); });
      await page.screenshot({ path: path.join(input.output_directory, input.screenshot_name), fullPage: false });
      result.screenshot = input.screenshot_name;
    }
    result.status = "PASSED_STAGE_ONLY";
  } finally {
    if (browser) {
      try { await browser.close(); result.browser_closed = true; }
      finally {
        if (result.browser_process) {
          result.browser_pid_stopped = processAbsent(result.browser_process.pid);
          const stopFile = path.join(input.output_directory, input.stage + "-browser-stop.json");
          exclusiveJson(stopFile, { stage: input.stage, run_id: input.run_id,
            parent_handoff_sha256: input.parent_handoff_sha256, pid: result.browser_process.pid,
            browser_closed: result.browser_closed === true, pid_absent: result.browser_pid_stopped });
          result.browser_stop_ref = { path: stopFile, sha256: digest(fs.readFileSync(stopFile)) };
          ensure(result.browser_pid_stopped === true, "BROWSER_PROCESS_STOP_UNPROVED");
        }
      }
    }
  }
  if (routeFailure) throw routeFailure;
  return result;
}

module.exports = { execute, readPrivate, origin, dtoErrors, responseValidator, launchBoundBrowser,
  loadBoundChromium, browserProcessReceipt, processAbsent };
if (require.main === module) {
  (async () => {
    try {
      const inputPath = process.argv[2], expected = process.argv[3];
      ensure(hash(expected) && typeof inputPath === "string", "INPUT_REFERENCE_INVALID");
      privateDirectory(path.dirname(inputPath));
      const input = readPrivate({ path: inputPath, sha256: expected }, path.dirname(path.dirname(inputPath)));
      const result = await execute(input);
      exclusiveJson(path.join(input.output_directory, input.stage + "-ui-result.json"), result);
      process.stdout.write(JSON.stringify({ status: result.status, stage: result.stage }) + "\n");
    } catch (error) {
      const safe = error instanceof Failure ? { code: error.code, dto: error.dto } :
        { code: error && error.name === "TimeoutError" ? "UI_TIMEOUT" : "UI_FAILURE", dto: null };
      process.stderr.write(JSON.stringify({ status: "FAILED", ...safe }) + "\n"); process.exitCode = 1;
    }
  })();
}
