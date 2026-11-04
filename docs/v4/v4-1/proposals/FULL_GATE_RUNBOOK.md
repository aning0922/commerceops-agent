# V4-1 完整工程与 FullPG 运行手册（待执行）

日期：2026-11-04（台北）。GATES 单 owner。当前状态为只读规划完成，所列命令尚未执行；本页不授权资源、网络、Hosted、外部业务、push 或重跑。实际监督脚本由 QA 实现，Root 在最终源码冻结后登记精确来源、工具、资源和绝对 UTC 窗口。

## 来源与证据分账

已核合同来源为 `84db1ba34120cac3b4fccb6bbe316d3efbca1659`，tree 为 `a938c6cec22b347370e477c6044cd7835560b341`。相对 V4-0 基线仅十一份文档变化；当时原工程和 PG helper 未变。后续 API/WEB/QA 代码候选以 Root 新冻结 SHA/tree 为准，不能以合同来源预签测试。

原工程运行绑定 `cbd1c4e31569bf84f065fd38dd18448d438f6225`，实际 native 0、1,389.861 秒，即 23 分 9.861 秒，开始/结束 UTC 为 2026-11-03T18:53:32.256265Z / 19:16:42.182434Z。原登记窗口 1,800 秒，实际余量 410.139 秒。来源为 [ENGINEERING_CBD.json](../../acceptance/v4-0/ENGINEERING_CBD.json)，完整 offline 为 4,316 PASS；敏感扫描、依赖安装与 audit 等完整步骤未删除。这是旧实际耗时，不是 V4-1 容量上限或 30 分钟必过保证。

原 R2 FullPG 来源 `c6abe0528f05b458331f270d758317c1d7b38843`，existing 实际 1,947.500 秒，phase3 为 1,684.853 秒，包含当次 helper 工作和 cleanup，见 [原 PG 配对回执](../../validation/R2_FULL_PG_PAIR_20261104.md)。旧 568+177=745 不固定为 V4-1 集合；每个新候选重新动态 collect，完整节点 hash 与实际分区必须重新核对。

## 完整工程：原生命令与监督契约

在新冻结 checkout、原敏感 Gate 和依赖/网络准入满足后，运行原命令：

```sh
.venv/bin/python -m scripts.check
```

QA 父监督器直接用参数数组调用该命令，cwd 为精确 checkout，使用已核环境键白名单和实际工具路径，不经 shell 拼接；私有 log 0600，目录 0700。PATH 优先该 checkout `.tools/node/bin`、`.venv/bin` 和冻结 uv。保持 Node 24.21.0、Python 3.12.13、uv 0.11.25、gitleaks 8.30.1 的实际版本和 binary hash；所有原 lock/input 指纹逐项记录。

原命令包含全 reachable-history 敏感扫描、`uv lock --check`、文档、Ruff、mypy、`npm ci --ignore-scripts`、toolchain/schema/契约、完整 offline、前端 typecheck、npm audit、uv export 与严格 pip-audit。完整工程阶段需要 npm/pip 真实漏洞查询；Root 未释放网络前仅准备，不把离线缓存模拟为漏洞查询通过。旧私配不得继承，原历史环境键仅作名称参考，不复制值。

Root 需要分别登记工程开始 UTC、绝对 stop UTC、终止/收尾预留以及整批预算。QA 根据单调时钟剩余量调用 `Popen(..., start_new_session=True)`，`wait(timeout=剩余量减预留)`；超时后在预留内 TERM、必要时 KILL、wait/reap 并核注册子进程退出。不能用阻塞读取日志替代 deadline，也不能在 timeout 后继续下一条 Gate。工程预留由 Root 单独批准，不机械借用 FullPG 的 75 秒。

监督器记录原命令实际 returncode（含 signal 非零）、timeout 标志、开始/结束 UTC、日志 hash 和源码前后状态；自身 supervisor native 另由父进程 wait 实测。summary 打印放在回执原子持久化后，打印异常独立记录并使外层非零；required checks 与 information 分离。回执存在、日志末行通过、检查通过而摘要失败，均不能推断外层零退出。失败原件保留，修正后仅由 Root 释放新精确窗口，不自动重试完整工程。

容量规划以旧 1,389.861 秒加新 offline/type/build/audit/历史增长开销及批准收尾余量为输入。新依赖、缓存或网络延迟均未测，不能预先保证 1,800 秒足够，也不能提前删除 audit 或减少节点来适配窗口。

## FullPG：双线命令与前置条件

Root 提供同 SHA/tree 的两个新独立 checkout；不得共用 `.audit/issue23-ci/round-1.json`，该文件存在会被原 helper 拒绝。分别登记新 owned subnet、image binding、project/资源 owner 与绝对 stop UTC。既有网络盘点只是快照，执行前重新核占用；PG 不映射宿主端口。

若获准真实构建 extension 镜像，在每个对应源码树使用原入口：

```sh
.venv/bin/python -m scripts.m3_pgvector --stop-at-utc "$V41_PREP_STOP_UTC"
```

该入口会真实 `docker build`，不能在只读准备阶段调用。它要求新 binding，准备预算为 `min(300, 截止剩余秒数减85)`。复用旧 PG 镜像需要 Root 核实际 ID、平台、六项 image inputs，并在新源码下批准新 binding；不得复制旧 receipt、伪造新 build 或重写原 image guard。

以下为待执行命令模板，变量只能来自 Root 此次登记；existing 和 phase3 在各自 checkout 执行：

```sh
# existing 独占 G1/G2 full smoke
.venv/bin/python -m scripts.pg_diagnostic \
  --session ci --round 1 --combined --ci-scope existing \
  --full-smoke --no-child-trace --m3-pgvector \
  --owned-subnet "$V41_EXISTING_SUBNET" --deadline "$V41_EXISTING_STOP_UTC"

# phase3 不认领 full smoke
.venv/bin/python -m scripts.pg_diagnostic \
  --session ci --round 1 --combined --ci-scope phase3 \
  --no-child-trace --m3-pgvector \
  --owned-subnet "$V41_PHASE3_SUBNET" --deadline "$V41_PHASE3_STOP_UTC"
```

两线结果完整后，在同一精确来源 checkout 配对；下列路径由 Root 替换为此次两条真实绝对路径：

```sh
.venv/bin/python -m scripts.pg_ci_evidence \
  /EXISTING_CHECKOUT/.audit/ci-evidence-existing.json \
  /PHASE3_CHECKOUT/.audit/ci-evidence-phase3.json
```

原 checker 同时核 source/tree、十四项 LOCK_FILES、四项 runtime/三项 binary 指纹、完整 collection/hash、selected=actual=passed、模块覆盖、actual 并集完整且交集 0、G1/G2、cleanup 0 和 stopping confirmed。checker 自身 HEAD/tree 必须匹配，旧证据不得换来源标签。

G1 保留 verify-restart、verify-recreate、verify-unavailable 三项；unavailable 的预期非零命令与实际 native 原样分记。G2 为原五项 required 场景加 retired-probe 负例共六项；phase3 不重复认领 smoke。

## FullPG 容量、分组与清理

原每命令 300 秒、collection 30 秒、到绝对截止前 75 秒停止业务命令、cleanup 至多 60 秒合同保持。旧两线耗时不包括未来新增测试或单独 extension 准备，不是上限；Root 按新动态分组与实测新增开销分别给窗口，不共享短窗后续期。

新 V4-1 integration 若不属于既有 P3/P4/P5/M3 模块族，会进入 existing 的 `combined-existing`，共享该组 300 秒，不能把新文件误算成独立 300 秒预算。发现容量不足须保存未跑节点与各组耗时，Root 审核最小分组候选后才变更；本 owner 不修改原 helper、partition 或时限。

原 helper finally 写出报告和 safe evidence 后仍可能退出 1；监督器必须 wait 实际进程。原 owned 临时 PG cleanup 使用 `down --volumes --remove-orphans --rmi local`，仅限原登记临时资源；其他窗口的保卷合同、未知资源和旧私有卷不得套用。最后独立核精确标签的容器/网络/卷、端口和注册 PID；缺日志、非零、未确认停止或 UNKNOWN 均保留，不能由 cleanup 最后一行猜成功。

## 0025 current-head 断言：API 唯一 owner 清单

以下是合同来源时的具体兼容点；API 唯一 owner 在实际 0025 表名/ACL/revision 冻结后同步，QA 只消费/验证，不抢写。不要全局替换所有 0024 引用。当前读取位置仅供定位，以最终 diff 为准。

| 文件/节点 | 当前断言与需核定更新 |
| --- | --- |
| `tests/test_postgres.py::test_revision_and_schema` | 当前 head 精确 revision 为 0024；business 全表集合精确相等。更新为真实 0025 revision 和精确新增表，不改 public 空集、PG 版本或其他完整集合保护 |
| `tests/test_p4_history_pg.py::test_0016_upgrade_preserves_original_rows_payload_and_unknown_attempt` | 只在历史步骤之后 `migrate(owner)` 的 current-head 段更新新增表差集、所有新增表为空及精确 head revision；旧行/checkpoint bytes 相等、低权读取与原 payload/once 保护保持；0016→0017 原历史段不削弱 |
| `tests/test_p4_first_create_negatives_pg.py::test_forward_0012_upgrade_preserves_original_c0_rows_and_checkpoint_bytes` | current-head 新增表集合、空表清单、精确 revision、诊断 `current_head` 和 `new_tables_empty=36` 随实际新增表同步；原 0012→0013 与 legacy C0 拒绝、字节保全和 grants 保护保持 |
| `tests/test_p4_read_reply_pg.py` 的当前 revision 分支 | 约 284—292 行闭集列到 0024；加入真实 0025 后继续执行 history 不可改/保护断言，避免新 head 静默绕过该分支 |
| `tests/test_p4_f02_pg.py::test_persistent_partial_cross_process_round_history_and_zero_business_until_confirm` | 约 177 行精确 head revision 更新；确认前零业务增量、持久历史和回放保护不减 |
| `tests/test_p5_m2_backup_pg.py::test_current_m3_head_is_not_an_m2_backup_schema` | 两处 current-head revision 更新，仍拒绝 M2 snapshot 并保持只读；独立 0018 fixture、60 表及 M2 精确合同不改 |
| `tests/test_p4_migration_diagnostic.py::test_last_test_stages_cleanup_and_original_failures_with_fake_only` | 与上述 current-head SQL 快照对应的 Fake 新增表、空表集合和最终 revision 同步；历史 0013 分支和失败分类保持。该文件固定 d97 closure/hash 隔离测试不能顺带重写 |

`tests/v4/test_demo_seed_contract.py` 及 `tests/e2e/v4/migration_diagnostic.py` 等含 0024 路径的旧 V4-0 固定来源不自动改成 0025。若 Root 要求把其中工具用于新 head，须先限定复用范围并单独审查；原件与来源 hash 保留。新增 0025 低权 DDL/DML、锁序、迁移失败回滚和业务验收由 API/QA 的新测试证明，本清单不代签。

本页提交前只做文档、差异和显式 changed-file 的 current/index 原生预检；未重跑全历史、完整工程、collection 或资源。完成后将精确提交交 Root，最终源码冻结前不启动任何待执行命令。
