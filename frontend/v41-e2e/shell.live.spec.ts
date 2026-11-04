import {test,expect,verifyOwnedShellPage} from './owned-cdp.fixture';
import {type Response,type APIResponse,type Request,type Route,type Frame} from '@playwright/test';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import {mkdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import routes from '../lib/v41-routes.json' with {type:'json'};
import schema from '../lib/v4-schema.json' with {type:'json'};
import businessContract from '../../docs/v4/v4-1/API_CONTRACT.json' with {type:'json'};
const businessSchema=businessContract.json_schema;
import {readBrowserCase,subjectWriter} from './browser-subjects';
import {captureNative200} from './native-capture';

const c=readBrowserCase(),api=`http://127.0.0.1:${c.api_port}`;
const sessionCookieURL=api+'/api/v4/demo/session';
const evidence=join(c.directory,'browser-shell');
const ajv=new Ajv2020({strict:true,allErrors:true,allowUnionTypes:true});addFormats(ajv);
async function envelope(r:Response|APIResponse,definition:'SessionEnvelope'|'CreateEnvelope'|'ControlEnvelope'){
  expect(r.status()).toBe(definition==='CreateEnvelope'?201:200);
  expect(r.headers()['cache-control']).toBe('no-store');
  expect(r.headers()['vary'].toLowerCase().split(',').map(x=>x.trim())).toEqual(expect.arrayContaining(['cookie','origin']));
  const body=await r.json();
  expect(ajv.compile({...schema,$ref:'#/$defs/'+definition})(body)).toBe(true);
  return body;
}
async function session(r:Response|APIResponse){return envelope(r,'SessionEnvelope');}

test('LIVE V41: shell identity navigation and responsive boundaries',async({page,context})=>{
  mkdirSync(evidence,{mode:0o700});
  const subjects=subjectWriter(c,'shell');
  const screenshots:{path:string;sha256:string}[]=[];
  let creates=0,apiPosts=0;
  page.on('request',r=>{const u=new URL(r.url());if(u.origin===api&&r.method()==='POST')apiPosts++;if(u.origin===api&&u.pathname==='/api/v4/demo/sessions'&&r.method()==='POST')creates++;});
  await page.setViewportSize({width:1440,height:900});
  await page.goto(`http://127.0.0.1:${c.web_port}/v4`);
  const first=page.waitForResponse(r=>r.url()===api+'/api/v4/demo/session'&&r.request().method()==='GET'&&r.ok());
  const created=page.waitForResponse(r=>r.url()===api+'/api/v4/demo/sessions'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'一键体验 →',exact:true}).click();
  const creation=await envelope(await created,'CreateEnvelope');
  const current=await session(await first);
  expect(current.data.creation_request_key).toBe(creation.data.receipt.request_key);
  for(const shop of current.data.shops)subjects.scope(current.context,shop.shop_id);
  expect(current.data.persona_id).toBe('operator');expect(current.data.shops).toHaveLength(2);
  await page.getByRole('combobox',{name:'店铺',exact:true}).selectOption(current.data.shops[0].shop_id);
  await expect(page.getByText('当前视角：operator',{exact:false})).toBeVisible();
  for(const item of routes.modules){
    const nav=page.locator('nav[aria-label="业务导航"]:visible');
    await expect(nav.getByRole('link')).toHaveCount(14);
    await nav.getByRole('link',{name:item.name,exact:false}).click();
    await expect(page).toHaveURL(new URL(item.href,`http://127.0.0.1:${c.web_port}`).href);
    await page.reload();
    await expect(page.getByText('当前视角：operator',{exact:false})).toBeVisible();
    await expect(page.locator('nav[aria-label="业务导航"]:visible').locator('[aria-current="page"]')).toHaveCount(1);
  }
  for(const width of [1440,1280,390]){
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    if(width===390){
      const opener=page.getByRole('button',{name:'打开业务导航'});
      await opener.focus();await page.keyboard.press('Enter');
      const menu=page.getByRole('dialog',{name:'业务导航菜单'});
      await expect(menu).toBeVisible();await expect(menu.getByRole('link')).toHaveCount(14);
      await page.keyboard.press('Tab');
      expect(await menu.evaluate(el=>el.contains(document.activeElement))).toBe(true);
      await page.keyboard.press('Escape');await expect(menu).not.toBeVisible();await expect(opener).toBeFocused();
    }
    const assistant=page.getByRole('button',{name:'智能助手'});
    await assistant.focus();await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog',{name:'智能助手'}).getByText('模型未启用')).toBeVisible();
    await page.keyboard.press('Escape');await expect(assistant).toBeFocused();
    const path=join(evidence,`shell-${width}.png`);
    const bytes=await page.screenshot({path,fullPage:true});
    screenshots.push({path,sha256:createHash('sha256').update(bytes).digest('hex')});
  }
  // StageSpec clear gates use real browser lifecycle events and the existing visitor only.
  const identityFields=['tenant_id','organization_id','principal_id','reset_epoch','auth_generation'] as const;
  const sameCookies=()=>context.cookies(sessionCookieURL).then(items=>items.filter(item=>item.name==='commerceops_v4_demo').map(({name,value,domain,path})=>({name,value,domain,path})));
  const originalCookies=await sameCookies(),lifecyclePosts=apiPosts;
  expect(originalCookies).toHaveLength(1);
  await page.setViewportSize({width:1440,height:900});await page.goto(`http://127.0.0.1:${c.web_port}/v4/dashboard`);
  await expect(page.getByText('当前视角：operator',{exact:false})).toBeVisible();
  await page.getByRole('combobox',{name:'店铺',exact:true}).selectOption(current.data.shops[0].shop_id);
  async function restoreOriginal(){
    await page.bringToFront();
    await expect.poll(()=>page.evaluate(()=>document.visibilityState)).toBe('visible');
    let committed=false;
    const sessionRequests=new Set<Request>();
    const trackCommit=(frame:Frame)=>{if(frame===page.mainFrame())committed=true;};
    const trackRequest=(request:Request)=>{
      if(committed&&request.url()===sessionCookieURL&&request.method()==='GET'&&request.frame()===page.mainFrame())sessionRequests.add(request);
    };
    page.on('framenavigated',trackCommit);page.on('request',trackRequest);
    const renewed=page.waitForResponse(response=>sessionRequests.has(response.request()));
    try{
      await page.reload();
      const response=await renewed;
      expect(committed).toBe(true);expect(sessionRequests.has(response.request())).toBe(true);
      expect(await response.finished()).toBeNull();
      const restored=await session(response);
      for(const key of identityFields)expect(restored.context[key]).toBe(current.context[key]);
      expect(restored.data.creation_request_key).toBe(current.data.creation_request_key);
      expect(restored.data.persona_id).toBe('operator');expect(await sameCookies()).toEqual(originalCookies);
      await expect(page.getByText('当前视角：operator',{exact:false})).toBeVisible();
      await page.getByRole('combobox',{name:'店铺',exact:true}).selectOption(current.data.shops[0].shop_id);
      expect(creates).toBe(1);
    }finally{
      page.off('framenavigated',trackCommit);page.off('request',trackRequest);
    }
  }
  async function currentFacts(){
    const reply=page.waitForResponse(r=>new URL(r.url()).origin===api&&new URL(r.url()).pathname==='/api/v4/read-context'&&r.request().method()==='GET');
    await page.getByRole('button',{name:'智能助手',exact:true}).click();
    const response=await reply;expect(response.status()).toBe(200);
    expect(response.headers()['cache-control']).toBe('no-store');
    const body=await response.json();
    expect(ajv.compile({...businessSchema,$ref:'#/$defs/BusinessEnvelope_ReadContextData_'})(body)).toBe(true);
    for(const key of identityFields)expect(body.context[key]).toBe(current.context[key]);
    expect(body.context.shop_id).toBe(current.data.shops[0].shop_id);
    const panel=page.getByRole('dialog',{name:'智能助手'});
    await expect(panel.getByRole('heading',{name:'当前事实',exact:true})).toBeVisible();
    await expect(panel.getByText('数据读取于 '+body.data.snapshot.read_at,{exact:true})).toBeVisible();
    return body.data.snapshot.read_at as string;
  }
  async function sensitiveCleared(readAt:string){
    await expect(page.getByText('当前视角：',{exact:false})).toHaveCount(0);
    // includeHidden checks DOM removal, so backgrounding the page cannot itself make this pass.
    await expect(page.getByRole('heading',{name:'当前事实',exact:true,includeHidden:true})).toHaveCount(0);
    await expect(page.getByText('数据读取于 '+readAt,{exact:true})).toHaveCount(0);
  }
  const offlineReadAt=await currentFacts();
  try{
    await context.setOffline(true);
    await expect.poll(()=>page.evaluate(()=>navigator.onLine)).toBe(false);
    await sensitiveCleared(offlineReadAt);expect(await sameCookies()).toEqual(originalCookies);
  }finally{await context.setOffline(false);}
  await expect.poll(()=>page.evaluate(()=>navigator.onLine)).toBe(true);
  await restoreOriginal();
  const hiddenReadAt=await currentFacts();
  expect(page.context()).toBe(context);
  const windowSession=await context.newCDPSession(page);
  let hiddenWindowRestored=false;
  try{
    await verifyOwnedShellPage(page,windowSession);
    const {targetInfo:ownedTarget}=await windowSession.send('Target.getTargetInfo');
    expect(ownedTarget.type).toBe('page');
    expect(typeof ownedTarget.targetId).toBe('string');expect(ownedTarget.targetId.length).toBeGreaterThan(0);
    const contextIdPresent=Object.hasOwn(ownedTarget,'browserContextId');
    if(contextIdPresent&&(typeof ownedTarget.browserContextId!=='string'||!ownedTarget.browserContextId.length))throw new Error('Invalid owned context identity');
    expect(ownedTarget.url).toBe(page.url());expect(new URL(ownedTarget.url).origin).toBe(`http://127.0.0.1:${c.web_port}`);
    const ownedWindow=await windowSession.send('Browser.getWindowForTarget',{targetId:ownedTarget.targetId});
    expect(Number.isInteger(ownedWindow.windowId)).toBe(true);expect(ownedWindow.bounds.windowState).toBe('normal');
    async function verifyOwnedWindow(){
      await verifyOwnedShellPage(page,windowSession);
      expect(page.context()).toBe(context);
      const {targetInfo:actual}=await windowSession.send('Target.getTargetInfo');
      expect(actual.type).toBe('page');expect(actual.targetId).toBe(ownedTarget.targetId);
      expect(Object.hasOwn(actual,'browserContextId')).toBe(contextIdPresent);
      expect(actual.browserContextId).toBe(ownedTarget.browserContextId);
      expect(actual.url).toBe(ownedTarget.url);expect(page.url()).toBe(ownedTarget.url);
      const actualWindow=await windowSession.send('Browser.getWindowForTarget',{targetId:ownedTarget.targetId});
      expect(actualWindow.windowId).toBe(ownedWindow.windowId);
    }
    try{
      await verifyOwnedWindow();
      await windowSession.send('Browser.setWindowBounds',{windowId:ownedWindow.windowId,bounds:{windowState:'minimized'}});
      await expect.poll(async()=>(await windowSession.send('Browser.getWindowBounds',{windowId:ownedWindow.windowId})).bounds.windowState).toBe('minimized');
      await expect.poll(()=>page.evaluate(()=>document.visibilityState)).toBe('hidden');
      await sensitiveCleared(hiddenReadAt);expect(await sameCookies()).toEqual(originalCookies);
      await verifyOwnedWindow();
      expect((await windowSession.send('Browser.getWindowBounds',{windowId:ownedWindow.windowId})).bounds.windowState).toBe('minimized');
      expect(await page.evaluate(()=>document.visibilityState)).toBe('hidden');
    }finally{
      await verifyOwnedWindow();
      await windowSession.send('Browser.setWindowBounds',{windowId:ownedWindow.windowId,bounds:{windowState:'normal'}});
      await expect.poll(async()=>(await windowSession.send('Browser.getWindowBounds',{windowId:ownedWindow.windowId})).bounds.windowState).toBe('normal');
      await page.bringToFront();
      await expect.poll(()=>page.evaluate(()=>document.visibilityState)).toBe('visible');
      hiddenWindowRestored=true;
    }
  }finally{await windowSession.detach();}
  await restoreOriginal();await currentFacts();await page.keyboard.press('Escape');
  expect(apiPosts).toBe(lifecyclePosts);expect(creates).toBe(1);
  const lifecycleClear={tier:'REAL_BROWSER_OFFLINE_AND_VISIBILITY',offline:{navigatorOnLine:false,sensitiveDOM:'CLEARED',recovery:'SAME_COOKIE_GET_RELOAD'},hidden:{ownedTargetWindowMatched:true,windowState:'minimized',documentVisibilityState:'hidden',sensitiveDOM:'CLEARED',restoredWindowState:'normal',restoredVisible:hiddenWindowRestored,recovery:'SAME_COOKIE_GET_RELOAD'},extraPosts:apiPosts-lifecyclePosts};
  const nativeSession=await session(await page.request.get(api+'/api/v4/demo/session',{headers:{Origin:`http://127.0.0.1:${c.web_port}`},maxRedirects:0,maxRetries:0,timeout:10000}));
  for(const key of ['tenant_id','organization_id','principal_id','reset_epoch','auth_generation'])expect(nativeSession.context[key]).toBe(current.context[key]);
  const nativeShop=await page.getByRole('combobox',{name:'店铺',exact:true}).inputValue();
  expect(nativeSession.data.shops.some((shop:{shop_id:string})=>shop.shop_id===nativeShop)).toBe(true);
  let native200:Awaited<ReturnType<typeof captureNative200>>;
  try{native200=await captureNative200(c,await context.cookies(sessionCookieURL),nativeSession.context,nativeShop);}
  finally{await restoreOriginal();} // The native headed window may have hidden and cleared this Shell.

  // Network ACK delay injection: fetch a genuine read-context success, then hold its delivery.
  // read-context has no client AbortController; no signal, request, body or response is rewritten.
  await page.setViewportSize({width:1440,height:900});
  await page.goto(`http://127.0.0.1:${c.web_port}/v4/dashboard`);
  await expect(page.getByText('当前视角：operator',{exact:false})).toBeVisible();
  await page.getByRole('combobox',{name:'店铺',exact:true}).selectOption(current.data.shops[0].shop_id);
  const assistant=page.getByRole('button',{name:'智能助手',exact:true});
  const baseline=page.waitForResponse(r=>new URL(r.url()).origin===api&&new URL(r.url()).pathname==='/api/v4/read-context'&&r.request().method()==='GET');
  await assistant.click();
  const baselineResponse=await baseline;
  expect(baselineResponse.status()).toBe(200);
  expect(ajv.compile({...businessSchema,$ref:'#/$defs/BusinessEnvelope_ReadContextData_'})(await baselineResponse.json())).toBe(true);
  await expect(page.getByRole('dialog',{name:'智能助手'}).getByRole('heading',{name:'当前事实',exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  let releaseAck!:()=>void, capture!:(value:{upstream:APIResponse;request:Request})=>void, captureError!:(error:unknown)=>void;
  let delivered!:()=>void, deliveryError!:(error:unknown)=>void;
  const release=new Promise<void>(resolve=>{releaseAck=resolve;});
  const captured=new Promise<{upstream:APIResponse;request:Request}>((resolve,reject)=>{capture=resolve;captureError=reject;});
  const delivery=new Promise<void>((resolve,reject)=>{delivered=resolve;deliveryError=reject;});
  // Observe rejections immediately; the original promises are still awaited below and fail the test.
  void captured.catch(()=>{});void delivery.catch(()=>{});
  const target=(url:URL)=>url.origin===api&&url.pathname==='/api/v4/read-context';
  let claimed=false;
  const hold=async(route:Route)=>{
    if(claimed||route.request().method()!=='GET'){await route.continue();return;}
    claimed=true;
    let upstream:APIResponse|undefined;
    try{
      upstream=await route.fetch({maxRetries:0,maxRedirects:0,timeout:10000});
      capture({upstream,request:route.request()});
      await release;
      await route.fulfill({response:upstream}); // Forward the authentic status/headers/body unchanged.
      await upstream.dispose();upstream=undefined;
      delivered();
    }catch(error){captureError(error);deliveryError(error);await route.abort().catch(()=>{});}
    finally{await upstream?.dispose();}
  };
  await page.route(target,hold);
  let delayedAck:Record<string,unknown>;
  try{
    await assistant.click();
    const held=await captured,raw=await held.upstream.body(),old=JSON.parse(raw.toString('utf8'));
    expect(held.upstream.status()).toBe(200);expect(old.status).toBe('OK');
    expect(held.upstream.headers()['cache-control']).toBe('no-store');
    expect(ajv.compile({...businessSchema,$ref:'#/$defs/BusinessEnvelope_ReadContextData_'})(old)).toBe(true);
    for(const key of ['tenant_id','organization_id','principal_id','reset_epoch','auth_generation'])expect(old.context[key]).toBe(current.context[key]);
    expect(old.context.shop_id).toBe(current.data.shops[0].shop_id);
    expect(old.data.kind).toBe('dashboard');expect(old.data.metrics).toHaveLength(8);
    await expect(page.getByRole('dialog',{name:'智能助手'}).getByText('正在读取当前授权上下文…',{exact:true})).toBeVisible();
    await page.keyboard.press('Escape');
    await page.getByLabel('体验视角').selectOption('restricted_admin');
    const switched=page.waitForResponse(r=>r.url()===api+'/api/v4/demo/session'&&r.request().method()==='GET'&&r.ok());
    const changed=page.waitForResponse(r=>r.url()===api+'/api/v4/demo/persona'&&r.request().method()==='POST');
    await page.getByRole('button',{name:'切换视角',exact:true}).click();
    await envelope(await changed,'ControlEnvelope');
    const admin=await session(await switched);expect(admin.data.persona_id).toBe('restricted_admin');expect(admin.data.shops).toHaveLength(0);
    await expect(page.getByText('当前视角没有获授权店铺。')).toBeVisible();
    const loggedOut=page.waitForResponse(r=>r.url()===api+'/api/v4/demo/logout'&&r.request().method()==='POST');
    await page.getByRole('button',{name:'退出',exact:true}).click();await envelope(await loggedOut,'ControlEnvelope');
    await expect(page.getByText('当前视角：',{exact:false})).toHaveCount(0);
    expect((await context.cookies(sessionCookieURL)).filter(x=>x.name==='commerceops_v4_demo')).toHaveLength(0);
    const panel=page.getByRole('dialog',{name:'智能助手'});
    await assistant.click();await expect(panel).toBeVisible();
    await expect(panel.getByRole('heading',{name:'当前事实',exact:true})).toHaveCount(0);
    await expect(panel.getByText('选择授权店铺，并打开驾驶舱或具体商品、订单后查看。',{exact:true})).toBeVisible();
    const late=page.waitForResponse(r=>r.request()===held.request);
    releaseAck();await delivery;
    const received=await late;
    expect(await received.finished()).toBeNull();expect(received.status()).toBe(200);
    const receivedHash=createHash('sha256').update(await received.body()).digest('hex');
    const originalHash=createHash('sha256').update(raw).digest('hex');expect(receivedHash).toBe(originalHash);
    // readV41 parses/validates synchronously after body completion; wait for the following UI paint.
    await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
    await expect(page.getByText('当前视角：',{exact:false})).toHaveCount(0);
    await expect(panel.getByRole('heading',{name:'当前事实',exact:true})).toHaveCount(0);
    await expect(page.getByText('数据读取于 '+old.data.snapshot.read_at,{exact:true})).toHaveCount(0);
    await expect(panel.getByText('选择授权店铺，并打开驾驶舱或具体商品、订单后查看。',{exact:true})).toBeVisible();
    expect((await context.cookies(sessionCookieURL)).filter(x=>x.name==='commerceops_v4_demo')).toHaveLength(0);
    delayedAck={tier:'NETWORK_ACK_DELAY_INJECTION_REAL_UPSTREAM',path:'/api/v4/read-context',upstream_status:200,delivered_status:200,upstream_sha256:originalHash,delivered_sha256:receivedHash,release_barrier:'LOGOUT_COMMITTED_AND_SENSITIVE_STATE_CLEARED',sensitive_state_after_delivery:'ABSENT'};
    await page.keyboard.press('Escape');
  }finally{
    releaseAck();
    try{if(claimed)await delivery;}finally{await page.unroute(target,hold);}
  }
  await page.reload();await expect(page.getByRole('button',{name:'一键体验 →',exact:true})).toBeVisible();expect(creates).toBe(1);
  writeFileSync(join(evidence,'shell.safe.json'),JSON.stringify({source_sha:c.source_sha,source_tree:c.source_tree,scope:'LIVE_SHELL_ONLY',screenshots,native200,businessKPI:'NOT_VERIFIED_BY_SHELL',lifecycleClear,delayedAck,actual_create_requests:creates},null,2),{mode:0o600,flag:'wx'});
});
