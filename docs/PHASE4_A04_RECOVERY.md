# A04首轮新PG失败与测试最小修复

Root已核精确c31离线独审noP1/P2/98pure3.23s，新PG只collect；释放唯一自有30min实际窗。p4a04-99e294e1c082/P4-A04-WTfd38从UTC2026-10-11T06:12:44.376683开始，原绝对截止06:42:44.376683，最多两轮，不延期/不复位。COPY精确c31/244 Python manifest，SDK/平台/provider0，无hostport，0011初始化migrate/checkpointer/grant/revision各exit0。

首完整target collection39=21gateway+9clarification+5Base+2IM+1SDKledger+schema1。实际37passed/2failed，command111.372s/JUnit39、fail2/error0/skip0/suite107.904s，plugin完整phase与JUnit保留，不将partial计通过。停止exit0/全falsePID0/保卷，尚未down等原窗口有界复验。初次本地collect误写不存在test_database_pg路径exit4/0collected/0PG；更正为既有test_postgres后39collected，保留该负证据。

新增IM False节点CARD_CONTEXT_MISMATCH：Fake sender先记调用，原Worker的ACK+binding事务仍未提交，测试随即模拟callback，合法间隙正确拒绝。只补原p4_im_deliveries状态sent（unknown节点为unknown）持久屏障；终态result同样等sent，再读完整状态。维持原message/chat/nonce/version和唯一execution/binding断言，不改backend与审批条件、不假sleep已经送达。

新增SDKledger节点DELETE被低权commerceops_app以InsufficientPrivilege先拒绝，原测试错误期待CheckViolation。只拆成同一node内两层事实：runtime删除必须拒绝；owner删除仍由不可变触发器CheckViolation拒绝。不增加DELETE grant、不放宽原cap、不删账本。

最小修复仅两新PG测试+本文普通提交，Factory认证/bot/0012尚为独立未提交WIP，不能进入此修复的COPY镜像。Root精确复审后同原截止内最多第二轮全部39，不把旧c31独审替换成新测试审，不提前填通过。若失败/unknown/截止即停止相关包、保原JUnit/资源，不启动第三轮或新窗口。
