import {isSafeDataset} from './v41-dashboard.mjs';
import {isSafeCatalog} from './v41-catalog.mjs';
const types={created_order_count:'order',paid_order_count:'order',paid_order_amount:'order',average_paid_order_amount:'order',refund_event_count:'refund',refund_event_amount:'refund',product_count:'product',low_stock_count:'product'};
function sourceKey(source){return JSON.stringify([source.data_mode,source.evidence_mode,source.fixture_version,source.fixture_digest,source.baseline_snapshot_at,...source.uploads.map(row=>[row.import_job_id,row.import_row,row.file_digest,row.fixture_digest,row.baseline_snapshot_at].join(':')).sort()]);}
export function isSafeDrilldown(page,dashboard,metric) {
 const type=types[metric],source=page?.snapshot?.source,base=dashboard?.snapshot?.source;
 if(!type||!isSafeDataset(source)||!isSafeDataset(base)||page.snapshot.data_revision!==dashboard.snapshot.data_revision||sourceKey(source)!==sourceKey(base)||!Array.isArray(page.items)||!Number.isSafeInteger(page.total)||page.total<page.items.length)return false;
 if(type!=='refund')return isSafeCatalog(page,type);
 return page.items.every(item=>typeof item.refund_id==='string'&&typeof item.order_id==='string')&&new Set(page.items.map(item=>item.refund_id)).size===page.items.length;
}
