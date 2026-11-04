import {test,expect,type Page,type Route} from '@playwright/test';

// UI fixtures only: no real backend or authorization evidence.
const id='11111111-1111-4111-8111-111111111111';
const other='22222222-2222-4222-8222-222222222222';
const product='33333333-3333-4333-8333-333333333333';
const key='44444444-4444-4444-8444-444444444444';
const now='2026-11-03T00:00:00Z',digest='a'.repeat(64),after='b'.repeat(64);
const identity={tenant_id:id,organization_id:id,principal_id:id,shop_id:null,reset_epoch:0,auth_generation:0,authorized_at:now};
const source={data_mode:'demo_fixture',evidence_mode:'synthetic_demo',fixture_version:'v4-demo-seed-1',fixture_digest:digest};
const dataset={...source,baseline_snapshot_at:now,uploads:[]};
const itemSource={...source,baseline_snapshot_at:now,import_job_id:null};
const shop=(shop_id:string)=>({shop_id,display_name:shop_id===id?'第一店':'第二店',timezone:'Asia/Taipei',currency:'TWD',grants:['operator']});
const base={schema_version:'v4-demo-v1',server_time:now,trace_id:id,status:'OK'};
const business={schema_version:'v4-business-v1',server_time:now,trace_id:id,status:'OK'};
const failure={...business,status:'REJECTED',error:{code:'ACCESS_DENIED',safe_message:'denied',retryable:false,request_key:null}};
const snapshot={snapshot_id:digest,data_revision:digest,read_at:now,source:dataset};
const detail={snapshot,product:{product_id:product,title:'测试商品',tags:['初始'],version:0,source:itemSource,skus:[{sku_id:id,label:'SKU-1',price:'12',currency:'TWD',available_units:1,stock_reason:null}]},related_order_ids:[]};
const pending={operation:'product_tags',request_key:key,resource_id:product,shop_id:id,revision:digest,version:0,file_digest:null,job_digest:null,parent_job_id:null,context:identity};
function cors(handler:(route:Route)=>Promise<void>|void){return async(route:Route)=>{
 const headers={'access-control-allow-origin':new URL(process.env.V41_WEB_ORIGIN!).origin,'access-control-allow-credentials':'true','access-control-allow-methods':'GET,POST,OPTIONS','access-control-allow-headers':'content-type,x-csrf-token,x-demo-epoch,x-demo-generation'};
 if(route.request().method()==='OPTIONS'){await route.fulfill({status:204,headers});return;}
 const wrapped=new Proxy(route,{get(target,property){if(property==='fulfill')return (options:Parameters<Route['fulfill']>[0])=>target.fulfill({...options,headers:{...options?.headers,...headers}});const value=Reflect.get(target,property,target);return typeof value==='function'?value.bind(target):value;}});
 await handler(wrapped);
};}
async function fixture(page:Page,handler:(route:Route)=>Promise<void>|void){
 await page.route('**/api/v4/demo/**',cors(async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/session'))return route.fulfill({json:{...base,context:identity,data:{creation_request_key:id,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[shop(id),shop(other)],source}}});
  if(path.endsWith('/seed-summary'))return route.fulfill({json:{...base,context:{...identity,shop_id:new URL(route.request().url()).searchParams.get('shop_id')},data:{source,counts:{products:1,skus:1,orders:0,order_lines:0},snapshot_at:now}}});
  if(path.endsWith('/logout')){const request=route.request().postDataJSON();return route.fulfill({json:{...base,status:'COMMITTED',context:identity,data:{receipt:{receipt_id:id,operation:'logout',request_key:request.request_key,payload_digest:digest,status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0},next_step:'LOGGED_OUT'}}});}
  return route.fulfill({status:404,json:failure});
 }));
 await page.route('**/api/v4/**',cors(async route=>{if(new URL(route.request().url()).pathname.startsWith('/api/v4/demo/'))return route.fallback();await handler(route);}));
}
async function openDetail(page:Page){await page.goto(`/v4/products/${product}`);await expect(page.getByRole('combobox',{name:'店铺',exact:true})).toBeVisible();await page.getByRole('combobox',{name:'店铺',exact:true}).selectOption(id);await expect(page.getByRole('heading',{name:'测试商品'})).toBeVisible();}

test('UI_FIXTURE: late denied write cannot clear a newly selected shop',async({page})=>{
 let release!:()=>void;const wait=new Promise<void>(resolve=>{release=resolve;});let dispatched!:()=>void;const sent=new Promise<void>(resolve=>{dispatched=resolve;});
 await fixture(page,async route=>{const url=new URL(route.request().url());if(url.pathname.endsWith('/tags')){dispatched();await wait;return route.fulfill({status:401,json:failure});}return route.fulfill({json:{...business,context:{...identity,shop_id:url.searchParams.get('shop_id')},data:detail}});});
 await openDetail(page);await page.getByRole('button',{name:'编辑标签'}).click();await page.getByLabel('标签（逗号分隔，最多 8 项）').fill('新标签');await page.getByRole('button',{name:'确认保存'}).click();await sent;
 await page.getByRole('dialog',{name:'商品详情'}).getByRole('combobox',{name:'详情店铺',exact:true}).selectOption(other);await expect(page.getByRole('dialog',{name:'商品详情'}).getByRole('combobox',{name:'详情店铺',exact:true})).toHaveValue(other);const denied=page.waitForResponse(response=>response.request().method()==='POST'&&new URL(response.url()).pathname.endsWith('/tags')&&response.status()===401);release();await denied;await expect(page.getByRole('dialog',{name:'商品详情'}).getByRole('combobox',{name:'详情店铺',exact:true})).toHaveValue(other);await expect(page.getByRole('button',{name:'退出演示'})).toBeVisible();
});

for(const stage of ['lookup','readback'] as const)test(`UI_FIXTURE: current recovery ${stage} denial clears and retains original key`,async({page})=>{
 await page.addInitScript(value=>sessionStorage.setItem('commerceops-v41-pending',JSON.stringify(value)),pending);
 let lookups=0;
 await fixture(page,async route=>{
  const url=new URL(route.request().url());if(url.pathname.includes('/actions/')){lookups++;if(stage==='lookup')return route.fulfill({status:403,json:failure});return route.fulfill({json:{...business,context:{...identity,shop_id:id},data:{operation:'product_tags',request_key:key,status:'COMMITTED',receipt:{receipt_id:id,operation:'product_tags',request_key:key,payload_digest:digest,resource_id:product,resource_version:1,committed_at:now,before_revision:digest,after_revision:after}}}});}
  if(lookups&&stage==='readback')return route.fulfill({status:403,json:failure});return route.fulfill({json:{...business,context:{...identity,shop_id:id},data:detail}});
 });
 await openDetail(page);await page.getByRole('dialog',{name:'商品详情'}).getByRole('button',{name:'核对原业务操作'}).click();await expect(page.getByText('当前身份或店铺无法验证，请重新核对会话。')).toBeVisible();await expect(page.getByRole('heading',{name:'测试商品'})).toHaveCount(0);expect(JSON.parse((await page.evaluate(()=>sessionStorage.getItem('commerceops-v41-pending')))!).request_key).toBe(key);
});

test('UI_FIXTURE: pending business evidence does not disable logout after reload',async({page})=>{
 await page.addInitScript(value=>sessionStorage.setItem('commerceops-v41-pending',JSON.stringify(value)),pending);
 await fixture(page,route=>route.fulfill({json:{...business,context:{...identity,shop_id:id},data:detail}}));
 await openDetail(page);await page.reload();await expect(page.getByRole('button',{name:'退出演示'})).toBeEnabled();await page.getByRole('button',{name:'退出演示'}).click();await expect(page.getByText('已退出演示。')).toBeVisible();
 expect(JSON.parse((await page.evaluate(()=>sessionStorage.getItem('commerceops-v41-pending')))!).request_key).toBe(key);
});

test('UI_FIXTURE: nonprinting tag is rejected before a write key or request exists',async({page})=>{
 let posts=0;
 await fixture(page,route=>{if(route.request().method()==='POST')posts++;return route.fulfill({json:{...business,context:{...identity,shop_id:id},data:detail}});});
 await openDetail(page);await page.getByRole('button',{name:'编辑标签'}).click();
 await page.getByLabel('标签（逗号分隔，最多 8 项）').fill('bad\u200btag');
 await expect(page.getByRole('button',{name:'确认保存'})).toBeDisabled();await expect(page.getByText(/标签须为可打印字符/)).toBeVisible();
 expect(posts).toBe(0);expect(await page.evaluate(()=>sessionStorage.getItem('commerceops-v41-pending'))).toBeNull();
});

test('UI_FIXTURE: a shop selection is restored only after a fresh matching session',async({page})=>{
 await fixture(page,route=>route.fulfill({json:{...business,context:{...identity,shop_id:id},data:detail}}));
 await openDetail(page);await page.reload();await expect(page.getByRole('dialog',{name:'商品详情'}).getByRole('combobox',{name:'详情店铺',exact:true})).toHaveValue(id);await expect(page.getByRole('heading',{name:'测试商品'})).toBeVisible();
});

for(const width of [390,1440])test(`UI_FIXTURE: detail drawer opens and Escape returns to list at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:900});
 await fixture(page,route=>route.fulfill({json:{...business,context:{...identity,shop_id:id},data:detail}}));
 await openDetail(page);const drawer=page.getByRole('dialog',{name:'商品详情'});await expect(drawer).toBeVisible();
 expect(await drawer.evaluate(element=>element.contains(document.activeElement))).toBe(true);
 await page.keyboard.press('Escape');await expect(page).toHaveURL(/\/v4\/products$/);
});

test('UI_FIXTURE: old UNKNOWN survives logout while a verified new tenant can write',async({page})=>{
 const newTenant={...identity,tenant_id:other,organization_id:other,principal_id:other};let phase:'old'|'anonymous'|'new'='old',createdKey='',oldLookups=0;
 await page.addInitScript(value=>sessionStorage.setItem('commerceops-v41-pending',JSON.stringify(value)),pending);
 await fixture(page,route=>{
  const path=new URL(route.request().url()).pathname;if(path.includes('/actions/'))oldLookups++;
  return route.fulfill({json:{...business,context:{...(phase==='new'?newTenant:identity),shop_id:id},data:detail}});
 });
 await page.route('**/api/v4/demo/**',cors(async route=>{
  const path=new URL(route.request().url()).pathname,current=phase==='new'?newTenant:identity;
  const sessionData={creation_request_key:phase==='new'?createdKey:id,persona_id:'operator',expires_at:now,csrf_token:'csrf',shops:[shop(id)],source};
  if(path.endsWith('/session')&&phase!=='anonymous')return route.fulfill({json:{...base,context:current,data:sessionData}});
  if(path.endsWith('/seed-summary'))return route.fulfill({json:{...base,context:{...current,shop_id:id},data:{source,counts:{products:1,skus:1,orders:0,order_lines:0},snapshot_at:now}}});
  if(path.endsWith('/logout')){const request=route.request().postDataJSON();phase='anonymous';return route.fulfill({json:{...base,status:'COMMITTED',context:identity,data:{receipt:{receipt_id:id,operation:'logout',request_key:request.request_key,payload_digest:digest,status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0},next_step:'LOGGED_OUT'}}});}
  if(path.endsWith('/bootstrap'))return route.fulfill({json:{...base,data:{csrf_token:'csrf',expires_at:now,state:'anonymous_bootstrap'}}});
  if(path.endsWith('/sessions')){createdKey=route.request().postDataJSON().request_key;phase='new';return route.fulfill({json:{...base,status:'COMMITTED',context:newTenant,data:{session:{...sessionData,creation_request_key:createdKey},receipt:{receipt_id:id,operation:'session_create',request_key:createdKey,payload_digest:digest,status:'COMMITTED',committed_at:now,reset_epoch:0,auth_generation:0}}}});}
  return route.fulfill({status:401,json:{...base,status:'REJECTED',error:{code:'SESSION_INVALID',safe_message:'invalid',retryable:false,request_key:null}}});
 }));
 await openDetail(page);const preserved=await page.evaluate(()=>sessionStorage.getItem('commerceops-v41-pending'));await page.getByRole('button',{name:'退出演示'}).click();await expect(page.getByText('已退出演示。')).toBeVisible();
 await page.getByRole('button',{name:'一键体验'}).click();await expect(page.getByText('演示空间已建立。')).toBeVisible();await page.getByRole('combobox',{name:'店铺',exact:true}).selectOption(id);
 await expect(page.getByRole('button',{name:'编辑标签'})).toBeEnabled();await expect(page.getByRole('dialog',{name:'商品详情'}).getByText('其他演示空间的未确认记录已保留；当前空间独立核对。')).toBeVisible();expect(await page.evaluate(()=>sessionStorage.getItem('commerceops-v41-pending'))).toBe(preserved);expect(oldLookups).toBe(0);
});

test('UI_FIXTURE: session revalidation preserves unsaved tag input',async({page})=>{
 await fixture(page,route=>route.fulfill({json:{...business,context:{...identity,shop_id:id},data:detail}}));
 await openDetail(page);await page.getByRole('button',{name:'编辑标签'}).click();await page.getByLabel('标签（逗号分隔，最多 8 项）').fill('未提交的标签');
 const reread=page.waitForResponse(response=>new URL(response.url()).pathname===`/api/v4/products/${product}`&&response.request().method()==='GET');
 await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await reread;
 await expect(page.getByLabel('标签（逗号分隔，最多 8 项）')).toHaveValue('未提交的标签');
});

test('UI_FIXTURE: session revalidation preserves fulfillment confirmation',async({page})=>{
 const order={snapshot,order:{order_id:product,created_at:now,paid_at:now,payment_status:'payment_recorded',net_amount:'12',currency:'TWD',demo_fulfillment:'demo_unfulfilled',fulfillment_version:0,source:itemSource,lines:[{line_id:id,product_id:product,sku_id:id,quantity:1,net_amount:'12',currency:'TWD'}],refunds:[]}};
 await fixture(page,route=>route.fulfill({json:{...business,context:{...identity,shop_id:id},data:order}}));
 await page.goto(`/v4/orders/${product}`);await page.getByRole('combobox',{name:'店铺',exact:true}).selectOption(id);await page.getByRole('button',{name:'标记演示已履约'}).click();
 await expect(page.getByRole('button',{name:'确认演示履约'})).toBeVisible();
 const reread=page.waitForResponse(response=>new URL(response.url()).pathname===`/api/v4/orders/${product}`&&response.request().method()==='GET');
 await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await reread;
 await expect(page.getByRole('button',{name:'确认演示履约'})).toBeVisible();
});
