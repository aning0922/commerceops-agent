# P4 F02 持久澄清编号与原 T1 合同候选

2026-10-14（Asia/Shanghai）。Root已按P4持续授权及用户“澄清请求编号，确认后创建正式任务”决定派原A在WTfd38/同分支实施首包；当前仅offline和全新自有PG/Fake。本页先记录合同，实际测试/候选SHA/独审/CI及真人另记，不称能力完成。Base a1864 HOLD和原known70/0015/55表保持，不顺带修wire/RO/private bridge。

## 入口与编号

F02仅处理N01已支持的库存意图，复用pure支持句式及完整L/R/S参数文法，不搬Web auth、不调模型。不支持的意图保留原拒绝/固定澄清。F02入站模式默认关闭，首包由明确可信装配在Fake/PG启用；原受控演示T1/v1回复不被静默替换。正式Gateway/SDK装配须独审后单独安排，不能将Fake启用称平台可用。

初次支持请求无完整参数时建立随机UUID澄清请求，记录真实org/shop/App/Tenant/chat/principal/identity/初始auth版本、目标workflow_version、原inbox/hash、规范化窗口/范围和参数来源。此时无正式Task/source task/job/plan/approval/execution/item/outbox；不要求不存在的task引用。完整LRS仅产生待确认候选，不自动调用T1，不把演示默认值当已明确参数。

关联命令为`补充澄清 <UUID> 第<round>轮 <LRS参数块>`或`确认澄清 <UUID> 第<round>轮`，全消费、UUID规范格式、正整数round。只声称显式编号关联，不声称native-thread/reply关联已实现。补参使用0..365 ASCII整数，无bool/分数/重复字段/非法尾词/前导零，不自动补缺项。完整候选和待补项用确定性文本披露；标题是澄清编号，确认成功后才披露正式任务编号。不是审批按钮或B35事件。

## 持久范围与轮次

唯一前向0016新增`p4_clarification_requests`。当前候选可在该行保存partial参数、来源和递增round；每次变更须在immutable inbox/audit保留完整候选payload/hash/显式来源，旧round确认失效。稳定T1 request_key由服务端澄清UUID派生，不随round或客户端message key改变。

身份/原来源/目标workflow/source范围/create key/created_at/expires_at冻结。expiry为DB clock创建后固定15min，更新不延长；无最多3轮新产品限制，资源由既有event/window caps约束。过期不可复活，terminal consumed/expired不可覆写/开新轮；consumed所有重复确认只返回同一原Task，当前身份/权限仍须有效。每个request只消费一次。

0016仅扩现有replies的nullable v2 kind/request/round/frozen payload/hash及模板，v1原UUID/固定文本/原sent/unknown/dead保护保留。每个新reply仍1:1入站、provider UUIDv4持久，发送内容不可变。无新通用历史或draft平台，不修改原迁移，不应用于原known70；新测试库新增一表的56表与0016事实单列。

## 确认与 T1 原子性

在可信入站事务锁request，重核同org/shop/App/Tenant/chat、原principal/identity/initial auth_version、当前operator/shop scope、expiry、当前round/candidate hash和当前Gateway授权范围。他人/跨scope/重映射/撤权后恢复/旧round拒绝，无内容泄露与候选变化。重复物理event/message仍用原双层去重，语义冲突不覆盖。

只有完整显式参数的当前候选可确认。原`create_in_transaction`、稳定request_key、consumed/确认inbox及receipt同commit；事务失败全部回滚，commit后ACK丢失重放也只有一个T1。确认成功保持原T1一个formal workflow+一个source task+两jobs，不能错误要求确认jobs0。参数/读取阶段业务增量0，后续原审批/Graph/执行规则不改，不将确认当批准或补货完成。

## 发送及首包边界

v2仅显式选定request发送，不扫描全org pending。发送前再核当前真实身份/角色/App/Tenant/白名单/聊天、初始auth版本、request状态/轮次/候选hash及DB期限；旧pending问题失效则dead且0方法调用。沿用原单Worker与ledger/原UUID，持久sending后一次调用，unknown/dead不重发；新增轮次是新入站冻结的新载体，不复活旧unknown。

首包为迁移/窄grant、inbound/纯DTO文法/coordination/IM DTO、专项pure和新owned PG/Fake及事实文档。正式SDK child窄接线后续独审安排；本批真实Gateway/SDK/AppSecret/provider/IM/Base0。Web/Penpot/BaseRO/根lock/CI/Graph/审批状态机/原T1repository不改。

必要PG覆盖跨进程持久、补参业务零增量、confirm并发/重复同一T1、事务故障无半consumed、scope/role/revoke/expiry/旧round、v1兼容、v2唯一reply和unknown不重发、实际source hash及低权限。只新自有项目，事前登记固定deadline，每段累计≤20min并预留清理；普通stop/down不-v保卷，禁pg_diagnostic/force/prune/旧资源。三轮同源失败停止回传，不无限续。

首包6–8 Agent有效h、总F02 10–14h是原300h/P450h内计划估计，不是实际耗用；人工H/L not_reported/原D1/D30/18页保持。代码/真实结果/资源关闭/source冻结合批交原Core；不push/触CI/main/关Issue。

## 首包实际事实（2026-10-14）

已实施默认关闭的F02入站模式、单请求/原inbox与auth/hash来源重核、全轮candidate audit、严格补参/完整候选/显式确认及稳定server UUID派生T1 key。消费后重复确认返回同原Task，不新轮；确认成功原T1两Task/两jobs，补参/读取零业务增量。仅选定v2请求的原协调器与窄IM DTO已用Fake接线，正式Gateway/SDK child未启用或接线，不把本首包当真人能力完成。创建消息只报告创建回执，延迟发送不猜当前审批/执行状态。

作者87相关pure通过；收口完整1879offline/497integration排除/4warnings/105.16s，Ruff/424format/type316/Markdown104通过。首纯命令指定不存在文件0test保留；首完整1877pass/1fail是历史d97封存测试误把0016计入当时集合，仅排除后续0016并保留原文件/hash核验，定向33pass，再完整1878pass，文案收口后1879pass。未调用完整含在线audit的scripts.check，不宣称依赖在线漏洞查询已重跑。

全新project p4f02-f8ab7032b0固定UTC12:39:37.341835→12:59:37.341835、reserve75s。首23节点21pass/2fail（43.72s）：app读alembic_version和改expires_at被窄权限拒绝，非业务断言放宽；owner只核新库元数据、app拒expiry与owner触发器拒expiry分别保留后，23/23（43.95s）。末文案收口最新23/23（43.78s）=14新F02+9原v1，跨进程候选/真实confirm并发/同key重放、T1事务故障零半消费、各scope/初始auth撤权恢复/重映射/旧round、selected v2/stale0请求/unknown原UUID不重发、checkpoint0变更覆盖。新库实际0016/56表，app rolsuper/rolcreatedb/rolcreaterole均false；expiry用明确合成已过期fixture测DBclock拒绝，不称自然等待15min。

各次down不-v0，最终UTC12:51:44.401404容器0/网络0/保卷，原known70/原0015/55表0访问/升级。六产品模块+一测试的真实import路径/hash与host相等；0016实际执行前hash也捕获。提交前generic-api-key误报SQL request_key赋值，仅等价SQL换行、不改scanner；全部SQL去空白token流逐项相等，末PG后未再跑PG，该前后两个migration字节hash和等价证据分别保留，不伪称末PG用了换行后的hash。

旧a1864 Base wire/explicitRO/dispatcher/child/锁及private bridge均保持，本首包不解除其P1/HOLD；无新sealed runtime或正式SDK/Factory/AppSecret/provider/IM/Base请求。精确source候选、敏感三层扫描、import/SQL等价hash与owned closure在外置freeze合批，待原Core独审/精确CI；不push/main/关Issue，原预算/日期/人工H-L不重置。

## 正式运行装配源码候选（2026-10-14）

本接续批仍只源码/offline，未启真实Gateway/SDK。可信`BusinessSettings.f02_enabled`默认false，正式Gateway仅显式开启后向原入站store传递其已授权Gateway window ID。每个新F02 reply与原inbox/receipt同事务追加现有不可变audit的`reply_selected/f02_gateway_reply`，冻结实际request/reply/inbox/round/payload hash及org/shop/Gateway；重放不再插新选择。这里是原Gateway业务结果的持久交接，不接受平台输入自报的业务标识，也不新增表、角色、队列或调度器。

原受控parent增加显式`--worker-mode f02_clarification`，仍执行原spawn/截止/terminate/wait/reap/持久终止确认；默认workflow分支保持。F02 Worker window由Root可信准备，只需要runtime/Gateway window、org/shop、固定截止和method caps，不包含手工request/reply ID。它要求配置flag与window均开启、UTC剩余15..300秒、auth1/bot1/IM1..5，没有Base/其他方法；上限5是本运行窗口资源预算，不是产品最多轮次数。实际启动仍须原`--live`和`p4-controlled-test`、低权限runtime role。

child只持有原一个WorkerSession，用原Worker的maintenance，`dispatch_jobs=false`且不构造Graph/Base/业务runner。选择只读取该当前Gateway、该claim时间之后的明确选择audit；冻结首个request为本窗口唯一关联请求，后续只从该request的选择回执找pending/sending reply，不能扫描全org或换到另一请求。补参、确认各自在原Gateway事务生成新载体并自动进入同Worker维护；Factory只在首个合格reply后初始化一次，后续共用同一ledger/window预算。预算耗尽/unknown/窗口停止即停，不自动续窗。

每个选择在Secret/Factory之前和最终sending事务中复用同一权限/轮次/状态谓词，另核当前Gateway claim/终止、原不可变inbox/hash/发起人/初始auth、reply原inbox/回执、完整candidate唯一audit及逐参数来源、固定T1 key、当前scope和冻结payload hash/原UUID。只有同Gateway当前选定reply可recover/领取；stale或越权dead且IM0，sending孤儿unknown，ACK不明unknown终止且不重发。Factory preflight与最终IM之间若Gateway被关闭，发送阶段再次拒绝；已经执行的auth/bot必须分记，不能称总SDK0。

原补参/确认→原T1同事务、稳定key/两Task两jobs、审批/执行门槛未改；F02维护本身只发送通知，确认后产生的jobs仍留给后续原业务Worker授权，不能因此绕过Base HOLD执行Graph。本批没有私有桥接或现有运行元数据更新；产品源码变化使旧5b pin/镜像仅签旧版，后续由Root按新精确source准备。

新增runtime Fake检查覆盖实际原Worker循环、问题→完整参数→创建回执、同一Factory/lease、原provider UUID/冻结全文、无job claim/recovery/Graph/Base、来源/权限/hash拒绝、Gateway关闭与auth后终止、sending orphan、ACK unknown和重复入口、默认关闭/窄caps/原parent进入child。两项必要新PG用例代码追加在原F02 PG模块，覆盖同实际inbox/原T1/真实ledger的完整链和ACK unknown，但本批只collect，不将其写成通过；原14 F02节点保留，该模块现16节点、全PG原497加2为499。完整offline/静态/敏感扫描、精确源码/hash以本批冻结回执为准，独审/新精确CI/真人仍pending。
