import test from 'node:test';
import assert from 'node:assert/strict';
import {isSafeReadContext} from '../lib/v41-read-context.mjs';
const source={data_mode:'demo_fixture',fixture_digest:'a',baseline_snapshot_at:'t',import_job_id:null,import_row:null,file_digest:null};
const snapshot={source:{...source,uploads:[]}};
const product={product_id:'p',source,tags:['hot'],skus:[{available_units:null,stock_reason:'UNKNOWN_STOCK'}]};
const metric={unit:'count',currency:null,completeness:'COMPLETE',value:'2',known_value:'2',reason_codes:[]};
test('read context binds kind, object, source and honest metric completeness',()=>{
 const value={snapshot,kind:'product',resource_ids:['p'],product,order:null,metrics:[],insights:[],model_mode:'not_used'};
 assert.equal(isSafeReadContext(value,'product','p'),true);
 assert.equal(isSafeReadContext(value,'product','other'),false);
 assert.equal(isSafeReadContext({...value,product:{...product,source:{...source,fixture_digest:'wrong'}}},'product','p'),false);
 assert.equal(isSafeReadContext({...value,metrics:[metric]},'product','p'),false);
 const dashboard={...value,kind:'dashboard',resource_ids:[],product:null,metrics:[metric]};
 assert.equal(isSafeReadContext(dashboard,'dashboard',null),true);
 assert.equal(isSafeReadContext({...dashboard,metrics:[{...metric,value:null}]},'dashboard',null),false);
 assert.equal(isSafeReadContext({...dashboard,model_mode:'used'},'dashboard',null),false);
});
