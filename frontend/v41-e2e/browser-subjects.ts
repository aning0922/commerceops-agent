import {constants,closeSync,fstatSync,fsyncSync,lstatSync,openSync,readFileSync,realpathSync,writeSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {createHash} from 'node:crypto';

export type BrowserCase={directory:string;source_sha:string;source_tree:string;scenario:'shell_navigation';api_port:number;web_port:number;uid:number;starts_at:string;deadline:string;parent_deadline:string;project:string};
export type SubjectContext={tenant_id:string;organization_id:string;principal_id:string;reset_epoch:number;auth_generation:number};
export type Operation='preview'|'product_tags'|'order_fulfillment'|'import_confirm';
export type State='ATTEMPT_STARTED'|'ACK_OK'|'ACK_COMMITTED'|'ACK_REJECTED'|'ACK_UNKNOWN'|'COMMITTED_READBACK'|'UNKNOWN_READBACK'|'SQL_ROLLBACK_VERIFIED';
export type RequestWitness={method:'POST';path:string;body:Record<string,unknown>};
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const states=new Set<State>(['ATTEMPT_STARTED','ACK_OK','ACK_COMMITTED','ACK_REJECTED','ACK_UNKNOWN','COMMITTED_READBACK','UNKNOWN_READBACK','SQL_ROLLBACK_VERIFIED']);
const base=['shop_id','request_key','expected_epoch','expected_generation','expected_data_revision'];
const fields:Record<Operation,string[]>={
  preview:[...base,'format','filename','file_base64','mapping','mapping_version','parent_job_id'],
  product_tags:[...base,'expected_version','tags'],
  order_fulfillment:[...base,'expected_version','action'],
  import_confirm:[...base,'expected_job_version','expected_job_digest'],
};
function privateDirectory(path:string){
  const info=lstatSync(path);
  if(resolve(path)!==path||realpathSync(path)!==path||!info.isDirectory()||info.uid!==process.getuid?.()||(info.mode&0o777)!==0o700)throw new Error('Private canonical case directory required');
}
export function readBrowserCase():BrowserCase{
  const path=process.env.V41_CASE_FILE;
  if(!path||resolve(path)!==path||realpathSync(path)!==path)throw new Error('Explicit canonical V41_CASE_FILE required');
  const info=lstatSync(path);privateDirectory(dirname(path));
  if(!info.isFile()||(info.mode&0o777)!==0o600||info.uid!==process.getuid?.()||info.size>32768)throw new Error('Private bounded case file required');
  const c=JSON.parse(readFileSync(path,'utf8')) as BrowserCase;
  if(c.scenario!=='shell_navigation'||! /^[a-f0-9]{40}$/.test(c.source_sha)||! /^[a-f0-9]{40}$/.test(c.source_tree)||! /^v41qa_[a-z0-9_]{8,32}$/.test(c.project)||c.uid!==process.getuid?.()||join(c.directory,'case.json')!==path)throw new Error('Fixed Shell case required');
  const start=Date.parse(c.starts_at),end=Date.parse(c.deadline),parent=Date.parse(c.parent_deadline);
  if(![start,end,parent].every(Number.isFinite)||! /(?:Z|\+00:00)$/.test(c.starts_at)||! /(?:Z|\+00:00)$/.test(c.deadline)||! /(?:Z|\+00:00)$/.test(c.parent_deadline)||Date.now()<start||end-Date.now()<=180000||end>parent||end-start>1800000)throw new Error('Active Root window required');
  for(const p of [c.api_port,c.web_port])if(!Number.isInteger(p)||p<1024||p>65535)throw new Error('Explicit loopback ports required');
  if(c.api_port===c.web_port)throw new Error('Distinct ports required');
  return c;
}
function stable(value:unknown):string{
  if(value===null||typeof value==='string'||typeof value==='boolean')return JSON.stringify(value);
  if(typeof value==='number'&&Number.isSafeInteger(value))return JSON.stringify(value);
  if(Array.isArray(value))return '['+value.map(stable).join(',')+']';
  if(typeof value==='object'&&value!==null)return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stable((value as Record<string,unknown>)[k])).join(',')+'}';
  throw new Error('Finite JSON request required');
}
function scopeContext(c:SubjectContext):SubjectContext{
  for(const n of ['tenant_id','organization_id','principal_id'] as const)if(!uuid.test(c[n]))throw new Error('Actual UUID scope required');
  for(const n of ['reset_epoch','auth_generation'] as const)if(!Number.isSafeInteger(c[n])||c[n]<0)throw new Error('Actual scope counter required');
  return {tenant_id:c.tenant_id,organization_id:c.organization_id,principal_id:c.principal_id,reset_epoch:c.reset_epoch,auth_generation:c.auth_generation};
}
function witness(operation:Operation,key:string,shop:string,context:SubjectContext,request:RequestWitness){
  if(request.method!=='POST'||Object.keys(request).sort().join(',')!=='body,method,path')throw new Error('Fixed POST witness required');
  const patterns:Record<Operation,RegExp>={preview:/^\/api\/v4\/imports\/previews$/,product_tags:/^\/api\/v4\/products\/([a-f0-9-]{36})\/tags$/,order_fulfillment:/^\/api\/v4\/orders\/([a-f0-9-]{36})\/fulfillment$/,import_confirm:/^\/api\/v4\/imports\/([a-f0-9-]{36})\/confirm$/};
  const match=patterns[operation].exec(request.path);
  if(!match||(match[1]&&!uuid.test(match[1])))throw new Error('Fixed business path required');
  const body=request.body;
  if(!body||Array.isArray(body)||typeof body!=='object'||Object.keys(body).some(k=>!fields[operation].includes(k))||base.some(k=>!(k in body)))throw new Error('Strict business body fields required');
  if(body.shop_id!==shop||body.request_key!==key||body.expected_epoch!==context.reset_epoch||body.expected_generation!==context.auth_generation)throw new Error('Original body scope/key required');
  if(operation==='preview'&&body.mapping!==undefined&&body.mapping!==null){
    if(typeof body.mapping!=='object'||Array.isArray(body.mapping)||Object.keys(body.mapping).some(k=>!['sku','title','price','currency','tags'].includes(k)))throw new Error('Strict mapping required');
  }
  // Body values are synthetic test data. Headers, cookies and signing material are never accepted.
  const raw=stable(body);
  if(Buffer.byteLength(raw)>64000)throw new Error('Small synthetic body witness required');
  return {method:request.method,path:request.path,body:JSON.parse(raw),request_body_sha256:createHash('sha256').update(raw).digest('hex')};
}
export function subjectWriter(c:BrowserCase,label:'shell'|'business'){
  privateDirectory(c.directory);
  if(!['shell','business'].includes(label))throw new Error('Fixed journal label required');
  const path=join(c.directory,`browser-${label}.subjects.private.jsonl`);
  const initial=openSync(path,'wx',0o600);const identity=fstatSync(initial);fsyncSync(initial);closeSync(initial);
  let events=0;
  function append(context:SubjectContext,shop:string,operation:Operation|null,key:string|null,state:State,request?:RequestWitness){
    const scope=scopeContext(context);
    if(!uuid.test(shop)||!states.has(state)||(operation!==null&&!Object.hasOwn(fields,operation))||(key!==null&&!uuid.test(key)))throw new Error('Fixed original operation required');
    if((operation===null)!==(key===null)||(!operation&&request)||state==='ATTEMPT_STARTED'&&operation!==null&&!request)throw new Error('Write-ahead original POST required');
    const original=operation&&request?witness(operation,key!,shop,scope,request):null;
    const raw=Buffer.from(JSON.stringify({schema:'v41-browser-subject-event-1',source_sha:c.source_sha,source_tree:c.source_tree,context:scope,shop_id:shop,operation,request_key:key,state,request:original})+'\n');
    const fd=openSync(path,constants.O_WRONLY|constants.O_APPEND|constants.O_NOFOLLOW);
    try{
      const info=fstatSync(fd);
      if(!info.isFile()||info.ino!==identity.ino||info.dev!==identity.dev||info.uid!==process.getuid?.()||(info.mode&0o777)!==0o600||info.size+raw.length>512000||events>=1000)throw new Error('Private bounded original journal required');
      let offset=0;while(offset<raw.length)offset+=writeSync(fd,raw,offset,raw.length-offset);
      fsyncSync(fd);events++;
    }finally{closeSync(fd);}
  }
  return {
    scope:(context:SubjectContext,shop:string)=>append(context,shop,null,null,'ATTEMPT_STARTED'),
    operation:(context:SubjectContext,shop:string,operation:Operation,key:string,state:State,request?:RequestWitness)=>append(context,shop,operation,key,state,request),
  };
}
