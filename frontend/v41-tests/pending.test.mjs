import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {loadV41Pending,reserveV41Pending,finishV41Pending,finishV41Preview,loadV41Preview,scopedV41Storage} from '../lib/v41-pending.mjs';
function storage(){const m=new Map();return {get length(){return m.size;},key:i=>[...m.keys()][i]??null,getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};}
function fixture(){const id=()=>randomUUID(),context={tenant_id:id(),organization_id:id(),principal_id:id(),shop_id:null,reset_epoch:2,auth_generation:3,authorized_at:new Date().toISOString()};return {operation:'product_tags',request_key:id(),resource_id:id(),shop_id:id(),revision:'a'.repeat(64),version:0,file_digest:null,job_digest:null,parent_job_id:null,context};}
function resource(value){return {status:'OK',context:{...value.context,shop_id:value.shop_id},data:{snapshot:{data_revision:'b'.repeat(64)},product:{product_id:value.resource_id,version:value.version+1}}};}
function result(value){return {status:'COMMITTED',context:{...value.context,shop_id:value.shop_id},data:{next_step:'READ_CURRENT_RESOURCE',receipt:{operation:value.operation,request_key:value.request_key,resource_id:value.resource_id,before_revision:value.revision,after_revision:'b'.repeat(64),resource_version:value.version+1}}};}
test('reservation is exclusive, minimal, and unavailable/corrupt storage blocks',()=>{
 const s=storage(),value=fixture();assert.equal(reserveV41Pending(s,value),true);assert.equal(reserveV41Pending(s,fixture()),false);assert.equal(loadV41Pending(s).state,'pending');
 const corrupt=storage();corrupt.setItem('commerceops-v41-pending','{');assert.equal(loadV41Pending(corrupt).state,'blocked');assert.equal(reserveV41Pending(corrupt,value),false);
 const blocked={getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}};assert.equal(reserveV41Pending(blocked,value),false);
 assert.equal(reserveV41Pending(storage(),{...value,csrf:'no'}),false);
});
test('only matching committed receipt and fresh identity can remove original pending key',()=>{
 const s=storage(),value=fixture(),session={context:value.context,data:{shops:[{shop_id:value.shop_id,grants:['operator']}]}};assert.equal(reserveV41Pending(s,value),true);
 for(const altered of [{...result(value),status:'UNKNOWN'},{...result(value),context:{...result(value).context,shop_id:randomUUID()}},{...result(value),data:{receipt:{...result(value).data.receipt,resource_version:8}}}])assert.equal(finishV41Pending(s,session,altered,resource(value)),false);
 assert.equal(finishV41Pending(s,{...session,context:{...value.context,auth_generation:4}},result(value),resource(value)),false);
 assert.equal(finishV41Pending(s,{...session,data:{shops:[]}},result(value),resource(value)),false);
 assert.equal(finishV41Pending(s,session,{...result(value),data:{...result(value).data,status:'UNKNOWN'}},resource(value)),false);
 assert.equal(finishV41Pending(s,session,result(value),{...resource(value),data:{...resource(value).data,snapshot:{data_revision:'changed'}}}),false);
 assert.equal(loadV41Pending(s).state,'pending');assert.equal(finishV41Pending(s,session,result(value),resource(value)),true);assert.equal(loadV41Pending(s).state,'empty');
});

test('preview recovery saves a bound reference before clearing the original key',()=>{
 const s=storage(),value={...fixture(),operation:'import_preview',resource_id:null,file_digest:'c'.repeat(64),parent_job_id:null};
 const session={context:value.context,data:{shops:[{shop_id:value.shop_id,grants:['operator']}]}};
 const preview={job:{import_job_id:randomUUID(),version:1,parent_job_id:null,job_digest:'d'.repeat(64),data_revision:value.revision,parser_version:'v41-parser-1',import_schema_version:'v41-import-1',expires_at:'2026-11-03T00:10:00Z'},state:'DISCOVERED',file_digest:value.file_digest,mapping:null,headers:['sku'],sample:[],issues:[],row_count:1,issue_count:0,confirmable:false};
 const response={status:'OK',server_time:'2026-11-03T00:00:00Z',context:{...value.context,shop_id:value.shop_id},data:preview};
 assert.equal(reserveV41Pending(s,value),true);
 assert.equal(finishV41Preview(s,session,{...response,data:{...preview,file_digest:'e'.repeat(64)}}),false);
 assert.equal(loadV41Pending(s).state,'pending');assert.equal(finishV41Preview(s,session,response),true);
 assert.equal(loadV41Pending(s).state,'empty');assert.equal(loadV41Preview(s).value.job.import_job_id,preview.job.import_job_id);
});

test('preview reference survives a failed pending removal and can be reconciled without another POST',()=>{
 const s=storage(),value={...fixture(),operation:'import_preview',resource_id:null,file_digest:'c'.repeat(64),parent_job_id:null};
 const session={context:value.context,data:{shops:[{shop_id:value.shop_id,grants:['operator']}]}};
 const data={job:{import_job_id:randomUUID(),version:1,parent_job_id:null,job_digest:'d'.repeat(64),data_revision:value.revision,parser_version:'v41-parser-1',import_schema_version:'v41-import-1',expires_at:'2026-11-03T00:10:00Z'},state:'DISCOVERED',file_digest:value.file_digest,mapping:null,headers:['sku'],sample:[],issues:[],row_count:1,issue_count:0,confirmable:false};
 const response={status:'OK',server_time:'2026-11-03T00:00:00Z',context:{...value.context,shop_id:value.shop_id},data};
 assert.equal(reserveV41Pending(s,value),true);const remove=s.removeItem;s.removeItem=()=>{throw Error('unavailable');};
 assert.equal(finishV41Preview(s,session,response),false);assert.equal(loadV41Pending(s).state,'pending');assert.equal(loadV41Preview(s).state,'ready');
 s.removeItem=remove;assert.equal(finishV41Preview(s,session,response),true);assert.equal(loadV41Pending(s).state,'empty');
});
test('mapping creates a bound next preview and stale revision or lineage cannot replace the previous reference',()=>{
 const s=storage(),initial={...fixture(),operation:'import_preview',resource_id:null,file_digest:'c'.repeat(64),parent_job_id:null};
 const session={context:initial.context,data:{shops:[{shop_id:initial.shop_id,grants:['operator']}]}};
 const job={import_job_id:randomUUID(),version:1,parent_job_id:null,job_digest:'d'.repeat(64),data_revision:initial.revision,parser_version:'v41-parser-1',import_schema_version:'v41-import-1',expires_at:'2026-11-03T00:10:00Z'};
 const preview={job,state:'DISCOVERED',file_digest:initial.file_digest,mapping:null,headers:['sku','title','price','currency'],sample:[],issues:[],row_count:1,issue_count:0,confirmable:false};
 const response={status:'OK',server_time:'2026-11-03T00:00:00Z',context:{...initial.context,shop_id:initial.shop_id},data:preview};
 assert.equal(reserveV41Pending(s,initial),true);assert.equal(finishV41Preview(s,session,response),true);
 const next={...initial,request_key:randomUUID(),parent_job_id:job.import_job_id,version:1};assert.equal(reserveV41Pending(s,next),true);
 const nextJob={...job,import_job_id:randomUUID(),parent_job_id:job.import_job_id,version:2};
 const child={...preview,job:nextJob};
 assert.equal(finishV41Preview(s,session,{...response,data:{...child,job:{...nextJob,data_revision:'f'.repeat(64)}}}),false);
 assert.equal(loadV41Preview(s).value.job.import_job_id,job.import_job_id);
 assert.equal(finishV41Preview(s,session,{...response,data:{...child,job:{...nextJob,parent_job_id:randomUUID()}}}),false);
 assert.equal(finishV41Preview(s,session,{...response,data:child}),true);
 assert.equal(loadV41Preview(s).value.job.import_job_id,nextJob.import_job_id);assert.equal(loadV41Pending(s).state,'empty');
});
test('import confirmation needs bound job readback and matching imported provenance',()=>{
 const s=storage(),base={...fixture(),operation:'import_preview',resource_id:null,file_digest:'c'.repeat(64),parent_job_id:null};
 const session={context:base.context,data:{shops:[{shop_id:base.shop_id,grants:['operator']}]}};
 const job={import_job_id:randomUUID(),version:1,parent_job_id:null,job_digest:'d'.repeat(64),data_revision:base.revision,parser_version:'v41-parser-1',import_schema_version:'v41-import-1',expires_at:'2026-11-03T00:10:00Z'};
 const data={job,state:'READY',file_digest:base.file_digest,mapping:{sku:'sku',title:'title',price:'price',currency:'currency',tags:null},headers:['sku','title','price','currency'],sample:[],issues:[],row_count:1,issue_count:0,confirmable:true};
 const context={...base.context,shop_id:base.shop_id},preview={status:'OK',server_time:'2026-11-03T00:00:00Z',context,data};
 assert.equal(reserveV41Pending(s,base),true);assert.equal(finishV41Preview(s,session,preview),true);
 const confirm={...base,operation:'import_confirm',resource_id:job.import_job_id,job_digest:job.job_digest,version:job.version,request_key:randomUUID()};
 assert.equal(reserveV41Pending(s,confirm),true);
 const receipt={status:'COMMITTED',context,data:{next_step:'READ_CURRENT_RESOURCE',receipt:{operation:'import_confirm',request_key:confirm.request_key,resource_id:job.import_job_id,before_revision:confirm.revision,after_revision:'b'.repeat(64),resource_version:1}}};
 const readback={...preview,data:{...data,state:'COMMITTED',confirmable:false}};
 const sourceRow={data_mode:'demo_upload',fixture_digest:'source',baseline_snapshot_at:'time',import_job_id:job.import_job_id,import_row:2,file_digest:confirm.file_digest};
 const dataset={status:'OK',context,data:{snapshot:{data_revision:'b'.repeat(64),source:{data_mode:'demo_mixed',fixture_digest:'source',baseline_snapshot_at:'time',uploads:[sourceRow]}}}};
 assert.equal(finishV41Pending(s,session,{...receipt,data:{...receipt.data,receipt:{...receipt.data.receipt,resource_version:confirm.version+1}}},readback,dataset),false);
 assert.equal(finishV41Pending(s,session,receipt,readback,{...dataset,data:{snapshot:{...dataset.data.snapshot,data_revision:'f'.repeat(64)}}}),false);
 assert.equal(finishV41Pending(s,session,receipt,readback,{...dataset,data:{snapshot:{...dataset.data.snapshot,source:{...dataset.data.snapshot.source,uploads:[]}}}}),false);
 assert.equal(loadV41Pending(s).state,'pending');
 assert.equal(finishV41Pending(s,session,receipt,readback,dataset),true);assert.equal(loadV41Pending(s).state,'empty');
});

test('tenant scoped pending retains legacy UNKNOWN and isolates new verified tenant',()=>{
 const s=storage(),old=fixture(),other=fixture(),oldSession={context:old.context},newSession={context:other.context};
 assert.equal(reserveV41Pending(s,old),true);const original=s.getItem('commerceops-v41-pending');
 assert.equal(loadV41Pending(scopedV41Storage(s,oldSession)).value.request_key,old.request_key);
 const current=scopedV41Storage(s,newSession);assert.equal(loadV41Pending(current).state,'empty');
 assert.equal(reserveV41Pending(current,{...old,request_key:randomUUID()}),false);assert.equal(loadV41Pending(current).state,'empty');
 assert.equal(reserveV41Pending(current,other),true);assert.equal(s.getItem('commerceops-v41-pending'),original);
 assert.equal(loadV41Pending(scopedV41Storage(s,oldSession)).value.request_key,old.request_key);
 assert.equal(loadV41Pending(scopedV41Storage(s,newSession)).value.request_key,other.request_key);
 assert.equal(reserveV41Pending(current,{...old,request_key:randomUUID()}),false);
 assert.throws(()=>scopedV41Storage(s,{context:{...other.context,tenant_id:'invalid'}}),/SESSION_NOT_VALIDATED/);
});
test('corrupt, conflicting or wrong-owner scoped records block all new operations',()=>{
 const s=storage(),old=fixture(),fresh=fixture();assert.equal(reserveV41Pending(s,old),true);
 const oldKey=`commerceops-v41-pending:${old.context.tenant_id.toLowerCase()}`;s.setItem(oldKey,JSON.stringify(old));
 assert.throws(()=>scopedV41Storage(s,{context:old.context}),/STORAGE_BLOCKED/);
 s.setItem(oldKey,'{');assert.throws(()=>scopedV41Storage(s,{context:fresh.context}),/STORAGE_BLOCKED/);
 s.setItem(oldKey,JSON.stringify(fresh));assert.throws(()=>scopedV41Storage(s,{context:fresh.context}),/STORAGE_BLOCKED/);
});

test('old preview reference remains accessible only to its tenant',()=>{
 const s=storage(),old={...fixture(),operation:'import_preview',resource_id:null,file_digest:'c'.repeat(64),parent_job_id:null},other=fixture();
 const session={context:old.context,data:{shops:[{shop_id:old.shop_id,grants:['operator']}]}};
 const preview={job:{import_job_id:randomUUID(),version:1,parent_job_id:null,job_digest:'d'.repeat(64),data_revision:old.revision,parser_version:'v41-parser-1',import_schema_version:'v41-import-1',expires_at:'2026-11-03T00:10:00Z'},state:'DISCOVERED',file_digest:old.file_digest,mapping:null,headers:['sku'],sample:[],issues:[],row_count:1,issue_count:0,confirmable:false};
 assert.equal(reserveV41Pending(s,old),true);assert.equal(finishV41Preview(s,session,{status:'OK',server_time:'2026-11-03T00:00:00Z',context:{...old.context,shop_id:old.shop_id},data:preview}),true);
 const original=s.getItem('commerceops-v41-preview');assert.equal(loadV41Preview(scopedV41Storage(s,{context:other.context})).state,'empty');
 assert.equal(loadV41Preview(scopedV41Storage(s,session)).value.job.import_job_id,preview.job.import_job_id);assert.equal(s.getItem('commerceops-v41-preview'),original);
});
