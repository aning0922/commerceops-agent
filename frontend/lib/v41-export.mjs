import {isSafeDataset} from './v41-dashboard.mjs';

/** Only a schema-validated export for the same displayed query snapshot may be downloaded. */
export function matchesExportSnapshot(page,output,kind) {
  if(!['product','order'].includes(kind) || !page?.snapshot || !output?.snapshot || !isSafeDataset(page.snapshot.source) || !isSafeDataset(output.snapshot.source))return false;
  const sourceKey=source=>JSON.stringify([source.data_mode,source.evidence_mode,source.fixture_version,source.fixture_digest,source.baseline_snapshot_at,...source.uploads.map(row=>[row.import_job_id,row.import_row,row.file_digest,row.fixture_digest,row.baseline_snapshot_at].join(':')).sort()]);
  return output.format==='csv' && output.filename===(kind==='product'?'products.csv':kind==='order'?'orders.csv':'') &&
    Number.isSafeInteger(output.row_count) && output.row_count>=0 && output.row_count<=500 &&
    typeof output.csv_text==='string' && output.snapshot.data_revision===page.snapshot.data_revision &&
    output.snapshot.snapshot_id===page.snapshot.snapshot_id &&
    sourceKey(output.snapshot.source)===sourceKey(page.snapshot.source);
}
