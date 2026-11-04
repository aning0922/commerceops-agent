import {test,expect,type Page,type Route} from '@playwright/test';

// React UI Mock only. No API/PG authorization, real effect, or mobile acceptance evidence.
const tenant='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222';
const ids=['33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444'];
const now='2026-11-04T00:00:00Z',digest='a'.repeat(64),revision=(n:number)=>['a','b','c'][n].repeat(64);
const identity={tenant_id:tenant,organization_id:tenant,principal_id:tenant,shop_id:null,reset_epoch:0,auth_generation:0,authorized_at:now};
const source={data_mode:'demo_fixture',evidence_mode:'synthetic_demo',fixture_version:'v4-demo-seed-1',fixture_digest:digest};
const dataset={...source,baseline_snapshot_at:now,uploads:[]};
const demo={schema_version:'v4-demo-v1',server_time:now,trace_id:tenant,status:'OK'};
const envelope={schema_version:'v4-business-v1',server_time:now,trace_id:tenant,status:'OK'};
const shop=(shop_id:string)=>({shop_id,display_name:shop_id===tenant?'第一店':'第二店',timezone:'Asia/Taipei',currency:'TWD',grants:['operator']});
function latch(){let resolve!:()=>void;const promise=new Promise<void>(r=>{resolve=r;});return {promise,resolve};}
type Body={shop_id:string;request_key:string;expected_version:number;expected_data_revision:string;tags:string[]};
async function setup(page:Page,mode:'success'|'unknown'|'conflict'|'held'|'readback409'|'readback403'='success'){
 let committed=0;const requests:Body[]=[],events:string[]=[],sent=latch(),release=latch(),readback=latch();
 const lookups:{method:string;path:string;shop_id:string}[]=[];
 const products=ids.map((product_id,i)=>({product_id,title:`批量商品 ${i+1}`,tags:['原标签'],version:0,source:{...source,baseline_snapshot_at:now,import_job_id:null},skus:[{sku_id:product_id,label:`BATCH-${i}`,price:'12',currency:'TWD',available_units:null,stock_reason:'UNKNOWN_STOCK'}]}));
 const snapshot=()=>({snapshot_id:digest,data_revision:revision(committed),read_at:now,source:dataset});
 async function pending(){return page.evaluate(()=>{
  const raw=sessionStorage.getItem('commerceops-v41-pending:11111111-1111-4111-8111-111111111111');return raw?JSON.parse(raw):null;
 });}
 await page.route('**/api/v4/**',async(route:Route)=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname;
  const headers={'access-control-allow-origin':new URL(process.env.V41_WEB_ORIGIN!).origin,'access-control-allow-credentials':'true','access-control-allow-methods':'GET,POST,OPTIONS','access-control-allow-headers':'content-type,x-csrf-token,x-demo-epoch,x-demo-generation'};
  const fulfill=(json:unknown,status=200)=>route.fulfill({status,headers,json});
  if(request.method()==='OPTIONS')return route.fulfill({status:204,headers});
  if(path==='/api/v4/demo/session')return fulfill({...demo,context:identity,data:{creation_request_key:tenant,persona_id:'operator',expires_at:'2099-01-01T00:00:00Z',csrf_token:'mock-csrf',shops:[shop(tenant),shop(other)],source}});
  if(path==='/api/v4/demo/seed-summary')return fulfill({...demo,context:{...identity,shop_id:url.searchParams.get('shop_id')},data:{source,counts:{products:2,skus:2,orders:0,order_lines:0},snapshot_at:now}});
  const context={...identity,shop_id:url.searchParams.get('shop_id')??tenant};
  if(path==='/api/v4/products')return fulfill({...envelope,context,data:{snapshot:snapshot(),items:products,total:2,next_cursor:null}});
  if(request.method()==='GET'&&ids.some(id=>path===`/api/v4/products/${id}`)){
   const product=products.find(p=>path.endsWith(p.product_id))!;
   events.push(`read:${product.product_id}:v${product.version}`);
   if(committed===1&&product.product_id===ids[0]&&(mode==='readback409'||mode==='readback403')){
    readback.resolve();await release.promise;
    return fulfill({...envelope,status:'REJECTED',error:{code:mode==='readback403'?'ACCESS_DENIED':'VERSION_CONFLICT',safe_message:'Mock readback denied',retryable:false,request_key:requests[0].request_key}},mode==='readback403'?403:409);
   }
   return fulfill({...envelope,context,data:{snapshot:snapshot(),product,related_order_ids:[]}});
  }
  if(request.method()==='POST'&&path.endsWith('/tags')){
   const body=request.postDataJSON() as Body,product=products.find(p=>path===`/api/v4/products/${p.product_id}/tags`)!;
   const original=await pending();expect(original?.request_key).toBe(body.request_key);expect(original?.resource_id).toBe(product.product_id);
   expect(body.expected_version).toBe(product.version);expect(body.expected_data_revision).toBe(revision(committed));
   requests.push(body);events.push(`post:${product.product_id}:${body.request_key}`);sent.resolve();
   if(mode==='held')await release.promise;
   if(mode==='unknown'||mode==='conflict')return fulfill({...envelope,status:mode==='unknown'?'UNKNOWN':'REJECTED',error:{code:mode==='unknown'?'SERVICE_UNAVAILABLE':'VERSION_CONFLICT',safe_message:'Mock stopped',retryable:false,request_key:body.request_key}},mode==='unknown'?503:409);
   const before=revision(committed);product.version++;product.tags=[...body.tags];committed++;
   return fulfill({...envelope,status:'COMMITTED',context:{...identity,shop_id:body.shop_id},data:{next_step:'READ_CURRENT_RESOURCE',receipt:{receipt_id:product.product_id,operation:'product_tags',request_key:body.request_key,payload_digest:digest,resource_id:product.product_id,resource_version:product.version,committed_at:now,before_revision:before,after_revision:revision(committed)}}});
  }
  if(path.includes('/actions/')){
   expect(requests).toHaveLength(1);const original=requests[0];
   expect(request.method()).toBe('GET');expect(path).toBe(`/api/v4/actions/product_tags/${original.request_key}`);
   expect([...url.searchParams.entries()]).toEqual([['shop_id',original.shop_id]]);
   lookups.push({method:request.method(),path,shop_id:original.shop_id});
   return fulfill({...envelope,context:{...identity,shop_id:original.shop_id},data:{operation:'product_tags',request_key:original.request_key,status:'UNKNOWN',receipt:null}});
  }
  throw new Error('UNEXPECTED_MOCK_REQUEST '+request.method()+' '+path);
 });
 await page.goto('/v4/products');await page.getByRole('combobox',{name:'店铺',exact:true}).selectOption(tenant);
 await expect(page.locator('tbody tr')).toHaveCount(2);
 return {requests,events,sent,release,readback,pending,lookups};
}
async function selectTwo(page:Page){
 const rows=page.locator('tbody tr');await rows.nth(0).getByRole('checkbox').check();await rows.nth(1).getByRole('checkbox').check();
 await page.getByRole('button',{name:'批量设置标签',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'批量设置标签',exact:true});await expect(dialog).toBeVisible();return dialog;
}

test('UI_MOCK batch: two selected rows use distinct durable keys and sequential exact readbacks',async({page})=>{
 const f=await setup(page),dialog=await selectTwo(page);await dialog.getByLabel('标签（逗号分隔，最多 8 项）').fill('替换标签');await dialog.getByRole('button',{name:'确认逐项替换'}).click();
 await expect(dialog.getByRole('status',{name:'批量标签进度'})).toHaveText('已核成功 2 · 明确拒绝 0 · 待核对 0 · 未发送 0');
 expect(f.requests).toHaveLength(2);expect(new Set(f.requests.map(r=>r.request_key)).size).toBe(2);expect(f.requests.map(r=>r.tags)).toEqual([['替换标签'],['替换标签']]);
 expect(f.events).toEqual([`read:${ids[0]}:v0`,`post:${ids[0]}:${f.requests[0].request_key}`,`read:${ids[0]}:v1`,`read:${ids[1]}:v0`,`post:${ids[1]}:${f.requests[1].request_key}`,`read:${ids[1]}:v1`]);
 expect(await f.pending()).toBeNull();await dialog.getByRole('button',{name:'取消',exact:true}).click();
 await expect(page.locator('tbody tr').nth(0)).toContainText('替换标签');await expect(page.locator('tbody tr').nth(0)).not.toContainText('原标签');
});

for(const mode of ['unknown','conflict'] as const)test(`UI_MOCK batch: first ${mode} stops the second row and retains its original pending key`,async({page})=>{
 const f=await setup(page,mode),dialog=await selectTwo(page);await dialog.getByLabel('标签（逗号分隔，最多 8 项）').fill('替换标签');await dialog.getByRole('button',{name:'确认逐项替换'}).click();
 // Dispatch already publishes pending; observe POST and completed UI write lock before final assertions.
 await f.sent.promise;await expect(dialog.getByRole('button',{name:'取消',exact:true})).toBeVisible();
 await expect(dialog.getByRole('status',{name:'批量标签进度'})).toHaveText(mode==='unknown'?'已核成功 0 · 明确拒绝 0 · 待核对 1 · 未发送 1':'已核成功 0 · 明确拒绝 1 · 待核对 0 · 未发送 1');
 expect(f.requests).toHaveLength(1);expect((await f.pending()).request_key).toBe(f.requests[0].request_key);
 await dialog.getByRole('button',{name:'取消',exact:true}).click();await page.getByRole('button',{name:'核对原业务操作',exact:true}).click();
 await expect(page.getByText('原操作仍需核对；未重复提交。')).toBeVisible();expect(f.requests).toHaveLength(1);expect((await f.pending()).request_key).toBe(f.requests[0].request_key);
 expect(f.lookups).toEqual([{method:'GET',path:`/api/v4/actions/product_tags/${f.requests[0].request_key}`,shop_id:f.requests[0].shop_id}]);
});

for(const change of ['shop','close','query'] as const)test(`UI_MOCK batch: ${change} cancels remaining rows while a late POST preserves pending`,async({page})=>{
 const f=await setup(page,'held'),dialog=await selectTwo(page);await dialog.getByLabel('标签（逗号分隔，最多 8 项）').fill('替换标签');await dialog.getByRole('button',{name:'确认逐项替换'}).click();await f.sent.promise;
 try{
  if(change==='close')await dialog.getByRole('button',{name:'停止余下操作'}).click();
  else if(change==='shop')await page.getByRole('combobox',{name:'店铺',exact:true}).selectOption(other,{force:true});
  else await page.getByLabel('搜索商品').evaluate((input:HTMLInputElement)=>{input.value='different';input.form!.requestSubmit();});
 }finally{f.release.resolve();}
 // Waiting for the UI write lock to release observes the completed handler, not a timed guess.
 if(change!=='shop'&&change!=='close')await dialog.getByRole('button',{name:'取消',exact:true}).click();
 await expect(page.getByRole('button',{name:'核对原业务操作',exact:true})).toBeEnabled();
 expect(f.requests).toHaveLength(1);expect((await f.pending()).request_key).toBe(f.requests[0].request_key);
 if(change==='shop'){await expect(page.getByRole('combobox',{name:'店铺',exact:true})).toHaveValue(other);await expect(page.getByRole('status',{name:'批量标签进度'})).toHaveCount(0);}
 await expect(page.locator('tbody input[type=checkbox]:checked')).toHaveCount(0);
});

test('UI_MOCK batch: 390px dialog exposes replacement, empty-clear, focus and Escape without dispatch',async({page})=>{
 await page.setViewportSize({width:390,height:844});const f=await setup(page);const trigger=page.getByRole('button',{name:'批量设置标签',exact:true});
 await page.getByRole('checkbox',{name:'选择当前页商品',exact:true}).check();await trigger.click();const dialog=page.getByRole('dialog',{name:'批量设置标签',exact:true});
 await expect(dialog).toContainText('完整替换');await expect(dialog).toContainText('每项独立提交');await expect(dialog).toContainText('空标签表示清空');
 expect(await dialog.evaluate(element=>element.contains(document.activeElement))).toBe(true);
 const input=dialog.getByLabel('标签（逗号分隔，最多 8 项）');await input.fill('重复,重复');await expect(dialog.getByRole('button',{name:'确认逐项替换'})).toBeDisabled();await input.fill('');await expect(dialog.getByRole('button',{name:'确认逐项替换'})).toBeEnabled();
 const bounds=await dialog.boundingBox();expect(bounds).not.toBeNull();expect(bounds!.x).toBeGreaterThanOrEqual(0);expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(390);
 await page.keyboard.press('Escape');await expect(dialog).not.toBeVisible();
 const selectPage=page.getByRole('checkbox',{name:'选择当前页商品',exact:true});
 await expect(selectPage).toBeFocused();await expect(selectPage).not.toBeChecked();await expect(page.locator('tbody input[type=checkbox]:checked')).toHaveCount(0);
 await page.keyboard.press('Space');await expect(selectPage).toBeChecked();await expect(page.locator('tbody input[type=checkbox]:checked')).toHaveCount(2);
 expect(f.requests).toHaveLength(0);expect(await f.pending()).toBeNull();
});

for(const status of [409,403] as const)test(`UI_MOCK batch: COMMITTED POST followed by readback ${status} remains pending, never a rejected write`,async({page})=>{
 const f=await setup(page,status===409?'readback409':'readback403'),dialog=await selectTwo(page);
 await dialog.getByLabel('标签（逗号分隔，最多 8 项）').fill('替换标签');
 const posted=page.waitForResponse(response=>response.request().method()==='POST'&&new URL(response.url()).pathname.endsWith('/tags'));
 await dialog.getByRole('button',{name:'确认逐项替换'}).click();
 const response=await posted;expect(response.status()).toBe(200);expect((await response.json()).status).toBe('COMMITTED');
 try{
  await f.readback.promise;
  await expect(dialog.getByRole('status',{name:'批量标签进度'})).toHaveText('已核成功 0 · 明确拒绝 0 · 待核对 1 · 未发送 1');
 }finally{f.release.resolve();}
 if(status===409){
  await expect(dialog.getByRole('button',{name:'取消',exact:true})).toBeVisible();
  await expect(dialog.getByRole('status',{name:'批量标签进度'})).toHaveText('已核成功 0 · 明确拒绝 0 · 待核对 1 · 未发送 1');
 }else{
  // Current 403 must still clear the old scope; never resurrect progress just for this assertion.
  await expect(page.getByText('当前身份或店铺无法验证，请重新核对会话。')).toBeVisible();
  await expect(page.getByRole('status',{name:'批量标签进度'})).toHaveCount(0);
  await expect(page.getByRole('dialog',{name:'批量设置标签',exact:true})).not.toBeVisible();
 }
 expect(f.requests).toHaveLength(1);expect((await f.pending()).request_key).toBe(f.requests[0].request_key);
 expect(f.events.filter(event=>event.startsWith('post:'))).toHaveLength(1);
});
