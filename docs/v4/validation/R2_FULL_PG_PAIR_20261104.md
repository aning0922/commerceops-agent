# V4 R2 本地完整 PG 配对回执

记录日期：2026-11-04（台北）。本页记录新 owned 本地 PG 两线的实际运行和配对结果，由 SCHEMA/API owner 交 Root 核收。结论仅为 `PASS_EXACT_R2_PG_PAIR`，不代签完整工程、HTTP、浏览器、Hosted、amd64、人工验收、main 或发布。

## 精确来源与配对

两线测试源码均为 `c6abe0528f05b458331f270d758317c1d7b38843`，tree 为 `73e987375e2b6a2f06ac5aabaaab1499d78207d0`。配对命令也在该精确 checkout 运行，native exit 0，用时 0.085 秒。

| 项目 | existing | phase3 |
| --- | --- | --- |
| 全集动态 collect | 745 | 745 |
| selected / actual / passed | 568 / 568 / 568 | 177 / 177 / 177 |
| 原 helper 分组 | 24，全部 exit 0 | 18，全部 exit 0 |
| helper native exit | 0 | 0 |
| wrapper 实际用时（秒） | 1947.500 | 1684.853 |
| 开始 UTC | 2026-11-03T18:26:01.884386Z | 2026-11-03T19:01:15.459856Z |
| 结束 UTC | 2026-11-03T18:58:26.504460Z | 2026-11-03T19:29:20.312459Z |
| cleanup exit / stopping confirmed | 0 / true | 0 / true |
| cleanup 用时（秒） | 5.227 | 4.870 |
| project | `p123-a68a4a7f99a9` | `p123-54f804675b46` |
| owned subnet | `10.242.33.0/24` | `10.242.34.0/24` |

实际并集为 745、交集为 0。两线 SHA、tree、工具和锁文件指纹、完整 collection hash 均相等；完整节点 hash 为 `d1311c12dd85f55aa8bb32b27bfae736677bb8fa345798833c70c36af9aefe3f`。原 `scripts.pg_ci_evidence` 检查了每组 expected = actual = passed、分区完整性、G1/G2 和 cleanup，未修改其规则。

工具版本为 Python 3.12.13、uv 0.11.25、Node v24.21.0、gitleaks 8.30.1；两线使用相同锁文件及二进制指纹。每条原命令 300 秒、原分组、75 秒 reserve 和 60 秒 cleanup 合同保持。phase3 没有开启 full-smoke，也没有续窗、重启或重试。

## G1/G2 与资源清理

existing 的 G1 complete 为 true，verified count 为 3。G1 `unavailable` 命令按原负例合同实际 exit 1、timed_out false、stopping confirmed true；不能把这一预期非零命令写成所有命令均零退出。

existing 的 G2 实际六项为：

- `checkpoint_db_failure_recovered`
- `cross_process_resume`
- `graph_lock_loss_cancel`
- `graph_noncooperative_exit`
- `receipt_commit_checkpoint_gap`
- `retired_probe_version_refused`

phase3 的 G1 complete 为 false、verified count 为 0、G2 为 `[]`，不重复认领 existing smoke。

两线结束后均按精确 compose project label 独立查询容器、网络和卷，结果均为空；已登记临时卷 inspect exit 1，helper PID 均已退出。phase3 独立 inventory 记录时间为 2026-11-03T19:30:10Z。原 helper 的 owned cleanup 保持 `down --volumes --remove-orphans --rmi local`，仅本批临时卷被移除；不据此处理未知资源或旧私有卷。

## 镜像来源与差异保留

两线 PG 均复用 F1 已构建 extension 镜像，没有重建或 retag：

- 镜像标签：`commerceops-m3-pgvector:8ee1df0-v1`
- owned alias：`commerceops-v4-pg-frozen:047a43d`
- 实际 ID：`sha256:bb26ccd46218e47cd66abecb2fc6ea36f3815584743b60e9b9eb9f7c1072d91f`
- 平台：Linux arm64；PG 17.11 / vector 0.8.7
- 六项 image input hash 与已核绑定一致；各 R2 checkout 新建绑定明确标记 `REUSE_F1_BUILT_EXTENSION_NOT_NEW_BUILD`。

phase3 初次 runtime 元数据核对曾将 Root HTTP 自定义 test image `sha256:8c7dd760e679d45090bccbadc940d1d640ee6aeb450e1caea718d2176b6970e5` 与原 PG helper 的 canonical pg-test image 比较，断言失败。该失败属于元数据核对，未作为 pytest 业务失败；原差异回执保留。

Root 随后明确核定两类 test image 不同，允许原 helper 按当前 R2 源码执行原 `compose build db-init pg-test` 并继续同一运行；没有重启、重试或延长窗口。phase3 canonical pg-test 实际 ID 为 `sha256:d132a2041454e3adf48c7d904a7e725d4836ac04a054f0f13c246b296fa9246d`，原 build native exit 0。精确源码、Dockerfile、dockerignore、Compose、helper hash、容器 service label、无宿主 PG 端口及实际 PG ID 已写入独立 reconciliation。

existing 线 canonical pg-test image ID 为 `NOT_CAPTURED_NO_BACKFILL`，不借 phase3 的 ID 回填。结束后的两个 PG 标签仍指向上述 bb26 镜像。此前另一 HTTP PG 镜像消失的原因仍为 UNKNOWN，本页不归因为 helper cleanup。

## F1 失败和最小修正

F1 源码 `047a43dafef90edea2eb532c2a03b6f850da0b9a` / tree `5c0699edb2d30889ce770ca9b05b56dab957ce10` 的 existing 结果仍为 native exit 1：568 selected、556 actual、555 PASS、1 FAIL、12 NOT_RUN；G1 未运行，G2 六项和成功 cleanup 分列保留。失败节点为 `tests/test_p4_history_pg.py::test_0016_upgrade_preserves_original_rows_payload_and_unknown_attempt`，call 4.217 秒；原运行 `--tb=no`，实际失败 assertion 行为 `NOT_CAPTURED`。

静态核对发现当前 head 的精确新增表集合和空表列表未包含十张 V4 表。授权修正提交 `8ef54543aa0d32ba2caff4701650fcac1f03c208` 仅在该测试新增二十行表名；历史 0016→0017 段字节保持，未修改生产迁移、业务、断言强度、超时或分组。Root 将其合入 R2。R2 另行目标节点运行为 1 PASS，随后才有本页两线完整结果；这些新结果不回填 F1 的失败 assertion 行或未运行节点。

## 本地证据定位

以下均为实际 owned 工作树中的本地文件，未提交 `.audit`、private log 或凭据。existing 的单线回执在其记录时点写有 phase3/pair NOT_RUN，该原件保持；本次配对以新 `full-pair-result.safe.json` 为准。

existing 根目录：

```text
/Users/aipuli/.codex/worktrees/commerceops-v4-pg-existing-r2-20261104-c6abe05/commerceops-agent/.audit/
```

- `ci-evidence-existing.json`
- `full-existing-result.safe.json`
- `full-existing-native.safe.json`
- `full-existing-inventory.safe.json`
- `full-existing-runtime-bind.safe.json`
- `image-reuse.safe.json`
- `issue23-ci/round-1.json`

phase3 根目录：

```text
/Users/aipuli/.codex/worktrees/commerceops-v4-pg-phase3-r2-20261104-c6abe05/commerceops-agent/.audit/
```

- `ci-evidence-phase3.json`
- `full-phase3-result.safe.json`
- `full-phase3-native.safe.json`
- `full-phase3-inventory.safe.json`
- `full-pair-result.safe.json`
- `full-phase3-image-discrepancy.safe.json`
- `reconciliation.safe.json`
- `image-reuse.safe.json`
- `issue23-ci/round-1.json`

F1 原件根目录：

```text
/Users/aipuli/.codex/worktrees/commerceops-v4-pg-existing-20261104-047a43d/commerceops-agent/.audit/
```

其中 `full-existing-result.safe.json`、native、inventory、CI artifact 和原 log 均保留。R2 目标节点独立回执位于 `commerceops-v4-pg-target-20261104-c6abe05/commerceops-agent/.audit/head-target-result.safe.json`，与完整两线分别记账。

本页提交自身是事实文档提交，不是被测 R2 源码 SHA；不得将其或后续集成 HEAD 自动视为已有同 SHA 完整 PG 证据。后续工程、HTTP、浏览器和发布状态由各自实际回执及 Root 核收记录确定。
