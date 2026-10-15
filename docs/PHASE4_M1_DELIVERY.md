# Phase 4 / M1 剩余验收地图

更新：2026-10-15 夜间。**P4 / M1 仍为 partial；已有实现、实际 PG/Web 和真实 v1 RO 证据，真人 T6 / 实际 v2 及下列交付缺口尚未闭合。** 本页是剩余证据导航，不代替 Root 逐项验收，也不授权平台操作。

## 当前证据基线

- [Issue39 当前裁决](https://github.com/aning0922/commerceops-agent/issues/39)与原班 owner 协调为状态入口。PR43 已提交基线为 `049874ea3b5a2f814cce438f4602cc35cfd8b31d` / tree `8855ebc76c0fcb143a51410ac2cd53a4ddb92f9b`；[CI38734359318](https://github.com/aning0922/commerceops-agent/actions/runs/38734359318)五项 SUCCESS，Root 已核完整 504 PG、G1/G2、Web/N01 与清理。该 CI 不覆盖 A 当前未提交的 T6/v2 或新增 506 集合。
- 同 049 的 LAB full12 已由 Root 核定通过，证明其合成业务与外部 Fake 范围；不能当作真人操作或真实 Base v2。真实原 v1 RO 已 `verified / complete_unique`，原 manual 已 SPENT、Create1 / attempts3 保持，不为补地图重跑。
- C 原工作区 `phase4-web` / `codex/phase4-web`，本轮从 `432f3c2` 开始且 tracked clean；原四采集文件保持已审字节，不并改 A 源码。main 最后已核仍为 P3 的 `9d97c190`；P4 未合 main，未结案。
- 依据为 [PRD AC01–11](PRD.md#7-p0-交付验收)、[TEST_PLAN](TEST_PLAN.md)、冻结 18 逻辑界面的 [screens](ux/screens.yaml) / [交接映射](ux/ux-freeze-candidate.md)。冻结设计不等于 18 页均有当前真人证据；不新增设计批次。
- 原交付路线、故障分镜和历史结论保留于 [本页旧版](https://github.com/aning0922/commerceops-agent/blob/432f3c273fb94e820d8c9cabd55fa968e0efa279/docs/PHASE4_M1_DELIVERY.md)、[历史验收](PHASE4_ACCEPTANCE.md)、[Web 与原片 QA 记录](ux/phase4-implementation.md#既有证据怎样使用)。历史失败不改成通过，旧 pending 不覆盖当前已核事实。

## 逐 AC 证据与最小缺口

“已证实”指表内限定证据；“范围有限”不等于整项 AC 验收。真人缺口不要求重做已经通过的全部技术矩阵。

| AC | 已证实 / 可复用证据 | 范围有限 / 仍缺证据与最小补项 |
| --- | --- | --- |
| AC01 私聊、群 @ 闭环 | 049 正式 Gateway/T1/审批/执行的隔离 PG；原单用户真实 Gateway/Worker 历史；真实原项 v1 RO 完整唯一锚已核。 | **范围有限**：真实窗口曾接受新 T1，不等于私聊全部步骤及真人审批已签；原窗口 group_count=0。补齐私聊原链的可信回执/真人归属映射，并完成一次真实群 @ 全 20 SKU / 假设确认 / Base 关联，不重造原私聊任务。 |
| AC02 金标、事实不漂移 | P2 已验收金标；known70、twenty 20×100、raw null / effective 0 的 PG 与 Web；确定性规则不交给模型。 | **已证实限定技术范围**：把最终实际群报告逐项对回冻结 fixture / 参数 / 完整 20 行；无需新增模型调用或重算旧金标。 |
| AC03 拒绝零项、相反决定唯一 | `test_p4_a08_group_pg` 的联合确认/拒绝、十重放、相反 actor；P3 真实 PG 并发与 Web 决定场景，049 完整回归可复用。 | **范围有限**：缺当前正式真人卡片拒绝/冲突结果与原 task/decision 的配对；安排到同一有限群/审批批，拒绝分支不生成 item，不重复整个 PG 并发矩阵。 |
| AC04 十重放、提交边界恢复 | `test_p4_gateway_pg` 事件/ACK 重放；`test_p4_a09_workflow_pg` 跨 Gateway 五边界；单 Worker/执行唯一与 049 LAB 持久恢复。 | **范围有限**：技术矩阵不是真人点击十次或真实跨窗演示；核已有正式入站重放/kill 回执是否足量，再只补未覆盖的正式路径。不得在已终态原项上重做业务。 |
| AC05 身份、跨组织、hash、过期、撤权 | P3 authority、P4 group/identity/preflight/撤权 PG、真实 Web 权限和 N01 零业务拒绝均有可复用技术证据。 | **范围有限**：真实卡片的未授权人/当前范围拒绝与已审业务记录仍需配对；最少安排既有未授权测试身份的一次负向操作。其余完整组合用已核 PG/契约证明，不能声称平台全部负向已实测。 |
| AC06 外部故障、unknown 恢复 | Base adapter/reconciliation、delivery/IM PG 的 timeout/429/5xx/冲突/旧版本/unknown 不盲发；真实原 v1 unknown 后同键只读 verified / 同 record 锚。 | **范围有限**：已有真实恢复，不能再写“平台恢复全未跑”；仍缺真实 T6 后同 record v2 update/readback及当前同步画面。全部自然 429/5xx 并未因此被观测；Fake 注入、实际 unknown、真实 SDK 各自标识，不额外写记录制造故障。 |
| AC07 待审批跨进程、早决定不丢 | P3 checkpoint/ready、P4 A08/A09 五边界和同原 workflow/nonce/plan 恢复 PG 已覆盖；早期 SDK 重启未核事实保留。 | **范围有限**：正式真人卡片等待/恢复后原决定的关联演示未齐；可与群审批批共用一个已登记等待点，不重开同 pool 成功批。 |
| AC08 M1 干净 Compose、真实飞书 | 多次自有 Compose/真实 API+PG/Mock Web 部分闭环；049 LAB full12 / CI 的资源停止和不变量证据；旧录像有只读完成态补证。 | **缺最终交付证据**：最终稳定 SHA 在新空 checkout/新 owned project 的原始统一命令、成功新周期与重启/原回执回放、停止清理，以及对应真实私聊/群证据。LAB 进程 restart 不等于干净 Compose 重建。旧 source43 AC08 整体 failed/partial 保留；Woo 真实店只读属于 M2。 |
| AC09 来源、规则、模型/usage、工具与审批轨迹 | P2 一次 actual provider 解释及 usage/耗时已验收；P4 模板/冻结结果、read reply、events 来源绑定与真实 Web 只读可复用。 | **范围有限**：最终运行的来源/版本/审批/SDK 方法/同步轨迹和已有解释展示需串联；历史模型调用仅沿原绑定引用，不冒成本次新调用，无缓存显示 NOT_READY。P1 动态 Tool Agent / 40×3 不扩大为本次 M1 新 paid Gate。 |
| AC10 完整未知键、版本绑定、拒绝与幂等 | P3 A01–A08 与 P4 group20 的漏/多/篡改/跨版本/撤权/十重放 PG；Web 完整集合与 null/0 显示已有技术证据。 | **范围有限**：至少一次正式真人完整确认及拒绝的卡片/PG 关联未签；与群成功 20 项和独立拒绝计划合批。普通 approve 不代替联合确认，不能截断到前几项。 |
| AC11 T6、原因审计、新周期 | P3 C01–C05、旧 Mock complete/close、049 LAB T6/原键/重启、旧新周期完成态只读补证。 | **缺当前真人/平台闭环**：原项一次 human_web close、同 key GET / PG semantic hash/result/身份审计、唯一 v2 outbox、同 record update/readback；A 当前 WIP 不算通过。保留旧 task/execution/approval 与 3CP；新周期用已核历史或最终干净 Compose 补证，不重放旧 execution。 |

## F02、查询解释、群与恢复的实际边界

| 能力 | 当前可复用事实 | 仍需补的最少证据 |
| --- | --- | --- |
| F02 参数澄清 | [F02 合同](contracts/p4-f02-clarification.md)有默认关闭、原请求/轮次/当前身份、完整候选、显式确认同事务原 T1；049 包含正式 child 装配和 `test_p4_f02_pg` 的实际 Gateway-selected / Worker ledger 链（外 HTTP Fake）。 | 真实飞书“缺参→补参→确认→同原 T1”及原 UUID 回执仍缺；不能沿用首包“未接 child”旧状态，也不能以源码/PG 宣称真人已过。可作为后续一条群或私聊正式请求的前置步骤，避免额外成功业务批。 |
| 查询同任务、解释已有结果 | `test_p4_template_results_pg` / `test_p4_read_reply_pg` 已有真实 PG：固定来源、并发/十重放、零新业务、当前权限、不可变载体和 unknown；原 P2 actual 解释、Web 已有解释/NOT_READY 均可复用。 | 当前正式飞书原任务的进度查询与已有结论解释回复未有完整真人/SDK闭合证据；并入同一现场批，不新增模型付费调用。不得用 NOT_READY 冒充已有解释成功。 |
| 群 / 负向 / 恢复 | 049 group20 / callback / 原workflow / Base恢复已实际走隔离 PG、Fake 与 Web；原真实单用户窗口明确 group_count=0。 | 真人群 @、真实完整卡片/确认拒绝及必要权限负向；non@/self-bot 若平台不投递，只能证明平台行为，收到后的应用过滤仍按源码/受控测试记账。真实跨窗恢复与 PG kill/restart 分记。 |

## 最少现场批与可并行离线项

剩余至少分成两个逻辑现场批；可在一次协调中安排，但不能承诺共享一个 600 秒原库窗口或自动继承方法额度。

1. **当前唯一下一步：A 收齐同一最终 T6/v2 入口的隔离全链、故障清理、精确独审和新 CI，再由 Root 释放原项真人 T6 → 原 record v2。** 真实 v1 RO 不重跑，manual 不重置。人类明确提交一次 + DB 唯一效果不等于观测到网络 exactly-once；原 HTTP bytes 可为 not_captured，不增加 observer/DevTools/HAR。
2. **随后一次有限飞书场景批**：将 F02 补参、同任务查询/已有解释、群 @ / 全 20 项联合确认、独立拒绝、必要未授权点击和等待恢复配成一个明确对象清单。不能保证一个计划同时提供“拒绝零项”与“批准 20 项”；相反决定竞争的实际胜者决定后续最小对象数，由 Root 预先限定总量、pool 约束和原键。缺私聊完整归属时优先核原证据，不重跑已 verified 的私聊 RO。

可在正式现场前并行完成：最终新 checkout/Compose 的离线完整复现及录制、C 消费者/DTO/采集契约交叉核对、证据逐 AC 关联、说明文案/脱敏字幕准备、旧 P2 模型来源与性能报告的范围核对。已通过的 504 PG/Web 与金标不为填摘要重复运行；A 新源码仍须必要回归和精确 CI。性能复用 [P4 固定 100 事件/20 分析/扫描报告](contracts/p4-performance.md)，不能把 Mock 本地 p95 外推平台/供应商 SLA。

## 干净 Compose、18 页与录屏的剩余交付

- 最终 Compose 演示固定同一 source/tree/build/命令和新 owned project/volume：完整 20 SKU/未知键、拒绝零项、批准/执行、单项 T6、新旧周期隔离、持久重启与原键只读回放；结果按实际记录，失败保持 partial。只使用 MockCommerce，Fake/模型模式逐段标明；不能启动旧 profile 意外创建另一套 seed/API/Worker。
- 页面沿 S01/S02/S09 → S03/M03/M04 → S04 → S05/S11/M01 → S06 → M05/M02，F01/F02 采用相应真实渠道材料。18 逻辑页是设计范围，无须另造 18 次业务写入；S07/S08、390px、键盘/焦点、登录撤权的既有 Web 证据可作附录，缺当前展示则标缺镜头。
- 旧影片只有部分 20 行/投影标题与完成态，不是完整当前同步卡/close 原因/全链新周期录像。旧 QA 文档记载的两份私有 QA JSON 与三帧之一在本 C 当前路径未找到，**本轮仅确认路径缺失，不删除资产、不推断已丢失，也不把历史索引当现存文件证明**；由 Root 从既有保留包定位，若无法定位就明确缺素材。
- 最终录屏须完整可读地覆盖 20 行与 unknown/null、原因/版本、业务终态和独立同步、来源/usage/模型模式；真人与 simulated_web 分段，认证输入不录，原值/URL/标识/密钥不公开，不把旧 Fake 画面剪成真实 Base 过程。先保存私有原片和来源/hash，再脱敏 QA；片长不构成延长窗口理由。
- 最终 Root 汇总逐 AC 证据、剩余限制、无未解决 P1/P2、新精确 CI、正常 main 合并/合后同 SHA CI及 Issue 结案。P4/M1 未因本地图或当前 v1 RO 分项 PASS 而完成；原 300h / P4 计划 50h、H/L not_reported 及全部旧资源/Penpot/失败保留。
