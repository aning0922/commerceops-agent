# P1-01 工程底座实施证据

任务：[Issue #2](https://github.com/aning0922/commerceops-agent/issues/2)。基线：main `3179dbad9eea0b632a65642cd134d850506fbbf6`；独立分支 `codex/phase1-01-foundation`，从 origin/main 派生，未引入规划 PR #8。用户通过 Phase 1 主控明确授权本任务实施/测试/推送/PR；本交付等待外部审核和用户合并确认，不表示 Phase 1 Gate 或下一 Phase 授权。

文件负责人：本实施会话负责 backend、frontend tooling、锁文件、检查工具、workflow、本证据及开发说明；STATUS/AGENTS/ROADMAP 由主控单独维护。本任务没有改动三份阶段文件。

## 实际本地运行

本地运行日期：2026-10-08（Asia/Shanghai；以下汇总本轮实际执行结果，统一检查最终复验时间见页末记录）。机器：macOS / Darwin arm64；Python 3.12.13、uv 0.11.25、项目 Node 24.21.0/npm 11.19.0、Gitleaks 8.30.1。全局 Node 仍为 20.20.1，未升级；没有全局依赖安装。

证据模式：`source_mode=not_applicable`（技术骨架无电商数据），`model_mode=not_used`，`approval_mode=not_used`。合成扫描值是无效随机测试数据；实际 HTTP 进程 smoke 是本机技术运行，不是业务或真实平台联调。

| 实际命令 | 结果 / 范围 |
|---|---|
| `uv lock`、`uv lock --check` | 解析 59 个 lock 条目（含项目与条件依赖），一致性检查通过；直接版本与 Python 支持范围逐项核对后选入 |
| `uv sync --frozen` | 新建本项目 `.venv` 安装通过 |
| `UV_PROJECT_ENVIRONMENT=.tools/clean-env uv sync --frozen --no-editable` | 第二个全新项目内环境，非 editable wheel 安装通过 |
| `uv build --no-build-isolation` | 使用已安装锁定 build tooling 实际构建 sdist 与 wheel 成功 |
| `.tools/clean-env/bin/python -m pytest -m offline` | 17 passed（8.77 秒），非 editable 安装的入口/技术测试复验通过 |
| `docker info --format` | daemon 无法连接，实际退出 1；G1 不通过，不改变系统服务 |
| `uv run --frozen python -m scripts.bootstrap_tools` | macOS arm64 官方下载包 SHA256 与入库固定值匹配；只安装到 `.tools` |
| `uv run --frozen python -m scripts.check` | 统一检查退出 0：敏感/文档/lock/lint/format/typecheck/pytest/npm 安装与 typecheck/漏洞查询 |
| `uv run --frozen ruff check .`、`ruff format --check .` | 通过；含骨架、检查工具与测试 |
| `uv run --frozen mypy` | strict 通过，18 个 Python 源文件；无忽略整个包的豁免 |
| `uv run --frozen python -m pytest -m offline` | 17 passed（8.67 秒），无 skipped；HTTP 契约、真实安装入口进程、配置失败脱敏/显式环境、扫描阻断与文档检查失败合同 |
| `npm --prefix frontend ci --ignore-scripts`（项目 PATH） | 锁安装成功，实际安装 4 个依赖；npm 审计统计含根共 5 个包 |
| `npm --prefix frontend run check:toolchain` / `run typecheck` | Node 精确版本检查和实际 tooling TypeScript 文件检查通过；没有前端页面 build/Playwright 结论 |
| `pip-audit -r .audit/requirements.txt --require-hashes --disable-pip --strict --format json --output .audit/python.json` | PyPI advisory 查询 57 个实际平台锁依赖，0 已知漏洞、0 跳过；包含 runtime/dev/build tooling |
| `npm --prefix frontend audit --audit-level=low`（项目 PATH） | 0 已知漏洞，退出 0；包括 dev tooling |
| `python -m scripts.scan_secrets` | 当前工作区、暂存 index 各 0 命中；全部可达 Git 历史 0 命中；原始报告/输出不持久化 |

早期检查曾发现类型标注/测试导入路径问题，已修复并复验。敏感文件名合成用例最初因用户全局 ignore 排除了未跟踪 `.env` 而失败；改为临时仓库 force-stage，验证实际提交边界，最终阻断通过。`pip-audit --local --skip-editable --strict` 因项目 editable 而返回失败，随后改成导出完整带 hash 的锁依赖、明确排除未发布项目本体，strict 查询通过；没有将失败扫描算作成功。

## 合成阻断实证

`tests/test_quality_gates.py` 在临时 Git 仓库中实际执行固定扫描器，并断言退出码与 stdout/stderr 脱敏。运行时随机生成无效合成值，主仓库中不含合成凭据全文。

| 场景 | 实际断言与结果 |
|---|---|
| 无敏感基线 | dir/index/git 都 0 命中、退出 0 |
| 当前文件含合成 PAT，带内联 allow 注释 | `github-pat` 规则命中 dir、退出 1；内联 allow 不绕过；输出不含值或匹配行 |
| 提交合成值后删除并提交 | dir 0 命中；git 命中旧 commit、退出 1，证明删除当前文件不能清历史 |
| 合成值只在另一可达分支 | 当前 main 内容 0 命中；git 扫描另一 ref 的历史命中、退出 1 |
| 合成值只在 index，工作区已清理 | dir 0 命中；index 命中、退出 1，防止暂存/工作区分歧漏检 |
| force-stage `.env`（内容无秘密） | 敏感文件名策略单独阻断、退出 1 |
| 浅克隆 | fail closed，退出 2 |
| 文档错误 | 不存在的本地链接和未闭合围栏都实际触发错误；代码块内伪链接不误报 |

以上是初次交付 head `206c907` 的实际测试，保留其结果；当时 `.gitleaks.toml` 使用 `useDefault=true` 且无新增项目豁免，但继承了默认路径 allowlist。独立审核后来证实它没有覆盖锁文件/ignore/-diff 绕过，不能由 17 passed/旧 CI 推导全面内容覆盖。修复与新结果见下方审核修复记录；当前扫描合同见 [开发说明](DEVELOPMENT.md)。

## 版本支持与直接依赖许可证

以下是本轮读取官方注册表元数据、安装包 METADATA 与 lock 的事实，支持 Python 3.12 不等于未来业务/平台兼容验收。没有照抄 RESEARCH 快照直接声称组合可用；实际验证仅为本任务技术 smoke。未选入 LangGraph/checkpointer/PG/飞书 SDK/Next/React/Playwright，分别在所属任务锁定并实测。

| 直接依赖 | 固定版本 | 官方最低 Python / Node | 许可证及核对来源 |
|---|---|---|---|
| FastAPI | 0.142.4 | Python ≥3.10 | MIT，[PyPI](https://pypi.org/project/fastapi/0.142.4/) |
| Pydantic | 2.13.5 | Python ≥3.9 | MIT，[PyPI](https://pypi.org/project/pydantic/2.13.5/) |
| pydantic-settings | 2.15.0 | Python ≥3.10 | MIT，[PyPI](https://pypi.org/project/pydantic-settings/2.15.0/) |
| Uvicorn | 0.54.0 | Python ≥3.10 | BSD-3-Clause，[PyPI](https://pypi.org/project/uvicorn/0.54.0/) |
| Hatchling（build/dev） | 1.32.4 | Python ≥3.10 | MIT，[PyPI](https://pypi.org/project/hatchling/1.32.4/) |
| HTTPX（dev） | 0.28.1 | Python ≥3.8 | BSD-3-Clause，[PyPI](https://pypi.org/project/httpx/0.28.1/) |
| markdown-it-py（dev） | 4.2.0 | Python ≥3.10 | MIT（METADATA classifier），[PyPI](https://pypi.org/project/markdown-it-py/4.2.0/) |
| mypy（dev） | 2.4.0 | Python ≥3.10 | MIT，[PyPI](https://pypi.org/project/mypy/2.4.0/) |
| pip-audit（dev） | 2.10.1 | Python ≥3.10 | Apache-2.0（METADATA classifier），[PyPI](https://pypi.org/project/pip-audit/2.10.1/) |
| pytest（dev） | 9.1.1 | Python ≥3.10 | MIT，[PyPI](https://pypi.org/project/pytest/9.1.1/) |
| Ruff（dev） | 0.16.10 | Python ≥3.7 | MIT，[PyPI](https://pypi.org/project/ruff/0.16.10/) |
| tomli-w（规则生成 dev，审核修复阶段显式选入） | 1.2.0 | Python ≥3.9 | MIT，[PyPI](https://pypi.org/project/tomli-w/1.2.0/)；原锁中已作为传递依赖存在 |
| TypeScript（tooling） | 7.0.2 | Node ≥16.20.0 | Apache-2.0，[npm 元数据](https://registry.npmjs.org/typescript/7.0.2) |
| @types/node（tooling） | 24.19.1 | Node 24 类型系列 | MIT，[npm 元数据](https://registry.npmjs.org/@types/node/24.19.1) |

工具：uv 0.11.25（MIT OR Apache-2.0，[发布元数据](https://pypi.org/pypi/uv/0.11.25/json)）、Gitleaks 8.30.1（MIT，[固定发布](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1)）、Node 24.21.0 LTS/npm 11.19.0（Node 发布包含第三方许可，[Node LICENSE](https://github.com/nodejs/node/blob/v24.21.0/LICENSE)、[Node 发布政策](https://nodejs.org/en/about/previous-releases)、[SHA256](https://nodejs.org/dist/v24.21.0/SHASUMS256.txt)）。Python lock 和 npm lock 固定传递依赖/下载完整性；npm lock 记录 npm 包许可证，包括 TypeScript 平台可选包与 undici-types。本表是直接依赖记录，不宣称已完成全部传递依赖的法律审查。

配置与工具官方依据：[Pydantic settings](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/)、[uv frozen/locked](https://docs.astral.sh/uv/concepts/projects/sync/)、[Gitleaks 使用与扫描模式](https://github.com/gitleaks/gitleaks)。这些是官方资料核对；运行证据以命令表为准。

## 外部 CI 与保留边界

交付 [PR #9](https://github.com/aning0922/commerceops-agent/pull/9) 已建立并保持 OPEN。首个实际 [Actions run 37755417919](https://github.com/aning0922/commerceops-agent/actions/runs/37755417919) 对 head `91146d375abdd6e47dd76ce46900fa2b6b12760c` 返回 success；2026-10-08 17:15:44–17:16:32（Asia/Shanghai），Ubuntu 24.04/Linux x64，job 48 秒。下载 SHA256、frozen 安装、dir/index/git 0 命中、17 passed（14.39 秒）、mypy 18 文件、16 文档、Node24/TS tooling、Python57包/npm漏洞查询全部实际通过。

首个 run 提示旧 Action 声明 Node20、runner 强制 Node24 的弃用警告。根据官方 tag/ref 与 action.yml 的源码核对，现改为原生 Node24 Action：checkout v7.0.1 (`3d3c42e5aac5ba805825da76410c181273ba90b1`)、setup-python v7.0.0 (`5fda3b95a4ea91299a34e894583c3862153e4b97`)、setup-uv v10.2.0 (`c18668ad3cf93ea998bef934396af7bb5c839dc7`)。各自官方发布与 action.yml 均显示 Node24；源码核对之后已取得真实运行证据（下一段），没有将源码支持声明替代运行结果。发布来源：[checkout](https://github.com/actions/checkout/releases/tag/v7.0.1)、[setup-python](https://github.com/actions/setup-python/releases/tag/v7.0.0)、[setup-uv](https://github.com/astral-sh/setup-uv/releases/tag/v10.2.0)。workflow 固定 Action SHA、Python/uv/Node/scanner 版本与扫描器发布 SHA256，PR/main push、只读权限、完整历史；不提供飞书/Woo/模型密钥。

无业务 migration/checkpointer/持久 Worker/Graph/库存/审批/补货/真实平台调用；PG migration/checkpoint smoke 不适用。无前端应用，build/Playwright 不适用。Docker daemon 不可用时 G1 仍 blocked_external，G2/G3 未执行，不因本 PR 创建或 CI 通过而标绿。仓库分支保护未变更；外部审核、用户确认合并及主控 main 证据核对仍是正式完成条件。

本地最终复验记录：2026-10-08T17:14:56+08:00；统一检查退出 0，干净非 editable 环境 17 passed。提交前已审阅暂存 diff、敏感文件集合与全部可达历史，dir/index/git 均 0 命中。

原生 Node24 workflow 的实际 [Actions run 37755746183](https://github.com/aning0922/commerceops-agent/actions/runs/37755746183) 对 head `0b96392806455d48ee422fe7065389a5030b18c1` 返回 success；2026-10-08 17:18:38–17:19:29（Asia/Shanghai），Ubuntu 24.04/Linux x64，job 51 秒。17 passed（13.90 秒）、dir/index/git 0 命中、16 文档、mypy strict 18 文件、frozen 安装、Node24/TS tooling 与 Python57包/npm已知漏洞查询全部通过，check-run annotations=0。此后文档提交对应的最新 head/run 由 [PR checks](https://github.com/aning0922/commerceops-agent/pull/9/checks) 和 Issue #2 最终交付记录核对；不把旧 head 的检查冒充新 head 已通过。

## 2026-10-08 独立审核后的修复记录

审核：[完整 COMMENT review](https://github.com/aning0922/commerceops-agent/pull/9#pullrequestreview-5454598608)、[Issue 交接](https://github.com/aning0922/commerceops-agent/issues/2#issuecomment-6057054014)，审核 head `206c907b7892e33b3ea9d2f296a4d1bbc8700998`。发现 1 个 P1、2 个 P2，均为无效合成值复现，未发现真实凭据；状态 changes_requested。旧 17 项测试和同 head CI 成功是事实，但未覆盖这些绕过，不替代修复与复审。

本实施会话读取固定 v8.30.1 官方源码确认：[`cmd/root.go`](https://github.com/gitleaks/gitleaks/blob/v8.30.1/cmd/root.go) 额外加载 source 根 ignore；[`config/config.go`](https://github.com/gitleaks/gitleaks/blob/v8.30.1/config/config.go) append 继承 allowlists（空项目 allowlist 无法移除默认项）；[`config/gitleaks.toml`](https://github.com/gitleaks/gitleaks/blob/v8.30.1/config/gitleaks.toml) 的全局 paths 排除锁/SVG 等；[`sources/git.go`](https://github.com/gitleaks/gitleaks/blob/v8.30.1/sources/git.go) 跳过非归档 binary diff。以上为官方源码证据；以下对照才是实际运行证据。

| 审核项 | 修复及实证 |
|---|---|
| P1：fingerprint ignore 隐藏历史 | 拒绝原根 `.gitleaksignore`（含 ignored/untracked/symlink）及 index/可提交同名文件；历史扫描改用只有 Git 元数据指针的隔离 source。不将空 ignore 参数当作禁用保证。回归覆盖 untracked、tracked、ignored、index-only 四种状态，实际加载前阻断。 |
| P2：默认路径 allowlist 排除文本 | 固定副本保留全部 222 条规则，移除 1 全局/13 规则级上游 allowlist，不再 useDefault/extend。package-lock.json、uv.lock、SVG 分别验证 current/index-only/committed/history。仅两处规则/文件/精确整行 AND 格式误报豁免；同文件同一规则的合成值仍阻断。 |
| P2：Git -diff/textconv 隐藏旧文本 | 历史 `--text --no-textconv --no-ext-diff`，强制原始 patch；回归覆盖 -diff 与会掩盖值的 textconv，旧文本已删除、dir/index 无命中时 git 仍阻断，转换器没有执行。 |

实际原/新对照：从原审核 head 导出脚本/配置至完全临时目录，共用固定扫描器，只在临时 Git 仓库运行。ignored fingerprint、package-lock、-diff 三个案例均为 `original_exit=0, fixed_exit=1`，输出不含运行时生成的无效值；fingerprint 案例在加入 ignore 前，原脚本实际 exit=1。未联系任何凭据验证 API，合成全文未进入主仓库或日志。

移除上游 allowlist 的第一次真实本仓扫描暴露两处格式误报（数据模型公开字段行、规则自身声明行），退出 1，未写作通过。随后增加上面两个精确 AND 豁免；没有排除 docs 或整个 `.gitleaks.toml`。源码 location 会把前导换行包含在 Line 中，第一次精确豁免未匹配、检查仍失败，修正为只允许这个换行后重新验证。新扫描 dir/index/git 实际 0 命中。规则来源与派生 hash、inventory、两条豁免行 hash 见 [provenance](../scripts/gitleaks_rules.json)，MIT 通知见 [LICENSE](../third_party/gitleaks/LICENSE)；源码与生成步骤可重复核对，没有降低 regex/entropy 或移除规则。

本地修复相关验证：`uv run --frozen python -m pytest tests/test_quality_gates.py` 实际 34 passed（38.98 秒），包含原 9 项与新增 25 项；ruff/format/mypy strict（19 文件）通过。文档/转换器绝对 marker 细化后，实际运行一次 `uv run --frozen python -m scripts.check`，退出 0：42 passed（41.51 秒）、mypy 19 文件、16 Markdown、ruff/format、Node frozen install/typecheck 通过；dir/index/git 0 命中；Python57包和 npm 查询均 0 已知漏洞、0 跳过。本地记录时尚未取得修复 head 的 Actions，后续真实结果见下段；旧 head CI 不替代此证据。

二进制/不可达对象/外部 Gate 边界保持开发说明：不承诺归档递归、加密或任意二进制嵌入的完整检测；以 Git 属性标记为 binary 的文本仍强制检测。没有新增业务实现或改主控阶段文件；PR #9 保持 OPEN，等待独立复审、用户确认合并及 main 证据核对。

审核修复本地记录时间：2026-10-08T18:00:45+08:00。初次安装/业务边界证据保留；本轮只修敏感扫描与必要工具/回归，不开展下一任务。新 commit/同 head CI 以 PR 与 Issue 的逐项修复交付记录核对。

修复 commit `c9ed5f64e68d3c1dd3a4b036950c0ac485d1a94c` 的实际 [Actions run 37760638043](https://github.com/aning0922/commerceops-agent/actions/runs/37760638043) 返回 SUCCESS：2026-10-08 18:01:04–18:02:11（Asia/Shanghai），Ubuntu24.04/Linux x64，job67秒，annotations=0。42 passed（38.34秒）、mypy strict19文件、16文档、锁安装/ruff/format/Node tooling均通过；修复后的dir/index/git扫描实际0命中，Python57包/npm已知漏洞查询实际0命中。此后仅文档证据提交的最终head/run由PR checks与Issue逐项交付评论核对；不把c9ed5f6的CI冒充最终head通过。三项修复等待原独立审核会话复审，不自行给出approval或合并。
