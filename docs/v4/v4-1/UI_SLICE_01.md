# V41-01 首个实现切片冻结

Root 释放 WEB 的首个 Shell 切片。范围依据 STAGE_SPEC、已审用户四合同、WEB_PLAN 和 UI_ROUTES.json。此冻结只允许导航／布局及既有 V4-0 会话接线；新增业务 DTO／接口尚待 API owner 的精确合同，不由 WEB 猜测。

## 可写路径

`frontend/app/v4/**`、`frontend/components/v4/**`、`frontend/lib/v41-routes.*`、`frontend/v41-tests/**`、`frontend/playwright.v41.config.ts`。WEB 为唯一写入者。保持 approvedApiOrigin 配置校验、现有请求／cookie／CSRF／UNKNOWN、persona/reset/logout、迟到响应／失效清屏和固定 TTL 语义；不得切换到原型登录密码或前端授权。旧 v4-client/schema 和旧业务页面暂不修改，已有 v4-tests 先原样回归；必要选择器改动另报 Root 释放，不能删除功能断言。

## 本片行为

- 十四个导航类别与中文信息层级依 UI_ROUTES.json；数据系统主入口为现有演示设置。经营／商品／订单在本片是待业务 API 接线的入口，其真实数据页面随后切片完成，不显示自造数值；其余后续模块有准确分类与阶段说明，不签业务视图已完成。
- 保留三条实际演示辅助入口以及显式进入／切店／切视角／重置／退出；全局 Shell 共用服务端当前身份，不新增自己的权限或 token 缓存。无授权店铺时不显示业务数据或授予写能力；类别说明不是能力授权。
- 新的业务子路由接受静态保留字优先和资源 UUID；未知路径 404。标签／筛选等业务逻辑等 API 合同后接入。
- 侧栏、面包屑、状态文字、来源/演示标记和真实操作反馈保持一致；移动菜单、模态和未来侧栏有焦点约束／Esc／关闭后回焦点，表格只局部滚动，reduced-motion 生效。
- 可提前建立 presentational Copilot 侧栏与上下文槽位，明确模型未启用；不能模拟对话或工具执行。真实上下文／快捷数据后续 API 接线，不呈现不可信业务对象。

首片只签真实会话上的 Shell/导航，不签 Dashboard/商品订单/导入已经完成。由原型提取布局与交互，不嵌 HTML，不用相同占位卡替代最终业务页。所有后续数据页依赖冻结 DTO，由同一 WEB owner 串行接入共享 controller。

## 提交和验证

先新文件与控件组件，再接路由／现有 Demo 容器；小可审提交，逐次保留当前身份失效保护。提交前原生 changed-public-file dir/index 预检零命中，格式/类型与相关纯/fixture 测试通过；失败序列不提交，定位原因后在授权范围修复继续。全 history 与真实 API/PG/browser Gate 后续按 Root 源码和新 UTC 统一执行，本片不擅自启动服务。源码供独立 reviewer 检查，旧 V40 浏览器与 fixture 证据不转签新 UI。
