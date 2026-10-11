# P4 固定澄清窄意图与补证窗口（A02候选）

Root已纠正“澄清零写”：合法operator应得到异步固定回复，零的是inventory/P3 task、report、plan、approval、execution、item/Base及job，允许仅inbox、原回执、唯一reply。不能调用P2 create_intent_task或模型路由，不建设跨轮会话。初版A01的CLARIFICATION_REQUIRED无固定通知为历史候选，A02据本合同补齐。

## 1. 收件与原键

认证/当前role/shop先于语义分类；支持完整库存分析请求才进入既有T1。其他缺参数/歧义输入只同事务写入inbox和p4_inbox_receipts及1:1 p4_clarification_replies，原provider_uuid=UUIDv4、固定template_version/p4-clarification-v1与reason_code。不保存原输入全文、不让模型生成回复。重投原event/message只返原reply，无第二UUID或业务对象。补参数必须新完整请求/new message键，产生全新T1，不关联续答或继承旧plan/nonce。

## 2. 唯一Worker发送

ClarificationDeliveryStore只作为既有单Worker的reconcile步骤，无独立消费者。发送前复核原identity映射/当前principal与operator/shop grant、当前allowlist/app/tenant及原群范围；无权无回复。短事务先持久sending/attempt=1/原UUID/first_attempt_at/claimed_by，网络不持业务事务；明确SDK ACK+message_id才sent。超时/未知/发送后commit丢失以unknown保留，恢复先经旧PID死亡确认，由唯一新Worker将旧sending转unknown。unknown任何年龄均不自动重发（涵盖>1h），不换键、不回pending，不产生业务任务。

当前sender默认disabled，测试controlled_sender仅离线Fake transport；真实SDK调用/准入/固定窗口另经Root审后受限资源包，本候选不启用真实平台。旧P3/probe/outbox约束不修改。

## 3. 新有界自有PG补证范围

Root已允许Core释放自身network后A02登记新owned固定窗口。建议20min（启动登记时绝对UTC截止不重置），全新project/network/volume/owner+app0600、无hostport，无旧secret/env/DB/平台/provider调用。

执行冻结后保存完整Junit/现有diagnostic plugin expected/actual/call counts、源文件hash/镜像digest/命令耗时/低权限flags/stop回执，避免旧独审只有collect+exit0的证据缺项。范围：澄清p2p/group去重/零业务/补全新T1/原UUID/send/unknown/撤权/无权、现有21P4 Gateway/API全回归、schema/migration精确新表集合；必要性能驱动100入站+20预定baseline样本（金标完整、无warmup排除）与真实PG官方pendinginterrupt idle/busy补证。

20样本固定标签p4-baseline-01～20，fixture inventory-v1/baseline、完整report/state completed/单SKU/source_complete/全部goldens.baseline字段精确匹配。idle先持久before_ready CP→kill/reap旧child→显式termination confirmation，再新Worker实际repair；busy在同单Worker真实等待CP持久后有界延后ready，下一扫描点修复。代码/fixture/角色不在跑测中修改，余量不足停相关包并保留partial，不延长窗口或降低Gate。

## 4. 当前待核

迁移0009、窄存储/协议/定向测试及性能补证已完成作者30PG/56.65s及另1真实Worker维护PG/6.84s；100入站、预定20完整gold分析、真实pending idle/busy补证与低权flags/stop/network保卷均见[完整分层回执](../PHASE4_A02.md)及[安全摘要](p4-a02-author-evidence.json)。初始217源码hash/COPY镜像与后续SDK/renderer/entrypoint补充证据分层，不冒称后加代码进入早期30镜像；完整plugin保存，临时JUnit未保存，不伪称已留XML。

A02本地冻结/独审/精确新CI仍待。A01=545独审源码无P1/P2，原CI frontend生成schema同步失败保持；C610新CI38111683908原approval模块300秒超时/27callpass+1未结束、real read批failure且具体nodeunknown，Root裁决前不重跑/取消/开新PG。C修复审后才普通merge，A02不提前push。真实formal sender/Base/完整四组Web读DTO、20卡runtime、cleanCompose/human窗口仍按后续Root门槛，不以澄清或纯renderer替代主业务闭环。
