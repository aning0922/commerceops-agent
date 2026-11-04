import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {encodeImportFile,validMapping,validPreview} from '../lib/v41-import.mjs';
const digest='a'.repeat(64),now='2026-11-03T00:00:00Z',expires='2026-11-03T00:10:00Z';
const mapping={sku:'sku',title:'title',price:'price',currency:'currency',tags:null};
function preview(){return {job:{import_job_id:randomUUID(),version:1,parent_job_id:null,job_digest:'b'.repeat(64),expires_at:expires},state:'READY',file_digest:digest,mapping,headers:['sku','title','price','currency'],sample:[],issues:[],row_count:1,issue_count:0,confirmable:true};}
test('mapping only uses distinct server-provided headers',()=>{
 assert.equal(validMapping(mapping,['sku','title','price','currency']),true);
 assert.equal(validMapping({...mapping,title:'sku'},['sku','title','price','currency']),false);
 assert.equal(validMapping({...mapping,tags:'other'},['sku','title','price','currency']),false);
});
test('preview checks original file, lineage, expiry and ready invariants',()=>{
 const p=preview();assert.equal(validPreview(p,digest,null,now),true);
 assert.equal(validPreview({...p,file_digest:'c'.repeat(64)},digest,null,now),false);
 assert.equal(validPreview({...p,issue_count:1},digest,null,now),false);
 assert.equal(validPreview({...p,job:{...p.job,expires_at:now}},digest,null,now),false);
 const child={...p,job:{...p.job,import_job_id:randomUUID(),parent_job_id:p.job.import_job_id,version:2}};
 assert.equal(validPreview(child,digest,p.job,now),true);
 assert.equal(validPreview({...child,job:{...child.job,parent_job_id:null}},digest,p.job,now),false);
});
test('reject unsupported and oversized files before reading bytes',async()=>{
 let reads=0;const bad={name:'bad.xlsm',size:10,arrayBuffer(){reads++;}};
 await assert.rejects(encodeImportFile(bad),/UNSUPPORTED_FILE/);await assert.rejects(encodeImportFile({...bad,name:'large.csv',size:2*1024*1024+1}),/INVALID_FILE/);assert.equal(reads,0);
 const good=new File(['sku,title\na,b\n'],'sample.csv');const result=await encodeImportFile(good);assert.equal(result.format,'csv');assert.equal(result.file_digest.length,64);assert.equal(atob(result.file_base64),'sku,title\na,b\n');
});
