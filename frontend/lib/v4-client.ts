import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import schema from './v4-schema.json';

export type Context = {tenant_id:string; organization_id:string; principal_id:string; shop_id:string|null; reset_epoch:number; auth_generation:number; authorized_at:string};
export type Shop = {shop_id:string; display_name:string; timezone:string; currency:string; grants:string[]};
export type Session = {creation_request_key:string; persona_id:string; expires_at:string; csrf_token:string; shops:Shop[]; source:{fixture_version:string;fixture_digest:string}};
export type Envelope<T> = {schema_version:string; status:string; data:T; context:Context};
export type Summary = {counts:{products:number;skus:number;orders:number;order_lines:number};source:{fixture_version:string;fixture_digest:string};snapshot_at:string};
const ajv = new Ajv2020({strict:true, allowUnionTypes:true, validateFormats:true}); addFormats(ajv);
const validators = new Map<string, ReturnType<typeof ajv.compile>>();
function validate(name:string, data:unknown) {
  let validator = validators.get(name);
  if (!validator) { validator = ajv.compile({...schema, $ref:`#/$defs/${name}`}); validators.set(name, validator); }
  if (!validator(data)) throw new Error('INVALID_RESPONSE');
}
export class ApiError extends Error { constructor(public status:number, public code:string, public retryAfter:string|null = null, public outcome:string|null = null) {super(code);} }
export async function request<T>(origin:string|null, path:string, schema:string, init:RequestInit = {}):Promise<T> {
  if (!origin) throw new Error('API_NOT_CONFIGURED');
  const response = await fetch(`${origin}/api/v4/demo${path}`, {...init, credentials:'include', cache:'no-store', headers:{...(init.body ? {'Content-Type':'application/json'} : {}), ...init.headers}});
  let value:unknown; try {value = await response.json();} catch {throw new ApiError(response.status, 'INVALID_RESPONSE');}
  if (!response.ok) { validate('FailureEnvelope',value); const e=value as {status:string;error:{code:string}}; throw new ApiError(response.status,e.error.code,response.headers.get('Retry-After'),e.status); }
  validate(schema,value); return value as T;
}
export function post<T>(origin:string|null, path:string, schema:string, body:object, csrf:string) {
  return request<T>(origin,path,schema,{method:'POST',headers:{'X-CSRF-Token':csrf},body:JSON.stringify(body)});
}
