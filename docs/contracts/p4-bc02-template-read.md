# P4 BC02 显式读取与不可变模板合同

2026-10-14 原 A 后端批。Root/Core/Web 已批准原候选合同内容 hash `e1c112f7937a836c165dc3f0a80c92b106ebc218e1ed3c80c9a3736b5d8ecf10`；本页记录源码切片和 Root/Core 后续冻结的必要回复合同，不将计划描述为实际运行证据。P4/M1 继续 in_progress，main、原阶段预算、人工工时未报告和历史阻断保持。

## 显式读取

只接受全文匹配的 `查询任务<task_uuid>进度` 和 `解释任务<task_uuid>的报告<report_uuid>`；不猜最近任务、不接受多意图或残余文本、不省略报告编号。读取复用当前身份、角色、shop scope 与原 requester / 原 eligible approver 可见性；approver-only 不经过 operator 全局门禁。Feishu 使用真实服务端 identity 桥接 App/Tenant/OpenID 和原可信 chat，不合成 WebActor/session。

HTTP 仍为原 P3 22 操作加 N01 第 23 操作。既有 GET explanation 返回原 envelope；其 `explanation` 为按 `schema_version` 区分的 oneOf：

- 原 `p204-read-v1` 和六个 `P2Explanation*` schema 保持。匹配旧 cache 时仍先验原 child/link/request/result；损坏不回退新模板。
- 新 `p4-p3-template-read-v1` 独立严格 DTO，无 child_task_id。包含真实 P3 task/source_task、source_kind、observation_id、report_id、snapshot_id、facts_hash、模板版本、创建时间、explanation_id 与 typed result。原报告 snapshot 使用原 snapshot；重观测 snapshot 使用 observation.id，report 使用实际 observation.report_id。

DTO / OpenAPI 对应 [模板 DTO](../../backend/src/commerceops/application/replenishment/template_result.py)、[合同 JSON](p3-openapi.json) 与等字节 runtime asset。GET 不生成模板、不建业务任务/模型/Graph/job、不回填历史、不重投 Base。旧部署已完成 P3 缺缓存仍 NOT_READY。

## 两个冻结事务

仅 `ApprovalStore.prepare` 的可信 completed P203 原来源通过 `_stored` 与绑定检查后、no_action 返回之前，以及 `ExecutionStore.save_observation` 得到真实 observation/report UUID 并验证 canonical report 后，在各自原事务内写入缓存。

`business.p3_template_results` 为单一 forward migration `0014_p3_template_results` 创建的 immutable 表。org/shop/requester/P3/source_kind/source_task/observation/snapshot/report/facts/template_version 完整绑定到 logical key；ID 为该 key 的固定 UUID5。ready 保存 typed template、canonical_result、SHA256；unavailable 仅由命名 `TemplateRenderError` 导致，错误码 TEMPLATE_RENDER_FAILED，result/hash 均为空。其他事实/引用/权限/SQL/未知错误回滚原事务。相同 key 重放必须比较绑定、状态、完整内容和 hash；冲突不默默忽略。应用角色仅 SELECT/INSERT，无 UPDATE/DELETE/TRUNCATE；数据库触发器阻止历史变更。没有 RLS/policy，不把 explicit grants 描述为 RLS。

生成复用既有 `ModelExplanationService(provider=None)` 和实际 ReferenceIds；NO_PROVIDER / TEMPLATE_REQUIRED 是合法 ready template，provider/model/request/usage/cost 全为 null，evidence_mode=not_used。GET 验证 canonical/hash/typed metadata/SKU 数字及 refs 后只读原结果。

## Root/Core 已冻结的 read_reply 必要合同

正式 Feishu 回复是本原 M1 必要功能。原接口冻结 d97 时仅有入站 receipt 的历史状态保留；本后端候选已实现专用 carrier / 原事务冻结 / 单 lease 发送接线，入站 `reply_delivery=pending` 表示需要外发，不代表实际送达。使用 forward migration `0015_p4_read_replies`，不扩原 outbox 或 p4_im_deliveries.kind，不借 clarification。

专用 `business.p4_read_replies` 每原 inbox UNIQUE 一行；kind 仅 task_status / explain_report。固定 reply_id、org/shop/principal/identity/App/Tenant/chat/type、explicit task/report/snapshot/facts/source tuple、captured as_of、canonical 安全 payload/hash、UNIQUE provider_uuid。状态 pending/sending/sent/unknown/dead、attempts 0..1、claim/first_attempt/实际 message_id/error/created_at。identity/source/payload/asof/UUID immutable，unknown/dead 终止且 no truncate。同事件去重复用旧行/旧 asof/UUID/payload；新明确消息才取新 asof。

发送前同事务锁并复核 current actor/grant/shop/identity、App/Tenant/OpenID、原 trusted chat 和群 allowlist、inbox receipt、visibleTask、captured source/report/snapshot/facts/status/version/hash。变化、撤权、跨 chat、失效或 stale → dead 安全码且零发送，不重选报告、不更新旧 payload。unknown 不换 UUID、不重发；RO reconcile 只用已有合法 API 和 Root 新窗口，不增加 IM 历史/search 权限，不用人看到消息代写 sent。

复用 BusinessIMSDK / BusinessMessage / NoticeResult、单 WorkerSession lease、PersistentSDKLedger 的 started 预占并在 SDK 前 commit，再一次 invoke/10s deadline；不新建 Task/job/Graph/runner/第二 dispatcher。SDKScope('read_reply') task_id 非空，ledger subject 只认 carrier reply_id/task/完整来源；每 carrier 的 read_reply method 全局唯一，换窗口也不能再调用。canonical child 使用显式 `--mode read_reply`，在 metadata/source/permission 校验后才可构造原 Factory；auth1/bot1/IM1、总 3 次上限、UTC expiry ≤30 分钟。metadata/cap/expiry/lease 任缺均零调用。scope/ledger 约束仅在新 forward migration，绝不改已应用 0011 等历史。

必要 Gate：两 kind / 新旧 asof；stale/revoke/crosschat/source/report/facts；并发 claim；before-send crash、started 预 commit、after-send unknown 停发；caps/expiry/lease/late sender；PG trigger/grants/SDKscope/source binding。业务 Task/job/approval/execution/Base/model 零增量，inbox/carrier/IM ledger 分列。实际 SDK/Secret/provider/IM/Base 本批均 0。源码、隔离 PG、独审与精确 CI 后，真实 IM 另由 Root 安排有限窗口。

缺失历史 cache / 命名 unavailable 仍 Web NOT_READY；Feishu 在合法完整显式报告 refs 上冻结 `read_code=NOT_READY` 的固定回复，不生成解释、不回填。新 cache 出现或来源/版本变化后，旧待发 payload 不升级；发送复核不匹配即 dead。同事件仍复用原 asof/UUID/payload，只有新明确消息取新 asof。

clarification 编号仍等待用户决定，本批不改 F02 创建/持久化/文案；原 C 仅消费已独审 d97 合同，消费者独审不替 backend/实际 API Gate，其他 UX hold。R13 v4 TOCTOU/deadline 与旧 PermissionError unknown 保持 HOLD，不在此批扩 private harness。

## 当前验证边界

接口先冻 d97（5 文件、tree 0e60），原 Web Reviewer 独审无 P1/P2；C 消费者 0ce9a131 独审无 P1/P2，仅 offline / Mock，尚未集成本候选。d97 不替当前 repository、迁移、GET、权限或发送源码验收。

最终作者离线 1768 passed / 478 deselected / 103.30s；Ruff/format 413 文件、mypy 308 文件、Markdown 101 文件均通过。完整 PG collection 478，existing 300 / phase3 178，交集 0、并集完整；新增模板 9 / 回复 18 共 27 全部入既有分区。仅将模板完整模块（实测约 34–36s）移入 existing，回复模块仍 phase3；原测试、14-node approval 分片和 300s / 23min / 25min / 75s cleanup 不变，未触发 CI。

最终全新自有 PG 批 27 新 + 5 原回归 = 32 实际通过：模板 9 / 35.78s、回复 18 / 56.58s、原 P3 投影 1 / 3.98s、原重观测 3 / 11.94s、原 P204 cache/budget 1 / 1.46s。三个 SIGKILL 点后实际 reap / OS absence / 原确认流程再取单 lease：claim 后、started 预提交后、Fake SDK 返回后；原 payload/asof/UUID 保持、unknown 不重发。原用户身份/可信 chat、approver-only、原作用表零增量、并发 inbox/claim、caps/expiry/lease/late sender、no_action、unavailable、历史不回填、SDKscope/trigger/grants 均分项验证。Fake SDK/PG 不冒正式 SDK 或 wire。

失败完整保留：模板首轮 collect helper 名误用、业务 0；第二轮 7 passed / 2 failed / 35.17s；第三轮 8 passed / 1 failed / 33.31s。time_only 的 capture provenance 会改变事实字节，不能误断言 facts_hash 相同；相同 facts 不同 observation ID 的 key 隔离另有 pure 验证。角色改动漏增 auth_version 被原 DB 正确拒绝。回复首合批模板 9 passed / 34.01s，回复 10 failed / 1 passed / 32.55s：同存活 PID 连取 WorkerSession 被启动门禁拒绝，原回归未运行。修正为独立准备子进程实际 stop/reap 后，第二批 9+14+5=28 PG 全通过；随后增量批 DDL caps JSON 的 `:1` 被 SQL text 误识别，迁移失败/业务 0，静态核 13 条 DDL 修正后无绑定参数，最终批通过。扫描两类代码/SQL形状误报通过重写表达修正，规则不放宽。

每轮独立登记 owner/project、无发布端口、全新 private600 PG 密码与绝对截止；最终 Runtime/测试源码与实际 snapshot hash 全匹配、停止确认 true、所有本批容器 0。首 collect-only 工具沿旧默认删除本轮新卷；后续全部 stop/down no-v、保本轮卷/凭据，原 known70 / 旧资源 / Secret 不读取、不迁移、不重启。私有收口 receipt hash `d107904bf945961743c038fcea87c08e954841066bd50de7defa4075556dd987` 保留每轮事实。

本候选仍待 Root/Core 精确冻结源码独审、C 普通集成、精确 CI 与未来有限真 IM Gate；未 push / 改 PR body / 合 main / 关 Issue。实际 SDK/Factory/Secret/provider/IM/Base 0，M1 / 全 BC02 / Phase4 未正式验收；旧 P13 v4 / PermissionError unknown 与历史证据不被新 PG 覆盖。
