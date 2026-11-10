import test from 'node:test';
import assert from 'node:assert/strict';
import {approvedApiOrigin} from '../lib/v4-origin.mjs';
test('API origin requires an exact configured origin and explicit loopback HTTP mode',()=>{
 for (const value of [undefined,'','https://user:pass@example.com','https://example.com/path','https://example.com/','http://example.com','file:///tmp/x','https://example.com?x=1']) assert.equal(approvedApiOrigin(value,false),null);
 assert.equal(approvedApiOrigin('https://example.com',false),'https://example.com');
 assert.equal(approvedApiOrigin('http://127.0.0.1:4567',false),null);
 assert.equal(approvedApiOrigin('http://127.0.0.1:4567',true),'http://127.0.0.1:4567');
 assert.equal(approvedApiOrigin('http://[::1]:4567',true),'http://[::1]:4567');
 assert.equal(approvedApiOrigin('http://example.com',true),null);
});
