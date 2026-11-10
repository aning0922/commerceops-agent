import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {createV41Gate,guardV41Request} from '../lib/v41-context.mjs';
const id=()=>randomUUID();
function fixture(){const shop=id();return {shop,session:{context:{tenant_id:id(),organization_id:id(),principal_id:id(),shop_id:null,reset_epoch:0,auth_generation:0,authorized_at:new Date().toISOString()},data:{shops:[{shop_id:shop,grants:['operator']}]}}};}
function response(session,shop){return {status:'OK',context:{...session.context,shop_id:shop}};}
test('per-slot requests coexist while newer requests in same slot suppress old responses',()=>{
 const {shop,session}=fixture(),g=createV41Gate();assert.equal(g.establish(session,shop),true);
 const dashboard=g.begin('dashboard'),products=g.begin('products');
 assert.equal(g.accepts(dashboard,response(session,shop)),true);assert.equal(g.accepts(products,response(session,shop)),true);
 const newer=g.begin('products');assert.equal(g.accepts(products,response(session,shop)),false);assert.equal(g.accepts(newer,response(session,shop)),true);
});
test('switch, invalidation, mismatched context, ungranted shop and unknown responses fail closed',()=>{
 const {shop,session}=fixture(),g=createV41Gate();assert.equal(g.establish(session,shop),true);let ticket=g.begin('detail');
 for(const key of ['tenant_id','organization_id','principal_id','shop_id']){const r=response(session,shop);r.context[key]=id();assert.equal(g.accepts(ticket,r),false);}
 for(const key of ['reset_epoch','auth_generation']){const r=response(session,shop);r.context[key]++;assert.equal(g.accepts(ticket,r),false);}
 assert.equal(g.accepts(ticket,{...response(session,shop),status:'UNKNOWN'}),false);
 g.invalidate();assert.equal(g.accepts(ticket,response(session,shop)),false);
 assert.equal(g.establish(session,id()),false);assert.equal(g.begin('detail'),null);
 session.data.shops[0].grants=[];assert.equal(g.establish(session,shop),false);
 session.data.shops[0].grants=['approver'];assert.equal(g.establish(session,shop),true);ticket=g.begin('detail');
 assert.equal(g.establish(session,shop),true);assert.equal(g.accepts(ticket,response(session,shop)),false);
});

test('late denied writes cannot clear a newer shop; current lookup and readback denials clear',async()=>{
 const {session,shop}=fixture(),gate=createV41Gate();let cleared=0;
 gate.establish(session,shop);const old=gate.begin('write');let rejectOld;
 const deferred=new Promise((_,reject)=>{rejectOld=reject;});
 const pending=guardV41Request(gate,old,()=>deferred,e=>e.status===401||e.status===403,()=>cleared++);
 gate.invalidate();gate.establish(session,shop);rejectOld({status:401});await assert.rejects(pending);assert.equal(cleared,0);
 for(const slot of ['lookup','readback']){const ticket=gate.begin(slot);await assert.rejects(guardV41Request(gate,ticket,()=>Promise.reject({status:403}),e=>e.status===403,()=>cleared++));}
 assert.equal(cleared,2);
});
