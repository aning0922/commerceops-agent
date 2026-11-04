import test from 'node:test';
import assert from 'node:assert/strict';
import {buildCatalogQuery} from '../lib/v41-query.mjs';
test('filtered list and export share every filter, cursor belongs only to list',()=>{
 const filters={tag:'新品',origin:'demo_upload',sort:'price_desc'};
 const page=buildCatalogQuery('shop','product','帽',filters,'cursor-value'),output=buildCatalogQuery('shop','product','帽',filters);
 assert.equal(page.get('cursor'),'cursor-value');page.delete('cursor');assert.equal(page.toString(),output.toString());assert.equal(output.get('tag'),'新品');
 const order=buildCatalogQuery('shop','order','x',{payment:'unknown',fulfillment:'demo_unfulfilled',time_basis:'paid',sort:'amount_asc'});
 assert.equal(order.get('payment'),'unknown');assert.equal(order.get('time_basis'),'paid');
});
test('cross-kind, unsupported and malformed filters fail closed',()=>{
 for(const filters of [{payment:'unknown'},{origin:'anything'},{tag:' invalid '},{tag:'x'.repeat(25)},{extra:'x'}])assert.equal(buildCatalogQuery('shop','product','',filters),null);
 assert.equal(buildCatalogQuery('shop','order','x'.repeat(81),{}),null);
});
