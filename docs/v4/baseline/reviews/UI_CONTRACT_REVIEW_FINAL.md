# UI/API 合同复审

结论：**ACCEPT_CANDIDATE**，首审两项 P1 的合同级阻断已处理；未发现剩余 P1。接受范围仅限当前候选文本，不代表实现、测试、安全验收或 B 开发授权。保留以下 P2 文案一致性事项供冻结前清理。

本次审查绑定 SHA-256：

- DOMAIN_SOURCE_CONTRACT.md `303f187bf0acd604f5eb8260894bf57c2f739cfa9ae314e11fed3bbeaae4d0aa`
- PERMISSION_DEMO_CONTRACT.md `e195071d5faa33a25d0aebb97a9627d06f5f4589348e33cbeeaa1800fa5b4230`
- UI_ROUTES_CONTRACT.md `643b5f0903b5c6b8ceff763f709fcc5745f4fee062f00faa66f8dafc4adf1b2f`
- API_EVENTS_CONTRACT.md `3d413e86a883a6db164527b5a801af0594cc1cd81b9c6cf037840fa8c28546ab`
- v4-public-openapi.json `19f9585fc1db6de2c2037c369f50bd356d0f2e80599b0332ec49b14204ad5797`
- 首审 reviews/UI_CONTRACT_REVIEW.md `484fd138662465e0dde467ecb1417836220d970fa40ec96f9247d7ecd81ec6bd`

## 首审逐项

- P1 创建 ACK 丢失：API「精确恢复」规定 300 秒 bootstrap owner 与单个 key、最小状态、无凭据恢复、跨 key 404；区分 cookie 已应用、仅 bootstrap 可用、两者丢失/过期，明确 UNKNOWN 和用户显式新空间。权限合同同步该例外，已解决合同级冲突。实现时仍须实际验证提交、cookie 应用及隔离的各失败分支。
- P1 persona/reset 迟到响应：API 要求敏感成功数据带服务端 context，seed-summary 强制 epoch/generation header；UI 定义切换前清屏、请求快照/序号、同源标签无秘密失效信号、隐藏/恢复复核及可见页 5 秒 current 检查，明确通知丢失和跨设备像素无法即时撤销。服务端授权仍是最终屏障，合同级阻断已处理；收敛时间依赖实际调度和网络，不能作为即时保证。
- P2 范围：UI 明确 `/v4/settings/demo` 仅 V4-P14-06 子集，欢迎入口不计入 66 页面完成；完整导航与驾驶舱仍 V4-1。
- P2 GET Origin：API 明确有 Origin 的严格匹配、缺失时同源 Host 与 Fetch Metadata、可信代理限制，POST 仍强制 Origin/CSRF；需未来真实浏览器与部署环境验证。
- P2 同键语义：API 区分服务端抗重放与客户端不自动重发，并明确切换、reset、logout 和到期的回执边界。
- P2 失败及无障碍：UI 新增失败、429、401/403、UNKNOWN、越权、焦点和移动端等验证条款；均为未来验收要求。

## 剩余 P2 文案一致性

1. UI 修订段称“所有请求”都比较 tenant/principal/shop 等 context；API 已正确例外 bootstrap、失败响应和最小控制回执。建议 UI 明确仅对带敏感数据的成功响应比较完整 context，控制/匿名/错误按专用状态处理，避免实现者为例外响应制造虚假身份或误判无法恢复。
2. permission 原负例段写“无 Origin …均403”，API 修订允许受限同源 GET 缺 Origin。建议限定该负例为写请求，GET 采用后文受限例外，避免测试合同歧义。API 初始端点表的 bootstrap“受信Origin”也可交叉引用同一例外。
3. OpenAPI 将 bootstrap 与 active 表示为同一个 `demoCookie` 安全方案；这与合同的用途区分相容，但建议在各相关 operation 描述明确 cookie 阶段、替换和 bootstrap 唯一 key 绑定时点，以便生成客户端和审查者不误认为两者具有同等权限。

静态核到 OpenAPI 8 个路径、18 个 schema、seed-summary 两个 required header；未执行 schema 校验、代码、浏览器、服务或 PG。全部未来 Gate 保持未运行。
