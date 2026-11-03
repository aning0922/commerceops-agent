import test from 'node:test';
import assert from 'node:assert/strict';
import { createContextGate } from '../lib/v4-context.mjs';
const id='11111111-1111-4111-8111-111111111111', other='22222222-2222-4222-8222-222222222222';
const context = {tenant_id:id, organization_id:id, principal_id:id, shop_id:null, reset_epoch:0, auth_generation:0, authorized_at:'2026-11-03T00:00:00Z'};
test('only matching latest authorized context may render', () => {
  const gate = createContextGate(); assert.equal(gate.begin(), null);
  gate.establish(context); gate.selectShop(id);
  const old = gate.begin(), current = gate.begin(); const response = {...context, shop_id:id};
  assert.equal(gate.accepts(old, response), false); assert.equal(gate.accepts(current, response), true);
  assert.equal(gate.accepts(current, {...response, principal_id:other}), false);
  assert.equal(gate.accepts(current, {...response, reset_epoch:1}), false);
  gate.invalidate(); assert.equal(gate.accepts(current, response), false);
});
test('shop changes and invalid session context suppress stale responses', () => {
  const gate = createContextGate(); gate.establish(context); gate.selectShop(id);
  const ticket = gate.begin(); gate.selectShop(other);
  assert.equal(gate.accepts(ticket, {...context, shop_id:id}), false);
  gate.establish({...context, shop_id:id}); assert.equal(gate.begin(), null);
});
test('rejects incomplete or malformed contexts on both sides', () => {
  const invalid = [{shop_id:null}, {...context,tenant_id:''}, {...context,principal_id:'bad'}, {...context,organization_id:null}, {...context,reset_epoch:0.5}, {...context,auth_generation:'0'}, {...context,reset_epoch:-1}, {...context,authorized_at:''}, {...context,extra:true}];
  for (const value of invalid) {
    const gate = createContextGate(); gate.establish(value); assert.equal(gate.begin(),null);
    gate.establish(context); gate.selectShop(id); const ticket=gate.begin();
    assert.equal(gate.accepts(ticket,{...value,shop_id:id}),false);
  }
  const gate=createContextGate();gate.establish(context);gate.selectShop('');assert.equal(gate.begin(),null);
});
