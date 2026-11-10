import test from 'node:test';
import assert from 'node:assert/strict';
import {closeAndCleanOwnedProfile} from './lifecycle.profile.mjs';
test('no returned context preserves owned profile',async()=>{
 let removed=0;assert.equal(await closeAndCleanOwnedProfile(null,'owned',async()=>{removed++;}),false);assert.equal(removed,0);
});
test('close failure propagates and preserves owned profile',async()=>{
 let removed=0;const failure=new Error('close failed');await assert.rejects(closeAndCleanOwnedProfile({close:async()=>{throw failure;}},'owned',async()=>{removed++;}),error=>error===failure);assert.equal(removed,0);
});
test('successful close removes only the supplied owned profile afterward',async()=>{
 const actions=[];const result=await closeAndCleanOwnedProfile({close:async()=>actions.push('closed')},'owned',async(path,options)=>{actions.push([path,options]);});
 assert.equal(result,true);assert.deepEqual(actions,['closed',['owned',{recursive:true,force:true}]]);
});
