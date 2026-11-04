// JSON Schema checks structure; these invariants also mirror DTO validators that JSON Schema cannot express.
function validMetric(metric) {
  if (!metric || !Array.isArray(metric.reason_codes)) return false;
  const complete=metric.completeness==='COMPLETE';
  if (complete !== (metric.value!==null)) return false;
  if (complete && metric.value!==metric.known_value) return false;
  if (!complete && !metric.reason_codes.length) return false;
  return (metric.unit==='money') === (metric.currency!==null);
}
export function isSafeDataset(source) {
  if (!source || !Array.isArray(source.uploads)) return false;
  if ((source.data_mode==='demo_mixed') !== (source.uploads.length>0)) return false;
  const uploaded=new Set();
  for (const item of source.uploads) {
    if (item.data_mode!=='demo_upload' || !item.import_job_id || !item.file_digest || !Number.isInteger(item.import_row) || item.fixture_digest!==source.fixture_digest || item.baseline_snapshot_at!==source.baseline_snapshot_at) return false;
    const key=`${item.import_job_id}:${item.import_row}`;
    if(uploaded.has(key))return false;
    uploaded.add(key);
  }
  return true;
}
export function isSafeDashboard(data) {
  if (!isSafeDataset(data?.snapshot?.source) || !Array.isArray(data.metrics) || !Array.isArray(data.trend) || data.model_mode!=='not_used') return false;
  if (new Set(data.metrics.map(item=>item.metric)).size!==data.metrics.length || !data.metrics.every(validMetric)) return false;
  for (const point of data.trend) {
    if (!Array.isArray(point.metrics) || !point.metrics.every(validMetric) || new Set(point.metrics.map(item=>item.metric)).size!==point.metrics.length) return false;
  }
  return true;
}

// Compare calendar dates, without applying the browser's timezone.
export function matchesDashboardPeriod(period,days,timezone) {
  if(!period || ![7,14].includes(days) || period.timezone!==timezone ||
     !/^\d{4}-\d{2}-\d{2}$/.test(period.from_date) || !/^\d{4}-\d{2}-\d{2}$/.test(period.to_date)) return false;
  const from=Date.parse(`${period.from_date}T00:00:00Z`),to=Date.parse(`${period.to_date}T00:00:00Z`);
  return Number.isFinite(from)&&Number.isFinite(to)&&to-from===days*86400000 &&
    new Date(from).toISOString().slice(0,10)===period.from_date && new Date(to).toISOString().slice(0,10)===period.to_date;
}
