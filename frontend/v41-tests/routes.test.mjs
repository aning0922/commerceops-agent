import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import manifest from '../../docs/v4/v4-1/UI_ROUTES.json' with {type:'json'};
import bundled from '../lib/v41-routes.json' with {type:'json'};
import {modules, resolveV41Route} from '../lib/v41-routes.ts';

test('all frozen navigation and static stage routes resolve without granting access', () => {
  assert.deepEqual(bundled,manifest);
  assert.equal(modules.length,14);
  assert.equal(new Set(modules.map(item=>item.href)).size,14);
  for (const item of manifest.modules) assert.equal(resolveV41Route(item.href)?.module?.id,item.id);
  for (const view of manifest.stage_views.filter(item=>!item.route.includes(':'))) {
    assert.ok(resolveV41Route(view.route),view.route);
  }
  for (const path of manifest.auxiliary) assert.equal(resolveV41Route(path)?.auxiliary,true);
});

test('static reserved routes win and only canonical UUID resource paths resolve', () => {
  assert.equal(resolveV41Route('/v4/products/import')?.title,'商品导入');
  assert.equal(resolveV41Route('/v4/products/variants')?.title,'SKU规格');
  assert.equal(resolveV41Route('/v4/orders/anomalies')?.title,'异常订单');
  const sample=randomUUID();
  assert.equal(resolveV41Route(`/v4/products/${sample}`)?.title,'商品详情');
  assert.equal(resolveV41Route(`/v4/orders/${sample}`)?.title,'订单详情');
  for (const path of ['/v4/products/unknown','/v4/orders/anything','/v4/products/import/extra','/v4/unknown','/v4/dashboard/','/v4/products/%2f']) {
    assert.equal(resolveV41Route(path),null,path);
  }
});
