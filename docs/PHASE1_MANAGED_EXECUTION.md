# Phase 1 托管执行与集成迁移方案

日期：2026-10-08（Asia/Shanghai）。**状态：用户已批准混合编排与 Phase 1 主控合并裁决（包含最终 main）；持续 Goal 已激活。** 本文件只改变 Phase 1 的执行/审核/版本交付方式，不改变 ARCHITECTURE、DATA_MODEL、业务权限或 ROADMAP/TEST_PLAN 的 Gate。

## 1. 批准前核对快照

| 项目 | 读取结果 / 证据 |
|---|---|
| GitHub main | `a0d521ed79505287fa61bb6ddf82640e97824257`，Private；PR #8/#9 已合并，P1-01 已完成 |
| 阶段状态 PR | [#10](https://github.com/aning0922/commerceops-agent/pull/10) OPEN，原 head 804cc54，已取得同 head CI success；未合入 main，所以 main 的 STATUS/AGENTS 阶段介绍尚落后于 GitHub 实际事实 |
| P1-02 交付 | [PR #11](https://github.com/aning0922/commerceops-agent/pull/11) OPEN，head `bcbd9331257d3285234c47a22ecefe29815a582b`，当前 base=main，尚无独立 review |
| P1-02 CI | [run 37768892191](https://github.com/aning0922/commerceops-agent/actions/runs/37768892191)，head 精确一致、SUCCESS；交付记录包含 42 offline / 13 real PG、迁移/持久卷/重启/setup 证据，不是 Graph 中断/崩溃验证 |
| P1-02 原会话 | `01a11b26-75bf-7ca2-9735-d48553a3af78`，已交付、idle；Worktree `/Users/aipuli/.codex/worktrees/phase1-postgres/commerceops-agent`，branch `codex/phase1-02-postgres`，当前干净；不重复派发或并行写该目录 |
| 集成分支 | 当前远端不存在 `phase/1-integration`；批准后从届时最新 main 创建并记录精确 SHA |
| 当前 Gate | G1 有已交付技术运行证据，待独立审核/集成核对；G2 未实施；G3 没有真实消息/卡片/Base 验收证据，测试资源与凭据可用性尚未确认 |

本轮以 GitHub 合并、PR/head/CI、Issue 与会话/Worktree 实际读取为准，不把过时阶段介绍或聊天摘要作为当前完成结论。G1 的 saver 读写/重启不等于 G2 的真实 LangGraph interrupt/resume/crash。

## 2. 当前编排能力

- Goal 工具已实际创建本线程的 Phase 1 持续目标，status=active；不额外设置用户未指定的 token budget。后续授权和完成边界以本文件和 GitHub 记录为准。
- 原生子代理工具已实际完成独立上下文的只读集成可行性审计与方案复核。P1-02–P1-05 主要实施采用独立顶层会话，独立审核/专项检查采用子 Agent；最多两个实施任务，不重复写实施 Worktree。
- P1-02 保留原有顶层会话/Worktree作为唯一实施负责人；后续修复交回该会话，不另开竞争实现。本轮实际调用 `send_message_to_thread` 做只读接续，再由 `wait_threads` 收到原会话完成结果：HEAD 仍为 bcbd933、工作树干净、PR #11 OPEN/base main、同 head CI SUCCESS，未运行测试/Docker或修改文件。原会话可程序化驱动与等待；普通审核/修复/接续在已有 Phase 1 授权内无需重复询问。
- GitHub 读取、创建/更新 PR/Issue、推送与 merge 能力已由 P1-01 流程实际验证；当前账号仓库权限查询为 admin。main 的 protected=false；不会改变仓库可见性、协作者、保护策略，也不将独立 COMMENT 冒充平台 APPROVE。
- Goal 是本线程的目标与续接合同，受会话/账户预算、主机/工具可用性及用户中断约束；不承诺电脑休眠、应用离线时仍持续工作。不创建新的通用 Agent 框架或后台调度服务。

| 执行形态 | 上下文和生命周期 | 文件隔离与接续 | 本项目安排 |
|---|---|---|---|
| 主控内部子 Agent | 独立上下文，由主控派发、收取结果和接续；属于当前主控任务树，不等同于用户拥有的顶层 Codex 会话 | 默认共享文件系统，不自动隔离 checkout；必须明确独立分支和 Worktree，主控不得并写；followup_task 可接续 | 独立 Review Agent 和专项检查；独立上下文审核，绑定精确 SHA |
| 顶层 Codex 会话 | 单独的用户会话、侧栏记录和持久聊天历史 | 需独立 Worktree；create_thread/send_message_to_thread/wait_threads 支持创建、驱动与等待，已实际验证 | P1-02–P1-05 主要实施，保留原 P1-02；修复仍交原任务会话 |

两者均可满足独立上下文、明确分支、隔离 Worktree 与独立审查要求；隔离来自实际 Worktree 分配和写入责任合同。主控只维护规划/依赖/状态与证据，组织 PR/阶段审核，不承担 P1-02–P1-05 主体编码，也不在能力不足时退化为主控包办。每个实施派发写明目标、修改边界、验收、实际测试、PR 交付和文件负责人；审查使用另一个 Agent 的上下文与冻结 SHA 的独立只读 checkout，不能用开发者自检代替。

官方说明：[Codex 子 Agent](https://developers.openai.com/codex/subagents)、[Codex Goals](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)。本轮能力结论以实际工具调用为主，官方说明不代替本机能力证明。

## 3. 已批准的合并权限

用户授权主控在门禁满足后确认以下 Phase 1 任务 PR 内部合并到 **phase/1-integration**：

1. Phase 1 控制/状态/必要 CI 迁移（当前 #10）。
2. P1-02–P1-06 的已批准任务代码、测试、证据和对应修复（当前 #11 及后续关联 #3–#7 的 PR）。
3. 由主控协调、严格属于上述任务的必要集成修复与状态更新；不得扩大为新业务或新 Phase。

最终 phase/1-integration → main 阶段 PR 的合并裁决也已明确授权主控。仅在 G1/G2/G3 全部必要真实证据、完整阶段验收、独立审查和当前合并上下文实际 CI 通过后执行普通 merge，再核对 main CI 与阶段状态；不得将未完成 Gate 的候选代码提前最终合入。用户原话为“包含 main：全部必要 Gate、独立审查和实际 CI 通过后，由主控确认合入 main；不进入 Phase 2”。重大架构变更、真实业务敏感数据/权限扩大、危险系统操作、强推/改历史/删除未知数据、无法解释的 CI/恢复失败、预算/环境耗尽均停止相关操作并请求人工处理。

这里的“自动合并”是主控逐项核对后发出带 `--match-head-commit` 的普通 merge 命令；不启用跳过门禁或管理员绕过，不修改平台保护配置。每次门禁核对以 GitHub 当前 PR/head/base 与真实运行/审核为准。

## 4. 无历史改写的迁移顺序

依序执行，所有写入任务由独立执行者承担，主控只维护文档与调度：

1. 重新 fetch/核对最新 main、#10/#11 head、Issue/会话状态；确认没有另一个控制器或 Worktree 正在写相同分支。若集成分支已存在，先审计来源与历史，不覆盖它。
2. 从最新 main 创建 `phase/1-integration`，推送新分支；建立主控集成 Worktree，原实施 Worktree 保持独立。
3. 主控先将本轮仅文档变更普通提交/推送至原 #10，记录精确 head；确认当前 checkout 干净后冻结并交接该控制/状态分支，切离该分支，确认没有别的 checkout 占用它。将 #10 的 base 改为集成分支后，独立 CI 迁移执行 Agent 才在自己的 Worktree 接续同一明确分支/PR，只负责下项 CI 触发改动与验证，主控不并写。独立 Review Agent 再核对 #10 的精确新 head、改 base 后的实际 PR 检查和文档/敏感验证；条件满足才受限合入集成分支。这里是控制面 CI 的小型执行任务，不重新派发 P1-02。
4. CI 必须覆盖 PR 的 `opened/synchronize/reopened/edited`、`push main` 和 `push phase/1-integration`。当前 #10 只提交文档方案，workflow 尚未修改；批准后由上项独立执行者将 PR types 显式列出并增加集成分支 push 过滤，保留只读权限、固定 Action SHA、完整 fetch、锁定扫描器，不提供真实飞书/Woo/模型密钥。该真实 CI 提交在 retarget 后产生 synchronize，取得新合并上下文 run；集成 push 验证后才迁移 #11。
5. 将 #11 的 base 改为集成分支，保留原提交和同一 PR。主控与独立审查逐项核对 DATA_MODEL、migration/权限/幂等、G1 本机与 CI 证据；任何修复仍由原会话在原分支新增提交。只有真正需要同步已合基线时才普通 merge 集成分支到工作分支，不 rebase/amend/force-push。
6. 改 base 或改变内容后，取得与当前合并上下文一致的实际 CI；不能拿旧 base/head 的绿灯抵用。显式订阅 edited 后核对实际新 run。若没有产生适用 run，由原实施者普通 merge 已实际更新的集成基线到工作分支，保留 #11 的 PG smoke 与迁移检查，让真实基线同步产生 synchronize，再独立复核新 head。不能用旧 workflow 的 rerun 证明新 base，因为 rerun 保留原 GITHUB_SHA/GITHUB_REF。记录 PR head、base SHA、review SHA、run 的 merge SHA 与集成预检；不制造空提交，不跳过检查。
7. #3–#7 的阶段内依赖/完成合同须先获得本次用户批准并实际更新，才能将内部集成当作依赖或完成证据。该前置与所有门禁满足后，以普通 merge commit 合入 #11；等待集成分支 push CI 和必要 PG/迁移/持久化检查真实成功，再放行 #4 的依赖。#11 工作树不因重定向 base 被其他执行者直接写入。
8. 后续工作分支从当前已验证的集成 commit 建立，PR 统一指向集成分支。共享迁移、状态机、runner、锁文件和 workflow 有单一负责人/交接记录；不通过口头协商替代 Issue/PR 合同。

用户要求的分支名 `phase/1-integration` 优先于默认 `codex/` 前缀。已有工作分支保持 `codex/phase1-*`。

触发与重跑语义依据：[GitHub PR workflow 事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)、[重跑保留原 SHA/ref](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)。仅修改 PR base 不保证现有默认触发配置产生新运行。

## 5. 每次内部合并的门禁

| 条件 | 主控必须读取的证据 |
|---|---|
| 范围符合 | PR diff 对应 Issue 修改边界，无新架构/权限/平台设置扩张 |
| 必要测试完成 | 实际命令/版本/时间/退出码和关键数据库/进程断言；PG 不用 SQLite 替代，skipped 不计通过 |
| 独立审查无阻断 | 独立于实施者的 reviewer，结论绑定当前代码 SHA；原问题逐项解决，新内容必要复审。GitHub 同账号 COMMENT 是可审查记录，不假称平台 APPROVE |
| 实际 CI 通过 | 当前 head/合并上下文的所有必要检查 SUCCESS，无 queued/in_progress/failed/cancelled 抵用；读 job/log，不只相信会话文字 |
| 集成安全 | 无未解决冲突，必要集成测试已通过；采用精确 head 匹配 merge，基线变化后重核对 |
| 合入后收敛 | 集成 commit 的 push CI/必要测试通过，Issue/STATUS 记录实际 commit、测试/审核链接及后继依赖 |

Gate 通过仍必须对应 ROADMAP/TEST_PLAN 的运行证据，不能由“PR 已合入”推导。若合入后检查失败，暂停依赖任务、在已授权范围定位/新增修复提交并复审，不强推或回退改写历史。

## 6. 续接、并行与停止合同

Goal 完成合同：在 aning0922/commerceops-agent 按批准范围推进 #3–#7，取得 G1/G2/G3 全部真实证据、内部集成通过、阶段报告/STATUS 完整、创建并独立审核最终阶段 PR、必要检查通过后由主控确认合入 main 并验证 main；不进入 Phase 2。若真实 G3 等必须人工处理的前置阻塞，明确列证据和解锁条件，继续尚可独立完成的本阶段任务，不能因阻塞降低 Gate或把 Goal 标 complete。

- 主线：#3 PostgreSQL → #4 Worker → #5 Checkpoint → #7 集成验收。
- #6 飞书离线 SDK/卡片/字段契约可以与主线并行，最多两个实施；真实消息/卡片/Base 写入须具备已指定测试组织/应用/群/表、权限与本地秘密配置，缺失时 `blocked_external`，不联系生产资源。
- 每个任务完成内部集成/验证后，主控立即查找已满足依赖的下一项并委派，无需等待“继续”。Issue/STATUS 标为 `integrated`，明确集成分支与 SHA；不要宣称 main 已具备该能力。任务级内部交付可据合同关闭 Issue，最终阶段/main 状态单独验收。
- Issue 只有其完整验收合同均满足才可关闭；例如 #6 仅离线交付时保留 OPEN、真实部分 `blocked_external`，不因探针代码内部集成就关闭或将 G3 标 passed。#7 也等待全部必要 Gate 的真实证据。
- 用户已批准合同切换；须先实际修订 #3–#7 原“依赖必须合入 main”和完成状态合同，再合入 #11 或放行下游。阶段内依赖改为已审查/验证的集成 commit；最终 main 合并裁决已委托主控，但须全 Gate。不得修改 Gate、权限或业务合同，也不把 #6 离线代码合入当 G3 通过。
- 同一阻断连续三轮针对性修复仍不能解决：记录每轮假设/修改/命令/失败，暂停相关任务并查找安全独立任务；不无限重试。CI/恢复错误无法解释、重大架构/权限/危险操作等按用户规定立即停止相关操作。
- 任务阻塞不等于自动暂停整个 Goal。还有独立任务就继续；所有安全工作耗尽且同一人工阻断已持续三个 Goal turn，按 Goal 工具合同标为 blocked并交付解锁条件。只在用户明确暂停整个 Goal 时使用 paused；预算耗尽不冒称 complete。
- Goal 已启动；没有真实飞书证据时，不能推荐 Phase 1 全 Gate 通过、最终合入 main或以 blocked 报告伪装阶段完成。

## 7. 证据与版本归档

每个交付记录 `issue / PR / head / base / reviewer head / CI run / 集成 SHA / migration revision / 镜像 digest / workflow_version / source_mode / model_mode / approval_mode / 命令时间与结果` 的适用字段，包含未运行/skipped/真实平台与技术替身区分。

批准时 #10/#11 均 OPEN/base main，集成分支尚不存在；迁移逐步执行，实际 branch/PR/head/CI/审核和任务状态写入 GitHub 与 STATUS，不把批准前快照当作运行中的当前状态。

最终阶段报告说明 G1/G2/G3 各自结果、全部 Issue/PR/CI/审查索引、未解问题/外部配置与进入 Phase 2 的建议。全部门禁通过后按委托裁决合入 main；进入下一 Phase仍等待新授权。

## 8. 批准前方案核对记录

- 独立只读 Agent `integration_feasibility_audit` 完成可行性审计；没有代替 #11 的代码审核。本轮提出的分支交接与 Issue 合同前置已纳入方案。
- 主控使用 P1-01 已固定检查工具验证本轮文档：18 份 Markdown 本地链接/围栏与 Git 空白检查通过；修复后的 scanner 对当前/index/所有可达 Git 历史运行，三层 findings=0、exit=0。无业务测试或飞书真测新增结论。
- 本轮只更新阶段/控制文档，并将 Issue #3 的已交付状态改为 in_review；没有修改实现、锁文件、migration、workflow 或 GitHub 权限/保护策略。后续 CI 配置由独立实施者完成再独立审核。
