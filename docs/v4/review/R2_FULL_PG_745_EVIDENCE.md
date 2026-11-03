# R2完整双线PG745实际证据独立核收

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_LOCAL_EXACT_R2_FULL_PG_745_WITH_PROVENANCE_LIMIT。** 原R2完整双线、严格配对与清理可核收；镜像登记偏差及existing测试镜像ID未捕获保留。不是Hosted，也不把结果改签最终HEAD。

受测source `c6abe0528f05b458331f270d758317c1d7b38843` / tree `73e987375e2b6a2f06ac5aabaaab1499d78207d0`。原件位于 `/Users/aipuli/.codex/worktrees/commerceops-v4-pg-existing-r2-20261104-c6abe05/commerceops-agent/.audit` 与对应 `commerceops-v4-pg-phase3-r2-20261104-c6abe05` tree的.audit。本次只读各native/result/inventory、ci-evidence、round-1及镜像safe记录；未读取私有log、未运行PG/测试/Docker或CLI配对。

## 完整集合与原生终态

| scope | selected/actual/passed | 原分组 | 原helper native | 外层elapsed秒 | cleanup秒 |
|---|---:|---:|---:|---:|---:|
| existing | 568/568/568 | 24 | 0 | 1947.500 | 5.227 |
| phase3 | 177/177/177 | 18 | 0 | 1684.853 | 4.870 |

两线full_node_ids完全相同且为规范唯一745项，摘要 `d1311c12dd85f55aa8bb32b27bfae736677bb8fa345798833c70c36af9aefe3f`。独立核并集745、交集0；每组expected/actual/passed集合完全相同、native0、result true，分组label符合原combined_groups。不是把部分pass或两个不同collection直接相加。

从精确R2 Git快照只加载原纯metadata函数，verify_pair对两份已存在artifact校验通过；分别由原safe_report对原round-1与原metadata重建，产物逐对象等于各安全artifact。没有修改source/hash/field再喂校验。14个LOCK_FILES逐项hash等于R2 Git原文，两线runtime与binary完整字典相同；runtime为Python3.12.13/uv0.11.25/Node24.21.0/gitleaks8.30.1，三个binary hash另与现有对应工具文件核同。

Backend原 `full-pair-result.safe.json` 已出现：在phase3的精确R2 checkout运行原scripts.pg_ci_evidence，native0/0.085秒，stdout为原严格配对成功信息，source/tree/集合hash吻合。两个runtime tree读取时HEAD均R2。此原CLI运行与本次独立纯校验分记，不谎称reviewer重跑了CLI或业务测试。

## G1/G2与失败语义

existing原G1三条verified记录均count_one=true，另保留fixture committed阶段记录；g1_complete=true。G2六种原实际证据齐：cross_process_resume、receipt_commit_checkpoint_gap、graph_lock_loss_cancel、graph_noncooperative_exit、checkpoint_db_failure_recovered、retired_probe_version_refused。全部source_mode为postgres_technical、model not_used、approval simulated，不冒真人或模型实测。phase3不宣称G1/G2，原artifact对应false/0/空数组。

所有原command_end均未timeout、stopping_confirmed=true、sample_error=false。existing唯一非0命令是原G1 unavailable负例exit1，按原合同为预期；phase3无非0命令。两外层watchdog_actions为空、retry_allowed=false，均在原helper deadline前自然退出，不使用延窗或重试拼证。旧F1 555pass/1fail/12notrun、G1未跑和具体assertline NOT_CAPTURED全部保留；新R2不回写旧失败。

## 资源清理

两线cleanup_exit0/stopping_confirmed=true，原cleanup owned容器分别核33/移除33及核23/移除23。独立inventory显示各自project的containers/networks/volumes为空、helper已退出；registered volume检查为不存在（inspect非0为该缺失事实）。这里是canonical临时PG helper清理卷，**不称保留PG测试卷**，也不扩大为全机Docker0。两条PG镜像tag及冻结alias仍指向原bb26镜像；HTTP/browser/TTL保卷是另一组合同。

## 实际镜像与登记差异

两原m3 binding均为PG镜像 `sha256:bb26ccd46218e47cd66abecb2fc6ea36f3815584743b60e9b9eb9f7c1072d91f`，六输入hash逐项等于R2源码，原validate_binding/prepared_image通过；两raw round-1中的m3 binding与安全原件一致。existing运行时PG inspect记录同project、该镜像、无host ports和10.242.33子网；phase3对应10.242.34。

phase3原登记HTTP自定义测试镜像与实际canonical pg-test镜像不同，discrepancy原件未改写。实际测试镜像 `sha256:d132a2041454e3adf48c7d904a7e725d4836ac04a054f0f13c246b296fa9246d`，arm64/Linux；原多个pg-test容器均同project/service、该ID且无host ports。reconciliation保存ROOT明确允许原canonical build继续、不重启/重试/延窗的解释。

独立核原helper固定build db-init/pg-test、Compose目标、Dockerfile的runtime/test阶段和dockerignore；reconciliation的五个源码hash等于R2 Git对象，所引build command_end原记录逐对象存在于round-1且native0。测试镜像created时间早于本轮build结束可与构建缓存一致，不据此捏造新image创建。**existing线canonical test image ID为NOT_CAPTURED_NO_BACKFILL**；不能用phase3的d132反填existing，也不称两线实际test image ID已证明相同。原strict fingerprint绑定源码/工具/锁而不含此镜像ID，所以此缺失作为额外provenance限制保留，不伪造一致值来获得pair通过。

## 复用与后续边界

原full745对应62个PG测试模块，独立从node IDs提取完整集合，全部属于已核PG_REUSE69输入清单，关闭此前“62计数是否覆盖实际collection”的待核点。最终cbd对R2仍有两个scanner LOCK_FILES不同；原pair只签R2。可配合已核业务/PG输入字节不变及cbd完整工程检查分层复用，不写成最终HEAD同SHA完整PG运行。最终交付文档/阶段结论另审，M3三flow live、GC、manual、Hosted、外部provider均不由本PG结果代签。

关键SHA256：existing artifact `afd349ed5dfab5c43ff0d83169c68bfda57b34f783816b2823f17e5f0ea4b7d5`，raw `ce26725fe2d83cab5e949f1cf4974482140847d8cc2481d76c337cf55fce514d`；phase3 artifact `3ef265ba14c847078bbe8c7944d52c3aa2a1c85faa4b64745a400e149d4e815b`，raw `8efd1e5b4e3780c82ccd85a4c9664a98eb479d764a100f3535f8fe7080e0351c`；原pair `4acd2c9c93048069d4088ff49dd6241b5d7fcf4f63fc06048610412f4afb1e03`；reconciliation `73b2c3b5af639f7adbc23c51e4eaf34f7fc9cd2c2d44edefd365d2d8a24616ca`。
