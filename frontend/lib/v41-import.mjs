const maximumBytes=2*1024*1024;
const digest=/^[a-f0-9]{64}$/;
const columns=['sku','title','price','currency','tags'];

/** Files stay in memory only. Server remains responsible for format, content and security validation. */
export async function encodeImportFile(file) {
  if(!file || typeof file.name!=='string' || file.name.length<1 || file.name.length>128 || /[\u0000-\u001f\u007f]/.test(file.name) || !Number.isSafeInteger(file.size) || file.size<=0 || file.size>maximumBytes) throw new Error('INVALID_FILE');
  const extension=file.name.toLowerCase().endsWith('.csv')?'csv':file.name.toLowerCase().endsWith('.xlsx')?'xlsx':null;
  if(!extension)throw new Error('UNSUPPORTED_FILE');
  const bytes=new Uint8Array(await file.arrayBuffer());if(bytes.byteLength!==file.size)throw new Error('FILE_CHANGED');
  const hash=new Uint8Array(await crypto.subtle.digest('SHA-256',bytes));
  const fileDigest=Array.from(hash,value=>value.toString(16).padStart(2,'0')).join('');
  let binary='';for(let offset=0;offset<bytes.length;offset+=16384)binary+=String.fromCharCode(...bytes.subarray(offset,offset+16384));
  return {format:extension,filename:file.name,file_base64:btoa(binary),file_digest:fileDigest};
}
export function validMapping(mapping,headers) {
  if(!mapping || typeof mapping!=='object' || Array.isArray(mapping) || !Array.isArray(headers) || Object.keys(mapping).some(key=>!columns.includes(key)))return false;
  const required=['sku','title','price','currency'];
  if(required.some(key=>typeof mapping[key]!=='string'||!headers.includes(mapping[key])))return false;
  if(mapping.tags!==null && (typeof mapping.tags!=='string'||!headers.includes(mapping.tags)))return false;
  const values=columns.map(key=>mapping[key]).filter(value=>value!==null);
  return values.length===new Set(values).size;
}
/** The caller must schema-validate the complete envelope and its current context first. */
export function validPreview(preview,expectedDigest,parentJob,serverTime) {
  if(!preview || !preview.job || !digest.test(expectedDigest) || preview.file_digest!==expectedDigest ||
    !digest.test(preview.job.job_digest) || !Number.isInteger(preview.job.version) ||
    preview.job.version!==(parentJob?parentJob.version+1:1) || preview.job.parent_job_id!==(parentJob?.import_job_id??null) ||
    !Number.isFinite(Date.parse(serverTime)) || !Number.isFinite(Date.parse(preview.job.expires_at)) || Date.parse(preview.job.expires_at)<=Date.parse(serverTime) ||
    !Array.isArray(preview.headers) || !Array.isArray(preview.sample) || !Array.isArray(preview.issues) ||
    !Number.isSafeInteger(preview.row_count) || !Number.isSafeInteger(preview.issue_count) || preview.issue_count<preview.issues.length ||
    preview.confirmable!==(preview.state==='READY')) return false;
  if(preview.mapping!==null && !validMapping(preview.mapping,preview.headers))return false;
  if(preview.confirmable && (preview.mapping===null || preview.issue_count!==0 || preview.row_count===0))return false;
  return true;
}
