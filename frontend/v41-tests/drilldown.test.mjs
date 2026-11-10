import test from 'node:test';
import assert from 'node:assert/strict';
import {isSafeDrilldown} from '../lib/v41-drilldown.mjs';
const source={data_mode:'demo_fixture',fixture_digest:'a',baseline_snapshot_at:'t',uploads:[]};
const snapshot={data_revision:'r',source};
const itemSource={...source,import_job_id:null,import_row:null,file_digest:null};
const product={product_id:'p',source:itemSource,tags:[],skus:[{available_units:1,stock_reason:null}]};
const page=items=>({snapshot,items,total:items.length,next_cursor:null});
test('drilldown binds kind, current revision and dataset source',()=>{
 const dashboard={snapshot};assert.equal(isSafeDrilldown(page([product]),dashboard,'product_count'),true);
 assert.equal(isSafeDrilldown(page([product]),dashboard,'paid_order_count'),false);
 assert.equal(isSafeDrilldown({...page([product]),snapshot:{...snapshot,data_revision:'other'}},dashboard,'product_count'),false);
 assert.equal(isSafeDrilldown({...page([product]),snapshot:{...snapshot,source:{...source,fixture_digest:'other'}}},dashboard,'product_count'),false);
});
test('refund references require distinct refunds and their order ids',()=>{
 const refund={refund_id:'r1',order_id:'o1'};assert.equal(isSafeDrilldown(page([refund]),{snapshot},'refund_event_amount'),true);
 assert.equal(isSafeDrilldown(page([{refund_id:'r1'}]),{snapshot},'refund_event_amount'),false);
 assert.equal(isSafeDrilldown(page([refund,refund]),{snapshot},'refund_event_amount'),false);
});
