import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {loadShopPreference,saveShopPreference} from '../lib/v41-shop-preference.mjs';
function storage(){const values=new Map();return {getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};}
function fixture(){const id=()=>randomUUID(),shop=id();return {shop,session:{context:{tenant_id:id(),organization_id:id(),principal_id:id(),shop_id:null,reset_epoch:1,auth_generation:1,authorized_at:'2026-11-03T00:00:00Z'},data:{shops:[{shop_id:shop,grants:['operator']}]}}};}
test('shop preference requires freshly validated same identity and current shop membership',()=>{
 const s=storage(),{shop,session}=fixture();saveShopPreference(s,session,shop);assert.equal(loadShopPreference(s,session),shop);
 assert.equal(loadShopPreference(s,{...session,context:{...session.context,auth_generation:2}}),null);
 assert.equal(loadShopPreference(s,{...session,context:{...session.context,tenant_id:randomUUID()}}),null);
 assert.equal(loadShopPreference(s,{...session,data:{shops:[]}}),null);
 saveShopPreference(s,session,'');assert.equal(loadShopPreference(s,session),null);
});
test('unavailable or malformed preference never grants a selection',()=>{
 const s=storage(),{session}=fixture();s.setItem('commerceops-v41-shop-preference','{');assert.equal(loadShopPreference(s,session),null);
 assert.equal(loadShopPreference({getItem(){throw Error('blocked');}},session),null);
});
