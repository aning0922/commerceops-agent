import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire,stripTypeScriptTypes} from 'node:module';
import {pathToFileURL} from 'node:url';
import {randomUUID,createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const require=createRequire(import.meta.url);
const input=readFileSync(new URL('../lib/v41-client.ts',import.meta.url),'utf8');
const schema=readFileSync(new URL('../lib/v41-schema.json',import.meta.url),'utf8');
let output=stripTypeScriptTypes(input,{mode:'transform'});
output=output.replace("'ajv/dist/2020'",JSON.stringify(pathToFileURL(require.resolve('ajv/dist/2020')).href));
output=output.replace("'ajv-formats'",JSON.stringify(pathToFileURL(require.resolve('ajv-formats')).href));
output=output.replace("import schema from './v41-schema.json';",`const schema = ${schema};`);
const {validateV41,readV41,postV41}=await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
test('schema matches the reviewed candidate fingerprint and available source',()=>{
 assert.equal(createHash('sha256').update(schema).digest('hex'),'6a9e2fae9bf45077a2abb9c61699f5176e1fd5af156212ad45ea38f7c865e81e');
 let source;try{source=execFileSync('git',['show','00851a8c87191de52ab127d6ff46a6c56e892981:docs/v4/v4-1/API_CONTRACT.json'],{encoding:'utf8',stdio:['ignore','pipe','ignore']});}catch{return;}
 assert.deepEqual(JSON.parse(schema),JSON.parse(source).json_schema);
});
test('strict schema refuses unknown definitions and extra request fields',()=>{
 assert.equal(validateV41('Query',{shop_id:randomUUID()}),true);
 assert.equal(validateV41('Query',{shop_id:randomUUID(),role:'operator'}),false);
 assert.equal(validateV41('UnknownDefinition',{}),false);
});
test('read rejects unsupported routes before network and rejects malformed responses',async()=>{
 const original=globalThis.fetch;let calls=0;
 try {
  globalThis.fetch=async()=>{calls++;return Response.json({status:'OK'});};
  const context={reset_epoch:0,auth_generation:0};
  for(const path of ['/api/v4/demo/session','/api/v4/../v1/orders','/api/v4/products/%2f','//other.example/api/v4/products']) await assert.rejects(readV41('https://example.invalid',path,'BusinessEnvelope_Page_Product__',context),/INVALID_BUSINESS_PATH/);
  assert.equal(calls,0);
  await assert.rejects(readV41('https://example.invalid','/api/v4/products','BusinessEnvelope_Page_Product__',context),/INVALID_RESPONSE/);
  assert.equal(calls,1);
 } finally {globalThis.fetch=original;}
});
test('every candidate schema definition compiles in strict Ajv',()=>{
 for(const name of Object.keys(JSON.parse(schema).$defs))assert.doesNotThrow(()=>validateV41(name,null),name);
});

test('write accepts only frozen route and strict DTO and dispatches at most once',async()=>{
 const original=globalThis.fetch;let calls=0;const resource=randomUUID();
 const body={shop_id:randomUUID(),request_key:randomUUID(),expected_epoch:0,expected_generation:0,expected_data_revision:'a'.repeat(64),expected_version:0,tags:['checked']};
 try {
  globalThis.fetch=async(url,init)=>{calls++;assert.equal(init.method,'POST');assert.equal(init.credentials,'include');assert.equal(init.headers['X-CSRF-Token'],'csrf');assert.deepEqual(JSON.parse(init.body),body);throw new TypeError('network failure');};
  await assert.rejects(postV41('https://example.invalid',`/api/v4/products/${resource}/tags`,body,'csrf'),/network failure/);assert.equal(calls,1);
  await assert.rejects(postV41('https://example.invalid',`/api/v4/products/${resource}/tags`,{...body,role:'operator'},'csrf'),/INVALID_REQUEST/);
  await assert.rejects(postV41('https://example.invalid',`/api/v4/products/${resource}/delete`,body,'csrf'),/INVALID_BUSINESS_PATH/);
  await assert.rejects(postV41('https://example.invalid',`/api/v4/products/${resource}/tags`,body,''),/INVALID_REQUEST/);assert.equal(calls,1);
 } finally {globalThis.fetch=original;}
});
