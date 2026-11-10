import {test,expect,type Page,type Response,type Request,type Locator} from '@playwright/test';
import {createHash} from 'node:crypto';
import {mkdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {readBrowserCase,subjectWriter} from './browser-subjects';
import {assertScope,installBusinessJournal,installSessionRegistration,subjectContext,validated,waitApi,safeSession,type Identity} from './live-business.fixture';

const sha=(value:string|Buffer)=>createHash('sha256').update(value).digest('hex');
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function keyOf(response:Response){const key=response.request().postDataJSON()?.request_key;if(typeof key!=='string'||!uuid.test(key))throw new Error('INVALID_ORIGINAL_KEY');return key;}
function waitProducts(page:Page,api:string,shop:string,q:string,cursor:string){
 return page.waitForResponse(response=>{const url=new URL(response.url());return url.origin===api&&url.pathname==='/api/v4/products'&&response.request().method()==='GET'&&url.searchParams.get('shop_id')===shop&&(url.searchParams.get('q')??'')===q&&(url.searchParams.get('cursor')??'')===cursor;});
}
function pathFor(kind:'product_tags'|'order_fulfillment',id:string){return `/api/v4/${kind==='product_tags'?'products':'orders'}/${id}/${kind==='product_tags'?'tags':'fulfillment'}`;}
async function readable(page:Page,method:()=>Promise<void>,read:Promise<Response>,schema:string,identity:Identity,shop:string){
 await method();const result=await validated(await read,'business',schema);assertScope(result.context,identity,shop);return result;
}

type ScreenshotFact={state:string;width:number;path:string;sha256:string;pixel_width:number;pixel_height:number;viewport:{width:number;height:number;dpr:number};route:string;source:Record<string,unknown>};
function progressCounts(text:string){
 const result:Record<string,number>={};
 for(const match of text.matchAll(/(已核成功|明确拒绝|待核对|未发送)\s*[：:]?\s*(\d+)(?![\d.])/g)){
  if(Object.hasOwn(result,match[1]))throw new Error('AMBIGUOUS_BATCH_PROGRESS');result[match[1]]=Number(match[2]);
 }
 if(Object.keys(result).length!==4)throw new Error('INCOMPLETE_BATCH_PROGRESS');return result;
}
async function focusInside(page:Page,dialog:Locator){
 await dialog.getByRole('button').first().focus();await page.keyboard.press('Tab');
 expect(await dialog.evaluate(element=>element.contains(document.activeElement))).toBe(true);
}

test('LIVE V41: business reads writes and import roundtrip',async({page,browser})=>{
 const c=readBrowserCase(),api=`http://127.0.0.1:${c.api_port}`,web=`http://127.0.0.1:${c.web_port}`,evidence=join(c.directory,'browser-business');
 mkdirSync(evidence,{mode:0o700});
 const rawWriter=subjectWriter(c,'business');let identity:Identity|null=null;
 const pendingProofs:{key:string;operation:string;shop_id:string;resource_id:string|null;version:number;revision:string;context:ReturnType<typeof subjectContext>}[]=[];
 const writer={scope:rawWriter.scope,operation:async(...args:Parameters<typeof rawWriter.operation>)=>{
  const [scope,shop,operation,key,state,request]=args;
  if(state==='ATTEMPT_STARTED'&&request){
   const proof=await page.evaluate(slot=>{
    const raw=sessionStorage.getItem(slot);if(raw===null)throw new Error('NO_PERSISTED_ORIGINAL_PENDING');
    const value=JSON.parse(raw),ctx=value.context;
    return {key:value.request_key,operation:value.operation,shop_id:value.shop_id,resource_id:value.resource_id,version:value.version,revision:value.revision,context:{tenant_id:ctx.tenant_id,organization_id:ctx.organization_id,principal_id:ctx.principal_id,reset_epoch:ctx.reset_epoch,auth_generation:ctx.auth_generation}};
   },'commerceops-v41-pending:'+scope.tenant_id.toLowerCase());
   expect(proof.context).toEqual(scope);expect(proof.key).toBe(key);expect(proof.shop_id).toBe(shop);
   expect(proof.operation).toBe(operation==='preview'?'import_preview':operation);
   expect(proof.revision).toBe(request.body.expected_data_revision);
   if(operation!=='preview'){expect(proof.resource_id).toBe(request.path.split('/')[4]);expect(proof.version).toBe(request.body[operation==='import_confirm'?'expected_job_version':'expected_version']);}
   pendingProofs.push(proof);
  }
  await rawWriter.operation(...args);
 }};
 type OperationFact={operation:string;key:string;resource_id:string;version:number;before_revision:string;after_revision:string|null;effect_count:number|null;shop_id:string;context:ReturnType<typeof subjectContext>;width:number;post_ordinal:number;status:string;readback:Record<string,unknown>};
 const operations:OperationFact[]=[],screenshots:ScreenshotFact[]=[],interactions:Record<string,unknown>[]=[];
 const postRequests=new Map<Request,{ordinal:number;width:number;path:string}>();
 page.on('request',request=>{const url=new URL(request.url());if(url.origin===api&&request.method()==='POST')postRequests.set(request,{ordinal:postRequests.size+1,width:page.viewportSize()?.width??0,path:url.pathname});});
 function sourceOf(value:any){return {context:subjectContext(value.context),shop_id:value.context.shop_id,snapshot:value.data.snapshot??null,job:value.data.job?{import_job_id:value.data.job.import_job_id,version:value.data.job.version,job_digest:value.data.job.job_digest,data_revision:value.data.job.data_revision}:null,file_digest:value.data.file_digest??null};}
 async function capture(state:string,source:Record<string,unknown>,target:Page=page){
  const geometry=await target.evaluate(()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,document_width:document.documentElement.scrollWidth,body_width:document.body.scrollWidth}));
  expect(geometry.document_width).toBeLessThanOrEqual(geometry.width);expect(geometry.body_width).toBeLessThanOrEqual(geometry.width);
  const path=join(evidence,`${state}-${geometry.width}.png`),image=await target.screenshot({path,fullPage:true});
  screenshots.push({state,width:geometry.width,path,sha256:sha(image),pixel_width:image.readUInt32BE(16),pixel_height:image.readUInt32BE(20),viewport:{width:geometry.width,height:geometry.height,dpr:geometry.dpr},route:new URL(target.url()).pathname,source});
 }
 async function views(state:string,source:Record<string,unknown>,controls:()=>Locator[]){
  for(const width of [1440,1280,390]){
   await page.setViewportSize({width,height:900});
   for(const control of controls()){
    await control.scrollIntoViewIfNeeded();await expect(control).toBeVisible();
    const box=await control.boundingBox();if(!box)throw new Error('CONTROL_BOUNDS_UNKNOWN');expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(width+1);
   }
   await capture(state,source);
  }
 }
 function recordCommit(operation:string,raw:Response,result:any,readback:any){
  const post=postRequests.get(raw.request());if(!post)throw new Error('ORIGINAL_POST_NOT_OBSERVED');
  const key=keyOf(raw);if(operations.some(item=>item.key===key))throw new Error('DUPLICATE_OBSERVED_KEY');
  const receipt=result.data.receipt,job=result.data.job;
  const fact:OperationFact={operation,key,resource_id:receipt?.resource_id??job.import_job_id,version:receipt?.resource_version??job.version,before_revision:receipt?.before_revision??job.data_revision,after_revision:receipt?.after_revision??null,effect_count:receipt?.effect_count??null,shop_id:result.context.shop_id,context:subjectContext(result.context),width:post.width,post_ordinal:post.ordinal,status:result.status,readback:{...sourceOf(readback),resource_id:readback.data.product?.product_id??readback.data.order?.order_id??readback.data.job?.import_job_id??null,version:readback.data.product?.version??readback.data.order?.fulfillment_version??readback.data.job?.version??null,tags:readback.data.product?.tags??null,demo_fulfillment:readback.data.order?.demo_fulfillment??null,state:readback.data.state??null,row_count:readback.data.row_count??null}};
  operations.push(fact);return fact;
 }
 const batchFacts:{selected_ids:string[];keys:string[];initial_revision:string|null;current_page:Record<string,unknown>|null;serial_evidence:Record<string,unknown>[];progress:Record<string,number>|null;serial_readback:boolean}={selected_ids:[],keys:[],initial_revision:null,current_page:null,serial_evidence:[],progress:null,serial_readback:false};
 const journal=await installBusinessJournal(page,api,writer,()=>identity);const registrations=await installSessionRegistration(page,api,writer);
 const counts={tag_committed:0,fulfillment_committed:0,preview_committed:0,import_committed:0,downloads:0};
 const facts:{pagination:string;source_modes:string[];downloads:string[];second_tenant:boolean}={pagination:'NOT_OBSERVED',source_modes:[],downloads:[],second_tenant:false};
 await page.setViewportSize({width:390,height:900});await page.goto('/v4/products');
 await expect(page.getByRole('button',{name:'一键体验'})).toBeVisible();await expect(page.locator('tbody tr')).toHaveCount(0);
 await capture('anonymous_empty',{permission:'anonymous',revocation_tested:false,context:null,shop_id:null});
 const createdResponse=waitApi(page,api,'/api/v4/demo/sessions','POST');
 const sessionResponse=page.waitForResponse(response=>response.url()===api+'/api/v4/demo/session'&&response.request().method()==='GET'&&response.ok());
 await page.getByRole('button',{name:'一键体验'}).click();
 const createRaw=await createdResponse;expect(createRaw.ok()).toBe(true);expect((await sessionResponse).ok()).toBe(true);await expect(page.getByText('演示空间已建立。')).toBeVisible();
 const session=await safeSession(page,api),createKey=keyOf(createRaw);
 identity=session.context;expect(session.data.creation_request_key).toBe(createKey);expect(session.data.persona_id).toBe('operator');expect(session.data.shops).toHaveLength(2);
 const first=session.data.shops.find((item:{currency:string})=>item.currency==='TWD'),second=session.data.shops.find((item:{currency:string})=>item.currency==='CNY');
 if(!first||!second||!uuid.test(first.shop_id)||!uuid.test(second.shop_id)||first.shop_id===second.shop_id)throw new Error('OWNED_SHOPS_UNAVAILABLE');
 if(!registrations.some(item=>item.context.tenant_id===identity!.tenant_id&&item.context.organization_id===identity!.organization_id&&item.context.principal_id===identity!.principal_id&&item.context.reset_epoch===identity!.reset_epoch&&item.context.auth_generation===identity!.auth_generation&&item.shops.includes(first.shop_id)&&item.shops.includes(second.shop_id)))throw new Error('SESSION_SCOPE_NOT_REGISTERED');
 await page.getByRole('combobox',{name:'店铺',exact:true}).selectOption(first.shop_id);

 await test.step('dashboard, drilldown and read-only assistant',async()=>{
  const dashboardResponse=waitApi(page,api,'/api/v4/dashboard');
  const dashboard=await readable(page,()=>page.goto('/v4/dashboard').then(()=>{}),dashboardResponse,'BusinessEnvelope_DashboardData_',identity!,first.shop_id);
  expect(dashboard.data.period.timezone).toBe(first.timezone);expect(dashboard.data.model_mode).toBe('not_used');expect(dashboard.data.metrics.length).toBeGreaterThan(0);expect(dashboard.data.insights.length).toBeGreaterThan(0);await expect(page.getByRole('heading',{name:'规则洞察'})).toBeVisible();await expect(page.getByText('非模型生成')).toBeVisible();
  const periodResponse=page.waitForResponse(response=>{const url=new URL(response.url());return url.origin===api&&url.pathname==='/api/v4/dashboard'&&url.searchParams.get('days')==='14'&&response.request().method()==='GET';});
  await page.getByRole('combobox',{name:'时间范围'}).selectOption('14');const period=await validated(await periodResponse,'business','BusinessEnvelope_DashboardData_');assertScope(period.context,identity!,first.shop_id);
  const drillResponse=waitApi(page,api,'/api/v4/dashboard/drilldown');await page.getByRole('button',{name:'查看明细'}).first().click();const drill=await validated(await drillResponse,'business','BusinessEnvelope_Page_Union_Order__Product__RefundReference___');assertScope(drill.context,identity!,first.shop_id);expect(drill.data.snapshot.data_revision).toBe(period.data.snapshot.data_revision);
  const contextResponse=waitApi(page,api,'/api/v4/read-context');await page.getByRole('button',{name:'智能助手'}).click();const assistant=await validated(await contextResponse,'business','BusinessEnvelope_ReadContextData_');assertScope(assistant.context,identity!,first.shop_id);expect(assistant.data.kind).toBe('dashboard');expect(assistant.data.model_mode).toBe('not_used');await expect(page.getByRole('dialog',{name:'智能助手'}).getByText('模型未启用')).toBeVisible();await page.keyboard.press('Escape');
 });

 let productId='',productVersion=0;
 await test.step('product filtering, pagination, export and two tag writes',async()=>{
  const response=waitApi(page,api,'/api/v4/products');const products=await readable(page,()=>page.goto('/v4/products').then(()=>{}),response,'BusinessEnvelope_Page_Product__',identity!,first.shop_id);
  expect(products.data.items.length).toBeGreaterThan(0);const chosen=products.data.items[0];productId=chosen.product_id;productVersion=chosen.version;if(!uuid.test(productId))throw new Error('PRODUCT_ID_INVALID');
  facts.source_modes.push(products.data.snapshot.source.data_mode);
  await views('product_list',sourceOf(products),()=>[page.getByLabel('搜索商品'),page.getByRole('button',{name:'筛选',exact:true}),page.getByRole('checkbox',{name:'选择当前页商品',exact:true})]);
  const selected=products.data.items.slice(0,2);expect(selected).toHaveLength(2);expect(new Set(selected.map((item:any)=>item.product_id)).size).toBe(selected.length);
  const header=page.getByRole('checkbox',{name:'选择当前页商品',exact:true});
  await header.check();await expect(page.locator('tbody').getByRole('checkbox',{checked:true})).toHaveCount(products.data.items.length);await header.uncheck();await expect(page.locator('tbody').getByRole('checkbox',{checked:true})).toHaveCount(0);
  async function selectCurrentTwo(){
   for(const item of selected){const row=page.locator('tbody tr').filter({has:page.locator(`a[href="/v4/products/${item.product_id}"]`)});await row.getByRole('checkbox',{name:'选择商品 '+item.title,exact:true}).check();}
   await expect(page.locator('tbody').getByRole('checkbox',{checked:true})).toHaveCount(selected.length);
  }
  const batchButton=page.getByRole('button',{name:'批量设置标签',exact:true}),batchDialog=page.getByRole('dialog',{name:'批量设置标签',exact:true});
  await selectCurrentTwo();await batchButton.click();await expect(batchDialog).toBeVisible();
  await batchDialog.getByLabel('标签（逗号分隔，最多 8 项）').fill('v41-live-batch');
  await focusInside(page,batchDialog);const beforeCancel=postRequests.size;await page.keyboard.press('Escape');await expect(batchDialog).not.toBeVisible();expect(postRequests.size).toBe(beforeCancel);await expect(header).toBeFocused();
  await expect(page.locator('tbody').getByRole('checkbox',{checked:true})).toHaveCount(0);await selectCurrentTwo();await batchButton.click();
  await batchDialog.getByLabel('标签（逗号分隔，最多 8 项）').fill('v41-live-batch');
  await capture('batch_confirm',sourceOf(products));
  const batchPosts=selected.map((item:any)=>waitApi(page,api,pathFor('product_tags',item.product_id),'POST'));
  const batchReads=selected.map((item:any)=>page.waitForResponse(async response=>{
   const url=new URL(response.url());if(url.origin!==api||url.pathname!==`/api/v4/products/${item.product_id}`||response.request().method()!=='GET'||!response.ok())return false;
   try{const data=(await response.json()).data;return data.product.version===item.version+1&&JSON.stringify(data.product.tags)===JSON.stringify(['v41-live-batch']);}catch{return false;}
  }));
  await batchDialog.getByRole('button',{name:'确认逐项替换',exact:true}).click();
  const raws=await Promise.all(batchPosts),reads=await Promise.all(batchReads);
  const pairs=raws.map((raw:Response,index:number)=>({raw,read:reads[index],item:selected[index],post:postRequests.get(raw.request())!})).sort((a:any,b:any)=>a.post.ordinal-b.post.ordinal);
  let batchRevision=products.data.snapshot.data_revision;
  for(let index=0;index<pairs.length;index++){
   const {raw,read,item}=pairs[index];expect(await raw.finished()).toBeNull();expect(await read.finished()).toBeNull();
   const posted=await validated(raw,'business','BusinessEnvelope_ActionResult_'),after=await validated(read,'business','BusinessEnvelope_ProductDetail_');
   assertScope(posted.context,identity!,first.shop_id);assertScope(after.context,identity!,first.shop_id);expect(posted.status).toBe('COMMITTED');
   const body=raw.request().postDataJSON();expect(body.expected_version).toBe(item.version);expect(body.expected_data_revision).toBe(batchRevision);expect(body.tags).toEqual(['v41-live-batch']);
   expect(posted.data.receipt.resource_id).toBe(item.product_id);expect(posted.data.receipt.request_key).toBe(keyOf(raw));expect(posted.data.receipt.resource_version).toBe(item.version+1);expect(posted.data.receipt.before_revision).toBe(batchRevision);
   expect(after.data.product.product_id).toBe(item.product_id);expect(after.data.product.version).toBe(item.version+1);expect(after.data.product.tags).toEqual(['v41-live-batch']);expect(after.data.snapshot.data_revision).toBe(posted.data.receipt.after_revision);
   if(index>0){const prior=pairs[index-1].read.request().timing(),next=raw.request().timing();expect(prior.responseEnd).toBeGreaterThanOrEqual(0);expect(next.startTime).toBeGreaterThanOrEqual(prior.startTime+prior.responseEnd);batchFacts.serial_evidence.push({previous_key:keyOf(pairs[index-1].raw),next_key:keyOf(raw),read_start:prior.startTime,read_end_offset:prior.responseEnd,next_post_start:next.startTime});}
   await journal.flush();await writer.operation(subjectContext(identity!),first.shop_id,'product_tags',keyOf(raw),'COMMITTED_READBACK');
   const fact=recordCommit('product_tags',raw,posted,after);batchFacts.keys.push(fact.key);counts.tag_committed++;batchRevision=posted.data.receipt.after_revision;
   if(item.product_id===productId)productVersion=after.data.product.version;
  }
  batchFacts.selected_ids=selected.map((item:any)=>item.product_id);batchFacts.initial_revision=products.data.snapshot.data_revision;batchFacts.current_page={items:products.data.items.map((item:any)=>({product_id:item.product_id,version:item.version})),query:new URL((await response).url()).search,source:sourceOf(products)};batchFacts.serial_readback=true;
  const progress=page.getByRole('status',{name:'批量标签进度',exact:true});await expect(progress).toBeVisible();batchFacts.progress=progressCounts(await progress.innerText());expect(batchFacts.progress).toEqual({'已核成功':selected.length,'明确拒绝':0,'待核对':0,'未发送':0});
  expect(new Set(batchFacts.keys).size).toBe(selected.length);expect(postRequests.size-beforeCancel).toBe(selected.length);
  const pendingAfterBatch=await page.evaluate(slot=>sessionStorage.getItem(slot),'commerceops-v41-pending:'+identity!.tenant_id.toLowerCase());expect(pendingAfterBatch).toBeNull();
  // The original single-item edits follow, so their isolation sentinel is not overwritten by this batch.
  const afterBatchList=waitApi(page,api,'/api/v4/products');await page.goto('/v4/products');const afterBatch=await validated(await afterBatchList,'business','BusinessEnvelope_Page_Product__');assertScope(afterBatch.context,identity!,first.shop_id);expect(afterBatch.data.snapshot.data_revision).toBe(batchRevision);for(const item of selected)await expect(page.locator('tbody tr').filter({has:page.locator(`a[href="/v4/products/${item.product_id}"]`)}).getByText('v41-live-batch',{exact:true})).toBeVisible();await capture('batch_readback',sourceOf(afterBatch));

  const sku=chosen.skus[0]?.label;if(typeof sku!=='string'||!sku)throw new Error('PRODUCT_SKU_UNAVAILABLE');
  await page.getByLabel('搜索商品').fill(sku);const filteredResponse=waitProducts(page,api,first.shop_id,sku,'');await page.getByRole('button',{name:'筛选',exact:true}).click();
  const filtered=await validated(await filteredResponse,'business','BusinessEnvelope_Page_Product__');assertScope(filtered.context,identity!,first.shop_id);
  expect(filtered.data.total).toBe(1);expect(filtered.data.next_cursor).toBeNull();expect(filtered.data.items.map((item:{product_id:string})=>item.product_id)).toEqual([productId]);
  await expect(page.locator(`tbody a[href="/v4/products/${productId}"]`)).toBeVisible();
  const download=page.waitForEvent('download'),exportResponse=waitApi(page,api,'/api/v4/products/export');await page.getByRole('button',{name:'导出 CSV'}).click();const exported=await validated(await exportResponse,'business','BusinessEnvelope_ExportData_');assertScope(exported.context,identity!,first.shop_id);expect(exported.data.snapshot.data_revision).toBe(filtered.data.snapshot.data_revision);expect(exported.data.snapshot.snapshot_id).toBe(filtered.data.snapshot.snapshot_id);const file=await download;expect(file.suggestedFilename()).toBe('products.csv');const stream=await file.createReadStream(),chunks:Buffer[]=[];for await(const chunk of stream)chunks.push(Buffer.from(chunk));expect(Buffer.concat(chunks).equals(Buffer.from(exported.data.csv_text,'utf8'))).toBe(true);facts.downloads.push(sha(exported.data.csv_text));counts.downloads++;
  const detailResponse=waitApi(page,api,`/api/v4/products/${productId}`);await page.locator(`a[href="/v4/products/${productId}"]`).first().click();const initial=await validated(await detailResponse,'business','BusinessEnvelope_ProductDetail_');assertScope(initial.context,identity!,first.shop_id);expect(initial.data.product.product_id).toBe(productId);expect(initial.data.product.version).toBe(productVersion);
  const drawer=page.getByRole('dialog',{name:'商品详情'});
  await views('product_detail',sourceOf(initial),()=>[drawer.getByRole('button',{name:'编辑标签'}),drawer.getByRole('link',{name:'关闭并返回列表'})]);
  await focusInside(page,drawer);const beforeProductEsc=postRequests.size,backProducts=waitApi(page,api,'/api/v4/products');await page.keyboard.press('Escape');
  const backProductPage=await validated(await backProducts,'business','BusinessEnvelope_Page_Product__');assertScope(backProductPage.context,identity!,first.shop_id);await expect(drawer).not.toBeVisible();expect(postRequests.size).toBe(beforeProductEsc);await expect(page).toHaveURL(web+'/v4/products');
  interactions.push({state:'product_detail',width:390,tab_inside:true,escape:'RETURNED_LIST_NO_POST'});
  const reopened=waitApi(page,api,`/api/v4/products/${productId}`);await page.locator(`tbody a[href="/v4/products/${productId}"]`).click();const reopenedProduct=await validated(await reopened,'business','BusinessEnvelope_ProductDetail_');assertScope(reopenedProduct.context,identity!,first.shop_id);expect(reopenedProduct.data.product.version).toBe(productVersion);
  for(const tag of ['v41-live-a','v41-live-b']){
   await page.setViewportSize({width:tag==='v41-live-a'?390:1440,height:900});
   await drawer.getByRole('button',{name:'编辑标签'}).click();await drawer.getByLabel('标签（逗号分隔，最多 8 项）').fill(tag);
   if(tag==='v41-live-a'){
    await views('tag_edit',sourceOf(reopenedProduct),()=>[drawer.getByLabel('标签（逗号分隔，最多 8 项）'),drawer.getByRole('button',{name:'确认保存',exact:true})]);
    await drawer.getByLabel('标签（逗号分隔，最多 8 项）').focus();await page.keyboard.press('Tab');expect(await drawer.evaluate(element=>element.contains(document.activeElement))).toBe(true);
    interactions.push({state:'tag_edit',width:390,tab_inside:true,save:'EXPLICIT_UI_CONFIRMATION'});
   }
   const postResponse=waitApi(page,api,pathFor('product_tags',productId),'POST');const readback=page.waitForResponse(async response=>{const url=new URL(response.url());if(url.origin!==api||url.pathname!==`/api/v4/products/${productId}`||response.request().method()!=='GET'||!response.ok())return false;try{return (await response.json()).data.product.version===productVersion+1;}catch{return false;}});
   await drawer.getByRole('button',{name:'确认保存'}).click();const raw=await postResponse,key=keyOf(raw),posted=await validated(raw,'business','BusinessEnvelope_ActionResult_');assertScope(posted.context,identity!,first.shop_id);expect(posted.data.receipt.request_key).toBe(key);expect(posted.data.receipt.resource_id).toBe(productId);expect(posted.data.receipt.resource_version).toBe(productVersion+1);
   const reread=await validated(await readback,'business','BusinessEnvelope_ProductDetail_');assertScope(reread.context,identity!,first.shop_id);expect(reread.data.product.version).toBe(productVersion+1);expect(reread.data.product.tags).toEqual([tag]);expect(reread.data.snapshot.data_revision).toBe(posted.data.receipt.after_revision);await journal.flush();await writer.operation(
    subjectContext(identity!),
    first.shop_id,
    'product_tags',
    key,
    'COMMITTED_READBACK',
   );recordCommit('product_tags',raw,posted,reread);if(tag==='v41-live-a'){await expect(drawer.getByText('标签：'+reread.data.product.tags.join('、'),{exact:true})).toBeVisible();await expect(drawer.getByRole('button',{name:'编辑标签'})).toBeEnabled();await capture('tag_readback',sourceOf(reread));}productVersion++;counts.tag_committed++;await expect(drawer.getByRole('button',{name:'编辑标签'})).toBeEnabled();
  }
 });

 await test.step('known-payment fulfillment and unknown-payment refusal',async()=>{
  const listResponse=waitApi(page,api,'/api/v4/orders');const orders=await readable(page,()=>page.goto('/v4/orders').then(()=>{}),listResponse,'BusinessEnvelope_Page_Order__',identity!,first.shop_id);
  await views('order_list',sourceOf(orders),()=>[page.getByLabel('搜索订单'),page.getByRole('button',{name:'筛选',exact:true})]);
  const known=orders.data.items.find((item:{payment_status:string;demo_fulfillment:string})=>item.payment_status==='payment_recorded'&&item.demo_fulfillment==='demo_unfulfilled');const unknown=orders.data.items.find((item:{payment_status:string})=>item.payment_status==='payment_timestamp_unknown');
  if(!known||!unknown)throw new Error('OWNED_ORDER_SAMPLES_UNAVAILABLE');
  const unknownResponse=waitApi(page,api,`/api/v4/orders/${unknown.order_id}`);await page.locator(`a[href="/v4/orders/${unknown.order_id}"]`).first().click();const unknownDetail=await validated(await unknownResponse,'business','BusinessEnvelope_OrderDetail_');assertScope(unknownDetail.context,identity!,first.shop_id);expect(unknownDetail.data.order.payment_status).toBe('payment_timestamp_unknown');await expect(page.getByRole('dialog',{name:'订单详情'}).getByRole('button',{name:'标记演示已履约'})).toBeDisabled();
  const knownResponse=waitApi(page,api,`/api/v4/orders/${known.order_id}`);await page.goto(`/v4/orders/${known.order_id}`);const knownDetail=await validated(await knownResponse,'business','BusinessEnvelope_OrderDetail_');assertScope(knownDetail.context,identity!,first.shop_id);const drawer=page.getByRole('dialog',{name:'订单详情'});
  await views('order_detail',sourceOf(knownDetail),()=>[drawer.getByRole('button',{name:'标记演示已履约'}),drawer.getByRole('link',{name:'关闭并返回列表'})]);
  await drawer.getByRole('button',{name:'标记演示已履约'}).click();
  await views('fulfillment_confirm',sourceOf(knownDetail),()=>[drawer.getByRole('button',{name:'确认演示履约',exact:true}),drawer.getByRole('button',{name:'取消',exact:true})]);
  await focusInside(page,drawer);const beforeOrderEsc=postRequests.size,backOrders=waitApi(page,api,'/api/v4/orders');await page.keyboard.press('Escape');const orderReturn=await validated(await backOrders,'business','BusinessEnvelope_Page_Order__');assertScope(orderReturn.context,identity!,first.shop_id);await expect(drawer).not.toBeVisible();expect(postRequests.size).toBe(beforeOrderEsc);
  interactions.push({state:'fulfillment_confirm',width:390,tab_inside:true,escape:'RETURNED_LIST_NO_POST'});
  const reopenedOrder=waitApi(page,api,`/api/v4/orders/${known.order_id}`);await page.locator(`tbody a[href="/v4/orders/${known.order_id}"]`).click();const sameOrder=await validated(await reopenedOrder,'business','BusinessEnvelope_OrderDetail_');assertScope(sameOrder.context,identity!,first.shop_id);expect(sameOrder.data.order.fulfillment_version).toBe(knownDetail.data.order.fulfillment_version);expect(sameOrder.data.order.demo_fulfillment).toBe('demo_unfulfilled');await drawer.getByRole('button',{name:'标记演示已履约'}).click();
  const action=waitApi(page,api,pathFor('order_fulfillment',known.order_id),'POST');const readback=page.waitForResponse(async response=>{const url=new URL(response.url());if(url.origin!==api||url.pathname!==`/api/v4/orders/${known.order_id}`||response.request().method()!=='GET'||!response.ok())return false;try{return (await response.json()).data.order.demo_fulfillment==='demo_fulfilled';}catch{return false;}});
  await drawer.getByRole('button',{name:'确认演示履约'}).click();const raw=await action,key=keyOf(raw),posted=await validated(raw,'business','BusinessEnvelope_ActionResult_');assertScope(posted.context,identity!,first.shop_id);expect(posted.data.receipt.request_key).toBe(key);expect(posted.data.receipt.resource_id).toBe(known.order_id);expect(posted.data.receipt.resource_version).toBe(knownDetail.data.order.fulfillment_version+1);
  const after=await validated(await readback,'business','BusinessEnvelope_OrderDetail_');assertScope(after.context,identity!,first.shop_id);expect(after.data.order.fulfillment_version).toBe(posted.data.receipt.resource_version);expect(after.data.snapshot.data_revision).toBe(posted.data.receipt.after_revision);await journal.flush();await writer.operation(
    subjectContext(identity!),
    first.shop_id,
    'order_fulfillment',
    key,
    'COMMITTED_READBACK',
   );recordCommit('order_fulfillment',raw,posted,after);await expect(drawer.getByText('履约：演示已履约',{exact:true})).toBeVisible();await capture('fulfillment_readback',sourceOf(after));counts.fulfillment_committed++;
 });

 await test.step('CSV and XLSX preview, mapping, confirmation and source readback',async()=>{
  const initialProducts=waitApi(page,api,'/api/v4/products');const initial=await readable(page,()=>page.goto('/v4/products/import').then(()=>{}),initialProducts,'BusinessEnvelope_Page_Product__',identity!,first.shop_id);
  let revision=initial.data.snapshot.data_revision;
  for(const format of ['csv','xlsx'] as const){
   await page.setViewportSize({width:390,height:900});
   const input=page.getByLabel('文件');
   if(format==='csv')await input.setInputFiles({name:'owned-products.csv',mimeType:'text/csv',buffer:Buffer.from('sku,title,price,currency\n'+Array.from({length:22},(_,i)=>`V41LIVE-CSV-${String(i).padStart(2,'0')},Owned CSV product ${i},123,TWD\n`).join(''))});
   else await input.setInputFiles(fileURLToPath(new URL('../v41-tests/fixtures/sample.xlsx',import.meta.url)));
   const firstPreview=waitApi(page,api,'/api/v4/imports/previews','POST');const firstLookup=page.waitForResponse(response=>{const url=new URL(response.url());return url.origin===api&&url.pathname.startsWith('/api/v4/imports/preview-requests/')&&response.request().method()==='GET';});const firstJob=page.waitForResponse(response=>{const url=new URL(response.url());return url.origin===api&&/^\/api\/v4\/imports\/[0-9a-f-]{36}$/i.test(url.pathname)&&response.request().method()==='GET';});
   await page.getByRole('button',{name:'上传并预览'}).click();const firstRaw=await firstPreview,firstKey=keyOf(firstRaw),discovery=await validated(firstRaw,'business','BusinessEnvelope_ImportPreviewData_');assertScope(discovery.context,identity!,first.shop_id);expect(discovery.data.job.data_revision).toBe(revision);expect(discovery.data.state).toBe('DISCOVERED');
   const firstLookupRaw=await firstLookup;expect(new URL(firstLookupRaw.url()).pathname.endsWith(firstKey)).toBe(true);const firstFound=await validated(firstLookupRaw,'business','BusinessEnvelope_PreviewLookup_'),firstRead=await validated(await firstJob,'business','BusinessEnvelope_ImportPreviewData_');assertScope(firstFound.context,identity!,first.shop_id);assertScope(firstRead.context,identity!,first.shop_id);expect(firstFound.data.request_key).toBe(firstKey);expect(firstFound.data.status).toBe('COMMITTED');expect(firstFound.data.job.import_job_id).toBe(discovery.data.job.import_job_id);expect(firstRead.data.job.job_digest).toBe(discovery.data.job.job_digest);await journal.flush();await writer.operation(
    subjectContext(identity!),
    first.shop_id,
    'preview',
    firstKey,
    'COMMITTED_READBACK',
   );recordCommit('preview',firstRaw,discovery,firstRead);counts.preview_committed++;
   await expect(page.getByText(/状态 DISCOVERED/)).toBeVisible();
   await views(format+'_mapping',sourceOf(discovery),()=>['SKU','商品名称','价格','币种'].map(label=>page.getByRole('combobox',{name:label,exact:true})));
   const beforeMappingEsc=postRequests.size;await page.getByRole('combobox',{name:'SKU',exact:true}).focus();await page.keyboard.press('Tab');await page.keyboard.press('Escape');expect(postRequests.size).toBe(beforeMappingEsc);
   interactions.push({state:format+'_mapping',width:390,tab_controls:true,escape:'NON_MODAL_NO_POST'});
   for(const [label,column] of [['SKU','sku'],['商品名称','title'],['价格','price'],['币种','currency']]){const field=page.getByRole('combobox',{name:label,exact:true});await field.selectOption(column);await expect(field).toHaveValue(column);}
   const mappedResponse=waitApi(page,api,'/api/v4/imports/previews','POST');const mappedLookup=page.waitForResponse(response=>{const url=new URL(response.url());return url.origin===api&&url.pathname.startsWith('/api/v4/imports/preview-requests/')&&response.request().method()==='GET';});const mappedJob=page.waitForResponse(response=>{const url=new URL(response.url());return url.origin===api&&/^\/api\/v4\/imports\/[0-9a-f-]{36}$/i.test(url.pathname)&&response.request().method()==='GET';});
   await page.getByRole('button',{name:'确认映射并重新预览'}).click();const mappedRaw=await mappedResponse,mappedKey=keyOf(mappedRaw),mapped=await validated(mappedRaw,'business','BusinessEnvelope_ImportPreviewData_');assertScope(mapped.context,identity!,first.shop_id);expect(mapped.data.job.parent_job_id).toBe(discovery.data.job.import_job_id);expect(mapped.data.job.data_revision).toBe(revision);expect(mapped.data.file_digest).toBe(discovery.data.file_digest);expect(mapped.data.state).toBe('READY');expect(mapped.data.issue_count).toBe(0);expect(mapped.data.confirmable).toBe(true);
   const mappedLookupRaw=await mappedLookup;expect(new URL(mappedLookupRaw.url()).pathname.endsWith(mappedKey)).toBe(true);const mappedFound=await validated(mappedLookupRaw,'business','BusinessEnvelope_PreviewLookup_'),mappedRead=await validated(await mappedJob,'business','BusinessEnvelope_ImportPreviewData_');assertScope(mappedFound.context,identity!,first.shop_id);assertScope(mappedRead.context,identity!,first.shop_id);expect(mappedFound.data.request_key).toBe(mappedKey);expect(mappedFound.data.status).toBe('COMMITTED');expect(mappedFound.data.job.import_job_id).toBe(mapped.data.job.import_job_id);expect(mappedRead.data.job.job_digest).toBe(mapped.data.job.job_digest);await journal.flush();await writer.operation(
    subjectContext(identity!),
    first.shop_id,
    'preview',
    mappedKey,
    'COMMITTED_READBACK',
   );recordCommit('preview',mappedRaw,mapped,mappedRead);counts.preview_committed++;
   await expect(page.getByText(/状态 READY/)).toBeVisible();
   await page.getByRole('button',{name:'准备确认导入'}).click();const jobId=mapped.data.job.import_job_id;
   const confirmResponse=waitApi(page,api,`/api/v4/imports/${jobId}/confirm`,'POST');const jobResponse=page.waitForResponse(async response=>{const url=new URL(response.url());if(url.origin!==api||url.pathname!==`/api/v4/imports/${jobId}`||response.request().method()!=='GET'||!response.ok())return false;try{return (await response.json()).data.state==='COMMITTED';}catch{return false;}});
   const datasetResponse=page.waitForResponse(async response=>{const url=new URL(response.url());if(url.origin!==api||url.pathname!=='/api/v4/products'||response.request().method()!=='GET'||!response.ok())return false;try{return (await response.json()).data.snapshot.data_revision!==revision;}catch{return false;}});
   await page.getByRole('button',{name:'确认导入',exact:true}).click();const confirmRaw=await confirmResponse,key=keyOf(confirmRaw),confirmed=await validated(confirmRaw,'business','BusinessEnvelope_ActionResult_');assertScope(confirmed.context,identity!,first.shop_id);expect(confirmed.data.receipt.request_key).toBe(key);expect(confirmed.data.receipt.resource_id).toBe(jobId);expect(confirmed.data.receipt.resource_version).toBe(mapped.data.job.version);expect(confirmed.data.receipt.before_revision).toBe(revision);
   const committed=await validated(await jobResponse,'business','BusinessEnvelope_ImportPreviewData_');assertScope(committed.context,identity!,first.shop_id);expect(committed.data.job.import_job_id).toBe(jobId);expect(committed.data.job.job_digest).toBe(mapped.data.job.job_digest);expect(committed.data.state).toBe('COMMITTED');
   const after=await validated(await datasetResponse,'business','BusinessEnvelope_Page_Product__');assertScope(after.context,identity!,first.shop_id);expect(after.data.snapshot.data_revision).toBe(confirmed.data.receipt.after_revision);expect(after.data.snapshot.source.uploads.some((item:{import_job_id:string;file_digest:string})=>item.import_job_id===jobId&&item.file_digest===mapped.data.file_digest)).toBe(true);revision=after.data.snapshot.data_revision;await journal.flush();await writer.operation(
    subjectContext(identity!),
    first.shop_id,
    'import_confirm',
    key,
    'COMMITTED_READBACK',
   );const importFact=recordCommit('import_confirm',confirmRaw,confirmed,committed);importFact.readback.dataset=sourceOf(after);counts.import_committed++;facts.source_modes.push(after.data.snapshot.source.data_mode);
   await expect(page.getByText('已核对导入回执、作业状态和数据来源。')).toBeVisible();
   const sku=format==='csv'?'V41LIVE-CSV-00':'SKU-1',readProducts=waitApi(page,api,'/api/v4/products');await page.getByRole('link',{name:'查看商品列表'}).click();const productPage=await validated(await readProducts,'business','BusinessEnvelope_Page_Product__');assertScope(productPage.context,identity!,first.shop_id);
   if(format==='csv'){
    await page.getByLabel('搜索商品').fill('');const unfiltered=waitProducts(page,api,first.shop_id,'','');await page.getByRole('button',{name:'筛选',exact:true}).click();
    const firstPage=await validated(await unfiltered,'business','BusinessEnvelope_Page_Product__');assertScope(firstPage.context,identity!,first.shop_id);expect(firstPage.data.snapshot.data_revision).toBe(revision);
    const firstIds=firstPage.data.items.map((item:{product_id:string})=>item.product_id);expect(firstIds).toHaveLength(20);expect(firstPage.data.total).toBeGreaterThan(20);expect(firstPage.data.total).toBeLessThanOrEqual(40);
    const cursor=firstPage.data.next_cursor;if(!cursor)throw new Error('PAGINATION_CURSOR_UNAVAILABLE');
    const next=waitProducts(page,api,first.shop_id,'',cursor);await page.getByRole('button',{name:'下一页'}).click();
    const nextPage=await validated(await next,'business','BusinessEnvelope_Page_Product__');assertScope(nextPage.context,identity!,first.shop_id);
    expect(nextPage.data.snapshot.snapshot_id).toBe(firstPage.data.snapshot.snapshot_id);expect(nextPage.data.snapshot.data_revision).toBe(revision);expect(nextPage.data.total).toBe(firstPage.data.total);expect(nextPage.data.next_cursor).toBeNull();
    const nextIds=nextPage.data.items.map((item:{product_id:string})=>item.product_id);expect(nextIds.length).toBeGreaterThan(0);expect(nextIds.some((id:string)=>firstIds.includes(id))).toBe(false);expect(new Set([...firstIds,...nextIds]).size).toBe(firstPage.data.total);
    await expect(page.locator(`tbody a[href="/v4/products/${nextIds[0]}"]`)).toBeVisible();await expect(page.locator(`tbody a[href="/v4/products/${firstIds[0]}"]`)).toHaveCount(0);
    const previous=waitProducts(page,api,first.shop_id,'','');await page.getByRole('button',{name:'上一页'}).click();
    const previousPage=await validated(await previous,'business','BusinessEnvelope_Page_Product__');assertScope(previousPage.context,identity!,first.shop_id);
    expect(previousPage.data.snapshot.snapshot_id).toBe(firstPage.data.snapshot.snapshot_id);expect(previousPage.data.snapshot.data_revision).toBe(revision);expect(previousPage.data.total).toBe(firstPage.data.total);expect(previousPage.data.items.map((item:{product_id:string})=>item.product_id)).toEqual(firstIds);expect(previousPage.data.next_cursor).toBe(cursor);
    await expect(page.locator(`tbody a[href="/v4/products/${firstIds[0]}"]`)).toBeVisible();await expect(page.locator(`tbody a[href="/v4/products/${nextIds[0]}"]`)).toHaveCount(0);facts.pagination='OBSERVED';
   }
   await page.getByLabel('搜索商品').fill(sku);const search=waitProducts(page,api,first.shop_id,sku,'');await page.getByRole('button',{name:'筛选',exact:true}).click();const found=await validated(await search,'business','BusinessEnvelope_Page_Product__');assertScope(found.context,identity!,first.shop_id);expect(found.data.total).toBe(1);expect(found.data.next_cursor).toBeNull();expect(found.data.items).toHaveLength(1);const imported=found.data.items.find((item:{source:{import_job_id:string};skus:{label:string}[]})=>item.source.import_job_id===jobId&&item.skus.some(s=>s.label===sku));if(!imported)throw new Error('IMPORTED_SKU_NOT_FOUND');expect(imported.source.data_mode).toBe('demo_upload');expect(imported.source.file_digest).toBe(mapped.data.file_digest);
   await expect(page.locator(`tbody a[href="/v4/products/${imported.product_id}"]`)).toBeVisible();await capture(format+'_readback',sourceOf(found));
   if(format==='csv'){
    const returnProducts=waitApi(page,api,'/api/v4/products');await page.goto('/v4/products/import');const current=await validated(await returnProducts,'business','BusinessEnvelope_Page_Product__');assertScope(current.context,identity!,first.shop_id);revision=current.data.snapshot.data_revision;await page.getByRole('button',{name:'放弃本地预览引用'}).click();await page.getByRole('button',{name:'确认放弃本地引用'}).click();
   }
  }
 });

 await test.step('shop and visitor isolation',async()=>{
  const otherList=waitApi(page,api,'/api/v4/products');await page.getByRole('combobox',{name:'店铺',exact:true}).selectOption(second.shop_id);const other=await validated(await otherList,'business','BusinessEnvelope_Page_Product__');assertScope(other.context,identity!,second.shop_id);await expect(page.getByText('v41-live-b',{exact:false})).toHaveCount(0);
  const secondContext=await browser.newContext({baseURL:web});
  try{
   const visitor=await secondContext.newPage(),visitorRegistrations=await installSessionRegistration(visitor,api,writer);await visitor.setViewportSize({width:390,height:900});await visitor.goto('/v4/products');await expect(visitor.getByRole('button',{name:'一键体验'})).toBeVisible();await expect(visitor.getByText('v41-live-b',{exact:false})).toHaveCount(0);
   await expect(visitor.locator('tbody tr')).toHaveCount(0);await capture('second_visitor_empty',{permission:'anonymous',revocation_tested:false,context:null,shop_id:null},visitor);
   const created=waitApi(visitor,api,'/api/v4/demo/sessions','POST'),sessionRead=visitor.waitForResponse(response=>response.url()===api+'/api/v4/demo/session'&&response.request().method()==='GET'&&response.ok());await visitor.getByRole('button',{name:'一键体验'}).click();const create=await created;expect(create.ok()).toBe(true);expect((await sessionRead).ok()).toBe(true);await expect(visitor.getByText('演示空间已建立。')).toBeVisible();const otherSession=await safeSession(visitor,api);expect(otherSession.context.tenant_id).not.toBe(identity!.tenant_id);expect(otherSession.data.creation_request_key).toBe(keyOf(create));
   const shop=otherSession.data.shops.find((item:{currency:string})=>item.currency==='TWD');if(!shop)throw new Error('SECOND_VISITOR_SHOP_MISSING');if(!visitorRegistrations.some(item=>item.context.tenant_id===otherSession.context.tenant_id&&item.context.organization_id===otherSession.context.organization_id&&item.context.principal_id===otherSession.context.principal_id&&item.context.reset_epoch===otherSession.context.reset_epoch&&item.context.auth_generation===otherSession.context.auth_generation&&item.shops.includes(shop.shop_id)))throw new Error('SESSION_SCOPE_NOT_REGISTERED');
   const list=waitApi(visitor,api,'/api/v4/products');await visitor.getByRole('combobox',{name:'店铺',exact:true}).selectOption(shop.shop_id);const result=await validated(await list,'business','BusinessEnvelope_Page_Product__');assertScope(result.context,otherSession.context,shop.shop_id);expect(result.data.items.some((item:{tags:string[]})=>item.tags.includes('v41-live-b'))).toBe(false);await expect(visitor.getByText('v41-live-b',{exact:false})).toHaveCount(0);facts.second_tenant=true;
  }finally{await secondContext.close();}
 });
 await journal.flush();if(journal.pending())throw new Error('BUSINESS_REQUEST_UNSETTLED');
 const businessPaths=[...postRequests.values()].filter(item=>/^\/api\/v4\/(?:products\/[^/]+\/tags|orders\/[^/]+\/fulfillment|imports\/previews|imports\/[^/]+\/confirm)$/.test(item.path));
 expect(operations).toHaveLength(businessPaths.length);expect(pendingProofs).toHaveLength(operations.length);expect(new Set(operations.map(item=>item.key)).size).toBe(operations.length);
 const derived={tag_committed:operations.filter(item=>item.operation==='product_tags').length,fulfillment_committed:operations.filter(item=>item.operation==='order_fulfillment').length,preview_committed:operations.filter(item=>item.operation==='preview').length,import_committed:operations.filter(item=>item.operation==='import_confirm').length,downloads:facts.downloads.length};expect(counts).toEqual(derived);
 const mobileOperations=operations.filter(item=>item.width===390).map(item=>item.key);expect(operations.some(item=>item.width===390&&item.operation==='product_tags')).toBe(true);expect(operations.some(item=>item.width===390&&item.operation==='order_fulfillment')).toBe(true);
 const mobile_business={schema:'v41-business-mobile-v1',screenshots,operations,mobile_keys:mobileOperations,pending_proofs:pendingProofs,batch:batchFacts,interactions,permission_evidence:'ANONYMOUS_ONLY_NOT_403_REVOKED'};
 writeFileSync(join(evidence,'business.safe.json'),JSON.stringify({source_sha:c.source_sha,source_tree:c.source_tree,scope:'LIVE_BUSINESS_ONLY',native200:'NOT_RUN_IN_THIS_SPEC',counts,facts,mobile_business},null,2),{mode:0o600,flag:'wx'});
});
