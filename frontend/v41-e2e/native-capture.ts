import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {constants,closeSync,fstatSync,openSync,readFileSync,realpathSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import type {Cookie} from '@playwright/test';
import {readBrowserCase,type BrowserCase,type SubjectContext} from './browser-subjects';

const moduleFile=fileURLToPath(new URL('../../tests/e2e/v41/native_zoom.cjs',import.meta.url));
const moduleHash='295bf2c61e7cd30e7a47d7368d93fbadb40764fb41072a9119b5d78ed925689e';
const digest=(raw:Buffer|string)=>createHash('sha256').update(raw).digest('hex');
export type NativeCapture={status:'NATIVE_ZOOM_CAPTURED_PENDING_VISUAL_REVIEW';receiptPath:string;nativeBrowserExit:'NOT_EXPOSED';visualAcceptance:'PENDING_REVIEW';receiptSha256:string};
type CompleteCase=BrowserCase&{inputs:Record<string,string>;database:string;pg_image:string;test_image:string;pg_subnet:string;host_subnet:string};
type Runtime={executablePath:string;executableSha256:string;frameworkPath:string;frameworkSha256:string;nodeSha256:string;playwrightVersion:'1.64.0'};
type NativeRun={run:(input:{case:CompleteCase;browserRuntime:Runtime;shell:{cookies:Cookie[];context:SubjectContext&{shop_id:null}};currentShopId:string})=>Promise<Omit<NativeCapture,'receiptSha256'>>};
function requireValue(value:unknown,message:string):asserts value{if(!value)throw new Error(message);}
function privateBytes(filename:string,limit=2000000){
  requireValue(realpathSync(dirname(filename))===dirname(filename),'Canonical native receipt parent required');
  const fd=openSync(filename,constants.O_RDONLY|constants.O_NOFOLLOW);
  try{
    const info=fstatSync(fd);
    requireValue(info.isFile()&&info.uid===process.getuid?.()&&(info.mode&0o777)===0o600&&info.size<=limit,'Private native input required');
    return readFileSync(fd);
  }finally{closeSync(fd);}
}

function privateJSON(filename:string){const raw=privateBytes(filename);return {raw,value:JSON.parse(raw.toString('utf8'))};}

export async function captureNative200(c:BrowserCase,cookies:Cookie[],context:SubjectContext&{shop_id:null},currentShopId:string):Promise<NativeCapture>{
  // Re-read the same complete case, including inputs/database/images; never construct a reduced case.
  const complete=readBrowserCase() as CompleteCase;
  requireValue(JSON.stringify(complete)===JSON.stringify(c),'Native case changed');
  const keys=['source_sha','source_tree','inputs','scenario','project','database','directory','pg_image','test_image','api_port','web_port','pg_subnet','host_subnet','starts_at','deadline','parent_deadline','uid'];
  requireValue(Object.keys(complete).sort().join(',')===keys.sort().join(',')&&complete.inputs&&typeof complete.inputs==='object'&&!Array.isArray(complete.inputs),'Complete native case required');
  const {value:binding}=privateJSON(join(c.directory,'browser-runtime.safe.json'));
  requireValue(binding.source_sha===c.source_sha&&binding.source_tree===c.source_tree&&binding.directory===c.directory&&binding.uid===c.uid,'Native runtime identity changed');
  const browserRuntime:Runtime={executablePath:binding.executable,executableSha256:binding.sha256,frameworkPath:binding.framework,frameworkSha256:binding.framework_sha256,nodeSha256:binding.node_sha256,playwrightVersion:binding.playwright_version};
  requireValue(browserRuntime.playwrightVersion==='1.64.0'&&realpathSync(moduleFile)===moduleFile&&digest(readFileSync(moduleFile))===moduleHash,'Reviewed native module required');
  const native=createRequire(import.meta.url)(moduleFile) as NativeRun;
  const result=await native.run({case:complete,browserRuntime,shell:{cookies,context},currentShopId});
  const receiptPath=join(c.directory,'native-zoom/receipt.json');
  requireValue(result.status==='NATIVE_ZOOM_CAPTURED_PENDING_VISUAL_REVIEW'&&result.receiptPath===receiptPath&&result.nativeBrowserExit==='NOT_EXPOSED'&&result.visualAcceptance==='PENDING_REVIEW','Native capture was not completed');
  const {raw,value:receipt}=privateJSON(receiptPath);
  requireValue(receipt.status===result.status&&receipt.scope==='SAME_SHELL_VISITOR_READONLY_NATIVE_200'&&receipt.source?.head===c.source_sha&&receipt.source?.tree===c.source_tree&&receipt.source?.moduleSha256===moduleHash,'Native receipt source changed');
  requireValue(receipt.currentShopSha256===digest(currentShopId)&&receipt.shellContextSha256===digest(JSON.stringify(['tenant_id','organization_id','principal_id','reset_epoch','auth_generation'].map(k=>context[k as keyof SubjectContext]))),'Native visitor changed');
  requireValue(receipt.nativeBrowserExit==='NOT_EXPOSED'&&receipt.humanVisualAcceptance==='NOT_RUN'&&receipt.cleanup?.confirmed===true&&(!('forced' in receipt.cleanup)||receipt.cleanup.forced===false)&&(!('emergencyEvents' in receipt.cleanup)||(Array.isArray(receipt.cleanup.emergencyEvents)&&receipt.cleanup.emergencyEvents.length===0))&&receipt.cleanup.profileProcesses?.length===0&&receipt.cleanup.registeredAlive?.length===0&&!receipt.failure&&!receipt.cleanup.failure&&!receipt.cleanup.closeFailure,'Native cleanup not confirmed');
  requireValue(receipt.requests?.allowedReads>0&&receipt.requests.refused?.length===0,'Native non-read request observed');
  requireValue(receipt.profile?.path===join(c.directory,'browser-tmp/playwright_chromiumdev_profile-native200')&&receipt.profile.mode===0o700&&receipt.profile.uid===c.uid,'Native profile differed');
  requireValue(Array.isArray(receipt.pages)&&receipt.pages.map((p:{label:string})=>p.label).join(',')==='dashboard,products','Both native pages required');
  for(const p of receipt.pages){
    requireValue(p.baseline.actual===1&&p.zoom.actual===2&&Number.isInteger(p.zoom.tabId)&&p.baseline.tabId===p.zoom.tabId&&p.rowCount>0,'Actual native factor and rows required');
    for(const z of [p.baseline,p.zoom])requireValue(z.settings.mode==='automatic'&&z.settings.scope==='per-tab','Actual browser per-tab zoom required');
    requireValue(p.zoom.events.some((e:{tabId:number;oldZoomFactor:number;newZoomFactor:number})=>e.tabId===p.zoom.tabId&&e.oldZoomFactor===1&&e.newZoomFactor===2),'Actual native zoom event required');
    requireValue(p.before.outerWidth===1440&&p.before.outerHeight===1000&&p.after.outerWidth===1440&&p.after.outerHeight===1000&&Math.abs(p.after.innerWidth*2-p.before.innerWidth)<=2&&Math.abs(p.after.innerHeight*2-p.before.innerHeight)<=2&&Math.abs(p.after.devicePixelRatio-p.before.devicePixelRatio*2)<0.000001,'Actual native layout geometry required');
    for(const g of [p.before,p.after])for(const css of [g.rootCss,g.bodyCss])requireValue(['1','normal'].includes(css.zoom)&&css.transform==='none','CSS zoom or transform is not native proof');
    const expected=p.label==='dashboard'?['dashboard-100.png','dashboard-200.png']:['products-100.png','products-200.png','products-200-bottom.png'];
    requireValue(p.screenshots.map((s:{path:string})=>s.path).join(',')===expected.map(n=>'screenshots/'+n).join(','),'Exact native PNG set required');
    for(const shot of p.screenshots){
      const filename=join(c.directory,'native-zoom',shot.path),bytes=privateBytes(filename,8000000);
      requireValue(realpathSync(filename)===filename&&bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))&&digest(bytes)===shot.sha256&&bytes.readUInt32BE(16)===shot.pixelWidth&&bytes.readUInt32BE(20)===shot.pixelHeight,'Native PNG bytes differed');
    }
  }
  return {...result,receiptSha256:digest(raw)};
}
