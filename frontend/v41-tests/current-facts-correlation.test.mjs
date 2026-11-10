import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import test from 'node:test';
const source=readFileSync(new URL('../v41-e2e/shell.live.spec.ts',import.meta.url),'utf8');
const start=source.indexOf('// CURRENT_FACTS_CORRELATION_BEGIN');
const end=source.indexOf('// CURRENT_FACTS_CORRELATION_END');
assert.ok(start>=0&&end>start);
const {correlateCurrentFacts}=new Function(stripTypeScriptTypes(source.slice(start,end))+';return {correlateCurrentFacts};')();
const query={shop_id:'owned-shop',kind:'dashboard',days:'7'};
const times=['2026-11-04T08:14:57.575624Z','2026-11-04T08:15:02.433886Z'];
const immediate=()=>new Promise(resolve=>setImmediate(resolve));
function harness(){
  const page=new EventEmitter(),frame={};page.mainFrame=()=>frame;
  let ui=[],trace,clicks=0,validationCalls=0;
  const validated=[],exact=[];
  function request({time=times[0],start=Date.now()+1,status=200,noStore=true,finished=null,validationError=null,queryOverride=null,never=false,otherFrame=false,wrongRequest=false}={}){
    let nativeStart=0;
    const req={url:()=>`http://127.0.0.1:11200/api/v4/read-context?${new URLSearchParams(queryOverride??query)}`,method:()=>'GET',frame:()=>otherFrame?{}:frame,timing:()=>({startTime:nativeStart})};
    const response={request:()=>wrongRequest?{}:req,status:()=>status,headers:()=>({'cache-control':noStore?'no-store':'public'}),finished:async()=>finished,json:async()=>({read_at:time,validationError})};
    req.response=()=>never?new Promise(()=>{}):Promise.resolve().then(()=>{nativeStart=start;return response;});
    return req;
  }
  const options={page,api:'http://127.0.0.1:11200',query,timeout:250,
    click:async()=>{clicks++;},
    validate:body=>{validationCalls++;if(body.validationError)throw Error(body.validationError);validated.push(body.read_at);return body.read_at;},
    readUI:async()=>ui,
    poll:async(probe)=>{for(let n=0;n<200;n++){if(await probe())return;await immediate();}throw Error('bounded UI association not found');},
    exact:async text=>{assert.deepEqual(ui,[text]);exact.push(text);},trace:value=>{trace=value;},
  };
  return {page,frame,request,options,setUI:v=>{ui=v;},get trace(){return trace;},get clicks(){return clicks;},get validationCalls(){return validationCalls;},validated,exact,
    assertClean(){assert.equal(page.listenerCount('request'),0);assert.equal(page.listenerCount('requestfailed'),0);}};
}
test('only post-arm main-frame Requests participate, including delayed old-response events',async()=>{
  const h=harness(),old=h.request({start:Date.now()-10000});
  h.page.emit('request',old); // Before installation is never enrolled.
  h.options.click=async()=>{
    h.page.emit('request',old); // Even a late event cannot make its native pre-arm start eligible.
    h.page.emit('request',h.request({otherFrame:true}));
    h.page.emit('request',h.request({time:times[1]}));h.setUI(['数据读取于 '+times[1]]);
  };
  assert.equal(await correlateCurrentFacts(h.options),times[1]);
  assert.deepEqual(h.validated,[times[1]]);assert.equal(h.trace.ignored_before_arm,1);assert.equal(h.trace.ignored_other_frame,1);h.assertClean();
});
test('a later rendered same-scope response wins by exact UI identity, not arrival or max time',async()=>{
  const h=harness();let clicks=0;
  h.options.click=async()=>{clicks++;h.page.emit('request',h.request({time:times[1]}));h.page.emit('request',h.request({time:times[0]}));h.setUI(['数据读取于 '+times[0]]);};
  assert.equal(await correlateCurrentFacts(h.options),times[0]);assert.equal(clicks,1);assert.equal(h.trace.matched_ordinal,2);assert.deepEqual(h.exact,['数据读取于 '+times[0]]);h.assertClean();
});
for(const [label,delta] of [['unknown-start',{start:0}],['request-object',{wrongRequest:true}],['HTTP',{status:500}],['no-store',{noStore:false}],['finished',{finished:'transport failed'}],['schema',{validationError:'schema'}],['identity',{validationError:'5IDs'}],['shop',{validationError:'shop'}],['query',{queryOverride:{...query,shop_id:'other-shop'}}]]){
  test(`${label} failure cannot be swallowed by a later valid UI response`,async()=>{
    const h=harness();h.options.click=async()=>{h.page.emit('request',h.request(delta));h.page.emit('request',h.request({time:times[1]}));h.setUI(['数据读取于 '+times[1]]);};
    const reason={'unknown-start':'REQUEST_START_UNKNOWN','request-object':'RESPONSE_IDENTITY',HTTP:'HTTP_STATUS','no-store':'NO_STORE',finished:'FINISHED_FAILED',schema:'schema',identity:'5IDs',shop:'shop',query:'QUERY_MISMATCH'}[label];
    await assert.rejects(correlateCurrentFacts(h.options),new RegExp(reason));assert.equal(h.trace.status,'FAILED_OR_UNKNOWN');assert.equal(h.trace.matched_ordinal,null);assert.equal(h.exact.length,0);h.assertClean();
  });
}
test('two valid Requests sharing the displayed timestamp are ambiguous',async()=>{
  const h=harness();h.options.click=async()=>{h.page.emit('request',h.request());h.page.emit('request',h.request());h.setUI(['数据读取于 '+times[0]]);};
  await assert.rejects(correlateCurrentFacts(h.options),/AMBIGUOUS/);h.assertClean();
});
test('a UI-only timestamp is not accepted and listeners are removed on click failure',async()=>{
  const h=harness();h.options.click=async()=>{h.page.emit('request',h.request());h.setUI(['数据读取于 '+times[1]]);};
  await assert.rejects(correlateCurrentFacts(h.options));assert.equal(h.exact.length,0);h.assertClean();
  const failed=harness();failed.options.click=async()=>{throw Error('click failed');};
  await assert.rejects(correlateCurrentFacts(failed.options),/click failed/);failed.assertClean();
});
test('requestfailed is fatal; every enrolled task settles before failure trace',async()=>{
  const h=harness();h.options.click=async()=>{const r=h.request();h.page.emit('request',r);h.page.emit('requestfailed',r);h.setUI(['数据读取于 '+times[0]]);};
  await assert.rejects(correlateCurrentFacts(h.options));assert.ok(h.trace.requests.every(r=>r.done));h.assertClean();
});
test('unresolved response is bounded and cleaned without aborting or retrying transport',async()=>{
  const h=harness();h.options.timeout=20;h.options.click=async()=>{h.page.emit('request',h.request({never:true}));h.setUI(['数据读取于 '+times[0]]);};
  await assert.rejects(correlateCurrentFacts(h.options));assert.ok(h.trace.requests.every(r=>r.done));assert.equal(h.trace.status,'FAILED_OR_UNKNOWN');h.assertClean();
});
test('UI that changes during cutoff/drain fails the final exact correlation',async()=>{
  const h=harness();h.options.click=async()=>{h.page.emit('request',h.request());h.setUI(['数据读取于 '+times[0]]);};
  const poll=h.options.poll;h.options.poll=async probe=>{await poll(probe);h.setUI(['数据读取于 '+times[1]]);};
  await assert.rejects(correlateCurrentFacts(h.options));assert.equal(h.exact.length,0);h.assertClean();
});
