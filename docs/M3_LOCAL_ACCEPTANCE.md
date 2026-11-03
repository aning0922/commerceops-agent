# M3 本地实施与验证交付验收

2026-11-03，台北。本地状态 `LOCAL_IMPLEMENTATION_ACCEPTED / EXTERNAL_ACCEPTANCE_DEFERRED_BY_USER`。用户授权先完成本地实现；真实 SOP/商品资料未准备、真实模型/embedding 预算待定、飞书不实际发送。该授权不复活旧 M1/M2 一次性窗口。外部验收保持 NOT_RUN，不以本文件标记完整 M3 正式验收、合 main 或发布。

## 源码与证据分层

- 功能源码：`3a184e9a74c1db524d58228ed90b7ea20388a722`。真实本地 M3 Web、原离线 Web、原真实 API Web 各自按该来源记账。
- 修正后完整工程/PG 候选：`532eefd83e4b1d0e6ddc6e44e89c0d806021eb1e`。相对功能源码只改扫描精确公开例外/契约、K2 owner TRUNCATE 负例及其说明；backend/frontend/compose/PG pipeline/浏览器 harness 均字节不变。
- 最终文档提交另记；不把上述测试的 source SHA 改写为文档 HEAD。

## 已完成的本地功能

日报提供明确来源和确定性指标、时区/支付退款口径、冻结报告、持久调度去重与补最近一期、Fake receiver、模板追问及脱敏证据分页。询单在当前身份与店铺权限内使用受限只读工具、调用/时间/行数预算和持久回执；本地实际模型为 `offline_stub`。知识检索使用真实本地 PG17.11/pgvector0.8.7 和明确合成向量/商品/SOP，验证来源/版本/时效/身份、可定位引用与候选；指定审核人批准才保存一次内部草稿，拒绝不保存，不发布。

主 API 和原单 Worker 装配已接线，各开关默认关闭，复用原 session/Origin/CSRF/授权。copy 是有限同步 PG/模板路径，不虚增第二 Worker 或发布 outbox。客户端 UNKNOWN 保留原键，仅固定 GET 恢复，不自动重复 POST。

## 已核收的本地门禁

| 门禁 | 精确来源 | 当前已知结果 |
|---|---|---|
| 工程完整 scripts.check | 532eefd | native0；3684offlinepass/719排除/4warning539.16s；type496/format640/MD140/strict10files46/0skip0retry；Python95包0knownvuln/npm0；scan dir/index0、git20oldapproved0blocking，nativegit1保留 |
| PG K2修复后独立实跑30节点 | 532eefd | 30/30passed51.49s/native0，08:00:36.775587Zcleanup0；独立容器/网络/卷0 |
| 完整 PG existing542 + phase3 177 | 532eefd | 本机串行542+177=719全实际通过，交集0，严格来源/工具/锁/完整集合/G1G2/清理配对native0；本机40/42容量例外，Hosted35/33未验 |
| M3 主 API+单Worker+浏览器 | 3a184e9 | 3passed/47.1s/browser native0，7业务POST各只转发1次，7次实际本地HTTP回复被harness丢弃后原键GET恢复 |
| 原离线 Web六配置 | 3a184e9 | 145/145、skip0/retry0，各CLI0 |
| 原真实 API Web read/write/items | 3a184e9 | 7/10/7 passed、skip0/notrun0，父入口均0/supervisor0；14产物hash已独核，3新项目0container0network/各保留1新卷 |
| 原N01 | 3a184e9 | 6/6passed49.366s/helper0/PW0/supervisor0；五负例业务不变，一显式pair/GETunknown/dedup/409；cleanup0/独立0container0network1volpreserved；browser个体exitNOT_CAPTURED |
| 独立审查 | 各精确提交 | M3真实Web、离线145、原live24、N01六均已ACCEPT；扫描/K2fixture静态ACCEPT；fullcheck/K2actual已Astra独核ACCEPT；完整719及配对已独核，文档22b924f已ACCEPT/无P1P2；完整M3外部验收延后 |

M3 E2E project `m3web-3da9458c2dd4`，实际image `sha256:42acf2ebb32b9128c217eed624b3f988f242f2450b9642bbb537feefa51ff070`。实际分页完整且至少51条，不声称未保存的精确总数。两独立shop同新organization下当前账号各自有scope/role；指定审核批准/拒绝、跨身份404、草稿与390px无溢出通过。cleanup 07:25:20.806571Z exit0，独立容器/网络0、新卷1保留；进程退出为Worker0/API-15/Web143，后两者为实际owned TERM，不能改写成全0。

离线Web实际07:33:35.090948–07:35:41.392787Z，90+13+8+22+9+3=145；29保存产物含23张获准自创Mock图，hash核对、tracked恢复clean，固定端口/已采样PID/CLI进程组无残留。Next个体退出码未捕获，UNKNOWN保留。

## 失败与限制

3a18 scripts.check最初在测试参数声明敏感误报处exit1，后续阶段NOT_RUN；004b首修遗漏固定source计数导致独立6pass1fail，794仅精确同步25/28后关闭。3a18 PG existing实际542selected、387actual=386pass1fail、155NOT_RUN；K2 owner循环test285 SQLSTATE0A000，完整原错误全文未捕获。564修正让CASCADE纳入FK依赖并严格要求不可变23514/固定消息，新PG完整30已通过，关闭该测试失败；不补造旧失败原错误全文。旧52525existing245pass1fail/295NOT_RUN、旧52525phase3177pass按原源保留。后续3a18 phase3实际169/177 call通过、8 NOT_RUN；terminal_recovery part2容器/CLI原生退出139、timed_out=false、外层1，未捕获业务断言，根因UNKNOWN；cleanup0/stopping_confirmed，独立资源0。旧52525的177pass不抵销此失败。全部早期SQL/浏览器/准备失败按原源保留，不拼接成全量通过。

镜像固定tag不代表imageID永远相同；每个回执按实际imageID/来源/六输入/native架构核对。最终532候选实际新镜像为sha256:0678fc5fae0082e93727392eea662f3a02dc40e2c7a2dacaaac1a496d3042ec3，不能用旧42acf回执改写source。新PG仅使用登记的owned RFC1918 /24，不清旧Docker网络。M2备份工具仍严格支持0018并拒绝0023，未实现M3备份扩展。amd64/Hosted、真实模型/embedding/资料质量、真实飞书接收/外发、人工业务质量及生产均NOT_RUN；真实provider接入需后续实施/预算与独立评测，不能视为翻开开关即完成。

**稳定性限制：历史两次原生退出139仍是已观察到、尚未解释的问题。** 本轮原四节点定向验证及完整719串行回归均通过；这不证明并行资源竞争或CPython缺陷是根因，也不将该问题标为fixed。后续如复现，应先取native栈再决定修复，不无限重跑求绿。

## 本地启动准备边界

三个demo入口用途不同：`python -m scripts.m3_daily_demo --directory <新目录>`只接受空的新m3_daily_demo_*库；`COMMERCEOPS_MODE=m3-inquiry-demo python -m scripts.m3_inquiry_demo --directory <新目录> --web-port <端口>`只接受另一个空的新m3_inquiry_demo_*库，不能附加到已seed日报库。copy exporter是附加登记入口，`python -m scripts.m3_copy_demo --database <库名> --organization <UUID> --shop <UUID> --directory <新目录>`仅接受守卫范围内fresh synthetic baseline shop及明确owner授权。

共同前提是对应新库完成迁移/checkpointer/基础grant，使用通过实际表owner校验的连接及不存在的新绝对路径目录，并配置所需runtime凭据文件；copy另需显式grant-knowledge-copy-runtime。copy先提交owner事务再导出三文件，未实现三文件原子发布；导出失败可能留下已提交数据或部分文件，保留现场核实，不自动重试。联合双店铺装配由owner登记第二baseline shop、原账号的shop scope/role和对应InquiryDeployment；当前没有公开一键联合seedCLI。私有.audit assembler仅用于本次受控验证，不作为正式配置或默认开箱环境交付。API/唯一Worker/UI消费配置与开关详见M3_LOCAL_DELIVERY，不把UI展示开关当权限。

## 本地证据索引（原件保留在各独立工作树 .audit）

- control：`m3-post-fixture-fullcheck.log`、`functional-equivalence.safe.json`、`prepare-532-go.json`、`m3-pgvector-image.safe.json`。
- final-sql-probe：`issue23/round-1.json`，实际完整K2 30callpass；前收集79不计入实际执行。
- final-existing-serial / final-phase3-serial：各`issue23-ci/round-1.json`和`ci-evidence-*.json`；最终719严格配对已通过；旧并行两线失败另按原件保留。
- validation-complete：`m3web-3da9458c2dd4/root-ledger.json`、`m3-operations-ledger.jsonl`。
- offline-web：`final-3a18/run.json`、`summary.md`、六份原JSON及各产物hash清单。
- final-web-live：`original-web-delivery.safe.json`，SHA256 `233ea8e4b402c5d47921e20f1dbafa40ef8020e2b05efc71c35838a5dac4e987`，及各read/write/items原报告。
- final-n01：`n01-evidence-n01-owned-20261103-183db6b4c1/`的acceptance、不变量、manifest、独立清理与SHA清单。

这些是本机原件索引，不声称已提交原件、上传、公网发布或其他机器可直接访问；tracked记录只保存非秘密结论及来源。旧失败原件继续保留。

模型协调实际使用GPT-6.1 Sol负责实现/运行与小修复、GPT-6.1 Terra负责界面与浏览器、GPT-6 Astra负责关键独审，按任务调整high/xhigh/medium，侧边栏会话随职责改名。本次业务运行未调用真实商业provider模型/embedding API；询单实际使用offline_stub，知识检索使用合成向量。原D1/D30、300h、M1/M2历史预算、人工H/L UNKNOWN、原once/失败/UNKNOWN/NOT_CAPTURED及18页历史冻结不重置；M3不把旧计划净余当新可用额度。

历史532并行完整PG两线（本轮最终串行之前）：existing535/542callpass、7NOT_RUN，08:32:53.190665Zcleanup0，末verified-history part2因总期限耗尽command137/timed_outtrue；phase3169/177callpass、8NOT_RUN，08:27:14.351536Zcleanup0，terminal part2首setup45秒诊断后139再次发生；根因UNKNOWN。均原生外层1，Root独立资源0，无配对。CPython158200线索仅其他版本/架构官方报告；当前实际pg-test解释器3.12.13/aarch64、无PG官方最小复现程序预登记3次均native0/OOMfalse/cleanup0，只能记本轮未复现。该时点未核收完整门禁，失败不被后续成功记录改写。

本次最终串行完整验证使用已登记的本机容量例外：同532源码一次完整existing542、实际退出清理后再一次phase3177，每线40分钟诊断/42分钟外层，保留每命令300秒/45秒faulthandler/内部reserve75+外层额外120秒/完整节点/G1G2/严格配对。40分钟不是测得最低容量或通过保证；仓库Hosted35/33不改且未验证。此阶段不并行本目标其他重载，其他用户host负载UNKNOWN。本轮预先规定若再现139即停止整线重跑并转native栈取证；本轮完整运行未再现，不能推定已根治。定向原4实际4passed100.65s/45s完整栈/四时点无blocker只签局部，不抵全量。

## 完整 PG 最终实际回执

- existing：project `p123-b06a19cea724`，selected=actual=passed=542，cleanup0/stopping_confirmed，结束 `2026-11-03T09:29:47.495685+00:00`；Root独立容器/网络/本批ephemeral卷均0。
- phase3：project `p123-80f2cdffedee`，selected=actual=passed=177，cleanup0/stopping_confirmed，结束 `2026-11-03T09:59:19.433781+00:00`；Root独立容器/网络/本批ephemeral卷均0。

phase3终止恢复part2原四节点本轮全部通过，45秒转储完整44条安全栈。为保留未过滤stderr，该组另有只读Docker日志follower，唯一一次采集、collector原生0，不控制helper或修改pytest/源/计时；原始控制台文件仅本机0600保存。它是本轮观察条件，不抵Gate，也不作为根因修复。两线实际应用镜像分别为existing `sha256:047014fa9a0d61b6b3998574f2c0abd307f966d5d4141604135b9e5a78a2c07a`、phase3 `sha256:f9aad8588d356017e6de4d48131b7d2f8cecd07739f30122bb9ab431e11aca7b`，均arm64；PG使用同一绑定的0678镜像。

严格配对在532冻结HEAD执行，source/tree、工具与锁文件指纹、完整719节点集合一致；分区无交集、无缺项，原G1三项/G2六场景及原清理要求均保留并通过。两份ci-evidence的hash见本机final-pg-pair.safe.json；对应round原报告保留于上述各独立工作树索引；不把旧source局部结果拼成此并集。

最终文档合批仅更新事实导航与交付说明，受测功能/工程SHA如上，不预填文档未来SHA，不宣称文档HEAD重新执行全部PG或浏览器。未push、合main、触发Hosted或部署；原README工作树保持原样。


## 最终本地核收回执

Root于`2026-11-03T10:05:02.260708+00:00`登记已实际收到的独立模型审查：`ACCEPT_M3_LOCAL_DELIVERY_DOCS_22b924f`，绑定普通文档提交`22b924f0549c2740f1330ce755454934d3d92954`，无剩余P1/P2。其parent与完整工程/719 PG受测源码为532eefd；浏览器受测来源仍为3a184e9。独审同时接受本次授权本地范围可收口，完整M3外部验收未接受。本次增量只登记实际回执、机械更新本地状态及修正哈希索引，不改代码/测试/配置，不重写旧失败，不将139标为fixed，不预写本次提交未来SHA。
