# P1-01 开发与检查说明

本页只描述已实现的工程底座。API 是本机 liveness 技术入口，没有业务 API、数据库、Worker、Graph 或真实平台连接。阶段状态由主控维护；任务事实见 [Issue #2](https://github.com/aning0922/commerceops-agent/issues/2)，实际证据见 [P1_01_EVIDENCE](P1_01_EVIDENCE.md)。

## 环境与安装

从仓库根目录执行，使用 Python 3.12.13、uv 0.11.25。`.python-version` 固定开发 patch，`requires-python` 限定 3.12 系列；CI 使用相同 patch。已有其他 uv 版本时，可自行在项目内安装固定版本（不会更改全局环境）：

```sh
mkdir -p .tools
python3.12 -m venv .tools/uv
.tools/uv/bin/python -m pip install 'uv==0.11.25'
export PATH="$PWD/.tools/uv/bin:$PATH"
```

正式依赖用锁文件安装，不用 `pip install -r` 另行解析：

```sh
uv lock --check
uv sync --frozen
uv run --frozen python -m scripts.bootstrap_tools
uv run --frozen python -m scripts.check
```

`bootstrap_tools` 只向 `.tools` 安装 Node 24.21.0（自带 npm 11.19.0）和 Gitleaks 8.30.1；下载官方发布包并校验 [固定 SHA256](../scripts/tool_versions.json)。支持 macOS/Linux 的 arm64/x64。Linux x64 运行证据由本 PR 的 Actions 提供；其他平台只有明确记录后才可称已验证。不改全局 Node/Python/Docker 配置。重新 bootstrap 会替换本项目内同名工具。

`check` 使用项目 Node PATH，执行 `npm ci --ignore-scripts`、实际 tooling TypeScript 检查及 npm audit。当前没有 Next.js/React 应用；build/Playwright 不适用，因此没有假 build/e2e 脚本。页面任务再核对并选入这些依赖。

## 技术入口与配置

```sh
uv run --frozen commerceops-api
curl --fail http://127.0.0.1:8000/health/live
```

响应为 `{"status":"ok","service":"commerceops-api"}`，只表示 HTTP 进程活着，不表示 PostgreSQL、平台凭证或业务 readiness。默认仅绑定 `127.0.0.1`；启动配置只接受 `127.0.0.1`/`::1`，端口 1–65535。不启用 API 文档、公网入口或业务路由。

[.env.example](../.env.example) 只有占位启动配置。运行入口读取 `COMMERCEOPS_HOST`、`COMMERCEOPS_PORT`、`COMMERCEOPS_LOG_LEVEL` 环境变量，不隐式加载 `.env`。可显式设置变量，例如 `COMMERCEOPS_PORT=8001 uv run --frozen commerceops-api`。无效配置退出且只输出固定错误提示，避免 Pydantic 原始输入进入日志。未来秘密配置须由所属任务扩展；不得打印 settings/env 或把密钥粘贴到文档。

## 包边界与测试合同

实际包路径为 `backend/src/commerceops`：`domain`、`application`、`workflows`、`tools`、`adapters`、`infrastructure`、`entrypoints`。目前除 `infrastructure/config.py` 和 `entrypoints/api.py` 外均为分层包说明。依赖方向沿用 [ARCHITECTURE](ARCHITECTURE.md)；业务、持久化和外部操作由后续 Issue 实施，不在底座中预设假的实现。

后续任务使用 `Settings` 的环境前缀与显式类型校验约定，按任务扩展配置；机密字段使用 secret 类型并保持日志脱敏。pytest markers：`offline`（无外部服务）、`integration`（真实 PG 等基础设施）、`external`（真实平台配置）。未选中的测试不会当作通过；当前只有 offline 测试，不创建缺 PG 时恒绿的 integration smoke。

单独检查命令：

```sh
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy
uv run --frozen python -m pytest -m offline
uv run --frozen python -m scripts.check_docs
uv run --frozen python -m scripts.scan_secrets
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend ci --ignore-scripts
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run typecheck
```

检查工具以 `python -m scripts.<name>` 从根目录执行。文档检查覆盖 Git 可提交 Markdown 的本地文件链接（不查询远程 URL，不验证标题 anchor）、围栏闭合，以及工作区、暂存区、HEAD 和 `origin/main...HEAD` 的差异空白。

## 敏感检查与 CI

当前工作区扫描集合是 `git ls-files --cached --others --exclude-standard`：含已跟踪文件和未忽略的新文件。已跟踪敏感文件即使在 `.gitignore` 中也会阻断；本地未跟踪且忽略的 `.env`/`.tools`/`.audit` 等不进入可提交扫描。秘密只应保留在这样的本地配置中。另从 index 的 Git blob 构建暂存内容快照，防止已暂存内容与工作区不同（例如暂存秘密后只清理工作区）漏检。敏感文件名（`.env*`，明确 `.example` 模板除外；私钥/证书容器等）和可提交 symlink 会阻断。

历史扫描使用 `--all --full-history -m --text --no-textconv --no-ext-diff`，含所有可达 refs、root commit 和 merge 相对父提交的原始差异；强制文本 patch，不能由 `.gitattributes` 的 `-diff`、textconv 或 external diff 掩盖历史文本。浅克隆直接失败。不可达/已被远端删除的对象不属于“可达历史”，不会声称已扫描。

Gitleaks 8.30.1 会额外读取 source 根的 `.gitleaksignore`，显式指定空 ignore 文件并不能关闭这个行为。脚本拒绝仓库根存在的该文件（包括未跟踪、被 `.git/info/exclude` 等忽略的文件和 symlink），也拒绝可提交/index 中的同名文件。三个扫描 source 均在临时目录；历史入口只有指向原 Git 元数据的 `.git` 指针，扫描器不直接以原工作区根为 source，因而不会自动加载其 ignore 文件。没有 baseline，`--ignore-gitleaks-allow` 禁止内联绕过。

[.gitleaks.toml](../.gitleaks.toml) 是固定官方配置的完整规则副本，不使用 `extend/useDefault`。已删除上游 1 个全局和 13 个规则级 allowlist，保留全部 222 条规则的正向 regex/path/entropy 等条件；没有锁文件、SVG 或 docs 的整类排除。仅保留两个明确误报豁免，均为指定规则 + 指定文件路径 + 精确整行的 AND：`generic-api-key` 在 `docs/DATA_MODEL.md` 的公开 identities 字段说明行；`aws-amazon-bedrock-api-key-short-lived` 在 `.gitleaks.toml` 的该规则自身固定 regex 声明行。只允许扫描器 location 带上的一个前导换行，不允许任意附加内容。相同文件的其他行、同一规则的合成值仍阻断；不能按路径跳过整个文件。豁免依据与行 SHA256 可审查于 [gitleaks_rules.json](../scripts/gitleaks_rules.json)，Gitleaks MIT 通知保留在 [LICENSE](../third_party/gitleaks/LICENSE)。后续豁免必须作为配置/证据变更评审。

规则生成命令是 `uv run --frozen python -m scripts.vendor_gitleaks_rules <已下载的上游配置>`，只接受官方 v8.30.1 配置 SHA256 `e163e53b9e7e8a8511e77271e2b323ed057759542a6d988258afe3a1fa329caf`，不在 CI 动态下载或继承默认配置。生成时校验 TOML 语义 round-trip；运行时校验入库配置 hash、222 条规则 inventory 与豁免结构，变更不符会 fail closed。tomli-w 1.2.0 为显式固定 dev 依赖，已包含在漏洞检查。

当前工程的锁文件和 UTF-8 文本资产实际进入 dir/index/history 规则检测。原始二进制仅有扫描器能识别的特征检查，不承诺压缩包内条目、图片/PDF 嵌入内容、加密或任意编码数据的完整覆盖；未启用归档递归。私钥/证书容器的文件名策略仍独立阻断。此边界不用于排除以 `-diff` 标记的文本，Git 历史已强制原始文本差异。

扫描器原始 stdout/stderr 被捕获并丢弃，临时 JSON 在退出后删除；用户输出只含 scope（dir/index/git）/rule/file/line/commit 和计数，不含 Secret/Match。真实凭据命中时停止推送，只报告位置/类别，并由用户决定轮换和历史处理；不强推清历史。合成测试运行在临时 Git 仓库，运行时拼接无效随机值，既不提交到本仓库也不联系 GitHub 凭据 API。

[quality.yml](../.github/workflows/quality.yml) 用 PR/main push、`contents: read`、完整 fetch、固定 Action SHA/工具版本，不使用 `pull_request_target` 或业务平台 secrets。敏感检查先于依赖安装，统一检查再验证同一工作树；任何检查或漏洞查询失败均阻断 job。CI 只证明底座技术 smoke，G1–G3、真实平台联调和业务验收仍各自留证据。当前未配置分支保护，用户合并前须核对 CI、外部审核和主控证据，不声称平台已强制禁止合并。

## 依赖更新与漏洞查询

修改直接版本后在独立分支运行 `uv lock` / 项目 Node 的 npm install 更新锁，复验统一检查，禁止只改 manifest 省略锁。固定版本不是永久安全承诺；CI 每次查询已知漏洞，服务不可用同样失败。

Python 检查将全部 runtime/dev/build 锁依赖导出到忽略的 `.audit/requirements.txt`，用 pip-audit 2.10.1、PyPI advisory 服务、`--require-hashes --disable-pip --strict` 查询并检查 JSON 无命中/无跳过。项目自身没有 PyPI 发布记录，以源码检查和测试验收，不以 editable skip 冒充已审计。npm 对完整 tooling 依赖树查询，包含 dev；不只审计不存在的生产依赖。报告是查询时的已知漏洞结果，不等于代码安全证明。直接依赖许可证及兼容范围见证据页。
