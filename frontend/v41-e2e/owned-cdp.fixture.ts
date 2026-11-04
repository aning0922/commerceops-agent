import {test as base,expect,chromium,type Browser,type BrowserContext,type Page,type CDPSession} from '@playwright/test';
import {spawn,execFileSync,type ChildProcess} from 'node:child_process';
import {constants,openSync,closeSync,fstatSync,readFileSync,writeSync,fsyncSync,mkdirSync,lstatSync,realpathSync,renameSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import argvTemplate from './owned-cdp.argv.json' with {type:'json'};
import {readBrowserCase} from './browser-subjects';
export {expect};
const title='LIVE V41: shell identity navigation and responsive boundaries';
const sha=(raw:Buffer|string)=>createHash('sha256').update(raw).digest('hex');
function requireValue(v:unknown,message:string):asserts v{if(!v)throw new Error(message);}
function bytes(path:string,limit=32768){
  requireValue(realpathSync(dirname(path))===dirname(path),'Canonical receipt parent required');
  const fd=openSync(path,constants.O_RDONLY|constants.O_NOFOLLOW);
  try{const s=fstatSync(fd);requireValue(s.isFile()&&s.uid===process.getuid?.()&&(s.mode&0o777)===0o600&&s.size<=limit,'Private bounded receipt required');return readFileSync(fd);}finally{closeSync(fd);}
}
function persist(path:string,value:unknown){
  const temporary=path+'.pending',fd=openSync(temporary,'wx',0o600);
  try{const raw=Buffer.from(JSON.stringify(value,null,2)+'\n');let offset=0;while(offset<raw.length)offset+=writeSync(fd,raw,offset);fsyncSync(fd);}finally{closeSync(fd);}
  renameSync(temporary,path);
}
// Public validators are also used by the resource-free fixture component checks.
export function checkAck(actual:Record<string,unknown>,expected:Record<string,unknown>){
  for(const [key,value] of Object.entries(expected))requireValue(actual[key]===value,'Owned ACK binding mismatch: '+key);
  requireValue(actual.schema==='v41-shell-cdp-ack-v1'&&actual.host==='127.0.0.1'&&Number.isInteger(actual.port)&&(actual.port as number)>0&&(actual.port as number)<=65535&&typeof actual.browser_path==='string'&&/^\/devtools\/browser\/[A-Za-z0-9-]+$/.test(actual.browser_path),'Owned loopback endpoint required');
}
export async function usingOwnedContext<T>(setup:()=>Promise<T>,use:(value:T)=>Promise<void>,close:()=>Promise<void>){
  try{await use(await setup());}finally{await close();}
}
export async function verifyOwnedShellPage(page:Page,session:CDPSession){
  const c=readBrowserCase(),directory=join(c.directory,'browser-shell-cdp');
  const proof=JSON.parse(bytes(join(directory,'page-binding.safe.json')).toString());
  requireValue(proof.source_sha===c.source_sha&&proof.source_tree===c.source_tree&&proof.case_sha256===sha(bytes(join(c.directory,'case.json')))&&proof.runtime_sha256===sha(bytes(join(c.directory,'browser-runtime.safe.json')))&&proof.ack_sha256===sha(bytes(join(directory,'endpoint-ack.safe.json'))),'Owned page source and endpoint changed');
  const context=page.context(),browser=context.browser();
  requireValue(browser&&browser.contexts().length===1&&browser.contexts()[0]===context&&context.pages().length===1&&context.pages()[0]===page,'Owned default context changed');
  const {targetInfo}=await session.send('Target.getTargetInfo');
  requireValue(targetInfo.type==='page'&&targetInfo.targetId===proof.target_id&&Object.hasOwn(targetInfo,'browserContextId')===proof.context_id_present&&(targetInfo.browserContextId??null)===proof.context_id&&targetInfo.url===page.url()&&new URL(targetInfo.url).origin===`http://127.0.0.1:${c.web_port}`,'Owned target association changed');
  const window=await session.send('Browser.getWindowForTarget',{targetId:targetInfo.targetId});
  requireValue(window.windowId===proof.window_id,'Owned window association changed');
}
export const test=base.extend<{context:BrowserContext;page:Page}>({
  context:async({},use,testInfo)=>{
    requireValue(testInfo.title===title,'Shell fixture only');
    const c=readBrowserCase();
    const rawCase=bytes(join(c.directory,'case.json'));
    const complete=JSON.parse(rawCase.toString());
    const fields=['source_sha','source_tree','inputs','scenario','project','database','directory','pg_image','test_image','api_port','web_port','pg_subnet','host_subnet','starts_at','deadline','parent_deadline','uid'];
    requireValue(Object.keys(complete).sort().join(',')===fields.sort().join(','),'Complete original case required');
    const runtimeRaw=bytes(join(c.directory,'browser-runtime.safe.json')),runtime=JSON.parse(runtimeRaw.toString());
    requireValue(runtime.schema_version==='v41-browser-runtime-v1'&&runtime.source_sha===c.source_sha&&runtime.source_tree===c.source_tree&&runtime.directory===c.directory&&runtime.uid===c.uid&&runtime.project===c.project&&runtime.test_image===complete.test_image&&runtime.playwright_version==='1.64.0','Original runtime binding required');
    for(const [file,digest] of [[runtime.executable,runtime.sha256],[runtime.framework,runtime.framework_sha256],[process.execPath,runtime.node_sha256]])requireValue(typeof file==='string'&&realpathSync(file)===file&&sha(readFileSync(file))===digest,'Pinned binary required');
    requireValue(process.env.V41_CHROMIUM_EXECUTABLE===runtime.executable,'Pinned executable handoff required');
    const directory=join(c.directory,'browser-shell-cdp');mkdirSync(directory,{mode:0o700});
    for(const name of ['home','tmp'])mkdirSync(join(directory,name),{mode:0o700});
    const nonce=randomUUID(),profile=join(c.directory,'browser-tmp','playwright_chromiumdev_profile-shell-cdp-'+nonce);
    mkdirSync(profile,{mode:0o700});const pi=lstatSync(profile);
    requireValue(realpathSync(profile)===profile&&pi.isDirectory()&&!pi.isSymbolicLink()&&pi.uid===c.uid&&(pi.mode&0o777)===0o700,'Fresh owned profile required');
    const worker_birth=execFileSync('/bin/ps',['-p',String(process.pid),'-o','lstart='],{env:{LC_ALL:'C',NODE_ENV:'test'},encoding:'utf8',timeout:2000}).trim().replace(/\s+/g,' ');
    const identity={source_sha:c.source_sha,source_tree:c.source_tree,case_sha256:sha(rawCase),runtime_sha256:sha(runtimeRaw),directory:c.directory,uid:c.uid,worker_pid:process.pid,worker_birth,nonce,profile};
    const args=argvTemplate.map(v=>v.replace('<OWNED_SHELL_PROFILE>',profile));
    persist(join(directory,'intent.private.json'),{schema:'v41-shell-cdp-intent-v1',...identity,title,executable:runtime.executable,argv:args});
    let child:ChildProcess|undefined,browser:Browser|undefined,exitPromise:Promise<void>|undefined,log:number|undefined;
    let nativeExit:number|null|'UNKNOWN'='UNKNOWN',nativeSignal:NodeJS.Signals|null|'UNKNOWN'='UNKNOWN',nativePid:number|undefined;
    let ack:Record<string,unknown>|undefined,closeAck=false,closeFailure:unknown=null,pageBindingSha:string|null=null;
    const failures:unknown[]=[];
    async function setup(){
      log=openSync(join(directory,'chrome.raw.log'),'wx',0o600);
      const spawnedChild=spawn(runtime.executable,args,{detached:true,env:{NODE_ENV:'test',PATH:dirname(process.execPath)+':/usr/bin:/bin',HOME:join(directory,'home'),TMPDIR:join(directory,'tmp')},stdio:['ignore',log,log]});child=spawnedChild;nativePid=spawnedChild.pid;
      exitPromise=new Promise<void>((resolve,reject)=>{child!.once('error',reject);child!.once('exit',(code,signal)=>{nativeExit=code;nativeSignal=signal;persist(join(directory,'native-exit.private.json'),{schema:'v41-shell-cdp-native-exit-v1',...identity,native_pid:nativePid,native_exit:code,signal});resolve();});});void exitPromise.catch(()=>{});
      persist(join(directory,'spawn.private.json'),{schema:'v41-shell-cdp-spawn-v1',...identity,native_pid:nativePid});
      const until=Math.min(Date.now()+20000,Date.parse(c.deadline)-180000),ackPath=join(directory,'endpoint-ack.safe.json');
      while(true){
        requireValue(Date.now()<until&&nativeExit==='UNKNOWN','Owned endpoint deadline or early native exit');
        try{ack=JSON.parse(bytes(ackPath).toString());break;}catch(e){if((e as NodeJS.ErrnoException).code!=='ENOENT')throw e;}
        await new Promise(resolve=>setTimeout(resolve,25));
      }
      checkAck(ack!,{...identity,native_pid:nativePid});
      requireValue(execFileSync('/bin/ps',['-p',String(nativePid),'-o','lstart='],{env:{LC_ALL:'C',NODE_ENV:'test'},encoding:'utf8',timeout:2000}).trim().replace(/\s+/g,' ')===ack!.native_birth,'Native process birth changed');
      browser=await chromium.connectOverCDP(`ws://127.0.0.1:${ack!.port}${ack!.browser_path}`,{noDefaults:true,timeout:15000});
      const contexts=browser.contexts();requireValue(contexts.length===1,'One existing default context required');
      const context=contexts[0],pages=context.pages();requireValue(pages.length===1&&pages[0].url()==='about:blank','One existing blank page required');
      const proof=await context.newCDPSession(pages[0]);
      try{
        const {targetInfo}=await proof.send('Target.getTargetInfo');
        requireValue(targetInfo.type==='page'&&typeof targetInfo.targetId==='string'&&targetInfo.targetId.length>0&&targetInfo.url==='about:blank','Owned initial page target required');
        const contextIdPresent=Object.hasOwn(targetInfo,'browserContextId');
        requireValue(!contextIdPresent||(typeof targetInfo.browserContextId==='string'&&targetInfo.browserContextId.length>0),'Actual optional context ID required');
        const ownedWindow=await proof.send('Browser.getWindowForTarget',{targetId:targetInfo.targetId});
        requireValue(Number.isInteger(ownedWindow.windowId),'Owned initial window required');
        persist(join(directory,'page-binding.safe.json'),{schema:'v41-shell-cdp-page-v1',...identity,native_pid:nativePid,ack_sha256:sha(bytes(ackPath)),target_id:targetInfo.targetId,context_id_present:contextIdPresent,context_id:targetInfo.browserContextId??null,window_id:ownedWindow.windowId,transport:'OWNED_DEFAULT_CONTEXT_CDP',no_defaults:true,initial_url:'about:blank',context_count:1,page_count:1});
        pageBindingSha=sha(bytes(join(directory,'page-binding.safe.json')));
      }finally{await proof.detach();}
      await pages[0].emulateMedia({reducedMotion:'reduce'});
      return context;
    }
    async function close(){
      if(testInfo.status!==testInfo.expectedStatus&&failures.length===0)failures.push({stage:'use',status:testInfo.status});
      try{
        requireValue(browser&&browser.isConnected(),'Owned connection unavailable; parent cleanup required');
        const session:CDPSession=await browser.newBrowserCDPSession();
        await session.send('Browser.close');closeAck=true;
        let timer:ReturnType<typeof setTimeout>|undefined;
        try{await Promise.race([exitPromise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Native exit timeout')),10000);})]);}finally{clearTimeout(timer);}
        requireValue(nativeExit===0&&nativeSignal===null,'Native exit failed or unknown');
        await browser.close();
      }catch(e){closeFailure={type:(e as Error).name,message:(e as Error).message};}
      finally{
        if(log!==undefined)closeSync(log);
        persist(join(directory,'closeout.safe.json'),{schema:'v41-shell-cdp-closeout-v1',...identity,native_pid:nativePid??null,ack_sha256:ack?sha(bytes(join(directory,'endpoint-ack.safe.json'))):null,page_binding_sha256:pageBindingSha,close_ack:closeAck,native_exit:nativeExit,signal:nativeSignal,failures,close_failure:closeFailure,status:!closeFailure&&failures.length===0&&nativeExit===0&&nativeSignal===null?'NATIVE_CLOSED_PENDING_PARENT_CHECK':'FAILED_OR_UNKNOWN'});
      }
      requireValue(!closeFailure,'Owned native teardown failed; parent cleanup required');
    }
    await usingOwnedContext(async()=>{try{return await setup();}catch(e){failures.push({stage:'setup',message:(e as Error).message});throw e;}},async context=>{try{await use(context);}catch(e){failures.push({stage:'use',message:(e as Error).message});throw e;}},close);
  },
  page:async({context},use)=>{const pages=context.pages();requireValue(pages.length===1,'Existing owned page required');await use(pages[0]);},
});
