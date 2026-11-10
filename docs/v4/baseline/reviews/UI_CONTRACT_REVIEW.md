# UI/API 合同独立增量审查

结论：**HOLD，2 项 P1 待修**；仅审查候选文本和路由矩阵，未运行代码或验收。行号以下列精确内容为准，SHA-256：

- UI_ROUTES_CONTRACT.md `360f9a0610f5d76177f61f6e1171e57ee8cd517aaba58dd1b13d3be09f6c3a3e`
- API_EVENTS_CONTRACT.md `e8e154f9f51ccc196da49bac932f9e461f64a5682cc952f12cc7a1cc38a90e44`
- PERMISSION_DEMO_CONTRACT.md `1a571724f3bf2c3349a8ef262ad6c52ea31555040c9b75deb8d5c9083397673b`
- DOMAIN_SOURCE_CONTRACT.md `9fb3f09a361e4ababa661a8efafdd5184e2911ca7b2fd02de33fc9a626e97321`
- reviews/PAGE_ROUTE_MATRIX.json `11ab23e48969ca1fed997db34c1380cc16c503341887a36924688b42dd05c930`

## P1-1 创建丢 ACK 的 bootstrap 回读路径未定义

API 行 20 的 operation 查询只允许有效 owner 会话，行 22 却要求 header/cookie 整体丢失时以 bootstrap owner 和原 key 查询；此时可能没有可用 demo session。UI 行 17–19 也未定义两种 cookie 丢失情况的分流。若将 bootstrap 当作普通有效会话会扩大权限，若只接受 demo cookie 则无法实现承诺的只读查询。修订为明确独立、短期、单次/有界的 bootstrap owner 查询资格、cookie path/expiry、操作绑定及最小响应，禁止据此获取业务数据或恢复明文 token；或明确无法认证时直接 UNKNOWN/OWNER_RECOVERY_REQUIRED。分别规定 cookie 已应用而 body 丢失时先 GET current 并核对原 key，与 cookie 未应用时的受限恢复、过期及用户显式新建。新增跨 bootstrap/原 key 探测、bootstrap 过期、两种丢 ACK 验证。

## P1-2 响应归属与跨标签切换屏障不完整

UI 行 19 要求返回 generation/shop 才显示；API 行 17 的 seed-summary 与行 28 的通用信封只保证写响应含 epoch/generation，没有要求所有敏感读含经授权的 epoch、generation 和资源 shop。permission 行 19–23 使 persona/reset 改变服务端会话；domain 行 11 明确多标签共享 cookie，另一个标签已经渲染的数据及在切换前完成的迟到读取仍可能显示旧身份数据。修订读响应的服务端上下文和 UI 请求快照校验，控制操作开始立即使本标签旧结果失效；多标签需定义共享失效通知及失联/恢复时的重新验证，提交服务端切换后其他标签也清屏，且所有展示和写动作重新核 current；不能仅依赖 abort 或客户端通知。测试切换/reset 前已发读、操作完成后响应、跨标签已显示内容、通知丢失及服务端拒绝旧 generation。

## P2 建议和需澄清

1. UI 行 11 的 `/v4/settings/demo` 对应矩阵 `V4-P14-06`（原阶段 V4-0/V4-5），可以作为首批受限入口，但应明确 V4-0 只交 session/reset/退出子集，不将整页 V4-5 管理能力标完成；`/v4` 与 `/v4/demo` 是额外入口，不应计入 66 页面完成数。UI 行 13 与 domain 行 13 已将完整导航/驾驶舱留给 V4-1，未发现必然越界。
2. API 行 13、24 与 permission 行 31 对 GET 的 Origin 要求未说明浏览器同源 GET 无 Origin 的处理。明确缺失 Origin 时的受信同源策略与实际部署反代/CORS 边界；保留跨站拒绝和写入严格 Origin+CSRF，并以真实浏览器验证 bootstrap、current 和回读可用。不可由此放宽写入安全。
3. API 行 14 的“同key原结果”与行 22 禁止重发 POST 容易误读：区分服务端幂等防御与客户端恢复策略；UI 禁止自动重发仍保留，列出 receipt 在重置、persona 切换、logout 后的可见性与 401 的非证明语义。
4. UI 行 23 模态焦点和 27 的全链测试尚无失败状态细节：补充启动失败、限流、session 过期、reset UNKNOWN、无权限及键盘可访问验证；无服务端确认时不把摘要或重置标成功。

66 路由表属于拟案：静态路由和动态 ID 的匹配优先级、保留字仍应在实现前冻结；不以创建 catch-all 即视为 66 页可用。以上为文档审查，不改变候选合同或授权状态。
