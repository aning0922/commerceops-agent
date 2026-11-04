import test from 'node:test';
import assert from 'node:assert/strict';
import {orderTimeline} from '../lib/v41-order-timeline.mjs';
test('order timeline uses only known timestamps and keeps refund settlement unknown',()=>{
 const order={created_at:'2026-11-01T00:00:00Z',paid_at:null,refunds:[{refund_id:'r',occurred_at:'2026-11-03T00:00:00Z',amount:'12',currency:'TWD'}]};
 const events=orderTimeline(order);assert.deepEqual(events.map(e=>e.key),['created','refund:r']);assert.match(events[1].label,/到账状态未知/);
 assert.equal(orderTimeline({...order,paid_at:'2026-11-02T00:00:00Z'}).map(e=>e.key).join(','),'created,paid,refund:r');
});
