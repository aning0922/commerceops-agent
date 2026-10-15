# P4 真人 T6 与原记录 v2 接线合同 v1

本批由用户批准立即开始，Root T0 为 2026-10-15 13:34:15Z。
今晚 14:45Z 交接、15:00Z 停止；未完成明日 01:00–09:00Z 同批接续。
总 5.5 Agent 有效h，其中 A≤3.5/C≤0.5/独审≤1/Root≤0.5；不重置原项目日期或预算。
基线049的真实RO分项已核实，manual SPENT、Create1/automatic attempts3不变。
本合同是新业务候选，源码存在不代表完整合成、独审、精确CI或真实验收通过。

## 所有权与阶段

A独占 recovery DTO、Worker window、outbox准入、BaseDeliveryStore、Worker装配、
共享验收入口/父协调及相关tests/docs。C独占原四consumer/采集文件，A只调用其现有函数。
Root冻结全部源码/私有parent/镜像后安排原独审和新精确五job CI，随后才释放真实窗口。
今晚仅offline及全新owned合成PG，外HTTP可Fake；原库/身份历史/AppSecret/平台零访问。

真人阶段PG/API/Web，Worker/SDK/WS/Graph为0。只允许真人原生登录同身份、同open/v1项，
填写原因、准备原请求、明确close一次。协调器不生成request key、不代替真人业务提交；
为actual GET使用独立技术认证（CSRF/login/session/GET/logout）保持既有认证安全，无刷新重登。
使用现有api/capture/signal/process_probe/deadline及独立资源清理，不调用LAB consume_stage(t6)。
原HTTP字节为not_captured，不新增observer/DevTools/HAR，不据此报告网络恰好一次POST。
验收以新鲜app角色RR只读前后快照、native PG key/semantic_hash/result、当前身份/原因/审计、
唯一原生v2 outbox、同key operation=resolve GET及真人明确报告关联；业务closed与sync pending分列。
源task/plan/approval/execution/jobs及三个CP精确保持。异常只读核回执，不另造key或重投。

## terminal-update 独立准入

新增严格DTO/profile，不修改旧ApprovedOutboxRecovery/sender/v1/C0/unknown谓词。
绑定：原已消费explicit RO的原生claim/SDK hash、Gateway/Worker真实终止与OS absent、
同org/shop/task/plan/approval/execution/item/target、v1完整唯一verified/observed1及稳定record锚；
再绑定原生T6 request key、semantic hash、resolution/actor/identity/auth_version和唯一v2 outbox。
原生T6事务生成v2 outbox/provider key；工具不得直接造delivery/ledger/audit。
native BaseDeliveryStore只登记此一个v2 outbox，须先有严格持久授权，再核原快照/hash/版本顺序/
当前operator、原approver及resolver权限。原v1和旧once/attempts/锚不更新。

新窗口在实际claim之前复核来源、当前身份及原全部批准关系。claim按v2 outbox确定性唯一键，
新进程/并发窗口不能再次授权；maintenance和enrollment重核同一claim及权限。
只处理该v2，dispatch_jobs=false，无approval reconcile、IM或Graph；第一次dispatch结果即停止。
成功必须原record全15字段、唯一、version2完整读回，HTTP200不足。unknown/失败HOLD，
不自动再次update、不create、不换key；进一步真实只读恢复须另行明确范围。

caps精确为auth1/bot1/table-list2/field-list2/update1/record-list4，总≤11，
create/IM/provider/WS/jobs/Graph0。SDK≤300s，PG≤600s，reserve≥180s，arm余量≥480s，
Root新绝对UTC加各host自身monotonic，旧RO窗口及manual once不可复用。

## 必要证据

最终同一源码及真实最外命令在新合成0015/55与0016/56全链执行，真实SQL/app权限/DTO/
claim/enrollment/Factory/ledger/持久读回/OS stop-reap/独立cleanup；仅HTTP Fake。
包括权限撤销/错source/hash/anchor/request/version/window、并发/冷重放、HTTP/ACK/timeout/
partial readback及清理失败，实际外层退出与阶段分类一致。旧成功链不签新代码。
冻结独审与精确新CI后才通知真人，不push/触CI/main或试跑原库。

当前状态：合同冻结开始实施；上述新Gate均NOT_RUN，原RO PASS单独保留。


## 今晚续接状态（2026-10-15 22:45，北京）

当前为未验收WIP，不是完整准备PASS。独立terminal DTO/profile、native准入/enrollment/
单次Base dispatch、human-only api/capture/认证GET/stop/probe及terminal_v2有界父分支已实现。
C四consumer字节未改，迁移/grant/CI/锁/前端不改。源码检查、实际结果以本批私有回执为准。

新owned双schema开发验证保留全部失败：原授权state.window读取错位；实际低权对稳定锚
FOR SHARE的42501（只锁有UPDATE权的delivery，不加grant）；拒绝子例复用Gateway和
撤权夹具auth_version约束；Fake可变外端被误当不可变源码ref。新terminal LAB改由不可变
control固定DB/org/window/状态路径，外部可变记录不进入请求哈希，旧RO路径不改变。
双schema末轮已在原22:53:16截止内完成：0015/0016共2pass/337.05s、tests CLI0；
22:46:34完成down0，控制器exit0。随后独立核三新项目全部容器（含已停）/网络0、三卷保留、
开发控制进程0。仅签本轮native开发节点，不签同最终最外命令的完整human准备链。

human完整预演仍NOT_RUN，下一步须：自动从已核RO与原生T6结果派生disabled terminal模板；
形成同一600s绝对截止、不续期的人机与SDK合批编排及完整private bootstrap来源；
同最终源码/parent/image完整双schema全链及故障/未知/超时/独立清理，再冻结原独审与新精确CI。
当前独立human_t6与terminal_v2接口尚不能当作完整合批已就绪；不得操作者手工拼成功JSON或
以旧成功链替代。raw HTTP not_captured、原manual SPENT/Create1/attempts3继续保持。

末次完整检查日志已走完：当前/index/完整可达历史敏感扫描各0，Markdown106/错误0、
format438/type328通过、2069offline通过/506PG排除/121.90s，Node/typecheck与两依赖审计0。
原检查会话的进程退出码未恢复，记录为CLI exit unknown，不把日志结束补写为实际CLI0。
前两次扫描在5个公开dummy字面量命中时停止（未上传、未加豁免）；后两次分别因PATH缺mypy
及撤权夹具SQL单行超长停止。修正后末日志完整结束，所有旧日志保留，不删失败。

源码维持未提交WIP。049874ea3b5a2f814cce438f4602cc35cfd8b31d/tree8855是原已提交基线；
末轮测试有独立八文件SHA256清单，与交接时源码逐文件比较，差异不能借该轮通过签认。
原C四文件/迁移/grant/CI/锁/前端不改；今晚只整理受保护交接，不追加诊断或新PG。

Root另将CI容量列为明早前置：本轮两个新节点合计pytest337.05s，已超过现有每命令300s。
当前pg_diagnostic仍将整个test_p4_acceptance_pg模块独占同一命令，新增后为7节点，
不能直接释放此已知超时安排。明早由A在现有分区机制内做最小分批/必要独立测试模块，
完整506集合、两分区、G1/G2、35/33总限额、300命令/75 reserve/原清理保护全部保持。
本轮未开--durations或JUnit，每个节点及fixture独立秒数未采集，不能将337.05均分当实测。
保存原命令、完整日志及当前分组位置；后续真实计时须保留慢测试，不隐藏或降低断言。
此项是同批测试接线前置，旧40min异步授权不重开今晚CI窗口。

## 统一整改与两阶段模型（2026-10-16凌晨，北京）

用户取消原23:00硬停；Root集中核准总cap8 Agent有效h，A5.5/C0.5/Review1/Root1，
此前用量及126秒诊断不清零，从原P4/300h调配，不另增总预算。
两原库阶段为原则授权，具体执行仍HOLD，待最终同源隔离全链、独审、精确新CI及Root具体UTC。

同一run_once事先绑定两个不重叠绝对窗口：第一段PG≤600、真人等待≤300、清理reserve180；
第二段PG≤600、SDK≤300、清理reserve180；两段总跨度≤1200，不由第一段完成时间滚动续期。
images/source/config/端口与资源计划在开库前准备。第一段实际剩余须够完整等待加60秒证据采集，
否则不发human-ready；第二段必须剩余至少480秒才arm，否则HOLD。T6若已提交不重投。
第一段必须actual GET/PG一致且完整stop/reap/cleanup，第二段才重新开同卷、复核当前权限/
原生RO与v1锚/唯一v2并自动派生disabled模板；模板来自持久claim/lifecycle/item/outbox，
不由操作者拼recovery或成功JSON。模板及arm不能消费旧RO一次额度。

全批Feishu SDK方法上限不变：auth1/bot1/table2/field2/update1/record-list4≤11，
create/IM/provider0。两阶段只改变资源开放安排，不新增业务规则/迁移/grant/权限或重跑原RO。
真实与同源LAB统一复用049的同host/PID namespace子进程及受控loopback PG模式；
PG仅127.0.0.1自有随机/登记端口，API/Web也仅loopback，无公网入口。不保留新runner部署分支，
不改写历史namespace或终止回执；源码存在不签完整Gate。
