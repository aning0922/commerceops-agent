# A09 单原 workflow 跨 Gateway 接续合同

2026-10-12（Asia/Shanghai）。A 唯一 backend writer；A08 精确 efcd 的 Core/四 CI/422 PG 已由 Root 核定（Issue40/39 回执），不以其证据验收本 A09 新代码。当前新恢复入口已实现候选、独审/精确 CI/真人 SDK Gate pending。

`ControlledWorkerWindow.profile=approved_workflow` 必须只有一个显式 task_id，附 `ApprovedWorkflowRecovery(schema_version=p4-approved-workflow-v1)`。新 Gateway 必须已按原正式 claim/原子进程启动合同取得唯一 App lease，max_workflows=0，原 Mock 参数相同；最长窗口300s/15s停机预留。新 SDK UUID/新有限预算需 Root 单独批准；上限不超过原已核 SDK 窗口各方法且绝对不超过 group20 的73，auth1/bot1。不给新 T1、通用调度或额外 provider 权限。

manifest 绑定新 Worker/Gateway UUID与期限；原 Gateway claim/hash和完整 child started→同原 process/child_reaped/int child_exit 的 termination；原 Worker owner/唯一 started/显式 termination UUID、同 host/namespace 与 OS 已确认的证据（clean stopped 或 SIGKILL 后原 confirm_termination，不能凭锁可取得或 lease 过期）。终止证明均须先于新 Gateway claim。只接受原 SDK window/hash、同 org/shop、controlled_sdk enabled、在原 Worker 生命周期内持久的 auth HTTP200/code0 returned 账本；Fake账本测试不成为正式认证证据。

原 T1 绑定 task UUID/version、不可变 request/thread/source-task/参数/config hash、inbox/receipt hash、当前原 requester/platform identity/app/tenant/白名单/operator auth_version/current role，以及 group chat。共同 trusted_tasks 沿原 Gateway claim 的时间边界验证，不将新 Gateway 的 T1 起点套到旧 receipt。queued/analyzing 只有原 attempted job/旧 owner或旧 Worker 生命周期内 job 回执 + 已持久 checkpoint 才允许；旧 live binder 超时后 Worker0 的 queued、failed/needs_attention 无法通过。已停 Gateway 在原 guard 和 controlled 准入中关闭，不因原 expiry 尚未来到重开。

已有 approval 绑定原 id、plan id/version/hash、eligible、nonce digest/key version、created_at/expires_at 的不可变 hash；原决定有则绑定 decision_id/payload_hash，原 execution 有则绑定 execution_id。每轮 idle maintenance 再核当前 T1/角色及原不可变绑定；原 Graph 自身继续校验 checkpoint/request/plan/nonce/TTL/决定、T4当前权限/原执行唯一性。before-T2 尚未提交的原事务只能沿原 thread/原 analyze job生成首个计划；不得刷新已持久 plan/审批时间/决定或 outbox key。重验证需新审批或故障即停止本显式范围，不能以恢复批准代替业务批准。

IM 已 unknown/sending 的任务不能借此 profile 重发卡片；Base unknown 继续原 B 严格唯一 anchor 的 reconcile，原 UUID/client_token 不换。completed outbox-only 仍用 A08 approved_outbox profile，不以该 profile 代签未完成 workflow。IM sending→unknown 的恢复限定当前 org/shop/task/verification_mode，窗口外行不改；新任务及全部原 source 外 job 不恢复/领取/reconcile。

作者首批新 PG 五边界均在有界 ready/state/jobs 等待失败（具体子进程错误原未捕获，保留）；502 挂载 source无差异/10实际四模块 import匹配，19:18:33.659260Z stop/down0/资源0/保卷。源码核到初版对不可变 p4_inbox_receipts 多用 FOR SHARE，低权运行角色仅SELECT/INSERT；移除该额外锁，不扩权。修正后单 before-T2 实际PG1/1通过，14.094 testcase秒/2 import匹配，19:21:15.339510Z stop/down0/资源0。随后完整21/21 PG通过（新五边界+14子负例一个case与原15回归），testcaseΣ196.692/suite201.415秒，21实际Worker四import匹配/504source0差，19:29:13.390229Z stop/down0/资源0/保卷。首失败仍保留，不以定向成功覆盖。所有 SDK/client/secret/provider 实际0；PG/Fake ledger 单独标识。

本 A09 段真实起始19:03:09Z，停止01:03:09Z（客户端03:03:09→09:03:09 +08）；原A08诊断20:37:16Z不续期，自有PG每批≤30min/同源≤3。D1/D30/50h/300h不重置，human H/L not_reported；B/C/Penpot/旧资源/权限与Paid/生产/Woo/Phase5边界保持。
