# Phase4 A08 有限业务与原键恢复候选

2026-10-12 Asia/Shanghai；原A/WTfd38/codex/phase4-feishu，PR43同任务链。main仍9d97，阶段与Issues39–42未结案。本批主体原始base为9a395634dd05941645370cdd460dddca98793e17，Root已核其四CI38151837270全SUCCESS、383PG及三Web批13hash无差异，权威[Source9a回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6110882129)。该旧成功CI不验收本次WIP，也不抵Root后发现的scope P1。

## 业务范围与源码取舍

[有限合同](contracts/p4-a08-recovery.md)规定known70原14上限不变、group20有限73、approved_outbox有限11。Group20继续原twenty固定20×100/总2000/输入最后b02-19未知，原P2/T2/T4同factory，完整联合确认、拒绝、重复/冲突沿原T3，单Worker/Graph/PG权威不改。B三Base模块、其专属测试/PHASE4_BASE与C frontend/npm/Web保持原字节。

Root原Core对9a新发现P1：trusted_scope只校验task白名单，队列recover/claim与approval.reconcile却全库运行。修复将白名单T1及其真实同org/shop source_task_id传入原JobQueue，recover/claim只选择这些注册任务，reconcile仅原T1；普通默认None仍全库原行为。恢复only窗口跳过job recover/claim及approval协调器，禁enroll新IM/Base意图，仅manifest已有Base delivery。

approved_outbox严格绑定旧T1/receipt/task/version、原plan/hash/version/已消费决定/completed execution、同item原unknown v1和可选已有pending v2、原client_token/outbox/投影及请求hash、旧SDK窗口、旧Gateway+Worker完整终止、当前角色、全新active Gateway与新截止；新Gateway max_workflows=0。旧窗口已经真实终止后可早停交接，无须等旧expiry；不能因claim可读取或容器退出跳过完整原child同namespace wait/reap及不可变终止回执。旧failed/queued、Fake投影、错误原锚/参数/当前权限、缺proof均SDK前拒绝。原unknown只reconcile，B strict15/完整唯一读回后才建立v1锚，随后原v2 update；不更新内部业务或新建执行/键。

原Gateway child在读AppSecret前补实际PID/host/namespace started；原parent手动SIGTERM也完成terminate/wait/reap/OS复核及原audit终止回执，输出安全摘要。只证明本次真实进程生命周期，不追溯补造第二live旧summaries[]/child_reaped not_verified。

## 原实际运营回执与停止边界

[配置CAS](https://github.com/aning0922/commerceops-agent/issues/40#issuecomment-6111090153)只改当前shop元数据为demo/v2及一条local_preparation audit；历史任务/角色/SDK4窗口14调用等保持。随后[第二live失败](https://github.com/aning0922/commerceops-agent/issues/40#issuecomment-6111191331)：真人新T1 queued，Worker binding 30s超时/未启动，plan/approval/execution/item/outbox/IM/Base/card0，业务SDK0/global14不增；16:31:39.395845Z早于16:32:04Z停止、资源0、保卷。Gateway parent无原安全摘要，child_reaped not_verified保持。

A在Root通知真人之前先启了30s binder，是操作顺序错误；原TimeoutExpired与原具体断言未知保留。后续binder必须在Root收到真人“已发”后开始一次，原绝对截止与30s上限/停止余量不延长，失败禁自动重启/续窗/新键。当前不启动SDK、不请求真人、不重复CAS/G1G2/P2/P3平台Gate。

## 作者实际证据（冻结前）

| 批 | 真实结果 | 停止/保留 |
| --- | --- | --- |
| 初group PG | 11cases/9pass/2fail；同pytest活进程关闭再start触发真实OS终止拒绝，测试改为单真实child贯穿准备/决定/执行 | 16:51:04.131510Z stop/down0/资源0/保卷 |
| 第二group与首scope/recovery | 13cases/11group pass/2fail；scope读错public.checkpoints、unknown child原分类未捕获 | 17:04:02.706917Z资源0、低权false/temp0、source250零变化 |
| unknown定向诊断 | 1case/1fail，安全trace定位dispatch!=unknown断言；实际返回类别没记录，根因仍unknown；测试8s准备小于正式15s停止余量，后续用独立新180s窗，不续旧窗 | 17:07:44.985036Z资源0/保卷 |
| scope+outbox成功 | 2cases/2pass，JUnit testcaseΣ76.910s；same/different shop非T1 ready/retry/confirmed-running、waiting/自然过期与四checkpoint表完整行未变；原v1锚+原v2，无新执行/键 | 17:11:51.448930Z资源0、低权false/temp0、source250零变化 |
| 扩展矩阵初跑 | 18cases/3pass/15fail，JUnit testcaseΣ247.040s；统一测试child阶段失败，未到拒绝/kill断言 | 17:28:20.975462Z资源0、低权false/temp0、source251零变化 |
| 共享child定位 | 2cases/2fail，默认Worker ctor TypeError/scoped import ImportError，安全文件/函数/行号已捕获 | 17:36:27.928051Z资源0、低权false/temp0 |
| child源码路径修复定向 | 2cases/1outbox pass/1waiting hook fail，JUnit testcaseΣ39.994s；原waiting CP重入不产生新after_ready hook，改核真实PG ready/state及原冻结字段 | 17:42:10.379143Z资源0、低权false/temp0 |
| 五提交边界定向 | 5cases/5pass，JUnit testcaseΣ85.997s；原T2前后/waiting/T4前后，真实kill/-9/旧终止阻断/显式同namespace确认后恢复，无新plan/nonce/TTL或重复执行 | 17:46:38.031341Z资源0、低权false/temp0、source251零变化 |
| 最终受影响矩阵 | 40cases/31pass/9fail，其中30PG全部pass/JUnit testcaseΣ366.360s，另1pure pass；9pure仅缺容器docs配置例，未到断言，不冒整批exit0 | 17:56:59.902135Z资源0、低权false/temp0、source251零变化；33实际child回执、四imports全部match |
| 文档挂载与扫描等价增量复验 | 13cases全部pass：10pure+joint/reject两PG+原v1/v2一PG，JUnit testcaseΣ29.528s/3PG28.501s，补docs只读挂载；公开字段误报改等价写法不增豁免 | 17:59:35.746090Z资源0、低权false/temp0、source251零变化；3实际imports全部match |
| offline | 新10pure及旧相关62=72pass/6.64s；完整1464pass/410integration deselected/99.58s | 原SDK/Fork DeprecationWarning保留，SDK/秘密读取0 |

共享child原因已源码核实：P3Process重写PYTHONPATH只留checkout根，在旧依赖镜像加载旧wheel，绕开bound backend/src。仅修测试child source路径，新增四实际导入module hash安全回执和固定异常类别/文件/函数/行号；不保存异常message/参数/连接URL/密码/Token/config/raw SDK。普通主代码参数不弱化，旧失败与当前测试命令/JUnit/source/停止回执在ignored700/600原包保留。

计时口径：safe.JSON中的XML_seconds是JUnit testcase.time之和；cefa全40caseΣ=367.377s，30PGcaseΣ=366.360s，testsuite.time=374.548s；931c全13caseΣ=29.528s、3PGcaseΣ=28.501s、testsuite.time=35.645s。testsuite包含setup/overhead，不与caseΣ混称。无计时重跑。

新27PG及必要旧3PG已完整执行通过，30PG=group11+outbox10+scope1+workflow5+原controlled Worker2/Gateway1；10pure在正确docs挂载复验全部pass。公开字段扫描误报仍保原报告，随后等价SQL换行、conditional局部变量及if/else消除匹配，不改规则/豁免或业务断言。完整检查首停于两字段误报，再停于一个conditional误报，再停于DeliveryGate未格式化；这些都未冒称整个scripts.check通过，后续完整命令以最终实际输出为准。

最后仅if/else局部变量与DeliveryGate formatter等价调整，完整scripts.check已actual exit0：1464offline/410deselected/95.17s、Ruff374/mypy274/Markdown96、uv锁99依赖一致、Node24.21工具链/tsc/42npm audit0、Python95锁依赖audit0，目录/index/完整可达Git历史三scope扫描0。旧PG源快照与该增量分层，不把30PG冻结前运行描述成未来SHA CI。原B/C产品、Python/npm锁、迁移/rootCI无改；提交后精确head/tree在Issue40外部回执，不在本文件自指未来SHA。最终Root独审/精确CI未填。

## workflow恢复与剩余Gate

新同active Gateway测试复用原T1与原scoped Worker，覆盖T2提交前后、过早card拒绝、待审批kill、T4提交前后kill及旧OS未确认拒绝；只检查真实PG/进程/原Graph，不称SDK或真人平台恢复。原plan/hash/nonce/expiry不刷新，最终一个永久execution/20item/20原投影意图。源码、实际child imports与必要测试精确绑定后才交Root。

跨Gateway的workflow/审批未完成恢复入口及正式SDK运营合同仍pending，completed outbox-only不替该层。尤其同SDK window auth/bot=1若已消耗，不能盲重启Factory或新键刷新预算；必须Root核明确原任务/CP/批准/原期限/旧终止与新窗口有限预算，之后才有真实断线/重启/过早批准/kill平台证据。预计该层还需2–4 Agent有效小时及独审/精确CI/受控资源窗口，仍原8–12h整批估计与50h/300h内，不降低Gate、不称A08整体/M1/Phase4完成。

用户已新增授权N01+U02/U03/U06/U08合批，依赖A08源码稳定、独审及精确CI后Root释放A09：A仅Web session/current operator/shop零业务副作用preflight closed DTO，C独占M02输入/明确确认/原fresh显式submit与四UX项；13–19 Agenth为原预算内规划，不能混入当前A08WIP、不能新模型或通用draft框架、Feishu F02/B47续答仍待分记。本批不提前实现该接口。

本工作段16:37:16Z开始/硬stop20:37:16Z，最多4h/Token80k/同源三针对修复，Token遥测unknown、wall与步骤约束继续，人工H/L not_reported；机器命令/JUnit另记，不转人工承诺，也不因后续A09授权续期。D1=10-10/D30=11-08/300h/P4 D13–17/50h/18页设计与旧失败/972未知/wrapper1pytest0/SWC0test/Issue23风险/资产凭据卷不重置。无生产/Woo/Phase5/扩权/新成员/paid；最终Root独审/CI/main/合后CI/Issues闭环另据实时回执。
