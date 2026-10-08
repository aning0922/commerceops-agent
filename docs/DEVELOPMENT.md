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

## P1-02 PostgreSQL 与一次性初始化

数据库能力见 [P1_02_EVIDENCE](P1_02_EVIDENCE.md)；阶段文件由主控维护。Compose 默认仅启用 PostgreSQL，不发布宿主端口。`init` / `test` profiles 是一次性管理和技术验证，不是长期 Worker/Gateway。当前 API `/health/live` 的语义保持进程 liveness，没有 DB readiness。数据库 healthcheck 的 `pg_isready` 仅证明 PG 接受连接；业务 revision 与 checkpoint setup 另行验证，不能把 healthy 当成初始化成功。

从本仓库根目录运行（需要已有可连接 Docker daemon、Compose、uv；不安装全局服务）：

```sh
uv sync --frozen
uv run --frozen python -m scripts.prepare_pg
# 用明确项目名隔离开发容器/网络/持久卷。
docker compose -p commerceops-pg-dev up -d --wait postgres
docker compose -p commerceops-pg-dev build db-init
docker compose -p commerceops-pg-dev run --rm db-init
# 业务与 checkpoint 初始化是两个独立部署动作。
docker compose -p commerceops-pg-dev run --rm db-init python -m commerceops.entrypoints.database setup-checkpointer
docker compose -p commerceops-pg-dev run --rm db-init python -m commerceops.entrypoints.database grant-runtime
docker compose -p commerceops-pg-dev run --rm db-init python -m commerceops.entrypoints.database revision
```

`prepare_pg` 在忽略的 `runtime/pg` 生成两个随机密码文件，权限 0600；已有非空文件保留，禁止把内容粘贴到日志或提交。Compose 用 file secrets 挂载，数据库设置不隐式加载 `.env`。`COMMERCEOPS_PG_RUNTIME_DIR` 可指定本项目秘密目录。不要运行带秘密的 `docker inspect` 全输出、打印 settings/env/DSN 或启用 SQL 参数日志。修改密码文件不会自动轮换已有 PG owner 密码；需要先安排安全的 DB 角色密码变更，不能靠删除卷解决。

配置合同是 `COMMERCEOPS_DB_HOST`、`PORT`（默认 5432）、`NAME`、`USER`、`PASSWORD_FILE`；`grant-runtime` 另要求 `RUNTIME_PASSWORD_FILE`。其余四个连接字段均必填，无配置的 integration 测试失败；常规离线测试不选 integration。迁移目录默认 `backend/migrations`，命令从仓库/容器 `/app` 根运行。秘密读取用 `SecretStr`，仅在连接时解封；不存入业务表。初始化命令失败返回非零及固定错误类别，避免数据库错误原文泄漏参数。

`commerceops_owner` 是本地初始化管理角色（官方镜像的初始用户），用于创建 schema、迁移、官方 setup、授予受限权限。业务调用使用 `commerceops_app` 与 `app_password`：无超级用户/建库/建角色权限；业务 schema 无 CREATE，业务表无 DELETE/TRUNCATE，审计只有 SELECT/INSERT。checkpointer schema 的现有表授予官方运行所需 SELECT/INSERT/UPDATE/DELETE；业务与 checkpoint 不共用事务。新实体迁移后须明确审查新增权限，重新执行 grant，不用全业务 schema 的未来默认授权。此配置只面向本地技术开发；不声称提供生产 DBA 隔离或租户 RLS。

关闭开发容器保留卷：

```sh
docker compose -p commerceops-pg-dev down
```

不要对未知项目运行 `down --volumes` 或 `docker volume prune`。本任务自动 smoke 使用随机 `p102-*` 项目及独立卷，结束仅清理自己创建的容器/网络/卷/构建镜像与秘密文件：

```sh
uv run --frozen python -m scripts.pg_smoke
```

本地与 CI 使用同一个真实 PG 流程：构建锁依赖镜像、空库初始化及重复初始化、真实约束/失败恢复测试、提交持久样例、PG 重启、保留卷重建容器、数据库不可用非零失败和恢复回读。记录落到忽略的 `.audit/pg-smoke.json`，包含模式、时间、随机项目/卷和检查项。Docker 构建缓存与共享基础镜像保留。需要独立数据库权限的失败注入测试只在本任务 PG 实例中随机建库，并在 finally 删除自己创建的库；不得向共享或生产 DB 直接运行。

迁移恢复：Alembic 将 schema/version 表和整次 revision 放在同一 PG 事务。失败后查询 `business.alembic_version`，核对实际 revision 和冲突对象；修复原因再重跑 migrate，禁止手工 stamp 到 head 或把部分结构当成功。技术测试通过预置 `business.jobs` 冲突断言该次新表和版本表均回滚，移除测试冲突后重跑两次成功。真实 DB 遇到未知对象时先核对来源，不能直接套用测试里的 DROP。checkpointer 官方 setup 使用 autocommit，允许部分迁移已记录，须原版本官方 setup 重跑；测试注入中途失败并恢复，不能据此保证所有 DDL/网络故障都自动恢复。不要手改 checkpoint 内部列/迁移号。版本升级先在隔离库验证；破坏性 Alembic downgrade 明确禁用，业务历史恢复走备份流程（完整备份还原演练后续交付）。

后继任务合同：`connect` 的 connection context 成功提交、异常回滚，不内建重试；`TaskRepository.get` 按 organization/shop/task 精确限定，`enqueue` 在调用者事务内追加 job，同 key 同 task/kind/payload_ref 返回原 UUID，不同语义抛 `PersistenceConflict`。Scope 必须由应用已验证身份构造，repository 本身不授权。事务中查询/追加后由调用者负责提交；不得在事务内调用模型/网络。未实现 task 创建入口、ACK、job 领取/调度、Graph、中断恢复、正式审批或任何外部发送。待审批恢复/G2 仍由后继任务验证；本轮只验证官方 saver 数据读写与初始化。
