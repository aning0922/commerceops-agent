import {test,expect,verifyOwnedShellPage} from './owned-cdp.fixture';
import {type Page,type Response,type APIResponse,type Request,type Route,type Frame} from '@playwright/test';
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

// CURRENT_FACTS_CORRELATION_BEGIN: resource-free tests execute this exact helper.
type FactsRecord={ordinal:number;query_match:boolean;stage:string;done:boolean;excluded_before_arm?:boolean;status?:number;read_at?:string;valid?:boolean};
async function correlateCurrentFacts(options:{
  page:Page;api:string;query:Record<string,string>;click:()=>Promise<void>;
  validate:(body:any)=>string;readUI:()=>Promise<string[]>;
  poll:(probe:()=>Promise<boolean>,timeout:number)=>Promise<void>;
  exact:(text:string,timeout:number)=>Promise<void>;trace:(value:unknown)=>void;timeout?:number;
}):Promise<string>{
  const timeout=options.timeout??5000,deadline=performance.now()+timeout;
  const records=new Map<Request,FactsRecord>(),tasks:Promise<void>[]=[];
  let accepting=false,closed=false,arm=0,cutoff=0,ignoredBeforeArm=0,ignoredFrame=0;
  let fatal:unknown=null,uiReadAt:string|null=null,matched:number|null=null;
  const fail=(error:unknown)=>{fatal??=error;};
  const requireFacts=(value:unknown,stage:string)=>{if(!value)throw new Error('CURRENT_FACTS_'+stage);};
  const remaining=()=>Math.max(1,deadline-performance.now());
  async function bounded<T>(promise:Promise<T>):Promise<T>{
    const left=deadline-performance.now();
    if(left<=0){void promise.catch(()=>{});throw new Error('CURRENT_FACTS_DEADLINE');}
    let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([promise,new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(new Error('CURRENT_FACTS_DEADLINE')),left);})]);}
    finally{clearTimeout(timer);}
  }
  function onRequest(request:Request){
    if(!accepting)return;
    try{
      const url=new URL(request.url());
      if(url.origin!==options.api||url.pathname!=='/api/v4/read-context'||request.method()!=='GET')return;
      if(request.frame()!==options.page.mainFrame()){ignoredFrame++;return;}
      if(records.has(request))return;
      const expected=Object.entries(options.query).sort(),actual=[...url.searchParams.entries()].sort();
      const queryMatch=JSON.stringify(actual)===JSON.stringify(expected);
      const record:FactsRecord={ordinal:records.size+1,query_match:queryMatch,stage:'response',done:false};
      records.set(request,record);
      const task=(async()=>{
        try{
          const response=await bounded(request.response());
          requireFacts(response&&response.request()===request,'RESPONSE_IDENTITY');
          if(!response)throw new Error('CURRENT_FACTS_NO_RESPONSE');
          // Public timing is populated when Response is constructed, not at request emission.
          const began=request.timing().startTime;
          requireFacts(Number.isFinite(began)&&began>0,'REQUEST_START_UNKNOWN');
          if(began<arm){ignoredBeforeArm++;record.excluded_before_arm=true;record.stage='excluded_before_arm';return;}
          if(!queryMatch)fail(new Error('CURRENT_FACTS_QUERY_MISMATCH'));
          record.status=response.status();
          record.stage='finished';requireFacts(await bounded(response.finished())===null,'FINISHED_FAILED');
          record.stage='http';requireFacts(response.status()===200,'HTTP_STATUS');
          requireFacts(response.headers()['cache-control']==='no-store','NO_STORE');
          record.stage='json';const body=await bounded(response.json());
          record.stage='validation';const readAt=options.validate(body);
          requireFacts(typeof readAt==='string'&&Number.isFinite(Date.parse(readAt)),'READ_AT');
          record.read_at=readAt;record.valid=queryMatch;record.stage='validated';
        }catch(error){fail(error);}finally{record.done=true;}
      })();
      // Every captured Request owns one bounded, rejection-handled task, including failures.
      tasks.push(task);
    }catch(error){fail(error);}
  }
  function onFailed(request:Request){
    const record=records.get(request);
    if(record&&!record.excluded_before_arm){record.stage='request_failed';fail(new Error('CURRENT_FACTS_REQUEST_FAILED'));}
  }
  function unique(texts:string[]):FactsRecord|null{
    const markers=texts.map(text=>/^数据读取于 ([^\s]+)$/.exec(text)).filter(value=>value!==null);
    requireFacts(markers.length<=1,'UI_MARKER_AMBIGUOUS');
    uiReadAt=markers[0]?.[1]??null;
    if(uiReadAt===null)return null;
    const candidates=[...records.values()].filter(record=>record.valid&&record.read_at===uiReadAt);
    requireFacts(candidates.length<=1,'RESPONSE_TIME_AMBIGUOUS');
    return candidates[0]??null;
  }
  options.page.on('request',onRequest);options.page.on('requestfailed',onFailed);
  try{
    arm=Date.now();accepting=true;
    await bounded(options.click()); // Exactly one original click, never a retry or replay.
    await options.poll(async()=>{
      if(closed)throw new Error('CURRENT_FACTS_CLOSED');
      if(fatal)throw fatal;
      const candidate=unique(await bounded(options.readUI()));
      if(fatal)throw fatal;
      return !!candidate&&[...records.values()].every(record=>record.done);
    },remaining());
    // Stop admission, drain ALL captured tasks, then witness exact UI once more.
    accepting=false;cutoff=Date.now();await Promise.all(tasks);
    if(fatal)throw fatal;
    const candidate=unique(await bounded(options.readUI()));
    requireFacts(candidate&&candidate.read_at,'NO_UNIQUE_RENDERED_RESPONSE');
    if(!candidate?.read_at)throw new Error('CURRENT_FACTS_NO_MATCH');
    await bounded(options.exact('数据读取于 '+candidate.read_at,remaining()));
    if(fatal)throw fatal;
    matched=candidate.ordinal;
    return candidate.read_at;
  }catch(error){fail(error);throw error;}
  finally{
    accepting=false;cutoff=cutoff||Date.now();closed=true;
    // Bounded tasks settle at the same deadline; no transport is aborted or retried.
    await Promise.all(tasks);
    options.page.off('request',onRequest);options.page.off('requestfailed',onFailed);
    options.trace({scope:'CURRENT_FACTS_REQUEST_UI_ASSOCIATION',arm,cutoff,ignored_before_arm:ignoredBeforeArm,ignored_other_frame:ignoredFrame,requests:[...records.values()],ui_read_at:uiReadAt,matched_ordinal:matched,status:fatal?'FAILED_OR_UNKNOWN':'EXACT_RENDERED_RESPONSE_VALIDATED'});
  }
}
// CURRENT_FACTS_CORRELATION_END

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
  let factsCall=0;
  async function currentFacts(){
    const call=++factsCall,panel=page.getByRole('dialog',{name:'智能助手'});
    return correlateCurrentFacts({page,api,query:{shop_id:current.data.shops[0].shop_id,kind:'dashboard',days:'7'},
      click:()=>page.getByRole('button',{name:'智能助手',exact:true}).click(),
      validate:body=>{
        expect(ajv.compile({...businessSchema,$ref:'#/$defs/BusinessEnvelope_ReadContextData_'})(body)).toBe(true);
        for(const key of identityFields)expect(body.context[key]).toBe(current.context[key]);
        expect(body.context.shop_id).toBe(current.data.shops[0].shop_id);
        return body.data.snapshot.read_at as string;
      },
      readUI:()=>panel.locator('p').allTextContents(),
      poll:async(probe,timeout)=>{await expect.poll(probe,{timeout}).toBe(true);},
      exact:async(text,timeout)=>{
        await expect(panel.getByRole('heading',{name:'当前事实',exact:true})).toBeVisible({timeout});
        await expect(panel.getByText(text,{exact:true})).toBeVisible({timeout});
      },
      trace:value=>writeFileSync(join(evidence,`current-facts-${call}.safe.json`),JSON.stringify(value,null,2),{mode:0o600,flag:'wx'}),
    });
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
