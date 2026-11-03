import {test,expect,type Page,type Route} from '@playwright/test';
const fixtureCors = {
 'access-control-allow-origin': new URL(process.env.V4_WEB_ORIGIN ?? 'http://127.0.0.1:3000').origin,
 'access-control-allow-credentials':'true',
 'access-control-expose-headers':'Retry-After',
 'access-control-allow-methods':'GET,POST,OPTIONS',
 'access-control-allow-headers':'content-type,x-csrf-token,x-demo-epoch,x-demo-generation',
};
// Only fixture routes get these headers; real API CORS remains a separate Gate.
function withCors(handler:(route:Route)=>unknown) {
 return async (route:Route) => {
  if (route.request().method()==='OPTIONS') {await route.fulfill({status:204,headers:fixtureCors});return;}
  const wrapped = new Proxy(route,{get(target,property){
   if(property==='fulfill') return (options:Parameters<Route['fulfill']>[0])=>target.fulfill({...options,headers:{...options?.headers,...fixtureCors}});
   const value=Reflect.get(target,property,target);return typeof value==='function'?value.bind(target):value;
  }});
  await handler(wrapped);
 };
}
const id='11111111-1111-4111-8111-111111111111';
const now='2026-11-03T00:00:00Z';
const base={schema_version:'v4-demo-v1',server_time:now,trace_id:id,status:'OK'};
const source={data_mode:'demo_fixture',evidence_mode:'synthetic_demo',fixture_version:'v4-demo-seed-1',fixture_digest:'a'.repeat(64)};
const context={tenant_id:id,organization_id:id,principal_id:id,shop_id:null,reset_epoch:0,auth_generation:0,authorized_at:now};
test('UI_FIXTURE: welcome creates a session and displays authorized shops',async ({page})=>{
 let created=false, key='';
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  const url=new URL(route.request().url());
  if(url.pathname.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(url.pathname.endsWith('/sessions')){key=route.request().postDataJSON().request_key;created=true;return route.fulfill({json:{...base,status:'COMMITTED',context,data:{session:{creation_request_key:key,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source},receipt:{receipt_id:id,operation:'session_create',request_key:key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0}}}});}
  if(url.pathname.endsWith('/session')&&created)return route.fulfill({json:{...base,context,data:{creation_request_key:key,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}});
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 await page.goto('/v4');await page.getByRole('button',{name:'一键体验'}).click();
 await expect(page.getByText('当前视角没有获授权店铺。')).toBeVisible();
 await expect(page.getByText('演示空间已建立。')).toBeVisible();
});

test('UI_FIXTURE: unknown creation never automatically repeats the POST',async ({page})=>{
 let posts=0; let key='';
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  const url=new URL(route.request().url());
  if(url.pathname.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(url.pathname.endsWith('/sessions')){posts++;key=route.request().postDataJSON().request_key;return route.abort('failed');}
  if(url.pathname.includes('/operations/session_create/'))return route.fulfill({json:{...base,status:'UNKNOWN',data:{operation:'session_create',request_key:key,status:'UNKNOWN',recovery:'OWNER_RECOVERY_REQUIRED'}}});
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 await page.goto('/v4');await page.getByRole('button',{name:'一键体验'}).click();
 await expect(page.getByRole('button',{name:'核对原操作'})).toBeVisible();
 await page.getByRole('button',{name:'核对原操作'}).click();
 await expect(page.getByText(/无法恢复会话/)).toBeVisible();
 expect(posts).toBe(1);
});

test('UI_FIXTURE: a definite capacity rejection remains visible without retry',async ({page})=>{
 let posts=0;
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(path.endsWith('/sessions')){posts++;return route.fulfill({status:429,headers:{'Retry-After':'60'},json:{...base,status:'REJECTED',error:{code:'CAPACITY_LIMIT',safe_message:'full',retryable:false,request_key:null}}});}
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 await page.goto('/v4'); await page.getByRole('button',{name:'一键体验'}).click();
 await expect(page.getByRole('status')).toContainText('60'); expect(posts).toBe(1);
 await expect(page.getByRole('button',{name:'核对原操作'})).toHaveCount(0);
});

test('UI_FIXTURE: persona switch uses current epoch and re-reads server identity',async ({page})=>{
 let key='', persona='operator', generation=0, switched=0;
 const sessionData=()=>({creation_request_key:key,persona_id:persona,expires_at:now,csrf_token:'csrf',shops:[],source});
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(path.endsWith('/sessions')){key=route.request().postDataJSON().request_key;return route.fulfill({json:{...base,status:'COMMITTED',context,data:{session:sessionData(),receipt:{receipt_id:id,operation:'session_create',request_key:key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0}}}});}
  if(path.endsWith('/session')&&key)return route.fulfill({json:{...base,context:{...context,principal_id:persona==='operator'?id:'22222222-2222-4222-8222-222222222222',auth_generation:generation},data:sessionData()}});
  if(path.endsWith('/persona')){const body=route.request().postDataJSON();expect(body.expected_generation).toBe(0);expect(body.expected_epoch).toBe(0);persona=body.persona_id;generation++;switched++;return route.fulfill({json:{...base,status:'COMMITTED',context:{...context,principal_id:persona==='operator'?id:'22222222-2222-4222-8222-222222222222',auth_generation:generation},data:{receipt:{receipt_id:id,operation:'persona',request_key:body.request_key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:generation},next_step:'READ_CURRENT_SESSION'}}});}
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 await page.goto('/v4');await page.getByRole('button',{name:'一键体验'}).click();
 await expect(page.getByText('演示空间已建立。')).toBeVisible();
 await page.getByLabel('体验视角').selectOption('approver');await page.getByRole('button',{name:'切换视角'}).click();
 await expect(page.getByText(/当前视角：approver/)).toBeVisible();expect(switched).toBe(1);
});

test('UI_FIXTURE: welcome remains usable on narrow viewport with keyboard focus',async ({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.route('**/api/v4/demo/**',withCors(route=>route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}})));
 await page.goto('/v4');const button=page.getByRole('button',{name:'一键体验'});await expect(button).toBeVisible();
 await button.focus();await expect(button).toBeFocused();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test('UI_FIXTURE: revalidation clears a shop whose grant was removed',async ({page})=>{
 let key='',allowed=true;
 const shop={shop_id:id,display_name:'示例店铺',timezone:'Asia/Taipei',currency:'TWD',grants:['read']};
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(path.endsWith('/sessions')){key=route.request().postDataJSON().request_key;return route.fulfill({json:{...base,status:'COMMITTED',context,data:{session:{creation_request_key:key,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[shop],source},receipt:{receipt_id:id,operation:'session_create',request_key:key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0}}}});}
  if(path.endsWith('/session')&&key)return route.fulfill({json:{...base,context,data:{creation_request_key:key,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:allowed?[shop]:[],source}}});
  if(path.endsWith('/seed-summary'))return route.fulfill({json:{...base,context:{...context,shop_id:id},data:{source,counts:{products:2,skus:3,orders:4,order_lines:5},snapshot_at:now}}});
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 await page.goto('/v4');await page.getByRole('button',{name:'一键体验'}).click();
 await expect(page.getByText('演示空间已建立。')).toBeVisible();await page.getByLabel('店铺').selectOption(id);
 await expect(page.getByText(/商品 2/)).toBeVisible();allowed=false;
 await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await expect(page.getByText(/商品 2/)).toHaveCount(0);await expect(page.getByText('当前视角没有获授权店铺。')).toBeVisible();
});

test('UI_FIXTURE: rapid repeated activation makes only one bootstrap request',async ({page})=>{
 let bootstraps=0;
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/bootstrap')){bootstraps++;return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});}
  if(path.endsWith('/sessions'))return route.abort('failed');
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 await page.goto('/v4');const button=page.getByRole('button',{name:'一键体验'});await expect(button).toBeVisible();
 await button.evaluate(element=>{(element as HTMLButtonElement).click();(element as HTMLButtonElement).click();});
 await expect(page.getByRole('button',{name:'核对原操作'})).toBeVisible();expect(bootstraps).toBe(1);
});

test('UI_FIXTURE: corrupt pending storage fails closed without creating a space',async ({page})=>{
 let calls=0;
 await page.addInitScript(()=>sessionStorage.setItem('commerceops-v4-pending','{'));
 await page.route('**/api/v4/demo/**',route=>{calls++;return route.abort();});
 await page.goto('/v4');
 await expect(page.getByRole('status')).toContainText('无法读取待核对记录');
 await expect(page.getByRole('button',{name:'一键体验'})).toHaveCount(0);
 expect(calls).toBe(0);
});

test('UI_FIXTURE: reset confirms once and logout clears the visible session',async ({page})=>{
 let key='', epoch=0, generation=0, active=false, resets=0, logouts=0;
 const sessionData=()=>({creation_request_key:key,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source});
 const currentContext=()=>({...context,reset_epoch:epoch,auth_generation:generation});
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(path.endsWith('/sessions')){key=route.request().postDataJSON().request_key;active=true;return route.fulfill({json:{...base,status:'COMMITTED',context:currentContext(),data:{session:sessionData(),receipt:{receipt_id:id,operation:'session_create',request_key:key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:epoch,auth_generation:generation}}}});}
  if(path.endsWith('/session')&&active)return route.fulfill({json:{...base,context:currentContext(),data:sessionData()}});
  if(path.endsWith('/reset')||path.endsWith('/logout')){
   const body=route.request().postDataJSON();const operation=path.endsWith('/reset')?'reset':'logout';
   expect(body.expected_epoch).toBe(epoch);expect(body.expected_generation).toBe(generation);
   if(operation==='reset'){resets++;epoch++;generation++;}else{logouts++;active=false;}
   return route.fulfill({json:{...base,status:'COMMITTED',context:currentContext(),data:{receipt:{receipt_id:id,operation,request_key:body.request_key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:epoch,auth_generation:generation},next_step:operation==='reset'?'READ_CURRENT_SESSION':'LOGGED_OUT'}}});
  }
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 await page.goto('/v4');await page.getByRole('button',{name:'一键体验'}).click();
 await expect(page.getByText('演示空间已建立。')).toBeVisible();
 await page.getByRole('button',{name:'重置演示'}).click();await page.getByRole('button',{name:'确认重置'}).click();
 await expect(page.getByText('当前演示空间已重置。')).toBeVisible();expect(resets).toBe(1);
 await page.getByRole('button',{name:'退出'}).click();await expect(page.getByText('已退出演示。')).toBeVisible();
 await expect(page.getByText(/当前视角：/)).toHaveCount(0);expect(logouts).toBe(1);
});

test('UI_FIXTURE: another tab revalidates identity after a persona switch',async ({browser})=>{
 const contextBrowser=await browser.newContext();let key='',persona='operator',generation=0,active=false;
 const sessionData=()=>({creation_request_key:key,persona_id:persona,expires_at:now,csrf_token:'csrf',shops:[],source});
 await contextBrowser.route('**/api/v4/demo/**',withCors(async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(path.endsWith('/sessions')){key=route.request().postDataJSON().request_key;active=true;return route.fulfill({json:{...base,status:'COMMITTED',context,data:{session:sessionData(),receipt:{receipt_id:id,operation:'session_create',request_key:key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0}}}});}
  if(path.endsWith('/session')&&active)return route.fulfill({json:{...base,context:{...context,principal_id:persona==='operator'?id:'22222222-2222-4222-8222-222222222222',auth_generation:generation},data:sessionData()}});
  if(path.endsWith('/persona')){const body=route.request().postDataJSON();persona=body.persona_id;generation++;return route.fulfill({json:{...base,status:'COMMITTED',context:{...context,principal_id:persona==='operator'?id:'22222222-2222-4222-8222-222222222222',auth_generation:generation},data:{receipt:{receipt_id:id,operation:'persona',request_key:body.request_key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:generation},next_step:'READ_CURRENT_SESSION'}}});}
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 try {
  const first=await contextBrowser.newPage();await first.goto('/v4');await first.getByRole('button',{name:'一键体验'}).click();await expect(first.getByText('演示空间已建立。')).toBeVisible();
  const second=await contextBrowser.newPage();await second.goto('/v4');await expect(second.getByText(/当前视角：operator/)).toBeVisible();
  await first.bringToFront();await first.getByLabel('体验视角').selectOption('approver');await first.getByRole('button',{name:'切换视角'}).click();await expect(first.getByText(/当前视角：approver/)).toBeVisible();
  await second.bringToFront();await expect(second.getByText(/当前视角：approver/)).toBeVisible();await expect(second.getByText(/当前视角：operator/)).toHaveCount(0);
 } finally {await contextBrowser.close();}
});

test('UI_FIXTURE: a late first-shop summary cannot overwrite the second shop',async ({page})=>{
 const secondId='22222222-2222-4222-8222-222222222222';
 const shops=[{shop_id:id,display_name:'第一家',timezone:'Asia/Taipei',currency:'TWD',grants:['read']},{shop_id:secondId,display_name:'第二家',timezone:'Asia/Taipei',currency:'TWD',grants:['read']}];
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  const url=new URL(route.request().url());
  if(url.pathname.endsWith('/session'))return route.fulfill({json:{...base,context,data:{creation_request_key:id,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops,source}}});
  if(url.pathname.endsWith('/seed-summary')){
   expect(route.request().headers()['x-demo-epoch']).toBe('0');expect(route.request().headers()['x-demo-generation']).toBe('0');
   const target=url.searchParams.get('shop_id');if(target===id)await new Promise(resolve=>setTimeout(resolve,150));
   return route.fulfill({json:{...base,context:{...context,shop_id:target},data:{source,counts:{products:target===id?111:222,skus:1,orders:1,order_lines:1},snapshot_at:now}}});
  }
  return route.abort();
 }));
 await page.goto('/v4');const select=page.getByLabel('店铺');await expect(select).toBeVisible();
 await select.selectOption(id);await select.selectOption(secondId);
 await expect(page.getByText(/商品 222/)).toBeVisible();await page.waitForTimeout(250);await expect(page.getByText(/商品 111/)).toHaveCount(0);
});

test('UI_FIXTURE: lost creation body recovers only with the original request key',async ({page})=>{
 let original='',posts=0;
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(path.endsWith('/sessions')){posts++;original=route.request().postDataJSON().request_key;return route.abort('failed');}
  if(path.endsWith('/session')&&original)return route.fulfill({json:{...base,context,data:{creation_request_key:original,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}});
  if(path.endsWith(`/operations/session_create/${original}`))return route.fulfill({json:{...base,data:{receipt:{receipt_id:id,operation:'session_create',request_key:original,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0}}}});
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 await page.goto('/v4');await page.getByRole('button',{name:'一键体验'}).click();await expect(page.getByRole('button',{name:'核对原操作'})).toBeVisible();
 await page.getByRole('button',{name:'核对原操作'}).click();await expect(page.getByText('已核对原操作回执。')).toBeVisible();expect(posts).toBe(1);
});

test('UI_FIXTURE: server expiry clears session without creating another',async ({page})=>{
 let expired=false,posts=0;
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  if(route.request().method()==='POST')posts++;
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/session')&&!expired)return route.fulfill({json:{...base,context,data:{creation_request_key:id,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}});
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'EXPIRED',safe_message:'expired',retryable:false,request_key:null}}});
 }));
 await page.goto('/v4');await expect(page.getByText(/当前视角：operator/)).toBeVisible();
 expired=true;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await expect(page.getByRole('status')).toContainText('已到期');
 await expect(page.getByText(/当前视角：operator/)).toHaveCount(0);expect(posts).toBe(0);
});

for (const width of [1280,1440]) {
 test(`UI_FIXTURE: welcome fits ${width}px desktop viewport`,async ({page})=>{
  await page.setViewportSize({width,height:900});
  await page.route('**/api/v4/demo/**',withCors(route=>route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}})));
  await page.goto('/v4');await expect(page.getByRole('button',{name:'一键体验'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 });
}

test('UI_FIXTURE: reset dialog closes with Escape and returns focus',async ({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.route('**/api/v4/demo/**',withCors(route=>route.fulfill({json:{...base,context,data:{creation_request_key:id,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}})));
 await page.goto('/v4');const opener=page.getByRole('button',{name:'重置演示'});await expect(opener).toBeVisible();
 await opener.click();const dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();
 await page.keyboard.press('Escape');await expect(dialog).not.toBeVisible();await expect(opener).toBeFocused();
});

test('UI_FIXTURE: an invalidation closes the reset dialog before revalidation',async ({page})=>{
 await page.route('**/api/v4/demo/**',withCors(route=>route.fulfill({json:{...base,context,data:{creation_request_key:id,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}})));
 await page.goto('/v4');await page.getByRole('button',{name:'重置演示'}).click();
 const dialog=page.getByRole('dialog',{name:'重置当前演示空间？'});await expect(dialog).toBeVisible();
 await page.context().setOffline(true);
 await expect(dialog).not.toBeVisible();await expect(page.getByText(/当前视角：operator/)).toHaveCount(0);
});

// Capture only session-read call sites and lifecycle event names; no cookies, headers or bodies.
async function traceInitialSessionReads(page:Page) {
 await page.addInitScript(()=>{
  const traced=window as Window & {__v4InitialTrace?:{kind:string;at:number;stack?:string}[]};
  traced.__v4InitialTrace=[];
  const original=window.fetch;
  window.fetch=function(input:RequestInfo|URL,init?:RequestInit) {
   const raw=typeof input==='string'?input:input instanceof URL?input.href:input.url;
   if(new URL(raw,location.href).pathname==='/api/v4/demo/session')traced.__v4InitialTrace?.push({kind:'session-fetch',at:performance.now(),stack:new Error().stack});
   return original.call(this,input,init);
  };
  for(const kind of ['focus','online','offline']) window.addEventListener(kind,()=>traced.__v4InitialTrace?.push({kind,at:performance.now()}));
  document.addEventListener('visibilitychange',()=>traced.__v4InitialTrace?.push({kind:`visibility:${document.visibilityState}`,at:performance.now()}));
 });
}

test('UI_FIXTURE: an anonymous page does not poll or create sessions',async ({page},testInfo)=>{
 let reads=0,posts=0;const paths:string[]=[];await page.clock.install();await traceInitialSessionReads(page);
 await page.route('**/api/v4/demo/**',withCors(route=>{
  const req=route.request();paths.push(`${req.method()} ${new URL(req.url()).pathname}`);
  if(req.method()==='POST')posts++;else reads++;
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 try {
  await page.goto('/v4');await page.waitForLoadState('networkidle');
  const baseline=reads;
  // One mount read or the observed two startup reads are accepted; both must be session-only.
  expect([1,2]).toContain(baseline);expect(paths).toEqual(Array(baseline).fill('GET /api/v4/demo/session'));
  await page.clock.fastForward('00:15');expect(reads).toBe(baseline);expect(posts).toBe(0);
 } finally {
  const trace=await page.evaluate(()=>(window as Window & {__v4InitialTrace?:unknown}).__v4InitialTrace??[]);
  await testInfo.attach('anonymous-startup-trace',{body:JSON.stringify({reads,posts,paths,trace},null,2),contentType:'application/json'});
 }
});

test('UI_FIXTURE: an explicit cross-tab invalidation permits one anonymous recheck',async ({page},testInfo)=>{
 let reads=0;const paths:string[]=[];await traceInitialSessionReads(page);
 await page.route('**/api/v4/demo/**',withCors(route=>{
  const req=route.request();paths.push(`${req.method()} ${new URL(req.url()).pathname}`);reads++;
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 try {
  await page.goto('/v4');await page.waitForLoadState('networkidle');const baseline=reads;
  expect([1,2]).toContain(baseline);expect(paths).toEqual(Array(baseline).fill('GET /api/v4/demo/session'));
  await page.evaluate(()=>{const channel=new BroadcastChannel('commerceops-v4-invalidate');channel.postMessage('invalidate');channel.close();});
  await expect.poll(()=>reads).toBe(baseline+1);await page.waitForLoadState('networkidle');
  expect(reads).toBe(baseline+1);expect(paths).toEqual(Array(baseline+1).fill('GET /api/v4/demo/session'));
 } finally {
  const trace=await page.evaluate(()=>(window as Window & {__v4InitialTrace?:unknown}).__v4InitialTrace??[]);
  await testInfo.attach('invalidation-startup-trace',{body:JSON.stringify({reads,paths,trace},null,2),contentType:'application/json'});
 }
});

test('UI_FIXTURE: a verified visible session is rechecked on its interval',async ({page})=>{
 let reads=0;await page.clock.install();
 await page.route('**/api/v4/demo/**',withCors(route=>{
  reads++;return route.fulfill({json:{...base,context,data:{creation_request_key:id,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}});
 }));
 await page.goto('/v4');await expect(page.getByText(/当前视角：operator/)).toBeVisible();
 await page.clock.fastForward('00:05');await expect.poll(()=>reads).toBeGreaterThanOrEqual(2);
});

test('UI_FIXTURE: a control receipt from a different tenant is never shown as success',async ({page})=>{
 let key='',calls=0;
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(path.endsWith('/sessions')){key=route.request().postDataJSON().request_key;return route.fulfill({json:{...base,status:'COMMITTED',context,data:{session:{creation_request_key:key,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source},receipt:{receipt_id:id,operation:'session_create',request_key:key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0}}}});}
  if(path.endsWith('/session')&&key)return route.fulfill({json:{...base,context,data:{creation_request_key:key,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}});
  if(path.endsWith('/persona')){calls++;const body=route.request().postDataJSON();return route.fulfill({json:{...base,status:'COMMITTED',context:{...context,tenant_id:'22222222-2222-4222-8222-222222222222',auth_generation:1},data:{receipt:{receipt_id:id,operation:'persona',request_key:body.request_key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:1},next_step:'READ_CURRENT_SESSION'}}});}
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 await page.goto('/v4');await page.getByRole('button',{name:'一键体验'}).click();
 await expect(page.getByText('演示空间已建立。')).toBeVisible();await page.getByLabel('体验视角').selectOption('approver');await page.getByRole('button',{name:'切换视角'}).click();
 await expect(page.getByText('操作结果未知，请使用原操作核对。')).toBeVisible();await expect(page.getByText('身份视角已更新。')).toHaveCount(0);expect(calls).toBe(1);
});

test('UI_FIXTURE: creation response and current session must share the same identity',async ({page})=>{
 let key='';const other='22222222-2222-4222-8222-222222222222';
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(path.endsWith('/sessions')){key=route.request().postDataJSON().request_key;return route.fulfill({json:{...base,status:'COMMITTED',context:{...context,tenant_id:other},data:{session:{creation_request_key:key,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source},receipt:{receipt_id:id,operation:'session_create',request_key:key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0}}}});}
  if(path.endsWith('/session')&&key)return route.fulfill({json:{...base,context,data:{creation_request_key:key,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}});
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 await page.goto('/v4');await page.getByRole('button',{name:'一键体验'}).click();
 await expect(page.getByText('结果未知，请使用原操作核对。')).toBeVisible();await expect(page.getByText('演示空间已建立。')).toHaveCount(0);
});

test('UI_FIXTURE: current persona is selected and cannot be switched to itself',async ({page})=>{
 let writes=0;
 await page.route('**/api/v4/demo/**',withCors(route=>{
  if(route.request().method()==='POST')writes++;
  return route.fulfill({json:{...base,context,data:{creation_request_key:id,persona_id:'approver',expires_at:now,csrf_token:'csrf',shops:[],source}}});
 }));
 await page.goto('/v4');await expect(page.getByLabel('体验视角')).toHaveValue('approver');
 await expect(page.getByRole('button',{name:'切换视角'})).toBeDisabled();expect(writes).toBe(0);
});

test('UI_FIXTURE: rejected capacity requires a new explicit entry and new key',async ({page})=>{
 let bootstraps=0,posts=0,active=false;const keys:string[]=[];await page.clock.install();
 await page.route('**/api/v4/demo/**',withCors(async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/bootstrap')){bootstraps++;return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});}
  if(path.endsWith('/sessions')){
   posts++;const key=route.request().postDataJSON().request_key;keys.push(key);
   if(posts===1)return route.fulfill({status:429,headers:{'Retry-After':'60'},json:{...base,status:'REJECTED',error:{code:'CAPACITY_LIMIT',safe_message:'full',retryable:false,request_key:key}}});
   active=true;return route.fulfill({json:{...base,status:'COMMITTED',context,data:{session:{creation_request_key:key,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source},receipt:{receipt_id:id,operation:'session_create',request_key:key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0}}}});
  }
  if(path.endsWith('/session')&&active)return route.fulfill({json:{...base,context,data:{creation_request_key:keys[1],persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}});
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 await page.goto('/v4');await page.getByRole('button',{name:'一键体验'}).click();await expect(page.getByRole('status')).toContainText('60');
 await page.clock.fastForward('00:15');expect(bootstraps).toBe(1);expect(posts).toBe(1);
 await page.getByRole('button',{name:'一键体验'}).click();await expect(page.getByText('演示空间已建立。')).toBeVisible();
 expect(bootstraps).toBe(2);expect(posts).toBe(2);expect(keys[0]).not.toBe(keys[1]);
});

for (const scenario of ['401','403','UNKNOWN','MALFORMED'] as const) {
 test(`UI_FIXTURE: ${scenario} shop summary clears the current identity`,async ({page})=>{
  const shop={shop_id:id,display_name:'示例店铺',timezone:'Asia/Taipei',currency:'TWD',grants:['read']};
  await page.route('**/api/v4/demo/**',withCors(route=>{
   const path=new URL(route.request().url()).pathname;
   if(path.endsWith('/session'))return route.fulfill({json:{...base,context,data:{creation_request_key:id,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[shop],source}}});
   if(path.endsWith('/seed-summary')){
    if(scenario==='401'||scenario==='403')return route.fulfill({status:Number(scenario),json:{...base,status:'REJECTED',error:{code:scenario==='401'?'SESSION_INVALID':'ACCESS_DENIED',safe_message:'denied',retryable:false,request_key:null}}});
    if(scenario==='MALFORMED')return route.fulfill({json:{...base,data:{unexpected:true}}});
    return route.fulfill({json:{...base,status:'UNKNOWN',context:{...context,shop_id:id},data:{source,counts:{products:1,skus:1,orders:1,order_lines:1},snapshot_at:now}}});
   }
   return route.abort();
  }));
  await page.goto('/v4');await page.getByLabel('店铺').selectOption(id);
  await expect(page.getByText('当前身份或店铺无法验证，请重新核对会话。')).toBeVisible();
  await expect(page.getByText(/当前视角：operator/)).toHaveCount(0);
  await expect(page.getByLabel('店铺')).toHaveCount(0);
 });
}

test('UI_FIXTURE: restricted admin selection sends its persona ID',async ({page})=>{
 let sent='';
 await page.route('**/api/v4/demo/**',withCors(route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/session'))return route.fulfill({json:{...base,context,data:{creation_request_key:id,persona_id:sent||'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}});
  if(path.endsWith('/persona')){const body=route.request().postDataJSON();sent=body.persona_id;return route.abort('failed');}
  return route.abort();
 }));
 await page.goto('/v4');await page.getByLabel('体验视角').selectOption('restricted_admin');
 await page.getByRole('button',{name:'切换视角'}).click();await expect(page.getByRole('button',{name:'核对原操作'})).toBeVisible();
 expect(sent).toBe('restricted_admin');
});

for (const operation of ['reset','persona'] as const) {
 test(`UI_FIXTURE: ${operation} receipt without the required counter changes remains unknown`,async ({page})=>{
  await page.route('**/api/v4/demo/**',withCors(route=>{
   const path=new URL(route.request().url()).pathname;
   if(path.endsWith('/session'))return route.fulfill({json:{...base,context,data:{creation_request_key:id,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}});
   if(path.endsWith(`/${operation}`)){const body=route.request().postDataJSON();return route.fulfill({json:{...base,status:'COMMITTED',context,data:{receipt:{receipt_id:id,operation,request_key:body.request_key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0},next_step:'READ_CURRENT_SESSION'}}});}
   return route.abort();
  }));
  await page.goto('/v4');await expect(page.getByText(/当前视角：operator/)).toBeVisible();
  if(operation==='reset'){await page.getByRole('button',{name:'重置演示'}).click();await page.getByRole('button',{name:'确认重置'}).click();}
  else {await page.getByLabel('体验视角').selectOption('approver');await page.getByRole('button',{name:'切换视角'}).click();}
  await expect(page.getByText('操作结果未知，请使用原操作核对。')).toBeVisible();
  await expect(page.getByText(operation==='reset'?'当前演示空间已重置。':'身份视角已更新。')).toHaveCount(0);
 });
}

for (const hasProof of [false,true]) {
 test(`UI_FIXTURE: reset recovery ${hasProof?'with':'without'} original context`,async ({page})=>{
  const proof={context,creation_request_key:id,persona_id:'operator',target_persona:null};
  await page.addInitScript(({pending})=>sessionStorage.setItem('commerceops-v4-pending',JSON.stringify(pending)),{pending:hasProof?{operation:'reset',key:id,proof}:{operation:'reset',key:id}});
  const after={...context,reset_epoch:1,auth_generation:1};
  await page.route('**/api/v4/demo/**',withCors(route=>{
   const path=new URL(route.request().url()).pathname;
   if(path.endsWith('/session'))return route.fulfill({json:{...base,context:after,data:{creation_request_key:id,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}});
   if(path.endsWith(`/operations/reset/${id}`))return route.fulfill({json:{...base,data:{receipt:{receipt_id:id,operation:'reset',request_key:id,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:1,auth_generation:1}}}});
   return route.abort();
  }));
  await page.goto('/v4');await page.getByRole('button',{name:'核对原操作'}).click();
  if(hasProof)await expect(page.getByText('已核对原操作回执。')).toBeVisible();
  else {await expect(page.getByText(/无法完整核验/)).toBeVisible();await expect(page.getByText('已核对原操作回执。')).toHaveCount(0);}
 });
}

for(const width of [360,390]) {
 test(`UI_FIXTURE: mobile navigation links are keyboard reachable at ${width}px`,async ({page})=>{
  let posts=0;await page.setViewportSize({width,height:844});
  await page.route('**/api/v4/demo/**',withCors(route=>{if(route.request().method()==='POST')posts++;return route.fulfill({json:{...base,context,data:{creation_request_key:id,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}});}));
  await page.goto('/v4');const nav=page.getByRole('navigation',{name:'演示导航'});await expect(nav).toBeVisible();
  await expect(nav.getByRole('link',{name:'欢迎'})).toHaveAttribute('aria-current','page');
  await expect(nav.getByRole('link',{name:'演示空间'})).toHaveAttribute('href','/v4/demo');
  const target=nav.getByRole('link',{name:'演示设置'});await expect(target).toHaveAttribute('href','/v4/settings/demo');
  await target.focus();await expect(target).toBeFocused();await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/v4\/settings\/demo$/);
  await expect(page.getByRole('navigation',{name:'演示导航'}).getByRole('link',{name:'演示设置'})).toHaveAttribute('aria-current','page');
  await expect(page.getByText(/当前视角：operator/)).toBeVisible();expect(posts).toBe(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 });
}
