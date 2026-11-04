# V4-1 分批推送合同

2026-11-04（台北），用户明确补充：“要及时推送仓库，不能全累积到一起”。本授权覆盖 Root 将已独审、自检和敏感扫描通过的实际切片常规推至 `codex/v41-control-20261104`，不等待 V4-1 全阶段完成。未完成、未实测和 HOLD 仍如实登记，推送不等于阶段验收。

为满足用户不累积源码的要求，Root 还可将原生敏感预检通过的已提交候选快照，正常推送到同名单 owner 开发分支 codex/v41-api-20261104、codex/v41-web-20261104、codex/v41-qa-20261104 作进度备份。每个快照登记准确 SHA、已验和 HOLD/NOT_RUN；候选推送不解除独审或运行阻断。只推明确冻结的 commit，不上传未提交文件/私有配置/资源，不创建 PR 或触 Hosted；作者继续本地交接，Root统一推送。集成分支仍仅接独审核收的切片。

Root 统一正常集成和推送；各作者继续本地短提交，独审后分批接入。无 force/amend/reset，不覆盖未知远端工作。首次推送前核远端是否已有同名分支、打开的 PR 和工作流触发规则；每批推后只读核远端实际 HEAD 和 Actions。若网络结果不明，先核原分支 SHA，不盲重推。

实际已读远端 main 与本阶段提交中的唯一 quality 工作流：push 仅 `main` 和 `phase/1-integration`，PR 仅 opened/synchronize/reopened/edited；本阶段分支当前无 PR。Root 不创建 PR、改保护/工作流、手动 dispatch 或合 main。必要提交可带 `[skip ci]`；GitHub 官方说明该标记适用于 push/pull_request，不能代替对其他事件的检查，见[跳过工作流文档](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs)。

Hosted CI、真实模型/embedding、Woo/飞书外发和生产发布仍未授权。本阶段默认本地验收；旧“远端写未授权”按此前时点保留，由本次明确增量授权覆盖常规阶段分支推送，其他边界不变。
