import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
const spec=JSON.parse(readFileSync(new URL('../../docs/v4/baseline/v4-public-openapi.json',import.meta.url)));
const ajv=new Ajv2020({strict:false}); addFormats(ajv);
const validator=name=>ajv.compile({...spec,$ref:`#/components/schemas/${name}`});
const id='11111111-1111-4111-8111-111111111111';
const context={tenant_id:id,organization_id:id,principal_id:id,shop_id:null,reset_epoch:0,auth_generation:0,authorized_at:'2026-11-03T00:00:00Z'};
const source={data_mode:'demo_fixture',evidence_mode:'synthetic_demo',fixture_version:'v4-demo-seed-1',fixture_digest:'a'.repeat(64)};
const session={schema_version:'v4-demo-v1',server_time:'2026-11-03T00:00:00Z',trace_id:id,status:'OK',context,data:{creation_request_key:id,persona_id:'admin',expires_at:'2026-11-03T00:30:00Z',csrf_token:'x',shops:[],source}};
test('session accepts no grants but rejects missing context and extra data',()=>{const v=validator('SessionEnvelope');assert.equal(v(session),true);const {context:_,...missing}=session;assert.equal(v(missing),false);assert.equal(v({...session,data:{...session.data,role:'admin'}}),false);});
test('failure permits unknown DB time and rejects invented shape',()=>{const v=validator('FailureEnvelope');const input={schema_version:'v4-demo-v1',server_time:null,trace_id:id,status:'UNKNOWN',error:{code:'SERVICE_UNAVAILABLE',safe_message:'unavailable',retryable:false,request_key:null}};assert.equal(v(input),true);assert.equal(v({...input,error:{...input.error,retryable:true}}),false);});

test('bundled contract is byte-identical to frozen source',()=>{assert.deepEqual(readFileSync(new URL('../lib/v4-openapi.json',import.meta.url)),readFileSync(new URL('../../docs/v4/baseline/v4-public-openapi.json',import.meta.url)));});
