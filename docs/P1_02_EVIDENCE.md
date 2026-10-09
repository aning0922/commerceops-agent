# P1-02 PostgreSQL 持久层与 G1 实施证据

任务：[Issue #3](https://github.com/aning0922/commerceops-agent/issues/3)。实施基线 main `a0d521ed79505287fa61bb6ddf82640e97824257`，PR #8/#9 已合入；接单时无未合 PR。独立托管 Worktree `phase1-postgres`，分支 `codex/phase1-02-postgres`。本任务独占 migrations、持久层、Compose、依赖锁与必要 PG CI；STATUS/AGENTS/ROADMAP 由主控维护。PR 保持 OPEN 待独立审核与用户确认合并，Issue 不自动关闭。

## 版本与证据性质

| 项目 | 固定/实际值 | 核查方式 |
|---|---|---|
| Docker Desktop | 交接 4.83.0；本会话实际 daemon 29.6.2 | `docker version --format '{{.Server.Version}}'`，未修改全局工具 |
| Compose | v5.3.1 | `docker compose version` |
| 本机平台 | macOS arm64 | 实际镜像 inspect architecture=arm64 |
| PG 镜像 | `postgres:17.11-bookworm` | 官方镜像，实际 pull 与真实容器查询 |
| PG manifest digest | `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826` | pull/RepoDigests；Compose 固定，多架构 manifest |
| Python 镜像 | `python:3.12.13-slim-bookworm` | 实际 pull、Docker build |
| Python manifest digest | `sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2` | Dockerfile 固定；本机 arm64，CI amd64 另列 |
| Python / uv | 3.12.13 / 0.11.25 | 本机虚拟环境和容器实际构建，锁安装 |
| SQLAlchemy / Alembic | 2.1.4 / 1.20.0 | 公开包元数据、官方文档与本机/容器实际迁移 |
| psycopg / binary / pool | 3.3.6 / 3.3.6 / 3.3.3 | 锁依赖，实际连接 |
| checkpoint-postgres / checkpoint | 3.1.2 / 4.2.0 | 官方包范围 checkpoint >=4.1,<5，psycopg >=3.2；实际 async setup/读写 |
| 业务 schema/revision | `business` / `0001_task_foundation` | Alembic 实际查询 |
| checkpoint schema | `checkpoints` | 官方 `AsyncPostgresSaver.setup()`，未手写表/ORM |

本轮所有数据库技术结果：`source_mode=postgres_technical`、`model_mode=not_used`、`approval_mode=not_applicable`。technical_fixture principal/shop/inbox/task 是隔离数据库样例，不是平台身份验证或真实审批；没有飞书/Woo/模型调用、库存写入、补货项或外部发送。

官方文档核查：[PG 官方镜像](https://hub.docker.com/_/postgres)、[SQLAlchemy psycopg dialect](https://docs.sqlalchemy.org/en/21/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg)、[Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)、[官方 async setup](https://reference.langchain.com/python/langgraph.checkpoint.postgres/aio/AsyncPostgresSaver/setup)。Python 支持范围来自 PyPI 元数据（SQLAlchemy >=3.11、Alembic/psycopg/checkpoint-postgres >=3.10），项目限制 3.12。官方源码验证为实际安装包的 setup/from_conn_string：autocommit、dict_row、prepare_threshold=0，setup 根据官方 checkpoint_migrations 顺序继续执行；不是 Graph crash 运行证据。serializer 明确 `allowed_msgpack_modules=[]`、默认不启用 pickle fallback，不额外放行自定义类（仍允许官方 SAFE_MSGPACK_TYPES），本轮只验证原生 marker；无 LangSmith tracing/托管依赖授权（其包是上游 transitive dependency，未调用）。

## DATA_MODEL 到首批迁移映射

统一 UUID PK，通用 created_at/updated_at 为 timestamptz。业务所有关联用非级联 FK，runtime 不提供删除历史的权限；updated_at/version 更新由后继用例负责，本轮不实现状态转换或 Worker。

| 设计实体 | 本轮字段与关键约束 | 增量/应用边界 |
|---|---|---|
| organizations | name、feishu_tenant_key、feishu_app_id；tenant/app 各唯一，额外 `(id,app,tenant)` 候选键 | 单组织运行不删多组织隔离字段 |
| shops | organization_id、adapter_kind、external_shop_key、timezone、currency、config_ref、environment；organization FK，org+adapter+external 唯一，environment mock/test、currency 三位大写 | IANA timezone/币种目录、实际适配器与配置引用的验证由后继配置用例负责；只存 config_ref |
| principals | organization_id、display_name、enabled、roles、auth_version；org FK、roles operator/approver/admin 白名单、auth_version 正数 | trigger 要求 roles/enabled 变更版本恰好 +1，禁止版本倒退；同店铺访问授权仍属应用职责，未增加通用 RBAC |
| identities | principal_id、provider、app_id、tenant_key、external_subject；平台四元组唯一 | 增加 organization_id 以复合 FK 约束 principal 与组织注册的 app/tenant；首批供飞书/技术样例，未来其他 provider 的 scope 必须审查迁移 |
| conversations | organization_id、channel、chat_id、actor_id、topic_key、summary、summary_version；同组织 actor FK，org+channel/chat/actor/topic 唯一 | task 的强 FK 依赖，故保留此最小实体；不实现 conversation_messages/摘要生成 |
| business_tasks | 设计列全部保留；org/shop/requester/conversation 复合 FK，conversation.actor=requester；thread text=task UUID 且唯一，version 正数、设计状态白名单、state/updated_at 索引 | active_plan_id 保留 UUID、`active_plan_reserved` CHECK 强制 null；后继计划实体迁移须删除该 CHECK 并添加同 task/org/shop 复合 FK，不能留下无保护引用 |
| task 不变字段 | trigger 保护 id/thread/org/shop/conversation/requester/workflow_version | task/thread 与 workflow 版本稳定；合法状态转换/授权由后继业务用例实现 |
| inbox_events | source/app/tenant/event/message/hash/payload/received/status/task 全部保留；平台事件唯一、非空 message 部分唯一 | 增加 org/shop 复合 FK，task 若存在须同店铺；status received/processed/rejected 首批接入约定，后继状态新增走迁移，不是已实现 T1 ACK |
| jobs | task/kind/dedupe/payload/status/attempts/available/lease/error；dedupe 全局唯一，ready 部分索引，lease 两字段同时为空/非空、running 必须有 owner | 增加 org/shop 与 task 复合 FK；状态 ready/running/done/retry_wait/dead；不领取/续租/恢复/执行；不添加 fencing |
| audit_events | organization/task/actor/source/action/entity_type/entity_id/before/after/reason/trace/occurred 全部保留；同组织 task/actor FK | slash 记法 entity_type/id 映射为两个独立 text 列；runtime SELECT/INSERT，拒绝 UPDATE/DELETE/TRUNCATE；不承诺防 DBA 篡改 |

normalized_request/sanitized_payload 为 JSONB object，要求 schema_version 存在；精确输入类型/正版本、脱敏与可信身份由后继 Pydantic/应用层负责，数据库不能判断任意文本是不是秘密。任务状态 CHECK 只限制状态集合，合法转换、T1 原子 inbox+task+job+audit、T2–T6 正式合同均未实现，不将技术 seed 计作业务事务验收。任务强关联范围已落库，snapshot/plan/approval/execution/replenishment/outbox 等未使用实体保留在设计，后继独立增量迁移。

最小 repository 只有 scoped get 和事务内 enqueue。去重返回原 job UUID 前比较 organization/shop/task/kind/payload_ref；不同语义安全报冲突。没有接受模型租户、角色或 approved 布尔值的业务入口。owner 用于部署，runtime 用于技术业务/checkpoint 调用，职责与权限见 [开发说明](DEVELOPMENT.md)。

## 实际运行

2026-10-08（Asia/Shanghai），最终权限/初始化恢复逻辑运行 19:08:12–19:09:06（UTC 11:08:12–11:09:06）。随机项目 `p102-bec798b00263`、库 `commerceops`、卷 `p102-bec798b00263_pg_data`；容器 `postgres` 为 running/healthy，`Ports=5432/tcp` 无发布端口。实际 SQL 查询：`PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2)`、aarch64 Linux、gcc 12.2.0，初始化角色 `commerceops_owner`。所有检查后 cleanup exit=0，测试项目容器/网络/卷和该轮构建镜像、秘密文件已清理。首轮构建缓存与共享基础镜像保留。

| G1 项 | 实际断言/结果 |
|---|---|
| 空库及重复初始化 | migrate / setup-checkpointer / grant-runtime / revision 各执行两次成功；business revision `0001_task_foundation` |
| 官方 checkpoint revision | SQL max(v) 为 9，与安装包 `len(AsyncPostgresSaver.MIGRATIONS)-1` 一致；业务表只在 business，官方表只在 checkpoints，public 无表 |
| PG 集成 | `13 passed, 42 deselected in 1.50s`；见 tests/test_postgres.py 的真实约束断言 |
| 组织/店铺关联 | task shop/requester/conversation 跨组织 INSERT 拒绝；inbox/jobs 同组织跨店铺复合 FK 拒绝；identity principal/tenant 与 audit task 跨组织拒绝 |
| 去重与稳定 ID | inbox event/message 分别唯一、另 app/tenant 可同标识；job 同语义返回原 UUID，异语义/越界冲突；task UUID/thread/workflow 不可变 |
| 审计/权限 | runtime audit UPDATE/DELETE/TRUNCATE 拒绝、业务 schema CREATE 拒绝；角色白名单；roles/enabled 变更须 auth_version+1、禁止倒退 |
| 迁移失败恢复 | 随机独立库预置 jobs 冲突，失败后 organizations 和 alembic_version 均不存在；移除自建冲突，原 migration 重跑两次成功 |
| setup 部分失败 | 测试临时注入第二个官方迁移位置 division-by-zero；失败有异常，原官方 setup 恢复并重复成功，未持久修改官方内部模型 |
| 受限 saver 读写 | app 角色实际 aput、关闭连接后 aget_tuple 原生 marker 一致 |
| 卷与 DB 不可用 | task/thread `ba93213a-4eec-4e0e-8817-ccdf0a75a5b1`；重启、同卷强制重建容器、停库非零失败再启动后均保持 inbox/jobs/audit=1，checkpoint marker一致；enqueue 重试返回既有 job |

复现命令 `uv run --frozen python -m scripts.pg_smoke`；与 CI 完全相同，必须真实 PG，不缺配置恒绿、不用 SQLite。

## 质量与 CI 合同

最终本机 `uv run --frozen python -m scripts.check` 返回 0：18 Markdown、ruff lint/49 Python文件 format、mypy31文件、offline `42 passed, 13 deselected in 43.09s`，项目 Node24.21.0/npm11.19.0、实际 tooling typecheck、npm audit0命中；Python runtime/dev/build audit85包、已知漏洞0、无skip。`uv lock --check` 成功；敏感 dir/index/全部可达history0命中（提交前再以真实暂存内容扫描）。SQL公开字段及测试变量/fixture类型曾触发 generic-api-key 误报，改为常规SQL引用标识符/更清楚的变量写法；未修改scanner/规则/两项精确行豁免，没有加入真实秘密豁免。新增直接依赖许可证：SQLAlchemy/Alembic/checkpoint-postgres MIT，psycopg LGPL-3.0-only（公开包元数据）；二进制发行仍须遵循上游许可证。

[quality workflow](../.github/workflows/quality.yml) 保持只读权限/固定ActionSHA/完整history扫描，增加与本地一致的真实 PG smoke。实际CI的 run URL、head、平台与结果在 [Issue #3](https://github.com/aning0922/commerceops-agent/issues/3) 和交付PR留最终回执，只有同head实际成功才称CI通过；本页本地结果不替代远端结果。CI不接平台/模型secret；integration 必选且无PG配置会失败。

实施代码 head `d9c34bd1a744be8c22fa7c398f0091d99fb2ea99` 的 [Actions run 37768392902](https://github.com/aning0922/commerceops-agent/actions/runs/37768392902) 实际 SUCCESS（2026-10-08 19:11:12–19:14:24 Asia/Shanghai，quality 3分12秒）。Ubuntu24.04/Linux x86_64，PG17.11 Debian，42 offline/61.90秒、13真实PG/2.72秒，18Markdown、mypy31文件、Python85包与npm漏洞0、dir/index/history敏感0。远端任务/thread `26ecb769-2a62-4102-a4f8-b86533aa14b1` 三次恢复回读一致、inbox/jobs/audit=1、官方checkpoint marker一致；独立项目 `p102-a19a56fbb400` 最终清理成功。此处是已运行代码head的证据；随后仅文档收录/边界措辞提交，最终PR head的实际CI回执以Issue/PR为准，不将旧head结果冒充新head结果。

## 范围、风险与后继交接

- G1 本地运行证据由本页给出，正式 Gate 记账仍须主控核对；任务未合并不记正式完成。
- G2 尚未实施：没有 Worker 启动锁/单执行槽、Graph interrupt/resume、进程 kill 或业务提交/checkpoint 之间的崩溃窗口验证。官方 saver 的读写/重启回读只证明存储能力。
- API 仍是 loopback liveness，没有 DB readiness；本轮 Compose 只提供 PG 与显式一次性 init/test，不伪装占位 Worker/Gateway 健康服务。数据库无默认 host ports。
- PostgreSQL 17.11 / bookworm 与依赖在本轮版本有效；不是未来安全/生产部署承诺。主版本升级、备份还原、RLS、外部账号和真实模型仍需所属任务证据。
- 官方 setup 部分 autocommit 失败后可按已记录版本重跑，特定非事务 DDL 故障仍须检查对象，不能强制 stamp。迁移 owner 为高权限本地管理用户，runtime 不负责部署。
- P1-03/P1-04 使用本迁移、scope/job 去重合同和独立 checkpointer 连接；本任务仍为迁移唯一负责人，新增 revision、共享锁变更须协调。P1-05 只依赖业务/checkpoint 分 schema及必要配置，不从本轮推导真实平台 Gate 已通过。
