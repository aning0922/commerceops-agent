import test from 'node:test';
import assert from 'node:assert/strict';
import { createContextGate } from '../lib/v4-context.mjs';
const context = {tenant_id:'tenant', organization_id:'org', principal_id:'p', shop_id:null, reset_epoch:0, auth_generation:0};
test('only matching latest authorized context may render', () => {
  const gate = createContextGate();
  assert.equal(gate.begin(), null);
  gate.establish(context); gate.selectShop('shop');
  const old = gate.begin(), current = gate.begin();
  const response = {...context, shop_id:'shop'};
  assert.equal(gate.accepts(old, response), false);
  assert.equal(gate.accepts(current, response), true);
  assert.equal(gate.accepts(current, {...response, principal_id:'other'}), false);
  assert.equal(gate.accepts(current, {...response, reset_epoch:1}), false);
  gate.invalidate();
  assert.equal(gate.accepts(current, response), false);
});
test('shop changes and invalid session context suppress stale responses', () => {
  const gate = createContextGate(); gate.establish(context); gate.selectShop('one');
  const ticket = gate.begin(); gate.selectShop('two');
  assert.equal(gate.accepts(ticket, {...context, shop_id:'one'}), false);
  gate.establish({...context, shop_id:'one'});
  assert.equal(gate.begin(), null);
});
