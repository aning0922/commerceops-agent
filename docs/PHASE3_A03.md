# Phase3 A03：重验证、永久执行与单项跟进候选

状态：作者实施与完整实际验证已收口，A03冻结SHA按PR37新head核；独立审核、精确CI及Root A03 Gate待实际回执。沿用WT62c8、`codex/phase3-approval`和[Draft PR37](https://github.com/aning0922/commerceops-agent/pull/37)。A唯一负责后端、迁移、Worker/Graph、共享DTO/CI与阶段证据。B在独立WT实施；双方clean freeze、各自必要Gate及Root放行前不合B。本文件的作者自检不替代独审、GitHub CI或总控验收。

## 前置Gate与范围

A02已由Root核定通过：source `24856555fe23975fb19cd67ddcc033f6cac3905c` / tree `5306496d3681765f98707b69a850c28ec0151c4d`；新独立24实际PG/155.72s、migration1/pure19/actual wire21，Core无阻断。原独立12/8未核实记录保持not_verified。[精确CI38064613062](https://github.com/aning0922/commerceops-agent/actions/runs/38064613062) SUCCESS，actual merge `196d824ca2b3238d5491c494a3b813062587fcb1`、parents main59+248、tree同源；978offline/236旧PG/59P3/3G1/6G2/cleanup0。Root放行见[Issue34](https://github.com/aning0922/commerceops-agent/issues/34#issuecomment-6099399935)、[PR37](https://github.com/aning0922/commerceops-agent/pull/37#issuecomment-6099400132)、[Issue33](https://github.com/aning0922/commerceops-agent/issues/33#issuecomment-6099400410)。[A02](PHASE3_A02.md)的未放行与未实现是历史快照。

本批mock/session/simulated_web，实际PG与受控进程故障不代表人工真实审批。新增实际provider0、飞书/Card/Base/Woo业务网络写0，sender永久false；P1/P2/A01/A02/B资源、旧secret和.env未读或借用。Phase4、生产和扩权不在范围。正式main实时核为 `59b350cb719a9d2fed3f68b1ee598fa0a9b97875`，Issue33/34/35与Phase3未结案。

## 确定性T4与证据文法

生产Graph删除A02临时`interrupt_before`，保持同workflow/thread及五节点名；唯一业务interrupt在wait_approval。已批准的持久next=revalidate只能`ainvoke(None)`接续；PG delivery consumed表示送达，T4 consumed_at须永久execution证据。API和Graph共用确定性应用/存储权威，不把checkpoint当业务事务，也没有公开execute端点或客户端数量、角色、approved、来源路径旁路。

最终重验在task→plan→approval→principal→排序pool锁序下核当前identity/auth_version/逐角色shop scope/frozen eligible、nonce及专用key版本、不可变expiry、plan version/hash、来源与完整确认集合。释放业务锁后有界重新采集Mock typed事实及本店数据库open项，再复锁、复查权威、DB时钟和freshness；模型不参与金额/需求/数量/质量/幂等计算。

`0007_p3_execution`保留原P2 completed/task/report/snapshot/checkpoint和P3最初source四元组。新不可变p3_observations保存本次真实采集时间、typed input/report、canonical/hash版本、原P2 lineage、generation plan/version/config与material hash。plan内部显式`p2_original|p3_observation`及互斥FK组；v1绑定原P2，后续版本绑定本P3 task/org/shop的独立新observation。不是裸UUID猜测/UNION，不把新report ID伪装成P2实体，不改外部DTO文法。

时间/采集checksum/行顺序变化不构成material；数量、需求原始事实、状态/风险、在途null→known、source version、质量和open pools等实质变化生成新observation/report/snapshot、plan v+1、approval/nonce、当前eligible和完整新确认。旧approved意见、原请求回执、原plan内容和P2证据不改；旧plan仅superseded。hard quality/超容量/无可执行建议failclosed，保留阻断证明与旧approved未消费，不制造可执行新批准。

L/R/S只有活动计划冻结参数=原P3 source=已核原P2报告/来源或显式T1 new_cycle参数这一条权威链。没有同task热改L/R/S、live override表或部署默认值覆盖。配置版本字符串单独变化不构成实质变化；未知来源/rule/config伪造拒绝或attention，不猜测。合同“参数改变需要新确认”是条件安全不变量；不存在的同task hot edit明确not_implemented，实际证据来自合法独立new_cycle变化与参数/来源伪造拒绝。

版本化决定、旧approved→新plan强transition、卡片intent/audit和活动指针同Tx提交。transition有scope/plan/version/hash/decision/cause job/FK及规范digest；应用checkpoint一次。PG新版已提交、CP仍旧next=revalidate的间隙只凭精确强证明复用现有新版、None接续。维护扫描不把旧CP标成新版ready；新版实际wait CP后才ready。早到新版T3持久waiting_checkpoint，旧决定/continuation只收敛送达，不能向新版发Command或批准它。

## 永久执行与T6

一个T4 PG事务写永久`restock:shop:plan:version` operation key/hash、唯一execution、整计划全部内部项、每项outbox intent、批准consumed_at、plan executed、task completed和审计。延期约束在commit核真实clock/期限/freshness、整计划数量/身份/消费/终态/audit/outbox全套证明；事务中途失败或kill全套回滚。commit后CP前kill只查原execution/原item IDs，即使item已complete/close也不能重建。`(shop,pool) WHERE open`唯一与排序锁阻止同池新open；一项冲突整计划failclosed，不部分执行。

T6只允许当前同店approver跟进一个open项，含必填理由、严格expected_version、actor/identity/auth_version、resolved_at、version、audit/outbox、原actor/operation/key+semantic hash持久回执同Tx；旧版本/终态新键冲突，无reopen。当前同店approver不要求属于历史eligible；其item读/resolve权限不向上扩展源task/plan/approval读取，SourceLinks隐藏不可见ID，列表/count/detail同谓词。operator/admin-only/跨店不能拼接能力。

T6 hash使用canonical-facts-v1，输入仅item_id服务器规范小写UUID、action、Python3.12 `str.strip()`后的reason及严格整数expected_version；JSON键排序/ensure_ascii=false/紧凑分隔/allow_nan=false，UTF-8 SHA256小写64。无request_key/actor/time/schema_version；不NFC/NFKC、不casefold、不改内部空白。Python strip的U+001C–001F与JS trim差别及组合重音保留，B须按冻结server规则处理，不另造权威。

## Projection与22项实际接口

outbox只存intent/投影，无sender/network。原聚合版本、dedupe、request hash/payload/provider key等不可改写/删除；DB禁止sender=true、sending/sent、伪external receipt、unknown自动回pending或controlled_stub逆回mock。私有自有Mock测试支持local controlled_stub failure/unknown/missing repair/stale reconcile，事实与审计去重，业务terminal不变。当前sync按各aggregate最新version汇总，历史失败保留，不把missing/unknown当synced。

四个execution/items/resolve接口实际注册后，runtime完整22 operations，与approved OpenAPI/包内asset一致；唯一历史DTO delta仍Receipt ack maxLength300。ReportRead依据明确当前plan discriminator，或同task合法显式report_id，校验强来源及typed hashes。原P2 cached explanation只读取已核本来源的不可变结果；新P3观测无P2解释link返回NOT_READY，不复用旧事实说明、GET不发模型调用。

## 作者实际证据与失败历史

全部PG批次用本次新私有PG、真实session、Mock和simulated_web，临时DB每测finally DROP，严格串行。下表是当前实际结果；完整收口批/冻结/独审/精确CI另列，未完成项不提前标通过。

| 场景/命令 | 实际结果 | 边界 |
|---|---|---|
| `pytest tests/test_p3_execution_rules.py` | 9passed/0.53s，后0.45s | 纯material/native严格性/确定性；不是PG权限证据 |
| snapshot/rules/partition/shutdown纯组 | 67passed/0.43s | 自然模块分组与原预算检查；不是CI运行 |
| `pytest tests/test_p3_execution_pg.py` | 5passed/22.62s | 初始T4/T6/Unicode十次回放/终态不可重开 |
| stock-change修复专项；完整revalidation组 | 1passed/5.05s；5passed/17.36s | 三实质变化新v2、仅时间保持v1、硬质量0items；原P2/checkpoint字节hash不变 |
| 初始完整execution recovery组 | 8passed/40.92s | 真SIGKILL/旧PID闸门、replacement pre/post/早T3、T4 pre/post、关闭后原exec、T6 pre/post；之后增强T4为两item，最终完整组另核 |
| `pytest tests/test_p3_projection_pg.py` | 3passed/18.69s | 实际PG/local controlled_stub，无网络；unknown-held/repair/stale/原intent immutability |
| `pytest tests/test_p3_execution_authority_pg.py` | 9passed/95.14s | 当前五类撤权、真60s批准expiry、freshness重采、version-only不覆参数、新cycle改变LRS |
| items authority初始组 | 5passed；整联批后因evidence savepoint观测失败exit1 | 不把后段失败批称整体通过；最终完整模块结果另核 |
| evidence/pool修复组 | 3passed/14.42s | deferred FK以SET CONSTRAINTS ALL IMMEDIATE显式验证，来源参数伪造与同池整批0副作用/新周期 |
| `python -m tests.p3_wire` / jsonschema4.26.0 | exit0，32实际响应/22唯一operation | positive cached explanation自有P2 offline_stub一次、两个GET不增调用、actual provider0；含277ack及T4/items/resolve/admin |
| 当前完整敏感扫描 | dir/index/git均0 | 222原规则/四个精确例外未改；正式提交前后另扫 |
| 完整作者PG模块分组、offline/check、wheel | 333PG/988offline均通过；安装wheel22通过 | 最终每模块actual collection/时间/结果见后表；新独审/CI仍待 |

失败保留：初始material stock-change两次未达replacement提交，18.47s/19.48s；第三次输出在上下文压缩时丢失，结果不宣称。源码定位transition digest含UUID对象违反现有canonical输入；转规范字符串后专项通过。恢复间隙初次因receipt无plan_version的测试断言失败（3pass/1fail/20.87s）；再运行4pass/1fail/26.61s复现产品idle reconcile把DB新版/旧CP误标attention，强transition识别修复后8pass。A02回归初跑18pass/1fail/139.88s，兼容probe在delivery前业务仍awaiting_approval而旧断言executing；只纠正该观测，不改权威。authority初跑principal撤权缺auth_version递增违反原约束，1fail/13.18s；测试更新合法撤权后9pass。

wire初次长SKU说明路径不产生offline调用，测试把全22 UI长SKU与模型说明共用同报告的假设错误；改为同自有库独立baseline P2 offline_stub正向说明、长SKU仍验证决定/wire。后admin-only正向fixture缺role-bound admin grant导致失败；补合法自有授权后32/22通过。evidence初次5pass/1fail/24.22s是deferred FK到外层事务结束前未在savepoint抛出，测试显式核commit约束后3pass。敏感扫描初次dir3/index0/git0为公开SQL列比较误报；给原SQL比较加语义等价括号后全0，没有新增豁免/降规则，也没有上传失败候选。收口公有指纹JSON首次以filename→SHA256键值映射产生3处公开metadata误报（dir3/index0/git0）；改为path/sha256明确字段数组，值与实际29文件指纹不变，仍不增加扫描例外。完整PG首轮旧236通过/141.04s，A02模块23pass/1fail/167.40s：末项DB约束测试停在delivery前仍awaiting_approval，过时executing断言失败并导致测试屏障未释放的清理超时；该约束测试改停在实际after_delivery_receipt，仍未T4且业务executing，专项1pass/3.41s。完整全组重新执行，未降低任何DB/权限/恢复条件。普通lint/typecheck迭代单列，不冒称业务三轮阻断已通过。

## 唯一自有资源、时间和剩余Gate

PG项目 `p3a3-1571d50369ef`，owner `phase3-A03-WT62c8`，UID501、loopback62437、PostgreSQL17.11固定摘要。Docker前登记2026-10-11 01:31:30.390967+08:00，绝对停止03:01:30.390967，90min不延期。目录700，fresh两PG密码/ports/ledger600且ignored；只管理本项目，保卷/私有ledger，不读取或借用旧窗口。当前仍在窗口内运行；最终停机receipt待实际false/PID0、tempDB0、其他base连接0、app高权限false、revision0007后补，不能提前标cleanup0。

D1=10-10、D30=11-08、300h、D7–D12/A32+B18+Review10/60h保持。Agent等待按实际报告，未捕获有效开发时间不估算，人工H/L not_reported。A03新freeze独审/精确CI、B04后续接线/冻结与共享frontend检查、Root整阶段核收/main合并及合后CI仍待；[分层验收矩阵](PHASE3_ACCEPTANCE.md)维护当前事实。


## 最终作者收口实际回执

完整actual collection333=236旧回归+97P3（旧59+新38），从真实collection自然派生12个串行组，union无漏重、各组实际collection重新核对；全部exit0。下表pytest时间与命令墙钟分开记录，最大命令163.82s，合计607.14s；保持每条300s、CI全局23min/job25min/cleanup75s，没有提高预算。完整安全摘要与运行/测试文件指纹见[作者证据](contracts/p3-a03-author-evidence.json)。源码/测试29个文件从本轮完整回归前固定指纹到收口无变化；SHA/tree从新freeze/Root回执核。

| 模块 | 实际passed | pytest时间 | 命令墙钟 | 结果 |
|---|---|---|---|---|
| `既有六模块` | 236 | 142.47s | 143.421s | exit0 / actual collection精确一致 |
| `tests/test_p3_approval_pg.py` | 24 | 163.31s | 163.82s | exit0 / actual collection精确一致 |
| `tests/test_p3_evidence_pg.py` | 2 | 5.97s | 6.458s | exit0 / actual collection精确一致 |
| `tests/test_p3_execution_authority_pg.py` | 9 | 93.8s | 94.282s | exit0 / actual collection精确一致 |
| `tests/test_p3_execution_pg.py` | 5 | 19.28s | 19.753s | exit0 / actual collection精确一致 |
| `tests/test_p3_execution_recovery_pg.py` | 8 | 40.21s | 40.676s | exit0 / actual collection精确一致 |
| `tests/test_p3_items_authority_pg.py` | 5 | 21.07s | 21.542s | exit0 / actual collection精确一致 |
| `tests/test_p3_migration_pg.py` | 1 | 0.77s | 1.206s | exit0 / actual collection精确一致 |
| `tests/test_p3_pg.py` | 34 | 69.57s | 70.075s | exit0 / actual collection精确一致 |
| `tests/test_p3_pool_pg.py` | 1 | 6.72s | 7.176s | exit0 / actual collection精确一致 |
| `tests/test_p3_projection_pg.py` | 3 | 18.24s | 18.703s | exit0 / actual collection精确一致 |
| `tests/test_p3_revalidation_pg.py` | 5 | 19.55s | 20.028s | exit0 / actual collection精确一致 |

最终`python -m scripts.check` exit0：988offline/84.99s、333integration deselected、2既有SDK弃用warnings，Ruff/245format/mypy177、64Markdown/0error、Node24.21.0原tooling/typecheck、95Python和Node已知漏洞0，dir/index/git0。389合同checks/21paths/22ops/67schemas；实际安装wheel核全部22approved操作/输入/响应/components/security及asset原字节。actual wire32响应/22唯一operation、positive cached P2 offline_stub一次、两个GET不增加调用、actualprovider0；新P3 report解释NOT_READY且调用0包含在完整5revalidation组。

原236回归保留6实际G2 process records（包含cross-process、receipt/CP间隙、失锁取消、noncooperative exit、checkpoint故障恢复、retired版本拒绝），不升级为P3人工/平台Gate。自有项目再执行两轮migration/setup/grant/revision幂等及G1 fixture：restart前、同volume restart后、同项目同volume force-recreate后三次PG task/inbox/job/audit/checkpoint持久化断言全部exit0。所有生命周期仍在原窗口内，不借用旧资源。

实际2026-10-11 02:25:52.739376426+08:00停止postgres，02:25:53.065748观察running=false/PID0，早于03:01:30.390967原截止；tempDB0、其他base连接0、app superuser/createdb/createrole全false、revision0007、700目录/四私有文件600，volume及ledger保留。安全字段见[停机回执](contracts/p3-a03-stop-evidence.json)，只stop、不down-v、不称cleanup0。A03作者已收口，独审/精确CI/Root Gate及B集成仍pending，Phase3未完成。
