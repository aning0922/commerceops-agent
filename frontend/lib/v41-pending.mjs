import {isSessionContext,sameIdentityContext} from './v4-context.mjs';
import {validPreview} from './v41-import.mjs';
import {isSafeDataset} from './v41-dashboard.mjs';

const slot='commerceops-v41-pending', previewSlot='commerceops-v41-preview';
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const operations=['product_tags','order_fulfillment','import_confirm','import_preview'];
const digest=/^[a-f0-9]{64}$/;
function valid(record) {
  return !!record && typeof record==='object' && !Array.isArray(record) &&
    ['context,file_digest,job_digest,operation,parent_job_id,request_key,resource_id,revision,shop_id,version','context,file_digest,operation,parent_job_id,request_key,resource_id,revision,shop_id,version'].includes(Object.keys(record).sort().join(',')) &&
    operations.includes(record.operation) && uuid.test(record.request_key) && uuid.test(record.shop_id) &&
    (record.resource_id===null || uuid.test(record.resource_id)) &&
    (record.operation==='import_preview' ? record.resource_id===null && digest.test(record.file_digest) && record.job_digest==null && (record.parent_job_id===null || uuid.test(record.parent_job_id)) : record.operation==='import_confirm' ? record.resource_id!==null && digest.test(record.file_digest) && digest.test(record.job_digest) && record.parent_job_id===null : record.resource_id!==null && record.file_digest===null && record.job_digest==null && record.parent_job_id===null) &&
    digest.test(record.revision) && Number.isSafeInteger(record.version) && record.version>=0 &&
    isSessionContext(record.context);
}
/** Corrupt or unavailable storage is blocked, never interpreted as no pending operation. */
export function loadV41Pending(storage) {
  try {
    const raw=storage.getItem(slot);if(raw===null)return {state:'empty'};
    const value=JSON.parse(raw);return valid(value)?{state:'pending',value}:{state:'blocked'};
  } catch {return {state:'blocked'};}
}
/** Reserve before dispatch; do not persist CSRF, cookie, file bytes, request body or model data. */
export function reserveV41Pending(storage,value) {
  if(!valid(value)||loadV41Pending(storage).state!=='empty')return false;
  try {
    const serialized=JSON.stringify(value);storage.setItem(slot,serialized);
    return storage.getItem(slot)===serialized && loadV41Pending(storage).state==='pending';
  } catch {return false;}
}
/** Validated receipt, fresh identity and matching readback are required; UNKNOWN never clears. */
export function finishV41Pending(storage,session,response,resource,dataset) {
  const pending=loadV41Pending(storage);if(pending.state!=='pending')return false;
  const value=pending.value,receipt=response?.data?.receipt,current=session?.context;
  const currentOperator=Array.isArray(session?.data?.shops) && session.data.shops.some(shop=>shop.shop_id===value.shop_id && Array.isArray(shop.grants) && shop.grants.includes('operator'));
  const lookup=Object.hasOwn(response?.data??{},'status');
  if(!currentOperator || !isSessionContext(current) || !sameIdentityContext(value.context,current) ||
    !sameIdentityContext(value.context,response?.context) || response.context.shop_id!==value.shop_id ||
    !['OK','COMMITTED'].includes(response.status) || !receipt ||
    (lookup ? response.data.status!=='COMMITTED' || response.data.operation!==value.operation || response.data.request_key!==value.request_key : response.data.next_step!=='READ_CURRENT_RESOURCE') ||
    receipt.operation!==value.operation || receipt.request_key!==value.request_key ||
    receipt.resource_id!==value.resource_id || receipt.before_revision!==value.revision ||
    (value.operation!=='import_confirm' && receipt.resource_version!==value.version+1) || !digest.test(receipt.after_revision)) return false;
  if (!sameIdentityContext(value.context,resource?.context) || resource.context.shop_id!==value.shop_id || resource.status!=='OK') return false;
  if(value.operation==='import_confirm') {
    const ref=loadV41Preview(storage),job=resource.data?.job,source=dataset?.data?.snapshot?.source;
    if(ref.state!=='ready' || ref.value.shop_id!==value.shop_id || !sameIdentityContext(ref.value.context,value.context) ||
      ref.value.file_digest!==value.file_digest || ref.value.job.import_job_id!==value.resource_id || ref.value.job.job_digest!==value.job_digest ||
      !job || job.import_job_id!==value.resource_id || job.job_digest!==value.job_digest || job.data_revision!==value.revision || job.version!==value.version ||
      resource.data.state!=='COMMITTED' || resource.data.file_digest!==value.file_digest ||
      !validPreview(resource.data,value.file_digest,job.parent_job_id?{import_job_id:job.parent_job_id,version:job.version-1}:null,resource.server_time,value.revision,true) ||
      !sameIdentityContext(value.context,dataset?.context) || dataset.context.shop_id!==value.shop_id || dataset.status!=='OK' ||
      dataset.data?.snapshot?.data_revision!==receipt.after_revision || !isSafeDataset(source) ||
      source.uploads.filter(row=>row.import_job_id===value.resource_id && row.file_digest===value.file_digest).length!==resource.data.row_count || resource.data.row_count<1) return false;
  } else {
    if(resource.data?.snapshot?.data_revision!==receipt.after_revision)return false;
    const item=value.operation==='product_tags'?resource.data?.product:value.operation==='order_fulfillment'?resource.data?.order:null;
    const actualId=value.operation==='product_tags'?item?.product_id:item?.order_id;
    const actualVersion=value.operation==='product_tags'?item?.version:item?.fulfillment_version;
    if(!item || actualId!==value.resource_id || actualVersion!==receipt.resource_version) return false;
  }
  try {storage.removeItem(slot);return storage.getItem(slot)===null;} catch {return false;}
}

function validPreviewRef(value) {
  const job=value?.job;
  return !!value && Object.keys(value).sort().join(',')==='context,file_digest,job,shop_id' &&
    isSessionContext(value.context) && uuid.test(value.shop_id) && digest.test(value.file_digest) &&
    !!job && Object.keys(job).sort().join(',')==='data_revision,expires_at,import_job_id,import_schema_version,job_digest,parent_job_id,parser_version,version' &&
    uuid.test(job.import_job_id) && (job.parent_job_id===null || uuid.test(job.parent_job_id)) &&
    digest.test(job.job_digest) && digest.test(job.data_revision) && job.parser_version==='v41-parser-1' && job.import_schema_version==='v41-import-1' && Number.isInteger(job.version) && job.version>=1 && job.version<=5 &&
    typeof job.expires_at==='string' && Number.isFinite(Date.parse(job.expires_at));
}
export function loadV41Preview(storage) {
  try {const raw=storage.getItem(previewSlot);if(raw===null)return {state:'empty'};const value=JSON.parse(raw);return validPreviewRef(value)?{state:'ready',value}:{state:'blocked'};}
  catch{return {state:'blocked'};}
}
/** Store only the verified job reference; pending remains if saving or removal fails. */
export function finishV41Preview(storage,session,response) {
  const pending=loadV41Pending(storage);if(pending.state!=='pending'||pending.value.operation!=='import_preview')return false;
  const record=pending.value,current=session?.context,preview=response?.data;
  const operator=Array.isArray(session?.data?.shops) && session.data.shops.some(shop=>shop.shop_id===record.shop_id && Array.isArray(shop.grants) && shop.grants.includes('operator'));
  const parent=record.parent_job_id?{import_job_id:record.parent_job_id,version:record.version}:null;
  if(!operator || !isSessionContext(current) || !sameIdentityContext(record.context,current) ||
    !sameIdentityContext(record.context,response?.context) || response.context.shop_id!==record.shop_id ||
    !['OK','COMMITTED'].includes(response.status) || !validPreview(preview,record.file_digest,parent,response.server_time,record.revision))return false;
  const previous=loadV41Preview(storage);
  if(previous.state==='blocked')return false;
  const reference={context:record.context,shop_id:record.shop_id,file_digest:record.file_digest,job:preview.job};
  if(!validPreviewRef(reference))return false;
  if(previous.state==='ready') {
    const same=JSON.stringify(previous.value)===JSON.stringify(reference);
    const parentMatch=previous.value.job.import_job_id===record.parent_job_id && previous.value.job.version===record.version && previous.value.job.data_revision===record.revision && previous.value.file_digest===record.file_digest && previous.value.shop_id===record.shop_id && sameIdentityContext(previous.value.context,record.context);
    if(!same&&!parentMatch)return false;
  }
  if(previous.state==='empty' && parent)return false;
  try {const encoded=JSON.stringify(reference);storage.setItem(previewSlot,encoded);if(storage.getItem(previewSlot)!==encoded)return false;storage.removeItem(slot);return storage.getItem(slot)===null;}catch{return false;}
}
/** Explicitly discard only the local preview reference; this does not cancel the server job. */
export function discardV41Preview(storage,session,shopId) {
  const pending=loadV41Pending(storage),ref=loadV41Preview(storage);
  if(pending.state!=='empty'||ref.state!=='ready'||ref.value.shop_id!==shopId||
    !isSessionContext(session?.context)||!sameIdentityContext(ref.value.context,session.context)||
    !Array.isArray(session?.data?.shops)||!session.data.shops.some(shop=>shop.shop_id===shopId&&Array.isArray(shop.grants)&&shop.grants.includes('operator')))return false;
  try{storage.removeItem(previewSlot);return storage.getItem(previewSlot)===null;}catch{return false;}
}
