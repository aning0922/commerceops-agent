# 阶段状态与主控交接

更新日期：2026-10-08（Asia/Shanghai）。当前处于 **Phase 1 规划完成、任务实现待授权**。阶段目标和 Gate 仍以 [ROADMAP](ROADMAP.md) 为准；本文件只记录状态、依赖与证据，不改变批准的架构或验收条件。

## 1. 基线与授权

| 事项 | 核对结果与证据 |
|---|---|
| 事实基线 | GitHub main `3179dbad9eea0b632a65642cd134d850506fbbf6`；fetch 后本地 main 与 origin/main 一致，规划前工作树干净 |
| Phase 0 收口 | [PR #1](https://github.com/aning0922/commerceops-agent/pull/1) 为 MERGED，2026-10-08 16:34:06（Asia/Shanghai）合入；归档见 [PHASE0_CLOSEOUT](PHASE0_CLOSEOUT.md) |
| 审核证据边界 | 首次外部架构审核“有条件通过”及六项修订见归档；GitHub PR #1 的 reviews、review comments、conversation comments 当前均为空，不能声称外部二审已通过 |
| 用户本轮授权 | 明确启动 Phase 1 主控规划：研究依赖、建立最小计划和 Issues，完成后等待任务执行授权；尚未授权任何实现任务 |
| 本轮改动范围 | GitHub Issues、阶段状态和导航/授权说明、规划文档 PR；不创建业务代码、依赖锁、CI workflow，不连接真实平台 |
| 当前实现 | main 只有设计文档与 .gitignore；无业务代码、迁移、服务、锁文件、CI workflow 或业务测试结果 |
| GitHub 条件 | 仓库仍为 Private；Actions enabled=true；main protected=false。合并前人工核查 CI 与审核，用户明确确认后才合并 |

Phase 0 历史记录保持原样。“Phase 1 规划启动”不等于任务实现已获准，也不等于任何 Gate 已通过。阶段规划在 `codex/phase1-plan` 分支交付，通过 PR 等待审核；不得自动合并。

## 2. 最小任务与当前状态

各 Issue 已包含目标、修改边界、验收标准、测试要求、交付物、依赖及建议分支；任务接单与实现授权必须记录到对应 Issue，不能从聊天之间的口头交接推导完成。

| 编号 / Issue | 交付目标 | 启动依赖 | 当前状态 | 交付 PR / 运行证据 |
|---|---|---|---|---|
| P1-01 [#2](https://github.com/aning0922/commerceops-agent/issues/2) | 工程骨架、Python/Node 项目工具链与锁、基础 CI/敏感检查 | 用户授权本任务 | pending_authorization | 无 / 未执行 |
| P1-02 [#3](https://github.com/aning0922/commerceops-agent/issues/3) | Docker/PG、最小业务迁移、独立 checkpointer setup，G1 | P1-01 代码合入；可用 Docker | pending_authorization；环境前置受阻 | 无 / 仅环境可用性检查失败 |
| P1-03 [#4](https://github.com/aning0922/commerceops-agent/issues/4) | 持久任务、单 Worker 启动互斥与统一串行 runner | P1-02 代码合入及真实 PG 可用 | pending_authorization | 无 / 未执行 |
| P1-04 [#5](https://github.com/aning0922/commerceops-agent/issues/5) | 真实 PG Checkpoint interrupt/resume/crash，G2 | P1-03 代码合入、G1 和 runner 合同稳定 | pending_authorization | 无 / 未执行 |
| P1-05 [#6](https://github.com/aning0922/commerceops-agent/issues/6) | 飞书官方 SDK 消息/新版卡片/Base，G3 | 离线：P1-01；真测：另需 P1-02、测试资源与授权 | pending_authorization；真测外部前置未满足 | 无 / 未执行 |
| P1-06 [#7](https://github.com/aning0922/commerceops-agent/issues/7) | main 集成、证据索引、风险与外部阶段验收 | 各实现 PR 合入；全 Gate 验收还需 G1–G3 实测 | pending_authorization | 无 / 未执行 |

`pending_authorization` 表示实现尚未获准。环境/外部配置阻塞和依赖未满足是独立事实；当前不把“尚未执行”写成“测试失败”，也不把 PR 创建或 Issue 关闭视为正式完成。

## 3. 建议执行顺序与并行边界

最小主线为 **P1-01 → P1-02 → P1-03 → P1-04 → P1-06**。P1-05 在 P1-01 合入后可开始离线 SDK/卡片准备；P1-02 合入且测试资源齐备后才做真实联调。P1-06 只有在 G3 证据也达到条件时才能给出完整 Phase 1 验收通过结论。

建议每次最多两个实现会话：一个承担数据库/Worker/恢复主线，另一个承担飞书适配探针。若只有一个执行者，按 P1-01、P1-02、P1-03、P1-04、P1-05、P1-06 顺序推进；飞书配置准备尽早处理。外部配置等待不计为有效开发时间，也不承诺原 3–5 日估算一定成立。

| 共享领域 | 负责人/协调规则 |
|---|---|
| 业务模型、Alembic revision、schema 初始化 | P1-02 单一负责人；P1-03/04/05 需要新字段或表时先在 Issue 提出合同变化，由主控安排原负责人或明确转交，不同时写迁移 |
| jobs 状态转换、Worker 生命周期与 runner port | P1-03 单一负责人；P1-04 消费稳定 port，不另写第二套调度器；正式审批/补货状态机属于后续 Phase |
| Checkpoint/Graph 恢复合同 | P1-04 负责；只用隔离技术探针验证，不能顺便实现正式库存业务 Graph |
| 飞书 adapter/Gateway/技术卡片与 Base | P1-05 负责；不绕过任务入口直接调用 Graph，不实现正式 T3 或生产投影同步 |
| pyproject/uv.lock、Node lock、Compose、基础 CI | 初始化归 P1-01/02；新增依赖/启动配置/PG smoke 由当前任务提出，主控串行集成相关文件，避免多个 Worktree 同时改锁文件/workflow |
| docs/STATUS.md 与阶段结论 | 主控维护；执行会话在 Issue/PR 提交证据和建议，主控据 main 集成事实更新 |

每个任务从最新 main 建独立 `codex/phase1-*` 分支，可用独立 Worktree。依赖代码先完成审核并经用户确认合入 main，再作为正式实现基线；确需提前离线准备只限 Issue 明确的分段边界，不私下依赖尚未合并的分支。无需为并行新增部署服务、队列或应用内多 Agent。

## 4. Phase 1 Gate 与能力缺口

| 条件 | 当前结论 | 必须取得的证据 / 责任任务 |
|---|---|---|
| 基础 CI/敏感检查 | not_run；无 workflow | P1-01：实际 Actions run、当前内容与完整历史扫描、合成当前/历史凭据阻断且不回显值；随后 P1-02/04 补真实 PG smoke |
| 依赖锁与项目隔离 | not_run；无 lockfile | P1-01/02：独立环境 frozen install、实际兼容版本/许可证、实测镜像 digest；Node 工具链在项目环境固定，不改全局环境 |
| G1 Docker/PG | blocked_environment；未达到 | P1-02：daemon/Compose/PG 健康、持久卷重启、业务 migration 与 checkpointer setup 可复现 |
| 单 Worker/单 Graph 基线 | not_run | P1-03/04：S01–S03，第二进程拒绝启动、全局活跃 Graph ≤1、待审批释放槽、锁丢失停止与确认旧进程终止后恢复 |
| G2 Checkpoint | not_run；依赖 G1 与 Worker | P1-04：真实 PG interrupt、同 thread 跨进程恢复、业务探针提交后/checkpoint 前 kill、原幂等回执与图版本防错 |
| G3 飞书消息/回调/Base | blocked_external；未达到 | P1-05：真实私聊/群 @、card.action.trigger、专用确认/拒绝 action 与对象确认键往返、operator/event/时延、Base 创建/读回/更新与重复 |
| 阶段集成与外部验收 | not_run | P1-06：main commit 对应的集成结果、测试索引、残留风险、外部审核和用户决定 |

P1-04 的幂等写入是隔离 test schema 中的技术 receipt，不是正式内部补货执行。P1-05 的卡片是技术探针，探针里的测试动作不授权补货。Phase 3/4 的 T2–T6、R05–R12、A01–A08、C01–C05 等业务验收不能提前标通过；多 Worker R02–R04 为 C-EXT，不纳入 Phase 1。

## 5. 已核对的证据与本轮检查

以下均为本轮实际读取/执行结果，范围为仓库、平台设置和工具可用性；不能替代业务测试。

| 类型 | 实际命令/检查 | 2026-10-08 结果与限制 |
|---|---|---|
| 远端/本地基线 | `git fetch origin`、`git rev-parse HEAD origin/main`、`git status`、`git ls-tree -r origin/main` | fetch 成功；规划前两者同为 3179dba，工作树干净，仅设计文件 |
| Phase 0 PR | `gh pr view 1` 与 PR reviews/comments 查询 | MERGED，merge commit 与 main 一致；无二审 review/comment |
| 当前任务 | `gh issue list --state all`、`gh pr list --state all` | 规划前没有 Issues，仅已合并 PR #1；本轮新增 #2–#7 |
| GitHub | repo/Actions permissions/main branch 查询 | Private、Actions 启用、main 无保护；未改变设置或协作者 |
| 本地版本 | `python3 --version`、`uv --version`、`node --version`、`docker --version`、`docker compose version` | Python 3.12.13、uv 0.11.25、Node 20.20.1、Docker CLI 29.6.2、Compose v5.3.1；不代表项目依赖组合已通过 |
| Docker 可用性 | `docker info --format '{{.ServerVersion}}'` | exit 1，无法连接本地 daemon；未启动/安装 Docker 或修改系统服务 |
| Issue 回读 | `gh issue list --state all --json ...`，与提交正文核对 | #2–#7 均为 OPEN，目标/边界/验收/测试/交付及依赖齐全，远端正文一致 |
| 文档检查 | `git diff --check` 与临时 Python 本地链接/锚点/围栏检查 | 通过；15 份 Markdown、46 个本地链接/锚点，围栏闭合 |
| 敏感模式检查 | 临时 Python 检查当前文件及 `git rev-list --objects --all` 的所有可达 blob | 当前 16 个文件、历史 38 个 blob 未发现疑似凭据；仅定位、不回显值，不代表成熟扫描器已验收 |

上述计数对应规划提交前工作树，规划提交会新增文档 blob，不改写历史；结果同时写入本规划 PR。没有 pytest、业务 CI、PG/Checkpoint crash 或真实飞书运行结果。该临时文档检查不能计入 P1-01 的版本锁定扫描器/合成阻断验收。

## 6. 阻塞、风险与下一步

| 项目 | 当前影响 | 处理边界 |
|---|---|---|
| 任务执行授权 | 所有实现任务尚未开始 | 建议先授权 P1-01（#2）；主控再按依赖安排接单，不能把本轮规划指令扩大为整阶段实现授权 |
| Docker daemon | 阻塞 G1、真实 PG、G2 运行 | 用户正常启动可用 daemon；执行会话重新核对，不擅自修改全局设置或安装替代运行环境 |
| 飞书测试资源 | G3 未具备可验证凭证/组织/发布/最小权限/Base 资源证据 | 专用测试组织、自建应用、允许测试身份/群和 Base；秘密只填本地未跟踪配置，不在 Issue/聊天中索取或保存值 |
| 真实平台操作范围 | 本轮未授权真实联调，后续只允许明确的测试资源探针 | 扩权限、HTTP 公网/隧道、云部署另行确认；不得接生产表或修改库存/订单 |
| 未经运行验证的版本组合 | 锁文件/SDK/PG 兼容性尚无证据 | 由 P1-01/02 实测固定，官方资料/源码证据与运行证据分层，不能照抄版本快照当 lock |
| main 无分支保护 | 远程尚未自动强制 Gate | 合并前人工核查，不自行修改保护设置；无成功 CI/审核/用户确认不得合并 |
| 共享文件集成 | 迁移、锁文件、runner 和 workflow 易产生冲突 | 单一负责人、Issue/PR 合同、串行合入；发现架构差异暂停相关修改并交主控审核 |

正式任务交付后，主控核对：Issue → PR → 实际测试/CI → 外部审核 → 用户合并确认 → main commit → STATUS。任务 PR 未合入时写 `in_review`，合入且证据完整才写 `completed`；真测受阻单独记录，不能由探针代码合并自动把 Gate 改为 passed。

目前不具备 Phase 1 验收或进入 Phase 2 的证据。全部必要 Gate 达标后，由 P1-06 提交阶段总结并给出是否推荐 Phase 2；等待外部阶段审核和用户新授权。若 G3 仍受阻，只能报告未完成及受限推进建议，用户另行授权才可按 ROADMAP 继续本地工作。
