# Phase4 / M1 分层验收（实施中）

2026-10-11，Asia/Shanghai；[阶段39](https://github.com/aning0922/commerceops-agent/issues/39)/[A40](https://github.com/aning0922/commerceops-agent/issues/40)/[B41](https://github.com/aning0922/commerceops-agent/issues/41)/[交付42](https://github.com/aning0922/commerceops-agent/issues/42)。基线 main9d97c19009d932036809ac3e2638bb68f4b7f765，同 SHA 四 CI38093693335 SUCCESS，P3 Issues33–35 CLOSED；[P3结案](https://github.com/aning0922/commerceops-agent/issues/33#issuecomment-6103315682)及[历史证据](PHASE3_ACCEPTANCE.md)保留。用户已直接授权Phase4持续开发，本页不宣称M1通过。

当前2026-10-11部分收口：Root核06cd精确四CI38120338660 SUCCESS/完整375PG，source43原Core无P1/P2且必要A06现场PG1通过；新owned Compose的A known/API/T6/恢复部分通过，C实际三创建额度已消费，known读取/20拒绝零项/20完成与单T6通过，第4cycle needs_reapproval/v1已批v2待批/零执行。整体AC08 failed/not_accepted，M1/Phase4实施中；正式SDK/Base/Card/Feishu/human及source43新精确CI仍pending。详见[STATUS45](STATUS.md#45-phase4源码与受控m1部分验收)和下方当前矩阵；旧正文为当时证据，不覆盖最新收口。

## 当前范围与责任

A唯一共享合同/迁移/业务/outbox/Worker/Graph/Python锁/CI/Compose/阶段文档owner；B新Base三模块/测试/文档按Issue41独占，前端沿原owner。共享[p4-v1候选](contracts/p4-v1.md)与机器DTO/Protocol须Root独审后冻结。第一批仅offline/全新自有PG，真实平台0；资源有效性后续由Root受控诊断，不把旧probe存在/权限scope当作当前可用证明。

固定D1=10-10/D30=11-08/300h，P4 D13–17/50h，A18+B14+交付8+审核集成10是估计分配，人工H/L not_reported，Agent墙钟/机器等待另记。旧1057offline/337PG/24Web、旧失败/风险/资源/18页设计保留；无Phase5/Woo/生产/扩权/新成员/新增paid/强推/破坏清理。

## 必须证据矩阵

| Gate | 必需证据 | 当前P4状态 |
|---|---|---|
| 合同/身份 | strict DTO、可信平台桥接、锁后当前权限、Web共用T3 | d039及后续Core/Base/Web精确独审分层保留；source43 noP1/P2、Gateway PG1实际通过；真人身份/scope仍未核 |
| AC01 | formal私聊+群@ task/approval/execution/item/Base关联，真人另列 | not_run |
| AC02/09 | 金标/事实约束/P2实际解释与usage引用/轨迹 | P2/P3事实保留；P4 Mock known70/完整twenty20×100实证，M1不因此全过 |
| AC03/04/05/07/10 | 批准拒绝/全20SKU/完整unknown集合/10重复/冲突/期限/撤权/跨店租户/篡改/提交边界kill/CP | A01–A04定向PG与06cd精确CI分层；当前C模拟Web 20拒绝零项/20完整批准创建通过，正式真人与全部M1 Gate未签 |
| AC06/R13–16 | Basecreate/readback/T6update/ACK丢失/429/5xx/code/写冲突/旧版本/IMunknown超过1h | 原Base/Core Fake定向证据保留；当前23 offline_fake投影verified，非远端ACK；正式SDK/readback仍not_run |
| AC08 M1部分 | clean自有Compose离线与真Feishu；Woo留M2 | 当前owned Compose partial failed：known/T6/持久恢复通过，C第4cycle重批未完成；真人Feishu not_run，不验收 |
| AC11 | 完成关闭/原因审计/同步/新周期，不复活旧执行 | Aknown close v2+原键回放、C单项complete v2通过；原cycle needs_reapproval/v2待明确批准/无重复执行，目标未完成 |
| Web/性能 | 20SKU/角色登录撤权/390px/键盘焦点/真实服务权限/100受控入站p95/离线分析/恢复调度 | A02固定100/20/扫描证据保留；06cd三Web实际CI通过，当前C现场四步通过但整体exit1，不签所有Web/M1 Gate |
| 回归 | 既有1057offline/337PG/24Web完整保留，新测试另计 | 06cd精确CI完整375PG、source43新增Gateway PG1另计，非source43完整376回归；新最终CI未跑 |
| 交付 | M1复用P2actual1轨迹/降级（40例/三轮留M3）、配置挂载/资源清单/演示/真人与PW分记 | 配置/清洁Compose/恢复及私有raw视频部分实证；C raw视频QA未签、真人未跑，UX8/N01只待授权排期 |
| 独审/CI/main | 精确冻结SHA无P1/P2/CI/Root普通合main/合后同SHA CI/结案 | 06cd四CI SUCCESS与source43 Core noP1/P2分记，main9d97保持；后续source43/本doc独审精确CI/正式结案pending |

## 证据记账规则

各结果写source、command、实际exit/count/time、source/model/approval_mode、固定窗口/owner/停止证据。offline Fake、真实PG、SDK源码/官方文档、真人/平台、CI与main分层，不将作者自检记独审或将部分运行记全通过。当前没有新增P4正式真人/平台/provider证据；首提交与后续source/CI以原PR和Root回执绑定，不自指未来提交。

P4-A01当前作者证据与真实负证据见[PHASE4_A01](PHASE4_A01.md)及[安全摘要](contracts/p4-a01-author-evidence.json)。1120offline、旧337+19PG与跨入口2分层；性能100/20/调度为候选统计，pendinginterrupt/gold/sample补证仍待，不由此签M1。主体freeze/独审/精确CI/平台/交付/结案待，P3历史保持。

A02作者新补证见[PHASE4_A02](PHASE4_A02.md)及[安全摘要](contracts/p4-a02-author-evidence.json)：固定澄清窄reply/零业务对象、原UUID/未知停止重发与同Worker维护，30PG/56.65s和另1WorkerPG/6.84s；全1284offline/88.94s、367integration deselected。100本地SDKACK/PGcommit p95=.013282208s，预定20完整baseline goldmatch p95=.805768959s，真实pending idle=.037212458s/busy下一点=.045891333s补证只在固定scan1s/Mock范围；平台网络、人类审批、全20真实Card/Base闭环及M1未验收。低权3flagsfalse/tempDB0，固定04:42:39截止内停止/仅own网络释放保卷，不续期。新的独审/精确CI待。

C610/38111683908实际quality成功，phase3原approval模块300秒超时（28actual/27callpass/最后card_only未结束，0 assertion failed trace，后94not_run）、frontend real read失败且具体nodeunknown、pg-pair正确失败；[只读核对回执](https://github.com/aning0922/commerceops-agent/issues/40#issuecomment-6105516903)。545旧PG成功不替当前Gate，C的new-cycle P1修复/独审亦待Root解除；不重跑、取消、放宽期限或新开重大未知PG窗口。

## 当前source与AC08部分实证

[Root当前CI回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6106924247)绑定06cd2af59c338272ad5a0d117da9f8d7cef62094/CI38120338660四SUCCESS，完整236+139=375/actual-callpass375/disjoint/G1三/G2六/cleanup0；frontend read/write/items实际通过、13安全hash0偏差/20items2000units/provider0。旧CI失败、read unknown与27测试误断言、972未知不能由新成功抹除。source43c40bb955a1ce4ef07704173759983eb8c8f4f5/tree25dde89c392b82b71060b05812f38807fb9bbcf2原Core59pure5.37s/type2/noP1P2与Gateway现场1pass10.366s另计，不冒称新376完整回归。

本次m1off-a6e82834c857原UTC T0 08:33:24.939856Z、service09:03:24.939856Z/outer09:13:24.939856Z不复位；原0012/低role三false/tempDB0、seed一次、新synthetic session/Mock单Worker/Graph、485源码hash0偏差及BUILD_ID绑定真实运行。第一次caller错误字段partial failed后，Root只准一次同源同卷同绝对期限续验：先核旧started/stopped/termination完整链与其他runtime session0/锁，再核原known70/原T6close v2+同key一次效果、SIGUSR1及全服务restart，10组持久SHA256一致。无新seed/newknown/重T3、SDK/provider0。

C实际headless exit1且已停；四步known只读、group20拒绝零项、group20完成20项、单T6完成v2通过，第三个新cycle后段停止。当前有效Actor/权限只读PG确认4workflow为2completed/1rejected/1needs_reapproval，2executions/21items/2070内部units；Aclosed1、Ccompleted1、open19；cycle v1已批v2待批，两版各1item70、无执行/工作项。原execution-plan-item绑定完整，outbox28外部active0、23Fake投影verified、SDKledger0。完整Actor/状态证据及[停止回执](https://github.com/aning0922/commerceops-agent/issues/40#issuecomment-6107403734)支持部分实证，不支持newcycle pass或整M1验收。

cycle actual failure_code及完整源/观测差异未捕获：只读diag第一轮字段名report_id错误（正确source_report_id），第二轮被原cleanup停container而exit137；75s reserve没有为诊断延长。源码唯一生成pending v2的replace路径设置PLAN_CHANGED，并要求material_hash变化；collect读同shop全部open项，hash保留这些项。一轮原known+twenty disjoint19open离线复核显示相同fixture/params、数值同70而材料hash变化，支持既有重批保护/场景预期遗漏；[分类回执](https://github.com/aning0922/commerceops-agent/issues/40#issuecomment-6107433806)明确为源码推断，不是actual observation delta或Core缺陷证明。Root随后准PG-only只读scope时，核当前UTC09:12:07已超过09:11:30查询截止，未启动资源/延期；最小精确原cycle数据读取仍pending。不能降低重批保护或补批准追赶Gate。

原父截止进入收尾、C失败完成文件到达已cleanup，RuntimeError仅指完成metadata未在父cutoff到达；09:02:13.931583Z stop0/09:02:14.553147Z仅own down0/no-v/PID0、containers0/networks0/listeners0/tempDB0，保留卷/images/700与600完整私包。旧d868 partial/aea SQL失败及原CI未知/旧Gate保留，source43新CI、本四文档精确独审与阶段收口以Root实际回执另记，不预填未来SHA。

[UX8与N01](https://github.com/aning0922/commerceops-agent/issues/42#issuecomment-6107359838)仅待授权排期，当前Web结构化与PRD+冻结M02自然语言BC02差异待合同核对；不文案冒称实现/移M2/减Gate/并写UI或Penpot。RO资源准备disabled且缺Root确认的单AppSecret/Base/单群身份唯一路径，未读旧.env/旧密码或启动auth/WS。human_feishu/human_web/正式平台、M1/Phase4未验收，日期/原300h/P4 50h估计/人工H-L未报告与生产/Woo/Phase5/付费/扩权边界保持。
