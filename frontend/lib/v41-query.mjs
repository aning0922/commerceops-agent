const allowed={product:{origin:['demo_fixture','demo_upload'],sort:['title_asc','title_desc','price_asc','price_desc']},order:{payment:['recorded','unknown'],fulfillment:['demo_unfulfilled','demo_fulfilled'],time_basis:['created','paid'],sort:['created_desc','created_asc','amount_desc','amount_asc']}};
/** Build both list and export from the same validated filters; cursors are list-only. */
export function buildCatalogQuery(shop,kind,q,filters,cursor='') {
  if(!shop||!allowed[kind]||typeof q!=='string'||q.length>80||!filters||typeof filters!=='object')return null;
  const query=new URLSearchParams({shop_id:shop});if(q)query.set('q',q);
  for(const [key,value] of Object.entries(filters)) {
    if(value==='')continue;
    if(kind==='product'&&key==='tag') {if(typeof value!=='string'||!value.trim()||value!==value.trim()||value.length>24)return null;}
    else if(!allowed[kind][key]?.includes(value))return null;
    query.set(key,value);
  }
  if(cursor)query.set('cursor',cursor);
  return query;
}
