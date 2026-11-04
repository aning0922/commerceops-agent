# V4-1 Gate 与工具链方案

日期：2026-11-04（台北）。负责人：GATES。状态：方案与私有工具准备完成；V4-1 实际工程、FullPG、HTTP、浏览器及交付 Gate 均未运行。本页不预填未来候选 SHA 或验收通过。

## 来源与本批边界

新工作树基线为 `1730194028a01ddea0bbc573774d740ea4a29d55`，tree 为 `5f2a92dffb49ef21682077e89459c85db55b668d`。各 owner 完成独立可审切片后普通提交，由 Root 合入并冻结受测源码。原 M3、Harness、SCAN 工作树、失败原件和历史记录保留。

V4-0 工程证据绑定 `cbd1c4e31569bf84f065fd38dd18448d438f6225`；完整 PG 配对绑定 `c6abe0528f05b458331f270d758317c1d7b38843`，实际 568 + 177 = 745、交集 0，见 [原配对回执](../../validation/R2_FULL_PG_PAIR_20261104.md)。这些数字仅描述旧来源。新 collection、分区数量、命令退出和用时按 V4-1 实测记录。

V4-0 最终文档检查绑定本页基线；dir/index 为零命中，Git 原生命中 1,708，全部精确分类、阻断 0。原外层包装器在回执持久化后打印摘要失败而退出 1，该事实继续保留，不能用检查子命令的 0 替换外层退出。回执位于原 Root `.audit/v4-0/final-document-gate-1730194/receipt.json`。

本次准备不修改 scanner、规则或历史 provenance。现有 222 条规则、45 条 native 历史例外、96 条目录例外、152 条精确历史记录、7 条 copy 绑定和 34 个 blob 锚点继续保持其精确边界。任何未知命中须保留并由 Root 核定，不能自动加例外或扩大为通用允许。

## 后续 Gate 分账与释放

| 阶段 | 原入口与必要事实 | 准入与结果边界 |
| --- | --- | --- |
| 工程 | 完整 `python -m scripts.check`，保留敏感扫描、锁一致性、文档、lint/format/type、Node locked install/toolchain、schema、无 server 契约、完整 offline、前端 typecheck、Node 与 Python audit | Root 冻结来源并释放有界窗口；依赖安装与漏洞查询涉及网络，须由 Root 在该窗口统一准入。本批未运行，不能用纯测试替代 |
| FullPG existing | 新独立 owned 资源；原 helper 动态完整 collect、分区、实际节点、G1 三项、G2 六项及 cleanup | 原每命令 300 秒、75 秒 reserve、60 秒 cleanup 不放宽；Root 先登记绝对截止、owner、project、subnet、image/input hashes |
| FullPG phase3 | 同源码、工具、锁文件与完整 collection，使用原 helper 另一动态分区 | 不重复认领 existing smoke，不改变原分区或重试策略 |
| 双线配对 | 原 `scripts.pg_ci_evidence` 验证 selected = actual = passed，各模块及命令、source/tree/tool/lock/collection 一致，交集 0、并集精确等于完整 collect | 两份实际回执完整后才运行；部分节点、collect-only 或旧 745 不代签新 FullPG |
| 六卡运行验收 | QA 在 `tests/e2e/v41` 独占实现；绑定每个场景的来源、工具、资源、预期与实际状态、HTTP/DB/浏览器证据和 cleanup | GATES 只提供接口与汇总约束。用例集合和资源窗由 Root 与 QA 冻结，本批无实际运行 |
| 最终文档 | 新冻结来源上的完整原敏感扫描、check_docs、diffcheck、JSON、文件地图、输入 hash、保护 HEAD 与受测文件前后核对 | 信息性 refs 单列；必需检查与实际外层退出分别落盘。只在可证明输入逐项不变时复用既有运行证据；源码变化由 Root 重新划定实际重跑范围 |

FullPG 两线使用当前原 `partition()`：phase3 包含原 P3/P4 选择与 read-reply parent 分段，其余归 existing；不手工冻结列表或排除新增测试。G1 保留成功、不可用、重启三项真实证据。G2 保留五项 `G2_REQUIRED` 加既有 retired probe 负例，共六项。预期非零子命令须写明预期与实际；不能将其表述为所有命令零退出。

## 工具与资源准备

复用已核 V4-0 Root `.tools` 的公开工具，仅在对照 R2 实际 binary fingerprints 相等后复制到新 owned 树，不复制旧 `.audit`、env、私配或 runtime。版本冻结为 Python 3.12.13、uv 0.11.25、Node 24.21.0、gitleaks 8.30.1；同时保存实际 binary SHA256 和 `scripts/tool_versions.json` 的版本/归档校验，二者分别记录，不混用二进制与压缩包 hash。

本批允许 `uv sync --frozen --offline`，不修改锁文件。npm 仅能在原敏感 Gate 通过且 Root 后续释放后使用既有缓存和 locked 安装；缓存不足报告，不能自动联网升级。完整工程阶段的原 npm/pip audit 不删除，也不能以本批无网络准备代签。

本批 Docker 仅只读盘点容器、网络 IPAM 与监听端口；盘点快照不构成端口/subnet 预留。实际窗口前重新盘点，Root 分配新 project 和未占用 subnet，PG 不映射宿主端口。镜像须核真实 ID、平台和输入 hash，复用不得记为重建；未知镜像或旧私有资源不得停止、删除、retag。

未来 cleanup 独立记录开始/结束 UTC、命令退出、精确 owner 标签的容器/网络/端口与 PID inventory、卷策略和剩余资源。PG helper 原 owned 临时卷清理合同与其他运行场景的保卷合同分开；不拿一次成功 cleanup 推断其他窗口已清理。未捕获值明确记为 UNKNOWN/NOT_CAPTURED。

## 提交前最小原生预检

每个 owner 在自己的新树操作，仅 stage 本次公开文件；删除文件与缺失文件需另行核定，不用该窄工具静默跳过。Root 可提供本批已审私有预检脚本路径：

```sh
set -e
GATE_PROPOSAL_PREFLIGHT=/Users/aipuli/.codex/worktrees/commerceops-v41-gates/commerceops-agent/.audit/v4-1/gates-prep/proposal_preflight.py
git add -- docs/v4/v4-1/proposals/GATE_PLAN.md
python "$GATE_PROPOSAL_PREFLIGHT" docs/v4/v4-1/proposals/GATE_PLAN.md
git diff --cached --check
# 只有以上实际返回 0 才执行该切片的普通 git commit。
```

替换示例文件列表为本次明确公开 changed files；脚本只复制这些文件的当前/索引字节，保留相对路径，在新临时目录以原 `.gitleaks.toml`、原 binary、禁 inline allow/ignore 的参数分别运行原生 dir 扫描。当前和索引均须 native 0，报告完整保存本批 0600 文件；临时目录退出时清理。此预检是阻止新公开假阳性进入 Git 的窄措施，不能替代完整 repo dir/index/全部可达历史 Gate。失败即停止，原件保留，不盲加 exception。

## 私有 ops 接口与 QA 建议

本批私有原型与模拟回执在新树 `.audit/v4-1/gates-prep/`，不提交正式 QA 脚本。`required` 只容纳必需检查；`information` 保存 refs 等事实，汇总不访问其 `pass`。每条命令保存 argv、开始/结束 UTC、native exit、timeout、日志路径/hash；清理置于 finally，独立记录退出。检查回执原子持久化后才打印摘要。父进程 wait 实际子进程退出，再写 outer receipt；checks pass、cleanup pass、summary 状态与 outer native 不得互相推断。

QA 建议接收 source/tree、输入 hash 清单、绝对截止与 reserve、owner/project/resource binding、显式环境键白名单、required-command 结果、cleanup 结果、信息性事实和 outer-native 回执。stdout/stderr 保留私有 0600 原件，公开摘要不复制原长枚举、凭据形态或未经核定的 raw 内容。source/lock/tool 运行前后核对；任何 timeout、采集缺失或 cleanup 非零均保留并阻断相应 Gate。实际采集必须 wait/reap；仅从日志结尾猜测退出码不可接受。

原型模拟覆盖正常、检查非零、cleanup 非零、持久化后摘要打印失败四种情形。它只证明本批回执分账处理，不证明实际工程、PG、HTTP、浏览器或资源清理成功。正式 QA 接口由 Root 转交后实施，本 owner 不写其独占路径。
