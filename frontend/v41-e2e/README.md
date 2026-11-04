# QA 真实浏览器候选

独占目录，不修改WEB产品或其fixture specs。固定Shell live title、workers1/retries0/120s，
不mock route/response，创建真实DemoSession后点击/刷新14模块、验证当前服务端身份、三尺寸
1440/1280/390、菜单/Esc/焦点、restricted_admin无店铺、logout/cookie清除/刷新不自动重建。
使用原V4 strict SessionEnvelope核真实响应，source/case/window来自新的0600 Root manifest，
输出目录独占新建。截图只有显式合成页面，无trace/video/失败自动截图。

当前只有代码和工程typecheck；浏览器未启动，实际请求/权限/截图/cleanup全部NOT_RUN。
本spec不是完整业务验收，也不证明原生200%；安全结果明确native200=NOT_RUN_IN_THIS_SPEC。
原生200必须另以已审headful profile/zoom和截图几何接缝实现，不以viewport/CSS模拟。
需要新owned API/Web、本次源/镜像/资源/UTC及独立browser runner准备接受后才能执行；Shell
加载的真实业务仍取决于API/WEB实际接线，不将当前pending页称已完成KPI或商品订单行为。
