# 8835892 诊断读取有界性审查更正

2026-11-04（台北）。更新结论：`P2_DIAGNOSTIC_READ_BUDGET_HOLD`。收回原REVIEW_8835892.md中的NO_OPEN_P1_P2及可释放Hosted判断；原报告SHA256 643e738138fb656f0797373d33de56129a3fda1627b1d74b1d70cdc5ba4295d4保留不改。该收回仅针对新增诊断读取的有界性，其他已核代码事实仍有效。

具体问题：883的read_private_log使用无上限stream.read；prepare_image finally解析日志后又分别读取同日志计算hash，且未对诊断处理复核绝对截止/75秒预留。因此新路径的输入大小、内存和处理用时不受限，可能侵占原预留。此前独审接受该部分不足，不能以固定Dockerfile通常输出少为依据签严格有界。

Root已转唯一API owner窄修：每份日志8MiB、fd fstat和read(limit+1)共同防超限及增长；一次读取bytes复用于解析/hash；超限固定LOG_TOO_LARGE、不冒完整hash、不输出raw；诊断最多5秒且不侵占原75秒reserve，预算不足跳读；保留原build native exit/timeout/reaped，不续窗或重试。仅必要纯测试，不追加本机构建、PG、完整测试或CI。

原0700/0600、独占/no-follow/owner、source/arch guard、300/85/75、TERM-KILL-reap、正式receipt字段及Dockerfile原命令的核对结果继续保留。新的候选须精确冻结后复审才可解除本HOLD。第三轮Hosted尚未由本审释放，旧失败和根因UNKNOWN不改。
