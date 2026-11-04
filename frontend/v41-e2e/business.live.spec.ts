import {test,expect,type Page,type Response} from '@playwright/test';
import {createHash} from 'node:crypto';
import {mkdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {readBrowserCase,subjectWriter} from './browser-subjects';
import {assertScope,installBusinessJournal,installSessionRegistration,subjectContext,validated,waitApi,safeSession,type Identity} from './live-business.fixture';

const sha=(value:string)=>createHash('sha256').update(value).digest('hex');
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function keyOf(response:Response){const key=response.request().postDataJSON()?.request_key;if(typeof key!=='string'||!uuid.test(key))throw new Error('INVALID_ORIGINAL_KEY');return key;}
function pathFor(kind:'product_tags'|'order_fulfillment',id:string){return `/api/v4/${kind==='product_tags'?'products':'orders'}/${id}/${kind==='product_tags'?'tags':'fulfillment'}`;}
async function readable(page:Page,method:()=>Promise<void>,read:Promise<Response>,schema:string,identity:Identity,shop:string){
 await method();const result=await validated(await read,'business',schema);assertScope(result.context,identity,shop);return result;
}

test('LIVE V41: business reads writes and import roundtrip',async({page,browser})=>{
 const c=readBrowserCase(),api=`http://127.0.0.1:${c.api_port}`,web=`http://127.0.0.1:${c.web_port}`,evidence=join(c.directory,'browser-business');
 mkdirSync(evidence,{mode:0o700});
 const writer=subjectWriter(c,'business');let identity:Identity|null=null;
 const journal=await installBusinessJournal(page,api,writer,()=>identity);const registrations=await installSessionRegistration(page,api,writer);
 const counts={tag_committed:0,fulfillment_committed:0,preview_committed:0,import_committed:0,downloads:0};
 const facts:{pagination:string;source_modes:string[];downloads:string[];second_tenant:boolean}={pagination:'NOT_OBSERVED',source_modes:[],downloads:[],second_tenant:false};
 await page.setViewportSize({width:1440,height:900});await page.goto('/v4');
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
  expect(dashboard.data.period.timezone).toBe(first.timezone);expect(dashboard.data.model_mode).toBe('not_used');expect(dashboard.data.metrics.length).toBeGreaterThan(0);expect(dashboard.data.insights.length).toBeGreaterThan(0);
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
  if(products.data.next_cursor){const next=waitApi(page,api,'/api/v4/products');await page.getByRole('button',{name:'下一页'}).click();const nextPage=await validated(await next,'business','BusinessEnvelope_Page_Product__');assertScope(nextPage.context,identity!,first.shop_id);expect(nextPage.data.snapshot.snapshot_id).toBe(products.data.snapshot.snapshot_id);await page.getByRole('button',{name:'上一页'}).click();facts.pagination='OBSERVED';}else facts.pagination='NOT_AVAILABLE_IN_CURRENT_PAGE';
  await page.getByLabel('搜索商品').fill(chosen.title);const filteredResponse=waitApi(page,api,'/api/v4/products');await page.getByRole('button',{name:'筛选',exact:true}).click();const filtered=await validated(await filteredResponse,'business','BusinessEnvelope_Page_Product__');assertScope(filtered.context,identity!,first.shop_id);expect(filtered.data.items.some((item:{product_id:string})=>item.product_id===productId)).toBe(true);
  const download=page.waitForEvent('download'),exportResponse=waitApi(page,api,'/api/v4/products/export');await page.getByRole('button',{name:'导出 CSV'}).click();const exported=await validated(await exportResponse,'business','BusinessEnvelope_ExportData_');assertScope(exported.context,identity!,first.shop_id);expect(exported.data.snapshot.data_revision).toBe(filtered.data.snapshot.data_revision);expect(exported.data.snapshot.snapshot_id).toBe(filtered.data.snapshot.snapshot_id);const file=await download;expect(file.suggestedFilename()).toBe('products.csv');const stream=await file.createReadStream(),chunks:Buffer[]=[];for await(const chunk of stream)chunks.push(Buffer.from(chunk));expect(Buffer.concat(chunks).equals(Buffer.from(exported.data.csv_text,'utf8'))).toBe(true);facts.downloads.push(sha(exported.data.csv_text));counts.downloads++;
  const detailResponse=waitApi(page,api,`/api/v4/products/${productId}`);await page.locator(`a[href="/v4/products/${productId}"]`).first().click();const initial=await validated(await detailResponse,'business','BusinessEnvelope_ProductDetail_');assertScope(initial.context,identity!,first.shop_id);expect(initial.data.product.product_id).toBe(productId);expect(initial.data.product.version).toBe(productVersion);
  const drawer=page.getByRole('dialog',{name:'商品详情'});
  for(const tag of ['v41-live-a','v41-live-b']){
   await drawer.getByRole('button',{name:'编辑标签'}).click();await drawer.getByLabel('标签（逗号分隔，最多 8 项）').fill(tag);
   const postResponse=waitApi(page,api,pathFor('product_tags',productId),'POST');const readback=page.waitForResponse(async response=>{const url=new URL(response.url());if(url.origin!==api||url.pathname!==`/api/v4/products/${productId}`||response.request().method()!=='GET'||!response.ok())return false;try{return (await response.json()).data.product.version===productVersion+1;}catch{return false;}});
   await drawer.getByRole('button',{name:'确认保存'}).click();const raw=await postResponse,key=keyOf(raw),posted=await validated(raw,'business','BusinessEnvelope_ActionResult_');assertScope(posted.context,identity!,first.shop_id);expect(posted.data.receipt.request_key).toBe(key);expect(posted.data.receipt.resource_id).toBe(productId);expect(posted.data.receipt.resource_version).toBe(productVersion+1);
   const reread=await validated(await readback,'business','BusinessEnvelope_ProductDetail_');assertScope(reread.context,identity!,first.shop_id);expect(reread.data.product.version).toBe(productVersion+1);expect(reread.data.product.tags).toEqual([tag]);expect(reread.data.snapshot.data_revision).toBe(posted.data.receipt.after_revision);await journal.flush();await writer.operation(
    subjectContext(identity!),
    first.shop_id,
    'product_tags',
    key,
    'COMMITTED_READBACK',
   );productVersion++;counts.tag_committed++;await expect(drawer.getByRole('button',{name:'编辑标签'})).toBeEnabled();
  }
 });

 await test.step('known-payment fulfillment and unknown-payment refusal',async()=>{
  const listResponse=waitApi(page,api,'/api/v4/orders');const orders=await readable(page,()=>page.goto('/v4/orders').then(()=>{}),listResponse,'BusinessEnvelope_Page_Order__',identity!,first.shop_id);
  const known=orders.data.items.find((item:{payment_status:string;demo_fulfillment:string})=>item.payment_status==='payment_recorded'&&item.demo_fulfillment==='demo_unfulfilled');const unknown=orders.data.items.find((item:{payment_status:string})=>item.payment_status==='payment_timestamp_unknown');
  if(!known||!unknown)throw new Error('OWNED_ORDER_SAMPLES_UNAVAILABLE');
  const unknownResponse=waitApi(page,api,`/api/v4/orders/${unknown.order_id}`);await page.locator(`a[href="/v4/orders/${unknown.order_id}"]`).first().click();const unknownDetail=await validated(await unknownResponse,'business','BusinessEnvelope_OrderDetail_');assertScope(unknownDetail.context,identity!,first.shop_id);expect(unknownDetail.data.order.payment_status).toBe('payment_timestamp_unknown');await expect(page.getByRole('dialog',{name:'订单详情'}).getByRole('button',{name:'标记演示已履约'})).toBeDisabled();
  const knownResponse=waitApi(page,api,`/api/v4/orders/${known.order_id}`);await page.goto(`/v4/orders/${known.order_id}`);const knownDetail=await validated(await knownResponse,'business','BusinessEnvelope_OrderDetail_');assertScope(knownDetail.context,identity!,first.shop_id);const drawer=page.getByRole('dialog',{name:'订单详情'});await drawer.getByRole('button',{name:'标记演示已履约'}).click();
  const action=waitApi(page,api,pathFor('order_fulfillment',known.order_id),'POST');const readback=page.waitForResponse(async response=>{const url=new URL(response.url());if(url.origin!==api||url.pathname!==`/api/v4/orders/${known.order_id}`||response.request().method()!=='GET'||!response.ok())return false;try{return (await response.json()).data.order.demo_fulfillment==='demo_fulfilled';}catch{return false;}});
  await drawer.getByRole('button',{name:'确认演示履约'}).click();const raw=await action,key=keyOf(raw),posted=await validated(raw,'business','BusinessEnvelope_ActionResult_');assertScope(posted.context,identity!,first.shop_id);expect(posted.data.receipt.request_key).toBe(key);expect(posted.data.receipt.resource_id).toBe(known.order_id);expect(posted.data.receipt.resource_version).toBe(knownDetail.data.order.fulfillment_version+1);
  const after=await validated(await readback,'business','BusinessEnvelope_OrderDetail_');assertScope(after.context,identity!,first.shop_id);expect(after.data.order.fulfillment_version).toBe(posted.data.receipt.resource_version);expect(after.data.snapshot.data_revision).toBe(posted.data.receipt.after_revision);await journal.flush();await writer.operation(
    subjectContext(identity!),
    first.shop_id,
    'order_fulfillment',
    key,
    'COMMITTED_READBACK',
   );counts.fulfillment_committed++;
 });

 await test.step('CSV and XLSX preview, mapping, confirmation and source readback',async()=>{
  const initialProducts=waitApi(page,api,'/api/v4/products');const initial=await readable(page,()=>page.goto('/v4/products/import').then(()=>{}),initialProducts,'BusinessEnvelope_Page_Product__',identity!,first.shop_id);
  let revision=initial.data.snapshot.data_revision;
  for(const format of ['csv','xlsx'] as const){
   const input=page.getByLabel('文件');
   if(format==='csv')await input.setInputFiles({name:'owned-products.csv',mimeType:'text/csv',buffer:Buffer.from('sku,title,price,currency\nV41LIVE-CSV,Owned CSV product,123,TWD\n')});
   else await input.setInputFiles(fileURLToPath(new URL('../v41-tests/fixtures/sample.xlsx',import.meta.url)));
   const firstPreview=waitApi(page,api,'/api/v4/imports/previews','POST');const firstLookup=page.waitForResponse(response=>{const url=new URL(response.url());return url.origin===api&&url.pathname.startsWith('/api/v4/imports/preview-requests/')&&response.request().method()==='GET';});const firstJob=page.waitForResponse(response=>{const url=new URL(response.url());return url.origin===api&&/^\/api\/v4\/imports\/[0-9a-f-]{36}$/i.test(url.pathname)&&response.request().method()==='GET';});
   await page.getByRole('button',{name:'上传并预览'}).click();const firstRaw=await firstPreview,firstKey=keyOf(firstRaw),discovery=await validated(firstRaw,'business','BusinessEnvelope_ImportPreviewData_');assertScope(discovery.context,identity!,first.shop_id);expect(discovery.data.job.data_revision).toBe(revision);expect(discovery.data.state).toBe('DISCOVERED');
   const firstLookupRaw=await firstLookup;expect(new URL(firstLookupRaw.url()).pathname.endsWith(firstKey)).toBe(true);const firstFound=await validated(firstLookupRaw,'business','BusinessEnvelope_PreviewLookup_'),firstRead=await validated(await firstJob,'business','BusinessEnvelope_ImportPreviewData_');assertScope(firstFound.context,identity!,first.shop_id);assertScope(firstRead.context,identity!,first.shop_id);expect(firstFound.data.request_key).toBe(firstKey);expect(firstFound.data.status).toBe('COMMITTED');expect(firstFound.data.job.import_job_id).toBe(discovery.data.job.import_job_id);expect(firstRead.data.job.job_digest).toBe(discovery.data.job.job_digest);await journal.flush();await writer.operation(
    subjectContext(identity!),
    first.shop_id,
    'preview',
    firstKey,
    'COMMITTED_READBACK',
   );counts.preview_committed++;
   await expect(page.getByText(/状态 DISCOVERED/)).toBeVisible();
   for(const [label,column] of [['SKU','sku'],['商品名称','title'],['价格','price'],['币种','currency']]){const field=page.getByRole('combobox',{name:label,exact:true});await field.selectOption(column);await expect(field).toHaveValue(column);}
   const mappedResponse=waitApi(page,api,'/api/v4/imports/previews','POST');const mappedLookup=page.waitForResponse(response=>{const url=new URL(response.url());return url.origin===api&&url.pathname.startsWith('/api/v4/imports/preview-requests/')&&response.request().method()==='GET';});const mappedJob=page.waitForResponse(response=>{const url=new URL(response.url());return url.origin===api&&/^\/api\/v4\/imports\/[0-9a-f-]{36}$/i.test(url.pathname)&&response.request().method()==='GET';});
   await page.getByRole('button',{name:'确认映射并重新预览'}).click();const mappedRaw=await mappedResponse,mappedKey=keyOf(mappedRaw),mapped=await validated(mappedRaw,'business','BusinessEnvelope_ImportPreviewData_');assertScope(mapped.context,identity!,first.shop_id);expect(mapped.data.job.parent_job_id).toBe(discovery.data.job.import_job_id);expect(mapped.data.job.data_revision).toBe(revision);expect(mapped.data.file_digest).toBe(discovery.data.file_digest);expect(mapped.data.state).toBe('READY');expect(mapped.data.issue_count).toBe(0);expect(mapped.data.confirmable).toBe(true);
   const mappedLookupRaw=await mappedLookup;expect(new URL(mappedLookupRaw.url()).pathname.endsWith(mappedKey)).toBe(true);const mappedFound=await validated(mappedLookupRaw,'business','BusinessEnvelope_PreviewLookup_'),mappedRead=await validated(await mappedJob,'business','BusinessEnvelope_ImportPreviewData_');assertScope(mappedFound.context,identity!,first.shop_id);assertScope(mappedRead.context,identity!,first.shop_id);expect(mappedFound.data.request_key).toBe(mappedKey);expect(mappedFound.data.status).toBe('COMMITTED');expect(mappedFound.data.job.import_job_id).toBe(mapped.data.job.import_job_id);expect(mappedRead.data.job.job_digest).toBe(mapped.data.job.job_digest);await journal.flush();await writer.operation(
    subjectContext(identity!),
    first.shop_id,
    'preview',
    mappedKey,
    'COMMITTED_READBACK',
   );counts.preview_committed++;
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
   );counts.import_committed++;facts.source_modes.push(after.data.snapshot.source.data_mode);
   await expect(page.getByText('已核对导入回执、作业状态和数据来源。')).toBeVisible();
   const sku=format==='csv'?'V41LIVE-CSV':'SKU-1',readProducts=waitApi(page,api,'/api/v4/products');await page.getByRole('link',{name:'查看商品列表'}).click();const productPage=await validated(await readProducts,'business','BusinessEnvelope_Page_Product__');assertScope(productPage.context,identity!,first.shop_id);
   await page.getByLabel('搜索商品').fill(sku);const search=waitApi(page,api,'/api/v4/products');await page.getByRole('button',{name:'筛选',exact:true}).click();const found=await validated(await search,'business','BusinessEnvelope_Page_Product__');assertScope(found.context,identity!,first.shop_id);const imported=found.data.items.find((item:{source:{import_job_id:string};skus:{label:string}[]})=>item.source.import_job_id===jobId&&item.skus.some(s=>s.label===sku));if(!imported)throw new Error('IMPORTED_SKU_NOT_FOUND');expect(imported.source.data_mode).toBe('demo_upload');expect(imported.source.file_digest).toBe(mapped.data.file_digest);
   if(format==='csv'){
    const returnProducts=waitApi(page,api,'/api/v4/products');await page.goto('/v4/products/import');const current=await validated(await returnProducts,'business','BusinessEnvelope_Page_Product__');assertScope(current.context,identity!,first.shop_id);revision=current.data.snapshot.data_revision;await page.getByRole('button',{name:'放弃本地预览引用'}).click();await page.getByRole('button',{name:'确认放弃本地引用'}).click();
   }
  }
 });

 await test.step('shop and visitor isolation',async()=>{
  const otherList=waitApi(page,api,'/api/v4/products');await page.getByRole('combobox',{name:'店铺',exact:true}).selectOption(second.shop_id);const other=await validated(await otherList,'business','BusinessEnvelope_Page_Product__');assertScope(other.context,identity!,second.shop_id);await expect(page.getByText('v41-live-b',{exact:false})).toHaveCount(0);
  const secondContext=await browser.newContext({baseURL:web});
  try{
   const visitor=await secondContext.newPage(),visitorRegistrations=await installSessionRegistration(visitor,api,writer);await visitor.goto('/v4/products');await expect(visitor.getByRole('button',{name:'一键体验'})).toBeVisible();await expect(visitor.getByText('v41-live-b',{exact:false})).toHaveCount(0);
   const created=waitApi(visitor,api,'/api/v4/demo/sessions','POST'),sessionRead=visitor.waitForResponse(response=>response.url()===api+'/api/v4/demo/session'&&response.request().method()==='GET'&&response.ok());await visitor.getByRole('button',{name:'一键体验'}).click();const create=await created;expect(create.ok()).toBe(true);expect((await sessionRead).ok()).toBe(true);await expect(visitor.getByText('演示空间已建立。')).toBeVisible();const otherSession=await safeSession(visitor,api);expect(otherSession.context.tenant_id).not.toBe(identity!.tenant_id);expect(otherSession.data.creation_request_key).toBe(keyOf(create));
   const shop=otherSession.data.shops.find((item:{currency:string})=>item.currency==='TWD');if(!shop)throw new Error('SECOND_VISITOR_SHOP_MISSING');if(!visitorRegistrations.some(item=>item.context.tenant_id===otherSession.context.tenant_id&&item.context.organization_id===otherSession.context.organization_id&&item.context.principal_id===otherSession.context.principal_id&&item.context.reset_epoch===otherSession.context.reset_epoch&&item.context.auth_generation===otherSession.context.auth_generation&&item.shops.includes(shop.shop_id)))throw new Error('SESSION_SCOPE_NOT_REGISTERED');
   const list=waitApi(visitor,api,'/api/v4/products');await visitor.getByRole('combobox',{name:'店铺',exact:true}).selectOption(shop.shop_id);const result=await validated(await list,'business','BusinessEnvelope_Page_Product__');assertScope(result.context,otherSession.context,shop.shop_id);expect(result.data.items.some((item:{tags:string[]})=>item.tags.includes('v41-live-b'))).toBe(false);await expect(visitor.getByText('v41-live-b',{exact:false})).toHaveCount(0);facts.second_tenant=true;
  }finally{await secondContext.close();}
 });
 await journal.flush();if(journal.pending())throw new Error('BUSINESS_REQUEST_UNSETTLED');
 writeFileSync(join(evidence,'business.safe.json'),JSON.stringify({source_sha:c.source_sha,source_tree:c.source_tree,scope:'LIVE_BUSINESS_ONLY',native200:'NOT_RUN_IN_THIS_SPEC',counts,facts},null,2),{mode:0o600,flag:'wx'});
});
