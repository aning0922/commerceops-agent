const allowed={product:{origin:['demo_fixture','demo_upload'],sort:['title_asc','title_desc','price_asc','price_desc']},order:{payment:['recorded','unknown'],fulfillment:['demo_unfulfilled','demo_fulfilled'],time_basis:['created','paid'],sort:['created_desc','created_asc','amount_desc','amount_asc']}};
/** Build both list and export from the same validated filters; cursors are list-only. */
export function buildCatalogQuery(shop,kind,q,filters,cursor='') {
  if(!shop||!allowed[kind]||typeof q!=='string'||q.length>80||!filters||typeof filters!=='object')return null;
  const query=new URLSearchParams({shop_id:shop});if(q)query.set('q',q);
  if(kind==='order' && (filters.from_date||filters.to_date)){
    const from=filters.from_date,to=filters.to_date,valid=value=>typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(`${value}T00:00:00Z`)) && new Date(`${value}T00:00:00Z`).toISOString().slice(0,10)===value;
    if(!valid(from)||!valid(to))return null;const span=(Date.parse(`${to}T00:00:00Z`)-Date.parse(`${from}T00:00:00Z`))/86400000;if(span<1||span>90)return null;
  }
  for(const [key,value] of Object.entries(filters)) {
    if(value==='')continue;
    if(kind==='order'&&(key==='from_date'||key==='to_date')) {if(typeof value!=='string')return null;}
    else if(kind==='product'&&key==='tag') {if(typeof value!=='string'||!value.trim()||value!==value.trim()||value.length>24)return null;}
    else if(!allowed[kind][key]?.includes(value))return null;
    query.set(key,value);
  }
  if(cursor)query.set('cursor',cursor);
  return query;
}
