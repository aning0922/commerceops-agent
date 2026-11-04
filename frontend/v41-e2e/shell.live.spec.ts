import {test,expect,type Response} from '@playwright/test';
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import routes from '../lib/v41-routes.json' with {type:'json'};
import schema from '../lib/v4-schema.json' with {type:'json'};

const supplied=process.env.V41_CASE_FILE;
if(!supplied)throw new Error('Explicit Root case required');
const c=JSON.parse(readFileSync(supplied,'utf8')),api=`http://127.0.0.1:${c.api_port}`;
const evidence=join(c.directory,'browser-shell');
const ajv=new Ajv2020({strict:true,allErrors:true});addFormats(ajv);
async function session(r:Response){
  expect(r.status()).toBe(200);
  const body=await r.json();
  expect(ajv.compile({...schema,$ref:'#/$defs/SessionEnvelope'})(body)).toBe(true);
  return body;
}

test('LIVE V41: shell identity navigation and responsive boundaries',async({page,context})=>{
  mkdirSync(evidence,{mode:0o700});
  const screenshots:{path:string;sha256:string}[]=[];
  let creates=0;
  page.on('request',r=>{const u=new URL(r.url());if(u.origin===api&&u.pathname==='/api/v4/demo/sessions'&&r.method()==='POST')creates++;});
  await page.setViewportSize({width:1440,height:900});
  await page.goto('/v4');
  const first=page.waitForResponse(r=>r.url()===api+'/api/v4/demo/session'&&r.request().method()==='GET'&&r.ok());
  await page.getByRole('button',{name:'一键体验'}).click();
  const current=await session(await first);
  expect(current.data.persona_id).toBe('operator');expect(current.data.shops).toHaveLength(2);
  await expect(page.getByText('当前视角：operator',{exact:false})).toBeVisible();
  for(const item of routes.modules){
    const nav=page.locator('nav[aria-label="业务导航"]:visible');
    await expect(nav.getByRole('link')).toHaveCount(14);
    await nav.getByRole('link',{name:item.name,exact:false}).click();
    await expect(page).toHaveURL(new URL(item.href,`http://127.0.0.1:${c.web_port}`).href);
    await page.reload();
    await expect(page.getByText('当前视角：operator',{exact:false})).toBeVisible();
    await expect(page.locator('nav[aria-label="业务导航"]:visible').locator('[aria-current="page"]')).toHaveCount(1);
  }
  for(const width of [1440,1280,390]){
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    if(width===390){
      const opener=page.getByRole('button',{name:'打开业务导航'});
      await opener.focus();await page.keyboard.press('Enter');
      const menu=page.getByRole('dialog',{name:'业务导航菜单'});
      await expect(menu).toBeVisible();await expect(menu.getByRole('link')).toHaveCount(14);
      await page.keyboard.press('Tab');
      expect(await menu.evaluate(el=>el.contains(document.activeElement))).toBe(true);
      await page.keyboard.press('Escape');await expect(menu).not.toBeVisible();await expect(opener).toBeFocused();
    }
    const assistant=page.getByRole('button',{name:'智能助手'});
    await assistant.focus();await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog',{name:'智能助手'}).getByText('模型未启用')).toBeVisible();
    await page.keyboard.press('Escape');await expect(assistant).toBeFocused();
    const path=join(evidence,`shell-${width}.png`);
    const bytes=await page.screenshot({path,fullPage:true});
    screenshots.push({path,sha256:createHash('sha256').update(bytes).digest('hex')});
  }
  await page.getByLabel('体验视角').selectOption('restricted_admin');
  const switched=page.waitForResponse(r=>r.url()===api+'/api/v4/demo/session'&&r.request().method()==='GET'&&r.ok());
  await page.getByRole('button',{name:'切换视角'}).click();
  const admin=await session(await switched);expect(admin.data.persona_id).toBe('restricted_admin');expect(admin.data.shops).toHaveLength(0);
  await expect(page.getByText('当前视角没有获授权店铺。')).toBeVisible();
  const loggedOut=page.waitForResponse(r=>r.url()===api+'/api/v4/demo/logout'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'退出',exact:true}).click();expect((await loggedOut).status()).toBe(200);
  await expect(page.getByText('当前视角：',{exact:false})).toHaveCount(0);
  expect((await context.cookies(api)).filter(x=>x.name==='commerceops_v4_demo')).toHaveLength(0);
  await page.reload();await expect(page.getByRole('button',{name:'一键体验'})).toBeVisible();expect(creates).toBe(1);
  writeFileSync(join(evidence,'shell.safe.json'),JSON.stringify({source_sha:c.source_sha,source_tree:c.source_tree,scope:'LIVE_SHELL_ONLY',screenshots,native200:'NOT_RUN_IN_THIS_SPEC',businessKPI:'NOT_VERIFIED_BY_SHELL',actual_create_requests:creates},null,2),{mode:0o600});
});
