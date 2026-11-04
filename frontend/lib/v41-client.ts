import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import schema from './v41-schema.json';
import type {Context} from './v4-client';

// Generated schema source: independently reviewed API candidate 00851a8c87191de52ab127d6ff46a6c56e892981.
// Runtime routes and backend authorization must still be independently verified.
const ajv = new Ajv2020({strict:true,allowUnionTypes:true,validateFormats:true});
addFormats(ajv);
const validators = new Map<string,ReturnType<typeof ajv.compile>>();
export function validateV41(name:string, value:unknown):boolean {
  if (!Object.hasOwn(schema.$defs,name)) return false;
  let validator=validators.get(name);
  if (!validator) {validator=ajv.compile({...schema,$ref:`#/$defs/${name}`});validators.set(name,validator);}
  return Boolean(validator(value));
}
export type BusinessEnvelope<T> = {schema_version:'v4-business-v1';server_time:string;trace_id:string;status:'OK'|'COMMITTED'|'UNKNOWN';context:Context;data:T};
export class V41Error extends Error {
  constructor(public status:number,public outcome:string,public code:string){super(code);}
}
export async function readV41<T>(origin:string|null, path:string, schemaName:string, context:Context, signal?:AbortSignal):Promise<BusinessEnvelope<T>> {
  if (!origin) throw new Error('API_NOT_CONFIGURED');
  if (!/^\/api\/v4\/(?:dashboard(?:\/drilldown)?|products(?:\/(?:export|[0-9a-f-]{36}))?|orders(?:\/(?:export|[0-9a-f-]{36}))?|read-context|imports\/(?:preview-requests\/[0-9a-f-]{36}|[0-9a-f-]{36})|actions\/(?:product_tags|order_fulfillment|import_confirm)\/[0-9a-f-]{36})(?:\?[^#\\]*)?$/i.test(path)) throw new Error('INVALID_BUSINESS_PATH');
  const response=await fetch(`${origin}${path}`,{credentials:'include',cache:'no-store',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(15000)]):AbortSignal.timeout(15000),headers:{'X-Demo-Epoch':String(context.reset_epoch),'X-Demo-Generation':String(context.auth_generation)}});
  let value:unknown;try{value=await response.json();}catch{throw new V41Error(response.status,'UNKNOWN','INVALID_RESPONSE');}
  if (!response.ok) {
    if (!validateV41('FailureEnvelope',value)) throw new V41Error(response.status,'UNKNOWN','INVALID_RESPONSE');
    const failure=value as {status:string;error:{code:string}};
    throw new V41Error(response.status,failure.status,failure.error.code);
  }
  if (!validateV41(schemaName,value)) throw new V41Error(response.status,'UNKNOWN','INVALID_RESPONSE');
  return value as BusinessEnvelope<T>;
}

const uuidPath='[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const writes = [
  {pattern:new RegExp(`^/api/v4/products/${uuidPath}/tags$`,'i'),request:'SetProductTags',response:'BusinessEnvelope_ActionResult_'},
  {pattern:new RegExp(`^/api/v4/orders/${uuidPath}/fulfillment$`,'i'),request:'FulfillDemoOrder',response:'BusinessEnvelope_ActionResult_'},
  {pattern:/^\/api\/v4\/imports\/previews$/,request:'ImportPreviewInput',response:'BusinessEnvelope_ImportPreviewData_'},
  {pattern:new RegExp(`^/api/v4/imports/${uuidPath}/confirm$`,'i'),request:'ConfirmImport',response:'BusinessEnvelope_ActionResult_'},
] as const;
/** One dispatch only. The caller must persist a pending key before calling this function. */
export async function postV41<T>(origin:string|null,path:string,body:unknown,csrf:string,signal?:AbortSignal):Promise<BusinessEnvelope<T>> {
  if (!origin) throw new Error('API_NOT_CONFIGURED');
  const operation=writes.find(item=>item.pattern.test(path));
  if (!operation) throw new Error('INVALID_BUSINESS_PATH');
  if (!csrf || !validateV41(operation.request,body)) throw new Error('INVALID_REQUEST');
  const response=await fetch(`${origin}${path}`,{method:'POST',credentials:'include',cache:'no-store',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(15000)]):AbortSignal.timeout(15000),headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});
  let value:unknown;try{value=await response.json();}catch{throw new V41Error(response.status,'UNKNOWN','INVALID_RESPONSE');}
  if (!response.ok) {
    if (!validateV41('FailureEnvelope',value)) throw new V41Error(response.status,'UNKNOWN','INVALID_RESPONSE');
    const failure=value as {status:string;error:{code:string}};
    throw new V41Error(response.status,failure.status,failure.error.code);
  }
  if (!validateV41(operation.response,value)) throw new V41Error(response.status,'UNKNOWN','INVALID_RESPONSE');
  return value as BusinessEnvelope<T>;
}
