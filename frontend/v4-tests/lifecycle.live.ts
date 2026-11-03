import {test,expect,chromium,type BrowserContext,type Page,type Response} from '@playwright/test';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import {join} from 'node:path';
import {readFileSync} from 'node:fs';
import {mkdtemp,rm,writeFile} from 'node:fs/promises';
import {sessionResponseMatches} from './lifecycle.waiter.mjs';
import {closeAndCleanOwnedProfile} from './lifecycle.profile.mjs';
const schema=JSON.parse(readFileSync(new URL('../lib/v4-schema.json',import.meta.url),'utf8'));

const api=new URL(process.env.V4_API_ORIGIN!).origin;
const evidence=process.env.V4_EVIDENCE_DIR!;
const ajv=new Ajv2020({strict:true,allowUnionTypes:true,validateFormats:true});addFormats(ajv);
const validators=new Map<string,ReturnType<typeof ajv.compile>>();
function validate(name:string,body:unknown){let v=validators.get(name);if(!v){v=ajv.compile({...schema,$ref:`#/$defs/${name}`});validators.set(name,v);}expect(v(body),`invalid ${name}`).toBe(true);}
function response(page:Page,method:string,path:string){return page.waitForResponse(r=>{const u=new URL(r.url());return u.origin===api&&u.pathname===`/api/v4/demo${path}`&&r.request().method()===method&&(path!=='/session'||r.ok());});}
async function read(r:Response,name:string){expect(r.ok(),`${name} HTTP ${r.status()}`).toBe(true);const body=await r.json();validate(name,body);expect(body.status).not.toBe('UNKNOWN');return body;}
function sameTenant(a:any,b:any){expect(b.tenant_id).toBe(a.tenant_id);expect(b.organization_id).toBe(a.organization_id);}

// Capture the native window surface; Playwright fullPage clips horizontally at browser zoom 200%.
async function captureNative200(page:Page,stem:string,segments:boolean){
 const cdp=await page.context().newCDPSession(page);
 const measure=()=>page.evaluate(()=>({y:scrollY,width:innerWidth,height:innerHeight,documentHeight:document.documentElement.scrollHeight,dpr:devicePixelRatio}));
 const paint=()=>page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
 let original:number|undefined;
 try {
  const initial=await measure();original=initial.y;
  if(initial.width<=0||initial.height<=0||initial.documentHeight<=0||initial.dpr<=0)throw new Error('invalid native capture dimensions');
  const captures:{y:number;width:number;height:number;documentHeight:number;pngWidth:number;pngHeight:number}[]=[];
  let target=segments?0:initial.y;
  for(let index=0;index<32;index++){
   if(segments){await page.evaluate(y=>window.scrollTo({top:y,behavior:'instant'}),target);await paint();}
   const position=await measure();
   if(position.width!==initial.width||position.height!==initial.height||position.documentHeight!==initial.documentHeight||position.dpr!==initial.dpr)throw new Error('native capture dimensions changed');
   if(segments&&index===0&&position.y!==0)throw new Error('native capture did not start at top');
   const previous=captures.at(-1);
   if(previous&&(position.y<=previous.y||position.y>previous.y+previous.height))throw new Error('native capture repeated position or gap');
   const shot=await cdp.send('Page.captureScreenshot',{format:'png',fromSurface:false});
   const png=Buffer.from(shot.data,'base64');
   if(png.length<24||png.readUInt32BE(0)!==0x89504e47)throw new Error('invalid native capture PNG');
   const pngWidth=png.readUInt32BE(16),pngHeight=png.readUInt32BE(20);
   if(pngWidth!==Math.round(position.width*position.dpr)||pngHeight<position.height*position.dpr)throw new Error('native capture viewport dimensions do not match');
   const after=await measure();
   if(after.y!==position.y||after.width!==position.width||after.height!==position.height||after.documentHeight!==position.documentHeight||after.dpr!==position.dpr)throw new Error('native capture moved during screenshot');
   const name=segments?`${stem}-segment-${String(index+1).padStart(2,'0')}.png`:`${stem}.png`;
   await writeFile(join(evidence,name),png);
   captures.push({y:position.y,width:position.width,height:position.height,documentHeight:position.documentHeight,pngWidth,pngHeight});
   if(!segments||position.y+position.height>=position.documentHeight)break;
   target=Math.min(position.y+Math.max(1,Math.floor(position.height*0.8)),position.documentHeight-position.height);
  }
  if(segments){
   const last=captures.at(-1);
   if(!last||last.y+last.height<last.documentHeight)throw new Error('native capture coverage limit reached');
   await writeFile(join(evidence,`${stem}-coverage.json`),JSON.stringify({originalScrollY:original,segments:captures},null,2));
  }
 } finally {
  try {if(original!==undefined&&segments){await page.evaluate(y=>window.scrollTo({top:y,behavior:'instant'}),original);await paint();if((await measure()).y!==original)throw new Error('native capture scroll restoration failed');}}
  finally {await cdp.detach();}
 }
}

test('LIVE: isolated demo lifecycle and browser layout',async ({page,context})=>{
 expect(api).not.toBe(new URL('http://example.invalid').origin);
 await page.goto('/v4');
 for(const width of [1440,1280,390]){
  await page.setViewportSize({width,height:900});
  await expect(page.getByRole('button',{name:'一键体验'})).toBeVisible();
  expect(await page.evaluate(()=>({inner:innerWidth,scroll:document.documentElement.scrollWidth,reduced:matchMedia('(prefers-reduced-motion: reduce)').matches}))).toEqual({inner:width,scroll:width,reduced:true});
  await page.screenshot({path:join(evidence,`live-welcome-${width}.png`),fullPage:true});
 }
 await page.setViewportSize({width:1440,height:900});
 const createdResponse=response(page,'POST','/sessions');const firstCurrent=response(page,'GET','/session');
 await page.getByRole('button',{name:'一键体验'}).click();
 const createdRaw=await createdResponse;const created=await read(createdRaw,'CreateEnvelope');
 const createBody=createdRaw.request().postDataJSON();expect(created.data.receipt.operation).toBe('session_create');expect(created.data.receipt.request_key).toBe(createBody.request_key);
 const current=await read(await firstCurrent,'SessionEnvelope');expect(current.data.creation_request_key).toBe(createBody.request_key);sameTenant(created.context,current.context);
 expect(current.data.persona_id).toBe('operator');expect(current.data.shops).toHaveLength(2);
 expect(current.context.reset_epoch).toBe(created.data.receipt.reset_epoch);expect(current.context.auth_generation).toBe(created.data.receipt.auth_generation);
 await expect(page.getByText('演示空间已建立。')).toBeVisible();
 const createdCookies=(await context.cookies(`${api}/api/v4/demo/session`)).filter(c=>c.name==='commerceops_v4_demo');expect(createdCookies.length).toBe(1);expect(createdCookies[0].httpOnly).toBe(true);expect(createdCookies[0].sameSite).toBe('Lax');expect(createdCookies[0].path).toBe('/api/v4');if(new URL(api).protocol==='https:')expect(createdCookies[0].secure).toBe(true);
 for(const shop of current.data.shops){
  const summaryResponse=response(page,'GET','/seed-summary');await page.getByLabel('店铺').selectOption(shop.shop_id);
  const raw=await summaryResponse;const data=await read(raw,'SeedSummaryEnvelope');sameTenant(current.context,data.context);expect(data.context.shop_id).toBe(shop.shop_id);
  expect(data.context.reset_epoch).toBe(current.context.reset_epoch);expect(data.context.auth_generation).toBe(current.context.auth_generation);
  expect(new URL(raw.url()).searchParams.get('shop_id')).toBe(shop.shop_id);
  expect(raw.request().headers()['x-demo-epoch']).toBe(String(current.context.reset_epoch));expect(raw.request().headers()['x-demo-generation']).toBe(String(current.context.auth_generation));
  await expect(page.getByText(new RegExp(`商品 ${data.data.counts.products} · SKU ${data.data.counts.skus}`))).toBeVisible();
 }
 let previous=current;
 async function switchPersona(target:string,shopCount:number){
  await page.getByLabel('体验视角').selectOption(target);const action=response(page,'POST','/persona');const updated=page.waitForResponse(r=>sessionResponseMatches(r,api,{creationKey:current.data.creation_request_key,tenant:previous.context.tenant_id,organization:previous.context.organization_id,persona:target,epoch:previous.context.reset_epoch,generation:previous.context.auth_generation+1}));await page.getByRole('button',{name:'切换视角'}).click();
  const raw=await action;const result=await read(raw,'ControlEnvelope');const body=raw.request().postDataJSON();expect(body.persona_id).toBe(target);expect(body.expected_epoch).toBe(previous.context.reset_epoch);expect(body.expected_generation).toBe(previous.context.auth_generation);
  expect(result.data.receipt.request_key).toBe(body.request_key);expect(result.data.receipt.operation).toBe('persona');expect(result.data.receipt.reset_epoch).toBe(result.context.reset_epoch);expect(result.data.receipt.auth_generation).toBe(result.context.auth_generation);sameTenant(previous.context,result.context);expect(result.context.reset_epoch).toBe(previous.context.reset_epoch);expect(result.context.auth_generation).toBe(previous.context.auth_generation+1);expect(result.context.principal_id).not.toBe(previous.context.principal_id);
  const session=await read(await updated,'SessionEnvelope');expect(session.data.persona_id).toBe(target);expect(session.data.shops).toHaveLength(shopCount);expect(session.data.creation_request_key).toBe(current.data.creation_request_key);expect(session.context).toMatchObject({tenant_id:result.context.tenant_id,organization_id:result.context.organization_id,principal_id:result.context.principal_id,reset_epoch:result.context.reset_epoch,auth_generation:result.context.auth_generation});
  await expect(page.getByText(new RegExp(`当前视角：${target}`))).toBeVisible();previous=session;
 }
 await switchPersona('approver',1);await switchPersona('restricted_admin',0);
 const reset=page.getByRole('button',{name:'重置演示'});await reset.focus();await expect(reset).toBeFocused();await page.keyboard.press('Enter');
 const dialog=page.getByRole('dialog',{name:'重置当前演示空间？'});await expect(dialog).toBeVisible();await page.keyboard.press('Tab');await expect(dialog).toContainText('确认重置');await page.keyboard.press('Escape');await expect(dialog).not.toBeVisible();await expect(reset).toBeFocused();
 await reset.click();const resetResponse=response(page,'POST','/reset');const resetCurrent=page.waitForResponse(r=>sessionResponseMatches(r,api,{creationKey:current.data.creation_request_key,tenant:previous.context.tenant_id,organization:previous.context.organization_id,persona:'restricted_admin',epoch:previous.context.reset_epoch+1,generation:previous.context.auth_generation+1}));await page.getByRole('button',{name:'确认重置'}).click();
 const resetRaw=await resetResponse;const resetResult=await read(resetRaw,'ControlEnvelope');const resetBody=resetRaw.request().postDataJSON();expect(resetBody.expected_epoch).toBe(previous.context.reset_epoch);expect(resetBody.expected_generation).toBe(previous.context.auth_generation);expect(resetResult.data.receipt.request_key).toBe(resetBody.request_key);expect(resetResult.data.receipt.operation).toBe('reset');expect(resetResult.data.receipt.reset_epoch).toBe(resetResult.context.reset_epoch);expect(resetResult.data.receipt.auth_generation).toBe(resetResult.context.auth_generation);sameTenant(previous.context,resetResult.context);expect(resetResult.context.reset_epoch).toBe(previous.context.reset_epoch+1);expect(resetResult.context.auth_generation).toBe(previous.context.auth_generation+1);expect(resetResult.context.principal_id).toBe(previous.context.principal_id);
 const resetSession=await read(await resetCurrent,'SessionEnvelope');expect(resetSession.data.persona_id).toBe('restricted_admin');expect(resetSession.data.shops).toHaveLength(0);expect(resetSession.data.creation_request_key).toBe(current.data.creation_request_key);sameTenant(resetResult.context,resetSession.context);expect(resetSession.context.principal_id).toBe(resetResult.context.principal_id);expect(resetSession.context.reset_epoch).toBe(resetResult.context.reset_epoch);expect(resetSession.context.auth_generation).toBe(resetResult.context.auth_generation);await expect(page.getByText('当前演示空间已重置。')).toBeVisible();previous=resetSession;
 await switchPersona('operator',2);
 const logoutResponse=response(page,'POST','/logout');await page.getByRole('button',{name:'退出'}).click();const logoutRaw=await logoutResponse;const logout=await read(logoutRaw,'ControlEnvelope');const logoutBody=logoutRaw.request().postDataJSON();expect(logout.data.receipt.operation).toBe('logout');expect(logout.data.receipt.request_key).toBe(logoutBody.request_key);expect(logoutBody.expected_epoch).toBe(previous.context.reset_epoch);expect(logoutBody.expected_generation).toBe(previous.context.auth_generation);sameTenant(previous.context,logout.context);expect(logout.context.reset_epoch).toBe(previous.context.reset_epoch);expect(logout.context.auth_generation).toBe(previous.context.auth_generation);await expect(page.getByText('已退出演示。')).toBeVisible();await expect(page.getByText(/当前视角：/)).toHaveCount(0);
 const sessionCookies=(await context.cookies(`${api}/api/v4/demo/session`)).filter(c=>c.name==='commerceops_v4_demo');expect(sessionCookies.every(c=>!c.value)).toBe(true);
 // A separate 390px tenant verifies the actual signed-in UI, not only the welcome layout.
 await page.setViewportSize({width:390,height:844});
 const mobileCreate=response(page,'POST','/sessions');
 const mobileCurrent=page.waitForResponse(async r=>{
  const url=new URL(r.url());if(url.origin!==api||url.pathname!=='/api/v4/demo/session'||r.request().method()!=='GET'||!r.ok())return false;
  const created=await read(await mobileCreate,'CreateEnvelope');
  return sessionResponseMatches(r,api,{creationKey:created.data.receipt.request_key,tenant:created.context.tenant_id,organization:created.context.organization_id,persona:'operator',epoch:created.context.reset_epoch,generation:created.context.auth_generation});
 });
 await page.getByRole('button',{name:'一键体验'}).click();
 const mobileRaw=await mobileCreate;const mobileCreated=await read(mobileRaw,'CreateEnvelope');const mobileBody=mobileRaw.request().postDataJSON();
 expect(mobileCreated.data.receipt.operation).toBe('session_create');expect(mobileCreated.data.receipt.request_key).toBe(mobileBody.request_key);expect(mobileBody.request_key).not.toBe(createBody.request_key);expect(mobileCreated.context.tenant_id).not.toBe(current.context.tenant_id);
 const mobile=await read(await mobileCurrent,'SessionEnvelope');expect(mobile.data.creation_request_key).toBe(mobileBody.request_key);expect(mobile.data.persona_id).toBe('operator');expect(mobile.data.shops).toHaveLength(2);expect(mobile.context.reset_epoch).toBe(mobileCreated.data.receipt.reset_epoch);expect(mobile.context.auth_generation).toBe(mobileCreated.data.receipt.auth_generation);
 await expect(page.getByText('演示空间已建立。')).toBeVisible();const mobileShop=mobile.data.shops[0];
 const mobileSummaryResponse=response(page,'GET','/seed-summary');await page.getByLabel('店铺').selectOption(mobileShop.shop_id);
 const mobileSummaryRaw=await mobileSummaryResponse;const mobileSummary=await read(mobileSummaryRaw,'SeedSummaryEnvelope');
 sameTenant(mobile.context,mobileSummary.context);expect(mobileSummary.context.shop_id).toBe(mobileShop.shop_id);expect(mobileSummary.context.reset_epoch).toBe(mobile.context.reset_epoch);expect(mobileSummary.context.auth_generation).toBe(mobile.context.auth_generation);expect(new URL(mobileSummaryRaw.url()).searchParams.get('shop_id')).toBe(mobileShop.shop_id);
 expect(mobileSummaryRaw.request().headers()['x-demo-epoch']).toBe(String(mobile.context.reset_epoch));expect(mobileSummaryRaw.request().headers()['x-demo-generation']).toBe(String(mobile.context.auth_generation));
 await expect(page.getByText(new RegExp(`商品 ${mobileSummary.data.counts.products} · SKU ${mobileSummary.data.counts.skus}`))).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:join(evidence,'live-mobile-session-390.png'),fullPage:true});
 // Use the visible mobile navigation and verify the same authorized session is restored.
 const settingsCurrent=page.waitForResponse(r=>sessionResponseMatches(r,api,{creationKey:mobileBody.request_key,tenant:mobile.context.tenant_id,organization:mobile.context.organization_id,persona:'operator',epoch:mobile.context.reset_epoch,generation:mobile.context.auth_generation}));
 const mobileNavigation=page.getByRole('navigation',{name:'演示导航'});const settingsLink=mobileNavigation.getByRole('link',{name:'演示设置'});await expect(settingsLink).toBeVisible();await settingsLink.focus();await expect(settingsLink).toBeFocused();await page.keyboard.press('Enter');await expect(page).toHaveURL(/\/v4\/settings\/demo$/);await expect(page.getByRole('navigation',{name:'演示导航'}).getByRole('link',{name:'演示设置'})).toHaveAttribute('aria-current','page');const settings=await read(await settingsCurrent,'SessionEnvelope');expect(settings.data.creation_request_key).toBe(mobileBody.request_key);expect(settings.context.principal_id).toBe(mobile.context.principal_id);
 const mobileReset=page.getByRole('button',{name:'重置演示'});await expect(mobileReset).toBeVisible();await mobileReset.focus();await expect(mobileReset).toBeFocused();await page.keyboard.press('Enter');
 const mobileDialog=page.getByRole('dialog',{name:'重置当前演示空间？'});await expect(mobileDialog).toBeVisible();await expect(mobileDialog.getByRole('button',{name:'确认重置'})).toBeVisible();await expect(mobileDialog.getByRole('button',{name:'取消'})).toBeVisible();
 await page.keyboard.press('Tab');expect(await mobileDialog.evaluate(element=>element.contains(document.activeElement))).toBe(true);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:join(evidence,'live-mobile-reset-dialog-390.png'),fullPage:true});
 await page.keyboard.press('Escape');await expect(mobileDialog).not.toBeVisible();await expect(mobileReset).toBeFocused();
 const mobileLogoutResponse=response(page,'POST','/logout');await page.getByRole('button',{name:'退出'}).click();const mobileLogoutRaw=await mobileLogoutResponse;const mobileLogout=await read(mobileLogoutRaw,'ControlEnvelope');const mobileLogoutBody=mobileLogoutRaw.request().postDataJSON();
 expect(mobileLogout.data.receipt.operation).toBe('logout');expect(mobileLogout.data.receipt.request_key).toBe(mobileLogoutBody.request_key);expect(mobileLogoutBody.expected_epoch).toBe(mobile.context.reset_epoch);expect(mobileLogoutBody.expected_generation).toBe(mobile.context.auth_generation);sameTenant(mobile.context,mobileLogout.context);expect(mobileLogout.context.reset_epoch).toBe(mobile.context.reset_epoch);expect(mobileLogout.context.auth_generation).toBe(mobile.context.auth_generation);
 await expect(page.getByText('已退出演示。')).toBeVisible();await expect(page.getByText(/当前视角：/)).toHaveCount(0);expect((await context.cookies(`${api}/api/v4/demo/session`)).filter(c=>c.name==='commerceops_v4_demo').every(c=>!c.value)).toBe(true);
 // Isolated headful Chromium profile: native browser zoom, not viewport or CSS emulation.
 const profile=await mkdtemp(join(evidence,'v4-zoom-profile-'));let zoomContext:BrowserContext|null=null;let zoomFailure:unknown;let zoomFailed=false;
 try {
  zoomContext=await chromium.launchPersistentContext(profile,{headless:false,viewport:null,args:['--window-size=1440,1000'],reducedMotion:'reduce'});
  const zoomPage=zoomContext.pages()[0]??await zoomContext.newPage();
  const dimensions=()=>zoomPage.evaluate(()=>({outerWidth,innerWidth,dpr:devicePixelRatio,visualScale:visualViewport?.scale,cssZoom:getComputedStyle(document.documentElement).zoom,scrollWidth:document.documentElement.scrollWidth}));
  await zoomPage.goto(process.env.V4_WEB_ORIGIN!+'/v4');await expect(zoomPage.getByRole('button',{name:'一键体验'})).toBeVisible();const zoomBefore=await dimensions();
  await zoomPage.goto('chrome://settings/appearance');const zoomControl=zoomPage.locator('select#zoomLevel');await expect(zoomControl).toHaveValue('1');await zoomControl.selectOption('2');await expect(zoomControl).toHaveValue('2');
  await captureNative200(zoomPage,'live-native-settings-200',false);
  await zoomPage.goto(process.env.V4_WEB_ORIGIN!+'/v4');await expect(zoomPage.getByRole('button',{name:'一键体验'})).toBeVisible();const zoomAfter=await dimensions();
  expect(zoomBefore.outerWidth).toBe(1440);expect(zoomBefore.visualScale).toBe(1);expect(zoomBefore.cssZoom).toBe('1');expect(zoomAfter.outerWidth).toBe(zoomBefore.outerWidth);expect(zoomAfter.innerWidth*2).toBe(zoomBefore.innerWidth);expect(zoomAfter.dpr).toBe(zoomBefore.dpr*2);expect(zoomAfter.visualScale).toBe(1);expect(zoomAfter.cssZoom).toBe('1');expect(zoomAfter.scrollWidth).toBeLessThanOrEqual(zoomAfter.innerWidth);
  await writeFile(join(evidence,'live-native-zoom-metrics.json'),JSON.stringify({nativeZoomSelection:'2',before:zoomBefore,after:zoomAfter},null,2));
  const zoomCreate=response(zoomPage,'POST','/sessions');
  const zoomCurrent=zoomPage.waitForResponse(async r=>{
   const url=new URL(r.url());if(url.origin!==api||url.pathname!=='/api/v4/demo/session'||r.request().method()!=='GET'||!r.ok())return false;
   const created=await read(await zoomCreate,'CreateEnvelope');return sessionResponseMatches(r,api,{creationKey:created.data.receipt.request_key,tenant:created.context.tenant_id,organization:created.context.organization_id,persona:'operator',epoch:created.context.reset_epoch,generation:created.context.auth_generation});
  });
  await zoomPage.getByRole('button',{name:'一键体验'}).click();const zoomCreateRaw=await zoomCreate;const zoomCreated=await read(zoomCreateRaw,'CreateEnvelope');const zoomBody=zoomCreateRaw.request().postDataJSON();
  expect(zoomCreated.data.receipt.operation).toBe('session_create');expect(zoomCreated.data.receipt.request_key).toBe(zoomBody.request_key);expect(zoomBody.request_key).not.toBe(createBody.request_key);expect(zoomBody.request_key).not.toBe(mobileBody.request_key);expect(zoomCreated.context.tenant_id).not.toBe(current.context.tenant_id);expect(zoomCreated.context.tenant_id).not.toBe(mobile.context.tenant_id);
  const zoomSession=await read(await zoomCurrent,'SessionEnvelope');expect(zoomSession.data.creation_request_key).toBe(zoomBody.request_key);expect(zoomSession.data.persona_id).toBe('operator');expect(zoomSession.data.shops).toHaveLength(2);expect(zoomSession.context.reset_epoch).toBe(zoomCreated.data.receipt.reset_epoch);expect(zoomSession.context.auth_generation).toBe(zoomCreated.data.receipt.auth_generation);await expect(zoomPage.getByText('演示空间已建立。')).toBeVisible();
  const zoomShop=zoomSession.data.shops[0];const zoomSummaryResponse=response(zoomPage,'GET','/seed-summary');await zoomPage.getByLabel('店铺').selectOption(zoomShop.shop_id);const zoomSummaryRaw=await zoomSummaryResponse;const zoomSummary=await read(zoomSummaryRaw,'SeedSummaryEnvelope');sameTenant(zoomSession.context,zoomSummary.context);expect(zoomSummary.context.shop_id).toBe(zoomShop.shop_id);expect(zoomSummary.context.reset_epoch).toBe(zoomSession.context.reset_epoch);expect(zoomSummary.context.auth_generation).toBe(zoomSession.context.auth_generation);expect(new URL(zoomSummaryRaw.url()).searchParams.get('shop_id')).toBe(zoomShop.shop_id);expect(zoomSummaryRaw.request().headers()['x-demo-epoch']).toBe(String(zoomSession.context.reset_epoch));expect(zoomSummaryRaw.request().headers()['x-demo-generation']).toBe(String(zoomSession.context.auth_generation));await expect(zoomPage.getByText(new RegExp(`商品 ${zoomSummary.data.counts.products} · SKU ${zoomSummary.data.counts.skus}`))).toBeVisible();
  expect((await dimensions()).scrollWidth).toBeLessThanOrEqual((await dimensions()).innerWidth);await captureNative200(zoomPage,'live-session-native-200',true);
  const zoomSettingsCurrent=zoomPage.waitForResponse(r=>sessionResponseMatches(r,api,{creationKey:zoomBody.request_key,tenant:zoomSession.context.tenant_id,organization:zoomSession.context.organization_id,persona:'operator',epoch:zoomSession.context.reset_epoch,generation:zoomSession.context.auth_generation}));
  const zoomNav=zoomPage.getByRole('navigation',{name:'演示导航'});const zoomSettings=zoomNav.getByRole('link',{name:'演示设置'});await expect(zoomSettings).toBeVisible();await zoomSettings.focus();await expect(zoomSettings).toBeFocused();await zoomPage.keyboard.press('Enter');await expect(zoomPage).toHaveURL(/\/v4\/settings\/demo$/);await expect(zoomPage.getByRole('navigation',{name:'演示导航'}).getByRole('link',{name:'演示设置'})).toHaveAttribute('aria-current','page');const zoomRestored=await read(await zoomSettingsCurrent,'SessionEnvelope');expect(zoomRestored.context.principal_id).toBe(zoomSession.context.principal_id);
  const zoomReset=zoomPage.getByRole('button',{name:'重置演示'});await zoomReset.focus();await expect(zoomReset).toBeFocused();await zoomPage.keyboard.press('Enter');const zoomDialog=zoomPage.getByRole('dialog',{name:'重置当前演示空间？'});await expect(zoomDialog).toBeVisible();await expect(zoomDialog.getByRole('button',{name:'确认重置'})).toBeVisible();await expect(zoomDialog.getByRole('button',{name:'取消'})).toBeVisible();await zoomPage.keyboard.press('Tab');expect(await zoomDialog.evaluate(element=>element.contains(document.activeElement))).toBe(true);
  expect((await dimensions()).scrollWidth).toBeLessThanOrEqual((await dimensions()).innerWidth);await captureNative200(zoomPage,'live-dialog-native-200',false);await zoomPage.keyboard.press('Escape');await expect(zoomDialog).not.toBeVisible();await expect(zoomReset).toBeFocused();
  const zoomLogoutResponse=response(zoomPage,'POST','/logout');await zoomPage.getByRole('button',{name:'退出'}).click();const zoomLogoutRaw=await zoomLogoutResponse;const zoomLogout=await read(zoomLogoutRaw,'ControlEnvelope');const zoomLogoutBody=zoomLogoutRaw.request().postDataJSON();expect(zoomLogout.data.receipt.operation).toBe('logout');expect(zoomLogout.data.receipt.request_key).toBe(zoomLogoutBody.request_key);expect(zoomLogoutBody.expected_epoch).toBe(zoomSession.context.reset_epoch);expect(zoomLogoutBody.expected_generation).toBe(zoomSession.context.auth_generation);sameTenant(zoomSession.context,zoomLogout.context);expect(zoomLogout.context.reset_epoch).toBe(zoomSession.context.reset_epoch);expect(zoomLogout.context.auth_generation).toBe(zoomSession.context.auth_generation);await expect(zoomPage.getByText('已退出演示。')).toBeVisible();await expect(zoomPage.getByText(/当前视角：/)).toHaveCount(0);expect((await zoomContext.cookies(`${api}/api/v4/demo/session`)).filter(c=>c.name==='commerceops_v4_demo').every(c=>!c.value)).toBe(true);
 } catch(error) {zoomFailed=true;zoomFailure=error;throw error;} finally {
  try {await closeAndCleanOwnedProfile(zoomContext,profile,rm);}
  catch(cleanupError) {if(zoomFailed)throw new AggregateError([zoomFailure,cleanupError],'Live zoom and profile cleanup failed');throw cleanupError;}
 }
});
