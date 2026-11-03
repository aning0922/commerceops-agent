import test from 'node:test';
import assert from 'node:assert/strict';
import {sessionFailureMessage} from '../lib/v4-session-message.mjs';
test('session errors distinguish anonymous, expiry, denial and uncertainty',()=>{
 assert.equal(sessionFailureMessage(401,'SESSION_INVALID','REJECTED',false),'');
 assert.match(sessionFailureMessage(401,'SESSION_INVALID','REJECTED',true),/失效/);
 assert.match(sessionFailureMessage(401,'EXPIRED','REJECTED',true),/已到期/);
 assert.match(sessionFailureMessage(403,'ACCESS_DENIED','REJECTED',true),/权限/);
 assert.match(sessionFailureMessage(401,'EXPIRED','UNKNOWN',true),/无法验证/);
 assert.match(sessionFailureMessage(null,null,null,true),/无法验证/);
});
