import test from 'node:test';
import assert from 'node:assert/strict';
import {isSafeCatalog} from '../lib/v41-catalog.mjs';
function page(){const source={data_mode:'demo_fixture',fixture_digest:'a',baseline_snapshot_at:'t',import_job_id:null,import_row:null,file_digest:null};return {snapshot:{source:{...source,uploads:[]}},items:[{product_id:'p',source,tags:['hot'],skus:[{available_units:null,stock_reason:'UNKNOWN_STOCK'}]}],total:1};}
test('product results preserve source, unique identifiers, tag and stock invariants',()=>{
 const value=page();assert.equal(isSafeCatalog(value,'product'),true);
 assert.equal(isSafeCatalog({...value,items:[value.items[0],value.items[0]],total:2},'product'),false);
 assert.equal(isSafeCatalog({...value,items:[{...value.items[0],tags:['hot','hot']}]},'product'),false);
 assert.equal(isSafeCatalog({...value,items:[{...value.items[0],source:{...value.items[0].source,fixture_digest:'other'}}]},'product'),false);
 assert.equal(isSafeCatalog({...value,items:[{...value.items[0],skus:[{available_units:1,stock_reason:'UNKNOWN_STOCK'}]}]},'product'),false);
});
test('uploaded rows require matching dataset provenance and payments retain unknown',()=>{
 const value=page(),source={...value.items[0].source,data_mode:'demo_upload',import_job_id:'job',import_row:2,file_digest:'hash'};
 value.snapshot.source={...value.snapshot.source,data_mode:'demo_mixed',uploads:[source]};value.items[0].source=source;
 assert.equal(isSafeCatalog(value,'product'),true);
 assert.equal(isSafeCatalog({...value,items:[{...value.items[0],source:{...source,file_digest:'wrong'}}]},'product'),false);
 const order={order_id:'o',source,paid_at:null,payment_status:'payment_timestamp_unknown'};
 assert.equal(isSafeCatalog({...value,items:[order]},'order'),true);
 assert.equal(isSafeCatalog({...value,items:[{...order,payment_status:'payment_recorded'}]},'order'),false);
});
test('detail must match the requested object and its dataset provenance',async()=>{
 const {isSafeDetail}=await import('../lib/v41-catalog.mjs');
 const value=page(),detail={snapshot:value.snapshot,product:value.items[0]};
 assert.equal(isSafeDetail(detail,'product','p'),true);
 assert.equal(isSafeDetail(detail,'product','different'),false);
 assert.equal(isSafeDetail({...detail,product:{...detail.product,source:{...detail.product.source,fixture_digest:'other'}}},'product','p'),false);
});
