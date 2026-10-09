# 本分支提交前检查

日期：2026-10-09（Asia/Shanghai）。检查对象为独立工作树的 docs/ux 与 tools/design/penpot；业务文件、共享锁、CI 和主控 STATUS 未修改。main 基线及远端核对均为 `a0d521ed79505287fa61bb6ddf82640e97824257`。

| 实际命令/检查 | 结果与边界 |
|---|---|
| `uv sync --frozen --all-groups` | 成功安装当前仓库锁定环境到本工作树；锁文件未变 |
| `uv run --frozen python -m scripts.bootstrap_tools` | 本工作树 Node 24.21.0、Gitleaks 8.30.1 下载及入库 SHA256 核对成功；未改全局 PATH/Node |
| `ruff check tools/design/penpot` / `ruff format --check tools/design/penpot` | 4 个 Python 文件通过 lint/format |
| Python compileall、Node AsyncFunction 对 create-poc.js 语法检查 | 通过；JS 语法检查不替代实际设计创建 |
| `python tools/design/penpot/check_contract.py` | 3 POC 屏幕、4 控制件、14 次实际点击记录；screen/control/event、目标 UUID、恢复回读与 revision 一致，M1 保持 planned_unmapped |
| `python -m scripts.check_docs` / `git diff --check` | 本地 Markdown 链接、围栏与差异空白通过 |
| `python -m scripts.scan_secrets` | 提交前当前可提交内容、index、全部可达 Git 历史均 findings=0；暂存后再次检查 |
| 设计服务私有 env 的 `docker compose config --quiet` | 通过，未回显插值后的秘密；6 个镜像固定实际 tag+digest |
| 最终 CLI wrapper `mcp list`、CLI MCP smoke | wrapper 发现 penpot；真实 MCP read/write/readback completed，回读标记一致，其他全局配置未写入 |
| 本地实际设计、原型、快照恢复、服务重建 | 结果与失败细节见 [acceptance](acceptance.md)，不计为 M1 业务测试 |

早期扫描检测到公共文件 SHA 和官方 MCP overview 的设计 token API 属性名，均已对照来源确认为误报。改变 manifest 的表达结构，并在发布副本省略该单个公共 API 引用，原始输出留在私有运行目录；实际 mutation 调用和回读值未改变。详情见 [redactions](evidence/redactions.json)。没有增添 allowlist、改扫描规则、改 workflow 或改 Git 历史来让检查通过。

没有执行新的业务 pytest、G1–G3、真实飞书、库存审批 T3/T4/T6 或 Next.js/Playwright 业务 E2E；不得把本表解释为这些通过。GitHub PR 的基础 CI 另以对应 head 的实际运行结果为准，PR 未合并不记正式完成。
