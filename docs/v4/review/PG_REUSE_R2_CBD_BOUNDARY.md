# R2 PG证据与cbd候选复用边界审查

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_BOUNDARY_ONLY；FINAL_PG_PAIR_AND_IMAGE_RECONCILIATION_PENDING。** 可核收“R2精确运行证据+相同PG业务输入+候选独立工程检查”的分层说明；不能核收“cbd同SHA完整PG已运行”或“全部fingerprints相同”。本回执没有降低原strict pair Gate。

证据source R2 `c6abe0528f05b458331f270d758317c1d7b38843` / tree `73e987375e2b6a2f06ac5aabaaab1499d78207d0`；比较候选 `cbd1c4e31569bf84f065fd38dd18448d438f6225` / tree `68efd8feb282430e5eb950661bae07a19db6f0d9`。ROOT明确提供的 `.audit/v4-0/PG_REUSE.draft.json` SHA256为 `ead6f86f5d1ed0487f3f468c924656f6f58c3325c779be383d35553c7ba6e199`，本次只读核其69项：62个测试模块、1个probe conftest和6项Compose/helper/依赖配置，全部与两source Git原文相等且SHA256符合清单。draft仍不是最终pair回执；62模块是否恰覆盖最终实际collection，应在完整两线原件核收时再对full_node_ids证明，不能只凭草稿计数。

独立核14个LOCK_FILES，只有以下两项不同；其余12项文件字节完全相同：

| 路径 | R2 SHA256 | cbd SHA256 |
|---|---|---|
| scripts/gitleaks_rules.json | 1b70a08f8c8446e3ba207a6a5440c1ae94c315e251481b26367b7189c63be397 | 41c15ee2bcd34e4e7661ed77a1e1b4fcfb769e36c6ce411a09943ba85ee1a52f |
| .gitleaks.toml | c7d868bdbe91ff28d95801136bae0e2ec3bde9a53a3113ed363aae275909cfc1 | f15a4c2a47e74a9f14443da3de9b6ecda797c081f89f3ac51cba785a2607ccfe |

两项是已单独审查的精确扫描FP元数据，仍属于严格fingerprint，不可删除或改造成相同。原pg_ci_evidence与pg_diagnostic完整字节不变，SHA256依次 `379c302ca0e57163740a37f5bba2034aaf2f878ef3a2c96f9ec01f0bdbfb7b7d` / `5256f926724113f9cfb7efc138551492fd4a09f57b9ec530fa404fb0ba46dfe8`。backend/迁移/产品前端相同另见HTTP11独立字节回执；变更测试文件属于新HTTP/browser探针或扫描pure检查，没有修改原PG测试模块。源码配置相同不等于本次已核所有实际二进制hash；runtime/binaries仍须以两线原fingerprints核对。

原verify_pair仍同时比较source_sha/source_tree/完整fingerprints/full_node_ids摘要，要求两个scope的实际并集等于完整集合且交集0；main还将配对source/tree与checker实际HEAD核对。因此pair必须在R2精确checkout执行，不能在cbd运行后修改回执，也不能剔除两扫描文件来让不同fingerprint过关。候选的完整scripts.check负责验证候选扫描配置，不能补造一次候选PG配对。只有原R2双线全部结束、原严格pair成功及资源清理/实际镜像来源证据核收后，才能在交付表标R2 PG通过并单列复用理由。

ROOT当前报告existing568/568及G1三/G2六、phase3仍接续；本轮尚未接收完整两线/最终pair原件，故不独立签这些运行结果。新告知的phase3登记HTTP testimage与实际helper build产物不一致必须原样保留：登记值不能替换实际镜像；HTTP测试镜像与Full helper构建的db-init/pg-test不是同一执行证明。最终PG审查需核原helper构建路径、源/Compose/Dockerfile/ignore、实际image ID/架构及project labels、无host ports、时间与退出/清理，并把reconciliation标为解释登记差异而非原记录匹配。当前无实际inspect材料，不提前签image对应关系。

M3三flow live、Hosted、发布及未来HEAD均不由该复用边界关闭；待ROOT后续完整原件交付后另作实际PG核收。本轮没有运行PG、Docker或pair命令，没有更改R2/ROOT源码或任何Gate。
