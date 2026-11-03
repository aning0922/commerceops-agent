import test from 'node:test';
import assert from 'node:assert/strict';
import {sessionFailureMessage,shouldRevalidate} from '../lib/v4-session-message.mjs';
test('session errors distinguish anonymous, expiry, denial and uncertainty',()=>{
 assert.equal(sessionFailureMessage(401,'SESSION_INVALID','REJECTED',false),'');
 assert.match(sessionFailureMessage(401,'SESSION_INVALID','REJECTED',true),/失效/);
 assert.match(sessionFailureMessage(401,'EXPIRED','REJECTED',true),/已到期/);
 assert.match(sessionFailureMessage(403,'ACCESS_DENIED','REJECTED',true),/权限/);
 assert.match(sessionFailureMessage(401,'EXPIRED','UNKNOWN',true),/无法验证/);
 assert.match(sessionFailureMessage(null,null,null,true),/无法验证/);
});

test('automatic revalidation is limited to a known visible online session without pending writes',()=>{
 assert.equal(shouldRevalidate(true,true,true,false),true);
 for (const args of [[false,true,true,false],[true,false,true,false],[true,true,false,false],[true,true,true,true]]) assert.equal(shouldRevalidate(...args),false);
});
