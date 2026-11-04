import {test,expect,type Route} from '@playwright/test';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const id='11111111-1111-4111-8111-111111111111',first='22222222-2222-4222-8222-222222222222',second='33333333-3333-4333-8333-333333333333';
const now='2026-11-03T00:00:00Z',expires='2026-11-03T00:10:00Z',before='a'.repeat(64),after='b'.repeat(64);
const context={tenant_id:id,organization_id:id,principal_id:id,shop_id:null,reset_epoch:0,auth_generation:0,authorized_at:now};
const source={data_mode:'demo_fixture',evidence_mode:'synthetic_demo',fixture_version:'v4-demo-seed-1',fixture_digest:before};
const base={schema_version:'v4-demo-v1',server_time:now,trace_id:id,status:'OK'};
const business={schema_version:'v4-business-v1',server_time:now,trace_id:id,status:'OK',context:{...context,shop_id:id}};
const mapping={sku:'sku',title:'title',price:'price',currency:'currency',tags:null};
const cors=(handler:(route:Route)=>Promise<void>|void)=>async(route:Route)=>{
 const headers={'access-control-allow-origin':new URL(process.env.V41_WEB_ORIGIN!).origin,'access-control-allow-credentials':'true','access-control-allow-methods':'GET,POST,OPTIONS','access-control-allow-headers':'content-type,x-csrf-token,x-demo-epoch,x-demo-generation'};
 if(route.request().method()==='OPTIONS'){await route.fulfill({status:204,headers});return;}
 const wrapped=new Proxy(route,{get(target,property){if(property==='fulfill')return (options:Parameters<Route['fulfill']>[0])=>target.fulfill({...options,headers:{...options?.headers,...headers}});const value=Reflect.get(target,property,target);return typeof value==='function'?value.bind(target):value;}});await handler(wrapped);
};
for(const format of ['csv','xlsx'] as const)test(`UI_FIXTURE: ${format} discovery, mapping and original-key confirm recovery`,async({page})=>{
 let digest='',previewCount=0,confirmCount=0,lookupCount=0,confirmKey='',committed=false;
 const jobs=new Map<string,object>(),requests=new Map<string,string>();
 const job=(n:number)=>({import_job_id:n===1?first:second,version:n,parent_job_id:n===1?null:first,job_digest:(n===1?'c':'d').repeat(64),data_revision:before,parser_version:'v41-parser-1',import_schema_version:'v41-import-1',expires_at:expires});
 const preview=(n:number,state=n===1?'DISCOVERED':'READY')=>({job:job(n),state,file_digest:digest,mapping:n===1?null:mapping,headers:['sku','title','price','currency'],sample:[{row:2,cells:['SKU-1','Demo','12','TWD']}],row_count:1,issue_count:0,issues:[],confirmable:state==='READY'});
 await page.route('**/api/v4/demo/**',cors(async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path.endsWith('/session'))return route.fulfill({json:{...base,context,data:{creation_request_key:id,persona_id:'operator',expires_at:expires,csrf_token:'csrf',shops:[{shop_id:id,display_name:'示例店铺',timezone:'Asia/Taipei',currency:'TWD',grants:['operator']}],source}}});
  if(path.endsWith('/seed-summary'))return route.fulfill({json:{...base,context:{...context,shop_id:id},data:{source,counts:{products:0,skus:0,orders:0,order_lines:0},snapshot_at:now}}});
  return route.fulfill({status:404});
 }));
 await page.route('**/api/v4/**',cors(async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname;if(path.startsWith('/api/v4/demo/'))return route.fallback();
  if(path==='/api/v4/products'){
   const uploads=committed?[{...source,data_mode:'demo_upload',baseline_snapshot_at:now,import_job_id:second,import_row:2,file_digest:digest}]:[];
   return route.fulfill({json:{...business,data:{snapshot:{snapshot_id:before,data_revision:committed?after:before,read_at:now,source:{...source,data_mode:committed?'demo_mixed':'demo_fixture',baseline_snapshot_at:now,uploads}},items:committed?[{product_id:second,title:'Demo',tags:[],version:0,source:uploads[0],skus:[{sku_id:first,label:'SKU-1',price:'12',currency:'TWD',available_units:null,stock_reason:'UNKNOWN_STOCK'}]}]:[],total:committed?1:0,next_cursor:null}}});
  }
  if(path==='/api/v4/imports/previews'){
   const body=req.postDataJSON(),bytes=Buffer.from(body.file_base64,'base64'),actual=createHash('sha256').update(bytes).digest('hex');previewCount++;expect(body.format).toBe(format);if(previewCount===1){expect(body.parent_job_id).toBeNull();digest=actual;}else{expect(actual).toBe(digest);expect(body.parent_job_id).toBe(first);expect(body.mapping).toEqual(mapping);}requests.set(body.request_key,previewCount===1?first:second);jobs.set(previewCount===1?first:second,job(previewCount));return route.fulfill({json:{...business,data:preview(previewCount)}});
  }
  if(path.includes('/preview-requests/')){const key=path.split('/').at(-1)!;return route.fulfill({json:{...business,data:{request_key:key,status:'COMMITTED',job:jobs.get(requests.get(key)!)}}});}
  if(path===`/api/v4/imports/${first}`||path===`/api/v4/imports/${second}`){const n=path.endsWith(first)?1:2;return route.fulfill({json:{...business,data:preview(n,n===2&&committed?'COMMITTED':n===1?'DISCOVERED':'READY')}});}
  if(path===`/api/v4/imports/${second}/confirm`){confirmCount++;confirmKey=req.postDataJSON().request_key;committed=true;return route.fulfill({status:503,json:{...business,status:'UNKNOWN',error:{code:'SERVICE_UNAVAILABLE',safe_message:'unknown',retryable:false,request_key:confirmKey},context:undefined,data:undefined}});}
  if(path.includes('/actions/import_confirm/')){lookupCount++;expect(path.endsWith(confirmKey)).toBe(true);return route.fulfill({json:{...business,data:{operation:'import_confirm',request_key:confirmKey,status:'COMMITTED',receipt:{receipt_id:id,operation:'import_confirm',request_key:confirmKey,payload_digest:before,resource_id:second,resource_version:2,committed_at:now,before_revision:before,after_revision:after}}}});}
  return route.fulfill({status:404});
 }));
 await page.goto('/v4/products/import');await page.getByLabel('店铺').selectOption(id);await expect(page.getByRole('button',{name:'上传并预览'})).toBeDisabled();
 const input=page.getByLabel('文件');if(format==='csv')await input.setInputFiles({name:'sample.csv',mimeType:'text/csv',buffer:Buffer.from('sku,title,price,currency\nSKU-1,Demo,12,TWD\n')});else await input.setInputFiles(fileURLToPath(new URL('./fixtures/sample.xlsx',import.meta.url)));
 await page.getByRole('button',{name:'上传并预览'}).click();await expect(page.getByText(/状态 DISCOVERED/)).toBeVisible();
 await page.reload();await page.getByLabel('店铺').selectOption(id);await page.getByRole('button',{name:'读取已保存预览'}).click();await expect(page.getByText(/状态 DISCOVERED/)).toBeVisible();
 if(format==='csv')await input.setInputFiles({name:'sample.csv',mimeType:'text/csv',buffer:Buffer.from('sku,title,price,currency\nSKU-1,Demo,12,TWD\n')});else await input.setInputFiles(fileURLToPath(new URL('./fixtures/sample.xlsx',import.meta.url)));
 for(const [label,value] of [['SKU','sku'],['商品名称','title'],['价格','price'],['币种','currency']])await page.getByLabel(label,{exact:true}).selectOption(value);
 await input.setInputFiles({name:`different.${format}`,mimeType:'application/octet-stream',buffer:Buffer.from('different')});await page.getByRole('button',{name:'确认映射并重新预览'}).click();await expect(page.getByText('文件或预览状态无法核验，未发送操作。')).toBeVisible();expect(previewCount).toBe(1);
 if(format==='csv')await input.setInputFiles({name:'sample.csv',mimeType:'text/csv',buffer:Buffer.from('sku,title,price,currency\nSKU-1,Demo,12,TWD\n')});else await input.setInputFiles(fileURLToPath(new URL('./fixtures/sample.xlsx',import.meta.url)));
 await page.getByRole('button',{name:'确认映射并重新预览'}).click();await expect(page.getByText(/状态 READY/)).toBeVisible();await page.getByRole('button',{name:'准备确认导入'}).click();await page.getByRole('button',{name:'确认导入',exact:true}).click();
 await expect(page.getByText(/导入未确认或结果未知/)).toBeVisible();await page.getByRole('button',{name:'核对原业务操作'}).click();await expect(page.getByText('已核对原导入回执和来源。')).toBeVisible();expect(previewCount).toBe(2);expect(confirmCount).toBe(1);expect(lookupCount).toBe(1);
});
