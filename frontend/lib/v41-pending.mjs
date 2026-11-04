import {isSessionContext,sameIdentityContext} from './v4-context.mjs';

const slot='commerceops-v41-pending';
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const operations=['product_tags','order_fulfillment','import_confirm','import_preview'];
const digest=/^[a-f0-9]{64}$/;
function valid(record) {
  return !!record && typeof record==='object' && !Array.isArray(record) &&
    Object.keys(record).sort().join(',')==='context,operation,request_key,resource_id,revision,shop_id,version' &&
    operations.includes(record.operation) && uuid.test(record.request_key) && uuid.test(record.shop_id) &&
    (record.resource_id===null || uuid.test(record.resource_id)) &&
    (record.operation==='import_preview' ? record.resource_id===null : record.resource_id!==null) &&
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
export function finishV41Pending(storage,session,response,resource) {
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
    receipt.resource_version!==value.version+1 || !digest.test(receipt.after_revision)) return false;
  if (!sameIdentityContext(value.context,resource?.context) || resource.context.shop_id!==value.shop_id || resource.status!=='OK' || resource.data?.snapshot?.data_revision!==receipt.after_revision) return false;
  const item=value.operation==='product_tags'?resource.data?.product:value.operation==='order_fulfillment'?resource.data?.order:null;
  const actualId=value.operation==='product_tags'?item?.product_id:item?.order_id;
  const actualVersion=value.operation==='product_tags'?item?.version:item?.fulfillment_version;
  if(!item || actualId!==value.resource_id || actualVersion!==receipt.resource_version) return false;
  try {storage.removeItem(slot);return storage.getItem(slot)===null;} catch {return false;}
}
