import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID,createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {encodeImportFile,validMapping,validPreview} from '../lib/v41-import.mjs';
const digest='a'.repeat(64),now='2026-11-03T00:00:00Z',expires='2026-11-03T00:10:00Z';
const mapping={sku:'sku',title:'title',price:'price',currency:'currency',tags:null};
function preview(){return {job:{import_job_id:randomUUID(),version:1,parent_job_id:null,job_digest:'b'.repeat(64),data_revision:'a'.repeat(64),parser_version:'v41-parser-1',import_schema_version:'v41-import-1',expires_at:expires},state:'READY',file_digest:digest,mapping,headers:['sku','title','price','currency'],sample:[],issues:[],row_count:1,issue_count:0,confirmable:true};}
test('mapping only uses distinct server-provided headers',()=>{
 assert.equal(validMapping(mapping,['sku','title','price','currency']),true);
 assert.equal(validMapping({...mapping,title:'sku'},['sku','title','price','currency']),false);
 assert.equal(validMapping({...mapping,tags:'other'},['sku','title','price','currency']),false);
});
test('preview checks original file, lineage, expiry and ready invariants',()=>{
 const p=preview();assert.equal(validPreview(p,digest,null,now,digest),true);
 assert.equal(validPreview({...p,file_digest:'c'.repeat(64)},digest,null,now,digest),false);
 assert.equal(validPreview({...p,issue_count:1},digest,null,now,digest),false);
 assert.equal(validPreview({...p,job:{...p.job,data_revision:'f'.repeat(64)}},digest,null,now,digest),false);
 assert.equal(validPreview({...p,job:{...p.job,parser_version:'other'}},digest,null,now,digest),false);
 assert.equal(validPreview({...p,job:{...p.job,import_schema_version:'other'}},digest,null,now,digest),false);
 assert.equal(validPreview({...p,job:{...p.job,expires_at:now}},digest,null,now,digest),false);
 const committed={...p,state:'COMMITTED',confirmable:false,job:{...p.job,expires_at:now}};
 assert.equal(validPreview(committed,digest,null,now,digest),false);
 assert.equal(validPreview(committed,digest,null,now,digest,true),true);
 assert.equal(validPreview({...committed,state:'READY',confirmable:true},digest,null,now,digest,true),false);
 const child={...p,job:{...p.job,import_job_id:randomUUID(),parent_job_id:p.job.import_job_id,version:2}};
 assert.equal(validPreview(child,digest,p.job,now,digest),true);
 assert.equal(validPreview({...child,job:{...child.job,parent_job_id:null}},digest,p.job,now,digest),false);
});
test('reject unsupported and oversized files before reading bytes',async()=>{
 let reads=0;const bad={name:'bad.xlsm',size:10,arrayBuffer(){reads++;}};
 await assert.rejects(encodeImportFile(bad),/UNSUPPORTED_FILE/);await assert.rejects(encodeImportFile({...bad,name:'large.csv',size:2*1024*1024+1}),/INVALID_FILE/);assert.equal(reads,0);
 const good=new File(['sku,title\na,b\n'],'sample.csv');const result=await encodeImportFile(good);assert.equal(result.format,'csv');assert.equal(result.file_digest.length,64);assert.equal(atob(result.file_base64),'sku,title\na,b\n');
});

test('CSV and XLSX bytes survive encoding with an exact digest',async()=>{
 const xlsx=await readFile(new URL('./fixtures/sample.xlsx',import.meta.url));
 for(const [name,bytes] of [['sample.csv',Buffer.from('sku,title,price,currency\nSKU-1,Demo,12,TWD\n')],['sample.xlsx',xlsx]]){
  const output=await encodeImportFile(new File([bytes],name));
  assert.equal(output.format,name.endsWith('.xlsx')?'xlsx':'csv');
  assert.deepEqual(Buffer.from(output.file_base64,'base64'),bytes);
  assert.equal(output.file_digest,createHash('sha256').update(bytes).digest('hex'));
 }
});
