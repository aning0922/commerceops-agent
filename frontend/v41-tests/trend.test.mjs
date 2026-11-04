import test from 'node:test';
import assert from 'node:assert/strict';
import {trendPoints} from '../lib/v41-trend.mjs';
const day=(date,value,currency='TWD',completeness='COMPLETE')=>({day:date,metrics:[{metric:'paid_order_amount',value,currency,completeness}]});
test('trend plots complete same-currency observations and retains original values',()=>{
 const points=trendPoints([day('2026-10-01','10'),day('2026-10-02','20')],'paid_order_amount');
 assert.deepEqual(points.map(p=>p.value),['10','20']);assert.equal(points[0].y,100);assert.equal(points[1].y,20);
});
test('trend avoids inventing lines across missing, partial or mixed-currency data',()=>{
 assert.deepEqual(trendPoints([day('2026-10-01','10'),day('2026-10-02',null,'TWD','PARTIAL')],'paid_order_amount'),[]);
 assert.deepEqual(trendPoints([day('2026-10-01','10'),day('2026-10-02','20','CNY')],'paid_order_amount'),[]);
 assert.deepEqual(trendPoints([day('2026-10-01','10'),{day:'2026-10-02',metrics:[]}],'paid_order_amount'),[]);
});

test('missing or duplicate days do not imply a continuous trend',()=>{
 assert.deepEqual(trendPoints([day('2026-10-01','10'),day('2026-10-03','20')],'paid_order_amount'),[]);
 assert.deepEqual(trendPoints([day('2026-10-01','10'),day('2026-10-01','20')],'paid_order_amount'),[]);
});
