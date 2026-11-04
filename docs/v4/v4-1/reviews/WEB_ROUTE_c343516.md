# V41 Shell路由P2关闭复审

日期：2026-11-04（台北）。精确候选 `c343516e78d4d227a7f705aef4dc3b73469b0e99` / tree `0381ba2ec0c50ca678b63b39eda5de0db75cfc20`，父链包含已审f949781 Shell及6ad309f待接线布局。仅本提交route resolver与routes.test增量；后续业务client不在本次范围。

结论：ACCEPT_SHELL_FIXTURE_CANDIDATE，P2-W01关闭。可由Root以此完整SHA登记有限local fixture/browser窗口；Reviewer未启动窗口，不签实际浏览器、会话链或业务六卡通过。

静态stage_views匹配新增排除参数占位符条件，字面模板无法再绕过后续UUID解析；保留静态保留字优先及原UUID正则。测试加入商品/订单字面模板和编码模板四负例，原真实UUID和import/variants/anomalies正例不减。

独立纯复现从该git对象读取routes.ts与manifest，用Node内置stripTypeScriptTypes只去类型后调用原resolver：四模板负例返回null，全部静态stage_views及十四模块仍可解析，商品/订单UUID正例通过。没有浏览器/服务。作者2pure/type/native的报告未在此冒充独立重跑。

此增量不改身份、CSRF、UNKNOWN、跨标签/迟到清屏或未接线按钮；先前Shell与布局静态审查可按父链复用。后续fixture需实测1440/1280/390/200%、菜单与助手完整焦点循环/Esc/回焦点、路由刷新/404、禁用动作及既有会话回归。不能用公开分类页可达代签业务权限或66视图完成。
