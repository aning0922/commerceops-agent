import manifest from './v41-routes.json' with { type: 'json' };

export type NavigationItem = (typeof manifest.modules)[number];
export const modules: readonly NavigationItem[] = manifest.modules;
export type ResolvedRoute = { title: string; module: NavigationItem | null; auxiliary: boolean };
const auxiliary: Record<string, string> = {
  '/v4': '欢迎', '/v4/demo': '演示空间', '/v4/settings/demo': '演示设置',
};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Resolve only the frozen static routes and the two declared resource patterns. */
export function resolveV41Route(pathname: string): ResolvedRoute | null {
  if (Object.hasOwn(auxiliary, pathname)) {
    return { title: auxiliary[pathname], module: modules.find(item => item.href === pathname) ?? null, auxiliary: true };
  }
  const module = modules.find(item => item.href === pathname);
  if (module) return { title: module.name, module, auxiliary: false };
  const staticView = manifest.stage_views.find(view => view.route === pathname);
  if (staticView) {
    const owner = modules.find(item => item.id === staticView.id.slice(4, 6));
    return owner ? { title: staticView.name, module: owner, auxiliary: false } : null;
  }
  const parts = pathname.split('/');
  if (parts.length !== 4 || parts[1] !== 'v4' || !uuid.test(parts[3])) return null;
  const resource = parts[2] === 'products' ? '04' : parts[2] === 'orders' ? '05' : null;
  const owner = modules.find(item => item.id === resource);
  return owner ? { title: resource === '04' ? '商品详情' : '订单详情', module: owner, auxiliary: false } : null;
}
