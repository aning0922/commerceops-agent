# 单条公开摘要历史 metadata 独立复核

日期：2026-11-04（台北）。结论：`ACCEPT_EXACT_AUTHOR_HISTORY_METADATA_ONLY`。仅核收 source `d6fb87b60c63616f18c268f58bc0754507fc3eed` / tree `736758c8d167a07cdf8326e4cb2504986f3ab70d` 的单条 metadata 增量；不是完整扫描、推送或 UI P2 核收。

## 精确差异

相对直接父提交，仅 `scripts/vendor_gitleaks_rules.py` 增加一条 `V4_ADDITIONAL_HISTORY` tuple、docstring ten 改 eleven，以及 `scripts/gitleaks_rules.json` 增加对应十二行。逐对象核验原十条不变、生成函数输出与 JSON 全部十一条相等、其余 JSON 不变。`.gitleaks.toml` 与 `scripts/scan_secrets.py` 字节不变；copy anchors/bindings 未改，新路径没有加入 copy anchor。未发现新增 P1/P2。

允许对象仅为作者提交 `8d1f3fc971f2e62cfa2ff948808c4e1d28cec2b1` 中 `docs/v4/acceptance/v4-1/UI_MOCK_R4.json` 第41行、列17—96、rule `generic-api-key` 的原生 finding；同时绑定完整 fingerprint、脱敏 Match 摘要及整行 span 摘要。其值为已独立核实的零字节 R4 dummy 日志 SHA-256，不是凭据。不得以此允许其他作者、复制/合并来源、pattern、dir 或 index。

- exact span / whole row（不含换行）：`ef2044b08ac81ab8c2608eff2d3eb913e9eb96245d7ac374e57f928035828ecd`。
- redacted Match SHA-256：`3cd7e8955b0d42fea60694c8c2de19889f771ce5bf0f7c65febcf6d5d7c40270`。
- 原 native finding 来自独立固定 scanner 对 `8d1f3fc^..8d1f3fc` 的实际扫描：native1、恰一项；没有用 dir finding 的空 Commit 拼造历史 finding。

## 独立验证

从精确 d6fb87b 的 Git archive 提取 scripts 到审查树私有目录，使用 Root 固定 Python 导入候选完整模块；仅将模块 ROOT 指向独立审查树的 Git 对象库以读取固定来源，不合入 Root 历史，不读取作者 WIP。直接调用候选 `approved_v4_history_finding` 与 `approved_v4_merge_copy`，实际 **27 assertions PASS / 0 FAIL，命令 native0**：

- 原始 author-native finding 在 git scope 为 true；dir/index 均 false。
- RuleID、File、Commit、StartLine、EndLine、StartColumn、EndColumn、Fingerprint、Match 九字段逐一变更均 false；Match 缺失亦 false。
- 整行源 span 增加单字节或来源读取失败均 false。此两项明确使用 subprocess 返回故障注入验证，未篡改 Git 对象，不冒称创建了损坏历史提交。
- 换成实际 d6fb87b 或 9cd019a 完整作者 SHA，并同步重算 fingerprint，history 仍 false、copy 仍 None；实际历史 merge `c1447dbddd001b5aa3858c542aec41935d8ba2c7` 的同路径 finding 也不获 copy 准入。
- 新路径不属于 copy anchors；生成 metadata、旧行不变和算法/config 字节比较通过。

私有验证回执：独立 UI review 树 `.audit/v4-1/metadata-review-d6fb87b/result.json`；原 finding 位于 `.audit/v4-1/hash-review-8d1f3fc/author-native.json`。仅此文档提交；未修改扫描实现、metadata、前端或历史 refs，未运行服务/浏览器/网络请求。

Root 报告的 additional_history 原测试13PASS/238deselected及候选 native preflight0属于作者证据，本轮没有重跑该测试集。完整 dir/index/all-reachable history 扫描仍 `NOT_RUN`，由 Root 后续执行；不能以27项精确谓词检查代签完整扫描。

8d1 首次 preflight 仍保留 `pass=false`、helper2、dir native1、index NOT_RUN，失败后误提交事实不因本次例外变成预检通过；不删除或改写旧 ref。本核收不评价后续 push，不关闭 UI04—UI06，也不授予任何真实业务权限。
