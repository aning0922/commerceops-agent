import {test,expect} from '@playwright/test';
import manifest from '../lib/v41-routes.json' with {type:'json'};

test('navigation exposes fourteen categories and an honest model-disabled panel',async({page})=>{
  await page.setViewportSize({width:1440,height:900});
  await page.goto('/v4');
  const nav=page.getByRole('navigation',{name:'业务导航'});
  await expect(nav.getByRole('link')).toHaveCount(14);
  for (const item of manifest.modules) await expect(nav.getByRole('link',{name:item.name})).toHaveAttribute('href',item.href);
  await page.getByRole('button',{name:'智能助手'}).click();
  const panel=page.getByRole('dialog',{name:'智能助手'});
  await expect(panel.getByText('模型未启用')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(panel).not.toBeVisible();
  await expect(page.getByRole('button',{name:'智能助手'})).toBeFocused();
});

test('mobile menu traps focus, closes on Escape and static routes stay honest',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/v4/products/import');
  await expect(page.getByText('商品导入',{exact:true})).toBeVisible();
  await expect(page.getByText('导入服务待接入',{exact:true})).toBeVisible();
  const opener=page.getByRole('button',{name:'打开业务导航'});
  await opener.click();
  const menu=page.getByRole('dialog',{name:'业务导航菜单'});
  await expect(menu.getByRole('link')).toHaveCount(14);
  await page.keyboard.press('Tab');
  expect(await menu.evaluate(el=>el.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(menu).not.toBeVisible();
  await expect(opener).toBeFocused();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('business workspaces show clear pending states without invented data or actions',async({page})=>{
  await page.goto('/v4/dashboard');
  await expect(page.getByRole('heading',{name:'经营驾驶舱'})).toBeVisible();
  await expect(page.getByText('选择授权店铺后读取经营指标。')).toBeVisible();
  await expect(page.getByLabel('数值未知')).toHaveCount(4);
  await page.goto('/v4/products');
  await expect(page.getByRole('heading',{name:'商品列表'})).toBeVisible();
  await expect(page.getByRole('button',{name:'导出 CSV'})).toBeDisabled();
  await page.goto('/v4/orders');
  await expect(page.getByRole('heading',{name:'订单列表'})).toBeVisible();
  await expect(page.getByRole('button',{name:'筛选'})).toBeDisabled();
  await page.goto('/v4/products/import');
  await expect(page.getByRole('heading',{name:'导入商品'})).toBeVisible();
  await expect(page.getByRole('button',{name:'选择文件'})).toBeDisabled();
});
