import {validV41Tag} from './v41-tags.mjs';
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function batchTargets(items,ids,tags){
 if(!Array.isArray(items)||!Array.isArray(ids)||!ids.length||new Set(ids).size!==ids.length||!Array.isArray(tags)||tags.length>8||!tags.every(validV41Tag)||new Set(tags).size!==tags.length)return null;
 const targets=[];
 for(const id of ids){const matches=items.filter(item=>item.product_id===id);if(matches.length!==1||!uuid.test(id)||!Number.isSafeInteger(matches[0].version)||matches[0].version<0)return null;targets.push(Object.freeze({id,version:matches[0].version}));}
 return Object.freeze(targets);
}
export function matchesBatchRead(data,target,revision){
 return !!data&&data.product?.product_id===target.id&&data.product.version===target.version&&data.snapshot?.data_revision===revision;
}
export function matchesBatchTags(actual,expected){
 return Array.isArray(actual)&&Array.isArray(expected)&&actual.every(validV41Tag)&&new Set(actual).size===actual.length&&JSON.stringify([...actual].sort())===JSON.stringify([...expected].sort());
}
/** One ephemeral UI loop. No persistence, retry, recovery, or background work. */
export async function applyBatchTags(targets,revision,active,execute,publish){
 const counts={success:0,rejected:0,pending:0,unsent:targets.length};
 publish({...counts});
 for(const target of targets){
  if(!active())break;
  // The executor marks dispatch only after durable reservation, immediately before POST.
  let dispatched=false;
  const dispatch=()=>{if(dispatched)throw new Error('DUPLICATE_DISPATCH');dispatched=true;counts.unsent--;counts.pending++;publish({...counts});};
  let result;try{result=await execute(target,revision,dispatch);}catch{result={status:dispatched?'unknown':'cancelled'};}
  const committed=result.status==='success'&&dispatched&&/^[a-f0-9]{64}$/.test(result.revision??'');
  if(committed){counts.pending--;counts.success++;revision=result.revision;}
  else if(result.status==='rejected'&&dispatched){counts.pending--;counts.rejected++;}
  if(active())publish({...counts});
  if(!committed)break;
 }
 return counts;
}
