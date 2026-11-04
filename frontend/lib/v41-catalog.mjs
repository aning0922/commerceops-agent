import {isSafeDataset} from './v41-dashboard.mjs';

// Schema validates fields; these checks preserve source identity and page-level invariants.
export function isSafeCatalog(page, kind) {
  const dataset=page?.snapshot?.source;
  if (!isSafeDataset(dataset) || !Array.isArray(page?.items) || !['product','order'].includes(kind)) return false;
  const seen=new Set();
  for (const item of page.items) {
    const id=kind==='product'?item.product_id:item.order_id;
    const source=item.source;
    if(!id || seen.has(id) || !source || source.fixture_digest!==dataset.fixture_digest || source.baseline_snapshot_at!==dataset.baseline_snapshot_at) return false;
    seen.add(id);
    if(source.data_mode==='demo_upload') {
      if (!dataset.uploads.some(row=>row.import_job_id===source.import_job_id && row.import_row===source.import_row && row.file_digest===source.file_digest)) return false;
    } else if(source.data_mode!=='demo_fixture' || source.import_job_id!==null || source.import_row!=null || source.file_digest!=null) return false;
    if(kind==='product') {
      if(!Array.isArray(item.tags) || new Set(item.tags).size!==item.tags.length || item.tags.some(tag=>tag.trim()!==tag)) return false;
      if(!Array.isArray(item.skus) || item.skus.some(sku=>(sku.available_units===null)!==(sku.stock_reason!==null))) return false;
    } else if ((item.paid_at===null)!==(item.payment_status==='payment_timestamp_unknown')) return false;
  }
  return Number.isSafeInteger(page.total) && page.total>=page.items.length;
}
