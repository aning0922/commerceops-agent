import {isSessionContext, sameIdentityContext} from './v4-context.mjs';

// This is a display freshness boundary, never an authorization mechanism.
// Each independent slot has its own sequence; context/shop changes invalidate all slots.
export function createV41Gate() {
  let generation=0, context=null, shop=null;
  const sequences=new Map();
  return {
    invalidate(){generation++;context=null;shop=null;sequences.clear();},
    establish(session,shopId){
      generation++;sequences.clear();context=null;shop=null;
      if (!isSessionContext(session?.context) || typeof shopId!=='string' ||
          !Array.isArray(session?.data?.shops) ||
          !session.data.shops.some(s=>s.shop_id===shopId && Array.isArray(s.grants) && s.grants.some(g=>g==='operator'||g==='approver'))) return false;
      context={...session.context};shop=shopId;return true;
    },
    begin(slot){
      if (!context || !shop || typeof slot!=='string' || !slot) return null;
      const sequence=(sequences.get(slot)??0)+1;sequences.set(slot,sequence);
      return Object.freeze({generation,slot,sequence,context:{...context},shop});
    },
    accepts(ticket,response){
      return !!ticket && !!context && ticket.generation===generation &&
        sequences.get(ticket.slot)===ticket.sequence && ticket.shop===shop &&
        sameIdentityContext(ticket.context,context) && sameIdentityContext(ticket.context,response?.context) &&
        response.context.shop_id===ticket.shop && response.status==='OK';
    },
  };
}

// Run the rejection side effect only for the still-current request ticket.
export async function guardV41Request(gate,ticket,run,isDenied,onDenied) {
  try {return await run();} catch(error) {
    if(isDenied(error) && gate.accepts(ticket,{status:'OK',context:{...ticket.context,shop_id:ticket.shop}})) onDenied();
    throw error;
  }
}
