import {isSessionContext,sameIdentityContext} from './v4-context.mjs';
const slot='commerceops-v41-shop-preference';
/** This is only a selection hint; callers must first fetch and validate the current session. */
export function saveShopPreference(storage,session,shopId){
 try{
  if(!shopId){storage.removeItem(slot);return;}
  if(!isSessionContext(session?.context)||!Array.isArray(session?.data?.shops)||!session.data.shops.some(shop=>shop.shop_id===shopId))return;
  storage.setItem(slot,JSON.stringify({context:session.context,shop_id:shopId}));
 }catch{}
}
export function loadShopPreference(storage,session){
 try{
  const raw=storage.getItem(slot);if(raw===null)return null;const value=JSON.parse(raw);
  if(!value||Object.keys(value).sort().join(',')!=='context,shop_id'||!isSessionContext(session?.context)||!isSessionContext(value.context)||!sameIdentityContext(value.context,session.context)||typeof value.shop_id!=='string'||!Array.isArray(session?.data?.shops)||!session.data.shops.some(shop=>shop.shop_id===value.shop_id))return null;
  return value.shop_id;
 }catch{return null;}
}
