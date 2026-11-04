# 261f399 最终组合离线影响检查原件独立核收

2026-11-04（台北）。结论：`ACCEPTED_BOUNDED_OFFLINE_COMBINATION_EVIDENCE`。精确 source `261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e`，tree `34da95131e04d7360ea8aa5250ea40215bcb0713`。本次只读核收原件，没有重跑测试/Full、启动服务/PG/浏览器或运行新 probe。结果属于此组合源码的离线影响检查，不是旧 Full 4601 或 FullPG 773 在新 SHA 的重跑证明。

原件位于 `/Users/aipuli/.codex/worktrees/commerceops-v41-combination-check-r2/commerceops-agent/.audit/v4-1/combination-check-r2/`。实际窗口 UTC10:42:20.364593–10:42:58.856904，elapsed 38.491730584 秒。独立核 delivery.safe.json SHA-256 `1ce367215b440707d0bdd680da6ed86588e94a95020fa5619b806ce5c3caa876`、result.safe.json `e37f8af9fed24b307e4bad38e2b6c090be8607c8b9a6de5ae34845c48c1404e6`，与 Root 指定值一致。delivery 引用的全部六件 artifact 路径/hash 均匹配，十步原 stdout/stderr hash 全部匹配；before/after 文件逐字节相等，SHA-256 为 `c2182a77e4fc834d3568f8d04f003e57ba17feceff86d3ddcfbccf19b340e7fe`。

## 实际命令与结果层级

已读 run_checks.py（hash `bfa2464abcf7b5deda29019d9ce14537fa80ea26de9384f3822fdb558a836f03`）、逐步 argv 和原日志。十步均有 subprocess.run 原 native_exit=0；脚本保留首非零/timeout 停止与最终指纹比较，没有自动重试。实际范围如下：

| 步骤 | 原命令范围 | 原件结果 |
| --- | --- | --- |
| import-origin | 本 WT Python，校验 browser_shell 路径、commerceops backend/src 和 sys.prefix | NEW_OWNED_SOURCE_AND_VENV_CONFIRMED，exit 0 |
| Python offline | pytest tests/e2e/v41，marker 为 not integration and not external，JUnit | 235 PASS，0 failure/error/skip，exit 0 |
| Node pure | 固定 Node --test，19 个显式 *.test.mjs | 74 PASS，0 fail/cancelled/skip/todo，exit 0 |
| Native syntax | Node --check tests/e2e/v41/native_zoom.cjs | exit 0，输出空 |
| Native selftest | 同冻结模块 --self-test | 40 checks PASS，browserLaunches/profile=0，exit 0 |
| TypeScript | frontend/tsconfig.json，noEmit、incremental false | exit 0，输出空 |
| Ruff / format | browser_shell.py 与 test_browser_shell.py，两条 check 命令 | 均 exit 0，All checks passed / 2 files already formatted |
| mypy | 同两文件，follow-imports=silent、no-incremental、私有 cache-dir | exit 0，2 source files 无问题 |
| Mock collect | 原 frontend/playwright.v41.config.ts，--list --reporter=json | 33 项收集，测试体执行 0，exit 0 |

独立解析 python.xml（hash `dc14c163da239acf41aeb1548593cc19e4eae5bb7c1744cf367c8935656d6906`），确有 235 testcase、20 模块，其中 browser_shell 118；没有 failure/error/skipped 节点。stdout 为 235 passed in 18.73s，命令外层 elapsed 为 20.281117542 秒，口径分列。Node stdout 的 74 个通过条目及末尾汇总一致，含三处 stripTypeScriptTypes ExperimentalWarning；所有十步 stderr 为空，但不称无警告。

Native selftest 原 JSON 明确 nativeZoom/screenshots/S01 均 NOT_RUN，40 是纯组件检查数，不是 40 张截图或实际 Native 浏览器场景。Mock 原 JSON 33 项全部 results=[]、errors 空，9 batch-tags + 2 import-flow + 19 lifecycle + 3 shell，与 mock-collected.safe.json 逐条一致；该文件 hash `0ce643f27c0f458adb1ee6f7c4a7eca718b4d70ee600a1b393ed56aac8213109`。live 两个 spec 的收集仍 NOT_RUN_PENDING_NEW_ROOT_MANIFEST，不能用这次 Mock collect 代替。

## 源码、导入与依赖独立核对

Reviewer 仅执行原脚本中只读的 hash/Git/fingerprint 函数，未执行测试循环。当前重新计算结果与 before、after 完全一致：同 source/tree、git diff HEAD 为空，1858 个 tracked 文件摘要 `799840f6196e8123547e2ca19ee2d0265b756019c3a86828ebcd8d8118e025a6`；三个锁/配置、工具和两依赖树摘要亦全同。Native 模块字节、TS caller moduleHash、Python 父 NATIVE_MODULE_SHA256 独立核为同一 `0023672bfb9f648a5df2deac397fd7159dfbbc4c1cb385c5cab9d3c97396c538`。

工具 Node hash 为 `e4b5a3af0e05c75de2eae013904145f40fe7fc2a6e6f17510128bf45cca4e79b`，Python 实体 CPython3.12.13 hash 为 `a395f264e5612a2819662ed3e37fd30d39ed61179b98e5f86c3c783a008d8623`，Ruff hash 为 `70e977860c228661a4992c9558b8350903351845fa945715584f4c176a0f6c61`。python site-packages 29700 entries/hash `788b76a6277fbaeda6a55a583a4c9d73722232768a0f18a057294b651fbbc396`；frontend node_modules 12178 entries/hash `f6ab42b654b33dcadab64a3283748b2c83baedb5854170d895894110e3789a80`。本次当前重算包含这些全部文件字节及算法记录的模式/路径信息，没有仅比较前后 boolean。

依赖根为本 WT canonical 目录，两个依赖树内均无 symlink；唯一 .pth 为 `_virtualenv.pth` 的 import _virtualenv，无旧 editable 源路径。实际 import-origin exit 0 已验证本 WT 的业务包、consumer 模块与 venv prefix；Python 解释器实体在固定 uv 位置，不冒称该实体复制进本 WT。运行脚本仅保留基本系统环境，显式指向本 WT backend/src/PYTHONPATH 与 Node/Python PATH，设置 PYTHONDONTWRITEBYTECODE；Mock 收集单独设置 loopback origin。依赖准备方式按记录为 OWNED_APFS_COPIES_NO_INSTALL，本复核证明现有隔离目录与前后字节绑定，不另声称核验了 APFS 克隆历史或重新安装依赖。

## 核收边界

十步实际离线检查均通过，原 status 为 OFFLINE_CHECKS_PASS_LIVE_COLLECT_NOT_RUN。旧 Full4601/FullPG773 是历史独立层级，在此 source 未重执行；不得拼签。R4 capture lab 已关闭且本组合未重跑，详见[其独立工程核收](CAPTURE_LAB_R4.md)，该 lab 不变成 261 的实际产品 Native 运行。React Mock 实际执行、live collect/执行、服务/PG、真实权限、产品 Native/视觉与整链清理不由本包证明；无新窗口或阶段完成授权。此报告为组合离线原件核收，可交 Root 后续编排，后续实际原件另核。
