import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {sessionResponseMatches} from './lifecycle.waiter.mjs';
const id='11111111-1111-4111-8111-111111111111';
const api='https://api.example';
const current={schema_version:'v4-demo-v1',status:'OK',server_time:'2026-11-03T00:00:00Z',trace_id:id,context:{tenant_id:id,organization_id:id,principal_id:id,shop_id:null,reset_epoch:2,auth_generation:4,authorized_at:'2026-11-03T00:00:00Z'},data:{creation_request_key:id,persona_id:'approver',expires_at:'2026-11-03T00:30:00Z',csrf_token:'x',shops:[],source:{data_mode:'demo_fixture',evidence_mode:'synthetic_demo',fixture_version:'v4-demo-seed-1',fixture_digest:'a'.repeat(64)}}};
const expected={creationKey:id,tenant:id,organization:id,persona:'approver',epoch:2,generation:4};
const event=body=>({url:()=>`${api}/api/v4/demo/session`,request:()=>({method:()=> 'GET'}),ok:()=>true,json:async()=>body});
test('old in-flight response cannot consume the new session waiter',async()=>{
 const bus=new EventEmitter();let resolved=false;
 const waiter=new Promise(resolve=>bus.on('response',async response=>{if(await sessionResponseMatches(response,api,expected)){resolved=true;resolve(response);}}));
 const old=event({...current,context:{...current.context,auth_generation:3}});bus.emit('response',old);
 await new Promise(resolve=>setImmediate(resolve));assert.equal(resolved,false);
 const invalid=event({...current,extra:true});bus.emit('response',invalid);
 await new Promise(resolve=>setImmediate(resolve));assert.equal(resolved,false);
 const fresh=event(current);bus.emit('response',fresh);assert.strictEqual(await waiter,fresh);
 assert.equal(await sessionResponseMatches(event(current),'https://other.example',expected),false);
});
