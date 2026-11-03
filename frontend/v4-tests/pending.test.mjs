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
