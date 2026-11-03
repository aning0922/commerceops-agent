import {test,expect,type Page,type Response} from '@playwright/test';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import {join} from 'node:path';
import {readFileSync} from 'node:fs';
import {sessionResponseMatches} from './lifecycle.waiter.mjs';
const schema=JSON.parse(readFileSync(new URL('../lib/v4-schema.json',import.meta.url),'utf8'));

const api=new URL(process.env.V4_API_ORIGIN!).origin;
const evidence=process.env.V4_EVIDENCE_DIR!;
const ajv=new Ajv2020({strict:true,allowUnionTypes:true,validateFormats:true});addFormats(ajv);
const validators=new Map<string,ReturnType<typeof ajv.compile>>();
function validate(name:string,body:unknown){let v=validators.get(name);if(!v){v=ajv.compile({...schema,$ref:`#/$defs/${name}`});validators.set(name,v);}expect(v(body),`invalid ${name}`).toBe(true);}
function response(page:Page,method:string,path:string){return page.waitForResponse(r=>{const u=new URL(r.url());return u.origin===api&&u.pathname===`/api/v4/demo${path}`&&r.request().method()===method&&(path!=='/session'||r.ok());});}
async function read(r:Response,name:string){expect(r.ok(),`${name} HTTP ${r.status()}`).toBe(true);const body=await r.json();validate(name,body);expect(body.status).not.toBe('UNKNOWN');return body;}
function sameTenant(a:any,b:any){expect(b.tenant_id).toBe(a.tenant_id);expect(b.organization_id).toBe(a.organization_id);}

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
});
