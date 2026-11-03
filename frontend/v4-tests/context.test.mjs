import test from 'node:test';
import assert from 'node:assert/strict';
import { createContextGate, sameIdentityContext, matchesControlBoundary, matchesControlReadback, matchesRecoveredControl, matchesCreateBoundary, shouldClearSummaryFailure } from '../lib/v4-context.mjs';
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

test('identity comparison refuses incomplete or malformed DTOs', () => {
  assert.equal(sameIdentityContext(context,{...context,shop_id:id}),true);
  assert.equal(sameIdentityContext({shop_id:null},{shop_id:null}),false);
  assert.equal(sameIdentityContext(context,{...context,auth_generation:0.5}),false);
  assert.equal(sameIdentityContext(context,{...context,principal_id:other}),false);
});

test('control receipt stays bound to its tenant, counters and operation',()=>{
 const after={...context,principal_id:other,auth_generation:1};
 const receipt={operation:'persona',request_key:id,status:'COMMITTED',reset_epoch:0,auth_generation:1};
 const result={status:'COMMITTED',context:after,data:{receipt,next_step:'READ_CURRENT_SESSION'}};
 assert.equal(matchesControlBoundary(context,result,'persona',id),true);
 assert.equal(matchesControlBoundary(context,{...result,context:{...after,tenant_id:other}},'persona',id),false);
 assert.equal(matchesControlBoundary(context,{...result,data:{...result.data,receipt:{...receipt,auth_generation:0}}},'persona',id),false);
 assert.equal(matchesControlBoundary(context,result,'persona',other),false);
 assert.equal(matchesControlBoundary(context,{...result,status:'UNKNOWN'},'persona',id),false);
 assert.equal(matchesControlBoundary(context,{...result,data:{...result.data,next_step:'LOGGED_OUT'}},'persona',id),false);
 const logout={status:'COMMITTED',context,data:{receipt:{...receipt,operation:'logout',auth_generation:0},next_step:'LOGGED_OUT'}};
 assert.equal(matchesControlBoundary(context,logout,'logout',id),true);
 assert.equal(matchesControlBoundary(context,{...logout,context:{...context,principal_id:other}},'logout',id),false);
});

test('created session must match the original receipt and the re-read identity',()=>{
 const receipt={operation:'session_create',request_key:id,status:'COMMITTED',reset_epoch:0,auth_generation:0};
 const created={status:'COMMITTED',context,data:{receipt,session:{creation_request_key:id}}};
 const current={context,data:{creation_request_key:id}};
 assert.equal(matchesCreateBoundary(created,current,id),true);
 assert.equal(matchesCreateBoundary(created,{...current,context:{...context,tenant_id:other}},id),false);
 assert.equal(matchesCreateBoundary(created,{...current,data:{creation_request_key:other}},id),false);
 assert.equal(matchesCreateBoundary({...created,data:{...created.data,receipt:{...receipt,auth_generation:1}}},current,id),false);
 assert.equal(matchesCreateBoundary({...created,status:'UNKNOWN'},current,id),false);
});

test('reset and persona require exact per-operation counter changes',()=>{
 const receipt={operation:'reset',request_key:id,status:'COMMITTED',reset_epoch:1,auth_generation:1};
 const reset={status:'COMMITTED',context:{...context,reset_epoch:1,auth_generation:1},data:{receipt,next_step:'READ_CURRENT_SESSION'}};
 assert.equal(matchesControlBoundary(context,reset,'reset',id),true);
 for(const [epoch,generation] of [[0,0],[1,0],[0,1],[2,1],[1,2]]) {
  const bad={...reset,context:{...context,reset_epoch:epoch,auth_generation:generation},data:{...reset.data,receipt:{...receipt,reset_epoch:epoch,auth_generation:generation}}};
  assert.equal(matchesControlBoundary(context,bad,'reset',id),false);
 }
 assert.equal(matchesControlBoundary(context,{...reset,context:{...reset.context,principal_id:other}},'reset',id),false);
 const persona={...reset,context:{...context,principal_id:other,auth_generation:1},data:{...reset.data,receipt:{...receipt,operation:'persona',reset_epoch:0}}};
 assert.equal(matchesControlBoundary(context,persona,'persona',id),true);
 assert.equal(matchesControlBoundary(context,{...persona,context:{...persona.context,principal_id:id}},'persona',id),false);
 assert.equal(matchesControlBoundary(context,{...persona,context:{...context},data:{...persona.data,receipt:{...persona.data.receipt,auth_generation:0}}},'persona',id),false);
 assert.equal(matchesControlBoundary(context,{...persona,context:{...context,reset_epoch:1,auth_generation:1},data:{...persona.data,receipt:{...persona.data.receipt,reset_epoch:1}}},'persona',id),false);
 const unsafe=Number.MAX_SAFE_INTEGER;
 assert.equal(matchesControlBoundary({...context,auth_generation:unsafe},{...persona,context:{...context,auth_generation:unsafe+1},data:{...persona.data,receipt:{...persona.data.receipt,auth_generation:unsafe+1}}},'persona',id),false);
});
test('control readback preserves session key and correct target persona',()=>{
 const next={...context,auth_generation:1};
 const before={context,data:{creation_request_key:id,persona_id:'operator'}};
 const result={context:next};
 const current={context:next,data:{creation_request_key:id,persona_id:'restricted_admin'}};
 assert.equal(matchesControlReadback(before,result,current,'persona','restricted_admin'),true);
 assert.equal(matchesControlReadback(before,result,current,'persona','admin'),false);
 assert.equal(matchesControlReadback(before,result,current,'reset',''),false);
 assert.equal(matchesControlReadback(before,result,{...current,data:{...current.data,creation_request_key:other}},'persona','restricted_admin'),false);
 assert.equal(matchesControlReadback({data:{}},result,{context:next,data:{}},'reset',''),false);
 assert.equal(matchesControlReadback(before,result,{...current,context:{...next,auth_generation:2}},'persona','restricted_admin'),false);
});

test('UNKNOWN recovery needs original proof, exact effect and current persona',()=>{
 const proof={context,creation_request_key:id,persona_id:'operator',target_persona:null};
 const receipt={operation:'reset',request_key:id,status:'COMMITTED',reset_epoch:1,auth_generation:1};
 const current={context:{...context,reset_epoch:1,auth_generation:1},data:{creation_request_key:id,persona_id:'operator'}};
 assert.equal(matchesRecoveredControl(proof,receipt,current,'reset',id),true);
 assert.equal(matchesRecoveredControl(undefined,receipt,current,'reset',id),false);
 assert.equal(matchesRecoveredControl(proof,{...receipt,reset_epoch:0},current,'reset',id),false);
 assert.equal(matchesRecoveredControl(proof,receipt,{...current,data:{...current.data,persona_id:'approver'}},'reset',id),false);
 assert.equal(matchesRecoveredControl(proof,receipt,{...current,context:{...current.context,tenant_id:other}},'reset',id),false);
 assert.equal(matchesRecoveredControl(proof,receipt,current,'logout',id),false);
});

test('late summary failure clears only the still-selected identity and shop',()=>{
 assert.equal(shouldClearSummaryFailure(context,context,id,id),true);
 assert.equal(shouldClearSummaryFailure(context,{...context,auth_generation:1},id,id),false);
 assert.equal(shouldClearSummaryFailure(context,context,other,id),false);
 assert.equal(shouldClearSummaryFailure(context,null,id,id),false);
 assert.equal(shouldClearSummaryFailure(context,context,'',''),false);
});
