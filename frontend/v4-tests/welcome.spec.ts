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
