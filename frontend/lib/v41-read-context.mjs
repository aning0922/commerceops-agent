import {isSafeDashboard,isSafeDataset} from './v41-dashboard.mjs';
import {isSafeDetail} from './v41-catalog.mjs';

export function isSafeReadContext(data,kind,id) {
  if(!data || data.model_mode!=='not_used' || data.kind!==kind || !isSafeDataset(data.snapshot?.source) || !Array.isArray(data.resource_ids) || new Set(data.resource_ids).size!==data.resource_ids.length || !Array.isArray(data.insights) || !Array.isArray(data.metrics)) return false;
  if(kind==='dashboard') return id===null && data.product===null && data.order===null && isSafeDashboard({snapshot:data.snapshot,metrics:data.metrics,trend:[],model_mode:data.model_mode});
  if(!['product','order'].includes(kind) || data.metrics.length || data.resource_ids.length!==1 || data.resource_ids[0]!==id || (kind==='product' ? data.order!==null : data.product!==null)) return false;
  return isSafeDetail(data,kind,id);
}
