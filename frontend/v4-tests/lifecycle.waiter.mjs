import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import {readFileSync} from 'node:fs';
const schema=JSON.parse(readFileSync(new URL('../lib/v4-schema.json',import.meta.url),'utf8'));
const ajv=new Ajv2020({strict:true,allowUnionTypes:true,validateFormats:true});addFormats(ajv);
const validate=ajv.compile({...schema,$ref:'#/$defs/SessionEnvelope'});
export function matchesExpectedSession(body, expected) {
 if(!validate(body) || body.status !== 'OK' || body.context.shop_id !== null) return false;
 return body.data.creation_request_key===expected.creationKey && body.context.tenant_id===expected.tenant &&
  body.context.organization_id===expected.organization && body.data.persona_id===expected.persona &&
  body.context.reset_epoch===expected.epoch && body.context.auth_generation===expected.generation;
}
export async function sessionResponseMatches(r,api,expected) {
 const url=new URL(r.url());
 if(url.origin!==api||url.pathname!=='/api/v4/demo/session'||r.request().method()!=='GET'||!r.ok())return false;
 try{return matchesExpectedSession(await r.json(),expected);}catch{return false;}
}
