# P1-05 飞书技术探针配置与离线合同

更新：2026-10-08（Asia/Shanghai）。任务事实见 [Issue #6](https://github.com/aning0922/commerceops-agent/issues/6)。本页为完整离线技术探针的配置与复现说明；真实 G3 为 **blocked_external**。官方 SDK 类型/dispatcher/WS 帧与出站 HTTP 在离线替身上执行，技术接收/决定/幂等使用真实隔离 PG；没有真实飞书建连、消息发送、卡片点击或 Base 写入证据，不代表正式 T3/A01–A08/AC10 审批验收。

## 1. 当前实施边界

初始离线基线为已合入 P1-01 的 `a0d521ed79505287fa61bb6ddf82640e97824257`，之后普通 merge 主控已验证 PG 集成基线 `662fb575c377b174135bcf4755ba6d866dfe6cbb`。在隔离 Worktree 的 `codex/phase1-05-feishu` 实施，最终 PR 目标为 `phase/1-integration`。

- 已提供：`adapters/feishu/contracts.py` 的纯 JSON/身份/对象 value 校验、`cards.py` 的 JSON 2.0 技术卡片生成、`tests/fixtures/feishu/` 的合成脱敏消息和新版 callback，以及离线测试。
- 已实现完整离线接入：固定 SDK、技术 Gateway、受限 PG 短事务接收/决定、事件别名与消息去重、一次性卡片发送、Base 固定 token 与 unknown 分页对账、SDK 原始日志限制、默认拒绝 live 的配置入口。真实平台 transport 仍未运行。
- 主控已交接 SDK 依赖/uv.lock 的唯一修改责任，本分支增加 lark-oapi；隔离 `feishu_probe` schema 由显式 owner 命令初始化，不改正式 migration、PG smoke、CI workflow、Worker/Graph 或主控阶段状态。
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

配置加载器为 `FeishuProbeSettings`，前缀为 `COMMERCEOPS_FEISHU_`，不自动加载 dotenv。下表为实际变量。不要将真实值写入本页、聊天、Issue、PR、日志或截图。

| 配置项 | 用途与约束 |
|---|---|
| `COMMERCEOPS_FEISHU_APP_ID` / `COMMERCEOPS_FEISHU_APP_SECRET_FILE` | 专用测试 app_id；secret 是独立本地文件内容，运行时包装为 SecretStr |
| `COMMERCEOPS_FEISHU_TENANT_KEY` | 唯一允许租户；同时检查 envelope 与 sender/operator 租户 |
| `COMMERCEOPS_FEISHU_BOT_OPEN_ID` | 与官方机器人信息一致，用于群 mentions 校验 |
| `COMMERCEOPS_FEISHU_ALLOWED_OPEN_IDS` | JSON 字符串数组，包含 A/B 的 open_id，C 不在其中 |
| `COMMERCEOPS_FEISHU_ALLOWED_GROUP_CHAT_IDS` | JSON 字符串数组；技术卡片发送/接收只在该指定群范围 |
| `COMMERCEOPS_FEISHU_ORGANIZATION_ID` / `COMMERCEOPS_FEISHU_SHOP_ID` | PG 可信组织/店铺 UUID，不能由 callback value 决定 |
| `COMMERCEOPS_FEISHU_BASE_APP_TOKEN` / `COMMERCEOPS_FEISHU_BASE_TABLE_ID` | 指定测试 Base/表；操作还须匹配持久记录目标，配置改变时拒绝旧目标 |
| `COMMERCEOPS_FEISHU_EXTERNAL_READY` | 默认 false；未来经主控确认专用资源与运行授权后才设置 true，真实命令还必须带 `--live` |
| `COMMERCEOPS_DB_HOST/PORT/NAME/USER/PASSWORD_FILE` | 复用 DatabaseSettings；Gateway/出站探针必须 USER=commerceops_app，PASSWORD_FILE 指 app_password 文件 |
| 本地 plan / Base fields JSON 文件 | 仅技术样例，保存固定 UUID/nonce/字段，放未跟踪 runtime 并设 0600；发送/创建前在 PG 保存 hash 与持久操作键 |

若用户保存环境配置，可用现有忽略的 `.env.feishu.probe.local`，但程序不会自动读取；在指定终端显式注入环境，凭据文件权限设为仅本人读写。不建立真实 `.example` 凭据文件，不自动加载任意当前目录 `.env`。Verification Token/Encrypt Key 不是本段 WS 配置要求；如之后启用 HTTP 入口，须另外落实官方验签/解密合同及执行授权。

## 5. Base 资源和字段

创建独立测试 Base 与单独表，给应用指定资源权限；仅开通 API scope 不代表能访问该文件。若启用了高级权限，还须核对应用或包含应用的群是否具备对应权限。控制台中“添加文档应用”的实际路径及失败 code 需真机记录，不自动扩到其他 Base。

建议六个多行文本字段：`ProbeID`、`ProbeMarker`、`SourceMode`、`ApprovalMode`、`State`、`UpdatedAt`。ProbeMarker 固定含 `commerceops-p1-05-probe`，SourceMode 标技术测试，ApprovalMode 标模拟探针，UpdatedAt 使用 UTC ISO 文本。初期不用人员、附件、关联、公式或自动化列，不增加通讯录权限。

本任务只写带该标识的探针行，不使用真实订单/SKU/库存数据，不删除已有行或构建生产投影同步器。同表串行创建、读取、更新；创建前固定持久 UUIDv4 client_token。`ignore_consistency_check` 保持默认 false。

HTTP 成功不能替代业务 `code==0`；`1254290` 是限流，`1254291` 是同表并发写冲突，`1255006` 是 client_token 冲突。收到冲突不自动换 token 重建。网络超时/`1255040` 或无法确定响应属于 unknown，先按稳定 ProbeID 分页查找：一条则核对并链接，多条则停下人工对账，缺失也不无限新建。分页读完前不能声称未找到；幂等保留期限仍未知。[创建错误码及幂等参数](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/create.md)

## 6. 纯校验字段合同与后续接入注意

- 入站 JSON 限 32 KiB，拒绝重复键、非标准 NaN/Infinity；文本限 4000 字符。schema 必须是事件 envelope `2.0`，与卡片 JSON `2.0` 是两个独立版本轴。
- 群消息检查 chat allowlist 和 mentions 中真实 bot open_id/类型/租户；只移除本机器人的完整 @ 标记。机器人、非文本、非 @ 与不允许身份有固定错误分类。
- 按钮对象 value 仅允许 `probe_id/task_id/approval_id/plan_id/plan_version/plan_hash/action/acknowledged_assumption_keys/nonce`，不接收身份/角色/执行数量。整数版本不接受 bool 或数字字符串。nonce 明文仅在本地卡片文件/回传内存中出现，PG 只保存 SHA256；DB 中的 ProbeBinding 是受信合同。
- expected ProbePlan 是可信技术记录，未来须从 PG 读取；不能直接由按钮 value 构造 expected。nonce、目标卡片、计划身份/版本/hash、期限与完整确认键均须匹配。`approve_with_assumptions` 必须确认全部键，`reject_assumptions` 必须空键，普通 approve 被拒绝。
- 校验结果中的身份来自 operator/sender。脱敏 payload 保留最小平台 IDs、动作、确认键及 hash，不保留平台 token、nonce、消息正文。持久身份 IDs 用于审计；普通运行日志不直接打印这些对象。
- 消息需要 event_id 和 message_id 两层持久去重。卡片 callback 的 `context.open_message_id` 只放入 context 字段，不能填入 inbox 的唯一 message_id 列，否则同一卡片不同点击会被错误吞掉。
- 纯函数没有决定状态；`ProbeRepository` 从 business 身份映射读取 enabled/roles/app/tenant/组织/店铺，并锁定 principal 与技术卡片，只有首次有效动作能记录决定。相同身份/动作/确认集合重复返回已有结果，另一身份或相反动作记录技术冲突；COMMIT 完成后才返回技术 Toast，不写“已完成真实审批”。
- 实际 PG COMMIT 故障会回滚决定与接收；Gateway 将固定 DB 异常传给 SDK，WS 编码为 500 失败帧，没有成功 Toast。预建立受限连接池 checkout=200ms，lock_timeout=350ms、statement_timeout=650ms、transaction_timeout=1500ms；受控样本验证 <3 秒，不能推出真实网络 SLA。关键路径不等待 LLM/Woo/Base，真实 <3 秒与后续 p95 验收仍待外部资源。

JSON2.0 卡片使用 `body.elements` 内按钮及 `behaviors` 对象 value，明确标模拟审批；不使用旧 `tag=action` 容器。客户端 ≥7.20，当前只支持共享卡片，更新对所有接收者可见。[2.0 变更](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-json-v2-breaking-changes-release-notes.md)、[按钮配置](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-components/interactive-components/button.md)

## 7. SDK 候选与日志风险

2026-10-08 只读获取官方发布包：候选 `lark-oapi==1.7.3`，PyPI 未撤回，wheel SHA256 `c91f00087b7977dc9059ab492e8fe435e1a873863dca1d4e660d2be5b801e4cd`。已在内存静态读取，当前分支已锁定并实际执行 SDK。其要求 websockets>=11,<16，因此集成锁中的 websockets 从17.2调整到15.0.1；新增 pycryptodome3.24.0，既有HTTPX0.28.1保持。完整锁/漏洞/真实PG回归须以交付证据记录，未验证后续模型 websocket 行为。[PyPI](https://pypi.org/project/lark-oapi/1.7.3/)

官方 callback 注册/响应对象存在；ws EVENT 分支可编码 handler 返回值，CARD 分支直接返回。不能仅凭此分支判新版回调不可用。上游 Issue #126 的报告者重新发布应用配置后自行关闭，尚不是本项目真机运行证据；不据此私改 SDK。[官方回调示例](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/handle-callbacks.md)、[上游记录](https://github.com/larksuite/oapi-sdk-python/issues/126)

发布包源码在 DEBUG 打印完整 payload，在 INFO 打印完整连接 URL，错误日志格式化异常文本。只关 DEBUG 不够；完整实现应限制 SDK 原始 logger 的输出及传播，并只输出应用白名单日志字段/固定错误类别。不能直接记录 `JSON.marshal(data)`、原始异常、回调 token、nonce、App Secret、请求头或 wss URL。`restrict_sdk_logs` 在读秘密和建立客户端前禁用 Lark 与 websocket/httpx/httpcore/urllib3/psycopg 原始 logger 及传播；受控 canary 测试确认 payload、连接 URL 和异常原文无输出。入口只报告固定分类。日志限制意味着 SDK 原文诊断不可用，排障使用技术 PG 接收/状态与脱敏元数据。

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

实际检查结果记录在 [P1-05 进度证据](P1_05_EVIDENCE.md)。纯字段测试不能证明真实平台；PG/SDK 离线证据分开记录。真实 G3 不由这些离线/PG 技术结果推导。

| 真实检查 | 需要的证据 | 当前结果 |
|---|---|---|
| A/B 私聊、群 @、非 @/机器人/非允许身份 | 实际 event/message IDs、过滤结果、SDK/客户端版本 | blocked_external，未执行 |
| 新版确认/拒绝、完整对象值往返 | 真实 operator、plan/version/hash/action/确认键、Toast及延迟 | blocked_external，未执行 |
| 双击、A/B 相反动作、C、过期、DB 故障 | PG 探针层接收/重复/冲突/拒绝、无伪成功 | blocked_external，离线PG/handler已验证，真机未执行 |
| 断线/重启重连 | 断线区间、连接状态、恢复后实际投递，不推断无限补投 | blocked_external，未执行 |
| Base 创建/读回/更新/原 token 重投 | 最小权限、record_id、串行请求、HTTP/业务 code、unknown停止/对账 | blocked_external，离线客户端已验证，真平台未执行 |

真实联调必须由主控确认 PG 基线、完整离线交付和专用资源/运行授权齐备后启动。截图隐藏凭据、连接 URL 和未脱敏身份；记录时间、命令、版本、结果与证据模式。不把 skipped、模拟、代码合并或 CI 通过计为真实 G3 通过。


## 9. 实际命令与技术 schema

所有命令在项目根运行。先按已验证 P1-02 初始化业务迁移、官方 checkpointer 和 commerceops_app；不把密码放在命令行参数。`setup-schema` 单独使用显式 owner 环境，随后 runtime 命令切回 commerceops_app 和 app_password 文件。程序不创建组织/店铺/身份映射，它们须由主控协调准备；身份角色需 operator（消息）或 approver（卡片），admin 可用于专用测试。enabled=false、跨租户/应用/组织/店铺均拒绝。

```sh
uv run --frozen python -m commerceops.entrypoints.feishu_probe setup-schema
uv run --frozen python -m commerceops.entrypoints.feishu_probe verify-config
uv run --frozen python -m commerceops.entrypoints.feishu_probe emit-card --plan-file runtime/feishu/plan.json --output runtime/feishu/card.json
uv run --frozen python -m commerceops.entrypoints.feishu_probe register-card --plan-file runtime/feishu/received-plan.json
```

`emit-card` 只生成本地 JSON2.0，输出必须在 runtime 内，文件0600且不覆盖已有文件。plan 文件字段：probe_id、task_id、approval_id、plan_id 为固定技术 UUID；plan_version 为正整数；plan_hash 为64位小写十六进制；required_assumption_keys 为全部1–20条技术确认键数组；nonce 用本地 secrets.token_urlsafe(32) 生成；expires_at 为有时区 ISO 时间；chat_id 为指定群；message_id 为已发送卡片ID（register-card）或 pending-send（自动 send-card）。不要使用真实业务计划 IDs。

`register-card` 只登记已知目标消息的技术合同，不能批准、补货或发送。自动发送前由 send-card 登记 draft：PG 保存 nonce hash/合同/持久 UUID → COMMIT inflight → IM interactive SDK 请求 → 成功后绑定平台 message_id。unknown/inflight 均不重发，1小时消息 uuid 窗口不是永久幂等；需人工安全核对，禁止换 UUID 盲发。

**下面是真实外部命令，仅供专用资源和主控运行授权齐备后使用，本轮没有执行：**

```sh
uv run --frozen python -m commerceops.entrypoints.feishu_probe gateway --live
uv run --frozen python -m commerceops.entrypoints.feishu_probe send-card --plan-file runtime/feishu/plan.json --live
uv run --frozen python -m commerceops.entrypoints.feishu_probe base-create --probe-id UUID --base-fields-file runtime/feishu/base-fields.json --live
uv run --frozen python -m commerceops.entrypoints.feishu_probe base-reconcile --probe-id UUID --live
uv run --frozen python -m commerceops.entrypoints.feishu_probe base-update --probe-id UUID --state updated --updated-at UTC_ISO_TIME --live
```

真实命令还要求 EXTERNAL_READY=true；该配置是显式执行开关，不能替代人的资源/运行授权。默认模式在任何 SDK/DB 网络操作前拒绝。 live_client 先通过官方 bot info 核对 bot_open_id，再执行探针。无用户范围/群/Base权限时记录失败，不自动申请/发布。

Base fields 文件必须含六个指定列，ProbeID 与 --probe-id 相同；State 仅 created/updated/probe_complete，UpdatedAt 为 UTC ISO 时间。prepare 在 PG 固定 token/请求 hash，create_once 只处理 ready；只有明确1254290/1254291已拒绝状态可以由显式 `--retry-known-rejection` 使用原 token 重试。succeeded 不重新创建；1255006停为conflict；unknown/inflight只对账。base-reconcile读完整分页验证唯一行和请求内容；更新未知不能由“行存在”判已更新，须匹配持久 pending_fields/hash。分页异常/重复/未找到不会回到ready。测试表状态改动不反向授权业务。

technical schema 仅含 cards、receipts、event_keys、base_operations。接收记录与事件别名 append-only；runtime 不可DDL/DELETE，卡片与Base技术状态仅必要更新。业务 migration/checkpoint schema不变。PG integration fixtures只在既有 smoke 创建的随机测试项目中初始化该schema和技术身份；清理仅该项目/卷/镜像/秘密文件。
