'use strict';

// Fixed native zoom components. Only QA Shell calls run() in its approved case.
// The CLI remains component-only; it never launches a browser.
const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('node:vm');
const fs = require('node:fs');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const {createRequire} = require('node:module');

const PINS = Object.freeze({nodeVersion: 'v24.21.0', playwrightVersion: '1.64.0'});
const ROOT_WINDOW = Object.freeze({schema: 'v41-root-runtime-authorization-v1', marker: 'ROOT_EXACT_REVIEWED_WINDOW'});
const COOKIE_SCOPE_FAILURE = 'NATIVE_ONLY_OWNED_LOOPBACK_COOKIES_REQUIRED';
const WINDOW_FAILURE = 'NATIVE_ROOT_RUNTIME_AUTHORIZATION_REQUIRED';

function check(condition, reason) {
  if (!condition) throw new Error(reason);
}

function origin(value) {
  const url = new URL(value);
  check(url.protocol === 'http:' && url.hostname === '127.0.0.1', 'EXACT_OWNED_LOOPBACK_HTTP_REQUIRED');
  check(!url.username && !url.password && !url.search && !url.hash, 'ORIGIN_CREDENTIAL_QUERY_FRAGMENT_REFUSED');
  check(url.pathname === '/' && url.port && Number(url.port) >= 1024, 'EXPLICIT_ORIGIN_PORT_REQUIRED');
  return url.origin;
}

function paths(caseDirectory) {
  check(typeof caseDirectory === 'string' && path.isAbsolute(caseDirectory), 'ABSOLUTE_CASE_REQUIRED');
  check(path.resolve(caseDirectory) === caseDirectory && !caseDirectory.split(path.sep).includes('..'), 'CANONICAL_CASE_REQUIRED');
  return Object.freeze({
    caseDirectory,
    profile: path.join(caseDirectory, 'profile'),
    extension: path.join(caseDirectory, 'extension'),
    screenshots: path.join(caseDirectory, 'screenshots'),
    processes: path.join(caseDirectory, 'processes'),
    observations: path.join(caseDirectory, 'zoom-observations.json'),
  });
}

function launchOptions(caseDirectory, browserRuntime) {
  const owned = paths(caseDirectory);
  check(path.isAbsolute(browserRuntime.executablePath), 'NATIVE_ABSOLUTE_EXECUTABLE_REQUIRED');
  return {
    headless: false,
    channel: 'chromium',
    executablePath: browserRuntime.executablePath,
    viewport: null,
    args: [
      '--disable-extensions-except=' + owned.extension,
      '--load-extension=' + owned.extension,
      '--window-size=1440,1000',
    ],
  };
}

function extensionFiles(allowedOrigin) {
  const allowed = origin(allowedOrigin);
  // Host match permissions cannot constrain the port. Worker code additionally
  // checks the complete origin and exact requested tab URL before every call.
  const manifest = {
    manifest_version: 3,
    name: 'Owned native zoom witness',
    version: '0.0.1',
    host_permissions: ['http://127.0.0.1/*'],
    background: {service_worker: 'worker.js'},
  };
  const worker = `'use strict';
const ALLOWED_ORIGIN=${JSON.stringify(allowed)};
let boundTab=null;
let events=[];
chrome.runtime.onInstalled.addListener(()=>{});
chrome.tabs.onZoomChange.addListener(event=>{
  if(event.tabId===boundTab) events.push({tabId:event.tabId,oldZoomFactor:event.oldZoomFactor,newZoomFactor:event.newZoomFactor,zoomSettings:event.zoomSettings});
});
globalThis.nativeZoom=async ({targetUrl,factor})=>{
  const target=new URL(targetUrl);
  if(target.origin!==ALLOWED_ORIGIN || target.username || target.password || target.hash) throw new Error('TARGET_ORIGIN_REFUSED');
  if(factor!==1 && factor!==2) throw new Error('FIXED_NATIVE_FACTORS_ONLY');
  const candidates=(await chrome.tabs.query({})).filter(tab=>tab.url===target.href);
  if(candidates.length!==1 || !Number.isInteger(candidates[0].id)) throw new Error('ONE_EXACT_OWNED_TAB_REQUIRED');
  boundTab=candidates[0].id; events=[];
  const before=await chrome.tabs.getZoom(boundTab);
  await chrome.tabs.setZoomSettings(boundTab,{mode:'automatic',scope:'per-tab'});
  await chrome.tabs.setZoom(boundTab,factor);
  const actual=await chrome.tabs.getZoom(boundTab);
  const settings=await chrome.tabs.getZoomSettings(boundTab);
  if(actual!==factor || settings.mode!=='automatic' || settings.scope!=='per-tab') throw new Error('NATIVE_ZOOM_READBACK_DIFFERED');
  return {tabId:boundTab,origin:target.origin,pathname:target.pathname,before,actual,settings,events:events.slice()};
};
globalThis.nativeZoomRead=async ({targetUrl})=>{
  const target=new URL(targetUrl);
  if(target.origin!==ALLOWED_ORIGIN || target.username || target.password || target.hash) throw new Error('TARGET_ORIGIN_REFUSED');
  const tab=await chrome.tabs.get(boundTab);
  if(tab.url!==target.href) throw new Error('OWNED_TAB_NAVIGATED_REAPPLY_ZOOM');
  return {tabId:boundTab,actual:await chrome.tabs.getZoom(boundTab),settings:await chrome.tabs.getZoomSettings(boundTab),events:events.slice()};
};
`;
  return {'manifest.json': JSON.stringify(manifest, null, 2) + '\n', 'worker.js': worker};
}

// Evaluate only after Root's later exact URL/profile/window authorization.
async function setNativeZoom(worker, targetUrl, factor) {
  return worker.evaluate(async input => {
    if (typeof globalThis.nativeZoom !== 'function') throw new Error('OWNED_EXTENSION_NOT_READY');
    return globalThis.nativeZoom(input);
  }, {targetUrl, factor});
}

async function readNativeZoom(worker, targetUrl) {
  return worker.evaluate(async input => {
    if (typeof globalThis.nativeZoomRead !== 'function') throw new Error('OWNED_EXTENSION_NOT_READY');
    return globalThis.nativeZoomRead(input);
  }, {targetUrl});
}

async function geometry(page) {
  return page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const body = document.body ? getComputedStyle(document.body) : null;
    return {
      innerWidth, innerHeight, outerWidth, outerHeight,
      devicePixelRatio,
      screen: {width: screen.width, height: screen.height, availWidth: screen.availWidth, availHeight: screen.availHeight},
      visualViewport: visualViewport ? {width: visualViewport.width, height: visualViewport.height, scale: visualViewport.scale} : null,
      rootCss: {zoom: root.zoom, transform: root.transform},
      bodyCss: body ? {zoom: body.zoom, transform: body.transform} : null,
    };
  });
}

function requireNative200(baseline, readback) {
  check(baseline.actual === 1 && readback.actual === 2, 'ACTUAL_NATIVE_FACTORS_REQUIRED');
  check(baseline.tabId === readback.tabId && Number.isInteger(readback.tabId), 'SAME_EXACT_TAB_REQUIRED');
  for (const observation of [baseline, readback]) {
    check(observation.settings.mode === 'automatic' && observation.settings.scope === 'per-tab', 'BROWSER_AUTOMATIC_PER_TAB_REQUIRED');
  }
  check(readback.events.some(event => event.tabId === readback.tabId && event.oldZoomFactor === 1 && event.newZoomFactor === 2), 'NATIVE_ZOOM_EVENT_REQUIRED');
  return {status: 'NATIVE_FACTOR_2_CONFIRMED_ONLY', visualAcceptance: 'SEPARATE_SCREENSHOT_AND_SCENARIO_REVIEW_REQUIRED'};
}

function selfTest() {
  let checks = 0;
  const count = fn => {fn(); checks++;};
  count(() => assert.equal(origin('http://127.0.0.1:13460'), 'http://127.0.0.1:13460'));
  for (const invalid of ['https://example.com', 'http://localhost:13460', 'http://127.0.0.1', 'http://name:secret@127.0.0.1:13460', 'http://127.0.0.1:13460/?token=x']) {
    count(() => assert.throws(() => origin(invalid)));
  }
  count(() => assert.throws(() => paths('/tmp/../existing-profile')));
  count(() => {
    const options = launchOptions('/tmp/owned-uncreated-zoom-case', {executablePath: '/fixture/browser'});
    assert.equal(options.headless, false); assert.equal(options.viewport, null);
    assert.equal(options.executablePath, '/fixture/browser');
    assert.equal(options.args.length, 3);
    assert.equal('deviceScaleFactor' in options, false);
  });
  count(() => {
    const files = extensionFiles('http://127.0.0.1:13460');
    const manifest = JSON.parse(files['manifest.json']);
    assert.equal(manifest.permissions, undefined);
    assert.equal(manifest.content_scripts, undefined);
    assert.equal(manifest.externally_connectable, undefined);
    new vm.Script(files['worker.js']); // Compile only: no chrome calls or worker started.
  });
  const baseline = {tabId: 7, actual: 1, settings: {mode: 'automatic', scope: 'per-tab'}};
  const observation = {tabId: 7, actual: 2, settings: {mode: 'automatic', scope: 'per-tab'}, events: [{tabId: 7, oldZoomFactor: 1, newZoomFactor: 2}]};
  count(() => assert.equal(requireNative200(baseline, observation).status, 'NATIVE_FACTOR_2_CONFIRMED_ONLY'));
  count(() => assert.throws(() => requireNative200(baseline, {...observation, actual: 1})));
  count(() => assert.throws(() => requireNative200(baseline, {...observation, settings: {mode: 'manual', scope: 'per-tab'}})));
  count(() => assert.throws(() => requireNative200(baseline, {...observation, tabId: 9})));
  count(() => assert.throws(() => requireNative200(baseline, {...observation, events: []})));
  return {status: 'PURE_COMPONENT_CHECKS_PASS', checks, browserLaunches: 0, profilesCreated: 0, nativeZoom: 'NOT_RUN', screenshots: 'NOT_RUN', S01: 'NOT_RUN'};
}


/**
 * QA-only interface, after the same visitor's three Shell widths and BEFORE logout:
 *
 * await run({
 *   case: ownedCase,                    // exact Root OwnedManifest; shell_navigation
 *   browserRuntime: {                  // Root PRIVATE safe binding, no defaults
 *     executablePath, executableSha256, frameworkPath, frameworkSha256,
 *     nodeSha256, playwrightVersion: '1.64.0'
 *   },
 *   shell: {cookies, context},          // current Shell cookies + verified Session.context
 *   currentShopId                      // that Shell's already selected/verified shop
 * });
 *
 * Fixed pages: /v4/dashboard and /v4/products. Fresh 0700 profile; no storage copy,
 * bootstrap, POST, logout or new visitor. The original Shell remains responsible
 * for logout AFTER this promise settles. Receipt:
 *   <case.directory>/native-zoom/receipt.json
 * Screenshots: dashboard/products-100.png, -200.png, products-200-bottom.png.
 * A successful capture is PENDING_VISUAL_REVIEW, never human acceptance.
 */
const CONTEXT_KEYS = ['tenant_id', 'organization_id', 'principal_id', 'reset_epoch', 'auth_generation'];
const ROOT = path.resolve(__dirname, '../../..');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

function ownerJSON(filename) {
  check(path.isAbsolute(filename) && fs.realpathSync(path.dirname(filename)) === path.dirname(filename), 'NATIVE_CANONICAL_PRIVATE_PATH_REQUIRED');
  const fd = fs.openSync(filename, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
  try {
    const stat = fs.fstatSync(fd);
    check(stat.isFile() && stat.uid === process.getuid() && (stat.mode & 0o777) === 0o600 && stat.size <= 2000000, 'NATIVE_OWNER_600_INPUT_REQUIRED');
    return JSON.parse(fs.readFileSync(fd, 'utf8'));
  } finally { fs.closeSync(fd); }
}

function writeNew(filename, value) {
  fs.writeFileSync(filename, value, {flag: 'wx', mode: 0o600});
}

function sourceEvidence(ownedCase) {
  const git = args => execFileSync('git', args, {cwd: ROOT, encoding: 'utf8', timeout: 5000}).trim();
  check(git(['rev-parse', 'HEAD']) === ownedCase.source_sha && git(['rev-parse', 'HEAD^{tree}']) === ownedCase.source_tree && !git(['status', '--porcelain']), 'NATIVE_EXACT_CLEAN_SOURCE_REQUIRED');
  for (const [name, digest] of Object.entries(ownedCase.inputs)) {
    check(!path.isAbsolute(name) && !name.split('/').includes('..') && sha(fs.readFileSync(path.join(ROOT, name))) === digest, 'NATIVE_PUBLIC_INPUT_CHANGED');
  }
  return {head: ownedCase.source_sha, tree: ownedCase.source_tree, moduleSha256: sha(fs.readFileSync(__filename)), inputs: ownedCase.inputs};
}

function toolEvidence(runtime) {
  check(process.version === PINS.nodeVersion && runtime.playwrightVersion === PINS.playwrightVersion, 'NATIVE_FIXED_TOOL_VERSION_REQUIRED');
  const files = [[runtime.executablePath, runtime.executableSha256], [runtime.frameworkPath, runtime.frameworkSha256], [process.execPath, runtime.nodeSha256]];
  const result = {};
  for (const [filename, digest] of files) {
    check(typeof filename === 'string' && path.isAbsolute(filename) && /^[a-f0-9]{64}$/.test(digest), 'NATIVE_EXPLICIT_TOOL_PIN_REQUIRED');
    const actual = fs.realpathSync(filename);
    check(fs.statSync(actual).isFile() && sha(fs.readFileSync(actual)) === digest, 'NATIVE_TOOL_BYTES_DIFFER');
    result[actual] = digest;
  }
  const load = createRequire(path.join(ROOT, 'frontend/package.json'));
  const packageFile = load.resolve('playwright/package.json');
  check(JSON.parse(fs.readFileSync(packageFile, 'utf8')).version === runtime.playwrightVersion, 'NATIVE_PLAYWRIGHT_VERSION_DIFFER');
  result[packageFile] = sha(fs.readFileSync(packageFile));
  return {files: result, load};
}

function processRows() {
  const output = execFileSync('/bin/ps', ['-axo', 'pid=,ppid=,pgid=,uid=,lstart=,command='], {env: {PATH: '/usr/bin:/bin', LC_ALL: 'C'}, encoding: 'utf8', timeout: 1500});
  return output.trim().split('\n').filter(Boolean).map(line => {
    const fields = line.trim().split(/\s+/);
    check(fields.length >= 10 && fields.slice(0, 4).every(x => /^\d+$/.test(x)), 'NATIVE_PROCESS_INVENTORY_INVALID');
    return {pid: +fields[0], ppid: +fields[1], pgid: +fields[2], uid: +fields[3], birth: fields.slice(4, 9).join(' '), command: fields.slice(9).join(' ')};
  });
}

function processWitness(profile, known) {
  const rows = processRows(), byPid = new Map(rows.map(row => [row.pid, row]));
  const marker = '--user-data-dir=' + profile;
  const roots = rows.filter(row => row.command.includes(marker) && [' ', undefined].includes(row.command[row.command.indexOf(marker) + marker.length]));
  function below(row, parentPid) {
    const seen = new Set();
    while (row && !seen.has(row.pid)) {
      if (row.ppid === parentPid) return true;
      seen.add(row.pid); row = byPid.get(row.ppid);
    }
    return false;
  }
  for (const row of roots) check(row.uid === process.getuid() && (below(row, process.pid) || known.get(row.pid)?.birth === row.birth), 'NATIVE_PROFILE_PROCESS_OWNERSHIP_UNKNOWN');
  for (const row of rows) {
    if (roots.some(root => row.pid === root.pid || below(row, root.pid))) {
      check(row.uid === process.getuid() && row.pid !== process.pid, 'NATIVE_CHILD_IDENTITY_INVALID');
      known.set(row.pid, {pid: row.pid, ppid: row.ppid, pgid: row.pgid, uid: row.uid, birth: row.birth});
    }
  }
  const alive = rows.filter(row => known.get(row.pid)?.birth === row.birth);
  return {profileProcesses: roots.map(row => row.pid), alive: alive.map(row => ({pid: row.pid, ppid: row.ppid, pgid: row.pgid, uid: row.uid, birth: row.birth}))};
}

function sameContext(expected, measured, shopId = null) {
  check(expected && measured && CONTEXT_KEYS.every(key => expected[key] !== undefined && expected[key] === measured[key]), 'NATIVE_SHELL_IDENTITY_CHANGED');
  check(measured.shop_id === shopId, 'NATIVE_SHOP_CONTEXT_DIFFERED');
}

function safeFailure(error) {
  return {type: error?.name || 'Error', code: /^NATIVE_[A-Z0-9_]+$/.test(error?.message || '') ? error.message : 'NATIVE_BROWSER_OR_COMPONENT_FAILURE'};
}

async function run({case: ownedCase, browserRuntime, shell, currentShopId}) {
  check(ownedCase?.scenario === 'shell_navigation' && ownedCase.uid === process.getuid(), 'NATIVE_APPROVED_SHELL_CASE_REQUIRED');
  const caseDir = ownedCase.directory;
  check(path.isAbsolute(caseDir) && fs.realpathSync(caseDir) === caseDir && (fs.statSync(caseDir).mode & 0o777) === 0o700 && fs.statSync(caseDir).uid === process.getuid(), 'NATIVE_NEW_OWNED_CASE_DIRECTORY_REQUIRED');
  const auth = ownerJSON(path.join(caseDir, 'runtime-authorization.json'));
  check(ROOT_WINDOW.schema === auth.schema_version && ROOT_WINDOW.marker === auth.authority, WINDOW_FAILURE);
  for (const key of ['source_sha', 'source_tree', 'project', 'database', 'test_image', 'pg_image', 'scenario', 'uid', 'api_port', 'web_port', 'starts_at', 'deadline', 'parent_deadline']) check(auth[key] === ownedCase[key], 'NATIVE_CASE_AUTHORIZATION_DIFFERED');
  check(auth.case_directory === caseDir, 'NATIVE_CASE_AUTHORIZATION_DIFFERED');
  const verification = ownerJSON(path.join(caseDir, 'api/owner-setup-verification.json'));
  check(verification.status === 'VERIFIED' && verification.source_sha === ownedCase.source_sha && verification.database === ownedCase.database && verification.image_id === ownedCase.test_image, 'NATIVE_REAL_OWNER_VERIFICATION_REQUIRED');
  const start = Date.parse(ownedCase.starts_at), end = Date.parse(ownedCase.deadline), started = Date.now();
  check(Number.isFinite(start) && Number.isFinite(end) && start <= started && started < end - 180000, 'NATIVE_ROOT_WORK_WINDOW_INACTIVE');
  const monoEnd = performance.now() + end - started;
  const left = cleanup => Math.min(end - Date.now(), monoEnd - performance.now()) - (cleanup ? 0 : 180000);
  const timeout = (cap = 15000, cleanup = false) => {const value = Math.min(cap, left(cleanup)); check(value > 0, 'NATIVE_DEADLINE_EXHAUSTED'); return value;};
  async function limited(promise, cap, cleanup = false) {
    let timer;
    try {return await Promise.race([promise, new Promise((_, reject) => {timer = setTimeout(() => reject(new Error('NATIVE_OPERATION_TIMEOUT')), timeout(cap, cleanup));})]);}
    finally {clearTimeout(timer);}
  }
  const webOrigin = origin('http://127.0.0.1:' + ownedCase.web_port), apiOrigin = origin('http://127.0.0.1:' + ownedCase.api_port);
  check(/^[a-f0-9-]{36}$/i.test(currentShopId || '') && Array.isArray(shell?.cookies) && shell.cookies.length > 0 && shell.context?.shop_id === null, 'NATIVE_EXISTING_SHELL_SESSION_REQUIRED');
  for (const key of CONTEXT_KEYS) check(shell.context[key] !== undefined, 'NATIVE_SHELL_CONTEXT_REQUIRED');
  const cookies = shell.cookies.map(cookie => {
    check(cookie.domain?.replace(/^\./, '') === '127.0.0.1' && cookie.path?.startsWith('/') && typeof cookie.value === 'string' && cookie.value && !cookie.partitionKey, COOKIE_SCOPE_FAILURE);
    return {...cookie};
  });
  check(cookies.some(cookie => cookie.name === 'commerceops_v4_demo'), 'NATIVE_CURRENT_DEMO_COOKIE_REQUIRED');
  const sourceBefore = sourceEvidence(ownedCase), toolsBefore = toolEvidence(browserRuntime);
  const directory = path.join(caseDir, 'native-zoom');
  fs.mkdirSync(directory, {mode: 0o700}); // EEXIST is a spent/new-case refusal, never replay.
  const owned = paths(directory);
  for (const name of ['profile', 'extension', 'screenshots', 'processes']) fs.mkdirSync(owned[name], {mode: 0o700});
  writeNew(path.join(directory, 'execution.once'), 'ONE_NEW_SHELL_NATIVE_ZOOM_ATTEMPT\n');
  const extension = extensionFiles(webOrigin);
  for (const [name, bytes] of Object.entries(extension)) writeNew(path.join(owned.extension, name), bytes);
  const receiptPath = path.join(directory, 'receipt.json');
  const report = {status: 'FAILED_OR_UNKNOWN', scope: 'SAME_SHELL_VISITOR_READONLY_NATIVE_200', startedUtc: new Date().toISOString(), source: sourceBefore, tools: toolsBefore.files, currentShopSha256: sha(currentShopId), shellContextSha256: sha(JSON.stringify(CONTEXT_KEYS.map(k => shell.context[k]))), cookieCount: cookies.length, profile: {path: owned.profile, mode: fs.statSync(owned.profile).mode & 0o777, uid: process.getuid()}, extensionSha256: Object.fromEntries(Object.entries(extension).map(([name, bytes]) => [name, sha(bytes)])), nativeBrowserExit: 'NOT_EXPOSED', pages: [], requests: {allowedReads: 0, refused: []}, processes: [], cleanup: {confirmed: false}, humanVisualAcceptance: 'NOT_RUN'};
  let context = null, monitor = null, monitorFailure = null, failure = null;
  const known = new Map();
  const observe = () => {try {return processWitness(owned.profile, known);} catch (error) {monitorFailure = safeFailure(error); return null;}};
  try {
    timeout();
    monitor = setInterval(observe, 250);
    const {chromium} = toolsBefore.load('playwright');
    context = await limited(chromium.launchPersistentContext(owned.profile, {...launchOptions(directory, browserRuntime), timeout: timeout(30000)}), 31000);
    check(observe()?.profileProcesses.length > 0 && !monitorFailure, 'NATIVE_PROFILE_PROCESS_NOT_BOUND');
    report.browserVersion = context.browser().version();
    context.setDefaultTimeout(timeout(15000));
    await context.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      if (['GET', 'HEAD', 'OPTIONS'].includes(request.method()) && [webOrigin, apiOrigin].includes(url.origin)) {
        report.requests.allowedReads++; await route.continue();
      } else if (url.protocol === 'chrome-extension:') {
        await route.continue();
      } else {
        report.requests.refused.push({method: request.method(), origin: url.origin, pathname: url.pathname});
        await route.abort('blockedbyclient');
      }
    });
    await context.addCookies(cookies); // Only this fresh profile receives current cookies; receipt/logs never contain their values.
    let worker = context.serviceWorkers().find(item => item.url().startsWith('chrome-extension://'));
    if (!worker) worker = await context.waitForEvent('serviceworker', {timeout: timeout(15000)});
    const workerUrl = new URL(worker.url());
    check(workerUrl.protocol === 'chrome-extension:' && /^[a-p]{32}$/.test(workerUrl.hostname) && workerUrl.pathname === '/worker.js', 'NATIVE_EXACT_EXTENSION_WORKER_REQUIRED');
    report.worker = {extensionId: workerUrl.hostname, path: workerUrl.pathname};
    const page = context.pages()[0] || await context.newPage();
    for (const [label, pathname, dataPath] of [['dashboard', '/v4/dashboard', '/api/v4/dashboard'], ['products', '/v4/products', '/api/v4/products']]) {
      timeout(); check(!monitorFailure, 'NATIVE_PROCESS_OBSERVER_FAILED');
      const targetUrl = webOrigin + pathname;
      const sessionResponse = page.waitForResponse(response => new URL(response.url()).origin === apiOrigin && new URL(response.url()).pathname === '/api/v4/demo/session', {timeout: timeout(15000)});
      const dataResponse = page.waitForResponse(response => {
        const url = new URL(response.url());
        return url.origin === apiOrigin && url.pathname === dataPath && url.searchParams.get('shop_id') === currentShopId;
      }, {timeout: timeout(20000)});
      // Handle an early navigation error without an unhandled pending waiter.
      sessionResponse.catch(() => {}); dataResponse.catch(() => {});
      await page.goto(targetUrl, {waitUntil: 'domcontentloaded', timeout: timeout(20000)});
      const sessionReply = await sessionResponse;
      check(sessionReply.status() === 200, 'NATIVE_SESSION_READ_REJECTED');
      const session = await sessionReply.json();
      sameContext(shell.context, session.context);
      check(session.status === 'OK' && session.data?.shops?.some(shop => shop.shop_id === currentShopId && Array.isArray(shop.grants) && shop.grants.some(grant => ['operator', 'approver'].includes(grant))), 'NATIVE_SAME_AUTHORIZED_SHOP_REQUIRED');
      const selector = page.getByLabel('店铺', {exact: true});
      await selector.waitFor({state: 'visible', timeout: timeout(10000)});
      check(await selector.count() === 1, 'NATIVE_ONE_SHOP_SELECTOR_REQUIRED');
      await selector.selectOption(currentShopId, {timeout: timeout(10000)});
      const dataReply = await dataResponse;
      check(dataReply.status() === 200, 'NATIVE_BUSINESS_READ_REJECTED');
      const payload = await dataReply.json(); sameContext(shell.context, payload.context, currentShopId);
      check(payload.status === 'OK' && payload.data, 'NATIVE_REAL_BUSINESS_DATA_REQUIRED');
      const rows = page.locator(label === 'products' ? 'section[aria-label="商品中心"] tbody tr' : 'table tbody tr');
      const readyUntil = performance.now() + timeout(10000);
      while (await rows.count() === 0) {check(performance.now() < readyUntil, 'NATIVE_REAL_TABLE_ROWS_REQUIRED'); await pause(50);}
      const baseline = await setNativeZoom(worker, targetUrl, 1);
      const before = await geometry(page);
      check(before.outerWidth === 1440 && before.outerHeight === 1000, 'NATIVE_ACTUAL_WINDOW_1440_1000_REQUIRED');
      const first = path.join(owned.screenshots, label + '-100.png');
      await page.screenshot({path: first, fullPage: false, scale: 'device', timeout: timeout(10000)}); fs.chmodSync(first, 0o600);
      await setNativeZoom(worker, targetUrl, 2);
      let zoom = await readNativeZoom(worker, targetUrl);
      const eventUntil = performance.now() + timeout(5000);
      while (!zoom.events.some(event => event.oldZoomFactor === 1 && event.newZoomFactor === 2)) {
        check(performance.now() < eventUntil, 'NATIVE_ZOOM_EVENT_REQUIRED'); await pause(25); zoom = await readNativeZoom(worker, targetUrl);
      }
      requireNative200(baseline, zoom);
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const after = await geometry(page);
      const second = path.join(owned.screenshots, label + '-200.png');
      await page.screenshot({path: second, fullPage: false, scale: 'device', timeout: timeout(10000)}); fs.chmodSync(second, 0o600);
      const pictures = [first, second];
      if (label === 'products') {
        await rows.last().scrollIntoViewIfNeeded({timeout: timeout(10000)});
        check((await readNativeZoom(worker, targetUrl)).actual === 2, 'NATIVE_ZOOM_CHANGED_BEFORE_BOTTOM_CAPTURE');
        const bottom = path.join(owned.screenshots, 'products-200-bottom.png');
        await page.screenshot({path: bottom, fullPage: false, scale: 'device', timeout: timeout(10000)}); fs.chmodSync(bottom, 0o600); pictures.push(bottom);
      }
      report.pages.push({label, pathname, rowCount: await rows.count(), baseline, zoom, before, after, screenshots: pictures.map(filename => {
        const bytes = fs.readFileSync(filename);
        check(bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])), 'NATIVE_REAL_PNG_REQUIRED');
        return {path: path.relative(directory, filename), sha256: sha(bytes), pixelWidth: bytes.readUInt32BE(16), pixelHeight: bytes.readUInt32BE(20)};
      })});
      check(report.requests.refused.length === 0, 'NATIVE_NONREAD_OR_EXTERNAL_REQUEST_REFUSED');
    }
    report.status = 'NATIVE_ZOOM_CAPTURED_PENDING_VISUAL_REVIEW';
  } catch (error) {
    failure = safeFailure(error); report.failure = failure;
  } finally {
    if (monitor) clearInterval(monitor);
    try {if (context) await limited(context.close(), 15000, true);} catch (error) {report.cleanup.closeFailure = safeFailure(error); failure ||= safeFailure(error);}
    try {
      let witness = processWitness(owned.profile, known);
      const until = performance.now() + timeout(3000, true);
      while ((witness.profileProcesses.length || witness.alive.length) && performance.now() < until) {await pause(50); witness = processWitness(owned.profile, known);}
      // Only exact previously witnessed same-UID PID+birth identities, never a group
      // shared with QA, are eligible for emergency shutdown of this new profile.
      for (const sig of ['SIGTERM', 'SIGKILL']) {
        if (!witness.alive.length) break;
        for (const current of witness.alive) {
          const bound = known.get(current.pid);
          check(bound && bound.birth === current.birth && bound.uid === process.getuid() && current.pid !== process.pid, 'NATIVE_EMERGENCY_PROCESS_IDENTITY_REFUSED');
          try {process.kill(current.pid, sig);} catch (error) {if (error.code !== 'ESRCH') throw error;}
        }
        await pause(Math.min(250, timeout(1000, true))); witness = processWitness(owned.profile, known);
      }
      report.processes = [...known.values()]; report.cleanup.profileProcesses = witness.profileProcesses; report.cleanup.registeredAlive = witness.alive;
      check(!witness.profileProcesses.length && !witness.alive.length, 'NATIVE_PROFILE_PROCESSES_REMAIN');
      report.cleanup.sourceAfter = sourceEvidence(ownedCase); report.cleanup.toolsAfter = toolEvidence(browserRuntime).files;
      check(JSON.stringify(report.cleanup.sourceAfter) === JSON.stringify(sourceBefore) && JSON.stringify(report.cleanup.toolsAfter) === JSON.stringify(toolsBefore.files), 'NATIVE_SOURCE_OR_TOOL_CHANGED');
      check(!monitorFailure, 'NATIVE_PROCESS_OBSERVER_FAILED'); report.cleanup.confirmed = true;
    } catch (error) {report.cleanup.failure = safeFailure(error); failure ||= safeFailure(error);}
    if (failure) report.status = 'FAILED_OR_UNKNOWN';
    report.endedUtc = new Date().toISOString();
    try {writeNew(receiptPath, JSON.stringify(report, null, 2) + '\n');} catch {failure = {code: 'NATIVE_RECEIPT_WRITE_FAILED'};}
  }
  if (failure) {const error = new Error(failure.code); error.receiptPath = receiptPath; throw error;}
  return {status: report.status, receiptPath, nativeBrowserExit: 'NOT_EXPOSED', visualAcceptance: 'PENDING_REVIEW'};
}

module.exports = {PINS, origin, paths, launchOptions, extensionFiles, setNativeZoom, readNativeZoom, geometry, requireNative200, selfTest, run};
if (require.main === module) {
  if (process.argv.length === 3 && process.argv[2] === '--self-test') {
    process.stdout.write(JSON.stringify(selfTest()) + '\n');
  } else if (process.argv.length === 2 || (process.argv.length === 3 && process.argv[2] === '--plan')) {
    process.stdout.write(JSON.stringify({status: 'COMPONENT_CANDIDATE_ONLY', pins: PINS, noLaunchingCli: true, next: 'ROOT_EXACT_PROFILE_URL_UTC_AND_IDENTITY_BOUND_PARENT_REQUIRED', runtime: 'NOT_RUN'}) + '\n');
  } else {
    process.stderr.write('EXECUTION_NOT_IMPLEMENTED_OR_AUTHORIZED_IN_COMPONENT_CANDIDATE\n');
    process.exitCode = 2;
  }
}
