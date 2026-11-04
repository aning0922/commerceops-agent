# fbb29a4 组合离线影响检查原件独立核收

2026-11-04（台北）。结论：`ACCEPTED_BOUNDED_OFFLINE_IMPACT_EVIDENCE`。本次核收已有运行原件，没有重跑测试或资源。精确源码 `fbb29a429b7f680328ab4451a717adb3ad2d99c1`，tree `ef6d8230ac4b58401af2771d722064aadacc5eed`；来源 worktree 为 `/Users/aipuli/.codex/worktrees/commerceops-v41-combination-check-r1/commerceops-agent`，原件目录为其 `.audit/v4-1/combination-check-r1/`。记录窗口 UTC 2026-11-04 10:04:08.454969–10:04:46.262771，总 elapsed 37.807219291 秒。该结论只签这次组合离线影响检查，不是新 SHA 的 Full 或 FullPG。

## 原件、命令与实际输出

独立计算 delivery.safe.json SHA-256 `2c0aaae41467f4719acd09737c3be3ff77d41e0963388fe9de271e9bb3f0d9f0`、result.safe.json `5e430f15ad2574f18612a2243cafe0230bcbc9c8be99351f008dd1ed8bb000f7`，与 Root 指定值一致。delivery 引用的全部六件 artifact hash 均逐一匹配；八步原 stdout/stderr 字节均匹配 result 中摘要。before/after 原文件逐字节相同，SHA-256 均为 `ebd84006a8121e3de6ff1f4b7d986a2cee6dbcddd0fd65f443df27d2e979f17c`。run_checks.py 摘要为 `4a7b20290eaa627dd2510ae3995b1d6e05baf164df89a0d5f7383cbc1e260bf2`；已读脚本和逐步原 argv，记录的是 subprocess.run 返回码，非仅汇总文字。

| 实际步骤 | 命令范围及原件核验 | 结果层级 |
| --- | --- | --- |
| import-origin | 本 WT Python 导入 commerceops/browser_shell；断言 backend/src、模块位置及 sys.prefix 均属本 WT | native exit 0，输出 NEW_OWNED_SOURCE_AND_VENV_CONFIRMED |
| Python offline | `pytest tests/e2e/v41 -m 'not integration and not external' -q --junitxml=…/python.xml` | native exit 0；189 passed，0 failures/errors/skipped |
| Node pure | 固定 Node `--test`，19 个显式 v41-tests/*.test.mjs 路径 | native exit 0；74 tests/pass，fail/cancelled/skipped/todo 均 0 |
| TypeScript | 本 WT typescript/bin/tsc，frontend/tsconfig.json，noEmit、incremental false | native exit 0，stdout/stderr 空 |
| Ruff | check 两个 browser_shell.py/test_browser_shell.py | native exit 0，All checks passed |
| Ruff format | 同两文件，format --check | native exit 0，2 files already formatted |
| mypy | 同两文件，follow-imports=silent、no-incremental、私有 cache-dir | native exit 0，2 source files 无问题 |
| React Mock collect | 固定 playwright/cli.js，原 frontend/playwright.v41.config.ts，`--list --reporter=json` | native exit 0；33 项收集，测试体执行 0 |

独立解析 JUnit 得 189 个 testcase、20 个模块，其中 test_browser_shell 72 项；不是仅信 counts 字段。JUnit hash 为 `6a5dd404b575936ed7609a054f56baa8a6b1c92cadade0533f5de6014c91322c`，stdout 明示 189 passed in 18.10s，命令外层记录 19.858436667 秒，两种口径分列。Node 原 stdout 的 74 个通过条目及末尾汇总一致，包含三处 stripTypeScriptTypes ExperimentalWarning；八个原 stderr 文件均为空，但不能因此称无警告。

原 Mock JSON 的 33 项 tests.results 全为空，errors 空；按文件为 batch-tags 9、import-flow 2、lifecycle 19、shell 3。mock-collected.safe.json 的 33 个条目与原 JSON 一致，hash `0ce643f27c0f458adb1ee6f7c4a7eca718b4d70ee600a1b393ed56aac8213109`。`--list` 证明发现与加载，不证明 React 测试执行成功；live 两个 spec 的 collect 仍 `NOT_RUN_PENDING_ROOT_MANIFEST`，不能与此 Mock 收集混同。

## 源码、工具与依赖绑定

独立只执行脚本中的只读 fingerprint 函数，重新读取当前 tracked 文件、工具和依赖字节；没有调用 run_checks 的测试循环。所得当前 fingerprint 与 before/after 完全相等：1844 个 tracked 文件，汇总 `ce4834f16de6304973ab707bba77a8b6046f2ea433fe991086498850674d8e58`，同 source/tree、git diff HEAD 为空；三个锁/配置摘要及工具字节不变。Native 模块与 TS caller、Python 父 pin 也独立核为同一 `295bf2c61e7cd30e7a47d7368d93fbadb40764fb41072a9119b5d78ed925689e`。

Node SHA-256 为 `e4b5a3af0e05c75de2eae013904145f40fe7fc2a6e6f17510128bf45cca4e79b`；Python 实体为固定 uv CPython 3.12.13，hash `a395f264e5612a2819662ed3e37fd30d39ed61179b98e5f86c3c783a008d8623`，解释器实体在公共 uv 位置，sys.prefix 为本 WT 的 .venv。Ruff hash `70e977860c228661a4992c9558b8350903351845fa945715584f4c176a0f6c61`。python site-packages 29700 entries/hash `788b76a6277fbaeda6a55a583a4c9d73722232768a0f18a057294b651fbbc396`；frontend node_modules 12178 entries/hash `f6ab42b654b33dcadab64a3283748b2c83baedb5854170d895894110e3789a80`。本次按同算法独立重算这些摘要一致。

本 WT .venv、site-packages、node_modules 均为 canonical 本地目录，不是指向作者 WT 的目录 symlink；两个依赖树内也未发现 symlink。site-packages 唯一 .pth 为 `_virtualenv.pth` 的 `import _virtualenv`，没有指向旧源码的 editable path。运行脚本清理继承环境，只保留基本系统字段，显式设置本 WT backend/src 与根目录 PYTHONPATH、本 WT Node/Python PATH、PYTHONDONTWRITEBYTECODE；Mock collect 单独设置 loopback origin，仅用于收集。导入断言已在实际运行中通过。依赖准备方式按原件记为 OWNED_APFS_COPIES_NO_INSTALL；本复核证明当前隔离目录与执行前后字节一致，不另声称从文件元数据证明 APFS 克隆过程或重做依赖安装/锁一致性审计。

## 核收范围

八个步骤均有原 native exit 0 和对应输出，脚本对首个非零/timeout 停止并最终比较 source/dependency 指纹；本次没有该类失败。此核收不转移历史 4601 Full 或 773 FullPG 到 fbb29a4：两项均 NOT_REEXECUTED。React Mock 实际执行、live 两 spec 收集/执行、PG、浏览器、Native 200%、视觉、服务与整链清理不由本包证明；原件将服务/PG/browser/network/install 标为 NOT_RUN，本轮也没有重跑或启动这些动作。只读 hash/JSON/XML/log 核验不充作新的运行窗或阶段完成授权，后续 Mock 实际结果另核。
