# 飞书接入设计与验证边界

调研日期：2026-10-08。已读取官方文档 Markdown 正文及官方 Python SDK 源码；尚无应用凭证，未建立真实长连接、发送消息、点击卡片或写多维表格。来源索引见 [RESEARCH](RESEARCH.md)。

## 1. 推荐接入方式

使用个人创建的飞书测试组织中的**企业自建应用 + 应用机器人**。消息事件与新版卡片回调均优先配置长连接，但在控制台的“事件配置”与“回调配置”分别订阅。普通群自定义 Webhook 机器人不能替代这个接收事件与审批的应用机器人。

| 能力 | 官方资料确认 | 本项目选择与待实测项 |
|---|---|---|
| 私聊 / 群 @ | `im.message.receive_v1` 配套不同权限 | 只接收授权用户文本；忽略机器人、非 @ 群消息及其他类型 |
| 消息长连接 | 自建应用支持；出站访问公网即可 | 一个独立 Gateway 进程；断线与重启投递需实测 |
| 新版卡片回调 | `card.action.trigger` 支持 SDK 长连接 | 与消息共用 dispatcher，分别配置订阅 |
| 旧版卡片回调 | `card.action.trigger_v1` 不支持长连接 | 不订阅、不实现旧版 |
| 卡片 JSON 2.0 | 客户端≥7.20；与 1.0 结构不兼容 | 固定 `schema="2.0"`，只做共享卡片，不降级成 1.0 |
| 消息发送 | IM API 支持 interactive，uuid 有 1 小时去重窗口 | 发送前持久化 UUID；窗口外不盲目重发 |
| 多维表格记录 | 有创建、读取、更新 API；创建有 client_token | 标准 UUIDv4 持久化；幂等保留期限仍待实测/进一步确认 |
| 权限与可用范围 | API scope、资源协作者、应用发布范围均影响可用性 | 不以“scope 已开通”代表能够访问目标表格或成员 |

长连接限制：仅企业自建应用，每应用最多 50 个连接，同一应用多连接为随机单消费者而非广播；消息与回调处理应在 3 秒内完成。依据 [接收事件](https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/request-url-configuration-case.md) 与 [接收回调](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/event-subscription-guide/callback-subscription/configure-callback-request-address.md)。

**三个版本轴不能混淆**：事件 envelope schema、卡片 JSON schema、回调类型是不同概念。不是“用了 JSON 2.0 就自动配置了新版回调”，也不能由旧回调的限制推出所有卡片都不支持长连接。

官方卡片回调页面概要表仍写有 Webhook，但同页故障说明以及专门的回调订阅文档明确提供长连接。采用更具体的订阅文档与 Python SDK 示例交叉判断，保留真实组织验证闸门。SDK 源码中的旧 `MessageType.CARD` 分支直接 return，不能拿这个分支当作新版 `card.action.trigger` 不支持的证据；新版注册通过 event dispatcher。实际 wire 行为必须用锁定版 SDK 联调确认。

## 2. 最小权限与组织配置

| 目的 | 候选最小 scope / 配置 | 说明 |
|---|---|---|
| 私聊消息 | `im:message.p2p_msg:readonly` | 不需要全量通讯录 |
| 群 @ 消息 | `im:message.group_at_msg:readonly` | 不申请全群历史消息读取 |
| 机器人发送 | `im:message:send_as_bot` | 开启机器人能力、加入测试群 |
| 新版回调 | 订阅 `card.action.trigger` | 回调本身无额外 scope；身份字段各有条件 |
| 新增表格行 | `base:record:create` | 当前创建 API 支持细粒度权限 |
| 修改表格行 | `base:record:update` | 当前更新 API 支持细粒度权限 |
| 读取 / 对账 | 已核实 list API 的 `bitable:app:readonly` | 更窄 search/read scope 若可用应另核实；当前不假造 scope 名 |
| 表格资源 | 给应用目标 Base 的适当协作权限 | API 权限与资源授权同时满足；高级权限可能还需配置 |

创建/更新 API 也列出较宽的 `bitable:app` 作为替代；本项目不默认申请其管理权限，优先上述组合。若控制台或 API 不接受此组合，先记录具体错误和所缺 scope，再由用户决定权限扩大。读取回调的 open_id 足以建立应用内身份，不额外申请 `contact:user.employee_id:readonly`。

消息 scope 来源：[接收消息](https://open.feishu.cn/document/server-docs/im-v1/message/events/receive.md)。表格 scope 来源：[创建记录](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/create.md)、[更新记录](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/update.md)、[读取记录](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/list.md)。

开发配置步骤：创建测试组织/自建应用 → 开机器人 → 配置所需权限及用户可用范围 → 本地 SDK 建连 → 分别保存事件/回调长连接设置 → 发布测试应用版本 → 将机器人加群 → 为指定 Base 配置资源访问 → 真机联调。控制台保存长连接模式时客户端必须在线。

个人组织能否无需进一步认证获得全部目标权限、具体审批流程、成员/容量限制、租户 API 配额：**未通过真实控制台确认**。不承诺所有个人组织默认可用。P0 不需要外部群、跨租户、官方审批中心或商店应用。

## 3. 入站、身份与安全

Gateway 收到消息后只做解析、身份白名单、大小限制、去重和 PG 短事务，提交成功才完成 SDK handler。不能等待 LLM、Woo 或表格同步。DB 不可用时让 SDK 返回失败，不把只存内存当作成功接收。

消息以 event_id 做持久去重，再对 message_id 做逻辑去重；原始 JSON 仅保留脱敏必需字段与 hash。组织 tenant_key、app_id 必须匹配配置，用户 identity 使用 `(app_id, tenant_key, open_id)`，不以显示名匹配，也不接受卡片 value 里的“用户 ID”覆盖 operator。

群聊需校验 chat_id 允许列表、mentions 中确实包含本应用机器人身份，处理去掉 @ 标记后的文本。机器人身份来自应用配置/官方身份接口验证，不用名称比较。只处理人类 sender，避免自身消息循环。卡片转发或其他成员看到按钮不代表有审批权。

长连接由官方 SDK 在连接阶段鉴权、使用加密传输；应用仍必须校验事件租户/应用/操作人和业务权限。HTTP 备选若启用：必须按 SDK 官方验证流程处理原始 body、Verification Token、Encrypt Key、请求签名、URL challenge 及重放防护；应用鉴权和群自定义机器人签名方案不是同一套。具体 header/算法以锁定版 SDK 单测验证，不手抄网络示例。未配置验证信息时不得开放 HTTP 回调。

SDK 调试日志可能打印回调 payload，联调也需脱敏；不在 INFO/DEBUG 日志记录 App Secret、完整 token 或订单信息。

## 4. 卡片与快速审批

审批卡片包含 task_id、计划版本、数据窗口/来源标识、库存观测时点、最多 20 条 SKU/建议数量、确定性风险、规则参数、假设、审批期限。无未知在途时使用普通“批准创建内部补货任务”；存在未知在途时必须使用下述专用确认动作。完整批准范围必须能在卡片看到；大批量先缩小范围，不能只显示 top-N 却批准隐藏条目。

JSON 2.0 的 elements 放在 body 内，unsupported 属性会报错；共享更新不能用于隐藏不同用户的敏感信息。按钮 value 用对象：`approval_id, plan_id, plan_version, plan_hash, action, acknowledged_assumption_keys, nonce`，没有客户端决定的执行数量或角色。nonce 在数据库验证并绑定审批，不能替代平台身份认证。

### 4.1 在途未知卡片合同

逐项展示未知在途 SKU、建议数量和“按 0 估算可能造成重复补货；仅创建内部工作项”的风险。选择明确命名的两个按钮，避免默认勾选及额外的中间确认状态：

| 可见动作 | action | 确认键 | 服务端结果 |
|---|---|---|---|
| 确认在途未知按 0 估算并批准本版本 | `approve_with_assumptions` | 当前计划全部 `inbound_unknown_zero:{sku_key}` | T3 校验后一次保存确认+approved+resume job |
| 拒绝此假设并拒绝计划 | `reject_assumptions` | 空集合 | T3 保存 rejected，原因 `INBOUND_ASSUMPTION_DECLINED`；零补货 |

确认键和按钮 action 都是不可信请求值。服务端从数据库读取 required_assumptions，检查真实 operator、组织/店铺/角色、当前 pending、plan_id/version/hash、有效期、nonce、硬性数据质量；确认键必须精确匹配，不允许只确认部分 SKU。客户端传普通 approve 或缺确认键返回 `ASSUMPTION_ACK_REQUIRED`，保持 pending，不入执行队列。原始在途字段保持 null，不因确认改为“已知零”。Web 入口使用同一合同，不设置免确认通道。

同版本同操作者相同有效动作重复投递/点击，只返回已有决定，不重复产生确认记录、决定审计或 resume job；不同操作者/相反动作/不同确认集合返回已决定或冲突。旧卡片不能确认新版本，执行前复核到在途从未知变已知也需重批。未点击或退出卡片不改变状态。身份认证失败直接拒绝；nonce 校验失败不能因任务已结束而绕过认证。

Phase 1 的 G3 真实回调探针至少验证上述 action 和对象确认键能往返；最终 AC10 还需 Phase 3/4 的真实审批服务、重复/拒绝/篡改验收。专用按钮是本项目交互设计，不将其描述为已实现的飞书原生审批能力。

### 4.2 响应与更新

handler 在 3 秒内完成 T3 或返回明确失败/处理中 Toast；SDK 负责长连接响应帧，不能把 Webhook 的 HTTP 200 机械套进 ws handler。批准成功返回“已记录审批，执行中”，拒绝返回“已拒绝，不创建补货项”，重复请求显示既有决定；最终执行结果异步通知。

卡片 JSON 版本与更新保持一致。回调 token 的延时更新能力为 30 分钟内最多 2 次，不适合作为持久恢复凭据；长等待后优先用持久 message_id 的更新 API（先实测可更新条件）或发送新的结果消息。卡片 UI 更新失败不会回滚业务审批。参考 [回调结构](https://open.feishu.cn/document/feishu-cards/card-callback-communication.md)、[处理卡片回调](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/handle-card-callbacks.md) 与 [JSON 2.0 变更](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-json-v2-breaking-changes-release-notes.md)。

## 5. 多维表格投影

每个补货项一行，字段：CommerceOpsItemID（文本）、TaskID、SKU、Quantity、Risk、Window、SourceMode、ApprovalStatus、ApprovedBy（P0 用文本映射名）、BusinessStatus、ResolutionReason、ResolvedBy、ResolvedAt、SyncVersion、UpdatedAt。BusinessStatus 对应内部 item 的 open/completed/closed；关闭由受鉴权 Web/API 触发后单向投影，不在 Base 人工修改来反向授权。初期不用人员、附件、关联列以免追加通讯录权限和复杂字段适配。

PG 保存 row external_id；首次创建使用固定 client_token，后续对 external_id 更新。创建 API 文档支持 UUIDv4 幂等参数，但没有在本次读取中确认长期保留期限，不将其当作永久唯一约束。同一 table_id 串行写，按最新 projection_version 收敛；PG 仍是业务真值，表内人工改动不反向批准或执行。

网络超时导致写入结果未知：先按稳定 CommerceOpsItemID 分页查找；恰好一条则补 external_link，重复则标为异常人工核对，缺失也不能在外部一致性窗口未知时无限新建。旧投影不得覆盖新版本。文档列出同表并发写可能返回 1254291，即使 HTTP 200 也需校验业务 code。参考 [创建记录限制](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/create.md)。

## 6. 本地调试与接入闸门

无需预购服务器。开发电脑联网时由 Gateway 主动连接；电脑休眠/离线不承诺实时响应或无限历史补投。必要时的 HTTPS 隧道只暴露指定回调路径，需用户明确授权后启用，不能顺便暴露管理 API。

Phase 1 需先做技术探针（不在本轮实施）：

1. 固定 SDK 版本，私聊和群 @ 收到事件，断线后重连，记录 event/message IDs 与延迟。
2. 发送 JSON 2.0 卡片，通过长连接收到新版 callback，确认 operator/open_id、event_id、value 和 Toast 返回。
3. 拒绝、双击、两人同时点、非授权用户、过期卡片、DB 故障均有可解释结果。
4. 建立测试 Base，验证最小权限、创建/读回/更新/幂等重复及同表写串行。
5. 保存脱敏请求/响应、SDK 版本、客户端版本和截图；无凭证时只标记 blocked_external，不能判真机 E2E 通过。

若新版回调长连接实际不可用，先核对事件/回调分开配置、应用发布、SDK 版本；再选择受鉴权 HTTPS 回调。受鉴权 Web 审批可作为开发替代，但不能替代 AC01 飞书卡片闭环的正式验收。
