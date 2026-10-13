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

正式 Feishu 回复是本原 M1 必要功能。现稳定模板切片仅完成读取与入站回执，`reply_delivery=not_requested` 代表外发尚未实现，不能计作端到端通过。后续在同 A owner/分支正常实现以下窄方案，不扩原 outbox 或 p4_im_deliveries.kind，不借 clarification。

专用 `business.p4_read_replies` 每原 inbox UNIQUE 一行；kind 仅 task_status / explain_report。固定 reply_id、org/shop/principal/identity/App/Tenant/chat/type、explicit task/report/snapshot/facts/source tuple、captured as_of、canonical 安全 payload/hash、UNIQUE provider_uuid。状态 pending/sending/sent/unknown/dead、attempts 0..1、claim/first_attempt/实际 message_id/error/created_at。identity/source/payload/asof/UUID immutable，unknown/dead 终止且 no truncate。同事件去重复用旧行/旧 asof/UUID/payload；新明确消息才取新 asof。

发送前同事务锁并复核 current actor/grant/shop/identity、App/Tenant/OpenID、原 trusted chat 和群 allowlist、inbox receipt、visibleTask、captured source/report/snapshot/facts/status/version/hash。变化、撤权、跨 chat、失效或 stale → dead 安全码且零发送，不重选报告、不更新旧 payload。unknown 不换 UUID、不重发；RO reconcile 只用已有合法 API 和 Root 新窗口，不增加 IM 历史/search 权限，不用人看到消息代写 sent。

复用 BusinessIMSDK / BusinessMessage / NoticeResult、单 WorkerSession lease、PersistentSDKLedger 的 started 预占并在 SDK 前 commit，再一次 invoke/10s deadline；不新建 Task/job/Graph/runner/第二 dispatcher。SDKScope('read_reply') task_id 非空，ledger subject 只认 carrier reply_id/task/完整来源。canonical child 使用窄显式 mode；metadata/cap/expiry/lease 任缺均零调用。scope/ledger 约束在新 forward migration，绝不改已应用 0011 等历史。

必要 Gate：两 kind / 新旧 asof；stale/revoke/crosschat/source/report/facts；并发 claim；before-send crash、started 预 commit、after-send unknown 停发；caps/expiry/lease/late sender；PG trigger/grants/SDKscope/source binding。业务 Task/job/approval/execution/Base/model 零增量，inbox/carrier/IM ledger 分列。实际 SDK/Secret/provider/IM/Base 本批均 0。源码、隔离 PG、独审与精确 CI 后，真实 IM 另由 Root 安排有限窗口。

clarification 编号仍等待用户决定，本批不改 F02 创建/持久化/文案；其他 UX 由原 C owner 等待释放。R13 v4 TOCTOU/deadline 与旧 PermissionError unknown 保持 HOLD，不在此批扩 private harness。

## 当前验证边界

首冻结提交仅包含 DTO/OpenAPI 与本合同文档，供 Root/Web 独审和 C 离线消费。模板 repository、迁移与 Feishu 接线在同 owner WIP 中，尚未作为稳定业务源码交付。

纯模板/旧模型读取相关批 99 passed / 21.89s；DTO/OpenAPI/模板定向 19 passed / 0.80s；mypy 127 文件通过。新隔离 PG 首轮迁移/checkpointer/grants/revision 成功，collection 因测试 helper 名称错误失败、0 业务用例，已修正。第二轮 7 passed / 2 failed / 35.17s，time_only 夹具断言和 Feishu 读取路径仍在定位；失败与后续实际结果分别记账。独审、精确 CI、正式 read_reply/真实平台/M1 整体仍 pending，不借旧 CI 验收新源码。
