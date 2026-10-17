# Phase 4 / M1 剩余验收地图

更新：2026-10-17。**私聊任务/审批、已提交的原 T6、真实 Base v1/v2 已由 Root 核收；P4 / M1 整体仍为 partial。** 本页是交付作者稿，待本功能批独审及正式集成；不代替逐项验收，不授权新平台动作，不表示真人已看到当前 Web v2 页面。

## 当前证据基线

- [Issue39 正式核收](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6229884679) / [PR43 回执](https://github.com/aning0922/commerceops-agent/pull/43#issuecomment-6229884891)：source `0c90880761f7065b33ccf6b1ffc1c3a9ba5dc597` / tree `6cf9bdd26ad596443df522919b8b87fcb01d4e62`，私有 `sealed-e30306c7`；[CI38953939340](https://github.com/aning0922/commerceops-agent/actions/runs/38953939340)五绿、530 PG / G1 / G2 / Web / N01。main仍 `9d97c19009d932036809ac3e2638bb68f4b7f765`，PR43未合并；新 F02/read_reply 父流程功能批不由旧 CI 代签。
- 实际北京时间 **12:49:00–12:49:46**：SDK7（auth1/bot1/table1/field1/list2/Update1）全 returned/HTTP200/code0，Create/IM/provider0；同原 key/item/outbox/record 的 v2 verified、attempts2、observed_version2，15字段及完整分页唯一读回成立。原 T6 已 COMMITTED，本次未重复登录、批准或关闭；此前失败/SDK9/Create1 保留，该链累计SDK21/Create1/Update1不含其他独立探针。
- CLI/operation/cleanup均0，writers退出后、PG down前取最终快照；原关联 task/approval/item/关闭请求/item audit/outbox/link **七类原对象行**与前态相等，不扩为全库 execution 或逐表计数不变。资源0、端口关闭、保卷；Root与独立Reviewer回执SHA `5b52d7861ec6fe1b5eab5730170275f71d669e106c27b81567a0b4576972c22c`。原始HTTP wire未采集，不主张网络 exactly-once，也不把服务端/平台读回当真人页面观察。

<details><summary>10月15–16日基线、失败与只读诊断历史（仅当时状态）</summary>

- 旧源码 `049874ea` / [504 PG CI](https://github.com/aning0922/commerceops-agent/actions/runs/38734359318)、`0da42295` / [506 PG CI](https://github.com/aning0922/commerceops-agent/actions/runs/38834680327)保留。以下 NOT_RUN/NOT_VERIFIED、待恢复与 HOLD 是当时范围，不推翻10月17日单记录核收，也不倒改原失败回执。
- 历史 049 LAB full12、原 v1 RO `verified / complete_unique`及 manual SPENT / Create1 / attempts3 保留。旧密码未找回，旧库零操作；[fresh 新链批准](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6208312714)已允许新 task/item/record，当前不再要求恢复旧项后才能继续，也不重跑旧 RO。
- [locator/SYN 回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6208430056)：locator auth1+wiki1，fresh metadata4/6成功且额度已 SPENT。[首 business-ready 窗失败](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6208832737)发生于 Gateway/Worker 前，business SDK/T1/item/outbox/Base/IM 均0，已 down、资源0、保卷；失败窗不得复用。
- [readiness 修订回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6209264870)已独审：同实际 entry 的 API、hydrated、CSRF/session、实际 synthetic login → native Worker → v1 → 同 browser close → 同 record v2 与失败 cleanup 的合成证据成立（索引 `7e3464…` / final `7c1a47…`，27 refs）。仍为 Fake/合成，真人和真实 v2 **NOT_RUN**，不外推未冻结增量已被上述 CI 覆盖。
- [最新真实窗口回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6210030852)：新本地 arm 实际成功，服务通过 hydrated/CSRF/session 检查，真人确认登录并发送一次 DM；没有批准卡片或 Web close。Gateway 启动且有外向 TLS443，**不证明 WS 认证、订阅或入站就绪**。当时两次 watch 均报告未取得合格 T1；后续离线核实第二次未执行 SQL，不能解释为 SQL 查空；终核“业务表全零”断言失败且未先保存 counts，故最终 T1/inbox/receipt/job/item/outbox 均为 **NOT_VERIFIED，不得写0**，也不能断言消息永远未入库。Worker 未装配/启动，卡片、业务 SDK、Base create/update 均0；Gateway 网络请求总数未独立采集，不能写0。实际回执 SHA256 `d3a7ab800467d3c383600976dd0c7c0902310aaf9aafc484b0be262dd66770ee`。所有父/子进程已停并 reap，PG down0、容器/网络0、端口关闭、保卷；不重发、不重开，历史 locator/metadata 消费不重跑。
- [后续唯一 PG-only 只读核验](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6210671544)已 exit0、独审通过并停止保卷：inbox1/receipt1，原合同 tasks2（queued）/jobs2（ready、attempts0），无 clarification/item/outbox/Base/IM，仅历史 metadata4。规范原指令 hash、当前 actor/auth3、参数及窗口谱系匹配，**已解除最终是否受理的不确定性，业务尚未执行**；不得把这些后续事实倒写成旧失败当时已核实。receipt 在原 arm 后115.816652秒落库，前120秒准入仅余4.183348秒，Worker未启动；WS认证/订阅ack仍无独立证明，不将时间缺口称为全部唯一根因。
- A 离线核实际旧入口已确认：第二次 watch 剩余约145秒，`while remaining>=180` 未进入，`T1_unique=false` 是初值；旧“第二次 SQL 成功但未查到”表述已纠正，旧文件保持。第一次 watch 因 `remaining>190` 条件提前结束，异步 shell 返回后 bind/Worker 未自动接续；receipt 在首次观察后约5.70秒持久化。原因索引 SHA256 `06007693c5942d29e07ab5f1de2a5ef8d498002a260ec1ca9d116eae87ed9a43`，待整批 Core 独审；修正仍进行中，不预写修复 Gate 通过，也不把准入时间缺口说成全部唯一根因。
</details>

- C 原工作区 `phase4-web` / `codex/phase4-web` / HEAD `432f3c2`；本轮仅在已有已审文档补丁上更新状态，原四采集文件保持已审字节，不并改 A 源码。main 最后已核仍为 P3 的 `9d97c19009d932036809ac3e2638bb68f4b7f765`；P4 未合 main，未结案。
- 依据为 [PRD AC01–11](PRD.md#7-p0-交付验收)、[TEST_PLAN](TEST_PLAN.md)、冻结 18 逻辑界面的 [screens](ux/screens.yaml) / [交接映射](ux/ux-freeze-candidate.md)。冻结设计不等于 18 页均有当前真人证据；不新增设计批次。
- 原交付路线、故障分镜和历史结论保留于 [本页旧版](https://github.com/aning0922/commerceops-agent/blob/432f3c273fb94e820d8c9cabd55fa968e0efa279/docs/PHASE4_M1_DELIVERY.md)、[历史验收](PHASE4_ACCEPTANCE.md)、[Web 与原片 QA 记录](ux/phase4-implementation.md#既有证据怎样使用)。历史失败不改成通过，旧 pending 不覆盖当前已核事实。

## 逐 AC 证据与最小缺口

“已证实”指表内限定证据；“范围有限”不等于整项 AC 验收。真人缺口不要求重做已经通过的全部技术矩阵。

| AC | 已证实 / 可复用证据 | 范围有限 / 仍缺证据与最小补项 |
| --- | --- | --- |
| AC01 私聊、群 @ 闭环 | 私聊 task/审批/原 T6 与 Base v1/v2 已核收；原单用户链与049等隔离PG历史保留。 | **私聊限定范围已证实，群仍缺**：真实群 @ 全20 SKU、完整假设确认及Base关联仍待；同任务F02/查询解释属于新功能批，不由该单项成功外推。 |
| AC02 金标、事实不漂移 | P2 已验收金标；known70、twenty 20×100、raw null / effective 0 的 PG 与 Web；确定性规则不交给模型。 | **已证实限定技术范围**：把最终实际群报告逐项对回冻结 fixture / 参数 / 完整 20 行；无需新增模型调用或重算旧金标。 |
| AC03 拒绝零项、相反决定唯一 | `test_p4_a08_group_pg` 的联合确认/拒绝、十重放、相反 actor；P3 真实 PG 并发与 Web 决定场景，049 完整回归可复用。 | **范围有限**：缺当前正式真人卡片拒绝/冲突结果与原 task/decision 的配对；安排到同一有限群/审批批，拒绝分支不生成 item，不重复整个 PG 并发矩阵。 |
| AC04 十重放、提交边界恢复 | `test_p4_gateway_pg` 事件/ACK 重放；`test_p4_a09_workflow_pg` 跨 Gateway 五边界；单 Worker/执行唯一与 049 LAB 持久恢复。 | **范围有限**：技术矩阵不是真人点击十次或真实跨窗演示；核已有正式入站重放/kill 回执是否足量，再只补未覆盖的正式路径。不得在已终态原项上重做业务。 |
| AC05 身份、跨组织、hash、过期、撤权 | P3 authority、P4 group/identity/preflight/撤权 PG、真实 Web 权限和 N01 零业务拒绝均有可复用技术证据。 | **范围有限**：真实卡片的未授权人/当前范围拒绝与已审业务记录仍需配对；最少安排既有未授权测试身份的一次负向操作。其余完整组合用已核 PG/契约证明，不能声称平台全部负向已实测。 |
| AC06 外部故障、unknown 恢复 | Fake故障矩阵、真实v1 unknown同键恢复与10月17日同原record v2 Update1/完整唯一读回均已核收，旧失败和SPENT不变。 | **平台恢复限定范围已证实**：不能称自然429/5xx等全部真实观测；当前Web同步展示仍缺一次只读观察，不为镜头增加写入。 |
| AC07 待审批跨进程、早决定不丢 | P3 checkpoint/ready、P4 A08/A09 五边界和同原 workflow/nonce/plan 恢复 PG 已覆盖；早期 SDK 重启未核事实保留。 | **范围有限**：正式真人卡片等待/恢复后原决定的关联演示未齐；可与群审批批共用一个已登记等待点，不重开同 pool 成功批。 |
| AC08 M1 干净 Compose、真实飞书 | 多次自有 Compose/真实 API+PG/Mock Web 部分闭环；049 LAB full12 / CI 的资源停止和不变量证据；旧录像有只读完成态补证。 | **缺最终交付证据**：最终稳定 SHA 在新空 checkout/新 owned project 的原始统一命令、成功新周期与重启/原回执回放、停止清理，以及对应真实私聊/群证据。LAB 进程 restart 不等于干净 Compose 重建。旧 source43 AC08 整体 failed/partial 保留；Woo 真实店只读属于 M2。 |
| AC09 来源、规则、模型/usage、工具与审批轨迹 | P2 一次 actual provider 解释及 usage/耗时已验收；P4 模板/冻结结果、read reply、events 来源绑定与真实 Web 只读可复用。 | **范围有限**：最终运行的来源/版本/审批/SDK 方法/同步轨迹和已有解释展示需串联；历史模型调用仅沿原绑定引用，不冒成本次新调用，无缓存显示 NOT_READY。P1 动态 Tool Agent / 40×3 不扩大为本次 M1 新 paid Gate。 |
| AC10 完整未知键、版本绑定、拒绝与幂等 | P3 A01–A08 与 P4 group20 的漏/多/篡改/跨版本/撤权/十重放 PG；Web 完整集合与 null/0 显示已有技术证据。 | **范围有限**：至少一次正式真人完整确认及拒绝的卡片/PG 关联未签；与群成功 20 项和独立拒绝计划合批。普通 approve 不代替联合确认，不能截断到前几项。 |
| AC11 T6、原因审计、新周期 | P3 C01–C05及旧Mock技术证据保留；原真人T6已提交，原对象真实v2恢复已核收且未重复T6。 | **当前单项T6/v2已证实**：仍缺本次Web结果只读观察与最终新周期/旧执行不复活的交付证据；七类原对象相等不冒充全库execution计数已采。 |

## F02、查询解释、群与恢复的实际边界

| 能力 | 当前可复用事实 | 仍需补的最少证据 |
| --- | --- | --- |
| F02 参数澄清 | [F02 合同](contracts/p4-f02-clarification.md)有默认关闭、原请求/轮次/当前身份、完整候选、显式确认同事务原 T1；049 包含正式 child 装配和 `test_p4_f02_pg` 的实际 Gateway-selected / Worker ledger 链（外 HTTP Fake）。 | 真实飞书“缺参→补参→确认→同原 T1”及原 UUID 回执仍缺；不能沿用首包“未接 child”旧状态，也不能以源码/PG 宣称真人已过。可作为后续一条群或私聊正式请求的前置步骤，避免额外成功业务批。 |
| 查询同任务、解释已有结果 | `test_p4_template_results_pg` / `test_p4_read_reply_pg` 已有真实 PG：固定来源、并发/十重放、零新业务、当前权限、不可变载体和 unknown；原 P2 actual 解释、Web 已有解释/NOT_READY 均可复用。 | 当前正式飞书原任务的进度查询与已有结论解释回复未有完整真人/SDK闭合证据；并入同一现场批，不新增模型付费调用。不得用 NOT_READY 冒充已有解释成功。 |
| 群 / 负向 / 恢复 | 049 group20 / callback / 原workflow / Base恢复已实际走隔离 PG、Fake 与 Web；原真实单用户窗口明确 group_count=0。 | 真人群 @、真实完整卡片/确认拒绝及必要权限负向；non@/self-bot 若平台不投递，只能证明平台行为，收到后的应用过滤仍按源码/受控测试记账。真实跨窗恢复与 PG kill/restart 分记。 |

## 最少现场批与可并行离线项

当前原记录恢复窗口已完成并关闭；剩余额度不转作新业务，不重跑T6或v1/v2、不增加登录/批准/关闭来凑镜头。

1. **当前唯一下一步：A 在原PR43完成 F02/read_reply 父流程最小生命周期接线及真实模板实际入口的合成全链，再经同批独审、精确CI和Root统一准入，安排有限真实窗口。** 当前只是功能批实施/准备，不预写真实F02、查询解释或群业务通过。
2. 后续现场将F02补参、同任务进度/已有结论解释、群@完整20项联合确认、独立拒绝、重复冲突及必要负向恢复配成有限对象清单；一个计划不能同时证明拒绝零项和批准20项。Root限定对象、pool、次数及清理，既有成功私聊链只读引用，不另造管理体系或重复平台探针。

## 最短演示路径与唯一 Web 只读观测

| 演示段 | 复用已核证据 / 路径 | 当前仍需的观察或镜头 |
| --- | --- | --- |
| 私聊业务与同步结果 | S09任务→S04原审批→S11原项/原因/版本→同步事实，关联10月17日同record v2核收。 | **一次统一授权的Web只读会话**：在现有Web/API读取同原task/item、原key GET、closed/v2、原原因/actor、当前Base v2 verified/complete_unique及历史v1；不新建T1/T3/T6或平台写。登录属于认证单列，业务POST应0。实际入口/source/build/身份refs由A/Root供给，本轮不开页。 |
| 来源、模型与说明 | S03/M03报告事实→S06事件→M04已有解释；[P2一次真实模型证据](PHASE2_ACCEPTANCE.md)按原report/usage/耗时绑定引用。 | 新P4模板说明明确 template/not_used，不伪造成新模型调用；无既有解释显示NOT_READY。真实查询/解释reply由A新功能批补验，CI页面能力不冒充已被真人看见。 |
| 群、未知确认与拒绝 | F01/F02渠道材料→S03完整20行/null→S04完整键确认或独立拒绝→S09执行。 | F02/查询解释/群20与负向真实证据仍待，补完整20行可读、未知键全量、意见受理与执行分开画面；不能重剪旧partial当本次群成功。 |
| 新周期、复现和收尾 | S11结果→M05/M02新草稿→新分析审批→独立执行；原回执只读回放。 | 最终新空checkout/干净Compose全链、新周期/持久重启、清理与最终录屏仍待；LAB进程restart不等于AC08干净Compose。 |

现有Web/N01实际CI证明已审源码下页面/API行为；`simulated_web`、真人点击报告、真人对最终页面的实际观察分别记账。上述只读会话是当前单项成果的最低补充观察，不等于所有18页或全部M1已验收。优先在Root后续统一演示窗口一次完成，不为文档另开服务、浏览器或第二套工具。

可在正式现场前并行完成：最终新 checkout/Compose 的离线完整复现及录制、C 消费者/DTO/采集契约交叉核对、证据逐 AC 关联、说明文案/脱敏字幕准备、旧 P2 模型来源与性能报告的范围核对。已通过的当前 530 PG/Web 与金标不为填摘要重复运行；后续源码变化仍须必要回归和精确 CI。性能复用 [P4 固定 100 事件/20 分析/扫描报告](contracts/p4-performance.md)，不能把 Mock 本地 p95 外推平台/供应商 SLA。

## 干净 Compose、18 页与录屏的剩余交付

- 最终 Compose 演示固定同一 source/tree/build/命令和新 owned project/volume：完整 20 SKU/未知键、拒绝零项、批准/执行、单项 T6、新旧周期隔离、持久重启与原键只读回放；结果按实际记录，失败保持 partial。只使用 MockCommerce，Fake/模型模式逐段标明；不能启动旧 profile 意外创建另一套 seed/API/Worker。
- 页面沿 S01/S02/S09 → S03/M03/M04 → S04 → S05/S11/M01 → S06 → M05/M02，F01/F02 采用相应真实渠道材料。18 逻辑页是设计范围，无须另造 18 次业务写入；S07/S08、390px、键盘/焦点、登录撤权的既有 Web 证据可作附录，缺当前展示则标缺镜头。
- 旧影片只有部分 20 行/投影标题与完成态，不是完整当前同步卡/close 原因/全链新周期录像。既有盘点中，旧 QA 文档记载的两份私有 QA JSON 与三帧之一在原 C 路径未找到，**仅记当次路径缺证，不删除资产、不推断已丢失，也不把历史索引当现存文件证明**；由 Root 从既有保留包定位，若无法定位就明确缺素材。
- 最终录屏须完整可读地覆盖 20 行与 unknown/null、原因/版本、业务终态和独立同步、来源/usage/模型模式；真人与 simulated_web 分段，认证输入不录，原值/URL/标识/密钥不公开，不把旧 Fake 画面剪成真实 Base 过程。先保存私有原片和来源/hash，再脱敏 QA；片长不构成延长窗口理由。
- 最终 Root 汇总逐 AC 证据、剩余限制、无未解决 P1/P2、新精确 CI、正常 main 合并/合后同 SHA CI及 Issue 结案。P4/M1 未因本地图或原记录 T6/Base v2 单项 PASS 而完成；原 300h / P4 计划 50h、H/L not_reported 及全部旧资源/Penpot/失败保留。
