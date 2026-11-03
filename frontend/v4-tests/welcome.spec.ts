import {test,expect} from '@playwright/test';
const id='11111111-1111-4111-8111-111111111111';
const now='2026-11-03T00:00:00Z';
const base={schema_version:'v4-demo-v1',server_time:now,trace_id:id,status:'OK'};
const source={data_mode:'demo_fixture',evidence_mode:'synthetic_demo',fixture_version:'v4-demo-seed-1',fixture_digest:'a'.repeat(64)};
const context={tenant_id:id,organization_id:id,principal_id:id,shop_id:null,reset_epoch:0,auth_generation:0,authorized_at:now};
test('UI_FIXTURE: welcome creates a session and displays authorized shops',async ({page})=>{
 let created=false, key='';
 await page.route('**/api/v4/demo/**',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(url.pathname.endsWith('/sessions')){key=route.request().postDataJSON().request_key;created=true;return route.fulfill({json:{...base,status:'COMMITTED',context,data:{session:{creation_request_key:key,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source},receipt:{receipt_id:id,operation:'session_create',request_key:key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0}}}});}
  if(url.pathname.endsWith('/session')&&created)return route.fulfill({json:{...base,context,data:{creation_request_key:key,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[],source}}});
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 });
 await page.goto('/v4');await page.getByRole('button',{name:'一键体验'}).click();
 await expect(page.getByText('当前视角没有获授权店铺。')).toBeVisible();
 await expect(page.getByText('演示空间已建立。')).toBeVisible();
});

test('UI_FIXTURE: unknown creation never automatically repeats the POST',async ({page})=>{
 let posts=0; let key='';
 await page.route('**/api/v4/demo/**',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(url.pathname.endsWith('/sessions')){posts++;key=route.request().postDataJSON().request_key;return route.abort('failed');}
  if(url.pathname.includes('/operations/session_create/'))return route.fulfill({json:{...base,status:'UNKNOWN',data:{operation:'session_create',request_key:key,status:'UNKNOWN',recovery:'OWNER_RECOVERY_REQUIRED'}}});
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 });
 await page.goto('/v4');await page.getByRole('button',{name:'一键体验'}).click();
 await expect(page.getByRole('button',{name:'核对原操作'})).toBeVisible();
 await page.getByRole('button',{name:'核对原操作'}).click();
 await expect(page.getByText(/无法恢复会话/)).toBeVisible();
 expect(posts).toBe(1);
});

test('UI_FIXTURE: a definite capacity rejection remains visible without retry',async ({page})=>{
 let posts=0;
 await page.route('**/api/v4/demo/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(path.endsWith('/sessions')){posts++;return route.fulfill({status:429,headers:{'Retry-After':'60'},json:{...base,status:'REJECTED',error:{code:'CAPACITY_LIMIT',safe_message:'full',retryable:false,request_key:null}}});}
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 });
 await page.goto('/v4'); await page.getByRole('button',{name:'一键体验'}).click();
 await expect(page.getByRole('status')).toContainText('60'); expect(posts).toBe(1);
 await expect(page.getByRole('button',{name:'核对原操作'})).toHaveCount(0);
});

test('UI_FIXTURE: persona switch uses current epoch and re-reads server identity',async ({page})=>{
 let key='', persona='operator', generation=0, switched=0;
 const sessionData=()=>({creation_request_key:key,persona_id:persona,expires_at:now,csrf_token:'csrf',shops:[],source});
 await page.route('**/api/v4/demo/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(path.endsWith('/sessions')){key=route.request().postDataJSON().request_key;return route.fulfill({json:{...base,status:'COMMITTED',context,data:{session:sessionData(),receipt:{receipt_id:id,operation:'session_create',request_key:key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0}}}});}
  if(path.endsWith('/session')&&key)return route.fulfill({json:{...base,context:{...context,auth_generation:generation},data:sessionData()}});
  if(path.endsWith('/persona')){const body=route.request().postDataJSON();expect(body.expected_generation).toBe(0);expect(body.expected_epoch).toBe(0);persona=body.persona_id;generation++;switched++;return route.fulfill({json:{...base,status:'COMMITTED',context:{...context,auth_generation:generation},data:{receipt:{receipt_id:id,operation:'persona',request_key:body.request_key,payload_digest:'a'.repeat(64),status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:generation},next_step:'READ_CURRENT_SESSION'}}});}
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 });
 await page.goto('/v4');await page.getByRole('button',{name:'一键体验'}).click();
 await expect(page.getByText('演示空间已建立。')).toBeVisible();
 await page.getByLabel('体验视角').selectOption('approver');await page.getByRole('button',{name:'切换视角'}).click();
 await expect(page.getByText(/当前视角：approver/)).toBeVisible();expect(switched).toBe(1);
});

test('UI_FIXTURE: welcome remains usable on narrow viewport with keyboard focus',async ({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.route('**/api/v4/demo/**',route=>route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}}));
 await page.goto('/v4');const button=page.getByRole('button',{name:'一键体验'});await expect(button).toBeVisible();
 await button.focus();await expect(button).toBeFocused();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});
