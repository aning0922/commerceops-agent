# V4原13项公开字面量扫描兼容独立审查

日期：2026-11-03（Asia/Taipei）。结论：**ACCEPT_SCOPED_CODE（原13项兼容源码，无P1/P2）；CURRENT_FULL_SCAN_FAIL保持。** 此结论允许ROOT按授权核收该窄切片，不签完整扫描、B工程检查或V4本地Gate通过。

## 精确源与范围

- candidate：`8ab1c1b17c81b28806047756c916d69b28f3e3c7`。
- tree：`124066476b1ce88b19c080a02dca0384475ab116`。
- parent：`7c262fbf6fa48412cbd80a9afb65147e93a7033e`；tree `d11a2cc2714abae1a2f66e2f7567802f19446155`。
- 固定公开源：`fa96764cf2b8e3ab9adbb579b764f600a7d17e60`。
- 七变更路径：`.gitleaks.toml`、`scripts/gitleaks_rules.json`、`scripts/scan_secrets.py`、`scripts/vendor_gitleaks_rules.py`、`tests/test_quality_gates.py`、`tests/test_v4_scan_compat.py`、`docs/v4/acceptance/v4-0/SCAN_COMPAT.md`。

全部读取精确Git对象，未读SECURITY_SCAN WIP，未checkout/合入作者源码。独立完成diff审阅、标准库AST/JSON/TOML语义及固定源SHA-256检查；没有导入执行仓库模块，没有执行Gitleaks/pytest/工具链或任何服务。源码审查与作者实际验证分列。

## 独立静态核验结果

1. **旧规则未放宽。** 解析父/候选TOML，规则数量均222，allowlists为45→58。从候选generic-api-key删除末尾13项（保留其原44项与另一规则原1项）后，整个TOML语义对象与父提交相等，包括所有原规则字段与原例外，不只是计数相同。未发现新增全局allowlist/目录级豁免或改规则宽度。
2. **原审批/provenance未重写。** 候选provenance前45 exceptions与父完整exceptions逐字段相等；historical_findings原20条逐字段相等；`scan_secrets.py`的APPROVED_TEST_HISTORY经AST literal解析亦与父相同。新增V4的13历史记录另置v4_historical_findings，没有覆盖旧20。
3. **固定源可复核。** generator的13项均固定fa commit与path/起止行/hash。独立逐项git show固定源，LF连接完整span后计算SHA-256，13/13与常量/provenance相符；逐项重构Unicode codepoint精确正则，与生成配置相同。未打印来源行或任何Match/Secret原文。此项验证完整span，不声称独立重新捕获了Gitleaks redacted Match。
4. **dir/index双层限制。** `vendor_gitleaks_rules.py:456–476`拒绝缺源/错误span，生成path AND完整行/span精确regex。`scan_secrets.py:339–511`核规则/provenance；`:635–679`在实际snapshot上核固定行号/hash，并拒绝相同approved span在未登记行号重复。`:719–748`分别构造current与实际index blob快照并执行guard，不能用工作区恢复掩盖仅index变化。修改内容/移行/重复不能只依赖原生line allowlist逃逸。
5. **历史匹配没有被新增例外吞掉。** `scan_secrets.py:514–533`用固定表标记移除恰13块，并比较完整派生TOML与仅截去新13的expected相等；删除错误表/额外规则会失败。`:760–788`仅git模式用该派生配置，保留全部旧规则/45例外；`--all --full-history -m --text --no-textconv --no-ext-diff`、空ignore和`--ignore-gitleaks-allow`均保留。因此不是通过让原生扫描少报新13来消除阻断。
6. **历史批准是窄分类。** `approved_v4_history_finding:536–565`仅git接受，逐项比较RuleID/File/Commit/起止行列/Fingerprint，再核redacted Match hash及固定源span。错commit/path/位置/Match均不能按此类别批准；dir/index不使用该历史批准。新记录的完整span哈希通过固定源读取验证，不由输入finding自行宣告可信。
7. **新未知项继续失败。** `scan:793–830`校验原生退出码与findings一致，所有finding继续输出安全分类；`len(findings)>reviewed`保持blocking和非零。原生结果与reviewed计数分列，没有吞掉原生exit1。未发现把新增10自动加入本次13批准集合。

源码性质边界：history_config的语义相等检查证明相对已验证配置只去掉新13，不是对任意恶意改动配置的独立完整签名；正常scan入口先validate_rules。两层结合是本次受审调用路径，不把单独函数当整个信任边界。

## 测试源码审查（未运行）

`tests/test_v4_scan_compat.py`：

- :64–86原生dir/index正例及派生配置对父完整语义相等、222/45/58与旧provenance守恒。
- :89–115每项内容修改、移行、重复、仅index变化、同一行新key拒绝；index_only将工作区还原，明确断言仍由index阻断。
- :118–148其他路径/嵌套路径/邻接新key/其他规则，以及相同公开字节来自不同commit的原生负例；不输出生成的key值。
- :151–186每项provenance路径/regex/AND条件/source/行范围/hash篡改拒绝；:189–191缺固定source拒绝。
- :194–209不可信Match及非git scope拒绝；正向原生历史接受由现有全历史测试及作者扫描记录覆盖。不能将此合成fake负例冒称原生13项正向证明。
- :212–234派生配置标记缺失、误标旧allowance、规则结构变更拒绝；:237–245双行span任一行变化拒绝。

`tests/test_quality_gates.py:600–653`仍实际跑完整原生history，旧20和新13分别计数，逐finding必须被精确批准，篡改字段拒绝。没有用subset断言跳过未知记录；当存在新增10时，该全历史断言仍不应通过。未见为了新13删除旧负例。

## 作者证据与未验边界

以下来源为该commit的`docs/v4/acceptance/v4-0/SCAN_COMPAT.md`，是作者记录，不是Reviewer复跑：

- 初次ROOT dir/index各13 blocking、git33=旧20+新13；保留原失败。
- 修订后的全扫dir0/index0，git原生43，reviewed33=旧20+fa13，新增10 blocking，整体exit1。**当前完整扫描仍FAIL。** 全历史reachable refs可随并行提交变化，43只是该次观察，不是未来常数。
- 稳定矩阵164 PASS/246.58s，补测4 PASS/0.70s；Ruff/format和四文件mypy记录exit0。Reviewer未读私有.audit日志，也未重新执行这些命令。
- 首派生表边界错误、redacted Match hash不匹配，以及92 FAIL/72 PASS保留；后续成功不覆盖首失败。旧兼容回归/完整实际history断言未核收。

redacted Match哈希与原生43条结果的真实性在本审查仅有tracked作者记录和源码绑定，未独立重捕获；因此本结论限于窄源码/配置接受及静态固定源核验，不能出具独立运行PASS。新增10须另获窄授权、独立精确来源/差异/负例与新提交审查，不能混进这13或追溯篡改fa记录。

## 交接与后续

ROOT可核收原13兼容代码；整体Full扫描不准入。Backend身份SQL若转交则优先审关键路径；本审查不占用或开放PG/Web窗口。后续代码/配置发生变化须重新绑定SHA，保留此首轮结论及失败账；Reviewer未代作者修改实现或测试。
