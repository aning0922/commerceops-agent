import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {loadV41Pending,reserveV41Pending,finishV41Pending} from '../lib/v41-pending.mjs';
function storage(){const m=new Map();return {getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};}
function fixture(){const id=()=>randomUUID(),context={tenant_id:id(),organization_id:id(),principal_id:id(),shop_id:null,reset_epoch:2,auth_generation:3,authorized_at:new Date().toISOString()};return {operation:'product_tags',request_key:id(),resource_id:id(),shop_id:id(),revision:'a'.repeat(64),version:0,context};}
function result(value){return {status:'COMMITTED',context:{...value.context,shop_id:value.shop_id},data:{next_step:'READ_CURRENT_RESOURCE',receipt:{operation:value.operation,request_key:value.request_key,resource_id:value.resource_id,before_revision:value.revision,after_revision:'b'.repeat(64),resource_version:value.version+1}}};}
test('reservation is exclusive, minimal, and unavailable/corrupt storage blocks',()=>{
 const s=storage(),value=fixture();assert.equal(reserveV41Pending(s,value),true);assert.equal(reserveV41Pending(s,fixture()),false);assert.equal(loadV41Pending(s).state,'pending');
 const corrupt=storage();corrupt.setItem('commerceops-v41-pending','{');assert.equal(loadV41Pending(corrupt).state,'blocked');assert.equal(reserveV41Pending(corrupt,value),false);
 const blocked={getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}};assert.equal(reserveV41Pending(blocked,value),false);
 assert.equal(reserveV41Pending(storage(),{...value,csrf:'no'}),false);
});
test('only matching committed receipt and fresh identity can remove original pending key',()=>{
 const s=storage(),value=fixture(),session={context:value.context,data:{shops:[{shop_id:value.shop_id,grants:['operator']}]}};assert.equal(reserveV41Pending(s,value),true);
 for(const altered of [{...result(value),status:'UNKNOWN'},{...result(value),context:{...result(value).context,shop_id:randomUUID()}},{...result(value),data:{receipt:{...result(value).data.receipt,resource_version:8}}}])assert.equal(finishV41Pending(s,session,altered),false);
 assert.equal(finishV41Pending(s,{...session,context:{...value.context,auth_generation:4}},result(value)),false);
 assert.equal(finishV41Pending(s,{...session,data:{shops:[]}},result(value)),false);
 assert.equal(finishV41Pending(s,session,{...result(value),data:{...result(value).data,status:'UNKNOWN'}}),false);
 assert.equal(loadV41Pending(s).state,'pending');assert.equal(finishV41Pending(s,session,result(value)),true);assert.equal(loadV41Pending(s).state,'empty');
});
