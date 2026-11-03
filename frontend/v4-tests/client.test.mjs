import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire,stripTypeScriptTypes} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(import.meta.url);
const input=readFileSync(new URL('../lib/v4-client.ts',import.meta.url),'utf8');
const schema=readFileSync(new URL('../lib/v4-schema.json',import.meta.url),'utf8');
let output=stripTypeScriptTypes(input,{mode:'transform'});
output=output.replace("'ajv/dist/2020'",JSON.stringify(pathToFileURL(require.resolve('ajv/dist/2020')).href));
output=output.replace("'ajv-formats'",JSON.stringify(pathToFileURL(require.resolve('ajv-formats')).href));
output=output.replace("import schema from './v4-schema.json';",`const schema = ${schema};`);
const {request,ApiError}=await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
const id='11111111-1111-4111-8111-111111111111';
const envelope={schema_version:'v4-demo-v1',status:'OK',server_time:'2026-11-03T00:00:00Z',trace_id:id,data:{csrf_token:'csrf',expires_at:'2026-11-03T00:05:00Z',state:'anonymous_bootstrap'}};
test('client refuses missing origin and validates response with credentialed fetch',async()=>{
 const original=globalThis.fetch;let calls=0;
 try {
  globalThis.fetch=async (url,init)=>{calls++;assert.equal(url,'https://api.example/api/v4/demo/bootstrap');assert.equal(init.credentials,'include');assert.equal(init.cache,'no-store');return Response.json(envelope);};
  await assert.rejects(request(null,'/bootstrap','BootstrapEnvelope'),/API_NOT_CONFIGURED/);assert.equal(calls,0);
  assert.deepEqual(await request('https://api.example','/bootstrap','BootstrapEnvelope'),envelope);assert.equal(calls,1);
  globalThis.fetch=async()=>Response.json({...envelope,unexpected:true});
  await assert.rejects(request('https://api.example','/bootstrap','BootstrapEnvelope'),/INVALID_RESPONSE/);
 } finally {globalThis.fetch=original;}
});
test('client retains validated capacity error and server retry hint',async()=>{
 const original=globalThis.fetch;
 try {
  globalThis.fetch=async()=>Response.json({schema_version:'v4-demo-v1',status:'REJECTED',server_time:null,trace_id:id,error:{code:'CAPACITY_LIMIT',safe_message:'full',retryable:false,request_key:null}},{status:429,headers:{'Retry-After':'60'}});
  await assert.rejects(request('https://api.example','/bootstrap','BootstrapEnvelope'),error=>error instanceof ApiError&&error.status===429&&error.outcome==='REJECTED'&&error.retryAfter==='60');
 } finally {globalThis.fetch=original;}
});
