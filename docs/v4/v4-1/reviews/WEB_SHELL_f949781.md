# V41 首Shell独立源码审查

日期：2026-11-04（台北）。source `f949781fa0b9958fedeaf3303c4cf6cefdef8322`，tree `8b289514b2929dd43f4413ab56a4a97aa01b6548`。读取本提交12文件并对照UI_SLICE_01及UI_ROUTES；只读git对象，不采作者WIP。

结论：HOLD_ROUTE_PATTERN_P2；仅下述路由问题需修，其他首Shell结构可继续本地fixture验证准备。Reviewer不开放服务窗口；Root可按既定权限安排fixture浏览器，但在修复前不能核收静态/UUID路由正确性。本片不签完整业务页或runtime权限安全。

## P2-W01：manifest的动态模板被当作静态路径

`frontend/lib/v41-routes.ts`先对全部stage_views作字符串相等匹配，其中包含两个动态模板，因此实际请求 `/v4/products/:productId` 或 `/v4/orders/:orderId` 会命中详情分类，而不是进入UUID校验/404。App page依此判定notFound，违反只接受两种UUID资源路径的冻结边界。当前不返回敏感对象，但后续详情接线会继承错误入口。

纯复现：读取精确提交routes.ts，用Node内置stripTypeScriptTypes保留函数逻辑、注入同提交manifest后调用；两模板字面路径均返回商品/订单详情，普通unknown返回null。未启动浏览器或服务。

最小修复：静态匹配排除含参数占位符的模板（或直接生成分离静态/动态清单）；动态资源只走后续UUID分支。加两字面模板/编码占位符负例，继续保留import/variants/anomalies等静态保留字与真实UUID正例；不放宽UUID正则。

## 生命周期、权限与界面核查

- demo.tsx改动为Shell/分类包装和展示接线，原start/control/recover、当前session/summary、CSRF、UNKNOWN、清屏/轮询/跨标签逻辑没有变更；lib/v4-client与context未在本片改动。服务端origin校验仍在page入口。展示导航不赋权，分类内容为公开说明，无新增业务请求/对象数据/token缓存。
- 14模块依manifest显示，业务页明确待接入，其他类别明确规划；未显示伪KPI或宣称66视图完成。模型容器只有未启用说明，没有对话、工具成功轨迹或发送能力。
- 原演示三辅助入口及进入/切店/persona/reset/logout保留。a导航触发页面重读，不能将旧UI静态审核当作导航后session恢复实际已验。
- 移动导航和助手使用原生modal dialog、关闭/Esc及onClose回焦点；CSS有局部滚动、min-width0、窄屏布局和reduced-motion。源码机制合理；新浏览器测试仅单次Tab不能证明全循环焦点、1440/1280/390/原生200%和身份失效全矩阵，需要后续实测。
- playwright配置要求显式origin、单worker/retries0且不自行启动webServer；未知路由测试目前漏动态模板字面路径。没有permission/mock结果代替当前后端身份的实现。

本次完整静态审查及纯路由复现，没有运行tsc/fixture/browser/实际会话或全阶段测试。旧V40视觉/功能证据仍只绑定旧源码；本片修订后再按精确SHA核收。
