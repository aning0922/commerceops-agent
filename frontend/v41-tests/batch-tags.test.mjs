import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {batchTargets,applyBatchTags,matchesBatchRead,matchesBatchTags} from '../lib/v41-batch-tags.mjs';
import {reserveV41Pending,loadV41Pending,finishV41Pending} from '../lib/v41-pending.mjs';
const rev=n=>String(n).repeat(64),items=()=>[0,1].map(()=>({product_id:randomUUID(),version:3}));
function memory(){const m=new Map();return {getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};}
function context(){return {tenant_id:randomUUID(),organization_id:randomUUID(),principal_id:randomUUID(),shop_id:null,reset_epoch:1,auth_generation:1,authorized_at:new Date().toISOString()};}
test('selection is restricted to unique current-page objects and existing tag rules',()=>{
 const page=items(),ids=page.map(x=>x.product_id);
 assert.equal(batchTargets(page,[randomUUID()],['x']),null);assert.equal(batchTargets(page,[ids[0],ids[0]],[]),null);
 assert.equal(batchTargets([...page,page[0]],ids,[]),null);assert.equal(batchTargets(page,ids,['x','x']),null);assert.equal(batchTargets(page,ids,['x\n']),null);
 assert.equal(batchTargets(page,ids,Array(9).fill('x')),null);assert.equal(batchTargets(page,ids,['a'.repeat(25)]),null);
 assert.equal(batchTargets(page,ids,[]).length,2);assert.equal(batchTargets(page,[],[]),null);
});
test('serial commits preserve individual keys and advance only the readback revision',async()=>{
 const page=items(),targets=batchTargets(page,page.map(x=>x.product_id),['x']),storage=memory(),ctx=context(),shop=randomUUID(),keys=[];let concurrent=0;
 const counts=await applyBatchTags(targets,rev(1),()=>true,async(target,revision,dispatch)=>{
  assert.equal(++concurrent,1);assert.equal(revision,rev(keys.length+1));
  const record={operation:'product_tags',request_key:randomUUID(),resource_id:target.id,shop_id:shop,revision,version:target.version,file_digest:null,job_digest:null,parent_job_id:null,context:ctx};
  assert.equal(reserveV41Pending(storage,record),true);keys.push(record.request_key);dispatch();await Promise.resolve();
  const after=rev(keys.length+1),response={status:'COMMITTED',context:{...ctx,shop_id:shop},data:{next_step:'READ_CURRENT_RESOURCE',receipt:{...record,before_revision:revision,after_revision:after,resource_version:target.version+1}}};
  const resource={status:'OK',context:{...ctx,shop_id:shop},data:{snapshot:{data_revision:after},product:{product_id:target.id,version:target.version+1,tags:['x']}}};
  assert.equal(finishV41Pending(storage,{context:ctx,data:{shops:[{shop_id:shop,grants:['operator']}]}},response,resource),true);
  concurrent--;return {status:'success',revision:after};
 },()=>{});
 assert.deepEqual(counts,{success:2,rejected:0,pending:0,unsent:0});assert.equal(new Set(keys).size,2);
});
for(const status of ['unknown','rejected'])test(status+' stops, keeps the reserved key and never resumes from lookup',async()=>{
 const targets=batchTargets(items(),[],[]);assert.equal(targets,null);
 const page=items(),storage=memory(),ctx=context();let calls=0;
 const counts=await applyBatchTags(batchTargets(page,page.map(x=>x.product_id),[]),rev(1),()=>true,async(target,revision,dispatch)=>{
  calls++;assert.equal(reserveV41Pending(storage,{operation:'product_tags',request_key:randomUUID(),resource_id:target.id,shop_id:randomUUID(),revision,version:target.version,file_digest:null,job_digest:null,parent_job_id:null,context:ctx}),true);dispatch();return {status};
 },()=>{});
 assert.equal(calls,1);assert.equal(counts.unsent,1);assert.equal(counts[status==='unknown'?'pending':'rejected'],1);assert.equal(loadV41Pending(storage).state,'pending');await Promise.resolve();assert.equal(calls,1);
});
test('cancel during dispatched request suppresses late publication and remaining sends',async()=>{
 const page=items();let active=true,calls=0;const published=[];
 const counts=await applyBatchTags(batchTargets(page,page.map(x=>x.product_id),[]),rev(1),()=>active,async(target,revision,dispatch)=>{calls++;dispatch();active=false;await Promise.resolve();return {status:'unknown'};},x=>published.push(x));
 assert.equal(calls,1);assert.equal(counts.unsent,1);assert.equal(published.at(-1).pending,1);assert.equal(published.length,2);
});
test('pre-dispatch storage failure, cancellation or stale pre-read leaves all items unsent',async()=>{
 const page=items();let calls=0;
 const counts=await applyBatchTags(batchTargets(page,page.map(x=>x.product_id),[]),rev(1),()=>true,async()=>{calls++;throw new Error('STORAGE_BLOCKED_OR_STALE');},()=>{});
 assert.equal(calls,1);assert.deepEqual(counts,{success:0,rejected:0,pending:0,unsent:2});
});
test('malformed success cannot advance revision or start the next item',async()=>{
 const page=items();let calls=0;
 const counts=await applyBatchTags(batchTargets(page,page.map(x=>x.product_id),[]),rev(1),()=>true,async(t,r,dispatch)=>{calls++;dispatch();return {status:'success',revision:'bad'};},()=>{});
 assert.equal(calls,1);assert.equal(counts.pending,1);assert.equal(counts.unsent,1);
});

test('CAS pre-read and exact tag readback reject stale revisions, versions and altered tag sets',()=>{
 const target={id:randomUUID(),version:3},data={product:{product_id:target.id,version:3},snapshot:{data_revision:rev(1)}};
 assert.equal(matchesBatchRead(data,target,rev(1)),true);assert.equal(matchesBatchRead(data,target,rev(2)),false);assert.equal(matchesBatchRead(data,{...target,version:4},rev(1)),false);assert.equal(matchesBatchRead(data,{...target,id:randomUUID()},rev(1)),false);
 assert.equal(matchesBatchTags(['b','a'],['a','b']),true);assert.equal(matchesBatchTags([],[]),true);assert.equal(matchesBatchTags(['a','a'],['a','a']),false);assert.equal(matchesBatchTags(['a'],['a','b']),false);assert.equal(matchesBatchTags(undefined,[]),false);
});
