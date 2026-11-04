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

const SAFE_STAGES = Object.freeze(['launch', 'worker', 'navigation_session', 'shop_locate', 'shop_select', 'business_read', 'rows', 'native_zoom', 'png', 'cleanup']);
function safeStage(stage, evidence = {}) {
  check(SAFE_STAGES.includes(stage), 'NATIVE_UNSUPPORTED_SAFE_STAGE');
  check(evidence && Object.getPrototypeOf(evidence) === Object.prototype, 'NATIVE_UNSAFE_STAGE_EVIDENCE');
  const booleans = ['sessionVerified', 'shopVerified', 'businessVerified'];
  const counts = ['completedPages', 'rowCount', 'completedPngs'];
  for (const [key, value] of Object.entries(evidence)) {
    check(booleans.includes(key) ? typeof value === 'boolean' : counts.includes(key) && Number.isSafeInteger(value) && value >= 0, 'NATIVE_UNSAFE_STAGE_EVIDENCE');
  }
  return Object.freeze({stage, evidence: Object.freeze({...evidence})});
}

function pngGeometry(bytes, measured) {
  check(Buffer.isBuffer(bytes) && bytes.length >= 33 && bytes.length <= 8000000 && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) && bytes.readUInt32BE(8) === 13 && bytes.toString('ascii', 12, 16) === 'IHDR', 'NATIVE_REAL_PNG_REQUIRED');
  for (const key of ['innerWidth', 'innerHeight', 'devicePixelRatio']) check(typeof measured[key] === 'number' && Number.isFinite(measured[key]) && measured[key] > 0, 'NATIVE_FINITE_GEOMETRY_REQUIRED');
  const pixelWidth = bytes.readUInt32BE(16), pixelHeight = bytes.readUInt32BE(20);
  check(pixelWidth > 0 && pixelHeight > 0 && Math.abs(pixelWidth - measured.innerWidth * measured.devicePixelRatio) <= 2 && Math.abs(pixelHeight - measured.innerHeight * measured.devicePixelRatio) <= 2, 'NATIVE_PNG_BYTES_OR_GEOMETRY_MISMATCH');
  return {pixelWidth, pixelHeight};
}

function numericFields(value, keys) {
  return Object.fromEntries(keys.filter(key => typeof value?.[key] === 'number' && Number.isFinite(value[key])).map(key => [key, value[key]]));
}

function captureMetrics(value) {
  return Object.fromEntries(['layoutViewport', 'visualViewport', 'cssLayoutViewport', 'cssVisualViewport'].map(key => [key, numericFields(value[key], ['clientWidth', 'clientHeight', 'offsetX', 'offsetY', 'pageX', 'pageY', 'scale', 'zoom'])]));
}

async function captureNativePng(page, filename, expected, observations, limited, save = writeNew) {
  const observation = {shot: path.basename(filename), expected: numericFields(expected, ['innerWidth', 'innerHeight', 'devicePixelRatio'])};
  check(['dashboard-100.png', 'dashboard-200.png', 'products-100.png', 'products-200.png', 'products-200-bottom.png'].includes(observation.shot), 'NATIVE_FIXED_PNG_SET_REQUIRED');
  observations.push(observation);
  const end = performance.now() + 10000;
  const work = promise => limited(promise, Math.max(0, end - performance.now()));
  let session = null, failure = null;
  try {
    session = await work(page.context().newCDPSession(page));
    const beforeMetrics = await work(session.send('Page.getLayoutMetrics'));
    observation.before = captureMetrics(beforeMetrics);
    observation.beforeZoomPresent = Object.hasOwn(beforeMetrics.cssVisualViewport || {}, 'zoom');
    const result = await work(session.send('Page.captureScreenshot', {format: 'png', fromSurface: true, captureBeyondViewport: false}));
    check(typeof result.data === 'string' && result.data.length <= 10666668, 'NATIVE_BOUNDED_PNG_REQUIRED');
    const bytes = Buffer.from(result.data, 'base64');
    save(filename, bytes); // Keep the original browser bytes, including on geometry rejection.
    observation.byteLength = bytes.length;
    if (bytes.length >= 24) {observation.pixelWidth = bytes.readUInt32BE(16); observation.pixelHeight = bytes.readUInt32BE(20);}
    pngGeometry(bytes, expected); // Reject this shot before another protocol read or capture.
    const afterMetrics = await work(session.send('Page.getLayoutMetrics'));
    observation.after = captureMetrics(afterMetrics);
    observation.afterZoomPresent = Object.hasOwn(afterMetrics.cssVisualViewport || {}, 'zoom');
    observation.dom = numericFields(await work(geometry(page)), ['innerWidth', 'innerHeight', 'outerWidth', 'outerHeight', 'devicePixelRatio']);
    check(['innerWidth', 'innerHeight', 'devicePixelRatio'].every(key => observation.dom[key] === expected[key]) && observation.dom.outerWidth === 1440 && observation.dom.outerHeight === 1000 && expected.outerWidth === 1440 && expected.outerHeight === 1000, 'NATIVE_CAPTURE_GEOMETRY_DRIFT');
    const beforeZoom = observation.before.cssVisualViewport.zoom, afterZoom = observation.after.cssVisualViewport.zoom;
    if (observation.beforeZoomPresent || observation.afterZoomPresent) check(observation.beforeZoomPresent && observation.afterZoomPresent && Number.isFinite(beforeZoom) && beforeZoom > 0 && beforeZoom === afterZoom, 'NATIVE_CAPTURE_ZOOM_DRIFT');
    pngGeometry(bytes, observation.dom);
    return bytes;
  } catch (error) {failure = error; throw error;}
  finally {
    if (session) {
      try {await limited(session.detach(), 1000, true);}
      catch (error) {observation.detachFailure = safeFailure(error, safeStage('cleanup')); if (!failure) throw error;}
    }
  }
}

async function selfTest() {
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
  count(() => {
    const report = {status: 'NATIVE_ZOOM_CAPTURED_PENDING_VISUAL_REVIEW', cleanup: {confirmed: false}};
    const event = {boundIdentity: {pid: 123, uid: 501, birth: 'component-only'}, signal: 'SIGTERM', reason: 'PROFILE_REMAINS_AFTER_CLOSE_GRACE'};
    const failure = markForcedStop(report, event, null);
    report.cleanup.confirmed = true; // Later absence cannot erase the abnormal stop.
    assert.equal(failure.code, 'NATIVE_FORCED_PROFILE_STOP');
    assert.equal(report.status, 'FAILED_OR_UNKNOWN');
    assert.equal(report.cleanup.forced, true);
    assert.deepEqual(report.cleanup.emergencyEvents, [event]);
    assert.equal(failure.safeStage.stage, 'cleanup');
  });
  count(() => assert.throws(() => safeStage('unknown'), /NATIVE_UNSUPPORTED_SAFE_STAGE/));
  for (const evidence of [{url: 'unsafe'}, {sessionVerified: 'true'}, {rowCount: -1}, {rowCount: 1.5}, {completedPngs: Infinity}, []]) {
    count(() => assert.throws(() => safeStage('rows', evidence), /NATIVE_UNSAFE_STAGE_EVIDENCE/));
  }
  count(() => {
    const evidence = {sessionVerified: true, completedPages: 0};
    const located = safeStage('shop_locate', evidence);
    const failure = safeFailure(new Error('untrusted original text'), located);
    evidence.sessionVerified = false;
    const cleanup = safeStage('cleanup');
    assert.equal(located.evidence.sessionVerified, true);
    assert.throws(() => {located.evidence.sessionVerified = false;}, TypeError);
    assert.deepEqual(Object.keys(failure).sort(), ['code', 'safeStage', 'type']);
    assert.equal(failure.code, 'NATIVE_BROWSER_OR_COMPONENT_FAILURE');
    assert.equal(markForcedStop({cleanup: {}}, {}, failure), failure);
    assert.equal(failure.safeStage.stage, 'shop_locate');
    assert.equal(safeFailure({name: 'untrusted type', message: 'raw error'}, cleanup).type, 'Error');
  });
  const header = (width, height) => {const bytes = Buffer.alloc(33); Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]).copy(bytes); bytes.writeUInt32BE(13, 8); bytes.write('IHDR', 12); bytes.writeUInt32BE(width, 16); bytes.writeUInt32BE(height, 20); return bytes;};
  const measured = {innerWidth: 720, innerHeight: 456, devicePixelRatio: 4, outerWidth: 1440, outerHeight: 1000};
  count(() => assert.deepEqual(pngGeometry(header(2880, 1826), measured), {pixelWidth: 2880, pixelHeight: 1826}));
  for (const bytes of [header(1440, 912), header(2883, 1824), header(2880, 1827), Buffer.alloc(24), Buffer.alloc(8000001)]) count(() => assert.throws(() => pngGeometry(bytes, measured)));
  count(() => assert.throws(() => pngGeometry(header(2880, 1824), {...measured, devicePixelRatio: NaN})));
  for (const [badGeometry, detachFails] of [[false, false], [true, false], [true, true], [false, true]]) {
    const bytes = header(badGeometry ? 1440 : 2880, badGeometry ? 912 : 1824), saved = [], calls = [], observations = [], bounds = [];
    const session = {send: async (method, params) => {
      calls.push([method, params]);
      if (method === 'Page.getLayoutMetrics') return {cssVisualViewport: {clientWidth: 720, zoom: 2, unsafe: 'discard'}, arbitrary: 'discard'};
      assert.equal(method, 'Page.captureScreenshot');
      assert.deepEqual(params, {format: 'png', fromSurface: true, captureBeyondViewport: false});
      return {data: bytes.toString('base64')};
    }, detach: async () => {calls.push(['detach']); if (detachFails) throw new Error('NATIVE_DETACH_COMPONENT_FAILURE');}};
    const page = {context: () => ({newCDPSession: async target => {assert.equal(target, page); return session;}}), evaluate: async () => measured};
    const bound = async (promise, cap, cleanup = false) => {bounds.push({cap, cleanup}); return promise;};
    const task = captureNativePng(page, '/unused/products-200.png', measured, observations, bound, (filename, raw) => saved.push(raw));
    if (badGeometry) await assert.rejects(task, /NATIVE_PNG_BYTES_OR_GEOMETRY_MISMATCH/);
    else if (detachFails) await assert.rejects(task, /NATIVE_DETACH_COMPONENT_FAILURE/);
    else assert.deepEqual(await task, bytes);
    assert.equal(saved.length, 1); assert.deepEqual(saved[0], bytes);
    assert.deepEqual(calls.map(call => call[0]), badGeometry ? ['Page.getLayoutMetrics', 'Page.captureScreenshot', 'detach'] : ['Page.getLayoutMetrics', 'Page.captureScreenshot', 'Page.getLayoutMetrics', 'detach']);
    assert.deepEqual(bounds.at(-1), {cap: 1000, cleanup: true});
    assert(bounds.slice(0, -1).every(item => item.cap > 0 && item.cap <= 10000 && item.cleanup === false));
    assert.equal(JSON.stringify(observations).includes('discard'), false);
    checks++;
  }
  for (const drift of ['same_pixel_product', 'outer_window', 'cdp_zoom']) {
    const bytes = header(2880, 1824), saved = [], observations = [];
    let metricsReads = 0, detached = false;
    const session = {send: async method => {
      if (method === 'Page.getLayoutMetrics') return {cssVisualViewport: {zoom: ++metricsReads === 2 && drift === 'cdp_zoom' ? 1 : 2}};
      assert.equal(method, 'Page.captureScreenshot'); return {data: bytes.toString('base64')};
    }, detach: async () => {detached = true;}};
    const dom = drift === 'same_pixel_product' ? {...measured, innerWidth: 1440, innerHeight: 912, devicePixelRatio: 2} : drift === 'outer_window' ? {...measured, outerWidth: 1441} : measured;
    const page = {context: () => ({newCDPSession: async () => session}), evaluate: async () => dom};
    await assert.rejects(captureNativePng(page, '/unused/products-200.png', measured, observations, async promise => promise, (_, raw) => saved.push(raw)), drift === 'cdp_zoom' ? /NATIVE_CAPTURE_ZOOM_DRIFT/ : /NATIVE_CAPTURE_GEOMETRY_DRIFT/);
    assert.deepEqual(saved, [bytes]); assert.equal(detached, true);
    checks++;
  }
  for (const metadata of ['absent', 'presence_drift', 'invalid']) {
    let reads = 0;
    const session = {send: async method => {
      if (method === 'Page.getLayoutMetrics') return {cssVisualViewport: metadata === 'absent' || ++reads === 1 && metadata === 'presence_drift' ? {} : {zoom: metadata === 'invalid' ? 'untrusted' : 2}};
      return {data: header(2880, 1824).toString('base64')};
    }, detach: async () => {}};
    const page = {context: () => ({newCDPSession: async () => session}), evaluate: async () => measured};
    const task = captureNativePng(page, '/unused/products-200.png', measured, [], async promise => promise, () => {});
    if (metadata === 'absent') await task; else await assert.rejects(task, /NATIVE_CAPTURE_ZOOM_DRIFT/);
    checks++;
  }
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
 * Profile: <case.directory>/browser-tmp/playwright_chromiumdev_profile-native200
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

function markForcedStop(report, event, currentFailure) {
  report.cleanup.forced = true;
  (report.cleanup.emergencyEvents ||= []).push(event);
  report.status = 'FAILED_OR_UNKNOWN';
  return currentFailure || safeFailure(new Error('NATIVE_FORCED_PROFILE_STOP'), safeStage('cleanup'));
}

function persistEmergencyIntent(filename, event) {
  const fd = fs.openSync(filename, 'wx', 0o600);
  try {
    fs.writeFileSync(fd, JSON.stringify(event, null, 2) + '\n');
    fs.fsyncSync(fd); // Intent must reach storage before any attempted signal.
  } finally {fs.closeSync(fd);}
}

function safeFailure(error, stage) {
  return {type: error?.name === 'TimeoutError' ? 'TimeoutError' : 'Error', code: /^NATIVE_[A-Z0-9_]+$/.test(error?.message || '') ? error.message : 'NATIVE_BROWSER_OR_COMPONENT_FAILURE', safeStage: safeStage(stage.stage, stage.evidence)};
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
  const browserTmp = path.join(caseDir, 'browser-tmp');
  if (!fs.existsSync(browserTmp)) fs.mkdirSync(browserTmp, {mode: 0o700});
  check(fs.realpathSync(browserTmp) === browserTmp && fs.statSync(browserTmp).isDirectory() && fs.statSync(browserTmp).uid === process.getuid() && (fs.statSync(browserTmp).mode & 0o777) === 0o700, 'NATIVE_OWNER_BROWSER_TMP_REQUIRED');
  const owned = Object.freeze({...paths(directory), profile: path.join(browserTmp, 'playwright_chromiumdev_profile-native200')});
  for (const name of ['profile', 'extension', 'screenshots', 'processes']) fs.mkdirSync(owned[name], {mode: 0o700});
  writeNew(path.join(directory, 'execution.once'), 'ONE_NEW_SHELL_NATIVE_ZOOM_ATTEMPT\n');
  const extension = extensionFiles(webOrigin);
  for (const [name, bytes] of Object.entries(extension)) writeNew(path.join(owned.extension, name), bytes);
  const receiptPath = path.join(directory, 'receipt.json');
  const report = {status: 'FAILED_OR_UNKNOWN', scope: 'SAME_SHELL_VISITOR_READONLY_NATIVE_200', startedUtc: new Date().toISOString(), source: sourceBefore, tools: toolsBefore.files, currentShopSha256: sha(currentShopId), shellContextSha256: sha(JSON.stringify(CONTEXT_KEYS.map(k => shell.context[k]))), cookieCount: cookies.length, profile: {path: owned.profile, mode: fs.statSync(owned.profile).mode & 0o777, uid: process.getuid()}, extensionSha256: Object.fromEntries(Object.entries(extension).map(([name, bytes]) => [name, sha(bytes)])), nativeBrowserExit: 'NOT_EXPOSED', pages: [], requests: {allowedReads: 0, refused: []}, processes: [], cleanup: {confirmed: false}, humanVisualAcceptance: 'NOT_RUN'};
  let context = null, monitor = null, monitorFailure = null, failure = null;
  let stage = safeStage('launch'), completedPngs = 0;
  const enter = (name, evidence = {}) => {stage = safeStage(name, {completedPages: report.pages.length, completedPngs, ...evidence}); report.safeStage = stage;};
  const known = new Map();
  const observe = () => {try {return processWitness(owned.profile, known);} catch (error) {monitorFailure = safeFailure(error, stage); return null;}};
  try {
    enter('launch');
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
    enter('worker');
    let worker = context.serviceWorkers().find(item => item.url().startsWith('chrome-extension://'));
    if (!worker) worker = await context.waitForEvent('serviceworker', {timeout: timeout(15000)});
    const workerUrl = new URL(worker.url());
    check(workerUrl.protocol === 'chrome-extension:' && /^[a-p]{32}$/.test(workerUrl.hostname) && workerUrl.pathname === '/worker.js', 'NATIVE_EXACT_EXTENSION_WORKER_REQUIRED');
    report.worker = {extensionId: workerUrl.hostname, path: workerUrl.pathname};
    const page = context.pages()[0] || await context.newPage();
    for (const [label, pathname, dataPath] of [['dashboard', '/v4/dashboard', '/api/v4/dashboard'], ['products', '/v4/products', '/api/v4/products']]) {
      enter('navigation_session');
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
      enter('shop_locate', {sessionVerified: true});
      const selector = page.getByRole('combobox', {name: '店铺', exact: true});
      await selector.waitFor({state: 'visible', timeout: timeout(10000)});
      check(await selector.count() === 1, 'NATIVE_ONE_SHOP_SELECTOR_REQUIRED');
      enter('shop_select', {sessionVerified: true});
      await selector.selectOption(currentShopId, {timeout: timeout(10000)});
      enter('business_read', {sessionVerified: true, shopVerified: true});
      const dataReply = await dataResponse;
      check(dataReply.status() === 200, 'NATIVE_BUSINESS_READ_REJECTED');
      const payload = await dataReply.json(); sameContext(shell.context, payload.context, currentShopId);
      check(payload.status === 'OK' && payload.data, 'NATIVE_REAL_BUSINESS_DATA_REQUIRED');
      enter('rows', {sessionVerified: true, shopVerified: true, businessVerified: true});
      const rows = page.locator(label === 'products' ? 'section[aria-label="商品中心"] tbody tr' : 'table tbody tr');
      const readyUntil = performance.now() + timeout(10000);
      while (await rows.count() === 0) {check(performance.now() < readyUntil, 'NATIVE_REAL_TABLE_ROWS_REQUIRED'); await pause(50);}
      enter('native_zoom', {rowCount: await rows.count()});
      const baseline = await setNativeZoom(worker, targetUrl, 1);
      const before = await geometry(page);
      check(before.outerWidth === 1440 && before.outerHeight === 1000, 'NATIVE_ACTUAL_WINDOW_1440_1000_REQUIRED');
      const first = path.join(owned.screenshots, label + '-100.png');
      enter('png');
      await captureNativePng(page, first, before, (report.captureObservations ||= []), limited);
      completedPngs++;
      enter('native_zoom');
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
      enter('png');
      await captureNativePng(page, second, after, report.captureObservations, limited);
      completedPngs++;
      const pictures = [first, second];
      if (label === 'products') {
        enter('rows');
        await rows.last().scrollIntoViewIfNeeded({timeout: timeout(10000)});
        enter('native_zoom');
        check((await readNativeZoom(worker, targetUrl)).actual === 2, 'NATIVE_ZOOM_CHANGED_BEFORE_BOTTOM_CAPTURE');
        const bottom = path.join(owned.screenshots, 'products-200-bottom.png');
        enter('png');
        await captureNativePng(page, bottom, after, report.captureObservations, limited); pictures.push(bottom);
        completedPngs++;
      }
      enter('png');
      report.pages.push({label, pathname, rowCount: await rows.count(), baseline, zoom, before, after, screenshots: pictures.map(filename => {
        const bytes = fs.readFileSync(filename);
        check(bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])), 'NATIVE_REAL_PNG_REQUIRED');
        return {path: path.relative(directory, filename), sha256: sha(bytes), pixelWidth: bytes.readUInt32BE(16), pixelHeight: bytes.readUInt32BE(20)};
      })});
      check(report.requests.refused.length === 0, 'NATIVE_NONREAD_OR_EXTERNAL_REQUEST_REFUSED');
    }
    report.status = 'NATIVE_ZOOM_CAPTURED_PENDING_VISUAL_REVIEW';
  } catch (error) {
    failure = safeFailure(error, stage); report.failure = failure;
  } finally {
    if (monitor) clearInterval(monitor);
    enter('cleanup');
    try {if (context) await limited(context.close(), 15000, true);} catch (error) {report.cleanup.closeFailure = safeFailure(error, stage); failure ||= report.cleanup.closeFailure;}
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
          const event = {recordedUtc: new Date().toISOString(), boundIdentity: {...bound}, observedIdentity: {...current}, signal: sig, reason: report.cleanup.closeFailure ? 'CONTEXT_CLOSE_FAILED_PROFILE_REMAINS' : 'PROFILE_REMAINS_AFTER_CLOSE_GRACE'};
          failure = markForcedStop(report, event, failure);
          const stem = 'emergency-' + String(report.cleanup.emergencyEvents.length).padStart(4, '0');
          persistEmergencyIntent(path.join(owned.processes, stem + '.intent.json'), event);
          let outcome = 'SIGNAL_SENT';
          try {process.kill(current.pid, sig);} catch (error) {if (error.code !== 'ESRCH') throw error; outcome = 'ALREADY_EXITED';}
          writeNew(path.join(owned.processes, stem + '.result.json'), JSON.stringify({signal: sig, pid: current.pid, outcome}, null, 2) + '\n');
        }
        await pause(Math.min(250, timeout(1000, true))); witness = processWitness(owned.profile, known);
      }
      report.processes = [...known.values()]; report.cleanup.profileProcesses = witness.profileProcesses; report.cleanup.registeredAlive = witness.alive;
      check(!witness.profileProcesses.length && !witness.alive.length, 'NATIVE_PROFILE_PROCESSES_REMAIN');
      report.cleanup.sourceAfter = sourceEvidence(ownedCase); report.cleanup.toolsAfter = toolEvidence(browserRuntime).files;
      check(JSON.stringify(report.cleanup.sourceAfter) === JSON.stringify(sourceBefore) && JSON.stringify(report.cleanup.toolsAfter) === JSON.stringify(toolsBefore.files), 'NATIVE_SOURCE_OR_TOOL_CHANGED');
      check(!monitorFailure, 'NATIVE_PROCESS_OBSERVER_FAILED'); report.cleanup.confirmed = true;
    } catch (error) {report.cleanup.failure = safeFailure(error, stage); failure ||= report.cleanup.failure;}
    if (failure) {report.status = 'FAILED_OR_UNKNOWN'; report.failure = failure;}
    report.endedUtc = new Date().toISOString();
    try {writeNew(receiptPath, JSON.stringify(report, null, 2) + '\n');} catch {failure = {code: 'NATIVE_RECEIPT_WRITE_FAILED'};}
  }
  if (failure) {const error = new Error(failure.code); error.receiptPath = receiptPath; throw error;}
  return {status: report.status, receiptPath, nativeBrowserExit: 'NOT_EXPOSED', visualAcceptance: 'PENDING_REVIEW'};
}

module.exports = {PINS, origin, paths, launchOptions, extensionFiles, setNativeZoom, readNativeZoom, geometry, requireNative200, captureNativePng, selfTest, run};
if (require.main === module) {
  if (process.argv.length === 3 && process.argv[2] === '--self-test') {
    selfTest().then(result => process.stdout.write(JSON.stringify(result) + '\n')).catch(() => {process.stderr.write('NATIVE_COMPONENT_CHECK_FAILED\n'); process.exitCode = 1;});
  } else if (process.argv.length === 2 || (process.argv.length === 3 && process.argv[2] === '--plan')) {
    process.stdout.write(JSON.stringify({status: 'COMPONENT_CANDIDATE_ONLY', pins: PINS, noLaunchingCli: true, next: 'ROOT_EXACT_PROFILE_URL_UTC_AND_IDENTITY_BOUND_PARENT_REQUIRED', runtime: 'NOT_RUN'}) + '\n');
  } else {
    process.stderr.write('EXECUTION_NOT_IMPLEMENTED_OR_AUTHORIZED_IN_COMPONENT_CANDIDATE\n');
    process.exitCode = 2;
  }
}
