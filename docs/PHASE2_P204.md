# Phase 2 P2-04 集成合同与证据

当前 in_progress_p2_04 / changes_requested 修复复审待定：P203已获冻结3986dd独审/精确CI内部门禁；B组件经独审普通合入A07d3。A在同一Draft PR30完成固定五意图路由、解释子任务、权限和持久预算集成，作者代码/完整检查候选已交付，最终冻结SHA独审/精确CI与受控真实窗口尚未完成。真实provider请求0，真实routing not_run；不以Mock/模板或组件独审抵最终Gate。

## 1. 固定工作流与事务

P203 `inventory_analysis_only` / `p203-inventory-analysis-v1`、报告completed语义、冻结InventoryReport/goldens及checkpoint保持。说明使用一级显式 `report_explanation_only` / `p204-report-explanation-v1` 新UUID/thread；只有自己的已完成P203 Mock报告能作为父引用。父task、snapshot、report、facts_hash、body_hash、logical_key与当前操作者/identity/auth_version/org/shop/grant分别核验。完成结果、收据和child completed同一PG业务事务；checkpoint不是副作用事务。

模型路由是固定 `inventory_intent_only` / `p204-inventory-routing-v1` 新UUID/thread。原句限2000字符、catalog固定inventory-intents-v1、prompt固定inventory-routing-v1；原句不能提供scope/role/approved/evidence-mode。DeepSeekRoutingPort只接受五意图及有限L/R/S候选，确定性guard验证Unicode原句span、整数0..365、参数名及明确来源，拒绝重复/缺失确认/越权字段。不是字符串匹配冒充LLM。routing结果及单独routing审计不自动创建库存分析、审批或补货业务任务。

三张固定图由同一Worker/global Graph slot串行执行，各自pin版本/thread/key。没有通用子Agent/动态工具/通用调度。新表为显式intent请求/结果、说明引用/结果/收据、模型调用/观察及阶段预算；证据禁止UPDATE/DELETE/TRUNCATE。所有own PG测试是Mock/simulated范围，旧P1真实有限Gate另行记账。

## 2. 五意图与有限参数

| intent | 确定性边界 |
| --- | --- |
| inventory_replenishment | 仅受限分析意图；缺省L/R/S=3/7/2标demo_assumption。未确认参数不能自动创建库存业务任务 |
| task_status | context必须是当前org/shop/requester的P203任务；读取任务状态 |
| explain_report | context必须是自己的已完成可信报告；显式说明child，没有业务审批/执行 |
| clarify | 歧义、未知scope或不安全候选；不创建库存/补货/审批任务 |
| unsupported | 采购/支付/退款/执行等超范围请求；不执行 |

受控 `/test/route` 默认只入队template模式意图任务，HTTP输入不能开启paid/provider；`/test/routes/{task_id}`只读取已存结果。显式注入的Mock port用于契约验证；若参数未全部具有代码确认的explicit_text来源，受控业务分派返回澄清。正式session/飞书多轮权限未授权且未实现。

## 3. 同一阶段持久预算与恢复

routing和explanation真实调用共用 `phase2-deepseek-20261010:actual`；自有替身仅使用独立offline账本，不能当作实际provider证据。固定DeepSeek/deepseek-flash/https://api.deepseek.com Chat Completions，thinking disabled，无tool/自动重试/model切换/redirect/proxy继承。端到端绝对截止20秒。

输入上限8000，输出800；每次先原子持久预留一次调用和8000/800峰值cache-miss费用US$0.00336，再进入HTTP。阶段总调用≤10、USD cap≤0.10。随机HTTP request_id用于追踪；幂等依据scope、原句或报告hash、完整body、prompt/model/catalog/mode/pricing组成logical_key。预算count/金额只能单调增加，halt不能清除；预算行不能删除或TRUNCATE，重启不清零。

usage/价格估算/预留金额分别保存；无实际账单时actual_cost_usd=NULL，不编造实际费用，不经库存Money(20,6)serializer舍入。未知timeout/usage/cost、截断或usage越界保留完整预留并halt。已预留而无业务结果时，无论重试或OS确认后的恢复都不重发HTTP；返回安全模板/澄清，记录uncertain。已提交结果则优先收据，重复读取/恢复不再扣款。继续保留P1显式OS终止证明，lease/锁可用不等于原进程已停止。

## 4. Token与key边界

固定官方纯文本资产、完整chat framing、上界与API差异余量见[tokenizer资产说明](../backend/src/commerceops/infrastructure/token_assets/README.md)。本地GIL释放的有界BPE计数不冒充API实际usage；正式窗口须核对usage和上界差异。runtime使用锁定tokenizers0.23.2及httpx0.28.1，不下载模型或执行远端代码，no-dev wheel应包含资产。

默认Worker和API不读模型key、不连接provider。仅Root明确真实窗口后使用inventory-test-run的显式actual开关和key-file；key必须当前OS用户所有、普通600文件，拒symlink，open/fstat核同inode后限512字节读取为SecretStr。`model_probe verify-config`只stat/验证非secret固定profile，不读key/请求API。本轮没有读取现存`.env.model.probe.local`或`runtime/model/api_key`内容，没有balance/models探测。

## 5. 验证记账与保留边界

已实际执行的开发专项：解释7 PG第三轮全部通过/13.00s；两种SIGKILL→阻止启动→显式OS确认→新进程恢复均无第二次HTTP。预算并发两项PG通过/3.56s：12个不同请求最多10个预留、相同logical并发仅1个且unknown halt。路由/token/config+原P203离线契约59项通过/1.09s（含35新增P204）；当前/index/完整可达history敏感扫描0，scanner配置/豁免未改变。首轮tuple与JSON list缓存比较错误、第二轮严格DTO list错误真实失败记录保留，第三轮7项通过，不把失败或未运行写成通过。

准确profile组合后P204完整专项18 PG passed/26.47s：路由与解释同账本、五意图、same-key缓存、并发最多10/重复一次、四处真实SIGKILL恢复、授权撤销、读接口无调用、owner/runtime不可变保护，以及越界usage降级后只读可用。完整scripts.check实际826 offline/68.98s，182 integration deselected；mypy135源文件、ruff/format/文档/锁/Node工具链通过，Python95锁依赖及Node漏洞0。no-dev实际runtime中httpx0.28.1/tokenizers0.23.2/固定token资产可用、pytest未安装。

完整隔离PG supervisor使用自有p123-92f833c0a6ac/无宿主端口，0003迁移/初始化/授权/版本查询重跑成功；182 PG passed、826 deselected/90.79s（含85 P203、18 P204），G1三次count_one核验及六种G2必要证据完整，passed_no_hang_reproduced，cleanup_exit0。实际复核containers/volumes/networks均0、所属runtime目录已删除。早前自有p203-006432bf0e也已cleanup0且只移除所属PG密码；模型资源未读/改。最终冻结SHA独审与新精确CI尚待，作者自检不替代独审或实际模型Gate。

完整组合验证前另保留两个真实失败：旧B profile尚未同步时误提前运行1条routing PG，预留按prompt_version不匹配拒绝，1 failed/2.43s；准确B routing-v1同步后已通过。初次18项扩展前12项综合为11 passed/1 failed/20.93s，owner TRUNCATE被外键提前拒绝，测试调整CASCADE以明确触发不可变保护后通过；没有放宽数据库保护。安全扫描初轮两个非secret label/多赋值误报，改清晰分字段代码后三层0，scanner规则/豁免未改。真实routing/解释仍not_run，正式T3/真实库存/自然网络故障/wire/p95/长期幂等不外推；#23 risk_accepted/not_identified、P1冻结和M1冻结保持。

基线机器Darwin25.6.0/arm64，Python3.12.13；隔离容器PG17.11-bookworm。数据inventory-v1固定25场景，baseline为1 product/1 order/1 inventory、0 refund/open_item；P201/202共享DTO、fixtures/goldens的hash不变。真实模型基准、M1前端联调/交互回归、p95、40×3重复稳定性、生产认证、正式审批/执行仍not_run，不将这些开发运行时长外推为产品性能或人工有效工时。

双线及额外Review扣原P204/Phase2 30–40h与总300h，不增预算，不改D1=2026-10-10、D30=2026-11-08；人工H/L not_reported。A只交付实现与证据；Root在全Phase2必要Gate后按用户委托正常合main，A不自行合并，不扩后续Phase/飞书/生产。


## 6. a057独审两项P2与同批有界修复

[独审5478116042](https://github.com/aning0922/commerceops-agent/pull/30#pullrequestreview-5478116042)在冻结a057确认两项P2：同key不重发不足以防止恢复队列先执行另一key，在旧未知调用处理前会新增HTTP；整数regex可将L=4.5或4/5截为explicit_text L4，进而写库存分析任务。独审全量182PG通过也不解除这两个独立探针缺口。[旧a057 CI38033440268](https://github.com/aning0922/commerceops-agent/actions/runs/38033440268)实际SUCCESS（checkout30d0b7a8/caffe+a057/tree412eb219，826offline99.38s/182PG196.56s、3G1/6G2/cleanup0），保留为旧候选，不能抵新修复审核。

最小修复追加0004，仅给不可变model_calls增加nullable worker_owner记录原可信执行代际；不回填/清除旧ledger，不把owner纳入logical_key/bodyhash，不改变预算/权限/队列优先级/OS终止合同。在全阶段row lock内检查所有调用；只有observed、stop=false且completed+精确业务receipt才算确定。当前owner、仍running/analyzing的合法inflight保留；旧/无owner或已非在途未定调用持久halt，缺失观察追加uncertain，已有观察保持不可变。新不同key admission及恢复入口均先执行此fence，不依赖原job排序或其当前身份仍能授权。

参数来源改为独立完整整数词元确认，拒小数/分数/范围/相邻数字（含Unicode空白）及缺失/重复字段，不从模型截断候选推断确认。明确整数、天单位和合法标点控制保留；模型仍负责五意图，不用regex冒充模型路由。

30分钟原窗口07:17:48～07:47:48 UTC、最多两针对PG批，均由Root有界派发。自有p203-b2653e7c95：首批34 passed/12 failed/38.27s，其中33 P204全部通过，12 test_postgres失败均base库未初始化的UndefinedTable；正确完成0004/migrate/setup/grant后第二批46 passed/1 failed/38.13s。唯一失败是新增call_observation_committed屏障用例沿用旧expected uncertain，而正确不可变观察为observed/stop=false；该case在失败前已实证second HTTP=0、reserved_count=1/full金额不增、stage halted、原+另一task状态/owner绑定正确。测试source已仅更正该观察断言；corrected-image本地PG未再运行，不写作者全PG通过。Root明确不加第三轮，冻结后独立复审重放原两probe及修正用例，并由新精确CI覆盖完整正确测试；任何未通过仍阻断。

必要完整scripts.check实际838 offline/71.80s（最后Unicode空白增补前），mypy136源文件、ruff/format/docs/锁/Node检查及Python95包/Node漏洞0；最终source再跑840 offline/69.66s、198 integration deselected，新参数/token/config专项49/0.83s。corrected-image PG仍未额外跑。自有p203-b2653e7c95 containers/volumes/networks全0、所属runtime/PG密码已移除，model资源未读/改。提交前current/index/全部可达history扫描结果记于同PR冻结回执。没有扩大Bnamespace/权限、通用框架或新阶段预算；actual provider0、key/env未读、main未合。第5节完整通过属于a057作者候选历史，当前两P2解除须新冻结复审/新CI，不能复用旧全绿。


## 7. 6910复审参数单位空白残留与第二源码修复

Root在精确6910复审实跑198 PG/109.74s，corrected observed断言/撤权恢复通过；原恢复probe第二HTTP0/reserve1/halttrue、legacy NULL与新owner完成缓存复用通过，预算原P2独立解除。原L=4.5/4/5 realPG HTTP clarify且库存任务增量0，合法整数增量1。但同参数P2尚有单位前空白残留：`L=4 天到5天 R=7 S=2`、实际NBSP `L=4 天到5天 R=7 S=2`、`L=4 天 / 5 天 R=7 S=2`仍all explicit_text，独立realPG各错误创建1库存任务。旧6910 CI38035465760 SUCCESS不能抵此复审残留或完整Phase2 Gate。

本轮仅在原数值词元guard的单位lookahead前处理Unicode空白，再识别限定天单位及后续范围/分数/小数/邻数；没有整体重写原句，span/input/bodyhash保持。预算/Owner/migration/queue/权限/B均不改。原Root07:55～08:05 UTC10分钟source/offline窗口，作者不追加第三PG。

新增7项专属离线回归：三非法原句的旧6910 guard都在intent断言实际失败；四合法控制在guard后遇新测试DatabaseSettings必填配置缺失，首次after也因此7失败，补显式离线假配置后最终56专项passed/1.35s，mypy136/ruff通过。三非法的HTTP应用分派为明确scope/DB/创建函数替身，created次数0；`4`、`4天`、`4 天`、`4 天`控制各created1且候选原句span不变。替身不冒充realPG/生产auth或已完成独审。新冻结须Root增量独审及新SHA实际CI/必要PG，模型0/key不读/main未合，保留同源修复轮次与旧失败事实。


## 8. 同参数P2第三源码轮：Unicode数值字符与明确半天

0462指定增量由Root独立56offline/1.45s及fresh9真实HTTP/PG验证通过，原小数/分数/三单位空白非法Task0、四整数控制Task1/hash不变。但独立离线+实际FastAPI创建函数替身确认`L=4 ½ R=7 S=2`及`L=4 天 ½ R=7 S=2`仍explicit L4/create stub1；此两个发现不是PG插入证据，第二源码轮尚未覆盖Unicode numeric非decimal类别，不能称全参数P2解除。

原A第三轮按Root本通知起5分钟，仅将原词元后续数值类别isdecimal改isnumeric，并拒明确“半”续词；保持原句/span/hash与已有56控制，不改Budget/Owner/迁移/锁/queue/DTO/B/权限/fixtures，无作者新PG/完整大检查。新增9代表控制覆盖½/¼/⅓、天单位前后空白/NBSP与明确4天半/4天 半/4 天 半/4 半天。旧0462实测新增/既有单元16中8 failed/8 passed/0.92s；修正后专属65offline通过（实测时长见同PR回执）、mypy136/ruff。非法应用分派替身create0、原整数控制create1，替身不抵Root新冻结独立PG/HTTP与实际CI。

同源第三修复轮事实保留；若此轮复审仍同类未解除，按Root合同暂停参数任务并交原因/最小风险方案/ETA，不自行第四轮、免测或绕Gate。模型0/key-env未读/no main/既有预算不变。


## 9. 用户批准一次有限正向文法收口（尚待最终独审）

第三源码轮044a独审[5478299031](https://github.com/aning0922/commerceops-agent/pull/30#pullrequestreview-5478299031)真实PG确认`L=4 ⁄ 5 R=7 S=2`（U+2044）仍错误Task+1；65offline/正确控制不抵该反例，参数任务依第三轮上限暂停。用户随后明确批准一次完整有限正向文法有界收口，原A/WT/分支/PR不变，新增2.5–4 Agent有效工作小时扣原Phase2/300h，人工H/L not_reported、机器CI另记；绝对停止2026-10-10 12:25:16 UTC（20:25:16北京时间），最多一完整实现批次+一次冻结独审+精确CI。若最终同源阻断立即停止，不自动新冻结修复，不降低必要功能/Gate。此次不是第四次逐符号补丁。

唯一应用变化为inventory_routing私有 `_explicit_lrs_spans`：保留第一处明确赋值之前的意图原文；参数块从该处完整消费至EOF。PARAM=NAME(L/R/S)+现有SEP(=/:)+ASCII整数0..365+可选Unicode空白/天。参数间只接受Unicode空白或单个逗号/分号（中英文），下个必须是明确PARAM；句末只允许既有。!！?？及空白，保留单个尾置逗号/分号的既有明确控制。其他字符/未消费尾缀一律clarify，不列分数/范围坏字符拒绝集，不建通用parser/NLP框架。duplicate、模型候选缺失/错span/值/来源仍拒；没有显式候选的默认3/7/2始终demo_assumption，API未确认不写业务任务。原文、cursor span、input/body/logical hash不标准化，五意图仍由模型提出。

应用/测试文件边界仅inventory_routing、专属offline与既有PG dispatch测试及本合同/STATUS/ROADMAP当前事实；Worker/Graph/API逻辑、共享DTO、B、依赖锁、审批/权限、migration、Owner/budget与fixtures/goldens未改。作者先以044a实际回归U+2044：1 failed/16 passed/1.43s，保留旧缺口；正向helper后原65+该例66通过，再补全参数块验收38类（13明确合法、25澄清）。覆盖未知字/未知标点尾缀、标点夹数、分数/范围/duplicate、多余参数/不完整模型候选，及正常请求prefix、天、ASCII/Unicode WS、逗号分号、句末标点、顺序/0/365合法控制。

本批实际：105专属offline/1.98s（含原控制），完整scripts.check896 offline/69.45s、236 integration deselected，mypy136/ruff/format/docs/锁/Node通过，Python95锁依赖及Node漏洞0；current/index/全可达history敏感扫描0。唯一fresh自有隔离PG项目p203-c61413fcb4无host ports，0004/migrate/setup/grant与runtime NOSUPERUSER/NOCREATEDB/NOCREATEROLE/测试库残留0已核。85定向真实PG/47.40s（72 P204含38块级真实HTTP及13基础PG）通过：每个澄清Task增量0，13合法控制各Task1、原数值/hash/span保持，并保留既有预算恢复/权限/缓存回归。完成后仅该项目containers/volumes/networks全0，所属runtime/密码移除，模型资源未读/改。本批没有第二fresh项目或真实provider请求，没有作者失败循环。

这些仍为作者候选证据；新冻结必须一次独立复审及精确CI，旧CI不替代。通过后Root另安排原≤10/8000/800/US$0.10真实模型窗口，再阶段结案/main；actual0/key-env未读/no main/Phase3未授权。
