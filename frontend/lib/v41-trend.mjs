/** A chart is only drawn for complete numeric values of the same metric and unit. */
export function trendPoints(trend,metricId) {
  if(!Array.isArray(trend)||trend.length<2)return [];
  const values=trend.map(day=>({day:day.day,metric:day.metrics?.find(item=>item.metric===metricId)}));
  const dates=values.map(row=>/^\d{4}-\d{2}-\d{2}$/.test(row.day)?Date.parse(`${row.day}T00:00:00Z`):NaN);
  if(dates.some((date,index)=>!Number.isFinite(date)||new Date(date).toISOString().slice(0,10)!==values[index].day||(index>0 && date-dates[index-1]!==86400000)))return [];
  if(values.some(row=>!row.metric || row.metric.completeness!=='COMPLETE' || row.metric.value===null || !Number.isFinite(Number(row.metric.value))))return [];
  const unit=values[0].metric.currency;if(values.some(row=>row.metric.currency!==unit))return [];
  const numbers=values.map(row=>Number(row.metric.value)),min=Math.min(...numbers),max=Math.max(...numbers),span=max-min;
  return values.map((row,index)=>({day:row.day,value:row.metric.value,currency:unit,x:20+index*560/(values.length-1),y:span?100-(numbers[index]-min)*80/span:60}));
}
