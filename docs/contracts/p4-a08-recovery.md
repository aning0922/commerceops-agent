# A08 有限 profile 与恢复合同（实施候选）

2026-10-12 Asia/Shanghai。原A唯一后端/Worker/Graph/DTO/迁移/阶段导航 owner，B Base三产品文件、Base专属测试与PHASE4_BASE，C frontend/npm/Web/UX不并写。基线source9a的独审与四CI见[Root回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6110882129)；配置CAS仅改当前shop元数据及一条local_preparation audit，见[CAS回执](https://github.com/aning0922/commerceops-agent/issues/40#issuecomment-6111090153)。第二真人窗口仅产生新queued T1，Worker绑定超时、业务SDK0、Gateway同namespace reap仍not_verified，见[失败收口](https://github.com/aning0922/commerceops-agent/issues/40#issuecomment-6111191331)。历史失败不改写为成功。

本批只实施代码、pure与全新自有PG合成Gate；SDK/真人仍关闭。合同、必要测试、精确冻结SHA经Root原Core/Base/Web审查及精确CI后，平台窗口另核，本文不授予启动。整体初估8–12 Agent有效小时，复核workflow恢复缺口后重新说明剩余；原50h/300h内分配，不追加预算。当前工作段2026-10-11 16:37:16Z开始，硬截止20:37:16Z（客户端10-12 04:37:16）；wall≤4h、token≤80k、同源问题最多三轮，token遥测不可得则unknown并记wall/steps，禁止自动续期。人工H/L not_reported。

## 有限业务窗口

| profile | 固定业务与任务 | SDK method上限（auth/bot/table/field/IM/create/update/list） |
| --- | --- | --- |
| known70（原默认） | 原单项Q70；原最大5 task配置边界保留 | 1/1/2/2/2/1/1/4，总14；原general SDKWindow500不改 |
| group20 | 原已授权群和用户，同店baseline/twenty、L3/R7/S2，至多两个原群T1（拒绝与成功）；同fixture用于P2/T2/T4 | 1/1/2/2/4/20/1/42，总73 |
| approved_outbox | 一个completed且已有完整执行的可信原T1，同一item原unknown v1和可选已有pending v2 | 1/1/2/2/0/0/1/4，总11，IM/create方法禁止 |

所有窗口仍≤300s、Worker预留15s停止；caps可以更小，不能超过对应上限、不能添加method；实际分页/失败计入同一cap，完整性或预算不足即停止，不因“至少调用数”自动放大。group20成功一次20项/20×100/总2000，最后一SKU在途未知，全部计划/假设披露与联合确认复用原T3。拒绝0执行；完整联合成功仅一次永久T4/20item；普通approve、缺失/异集合、陈旧hash/version、转发chat/message、当前角色撤销均拒绝。同已决计划10次重复返回原决定；相反动作/不同actor冲突，不另建成功计划绕open pool。PG合成与真人重复分记。

## completed 外部 outbox-only 恢复

严格manifest绑定新Worker/Gateway UUID/截止、旧Gateway完整claim hash、旧入站inbox/identity/result/payload hash、原task/version、plan/hash/version、已消费approval/decision、已有completed execution、原item/outbox/client_token/投影与请求hash、旧SDK window/hash、旧Gateway与Worker真实终止receipt、当前原operator和审批actor auth_version及角色。旧Gateway完整参数必须等于新窗口；新Gateway max_workflows=0，不能创建T1。旧failed/queued/awaiting任务、离线fake投影、缺终止或当前权限不符在Factory/Secret/SDK前拒绝。

原parent wait/reap后核原child started的PID/host/namespace及OS缺席，将真实终止证明持久到既有不可变audit；缺原receipt则not_verified，不因容器退出补造。旧窗口历史缺proof不会因此变成功。manifest一次claim写原audit，不能同UUID重开；每次恢复维护前复核原绑定/当前权限/新active窗口。单Worker仍持原全局锁、心跳与停止协议，但不claim/recover Graph job、不调用审批协调器、不enroll IM/Base新意图，只选择manifest已有Base deliveries。

unknown v1任何年龄只原键reconcile，沿B strict15/完整分页/唯一内容版本读回，零条/省略nullable键/冲突/不符即hold并停止；不create、不换key、不复制审批。只有原v1 verified锚才能处理已有v2的原键update/完整读回。其他task/版本/outbox不被选择，内部执行/item/原outbox终态不回滚，不生成result IM。原三次attempt预算不重置。

## workflow/审批与kill恢复分层

上面仅外部副作用子profile，不替代P4/AC04/AC07。待审批跨进程、过早批准、决定已持久但T4未完成、业务提交前后kill/checkpoint实际恢复仍是必要Gate。优先复用原Gateway仍active的同一五分钟窗口和原单Worker/Graph；必要跨窗口恢复必须另绑定原receipt/plan/approval/decision/CP/原期限/当前角色/旧同namespace终止证明。不得刷新approval TTL、改nonce/hash、制造新决定/执行、复活failed或以P3旧恢复代证。

当前同active Gateway的新P4 T1/scoped单Worker已实际跑五个T2前后/waiting/T4前后kill恢复PG：过早批准拒绝、旧未确认OS阻断、实际wait=-9/同namespace显式确认、原CP/plan/nonce/hash/TTL及一次执行20项均验证；这是simulated_feishu/Fake受控进程与PG证据，SDK/provider0。跨Gateway workflow运行入口与实际SDK平台恢复仍pending，需Root独审/精确CI后的有限资源合同，尤其不能因Factory auth/bot=1已耗尽盲换window刷新业务预算。先交付outbox-only时必须明确这一剩余；不得据此宣称A08整体/M1/Phase4完成。平台ACK/断线、真人H/L、人工观察与完整AC仍not_run或not_reported，现有654 schema及旧offline v2证据沿原回执保留，不重复索取真人操作。
