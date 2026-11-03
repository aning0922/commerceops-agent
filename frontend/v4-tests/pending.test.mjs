import test from 'node:test';
import assert from 'node:assert/strict';
import {readPending} from '../lib/v4-pending.mjs';
const slot='slot', key='11111111-1111-4111-8111-111111111111';
const storage=value=>({getItem:()=>value});
test('pending storage treats corruption and access failure as unknown, not empty',()=>{
 assert.equal(readPending(storage(null),slot),null);
 for(const value of ['{','null','{}',JSON.stringify({operation:'reset',key:''}),JSON.stringify({operation:'bad',key}),JSON.stringify({operation:'reset',key,extra:true})]) {
  assert.deepEqual(readPending(storage(value),slot),{operation:'storage_unavailable',key:''});
 }
 assert.deepEqual(readPending({getItem(){throw new Error('denied');}},slot),{operation:'storage_unavailable',key:''});
 assert.deepEqual(readPending(storage(JSON.stringify({operation:'reset',key})),slot),{operation:'reset',key});
});
test('control recovery proof is strict and never stores credentials',()=>{
 const context={tenant_id:key,organization_id:key,principal_id:key,shop_id:null,reset_epoch:0,auth_generation:0,authorized_at:'2026-11-03T00:00:00Z'};
 const proof={context,creation_request_key:key,persona_id:'operator',target_persona:'approver'};
 const pending={operation:'persona',key,proof};
 assert.deepEqual(readPending(storage(JSON.stringify(pending)),slot),pending);
 for(const changed of [
  {...proof,csrf_token:0},
  {...proof,context:{...context,shop_id:key}},
  {...proof,context:{...context,auth_generation:0.5}},
  {...proof,creation_request_key:''},
  {...proof,target_persona:null},
 ]) assert.equal(readPending(storage(JSON.stringify({...pending,proof:changed})),slot).operation,'storage_unavailable');
 assert.equal(readPending(storage(JSON.stringify({...pending,operation:'reset'})),slot).operation,'storage_unavailable');
 assert.deepEqual(readPending(storage(JSON.stringify({operation:'reset',key,proof:{...proof,target_persona:null}})),slot).proof.target_persona,null);
});
