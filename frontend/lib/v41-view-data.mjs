const dashboards=new Set(['/v4/dashboard','/v4/insights','/v4/dashboard/drilldown']);
const orders=new Set(['/v4/orders','/v4/orders/anomalies','/v4/orders/fulfillment-demo']);
export function isDashboardView(pathname){return dashboards.has(pathname);}
export function isOrderListView(pathname){return orders.has(pathname);}
export function fixedOrderFilters(pathname){
 if(pathname==='/v4/orders/anomalies')return {payment:'unknown'};
 if(pathname==='/v4/orders/fulfillment-demo')return {fulfillment:'demo_unfulfilled'};
 return {};
}
