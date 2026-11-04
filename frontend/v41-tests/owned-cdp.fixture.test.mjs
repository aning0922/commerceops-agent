import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import test from 'node:test';
const source=readFileSync(new URL('../v41-e2e/owned-cdp.fixture.ts',import.meta.url),'utf8');
// Execute the exact dependency-free validator/lifecycle definitions from the fixture.
const guard=source.slice(source.indexOf('function requireValue'),source.indexOf('function bytes'));
const helpers=source.slice(source.indexOf('export function checkAck'),source.indexOf('export const test')).replaceAll('export ','');
const {checkAck,usingOwnedContext}=new Function(stripTypeScriptTypes(guard+helpers)+';return {checkAck,usingOwnedContext};')();
const expected={nonce:'owned-one',worker_pid:17,native_pid:19,profile:'/private/owned'};
const ack={...expected,schema:'v41-shell-cdp-ack-v1',host:'127.0.0.1',port:52345,browser_path:'/devtools/browser/owned-one'};
test('owned handshake refuses identity drift and non-loopback endpoints before connect',async()=>{
  checkAck(ack,expected);
  for(const delta of [{nonce:'other'},{native_pid:20},{profile:'/other'},{host:'0.0.0.0'},{port:0},{browser_path:'https://other'}]){
    let connected=0,closed=0;
    await assert.rejects(usingOwnedContext(async()=>{checkAck({...ack,...delta},expected);connected++;return {};},async()=>{},async()=>{closed++;}));
    assert.equal(connected,0);assert.equal(closed,1);
  }
});
test('setup and use failures both execute native teardown and teardown failures propagate',async()=>{
  for(const stage of ['setup','use','close']){
    const order=[];
    await assert.rejects(usingOwnedContext(async()=>{order.push('setup');if(stage==='setup')throw Error(stage);return {};},async()=>{order.push('use');if(stage==='use')throw Error(stage);},async()=>{order.push('close');if(stage==='close')throw Error(stage);}));
    assert.equal(order.at(-1),'close');assert.equal(order.filter(x=>x==='close').length,1);
  }
});
