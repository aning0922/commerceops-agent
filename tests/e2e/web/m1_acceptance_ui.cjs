"use strict";
// A fixed headless M1 consumer. The product creates its own key; no body/crypto patching.
process.umask(0o077);
const fs = require("node:fs"), path = require("node:path"), crypto = require("node:crypto");
const { execFileSync } = require("node:child_process");
const { isDeepStrictEqual } = require("node:util");
const digest = (b) => crypto.createHash("sha256").update(b).digest("hex");
class Failure extends Error {
  constructor(code, dto = null, httpStatus = null) {
    super(code); this.code = code; this.dto = dto;
    this.http_status = Number.isInteger(httpStatus) && httpStatus >= 100 && httpStatus <= 599 ? httpStatus : null;
  }
}
const ensure = (ok, code, dto = null, httpStatus = null) => { if (!ok) throw new Failure(code, dto, httpStatus); };
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
// Self-contained for page.evaluate: one GET of the original key, as required by
// native requestReceipt(key, "resolve"). No POST, key creation, or retry path.
async function fetchOriginalResolve({ api, key, timeout }) {
  const url = new URL("/api/v1/requests/" + encodeURIComponent(key), api);
  url.searchParams.set("operation", "resolve");
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), timeout);
  let status = null;
  try {
    const response = await fetch(url.href, { method: "GET", credentials: "include",
      cache: "no-store", redirect: "error", signal: abort.signal });
    status = response.status;
    const text = await response.text();
    try { return { status, body: JSON.parse(text), body_json: true, transport: "RECEIVED" }; }
    catch { return { status, body: null, body_json: false, transport: "RECEIVED" }; }
  } catch {
    return { status, body: null, body_json: null,
      transport: abort.signal.aborted ? "TIMEOUT" : "NETWORK_ERROR" };
  } finally { clearTimeout(timer); }
}
function inspectOriginalResolve(value, validate, key, itemId) {
  const status = Number.isInteger(value.status) && value.status >= 100 && value.status <= 599 ? value.status : null;
  const diagnostic = { operation: "resolve", method: "GET", http_status: status,
    body_json: value.body_json === true ? true : value.body_json === false ? false : null,
    schema_valid: null, dto: null, code: "ORIGINAL_GET_FAILED", accepted: false };
  if (value.transport === "TIMEOUT") diagnostic.code = "ORIGINAL_GET_TIMEOUT";
  else if (value.transport === "EVALUATION_FAILED") diagnostic.code = "ORIGINAL_GET_EVALUATION_FAILED";
  else if (value.transport !== "RECEIVED") diagnostic.code = "ORIGINAL_GET_NETWORK_FAILED";
  else if (value.body_json !== true) diagnostic.code = "ORIGINAL_GET_JSON_INVALID";
  else {
    try { validate("GET", "/api/v1/requests/" + key, status, value.body); diagnostic.schema_valid = true; }
    catch (error) {
      diagnostic.schema_valid = false;
      diagnostic.dto = error instanceof Failure ? error.dto : null;
      diagnostic.code = "ORIGINAL_GET_DTO_INVALID";
      return diagnostic;
    }
    if (status === 200) {
      const receipt = value.body.receipt;
      if (value.body.request_key === key && receipt.operation === "resolve" &&
        receipt.result.request_key === key && receipt.result.item.item_id === itemId) {
        diagnostic.code = "ORIGINAL_GET_VERIFIED"; diagnostic.accepted = true;
      } else diagnostic.code = "ORIGINAL_GET_BINDING_INVALID";
    }
  }
  return diagnostic;
}
const REAL_READONLY = "persisted_real_v2_readonly";
function evidenceMode(input) {
  const mode = input.evidence_mode === undefined ? "lab_mock" : input.evidence_mode;
  ensure(["lab_mock", REAL_READONLY].includes(mode), "EVIDENCE_MODE_INVALID");
  ensure(mode !== REAL_READONLY || (["page", "replay"].includes(input.stage) &&
    input.case_kind === "recover_single_item" && input.item_count === 1 && uuid(input.request_key)),
  "REAL_READONLY_SCOPE_INVALID");
  ensure(mode !== REAL_READONLY || input.screenshot_name == null ||
    input.screenshot_name === "page-persisted-v2-readonly.png", "REAL_SCREENSHOT_NAME_INVALID");
  return mode;
}
// These are existing A artifacts, not caller-supplied expected action/reason/status.
// Their hashes must be selected by the authorized outer owner. The browser cannot
// independently attest which image serves a port; A retains live ownership checks.
function readonlyBinding(input, human, base, handoff, manifest) {
  const c = human.capture_context, r = human.receipt, p = base.projection;
  ensure(c && r && p && human.business === "closed/v2" && human.human_reported_once === true &&
    isDeepStrictEqual(human.request_key, input.request_key) &&
    isDeepStrictEqual(c.request_key, input.request_key) &&
    c.item_id === input.item_id && c.task_id === input.task_id &&
    c.case_kind === input.case_kind && c.expected_item_count === input.item_count &&
    c.expected_quantity_total === input.quantity_total &&
    [c.organization_id, c.shop_id, c.principal_id, c.identity_id].every(uuid) &&
    Number.isSafeInteger(c.auth_version) && c.auth_version > 0,
  "REAL_ORIGINAL_CONTEXT_INVALID");
  ensure(isDeepStrictEqual(r.request_key, input.request_key) && r.item?.item_id === input.item_id &&
    r.item.shop_id === c.shop_id && r.item.state === "closed" && r.item.version === 2 &&
    isDeepStrictEqual(r.resolution?.request_key, input.request_key) && r.resolution.action === "close" &&
    typeof r.resolution.reason === "string" && r.resolution.reason.trim().length > 0 &&
    r.resolution.resolved_by === c.principal_id &&
    Number.isFinite(Date.parse(r.resolution.resolved_at)) &&
    r.resolution.before_version === 1 && r.resolution.after_version === 2 &&
    hash(r.resolution.resolution_payload_hash) &&
    r.resolution.resolution_payload_hash === human.semantic_hash,
  "REAL_ORIGINAL_RECEIPT_INVALID");
  const outbox = base.snapshot?.queries?.OUTBOX;
  const rows = outbox?.rows?.filter((x) => x.id === p.outbox_id);
  ensure(p.item_id === input.item_id && p.outbox_id === human.v2_outbox?.id &&
    p.version === 2 && p.status === "verified" && p.observed_version === 2 &&
    p.complete_unique_verified === true && p.verification_mode === "controlled_sdk" &&
    outbox?.status === "PASSED" && rows?.length === 1 &&
    rows[0].aggregate_id === input.item_id && rows[0].task_id === input.task_id &&
    rows[0].aggregate_version === 2 && rows[0].destination === "bitable" &&
    rows[0].organization_id === c.organization_id && rows[0].shop_id === c.shop_id &&
    ["blocked", "pending", "sending", "sent", "retry_wait", "unknown", "dead"].includes(rows[0].status),
  "REAL_BASE_HISTORY_INVALID");
  ensure(handoff.candidate?.source_sha === input.source_sha &&
    handoff.candidate.tree === input.source_tree &&
    manifest.candidate?.source_sha === input.source_sha && manifest.candidate.tree === input.source_tree &&
    handoff.web?.api_origin === input.api_origin && handoff.web.web_origin === input.web_origin &&
    handoff.resource?.run_id === input.run_id && handoff.resource.project === input.project &&
    input.original_record_ref?.sha256 === input.parent_handoff_sha256 &&
    isDeepStrictEqual(handoff.private_refs?.web_credentials, input.credentials_ref),
  "REAL_PAGE_SOURCE_INVALID");
  for (const name of ["runner", "web"]) {
    const image = handoff.candidate.actual_images?.[name];
    ensure(image && /^sha256:[a-f0-9]{64}$/.test(image.id) &&
      image.source_sha === input.source_sha && image.source_tree === input.source_tree,
    "REAL_PAGE_IMAGE_INVALID");
  }
  return { context: c, receipt: r, projection: p, outbox_status: rows[0].status };
}
function verifyReadonlySession(session, binding) {
  const p = session.principal, c = binding.context;
  ensure(p?.principal_id === c.principal_id && p.organization_id === c.organization_id &&
    isDeepStrictEqual(p.auth_version, c.auth_version) && p.linked_channels.includes("web") &&
    p.role_shop_grants.some((g) => g.shop_id === c.shop_id) &&
    session.config?.source_mode === "mock" && session.config.transport_mode === "local_http",
  "REAL_SESSION_IDENTITY_INVALID");
}
function verifyReadonlyFacts(original, current, execution, binding) {
  const r = original.receipt?.result, expected = binding.receipt, c = binding.context;
  ensure(original.status === "succeeded" && original.request_key === expected.request_key &&
    original.receipt?.operation === "resolve" && r?.request_key === expected.request_key &&
    isDeepStrictEqual(r.resolution, expected.resolution) &&
    isDeepStrictEqual(current.resolution, expected.resolution), "REAL_RESOLUTION_CHANGED");
  // Receipt sync is historical (pending); only the current item GET proves current sync.
  for (const key of ["item_id", "shop_id", "sku_key", "stock_pool_key", "quantity", "state", "version"]) {
    ensure(r.item?.[key] === expected.item[key] && current.item?.[key] === expected.item[key],
      "REAL_ITEM_CHANGED");
  }
  ensure(execution.task_id === c.task_id && execution.status === "completed" &&
    execution.item_ids.filter((id) => id === c.item_id).length === 1 && current.can_resolve === false,
  "REAL_TASK_ITEM_BINDING_INVALID");
  const sync = current.item.sync, projections = sync.projections;
  const candidates = projections.filter((p) => p.destination_alias === "Base" && p.is_current_version);
  ensure(sync.state === "synced" && candidates.length === 1, "REAL_CURRENT_SYNC_INVALID");
  const p = candidates[0];
  ensure(p.outbox_id === binding.projection.outbox_id && p.aggregate_id === c.item_id &&
    p.projection_version === 2 && p.target_version === 2 && p.observed_version === 2 &&
    p.state === "synced" && p.outbox_status === binding.outbox_status && p.complete_unique_verified === true &&
    p.verification_mode === "controlled_sdk" && ["mock", "controlled_stub"].includes(p.source_mode) &&
    p.error_code === null, "REAL_CURRENT_PROJECTION_INVALID");
  return p;
}
// Self-contained, GET only. This is also used for the current session and the
// task->item execution association, which ItemRead does not expose in its DTO.
async function fetchReadonly({ api, path: pathname, timeout }) {
  const abort = new AbortController(), timer = setTimeout(() => abort.abort(), timeout);
  try {
    const response = await fetch(new URL(pathname, api).href, { method: "GET", credentials: "include",
      cache: "no-store", redirect: "error", signal: abort.signal });
    return { status: response.status, body: await response.json() };
  } finally { clearTimeout(timer); }
}
function evidenceLabel(mode) {
  return mode === REAL_READONLY
    ? "AUTOMATIC · PG persisted-state read · MockCommerce business source · historical accepted Base v2 / controlled SDK · this run: SDK/platform writes 0 · not human observation"
    : "LAB / synthetic Mock · native business checks · Fake external transport · no real platform";
}
function checkSessionRequest(auth, method, pathname, request = null, probe = null) {
  if (method === "GET" && pathname === "/api/v1/auth/session" && auth.login_posts === 0 &&
    request !== null && typeof request === "object" && probe && probe.request === null)
    probe.request = request;
  if (method !== "POST") return;
  ensure(["/api/v1/auth/login", "/api/v1/auth/logout"].includes(pathname), "REAL_BUSINESS_POST_BLOCKED");
  const name = pathname.endsWith("/logout") ? "logout_posts" : "login_posts";
  ensure(auth[name] === 0, "REAL_AUTH_RETRY_BLOCKED");
  auth[name]++;
}
function checkSessionResponse(auth, method, pathname, status, request = null, probe = null) {
  if (![401, 403].includes(status)) return;
  // LiveConsole's first mount probes session before showing the login form.
  // Bind at request dispatch: the login can finish before this response arrives.
  // Never infer the request's phase from the login counter at response time.
  if (status === 401 && method === "GET" && pathname === "/api/v1/auth/session" &&
    request !== null && probe?.request === request && auth.anonymous_session_401 === 0) {
    auth.anonymous_session_401++; return;
  }
  throw new Failure("REAL_AUTH_REJECTED", null, status);
}
async function verifyReadonlyPage(page, binding, projection) {
  const r = binding.receipt.resolution, item = binding.receipt.item;
  const card = (title) => page.locator("section.card").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
  const visible = async (locator) => { await locator.waitFor({ state: "visible" }); ensure(await locator.count() === 1, "REAL_PAGE_FACT_MISSING"); };
  await visible(page.locator('[data-source-mode="live-session"]'));
  const summary = page.locator('[data-item-summary]');
  await visible(summary.getByText("已关闭", { exact: true }));
  await visible(summary.getByText(`${item.item_id} · ${item.sku_key}`, { exact: true }));
  await visible(summary.getByText(`pool：${item.stock_pool_key} · ${item.quantity} 件`, { exact: true }));
  const record = card("跟进记录");
  await visible(record.getByText(`原动作 ${r.action} · 原因：${r.reason}`, { exact: true }));
  await visible(record.getByText(`原处理人 ${r.resolved_by} · ${r.resolved_at}`, { exact: true }));
  await visible(record.getByText(`版本 v1 → v2 · hash ${r.resolution_payload_hash}`, { exact: true }));
  const sync = card("同步 · 独立投影事实");
  await visible(sync.getByText("协作同步：当前版本核实；请核对逐条验证模式", { exact: true }));
  const p = sync.locator('[data-projection-version="2"]');
  await visible(p.getByText("Base · 当前版本完整唯一核实（按记录验证模式）", { exact: true }));
  await visible(p.getByText("投影 v2 · 当前目标 v2 · 观察版本 v2", { exact: true }));
  await visible(p.getByText(`完整唯一核实：是 · 当前版本 · attempts：${projection.attempts}`, { exact: true }));
  await p.getByText("投影技术详情", { exact: true }).click();
  await visible(p.getByText(`原同步状态：已同步 · outbox：${projection.outbox_status} · source：${projection.source_mode} · 验证模式：受控 SDK`, { exact: true }));
  await visible(page.getByText("终态只读", { exact: true }));
  ensure(await page.locator('[data-control="B26"], [data-control="B27"]').count() === 0,
    "TERMINAL_ACTION_VISIBLE");
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
async function pollProcessAbsent(pid, deadlineMs, probe = processAbsent) {
  const started = performance.now();
  const end = started + Math.min(3000, Math.max(0, deadlineMs - Date.now()));
  let value = null, probes = 0;
  do {
    value = probe(pid); probes++;
    if (value === true) return { pid_absent: true, final_state: "ABSENT",
      timed_out: false, probes, elapsed_ms: Math.ceil(performance.now() - started) };
    const remaining = Math.min(end - performance.now(), deadlineMs - Date.now());
    if (remaining <= 0) break;
    await new Promise((resolve) => setTimeout(resolve, Math.min(50, remaining)));
  } while (performance.now() <= end && Date.now() <= deadlineMs);
  return { pid_absent: value === false ? false : null,
    final_state: value === false ? "PRESENT" : "UNKNOWN", timed_out: true,
    probes, elapsed_ms: Math.ceil(performance.now() - started) };
}
async function execute(input) {
  ensure(input.contract === "p4-acceptance-preparation-v1" && ["t6", "page", "replay"].includes(input.stage), "INPUT_INVALID");
  const mode = evidenceMode(input), realReadonly = mode === REAL_READONLY;
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
  let binding;
  if (realReadonly) {
    const human = readPrivate(input.original_record_ref, input.private_root);
    const base = readPrivate(input.accepted_base_v2_ref, input.private_root);
    const handoff = readPrivate(input.page_source_ref, input.private_root);
    const manifest = readPrivate({ path: handoff.candidate?.manifest_file,
      sha256: handoff.candidate?.manifest_sha256 }, input.private_root);
    binding = readonlyBinding(input, human, base, handoff, manifest);
    ensure(manifest.files?.["tests/e2e/web/m1_acceptance_ui.cjs"] === digest(fs.readFileSync(__filename)) &&
      manifest.files?.["frontend/lib/p3-read-schema.generated.json"] === digest(schemaBytes),
    "REAL_CONSUMER_SOURCE_INVALID");
    validate("POST", "/api/v1/replenishment-items/" + input.item_id + "/resolve", 200, binding.receipt);
  }
  const credential = readPrivate(input.credentials_ref, input.private_root);
  ensure(typeof credential.login === "string" && typeof credential.password === "string" &&
    credential.login.length > 0 && credential.password.length > 0, "CREDENTIAL_SHAPE_INVALID");
  const result = { contract: input.contract, stage: input.stage, source_sha: input.source_sha,
    source_tree: input.source_tree, run_id: input.run_id, project: input.project,
    item_id: input.item_id, task_id: input.task_id, business_posts: 0,
    case_kind: input.case_kind, item_count: input.item_count, quantity_total: input.quantity_total,
    external_origin_attempts: 0, original_key_gets: 0, screenshot: null, real_platform_pass: false };
  result.browser_source_binding = browserSource;
  if (realReadonly) Object.assign(result, { evidence_mode: mode, observer: "automatic",
    observation_scope: "current API/PG persisted state; historical accepted Base v2; not a new platform verification",
    business_source: "MockCommerce", this_consumer_sdk_calls: 0, this_consumer_platform_writes: 0,
    original_record_ref: input.original_record_ref, accepted_base_v2_ref: input.accepted_base_v2_ref,
    page_source_ref: input.page_source_ref,
    source_binding_scope: "hash-bound A handoff/manifest; live process and image ownership remains the outer owner's check",
    identity_binding_scope: "session principal/org/auth_version; web identity mapping from A original artifact",
    auth: { login_posts: 0, logout_posts: 0, anonymous_session_401: 0,
      automatic_refresh_or_relogin: 0 } });
  let browser, context, page, routeFailure, prepared, loginSession, primary;
  const anonymousProbe = { request: null };
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
    if (realReadonly) page.on("response", (response) => {
      const u = new URL(response.url());
      if (u.origin === api) {
        try { checkSessionResponse(result.auth, response.request().method(), u.pathname,
          response.status(), response.request(), anonymousProbe); }
        catch (error) { routeFailure = error; }
      }
    });
    await context.route("**/*", async (route) => {
      try {
        const request = route.request(), u = new URL(request.url());
        const logout = realReadonly && u.origin === api && u.pathname === "/api/v1/auth/logout";
        if (realReadonly && routeFailure && !logout) throw routeFailure;
        if (![api, web].includes(u.origin)) { result.external_origin_attempts++; throw new Failure("EXTERNAL_ORIGIN_BLOCKED"); }
        ensure(["GET", "HEAD", "OPTIONS"].includes(request.method()) ||
          (request.method() === "POST" && u.origin === api &&
            (u.pathname === "/api/v1/auth/login" || logout || (input.stage === "t6" && u.pathname === resolvePath))),
          "UNAPPROVED_METHOD_BLOCKED");
        if (realReadonly && u.origin === api) {
          checkSessionRequest(result.auth, request.method(), u.pathname, request, anonymousProbe);
        }
        if (request.method() === "POST" && u.origin === api && u.pathname !== "/api/v1/auth/login" && !logout) {
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
    const loginResponse = realReadonly ? page.waitForResponse((r) => r.request().method() === "POST" &&
      r.url() === api + "/api/v1/auth/login", { timeout: remaining() }).catch(() => null) : null;
    await page.getByRole("button", { name: "登录", exact: true }).click();
    if (realReadonly) {
      const response = await loginResponse;
      ensure(response && response.status() === 200, "REAL_LOGIN_FAILED", null, response?.status() ?? null);
      loginSession = await response.json();
      validate("POST", "/api/v1/auth/login", 200, loginSession);
      verifyReadonlySession(loginSession, binding);
      if (routeFailure) throw routeFailure;
    }
    await page.locator('[data-source-mode="live-session"]').waitFor();
    const currentResponse = realReadonly ? page.waitForResponse((r) => r.request().method() === "GET" &&
      r.url() === api + itemPath, { timeout: remaining() }).catch(() => null) : null;
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
    let original;
    try { original = await page.evaluate(fetchOriginalResolve,
      { api, key: result.request_key, timeout: remaining() }); }
    catch { original = { status: null, body: null, body_json: null, transport: "EVALUATION_FAILED" }; }
    result.original_key_gets++;
    const getDiagnostic = inspectOriginalResolve(original, validate, result.request_key, input.item_id);
    const getFile = path.join(input.output_directory, input.stage + "-original-get.safe.json");
    exclusiveJson(getFile, getDiagnostic);
    result.original_get_diagnostic_ref = { path: getFile, sha256: digest(fs.readFileSync(getFile)) };
    if (!getDiagnostic.accepted)
      throw new Failure(getDiagnostic.code, getDiagnostic.dto, getDiagnostic.http_status);
    result.original_get = original.body;
    if (realReadonly) {
      if (routeFailure) throw routeFailure;
      const response = await currentResponse;
      ensure(response && response.status() === 200, "REAL_ITEM_GET_FAILED");
      const current = await response.json(); validate("GET", itemPath, 200, current);
      const read = async (pathname) => {
        const value = await page.evaluate(fetchReadonly, { api, path: pathname, timeout: remaining() });
        if (routeFailure) throw routeFailure;
        ensure(value.status === 200, "REAL_READ_FAILED");
        validate("GET", pathname, 200, value.body); return value.body;
      };
      verifyReadonlySession(await read("/api/v1/auth/session"), binding);
      const execution = await read("/api/v1/tasks/" + input.task_id + "/execution");
      const projection = verifyReadonlyFacts(original.body, current, execution, binding);
      await verifyReadonlyPage(page, binding, projection);
      result.current_item = current;
      result.task_item_binding = { task_id: execution.task_id, item_id: input.item_id,
        execution_id: execution.execution_id };
      result.readonly_checks = { original_resolution_unchanged: true, task_item_bound: true,
        current_closed_v2: true, current_base_v2_synced: true,
        complete_unique_verified: true, verification_mode: projection.verification_mode,
        rendered_native_facts: true };
    }
    await page.getByText("当前版本 v2", { exact: false }).waitFor();
    ensure(await page.locator('[data-control="B27"]').count() === 0, "TERMINAL_ACTION_VISIBLE");
    if (input.screenshot_name) {
      ensure(realReadonly || ["t6-closed-v2.png", "page-after-restart.png"].includes(input.screenshot_name), "SCREENSHOT_NAME_INVALID");
      ensure(await page.locator('input[type="password"]').count() === 0, "PASSWORD_IN_CAPTURE");
      await page.evaluate(({ label, real }) => { const d = document.createElement("div"); d.textContent = label;
        d.style.cssText = "position:fixed;bottom:8px;right:8px;z-index:2147483647;background:#123246;color:white;padding:10px;font:14px sans-serif;pointer-events:none";
        if (real) d.style.maxWidth = "75vw";
        document.body.appendChild(d); }, { label: evidenceLabel(mode), real: realReadonly });
      await page.screenshot({ path: path.join(input.output_directory, input.screenshot_name), fullPage: realReadonly });
      result.screenshot = input.screenshot_name;
    }
    result.status = "PASSED_STAGE_ONLY";
  } catch (error) { primary = routeFailure || error; throw primary; }
  finally {
    try {
      if (realReadonly && loginSession) {
        const logout = await page.evaluate(async ({ api, csrf, timeout }) => {
          const abort = new AbortController(), timer = setTimeout(() => abort.abort(), timeout);
          try {
            const response = await fetch(api + "/api/v1/auth/logout", { method: "POST", credentials: "include",
              cache: "no-store", redirect: "error", signal: abort.signal,
              headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
              body: JSON.stringify({ schema_version: "p3-web-v1" }) });
            return { status: response.status, body: await response.json() };
          } finally { clearTimeout(timer); }
        }, { api, csrf: loginSession.csrf_token, timeout: remaining() });
        ensure(logout.status === 200, "REAL_LOGOUT_FAILED");
        validate("POST", "/api/v1/auth/logout", 200, logout.body);
        ensure(result.auth.login_posts === 1 && result.auth.logout_posts === 1, "REAL_AUTH_COUNTS_INVALID");
        result.auth.logout_verified = true;
      }
    } catch (error) { result.auth.cleanup_failed = true; if (!primary) primary = error; }
    finally {
      if (browser) {
        try { await browser.close(); result.browser_closed = true; }
        finally {
          if (result.browser_process) {
            const observation = await pollProcessAbsent(result.browser_process.pid, deadline);
            result.browser_pid_stopped = observation.pid_absent;
            const stopFile = path.join(input.output_directory, input.stage + "-browser-stop.json");
            exclusiveJson(stopFile, { stage: input.stage, run_id: input.run_id,
              parent_handoff_sha256: input.parent_handoff_sha256, pid: result.browser_process.pid,
              browser_closed: result.browser_closed === true, ...observation });
            result.browser_stop_ref = { path: stopFile, sha256: digest(fs.readFileSync(stopFile)) };
            ensure(result.browser_pid_stopped === true, "BROWSER_PROCESS_STOP_UNPROVED");
          }
        }
      }
    }
  }
  if (primary) throw primary;
  if (routeFailure) throw routeFailure;
  return result;
}

module.exports = { execute, readPrivate, origin, dtoErrors, responseValidator, launchBoundBrowser,
  loadBoundChromium, browserProcessReceipt, processAbsent, pollProcessAbsent,
  fetchOriginalResolve, inspectOriginalResolve, evidenceMode, evidenceLabel, readonlyBinding,
  verifyReadonlySession, verifyReadonlyFacts, verifyReadonlyPage, fetchReadonly,
  checkSessionRequest,
  checkSessionResponse };
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
      const safe = error instanceof Failure ? { code: error.code, dto: error.dto,
        ...(error.http_status === null ? {} : { http_status: error.http_status }) } :
        { code: error && error.name === "TimeoutError" ? "UI_TIMEOUT" : "UI_FAILURE", dto: null };
      process.stderr.write(JSON.stringify({ status: "FAILED", ...safe }) + "\n"); process.exitCode = 1;
    }
  })();
}
