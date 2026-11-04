> 状态：PROPOSED / A阶段候选合同；V4-0代码NOT_STARTED。冻结的是文档内容，须用户审核并另发B授权后才允许实施。绑定远端M3 `952e6246deb01ec763f2541d9f316753987744f3`；不修改旧业务合同。

# UI + routes · v4-v1 候选

## 已存在 already_existing

Next App Router的frontend/app/[[...path]]/page.tsx、现有P3 shell/session/live client、日报/询单/copy组件及专属schema/client。保留原/tasks、/approvals等和原M3功能，不复制博客或ANING LAB内容；本轮任务已经明确切回CommerceOps。

## 新页面 proposed

66逻辑视图/14模块的全量拟定映射见 reviews/PAGE_ROUTE_MATRIX.json，所有/v4路径均未实现。该映射是页面审查清单，不意味着V4-0会交66个正式页面。V4-0首批仅/v4（欢迎、一键体验）、/v4/demo（当前身份/双店seed摘要/到期状态）、/v4/settings/demo（本会话重置/退出）；在App Router可采用frontend/app/v4/[[...path]]/page.tsx的单一专属入口，由WEB owner独占。原catch-all必须回归路由优先级且禁止替换为原型HTML。

V4-1再交14模块导航、经营驾驶舱和Copilot容器。目录中dashboard/商品/订单/知识等处于后续阶段，不提前添加假入口冒充完成；V4-0欢迎页展示六链的规划说明与可运行状态，未运行项明确未开放，不拿占位页签完成量。

## 首次打开和会话状态

欢迎明确“互动演示·合成数据·无真实外发/模型”；从服务端bootstrap获取CSRF，再POST一次会话创建，成功GET current后展示两个授权店铺与seed版本/真实数量摘要。用户可选预登记persona体验，前端不持角色权威。不使用localStorage保存会话token/权限，不使用原型demo密码。

状态机：anonymous → creating → active → switching/resetting/unknown → active或expired/revoked/logged_out/error。创建/写入unknown保留原operation/key/context，仅安全GET回读，不自动创建新空间。清单空、未配置、质量不足、服务错误、UNKNOWN分别展示。切shop/persona/epoch后清理结果/抽屉/敏感选择，迟到响应必须与服务端返回generation/shop相符才显示。

## 交互、视觉和可访问性

参考V4.5深色侧栏/浅色主体/克制蓝青绿，但重组为现有React组件，不内嵌Standalone HTML。1440、1280、390及200%缩放；移动菜单可关闭、Esc与焦点回归、Tab不逃出模态；表格局部滚动不撑宽全页。状态有文字和aria反馈、可见焦点；prefers-reduced-motion关闭非必要动画。重置必须明确二次确认“仅当前演示空间”，操作中禁止新写/重复提交，UNKNOWN留只读核对入口。

## owner与未来验证

WEB仅写新frontend/app/v4/**、components/v4/**、lib/v4-*与专属测试；共享layout/global styles和旧session client默认只读，有必要变更必须ROOT精确释放。类型来自SCHEMA/API批准的v4-public-openapi.json，不由UI自行猜API。欢迎→建立会话→切双店→切persona→重置→退出至少一个真实API/PG/Web全链；与原M3对应回归分开记录，Full/Hosted未运行不得标绿。

## A独审修订：多标签与失败状态

带敏感数据的成功请求捕获已核server context与request_seq，只有response的tenant/principal/shop/epoch/generation及当前选择一致、请求仍最新才显示。匿名bootstrap、最小控制回执和错误不制造虚假context，按专用状态/原key及operation校验处理。persona/reset/logout开始同步清敏感状态、禁止新业务请求，再发送控制POST；不因AbortController成功就认定服务器停止。创建丢ACK分两种cookie状态，严格按API恢复节，unknown页面不自动重新进入或填假seed数据。

同源标签通过BroadcastChannel只广播不含身份/token/业务数据的invalidate信号，接收即清屏并GET current重新核验；消息不能设置权限。标签hidden/offline时立即遮蔽并清敏感内容；visibility/focus/online恢复时先GET current，确认后重读授权数据。可见active页每5秒只读核current；轮询失败立即清屏/保持未验证，不能复用旧context。通知丢失情况下以当前GET与服务端generation校验收敛；这不保证跨设备已渲染像素即时消失，不把轮询冒充实时撤屏。当前服务端对所有新读写即时拒绝旧generation/epoch；跨标签显示有显式验证时延边界。B需注入BC消息丢失/后台→前台/已发读取后切换的负例。

/v4/settings/demo仅是V4-P14-06的session/reset/logout子集；/v4、/v4/demo为辅助欢迎入口，不计为66个业务页已完成。固定路由优先于动态资源ID；variants/categories/import/segments是保留字，动态ID须UUID或冻结opaque格式并核资源owner，不能吞掉静态路由。

逐状态验收：bootstrap或seed创建失败不显示成功；429显示剩余等待且不自动新建；401/403清屏且无重新登录/切角色提权；reset UNKNOWN保留原key/禁写/GET核对；无权店铺404不泄漏；模态Tab/Esc/焦点回归、到期提示aria-live与移动菜单均有实测。BC/轮询均为客户端防泄漏辅助手段，不替代任何服务端授权。
