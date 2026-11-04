import {expect,type Page,type Request,type Response} from '@playwright/test';
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import businessSchema from '../lib/v41-schema.json' with {type:'json'};
import sessionSchema from '../lib/v4-schema.json' with {type:'json'};

export type Identity={tenant_id:string;organization_id:string;principal_id:string;shop_id:string|null;reset_epoch:number;auth_generation:number;authorized_at:string};
export type SubjectContext={tenant_id:string;organization_id:string;principal_id:string;reset_epoch:number;auth_generation:number};
export function subjectContext(value:Identity):SubjectContext{return {tenant_id:value.tenant_id,organization_id:value.organization_id,principal_id:value.principal_id,reset_epoch:value.reset_epoch,auth_generation:value.auth_generation};}
export type SubjectState='ATTEMPT_STARTED'|'ACK_OK'|'ACK_COMMITTED'|'ACK_REJECTED'|'ACK_UNKNOWN'|'COMMITTED_READBACK'|'UNKNOWN_READBACK'|'SQL_ROLLBACK_VERIFIED';
export type SubjectWriter={scope:(context:SubjectContext,shopId:string)=>void|Promise<void>;operation:(context:SubjectContext,shopId:string,operation:'preview'|'product_tags'|'order_fulfillment'|'import_confirm',key:string,state:SubjectState,request?:{method:'POST';path:string;body:Record<string,unknown>})=>void|Promise<void>};
const ajv=new Ajv2020({strict:true,allowUnionTypes:true});addFormats(ajv);
const validators=new Map<string,ReturnType<typeof ajv.compile>>();
function validator(schema:'session'|'business',name:string){
 const key=`${schema}:${name}`;let result=validators.get(key);if(!result){const root=schema==='session'?sessionSchema:businessSchema;result=ajv.compile({...root,$ref:`#/$defs/${name}`});validators.set(key,result);}return result;
}
export async function validated(response:Response,schema:'session'|'business',name:string){
 if(!response.ok())throw new Error('OWNED_RESPONSE_NOT_OK');
 const body=await response.json();if(!validator(schema,name)(body))throw new Error('OWNED_RESPONSE_SCHEMA_MISMATCH');return body;
}
export function sameScope(actual:Identity,expected:Identity,shopId:string|null){
 return actual.tenant_id===expected.tenant_id&&actual.organization_id===expected.organization_id&&actual.principal_id===expected.principal_id&&actual.reset_epoch===expected.reset_epoch&&actual.auth_generation===expected.auth_generation&&actual.shop_id===shopId;
}
export function assertScope(actual:Identity,expected:Identity,shopId:string|null){expect(sameScope(actual,expected,shopId)).toBe(true);}
export function waitApi(page:Page,api:string,path:string,method='GET'){
 return page.waitForResponse(response=>{const url=new URL(response.url());return url.origin===api&&url.pathname===path&&response.request().method()===method;});
}
/** Pass-through only: durable intent precedes each real UI POST; no response is fabricated. */
export async function installBusinessJournal(page:Page,api:string,writer:SubjectWriter,getIdentity:()=>Identity|null){
 type Operation='preview'|'product_tags'|'order_fulfillment'|'import_confirm';
 type Entry={context:Identity;shop:string;key:string;operation:Operation};
 const active=new Map<Request,Entry>(),writes=new Set<Promise<void>>();let failure=false;
 const enqueue=(job:Promise<void>)=>{writes.add(job);void job.then(()=>writes.delete(job),()=>{failure=true;writes.delete(job);});};
 const classify=(path:string):Operation|null=>path==='/api/v4/imports/previews'?'preview':/^\/api\/v4\/products\/[0-9a-f-]+\/tags$/i.test(path)?'product_tags':/^\/api\/v4\/orders\/[0-9a-f-]+\/fulfillment$/i.test(path)?'order_fulfillment':/^\/api\/v4\/imports\/[0-9a-f-]+\/confirm$/i.test(path)?'import_confirm':null;
 await page.route(api+'/api/v4/**',async route=>{
  const request=route.request(),url=new URL(request.url()),operation=request.method()==='POST'&&url.origin===api?classify(url.pathname):null;
  if(!operation){await route.continue();return;}
  const identity=getIdentity();let body:Record<string,unknown> & {shop_id?:string;request_key?:string;expected_epoch?:number;expected_generation?:number};
  try{body=request.postDataJSON();}catch{failure=true;await route.abort();return;}
  if(!identity||typeof body.shop_id!=='string'||typeof body.request_key!=='string'||body.expected_epoch!==identity.reset_epoch||body.expected_generation!==identity.auth_generation){failure=true;await route.abort();return;}
  const entry={context:{...identity},shop:body.shop_id,key:body.request_key,operation};
  try{await writer.operation(subjectContext(entry.context),entry.shop,entry.operation,entry.key,'ATTEMPT_STARTED',{method:'POST',path:url.pathname,body});}
  catch{failure=true;await route.abort();return;}
  active.set(request,entry);try{await route.continue();}catch{failure=true;active.delete(request);enqueue(Promise.resolve().then(()=>writer.operation(subjectContext(entry.context),entry.shop,entry.operation,entry.key,'ACK_UNKNOWN')));} 
 });
 page.on('response',response=>{
  const entry=active.get(response.request());if(!entry)return;active.delete(response.request());
  enqueue((async()=>{let state:SubjectState='ACK_UNKNOWN';try{const body=await response.json();const schemaName=entry.operation==='preview'?'BusinessEnvelope_ImportPreviewData_':'BusinessEnvelope_ActionResult_';const valid=validator('business',schemaName)(body)&&sameScope(body?.context,entry.context,entry.shop)&&(entry.operation==='preview'||body?.data?.receipt?.request_key===entry.key);if(response.ok()&&valid&&body?.status==='COMMITTED')state='ACK_COMMITTED';else if(response.ok()&&valid&&body?.status==='OK')state='ACK_OK';else if(!response.ok()&&body?.status==='REJECTED'&&validator('business','FailureEnvelope')(body))state='ACK_REJECTED';}catch{}await writer.operation(subjectContext(entry.context),entry.shop,entry.operation,entry.key,state);})());
 });
 page.on('requestfailed',request=>{const entry=active.get(request);if(!entry)return;active.delete(request);enqueue(Promise.resolve().then(()=>writer.operation(subjectContext(entry.context),entry.shop,entry.operation,entry.key,'ACK_UNKNOWN')));});
 return {async flush(){await Promise.allSettled([...writes]);if(failure||active.size)throw new Error('SUBJECT_JOURNAL_FAILED');},pending:()=>active.size};
}
