# P1-05 飞书技术探针配置与离线合同

更新：2026-10-08（Asia/Shanghai）。任务事实见 [Issue #6](https://github.com/aning0922/commerceops-agent/issues/6)。本页当前交付是配置准备、纯校验代码与合成样例；真实 G3 为 **blocked_external**。没有真实 SDK 建连、消息发送、卡片点击或 Base 写入证据，不代表正式 T3/A01–A08/AC10 审批验收。

## 1. 当前实施边界

本段基线为已合入 P1-01 的 `a0d521ed79505287fa61bb6ddf82640e97824257`。在隔离 Worktree 的 `codex/phase1-05-feishu` 实施，最终 PR 目标为 `phase/1-integration`。

- 已提供：`adapters/feishu/contracts.py` 的纯 JSON/身份/对象 value 校验、`cards.py` 的 JSON 2.0 技术卡片生成、`tests/fixtures/feishu/` 的合成脱敏消息和新版 callback，以及离线测试。
- 尚未提供：锁定 SDK、实际 dispatcher/长连接入口、PG 持久接收与探针决定、Base 客户端和持久 client_token、DB 故障响应、SDK 日志限制及真实运行命令。不能将纯校验当作可运行 Gateway。
- P1-02 集成 SHA/PG 合同和共享锁由主控交接后再实施；本段不改 migration、依赖清单/锁、PG smoke、CI workflow 或主控阶段状态。
- 卡片只展示模拟确认/拒绝。字段通过不表示审批提交、业务授权、持久幂等或补货执行；后续仍须从 PG 查询 principal.enabled/roles、绑定探针记录并事务提交。

证据模式：当前执行 `source_mode=offline_synthetic`、`model_mode=not_used`、`approval_mode=simulated_probe`。样例中的 app/tenant/user/群标识均为虚构 `probe-*`；UUID、hash 和 nonce 也是固定技术样例，不是生产授权凭据。

## 2. 测试组织与应用准备清单

以下为用户准备或之后受控联调的操作清单，本段没有替用户执行平台配置。应用发布、权限扩大或公网隧道仍须按 Issue 的授权边界交由主控确认。

| 项目 | 需要的配置 | 验证/失败时记录 |
|---|---|---|
| 组织 | 专用测试组织，明确 tenant_key；仅内部测试成员 | 组织类型、资源可用性与套餐限制，不能假定个人组织全部权限默认可用 |
| 应用 | 企业自建应用，名称清楚标注技术探针；启用应用机器人 | app_id、机器人启用状态、版本与可用范围；不使用普通群 Webhook 机器人替代 |
| 成员 | 两个允许的测试用户 A/B，加一个不在 allowlist 的用户 C | 本应用 open_id、对应组织及测试角色；不能用显示名匹配 |
| 群 | 专用内部测试群，加入应用机器人及 A/B/C | chat_id；单聊与群范围分开记录，不扩大到全群消息 |
| 客户端 | 测试成员使用飞书客户端 ≥7.20 | 每次真机测试记录实际客户端版本 |
| 本地网络 | 允许出站 HTTPS/WSS，电脑保持在线 | 实际断线/重连时间与投递情况；不承诺休眠后的无限补投 |
| 发布生效 | 用户准备专用测试版本并使上述配置生效 | 版本号和生效状态；不能由保存配置推断已发布 |

官方支持企业自建应用通过长连接接收新版回调；每应用最多 50 连接，同一应用多连接为随机单消费者。探针运行时只开一个 Gateway，避免另一个测试客户端消费样本。接收与响应需在 3 秒内完成。[回调长连接配置](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/event-subscription-guide/callback-subscription/configure-callback-request-address.md)

## 3. 最小权限与两处订阅

| 能力 | 当前已核实的候选最小 scope/订阅 | 配置位置 |
|---|---|---|
| 私聊接收 | `im:message.p2p_msg:readonly` | 权限管理；事件 `im.message.receive_v1` |
| 群 @ 接收 | `im:message.group_at_msg:readonly` | 权限管理；事件 `im.message.receive_v1` |
| 发技术卡片 | `im:message:send_as_bot` | 权限管理；机器人能力与目标成员/群可用性 |
| 新版卡片回调 | `card.action.trigger`，本身无额外 scope | **事件与回调 → 回调配置** |
| 新增探针行 | `base:record:create` | 权限管理，同时需要目标 Base 资源权限 |
| 更新探针行 | `base:record:update` | 权限管理，同时需要目标 Base 资源权限 |
| 分页读回/对账 | `bitable:app:readonly` | 本段采用已核实 list API，不假造更窄 scope |

参考：[消息接收](https://open.feishu.cn/document/server-docs/im-v1/message/events/receive.md)、[消息发送](https://open.feishu.cn/document/server-docs/im-v1/message/create.md)、[Base 创建](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/create.md)、[更新](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/update.md)、[读取](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/list.md)。

配置顺序：准备组织/应用及机器人 → 配置最小权限和测试成员范围 → 用户安排测试版本发布生效 → 经主控授权启动锁定版本地 SDK → 在 **事件配置** 保存长连接并订阅 `im.message.receive_v1` → 在 **回调配置** 另行保存长连接并订阅 `card.action.trigger` → 将机器人加入测试群 → 为指定 Base 授予应用资源权限 → 按受控清单联调。保存长连接方式时，本地 SDK 必须已连接并运行。

不订阅 `card.action.trigger_v1`；不申请全群历史/全部消息、全量通讯录、审批中心或用户 user_id 权限。应用内 open_id 足够用于本探针身份映射。若 scope 组合不能访问目标资源，记录实际 HTTP/业务 code、所缺权限及资源授权，再由主控处理；不能自动换成宽权限。

机器人 open_id 应由官方 `GET /open-apis/bot/v3/info` 验证，不用应用名称或 app_id 代替。该 API 无额外权限要求，需机器人能力已启用并发布，响应为根级 `bot.open_id`，不是 `data.bot`。[机器人信息](https://open.feishu.cn/document/client-docs/bot-v3/obtain-bot-info.md)

## 4. 本地未跟踪配置清单

当前没有 Gateway 配置加载器，下面是待接入的配置合同，变量名须在完整实现时再次核对。不要将真实值写入本页、聊天、Issue、PR、日志或截图。

| 配置项 | 用途与约束 |
|---|---|
| app_id / app_secret | 专用测试应用凭据；secret 只存本地受限文件或注入环境 |
| tenant_key | 唯一允许租户；同时检查 envelope 与 sender/operator 租户 |
| bot_open_id | 与该应用官方机器人信息一致，用于群 mentions 校验 |
| allowed_open_ids | A/B 的应用内 open_id；C 不在其中；不能从 card value 动态扩充 |
| allowed_group_chat_ids | 指定测试群；单聊用户仍须通过身份允许范围 |
| PG runtime 连接 | 使用主控交付的 P1-02 受限连接合同；不能用 checkpointer 当副作用事务 |
| organization/shop 映射 | 服务端可信配置/PG 映射，不能由 callback 提供 |
| Base app_token / table_id | 指定测试 Base/表，不接受用户消息或卡片改写目标 |
| probe_id / client_token / 请求 hash | 发送前持久化；同一创建操作固定 UUIDv4 client_token |
| card message_id / chat_id | 发送成功后持久绑定到探针，callback 只匹配此目标卡片 |

建议本地文件名 `.env.feishu.probe.local`，现有 `.gitignore` 已忽略；文件权限设为仅本人读写。不建立真实 `.example` 凭据文件，不自动加载任意当前目录 `.env`。Verification Token/Encrypt Key 不是本段 WS 配置要求；如之后启用 HTTP 入口，须另外落实官方验签/解密合同及执行授权。

## 5. Base 资源和字段

创建独立测试 Base 与单独表，给应用指定资源权限；仅开通 API scope 不代表能访问该文件。若启用了高级权限，还须核对应用或包含应用的群是否具备对应权限。控制台中“添加文档应用”的实际路径及失败 code 需真机记录，不自动扩到其他 Base。

建议六个多行文本字段：`ProbeID`、`ProbeMarker`、`SourceMode`、`ApprovalMode`、`State`、`UpdatedAt`。ProbeMarker 固定含 `commerceops-p1-05-probe`，SourceMode 标技术测试，ApprovalMode 标模拟探针，UpdatedAt 使用 UTC ISO 文本。初期不用人员、附件、关联、公式或自动化列，不增加通讯录权限。

本任务只写带该标识的探针行，不使用真实订单/SKU/库存数据，不删除已有行或构建生产投影同步器。同表串行创建、读取、更新；创建前固定持久 UUIDv4 client_token。`ignore_consistency_check` 保持默认 false。

HTTP 成功不能替代业务 `code==0`；`1254290` 是限流，`1254291` 是同表并发写冲突，`1255006` 是 client_token 冲突。收到冲突不自动换 token 重建。网络超时/`1255040` 或无法确定响应属于 unknown，先按稳定 ProbeID 分页查找：一条则核对并链接，多条则停下人工对账，缺失也不无限新建。分页读完前不能声称未找到；幂等保留期限仍未知。[创建错误码及幂等参数](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/create.md)

## 6. 纯校验字段合同与后续接入注意

- 入站 JSON 限 32 KiB，拒绝重复键、非标准 NaN/Infinity；文本限 4000 字符。schema 必须是事件 envelope `2.0`，与卡片 JSON `2.0` 是两个独立版本轴。
- 群消息检查 chat allowlist 和 mentions 中真实 bot open_id/类型/租户；只移除本机器人的完整 @ 标记。机器人、非文本、非 @ 与不允许身份有固定错误分类。
- 按钮对象 value 仅允许 `probe_id/task_id/approval_id/plan_id/plan_version/plan_hash/action/acknowledged_assumption_keys/nonce`，不接收身份/角色/执行数量。整数版本不接受 bool 或数字字符串。
- expected ProbePlan 是可信技术记录，未来须从 PG 读取；不能直接由按钮 value 构造 expected。nonce、目标卡片、计划身份/版本/hash、期限与完整确认键均须匹配。`approve_with_assumptions` 必须确认全部键，`reject_assumptions` 必须空键，普通 approve 被拒绝。
- 校验结果中的身份来自 operator/sender。脱敏 payload 保留最小平台 IDs、动作、确认键及 hash，不保留平台 token、nonce、消息正文。持久身份 IDs 用于审计；普通运行日志不直接打印这些对象。
- 消息需要 event_id 和 message_id 两层持久去重。卡片 callback 的 `context.open_message_id` 只放入 context 字段，不能填入 inbox 的唯一 message_id 列，否则同一卡片不同点击会被错误吞掉。
- 纯函数没有决定状态、锁或数据库；两名允许用户的相反动作均可能通过字段校验，首次决定/重复/冲突必须由后续 PG 短事务处理。完成事务提交后才返回技术接收 Toast，不写“已完成真实审批”。
- DB 不可用时不能伪成功；锁定 SDK 的失败帧、提交后返回和预算须实际测试。回调处理不等待 LLM、Woo 或 Base 写入，3 秒合同与后续 p95 性能验收分开记账。

JSON2.0 卡片使用 `body.elements` 内按钮及 `behaviors` 对象 value，明确标模拟审批；不使用旧 `tag=action` 容器。客户端 ≥7.20，当前只支持共享卡片，更新对所有接收者可见。[2.0 变更](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-json-v2-breaking-changes-release-notes.md)、[按钮配置](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-components/interactive-components/button.md)

## 7. SDK 候选与日志风险

2026-10-08 只读获取官方发布包：候选 `lark-oapi==1.7.3`，PyPI 未撤回，wheel SHA256 `c91f00087b7977dc9059ab492e8fe435e1a873863dca1d4e660d2be5b801e4cd`。已在内存静态读取，当前分支没有添加/安装 SDK。锁定、兼容、dispatcher 响应及 transport 测试仍待主控交接。[PyPI](https://pypi.org/project/lark-oapi/1.7.3/)

官方 callback 注册/响应对象存在；ws EVENT 分支可编码 handler 返回值，CARD 分支直接返回。不能仅凭此分支判新版回调不可用。上游 Issue #126 的报告者重新发布应用配置后自行关闭，尚不是本项目真机运行证据；不据此私改 SDK。[官方回调示例](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/handle-callbacks.md)、[上游记录](https://github.com/larksuite/oapi-sdk-python/issues/126)

发布包源码在 DEBUG 打印完整 payload，在 INFO 打印完整连接 URL，错误日志格式化异常文本。只关 DEBUG 不够；完整实现应限制 SDK 原始 logger 的输出及传播，并只输出应用白名单日志字段/固定错误类别。不能直接记录 `JSON.marshal(data)`、原始异常、回调 token、nonce、App Secret、请求头或 wss URL。当前纯校验代码没有日志输出；这不表示 SDK 日志脱敏已经验收。

## 8. 当前检查与真实 G3 待执行矩阵

当前纯合同可用既有锁依赖验证：

```sh
uv sync --frozen
uv run --frozen --no-sync pytest tests/test_feishu_contracts.py -q
uv run --frozen --no-sync ruff check .
uv run --frozen --no-sync ruff format --check .
uv run --frozen --no-sync mypy
uv run --frozen --no-sync python -m scripts.check_docs
```

实际检查结果将在当前部分完成后记录到 [P1-05 进度证据](P1_05_EVIDENCE.md)。合成字段测试不能证明真实 callback、DB 持久接收、SDK 响应时延或外部权限已通过。

| 真实检查 | 需要的证据 | 当前结果 |
|---|---|---|
| A/B 私聊、群 @、非 @/机器人/非允许身份 | 实际 event/message IDs、过滤结果、SDK/客户端版本 | blocked_external，未执行 |
| 新版确认/拒绝、完整对象值往返 | 真实 operator、plan/version/hash/action/确认键、Toast及延迟 | blocked_external，未执行 |
| 双击、A/B 相反动作、C、过期、DB 故障 | PG 探针层接收/重复/冲突/拒绝、无伪成功 | blocked_external；PG/handler待实施 |
| 断线/重启重连 | 断线区间、连接状态、恢复后实际投递，不推断无限补投 | blocked_external，未执行 |
| Base 创建/读回/更新/原 token 重投 | 最小权限、record_id、串行请求、HTTP/业务 code、unknown停止/对账 | blocked_external；客户端待实施 |

真实联调必须由主控确认 PG 基线、完整离线交付和专用资源/运行授权齐备后启动。截图隐藏凭据、连接 URL 和未脱敏身份；记录时间、命令、版本、结果与证据模式。不把 skipped、模拟、代码合并或 CI 通过计为真实 G3 通过。
