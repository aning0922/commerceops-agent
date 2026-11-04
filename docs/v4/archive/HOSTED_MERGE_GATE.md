# PR #53 Hosted 与主线合并门禁

2026-11-04 用户明确授权本次必要 Hosted CI，检查通过后正常合入 main 并核对合后结果；
不绕过保护，完成后继续暂停后续功能，等待新研究包。

## 首轮实际结果

[运行 41848095782](https://github.com/aning0922/commerceops-agent/actions/runs/41848095782) 的 PR head 为
`a1fc837d5e8ce161eb220edfb78295608a8ebdcb`，实际 checkout 为 GitHub 临时合并提交
`98ce4a1e523de5bae3eac683728d43f5c6a1c694`；其 tree 与该 head 相同。
运行终态五项失败，业务测试与 PG 配对未核收，不以原本地通过替代。

当前文件和 index 扫描均 native0；完整历史扫描 native1，1707项中1706已审、1项阻断。
唯一阻断是公开前端页面在临时合并提交中的完整文件副本：原机制仅接受既有精确 blob，
当前已验页面的完整 blob 不在该表，因此按设计拒绝。没有真实密钥泄漏结论。

整改限定为既有不可变来源表中增加该页面的精确已验 source、完整 blob 及原位置/内容绑定，
同步原衍生 provenance 配置和针对性正反例；检测规则、分类算法、扫描范围、业务和权限不变。
正规生成确认222条规则、96项精确行例外与 `.gitleaks.toml` 同字节，仅新增一个完整文件锚点。
修复的实际提交与独立检查另按冻结回执核对，不预填下一轮通过。

## 合并条件

使用本次精确候选完成 quality、phase3、frontend、n01-web 和 pg-pair 全部既有门禁；
PG 严格来源配对与清理证据另核，不能只看绿色状态。再次确认 main 与 PR HEAD，
在原保护规则下普通 merge 并保留分支，然后核对合并提交及其主线 CI。
首轮独立诊断见 [原始诊断](HOSTED_R1_DIAGNOSTIC.md) 与 [实际结果](HOSTED_R1_RESULT.json)。
实时结果见 [PR #53](https://github.com/aning0922/commerceops-agent/pull/53)。

Hosted 许可不授权真实模型/embedding、飞书/Woo业务外发、生产或下一阶段功能。
旧失败、原本地证据、UNKNOWN 与人工未验边界保持。
