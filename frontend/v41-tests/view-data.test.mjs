import test from 'node:test';
import assert from 'node:assert/strict';
import {isDashboardView,isOrderListView,fixedOrderFilters} from '../lib/v41-view-data.mjs';
import {buildCatalogQuery} from '../lib/v41-query.mjs';
test('all three frozen dashboard views use current dashboard data',()=>{
 for(const path of ['/v4/dashboard','/v4/insights','/v4/dashboard/drilldown'])assert.equal(isDashboardView(path),true);
 assert.equal(isDashboardView('/v4/analytics'),false);
});
test('order subviews bind their declared subset to both list and export queries',()=>{
 for(const [path,key,value] of [['/v4/orders/anomalies','payment','unknown'],['/v4/orders/fulfillment-demo','fulfillment','demo_unfulfilled']]){
  assert.equal(isOrderListView(path),true);const filters={sort:'created_desc',...fixedOrderFilters(path)};
  const page=buildCatalogQuery('shop','order','',filters,'cursor'),output=buildCatalogQuery('shop','order','',filters);
  assert.equal(page.get(key),value);assert.equal(output.get(key),value);page.delete('cursor');assert.equal(page.toString(),output.toString());
 }
 assert.equal(isOrderListView('/v4/orders'),true);assert.equal(isOrderListView('/v4/orders/invalid'),false);
});
