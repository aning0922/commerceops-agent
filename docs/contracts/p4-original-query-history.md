# 原两条查询的历史来源恢复

本批按用户已批准的四小时整包接续，由原 A 实施、原 Reviewer 审核、Root 统一真实准入。
此前设计与预审用量累计，不重置原 P4、300h、旧 SDK、Create、attempt 或 once 账。
公开 `9ee82e15` / CI `39101285628` 只签旧候选；本合同对应的新源码须另行冻结、独审和精确 CI。
M1 与 Phase4 仍未结案。

## 唯一实际范围

只读取原 A 与机器人的已确认 p2p chat，固定 UTC
`2026-10-17 13:01:45–13:05:45`，最多两页、每页 50 条。
原两条精确文本在私有 Root 输入中冻结，分别是 `task_status` 和 `explain_report`；
实际 original message_id 目前未知，只能从首次官方响应中唯一取得并持久保存。
不扫描其他 chat，不扩大时间或页数，不让用户重发，不补造 WS event 或 Gateway claim。

平台能力依据为[飞书历史消息 API](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/list)。
请求使用秒级字符串边界、`ByCreateTimeAsc`、固定分页大小和原响应 token；
响应按原始 HTTP JSON 校验，保留毫秒字符串、布尔类型、原发送者、正文及编辑/删除标识。
完整分页后，两条精确原文必须各唯一匹配；列表可以包含无关消息，无关行不进入回复路径。
缺失、歧义、字段冲突、权限拒绝、分页不完整、超时或 unknown 均 HOLD，不重试或换窗口。

## 来源、当前权限和去重

新增 `0017_p4_verified_history`，旧 migration 原字节保留：

- `p4_history_recoveries` 独立提交一次取回机会，绑定当前身份、配置、两条原文和绝对 SDK 截止。
  每页原始响应、HTTP 状态、观察时间和 hash 逐页保存；终态不可复活。
- `p4_history_messages` 只保存完整验证批的两条原消息及处理回执，保留真实 message_id、原发送时间、
  API 观察时间和当前处理时间；不创建伪造的 inbox/event。
- `p4_read_message_sources` 提供实时/历史共同的消息唯一键。两者使用原 app/tenant/message 锁；
  唯一键同时阻断实时 RR 等待后仍持有旧 snapshot 时的第二个载体。

`p4_read_replies` 的来源为原 inbox 与历史消息二选一，原 payload、provider UUID、attempt1、
unknown 终态与旧窗口上限保持。旧数据升级仅增加来源键，旧列值、payload 和消费状态不得改写。
历史处理时重新核当前身份、auth_version、店铺、任务可见性、报告和事实源，as_of 来自当前数据库时间。
实时先到则保留原回复 UUID；历史先到则实时重投返回同一载体。身份、chat 或正文冲突保持拒绝。

## 原生实际入口与窗口

现有 `commerceops.entrypoints.feishu_business worker` 增加显式
`--worker-mode history_recovery`，输入为默认关闭的 `HistoryRecoveryRequest`。
Root 绑定实际解释器、CWD、配置/请求/source hash 与绝对 UTC 后，才可使用 `--live` 与
`COMMERCEOPS_MODE=p4-controlled-test`。原生父进程管理 canonical child、退出与生命周期核验；
child 复用原 WorkerSession、Factory 和持久 SDK ledger，不构造普通 Worker/Graph 或模型。

独立 once 注册和当前权限检查在 AppSecret/Factory 之前；Factory 自身也要求已登记的当前历史 once。
取回仅 auth1 + bot1 + message.list2，总 SDK 至多 4，SDK 窗口至多 120 秒。
取回成功只生成待发送的读取载体，不在该模式发送 IM。
Root 以 `read_reply_window_from_history` 从原恢复批和原 message_id 派生两个默认关闭的发送输入，
再使用现有 `read_reply` 原生父/child。两条回复分别 auth1/bot1/IM1，总新增回复 SDK 至多 6，
实际统一回复段至多 300 秒；历史载体在发前继续检查当前权限、版本和来源。
回复明确说明原查询的延迟处理；unknown 不改 UUID、不换窗口重发。

Root 的实际 PG/采集父窗口至多 600 秒，最后至少 180 秒清理。
配置、原库、Secret、平台调用与真实 SDK 当前仍 HOLD；代码和 Fake HTTP 不代表真实取回或回复成功。
不写 Base/Card，不创建新业务任务，不改审批、库存、迁移前历史消费状态或权限范围。
本批仅使用已批准的 `im:message:readonly`；不增加群历史或通讯录权限。

## 验证和当前事实

隔离验证只使用全新 owned PG 和合成身份；新增用例仅替换最底层 HTTP。
SQL、角色、once、Factory、SDK ledger、父/child 和退出均真实执行。
最终同源业务/SQL 候选新增 14 项实际通过，JUnit 134.666 秒；受影响的旧读取及迁移 31 项通过，
JUnit 212.246 秒。两条命令及最外层均 CLI0，在固定 600 秒 PG 窗口内于
`2026-10-18 11:10:49 UTC` 完成清理：容器/网络0、端口关闭、卷保留。
覆盖两条回复、两种并发顺序、冷重放、API403/API unknown/IM unknown、撤权、中断与
0016 旧 unknown 载体升级保留。13 项开发候选 123.104 秒的旧结果仍保留，不混签最终候选。

0017 保持原生可延迟检查的 history→reply FK。owner 普通 TRUNCATE 在原触发器前被 FK
以 `0A000` 拒绝，CASCADE 仍以 `23514` 拒绝，实际非空历史和回复行的全部字节不变；
旧 0015/0016 触发器契约及应用角色权限、UPDATE/DELETE/篡改拒绝保持。
曾为异常类型一致试用的延迟触发器候选已放弃，其 300 秒单命令截止、exit -15 和资源清理单列。

从原 `9ee82e15` Git 对象独立 collect 的 541 个旧 PG 节点全部保留；当前完整 555，
quality372 + phase3183，交集0。新增 14 项仍进入既有 phase3 分组，与原三个节点合为17项，
不新增 job、不提高单命令300秒或既有绝对截止与清理预算。本机时长不保证 Hosted 同速。
最终标准检查、源码 SHA/tree 与独审/新精确 CI 以冻结回执和 Root 后续事实为准。

开发失败保留：首轮卡片文案断言未解析 JSON 转义；次轮撤权夹具遗漏 auth_version 递增，
由数据库原约束拒绝；原生 FK 下旧 TRUNCATE 错误类预期失败亦保留，按精确 schema 合同更新测试，
不泛化捕获。旧 d97 固定源码闭包与 0012→0013 保留测试不改历史。
原 6337 身份映射验证另属先前批：normal0/7 行、permission1/42501/writer0 与 outer driver1 分列，
不以此合同重新开启原库或修订旧提交。
## 2026-10-19 取证整改接续（台北）

用户已批准[完整整改合同](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6252003251)；
Root 授权文件摘要 8b9f932af1a3c1abd400430c1cc2f85507364a167bbc33ffbbed1e091e272a9d。
总有效分钟由315增至435，新增最多120（A75/原Reviewer25/Root20，可统一调配），
此前 A186–207 分钟为未精确计量估计，所有既有消耗、失败和窗口保留，机器等待单列。

824 精确 CI39137562112 五作业通过、395+163=558及交集0由Root接纳。
原库0016→0017已原生COMMIT返回、父/child0，52表数据指纹和旧角色/ACL不变、资源清理保卷。
原历史取回于10-18 15:43:08Z启动、15:45:37Z清理，父/child1、summary空。
原两条message_id未验证，原始异常和HTTP未捕获，实际SDK/AppSecret及数据库once状态仍UNKNOWN；
不得由“实际启动机会用1/1”推填数据库once已SPENT。

整改先构造固定query-ID、schema17精确目录、低权app、RR READ ONLY、真实SQLSTATE、
rollback及I/U/D0的共享collector；独立窄RO入口无Worker/Factory/SDK启动分支。
第1新owned PG固定10-18 16:55–17:05Z，work cutoff17:02Z，cleanup至少180s；
最多两个新owned窗口，各600s，未启动不记消耗，不自动顺延。先冻结该入口及实际成功/SQL拒绝/
清理失败证据给原Reviewer；只有独审及Root新的绝对UTC放行才能开唯一原PG RO窗口。
原RO不读AppSecret、不调用SDK，不执行行锁权限函数、业务修复或恢复操作。

原库只读核账后，才完成既有父入口的reap→最终采集→清理→结果出口，
保留原始失败、采集失败、清理失败三个独立事实；采集预算不挪用180s清理。
公共child/parent通过既有JSON通道保留固定stage/category/code/SQLSTATE，禁止任意异常文本和秘密。
第2owned用同最终outer/argv验证成功、native非0、采集失败、清理失败和原键新进程重放，
Fake仅底层HTTP，SQL/角色/once/进程和清理真实。
最终冻结独审后由Root释放唯一新完整CI，45/43及旧558不减，新增节点另计。
真实RO或CI失败/unknown停止；本包不授权任何真实重取、回复、新消息或业务写入，
不新增迁移、表、权限、状态机、wrapper/框架/observer或重试。

原第1窗口16:55–17:05Z未启动，仍0/2：Root/Reviewer指出同chat批次扫描及新证据保存pagination token两项P2。原计划保留，修正后由Root另定UTC，不自动顺延。新collector仅原recovery并核app/tenant/chat，0行是合法观察；页面原字节仅在内存验证，新证据仅安全结构/链匹配、原文匹配计数、页面SHA和token摘要，不保存raw body或token原值。截止TimeoutError直接上抛，不吞入普通查询故障。

## 2026-10-19 第一 owned 失败及最终整包接续

Root重定第1新owned为10-18 17:12–17:22Z，work17:19；实际启动后夹具初始化
OperationalError/sqlstate未捕获，三RO命令及4PG均未运行。原生驱动1，容器/网络0、
端口关闭、保卷和标签由独立探针确认。候选根因仅为宿主接线，未作已证结论。
17:16:43Z尚余137s，小于210s保守上界，未启动同项目续段；窗口1/2保留。
原库RO0/1、原两条回复和真实SDK仍HOLD，原DB once仍UNKNOWN。

Root在同新增120min/总435min、最多两owned的既有授权内重排：先离线完成
原历史parent的失败finalizer与public history child/parent安全诊断，再于唯一剩余owned
同源验证全部必要路径；之后才准入唯一原库只读。最后完整CI仍由Root独审后释放。

公共诊断仅history模式：阶段/类型/允许错误码/SQLSTATE/固定栈位置，不传异常原文、
locals或响应。原始异常、hold异常、session close异常分别保留，缺child摘要明确NOT_CAPTURED，
不改变原非零、业务条件、once、迁移或权限。私有parent在writers真实reap后有界采集，
然后独立清理并出最终结果；原失败、reap、采集、清理错误互不覆盖。
最终采集预留90s及reap15s，不挤占180s清理；读取仍用同一低权collector。
绑定/目录失败后只补事务元数据以证明只读/rollback，不再继续读取业务数据。

待释放第2窗口的保守work预算385s：夹具接线50、业务成功/冷重放60、native非0 30、
采集失败40、业务清理失败40、三RO65、4PG100，另留35s work和180s cleanup。
先业务再纯RO/PG，保证SDK子窗、reap及采集余量。正常和预期失败的native exit分记，
测试blocker清理与被测入口cleanup失败分别记录，不拼接为实际运行成功。
当前相关126pure已通过；4新PG仍仅collect，最终owned/原RO/独审/新CI均未通过。
本次只验证历史取回的诊断和取证，不据此放行两条真实回复或解除原历史尝试。
