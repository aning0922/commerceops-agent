import test from 'node:test';
import assert from 'node:assert/strict';
import {matchesExportSnapshot} from '../lib/v41-export.mjs';
function example(){const source={data_mode:'demo_fixture',fixture_digest:'source',baseline_snapshot_at:'time',uploads:[]},snapshot={source,data_revision:'revision',snapshot_id:'snapshot'};return {page:{snapshot},out:{snapshot,format:'csv',filename:'products.csv',row_count:3,csv_text:'safe'}};}
test('export is limited to same snapshot, revision, source and allowed name',()=>{
 const {page,out}=example();assert.equal(matchesExportSnapshot(page,out,'product'),true);
 assert.equal(matchesExportSnapshot(page,{...out,filename:'orders.csv'},'product'),false);
 assert.equal(matchesExportSnapshot(page,{...out,row_count:501},'product'),false);
 assert.equal(matchesExportSnapshot(page,{...out,snapshot:{...out.snapshot,data_revision:'other'}},'product'),false);
 assert.equal(matchesExportSnapshot(page,{...out,snapshot:{...out.snapshot,snapshot_id:'other'}},'product'),false);
 assert.equal(matchesExportSnapshot(page,{...out,snapshot:{...out.snapshot,source:{...out.snapshot.source,fixture_digest:'other'}}},'product'),false);
});
