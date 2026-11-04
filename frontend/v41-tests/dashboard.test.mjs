import test from 'node:test';
import assert from 'node:assert/strict';
import {isSafeDashboard} from '../lib/v41-dashboard.mjs';
function sample(){return {model_mode:'not_used',snapshot:{source:{data_mode:'demo_fixture',fixture_digest:'same',baseline_snapshot_at:'same',uploads:[]}},metrics:[{metric:'paid_order_amount',completeness:'PARTIAL',value:null,known_value:'2140',unit:'money',currency:'TWD',reason_codes:['UNKNOWN_PAYMENT_TIME']}],trend:[]};}
test('partial metrics remain unknown and invalid semantic combinations are rejected',()=>{
 const value=sample();assert.equal(isSafeDashboard(value),true);
 for (const patch of [{value:'2140'},{reason_codes:[]},{currency:null},{completeness:'COMPLETE'}]) assert.equal(isSafeDashboard({...value,metrics:[{...value.metrics[0],...patch}]}),false);
 assert.equal(isSafeDashboard({...value,model_mode:'actual'}),false);
 assert.equal(isSafeDashboard({...value,metrics:[value.metrics[0],value.metrics[0]]}),false);
});
test('mixed source preserves upload provenance and rejects duplicates or wrong snapshot',()=>{
 const value=sample(),row={data_mode:'demo_upload',import_job_id:'job',import_row:2,file_digest:'hash',fixture_digest:'same',baseline_snapshot_at:'same'};
 value.snapshot.source={...value.snapshot.source,data_mode:'demo_mixed',uploads:[row]};
 assert.equal(isSafeDashboard(value),true);
 assert.equal(isSafeDashboard({...value,snapshot:{source:{...value.snapshot.source,uploads:[row,row]}}}),false);
 assert.equal(isSafeDashboard({...value,snapshot:{source:{...value.snapshot.source,uploads:[{...row,fixture_digest:'wrong'}]}}}),false);
});
