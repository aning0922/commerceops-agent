/** Derive only events whose timestamps are present in the verified order DTO. */
export function orderTimeline(order){
 if(!order||!order.created_at)return [];
 const events=[{key:'created',at:order.created_at,label:'订单创建'}];
 if(order.paid_at)events.push({key:'paid',at:order.paid_at,label:'支付已记录'});
 for(const refund of order.refunds??[])events.push({key:`refund:${refund.refund_id}`,at:refund.occurred_at,label:`退款事件 ${refund.currency} ${refund.amount} · 到账状态未知`});
 return events.sort((a,b)=>Date.parse(a.at)-Date.parse(b.at)||a.key.localeCompare(b.key));
}
