'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import {usePathname} from 'next/navigation';
import {ApiError,post,request,type Context,type Envelope,type Session,type Summary} from '../../lib/v4-client';
import styles from './demo.module.css';
import {Shell} from './shell';
import {ModuleIntro} from './module-intro';
import {BusinessPending, type DashboardData, type CatalogData, type CatalogDetailData} from './business-pending';
import {createV41Gate} from '../../lib/v41-context.mjs';
import {readV41, postV41, V41Error, type BusinessEnvelope} from '../../lib/v41-client';
import {loadV41Pending,reserveV41Pending,finishV41Pending} from '../../lib/v41-pending.mjs';
import {isSafeDashboard} from '../../lib/v41-dashboard.mjs';
import {isSafeCatalog,isSafeDetail} from '../../lib/v41-catalog.mjs';
import {matchesExportSnapshot} from '../../lib/v41-export.mjs';
import {resolveV41Route} from '../../lib/v41-routes';
import {sameIdentityContext,matchesControlBoundary,matchesControlReadback,matchesCreateBoundary,matchesRecoveredControl,shouldClearSummaryFailure} from '../../lib/v4-context.mjs';
import {readPending} from '../../lib/v4-pending.mjs';
import {sessionFailureMessage,shouldRevalidate} from '../../lib/v4-session-message.mjs';

type Pending = {operation:'session_create'|'persona'|'reset'|'logout'|'storage_unavailable'; key:string; proof?:{context:Context;creation_request_key:string;persona_id:string;target_persona:string|null}};
const pendingStorageSlot='commerceops-v4-pending';
const fixture='v4-demo-seed-1';
const flows=['经营诊断','缺货采购','滞销营销','客服售后','自然语言自动化','数据导入到看板'];
function loadPending():Pending|null { try {return readPending(sessionStorage,pendingStorageSlot) as Pending|null;} catch{return {operation:'storage_unavailable',key:''};} }
function savePending(p:Pending|null){if(p)sessionStorage.setItem(pendingStorageSlot,JSON.stringify(p));else sessionStorage.removeItem(pendingStorageSlot);}
export function Demo({origin}:{origin:string|null}){
 const pathname=usePathname();
 const [session,setSession]=useState<Envelope<Session>|null>(null), [summary,setSummary]=useState<Summary|null>(null), [shop,setShop]=useState(''), [message,setMessage]=useState(''), [busy,setBusy]=useState(false), [pending,setPending]=useState<Pending|null>(null), [persona,setPersona]=useState('operator');
 const compactHero=!!session&&!pending&&!resolveV41Route(pathname)?.auxiliary;
 const businessGate=useRef(createV41Gate()), recoveryGate=useRef(createV41Gate()), writeLock=useRef(false);
 const [writeState,setWriteState]=useState<'empty'|'pending'|'blocked'>('blocked'), [writeBusy,setWriteBusy]=useState(false), [writeMessage,setWriteMessage]=useState('');
 const [dashboard,setDashboard]=useState<DashboardData|null>(null), [dashboardState,setDashboardState]=useState<'idle'|'loading'|'error'>('idle');
 const [catalog,setCatalog]=useState<CatalogData|null>(null), [catalogState,setCatalogState]=useState<'idle'|'loading'|'error'>('idle'), [catalogQuery,setCatalogQuery]=useState(''), [catalogCursor,setCatalogCursor]=useState(''), [catalogHistory,setCatalogHistory]=useState<string[]>([]), [catalogRequest,setCatalogRequest]=useState(0);
 const [detail,setDetail]=useState<CatalogDetailData|null>(null), [detailState,setDetailState]=useState<'idle'|'loading'|'error'>('idle');
 const [exportState,setExportState]=useState<'idle'|'loading'|'error'>('idle');
 const activeKnown=useRef(false), actionLock=useRef(false), seq=useRef(0), current=useRef<Envelope<Session>|null>(null), selected=useRef(''), channel=useRef<BroadcastChannel|null>(null), dialog=useRef<HTMLDialogElement>(null), resetButton=useRef<HTMLButtonElement>(null);
 const clear=useCallback(()=>{businessGate.current.invalidate();recoveryGate.current.invalidate();setDashboard(null);setDashboardState('idle');setCatalog(null);setCatalogState('idle');setExportState('idle');setCatalogQuery('');setCatalogCursor('');setCatalogHistory([]);setDetail(null);setDetailState('idle');if(dialog.current?.open)dialog.current.close();seq.current++;current.current=null;selected.current='';setSession(null);setShop('');setSummary(null);},[]);
 const remember=useCallback((p:Pending|null)=>{savePending(p);setPending(p);},[]);
 const refresh=useCallback(async()=>{if(!origin)return null;businessGate.current.invalidate();recoveryGate.current.invalidate();setDashboard(null);setDashboardState('idle');setCatalog(null);setCatalogState('idle');setDetail(null);setDetailState('idle');const n=++seq.current;try {const v=await request<Envelope<Session>>(origin,'/session','SessionEnvelope');if(n!==seq.current||document.hidden||!navigator.onLine)return null;if(v.status!=='OK'||v.context.shop_id!==null)throw new Error('UNKNOWN');const identityChanged=!current.current||!sameIdentityContext(current.current.context,v.context)||current.current.data.persona_id!==v.data.persona_id;if(identityChanged)setPersona(v.data.persona_id);if((current.current&&identityChanged)||(selected.current&&!v.data.shops.some(item=>item.shop_id===selected.current))){selected.current='';setShop('');setSummary(null);}activeKnown.current=true;current.current=v;setSession(v);return v;} catch(error) {if(n===seq.current){const hadSession=activeKnown.current;if(error instanceof ApiError&&error.outcome==='REJECTED'&&(error.status===401||error.status===403))activeKnown.current=false;clear();setMessage(error instanceof ApiError?sessionFailureMessage(error.status,error.code,error.outcome,hadSession):sessionFailureMessage(null,null,null,hadSession));}return null;}},[clear,origin]);
 useEffect(()=>{try{setWriteState(loadV41Pending(sessionStorage).state as 'empty'|'pending'|'blocked');}catch{setWriteState('blocked');}},[]);
 useEffect(()=>{const p=loadPending();setPending(p);if(!p)void refresh();else setMessage(p.operation==='storage_unavailable'?'无法读取待核对记录；为避免重复操作，请先恢复浏览器会话存储。':'上次操作结果未知，请使用原操作核对。');try {channel.current=new BroadcastChannel('commerceops-v4-invalidate');channel.current.onmessage=()=>{clear();if(!document.hidden&&navigator.onLine&&!loadPending())void refresh();};}catch {} const check=()=>{if(document.hidden||!navigator.onLine){clear();return;}if(shouldRevalidate(activeKnown.current,true,true,!!loadPending()))void refresh();};document.addEventListener('visibilitychange',check);window.addEventListener('focus',check);window.addEventListener('online',check);window.addEventListener('offline',check);const timer=window.setInterval(()=>{if(shouldRevalidate(activeKnown.current,!document.hidden,navigator.onLine,!!loadPending()))void refresh();},5000);return()=>{window.clearInterval(timer);channel.current?.close();document.removeEventListener('visibilitychange',check);window.removeEventListener('focus',check);window.removeEventListener('online',check);window.removeEventListener('offline',check);};},[clear,refresh]);
 async function chooseShop(id:string){businessGate.current.invalidate();recoveryGate.current.invalidate();setDashboard(null);setDashboardState('idle');setCatalog(null);setCatalogState('idle');setExportState('idle');setCatalogQuery('');setCatalogCursor('');setCatalogHistory([]);setDetail(null);setDetailState('idle');setShop(id);selected.current=id;setSummary(null);seq.current++;const base=current.current;if(!base||!id||!base.data.shops.some(item=>item.shop_id===id))return;const n=++seq.current;try{const result=await request<Envelope<Summary>>(origin,`/seed-summary?shop_id=${encodeURIComponent(id)}`,'SeedSummaryEnvelope',{headers:{'X-Demo-Epoch':String(base.context.reset_epoch),'X-Demo-Generation':String(base.context.auth_generation)}});if(n!==seq.current){if(result.status!=='OK'&&shouldClearSummaryFailure(base.context,current.current?.context,selected.current,id)){clear();setMessage('当前身份或店铺无法验证，请重新核对会话。');}return;}if(result.status==='OK'&&current.current&&sameIdentityContext(base.context,current.current.context)&&sameIdentityContext(base.context,result.context)&&result.context.shop_id===id&&selected.current===id){setSummary(result.data);}else{clear();setMessage('当前身份或店铺无法验证，请重新核对会话。');}}catch(error){if(n===seq.current||shouldClearSummaryFailure(base.context,current.current?.context,selected.current,id)){if(error instanceof ApiError&&(error.status===401||error.status===403)){activeKnown.current=false;channel.current?.postMessage('invalidate');}clear();setMessage('当前身份或店铺无法验证，请重新核对会话。');}}}
 useEffect(()=>{
  if(pathname!=='/v4/dashboard'||!origin||!session||!shop||!businessGate.current.establish(session,shop)){businessGate.current.invalidate();setDashboard(null);setDashboardState('idle');return;}
  const gate=businessGate.current, ticket=gate.begin('dashboard'), controller=new AbortController();
  if(!ticket)return;
  setDashboard(null);setDashboardState('loading');
  void readV41<DashboardData>(origin,`/api/v4/dashboard?shop_id=${encodeURIComponent(shop)}`,'BusinessEnvelope_DashboardData_',session.context,controller.signal).then(value=>{
   if(gate.accepts(ticket,value)&&isSafeDashboard(value.data)){setDashboard(value.data);setDashboardState('idle');}
   else if(gate.accepts(ticket,{...value,status:'OK'})){setDashboard(null);setDashboardState('error');}
  }).catch(error=>{
   if(controller.signal.aborted)return;
   if(gate.accepts(ticket,{status:'OK',context:{...ticket.context,shop_id:ticket.shop}})){
    if(error instanceof V41Error&&(error.status===401||error.status===403)){activeKnown.current=false;clear();channel.current?.postMessage('invalidate');setMessage('当前身份或店铺无法验证，请重新核对会话。');}
    else{setDashboard(null);setDashboardState('error');}
   }
  });
  return ()=>{controller.abort();gate.invalidate();};
 },[origin,pathname,shop,session,clear]);
 useEffect(()=>{
  const product=['/v4/products','/v4/products/variants','/v4/products/categories'].includes(pathname), order=pathname==='/v4/orders';
  if((!product&&!order)||!origin||!session||!shop||!businessGate.current.establish(session,shop)){setCatalog(null);setCatalogState('idle');return;}
  const gate=businessGate.current,ticket=gate.begin('catalog'),controller=new AbortController();
  if(!ticket)return;
  setCatalog(null);setCatalogState('loading');
  const query=new URLSearchParams({shop_id:shop});if(catalogQuery)query.set('q',catalogQuery);if(catalogCursor)query.set('cursor',catalogCursor);
  void readV41<CatalogData>(origin,`/api/v4/${product?'products':'orders'}?${query}`,'BusinessEnvelope_Page_'+(product?'Product':'Order')+'__',session.context,controller.signal).then(value=>{
   if(gate.accepts(ticket,value)&&isSafeCatalog(value.data,product?'product':'order')){setCatalog(value.data);setCatalogState('idle');}
   else if(gate.accepts(ticket,{...value,status:'OK'})){setCatalog(null);setCatalogState('error');}
  }).catch(error=>{
   if(controller.signal.aborted)return;
   if(gate.accepts(ticket,{status:'OK',context:{...ticket.context,shop_id:ticket.shop}})){
    if(error instanceof V41Error&&(error.status===401||error.status===403)){activeKnown.current=false;clear();channel.current?.postMessage('invalidate');setMessage('当前身份或店铺无法验证，请重新核对会话。');}
    else{setCatalog(null);setCatalogState('error');}
   }
  });
  return ()=>{controller.abort();gate.invalidate();};
 },[origin,pathname,shop,session,catalogQuery,catalogCursor,catalogRequest,clear]);
 useEffect(()=>{
  const route=resolveV41Route(pathname),product=route?.title==='商品详情',order=route?.title==='订单详情';
  if((!product&&!order)||!origin||!session||!shop||!businessGate.current.establish(session,shop)){setDetail(null);setDetailState('idle');return;}
  const gate=businessGate.current,ticket=gate.begin('detail'),controller=new AbortController(),id=pathname.split('/')[3];
  if(!ticket)return;
  setDetail(null);setDetailState('loading');
  const kind=product?'product':'order';
  void readV41<CatalogDetailData>(origin,`/api/v4/${product?'products':'orders'}/${encodeURIComponent(id)}?shop_id=${encodeURIComponent(shop)}`,'BusinessEnvelope_'+(product?'Product':'Order')+'Detail_',session.context,controller.signal).then(value=>{
   if(gate.accepts(ticket,value)&&isSafeDetail(value.data,kind,id)){setDetail(value.data);setDetailState('idle');}
   else if(gate.accepts(ticket,{...value,status:'OK'})){setDetail(null);setDetailState('error');}
  }).catch(error=>{
   if(controller.signal.aborted)return;
   if(gate.accepts(ticket,{status:'OK',context:{...ticket.context,shop_id:ticket.shop}})){
    if(error instanceof V41Error&&(error.status===401||error.status===403)){activeKnown.current=false;clear();channel.current?.postMessage('invalidate');setMessage('当前身份或店铺无法验证，请重新核对会话。');}
    else{setDetail(null);setDetailState('error');}
   }
  });
  return ()=>{controller.abort();gate.invalidate();};
 },[origin,pathname,shop,session,clear]);
 const catalogEnabled=!!session&&!!shop&&!busy&&!pending&&session.data.shops.some(item=>item.shop_id===shop&&item.grants.some(grant=>grant==='operator'||grant==='approver'));
 function catalogSearch(q:string){businessGate.current.invalidate();setCatalog(null);setCatalogState('idle');setExportState('idle');setCatalogHistory([]);setCatalogCursor('');setCatalogQuery(q.slice(0,80));setCatalogRequest(value=>value+1);}
 function catalogNext(){if(!catalog?.next_cursor)return;businessGate.current.invalidate();setExportState('idle');setCatalogHistory(history=>[...history,catalogCursor]);setCatalogCursor(catalog.next_cursor);setCatalog(null);}
 function catalogPrevious(){if(!catalogHistory.length)return;businessGate.current.invalidate();setExportState('idle');setCatalogCursor(catalogHistory[catalogHistory.length-1]);setCatalogHistory(history=>history.slice(0,-1));setCatalog(null);}
 async function catalogExport(){
  const base=current.current,page=catalog,kind=pathname==='/v4/orders'?'order':pathname.startsWith('/v4/products')?'product':null;
  if(!origin||!base||!page||!kind||!catalogEnabled||exportState==='loading')return;
  const gate=businessGate.current,ticket=gate.begin('export');if(!ticket)return;
  const query=new URLSearchParams({shop_id:shop});if(catalogQuery)query.set('q',catalogQuery);
  setExportState('loading');
  try {
   const result=await readV41<{snapshot:CatalogData['snapshot'];format:string;filename:string;csv_text:string;row_count:number}>(origin,`/api/v4/${kind==='product'?'products':'orders'}/export?${query}`,'BusinessEnvelope_ExportData_',base.context);
   if(!gate.accepts(ticket,result))return;
   if(!matchesExportSnapshot(page,result.data,kind)){setExportState('error');return;}
   const url=URL.createObjectURL(new Blob([result.data.csv_text],{type:'text/csv;charset=utf-8'}));
   try{const link=document.createElement('a');link.href=url;link.download=result.data.filename;link.click();}finally{setTimeout(()=>URL.revokeObjectURL(url),0);}
   setExportState('idle');
  } catch(error){
   if(gate.accepts(ticket,{status:'OK',context:{...ticket.context,shop_id:ticket.shop}})){
    if(error instanceof V41Error&&(error.status===401||error.status===403)){activeKnown.current=false;clear();channel.current?.postMessage('invalidate');setMessage('当前身份或店铺无法验证，请重新核对会话。');}
    else setExportState('error');
   }
  }
 }
 async function settleWrite(record:{operation:string;request_key:string;resource_id:string;shop_id:string;context:Context},result:BusinessEnvelope<unknown>){
  const fresh=await refresh();if(!fresh||!origin||selected.current!==record.shop_id||!sameIdentityContext(record.context,fresh.context))return false;
  const gate=recoveryGate.current;if(!gate.establish(fresh,record.shop_id))return false;const ticket=gate.begin('write-readback');if(!ticket)return false;
  const product=record.operation==='product_tags';
  if(!product&&record.operation!=='order_fulfillment')return false;
  const resource=await readV41<CatalogDetailData>(origin,`/api/v4/${product?'products':'orders'}/${encodeURIComponent(record.resource_id)}?shop_id=${encodeURIComponent(record.shop_id)}`,'BusinessEnvelope_'+(product?'Product':'Order')+'Detail_',fresh.context);
  if(!gate.accepts(ticket,resource)||!isSafeDetail(resource.data,product?'product':'order',record.resource_id))return false;
  return finishV41Pending(sessionStorage,fresh,result,resource);
 }
 async function businessWrite(operation:'product_tags'|'order_fulfillment',tags?:string[]){
  const base=current.current,data=detail,product=operation==='product_tags',item=product?data?.product:data?.order;
  const resource=product?item?.product_id:item?.order_id,version=product?item?.version:item?.fulfillment_version;
  if(!origin||!base||!data||!resource||version===undefined||!shop||writeLock.current||writeState!=='empty'||loadPending()||!base.data.shops.some(s=>s.shop_id===shop&&s.grants.includes('operator')))return;
  const ticket=businessGate.current.begin('business-write');if(!ticket)return;
  let storage:Storage;try{storage=sessionStorage;}catch{setWriteState('blocked');setWriteMessage('无法保存待核对状态，未发送操作。');return;}
  const record={operation,request_key:crypto.randomUUID(),resource_id:resource,shop_id:shop,revision:data.snapshot.data_revision,version,context:{...base.context}};
  if(!reserveV41Pending(storage,record)){setWriteState(loadV41Pending(storage).state as 'empty'|'pending'|'blocked');setWriteMessage('无法安全登记操作，未发送。');return;}
  setWriteState('pending');writeLock.current=true;setWriteBusy(true);setWriteMessage('正在提交；请勿重复操作。');
  const payload={shop_id:shop,request_key:record.request_key,expected_epoch:base.context.reset_epoch,expected_generation:base.context.auth_generation,expected_data_revision:record.revision,expected_version:version,...(product?{tags:tags??[]}:{action:'mark_demo_fulfilled'})};
  try{
   const result=await postV41<unknown>(origin,`/api/v4/${product?'products':'orders'}/${encodeURIComponent(resource)}/${product?'tags':'fulfillment'}`,payload,base.data.csrf_token);
   if(!businessGate.current.accepts(ticket,{...result,status:'OK'})||!['OK','COMMITTED'].includes(result.status))throw new Error('UNKNOWN');
   if(await settleWrite(record,result)){setWriteState('empty');setWriteMessage('已核对提交回执和当前详情。');}
   else setWriteMessage('操作结果需要核对，请使用原操作查询。');
  }catch(error){
   if(error instanceof V41Error&&(error.status===401||error.status===403)){activeKnown.current=false;clear();channel.current?.postMessage('invalidate');}
   setWriteMessage('操作未确认或结果未知，请使用原操作查询，不要重复提交。');
  }finally{writeLock.current=false;setWriteBusy(false);}
 }
 async function recoverBusinessWrite(){
  if(writeLock.current||!origin)return;let storage:Storage;try{storage=sessionStorage;}catch{setWriteState('blocked');return;}
  const pending=loadV41Pending(storage);if(pending.state!=='pending'){setWriteState(pending.state as 'empty'|'pending'|'blocked');return;}
  const record=pending.value;if(!record.resource_id||!['product_tags','order_fulfillment'].includes(record.operation)){setWriteMessage('此操作需要原流程核对。');return;}
  writeLock.current=true;setWriteBusy(true);setWriteMessage('正在只读核对原操作。');
  try{
   const fresh=await refresh();if(!fresh||selected.current!==record.shop_id||!sameIdentityContext(record.context,fresh.context))throw new Error('CONTEXT_CHANGED');
   const gate=recoveryGate.current;if(!gate.establish(fresh,record.shop_id))throw new Error('NOT_AUTHORIZED');const ticket=gate.begin('write-lookup');if(!ticket)throw new Error('NOT_AUTHORIZED');
   const result=await readV41<unknown>(origin,`/api/v4/actions/${record.operation}/${record.request_key}?shop_id=${encodeURIComponent(record.shop_id)}`,'BusinessEnvelope_ActionLookup_',fresh.context);
   if(!gate.accepts(ticket,result))throw new Error('UNKNOWN');
   if(await settleWrite(record,result)){setWriteState('empty');setWriteMessage('已核对原操作和当前详情。');}
   else setWriteMessage('原操作仍需核对；未重复提交。');
  }catch{setWriteMessage('无法核对原操作；未重复提交。');}finally{writeLock.current=false;setWriteBusy(false);}
 }
 async function start(){if(!origin||actionLock.current||loadPending())return;actionLock.current=true;setBusy(true);setMessage('');try {const boot=await request<{status:string;data:{csrf_token:string}}>(origin,'/bootstrap','BootstrapEnvelope');if(boot.status!=='OK')throw new Error('UNKNOWN');const p:Pending={operation:'session_create',key:crypto.randomUUID()};remember(p);const created=await post<Envelope<{session:Session;receipt:{operation:string;request_key:string;status:string;reset_epoch:number;auth_generation:number}}>>(origin,'/sessions','CreateEnvelope',{request_key:p.key,fixture_version:fixture},boot.data.csrf_token);if(created.status==='UNKNOWN'||created.data.receipt.operation!==p.operation||created.data.receipt.request_key!==p.key||created.data.receipt.status!=='COMMITTED')throw new Error('UNKNOWN');const v=await refresh();if(v&&matchesCreateBoundary(created,v,p.key)){remember(null);setMessage('演示空间已建立。');}else{clear();setMessage('结果未知，请使用原操作核对。');}}catch(e){if(e instanceof ApiError && e.status===429 && e.outcome==='REJECTED'){remember(null);setMessage(`当前空间已满，请稍后重试（${e.retryAfter??'等待时间未知'}）。`);}else if(!loadPending())setMessage('无法开始演示，请稍后重试。');else setMessage('创建结果未知，请使用原操作核对。');}finally{channel.current?.postMessage('invalidate');actionLock.current=false;setBusy(false);}}
 async function control(operation:'persona'|'reset'|'logout') {const base=current.current;if(!base||actionLock.current||writeState!=='empty'||loadPending()||(operation==='persona'&&persona===base.data.persona_id))return;actionLock.current=true;setBusy(true);try {const p:Pending={operation,key:crypto.randomUUID(),proof:{context:base.context,creation_request_key:base.data.creation_request_key,persona_id:base.data.persona_id,target_persona:operation==='persona'?persona:null}};remember(p);clear();channel.current?.postMessage('invalidate');setMessage('正在处理…');const body={request_key:p.key,expected_epoch:base.context.reset_epoch,expected_generation:base.context.auth_generation,...(operation==='reset'?{fixture_version:fixture}:{}),...(operation==='persona'?{persona_id:persona}:{})};const result=await post<Envelope<{receipt:{operation:string;request_key:string;status:string;reset_epoch:number;auth_generation:number};next_step:string}>>(origin,`/${operation}`,'ControlEnvelope',body,base.data.csrf_token);if(!matchesControlBoundary(base.context,result,operation,p.key))throw new Error('UNKNOWN');if(operation==='logout'){activeKnown.current=false;remember(null);setMessage('已退出演示。');}else{const s=await refresh();if(s&&matchesControlReadback(base,result,s,operation,persona)){remember(null);setMessage(operation==='reset'?'当前演示空间已重置。':'身份视角已更新。');}else{clear();setMessage('操作结果需要核对。');}}}catch{setMessage('操作结果未知，请使用原操作核对。');}finally{channel.current?.postMessage('invalidate');actionLock.current=false;setBusy(false);}}
 async function recover(){if(!pending||pending.operation==='storage_unavailable'||actionLock.current)return;actionLock.current=true;setBusy(true);try {const s=await refresh();if(pending.operation==='session_create' && s && s.data.creation_request_key!==pending.key){clear();setMessage('当前会话与原创建请求不匹配，保持未知。');return;}const r=await request<{status:string;data:{receipt?:{operation:string;request_key:string;status:string;reset_epoch:number;auth_generation:number};operation?:string;request_key?:string;status?:string;recovery?:string}}>(origin,`/operations/${pending.operation}/${encodeURIComponent(pending.key)}`,'OperationEnvelope');if(r.status!=='UNKNOWN'&&r.data.receipt?.request_key===pending.key&&r.data.receipt.operation===pending.operation){if(pending.operation==='session_create'&&s&&r.data.receipt.reset_epoch===s.context.reset_epoch&&r.data.receipt.auth_generation===s.context.auth_generation){remember(null);setMessage('已核对原操作回执。');}else if((pending.operation==='reset'||pending.operation==='persona')&&s&&matchesRecoveredControl(pending.proof,r.data.receipt,s,pending.operation,pending.key)){remember(null);setMessage('已核对原操作回执。');}else{clear();setMessage('已读取回执，但原操作上下文或当前会话无法完整核验；状态仍需核对。');}}else {clear();setMessage(r.data.operation===pending.operation&&r.data.request_key===pending.key&&r.data.recovery==='OWNER_RECOVERY_REQUIRED'?'原空间可能已创建，但无法恢复会话。可明确选择重新开始新空间。':'结果仍未知，请稍后只读核对。');}}catch {clear();setMessage('无法核对原操作，结果仍未知。');}finally{actionLock.current=false;setBusy(false);}}
 return <Shell pathname={pathname}><main className={styles.main}><nav className={styles.mobileNav} aria-label="演示导航">{[["/v4","欢迎"],["/v4/demo","演示空间"],["/v4/settings/demo","演示设置"]].map(([href,label])=><a key={href} href={href} aria-current={pathname===href?"page":undefined}>{label}</a>)}</nav><section className={`${styles.hero} ${compactHero?styles.compactHero:''}`}><span className={styles.eyebrow}>COMMERCEOPS · INTERACTIVE DEMO</span><h1>{session?(compactHero?'当前演示空间':'欢迎回来，开始探索'):'让经营有依据，让行动更清晰。'}</h1><p className={styles.heroIntro}>互动演示使用合成数据，不连接真实店铺、不对外发送消息，也不调用真实模型。</p>{!origin&&<div role="status" className={styles.notice}>演示服务尚未配置，请联系管理员。</div>}{message&&<div role="status" aria-live="polite" className={styles.notice}>{message}</div>}{!session&&!pending&&<button className={styles.button} disabled={busy||!origin} onClick={()=>void start()}>一键体验 →</button>}{pending&&pending.operation!=='storage_unavailable'&&<div className={styles.row}><button className={styles.button} disabled={busy} onClick={()=>void recover()}>核对原操作</button><button className={styles.secondary} disabled={busy} onClick={()=>{activeKnown.current=false;remember(null);clear();setMessage('原操作状态仍未知；可再次点击一键体验建立新空间。');}}>放弃核对并重新开始</button></div>}{session&&!pending&&<><div className={styles.notice}>当前视角：{session.data.persona_id} · 到期：{session.data.expires_at} · 授权店铺 {session.data.shops.length} 家</div><div className={styles.row}><label>店铺 <select value={shop} onChange={e=>void chooseShop(e.target.value)}><option value="">选择店铺</option>{session.data.shops.map(s=><option key={s.shop_id} value={s.shop_id}>{s.display_name}</option>)}</select></label><label>体验视角 <select value={persona} onChange={e=>setPersona(e.target.value)}>{!['operator','approver','restricted_admin'].includes(session.data.persona_id)&&<option value={session.data.persona_id}>当前视角（{session.data.persona_id}）</option>}<option value="operator">运营</option><option value="approver">审批人</option><option value="restricted_admin">管理员</option></select></label><button className={styles.secondary} disabled={busy||writeState!=='empty'||persona===session.data.persona_id} onClick={()=>void control('persona')}>切换视角</button><button ref={resetButton} className={styles.secondary} disabled={busy||writeState!=='empty'} onClick={()=>dialog.current?.showModal()}>重置演示</button><button className={styles.secondary} disabled={busy||writeState!=='empty'} onClick={()=>void control('logout')}>退出</button></div>{session.data.shops.length===0&&<p>当前视角没有获授权店铺。</p>}{summary&&<p>合成种子 {summary.source.fixture_version} · 商品 {summary.counts.products} · SKU {summary.counts.skus} · 订单 {summary.counts.orders} · 订单行 {summary.counts.order_lines}</p>}</>}</section>{resolveV41Route(pathname)?.auxiliary && <section className={styles.grid} aria-label="规划中的演示场景">{flows.map((f,i)=><article className={styles.card} key={f}><span className={styles.eyebrow}>SCENARIO 0{i+1}</span><strong>{f}</strong><p>规划中 · 尚未开放</p></article>)}</section>}{['01','04','05'].includes(resolveV41Route(pathname)?.module?.id ?? '') && !resolveV41Route(pathname)?.auxiliary ? <BusinessPending pathname={pathname} dashboard={dashboard} dashboardState={dashboardState} catalog={{data:catalog,state:catalogState,enabled:catalogEnabled,scopeToken:shop,canWrite:catalogEnabled&&writeState==='empty'&&!!session?.data.shops.some(item=>item.shop_id===shop&&item.grants.includes('operator')),writeBusy,onTags:(tags:string[])=>void businessWrite('product_tags',tags),onFulfill:()=>void businessWrite('order_fulfillment'),exportState,onExport:catalogExport,detail,detailState,previous:catalogHistory.length>0,onSearch:catalogSearch,onNext:catalogNext,onPrevious:catalogPrevious}}/> : <ModuleIntro pathname={pathname}/>}{(writeState!=='empty'||writeMessage)&&<div role="status" className={styles.notice}>{writeMessage||'有业务操作等待原回执核对。'}{writeState==='pending'&&<button type="button" className={styles.secondary} disabled={writeBusy||!session} onClick={()=>void recoverBusinessWrite()}>核对原业务操作</button>}</div>}<p className={styles.muted}>本空间仅供互动体验，权限和会话状态以服务端为准。</p></main><dialog ref={dialog} className={styles.dialog} aria-labelledby="v4-reset-title" onClose={()=>resetButton.current?.focus()}><h2 id="v4-reset-title">重置当前演示空间？</h2><p>这将恢复当前演示空间的数据。其他访客的空间不会受影响。</p><div className={styles.row}><button className={styles.secondary} onClick={()=>dialog.current?.close()}>取消</button><button className={styles.button} onClick={()=>{dialog.current?.close();void control('reset');}}>确认重置</button></div></dialog></Shell>;
}
