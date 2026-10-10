# Phase3 A02：T3决定、单业务中断恢复与持久执行边界

正式后续回执（2026-10-11）：A02已由Root核定通过，source24856555fe23975fb19cd67ddcc033f6cac3905c/tree5306496d、新独立24实际PG/155.72s、migration1/pure19/wire21/Core无阻断；[CI38064613062](https://github.com/aning0922/commerceops-agent/actions/runs/38064613062) SUCCESS，actual196d824ca2b3238d5491c494a3b813062587fcb1/main59+248/tree同源、978offline/236旧PG/59P3/3G1/6G2/cleanup0。[Root放行](https://github.com/aning0922/commerceops-agent/issues/34#issuecomment-6099399935)。旧独立12/8 not_verified保持；下方“待Gate/A03未实现”是原A02冻结历史，当前[A03](PHASE3_A03.md)候选与[Phase3分层验收](PHASE3_ACCEPTANCE.md)另核。

状态：作者源码与实际验证收口；冻结SHA独审、精确CI及Root A02 Gate待新回执。分支`codex/phase3-approval`、隔离WT62c8、同[Draft PR37](https://github.com/aning0922/commerceops-agent/pull/37)，A不合main。Root在A01 Gate后已派本批完整T3/恢复范围；A唯一负责后端/迁移/Worker/Graph/共享合同/集成，B前端独立未合入。

## 已核前置与边界

A01已由Root核收：`aeaa916a59341a6ffa4a89f863d065580599f6d3`，独立39业务/40增量、[CI38055767391](https://github.com/aning0922/commerceops-agent/actions/runs/38055767391) SUCCESS。实际checkout9226da3（main59+aeaa）/tree3dde1cde同源；952offline/116.70s、236旧PG/265.70s、35P3/101.44s、3 verified G1/6 G2/cleanup0。放行见[Issue34](https://github.com/aning0922/commerceops-agent/issues/34#issuecomment-6098087434)及[Issue33](https://github.com/aning0922/commerceops-agent/issues/33#issuecomment-6098087681)。[A01](PHASE3_A01.md)此前未通过/未放行是历史快照，失败事实保留。

期间Root插入一次≤15min扫描策略批：`9f4aee5afaa83b9999ef190eec778584efd988c4`只提交六个策略/测试/记录文件，A02 WIP未上传。Root核独立14专项、[CI38061513830](https://github.com/aning0922/commerceops-agent/actions/runs/38061513830) SUCCESS，实际checkout238e743/tree3dc372571a4ba509743eb784b35afcd68448dbc5同源；959offline/124.72s、236旧PG/239.21s、35P3/100.14s、3 G1/6 G2/cleanup0。第四例外仅B历史公开元数据generic-api-key/精确path/line/整行regex同时匹配；222原规则、原三例外保持，见[策略记录](PHASE3_B_SCAN_POLICY.md)。此CI不含A02，不能代替A02 Gate。

本批source_mode=mock、identity_mode=session、approval_mode=simulated_web；实际PG与进程故障并非人工业务审批。新付费调用0/飞书业务写0，旧P1/P2/A01密钥及.env未读。A03重验/execute/T4/items/T6未实现；生产/飞书扩权/Phase4未授权。P1/P2/#23 not_identified/risk_accepted、M1冻结18页、D1/D30/300h保持，人工H/L not_reported。

Root另核B02只读Gate：source8365abf8、独立Review无阻断、实际7PW/22Origin/17contract，[CI38063196793](https://github.com/aning0922/commerceops-agent/actions/runs/38063196793) SUCCESS、actual4fdb18c4/tree5c4ade82同源；981offline/125.66s、236旧PG/247.43s、35P3/100.65s、3G1/6G2/cleanup0、三scan0。这是B的独立只读/会话证据，不是A02作者测试，PR36仍未合本脏WT，write接线待Root在A02 Gate后派单。

## T3持久事务与唯一决定

POST `/api/v1/approvals/{approval_id}/decision`核PG Cookie会话、精确Origin/CSRF、当前identity/credential/principal/auth_version、当前逐角色shop scope与冻结eligible；权限预检先于严格JSON。持久幂等锁后按task→plan→approval→当前身份锁序，全部锁取得后才读DB clock判expiry。plan ID/version/hash、nonce摘要/当前key及当前plan完整核对，客户端actor/approved/role、bool/float版本、重复键拒绝。

unknown_inbound只能`approve_with_assumptions`提交冻结要求完整精确集合；普通approve、缺项/多项不隐式确认，重排不改变语义hash；硬阻塞/披露不全不能批准。一次T3事务写唯一决定与决定者identity/auth_version、一审计、一resume job、强绑定approval_resumes及不可变原请求回执。原actor十次回放/同语义新key复用决定，反向/他actor冲突，仍须当前可读原任务。撤权旧session失效；重新登录并保留原task读权时仅已决定回执可读，新决定仍无权限。checkpoint不替代副作用事务。

`0006_p3_decisions`新增ready checkpoint、决定者版本/身份、resume/continuation绑定、原请求不可变与拒绝/过期终态证明；`a02_no_t4_consumption`要求approvals.consumed_at恒NULL。delivery_state=consumed仅表示业务interrupt已接收PG决定，绝非T4消耗。A03须普通后续迁移替换临时CHECK并补永久execution证明；带plan task不提前completed。

## 同Worker恢复与静态断点

固定同workflow/thread/节点prepare_approval→wait_approval→revalidate→execute→finish；唯一业务interrupt仍在wait_approval。Command只带最小标识，wait节点重新读PG权威决定。ready/card须实际官方StateSnapshot匹配workflow/task/request/plan/version/hash、next精确wait_approval及唯一匹配interrupt；card pending但sender永久false，不发平台消息。

Worker空闲时按1–30s串行扫描已注册等待任务，没有第二Graph/调度进程。早到T3 resume持久等ready，不按普通三次执行失败杀死；ordinary retry限制保持。旧进程未确认终止时替代Worker拒绝启动，实际SIGKILL/失锁退出、OS wait/reaped并显式confirm后才能接续原job，不热接管。

Root批准临时compile `interrupt_before=["revalidate"]`，这是程序静态边界，没有第二个人工interrupt。批准送达后实际next=revalidate、interrupts空；同持久事务记录唯一recover continue:decision_id、delivery receipt及task executing。原resume done后continuation job仍在A02 pending_execution持久等候，执行0/T4消耗NULL。A03只能去掉此静态策略并`ainvoke(None)`续同CP，不能回START/重发Command/换thread或版本/索要新决定。官方[静态断点文档](https://docs.langchain.com/oss/python/langgraph/interrupts)说明None接续；本批真实PG兼容probe用相同固定节点仅运行无副作用revalidate探针，execute前停止，不冒称A03重验/执行证据。

失锁专项实际复现prepare_approval CP已存但无approval时误判P3_APPROVAL_MISSING。修复仅允许旧WORKER_TERMINATION_UNCONFIRMED在session.start核旧OS退出后、无active plan/已决定记录、相同workflow/task/request/thread、next精确prepare_approval/无interrupt、原analyze固定dedupe/payload/组织店/运行lease归属，恢复queued并以None续现有CP；实际核原绑定保持、plan/approval/outbox各一。其他CP版本/plan/未知next转needs_attention，不泛化扫描批准任务。未知workflow job和非终态task同事务dead/needs_attention，不当新图运行。

## 唯一DTO纠正与准确导出

Root仅批准[冻结合同](contracts/p3-openapi.json)DecisionReceipt.acknowledged_assumption_keys.items.maxLength 256→300；Input/Assumption原已300，SKU/pool仍256，没有新增长SKU/plan拒绝或截断。前缀21+合法256SKU=277键，纯合同正例/301负例、实际PG决定/十次重复及HTTP JSON Schema回执均校验完整键。

包内assets/p3-web-v1.openapi.json与合同原字节一致；FastAPI仅导出已注册operation的approved input/responses/security/components并标implemented，无合同注册拒绝。runtime是17 paths/18 operations，完整合同21 paths/22 operations。getExecution/listItems/getItem/resolveItem四个未实现，完整22 runtime Gate、正向cached explanation HTTP和B浏览器决定页面仍待后续实际证据。

## 实际检查与失败保留

PG批次用唯一新A02项目/显式本阶段密码文件，fresh临时DB每测finally DROP，严格串行，不记录Cookie/CSRF/密码/DSN/原始业务行。

| 命令/场景 | 实际结果 | 边界 |
|---|---|---|
| `pytest tests/test_p3_decisions.py` | 17passed/0.40s | 纯集合/hash/严格shape/官方snapshot绑定 |
| 初始完整A02 PG | 17passed/102.56s | 四决定分支/十次回放、两eligible approve/reject race、R05/R06/R07/R08/R17实际kill、单Worker/slot释放、语义新key/两unknown/277键/撤权 |
| 实际DB锁等待跨TTL | 1passed/65.06s | 真60s不可变expiry，实际API task锁等越期→410、T3副作用0 |
| 失锁修复/增强专项 | 1passed/6.34s；随后4passed/17.48s | 终止owned backend、OS exit2/reaped、TermRequired、confirm原CP；另三个真实持久CP版本/plan/next错误转attention |
| 首次完整P3组 | 55passed/225.13s | 35旧+20新，之后增强绑定/断言并新增三个不可信CP测试；最终结果另记 |
| 增强后完整P3组 | 58passed/231.38s | 35旧+23新，含真expiry恢复expired/唯一recover；随后仅追加一个DB约束负例，最终59项组另记 |
| DB约束/历史断言修复专项 | 2passed/4.86s | runtime提前消耗/完成/回执改写/续跑拼接均DB拒绝；runtime无DELETE权限、owner DELETE也被不可变trigger拒绝；旧workflow保持原内容/thread且attention/新采集0 |
| 最终实际旧PG组 | 236passed/143.20s、2既有SDK弃用warnings | 当前完整collection295，既有236/P3新增59无重叠/遗漏；组实际collection与expected精确一致，旧断言修正后完整重跑 |
| 最终实际P3组 | 59passed/223.88s | 35既有A01+24 A02；每组重新核实际collection精确相等，全部295 integration已实际运行通过，单组仍低于原300s；G1/G2/精确CI另待Root |
| `python -m tests.p3_wire`，临时jsonschema4.26.0 | 21实际HTTP响应checks passed | A01原17响应+决定/重复/原请求/决定后详情，含277键，不冒称22ops全部运行 |
| `python docs/contracts/p3-validate.py`，临时openapi-spec-validator0.7.2 | 389checks、21/22/67 | 原385+4长键合同检查，无PG/服务/权限运行 |
| `pytest tests/test_p3_openapi.py tests/test_p3_decisions.py` | 19passed/0.98s | 实际注册导出subset/package原字节、无合同operation拒绝与纯决定测试 |
| `python -m scripts.check` | exit0；978offline/92.27s、291 integration deselected、2既有SDK弃用warnings；Ruff/228format/mypy163、Node24.21.0原tooling/typecheck，Node/95Python漏洞0，dir/index/git扫描0 | 完整离线工程检查，不替新增3PG/精确CI |
| 收口后`python -m scripts.check` | exit0；978offline/91.46s、294 integration deselected；Ruff/229format/mypy163、扫描0、Node/95Python漏洞0 | 后续仅增一PG负例/更新旧PG断言，纯测试集合未变；最终静态检查另核 |

失败历史：最初十项8pass/2fail/55.76s是恢复观测断言错误（idle reconcile不发after_ready测试hook、confirm后瞬态旧TermUnconfirmed应有界等待）；改实际DB ready/state后三R05–07/15.28s、static/delivery/单Worker三项16.24s通过。expiry前两次68.60s/73.73s失败因observer事务缓存pg_stat_activity，第二次future Timeout说明仍锁等；显式pg_stat_clear_snapshot后65.06s通过，没改expiry/hash/批准规则。wire helper与T1局部变量同名，16 checks后TypeError，alias后21响应通过。static兼容/失锁联合1pass/1fail/10.36s复现产品prepare gap，修复后失锁通过；此前联合调用输出未取回，另次真实重跑单列，不虚填原结果。纯OpenAPI初次缺offline DatabaseSettings必填配置，1fail/18pass/0.40s，显式不读密钥的离线参数修复后19pass。普通lint/format迭代保留，不归成三轮同类产品阻断。

旧236回归第一轮235passed/1failed/149.44s：唯一旧inventory workflow断言仍期待queued，与本批明确unknown workflow/task原子needs_attention合同不符；只更新该断言并增原kind/workflow/thread/request保持及采集/报告0证明，2专项通过，完整旧组重跑另记。没有修改旧版本/历史请求来通过测试。

最终295 PG全部通过；最新19纯决定/export/0.66s、Ruff/229format/mypy163及文档检查全部通过。冻结前后扫描与上传回执另由提交/PR记录核对；独审/精确CI/Root A02 Gate待实际回执，R09和A03 R10–12/C01–05/T4/T6、完整Phase3 Gate尚未运行。

## 自有资源与时间账

唯一新项目p3a2-1ec0f4e8c9fb、owner phase3-A02-WT62c8、UID501、loopback49296，PG17.11-bookworm固定镜像摘要。登记22:27:26.699148+08:00，Docker实际StartedAt22:27:54.497618178，原停止截止2026-10-10 23:57:26.699148+08:00，90min不延期。私有目录700、两PG密码/ports/ledger600且ignored，仅启动本项目postgres；每测临时DB DROP。实际23:38:08.318816587停止，23:38:19观察running=false/PID0，早于原截止；停前临时DB0/其他base连接0，app superuser/createdb/createrole全false、revision0006，ledger更新仍0600。只stop postgres、保卷/证据、不down-v，不宣称cleanup0。安全字段见[停止回执](contracts/p3-a02-stop-evidence.json)，未上传raw rows/secret。

Agent墙钟21:41:21开始（Asia/Shanghai），测试等待按报告单列，不估算未捕获有效开发时间；人工H/L not_reported，不提前宣称main合入/合后CI/Phase3完成。
