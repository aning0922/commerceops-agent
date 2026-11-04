import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire,stripTypeScriptTypes} from 'node:module';
import {pathToFileURL} from 'node:url';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const require=createRequire(import.meta.url);
const input=readFileSync(new URL('../lib/v41-client.ts',import.meta.url),'utf8');
const schema=readFileSync(new URL('../lib/v41-schema.json',import.meta.url),'utf8');
let output=stripTypeScriptTypes(input,{mode:'transform'});
output=output.replace("'ajv/dist/2020'",JSON.stringify(pathToFileURL(require.resolve('ajv/dist/2020')).href));
output=output.replace("'ajv-formats'",JSON.stringify(pathToFileURL(require.resolve('ajv-formats')).href));
output=output.replace("import schema from './v41-schema.json';",`const schema = ${schema};`);
const {validateV41,readV41}=await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
test('schema exactly derives from the committed candidate source',()=>{
 const source=execFileSync('git',['show','b72331fa572d9d67ad176902283da721aeda4cf1:docs/v4/v4-1/API_CONTRACT.json'],{encoding:'utf8'});
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
test('every committed route request and response schema compiles in strict Ajv',()=>{
 const source=execFileSync('git',['show','b72331fa572d9d67ad176902283da721aeda4cf1:docs/v4/v4-1/API_CONTRACT.json'],{encoding:'utf8'});
 const contract=JSON.parse(source);
 for(const route of contract.routes) for(const ref of [route.request,route.response,route.failure]) {
  const name=ref.$ref.slice('#/$defs/'.length);
  assert.equal(validateV41(name,null),false,`${route.method} ${route.path} ${name}`);
 }
});
