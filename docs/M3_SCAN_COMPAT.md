# M3 公开代码行扫描兼容候选

状态：LOCAL_CANDIDATE / AWAITING_ROOT_REVIEW。本候选不代表完整历史扫描、CI或M3验收通过。

## 范围与来源

授权工作树：`commerceops-m3-scan-compat/commerceops-agent`，分支 `codex/m3-scan-compat-20261103`，基线 `44ad22c7a9403e7947d490cfa88eedcd6e73e8b3`。仅扫描生成器、固定规则产物、规则验证/快照检查和定向测试；不修改业务实现。日期为2026-11-03（台北）。

Root提供的既有脱敏报告原生42项，其中20项原历史审批不变，22项M3命中归并为9个“路径＋完整行”组合。相同内容在不同路径分别登记；合并提交造成的重复命中不新增宽泛豁免。

脱敏输入文件：`.audit/m3-s2-history-redacted.json`（Root validation-s2树，只读）；SHA256：`44aa4dcd39b8a73f20e018865e0c3ff741b8ed6e5ee909e9cff7c656a02b1e3e`。

下表每项由 `git show <commit>:<path>` 直接取得完整原始行，以UTF-8行内容（不含行终止符）计算SHA256。完整行内容可在固定源或生成的 `.gitleaks.toml` 中审阅；表内缩写只解释用途，不参与匹配。

| 固定来源commit | 路径 | 行 | 完整行SHA256 | 公开语义 |
| --- | --- | ---: | --- | --- |
| `b63f9bc5efc9b360c872df4ef15481ba15420503` | `frontend/m3-tests/daily-read.fixture.json` | 137 | `9ba1d2eaf28dee54c74df8009dfe068f2205261d884e6eee9b5b816c0dfde3d8` | 日报fixture指标枚举 |
| `b63f9bc5efc9b360c872df4ef15481ba15420503` | `frontend/lib/m3-read-client.ts` | 72 | `7cd875fcc4788e55e5bd0ecb98a6f6a096fa1d4539bad46c62633047ef543c41` | 日报客户端指标枚举 |
| `b4b3c9ea8ab4b60c3406178c7a08e4ca6d3fb9e4` | `frontend/m3-tests/daily-empty.fixture.json` | 140 | `9ba1d2eaf28dee54c74df8009dfe068f2205261d884e6eee9b5b816c0dfde3d8` | 空日报fixture指标枚举 |
| `e1a52d6bfe2739f5890bf04c4bf2aafc36c00fc8` | `backend/src/commerceops/infrastructure/knowledge_copy_repository.py` | 271 | `f88e20474894ad7b68ada1bb12c042aa419747488fdb40bcba47523e5503cd26` | registry JSON字段与SQL列引用 |
| `e1a52d6bfe2739f5890bf04c4bf2aafc36c00fc8` | `backend/migrations/versions/0020_p6_knowledge_copy.py` | 152 | `2016dfbb0029ad7285c16c3169cb895854864410744d51bb89fc5d6592fd7948` | registry JSON字段与SQL列引用 |
| `8a6c6ebb59abf451c810bb6aebcdf1b8f6510e9d` | `backend/migrations/versions/0020_p6_knowledge_copy.py` | 54 | `1e860e56789ea17cf4df6d514d07d28135dd78010d9e9230cc6f1cc2f48464e0` | 知识chunk字段DDL |
| `22b60150add80f59613445260e1e2851b5d0b86f` | `backend/src/commerceops/application/commerce/readonly_inquiry_tools.py` | 199 | `23006e136c68711f9ce3672034e86c0176d21387c04c9824468927b5be39d942` | 共享库存池字段比较 |
| `1a78d5a23fd888265cc8e30dde6c492d8b6c94cc` | `backend/src/commerceops/entrypoints/inquiry_http.py` | 176 | `eaf8d3d2af552e3a55b0f9c3a45ba8dcaf93438deda500af53d3792fcae842cf` | 询单回执路由及OpenAPI操作名 |
| `e2e50f53661a8b07e8bf62f1ad4afa6fe5c769da` | `backend/migrations/versions/0021_p6_readonly_inquiries.py` | 80 | `47034fc2724e57435d98f01be94605e95af668f2f3c865c1bed96b5b9a0e401a` | 会话身份与权限版本列比较 |

## 兼容边界

- 只在 `generic-api-key` 增加9项 `condition=AND`、`regexTarget=line`、完整仓库相对路径与完整行匹配。没有secret级、keyword级或整文件豁免；其他规则保持适用。9条固定源行均为ASCII；正则采用等价的`\xNN`逐字节声明，避免生成配置中的公开列名被扫描器再次误报，不增加配置自豁免。
- 生成与运行前均从固定Git源校验行号/整行hash；缺少commit、行缺失或hash不同即失败。规则产物及provenance逐项绑定source commit/path/line/hash。
- 当前与index快照分别按指定路径、指定行号和完整行hash检查，低熵改动、位置移动同样阻断。未出现的文件不因历史例外而被要求凭空存在；若该文件随后被集成，立即按相同固定行核验。
- Git历史允许同一路径同一完整行跨提交/merge重复；历史中的嵌套同名路径、任意一字节变化或同路径换token不能匹配该例外。新增M3的路径regex从`^`到`$`完整锚定。
- 为支持严格路径，目录扫描在隔离的current/index快照内以`.`执行，让扫描器原生File成为仓库相对路径；原隔离快照内容、index blob采集和Git `--all --full-history -m --text --no-textconv --no-ext-diff`不变。
- 222条规则去掉新增9项后，与基线TOML语义完全一致；原17项例外、原20项历史审批逐项相等。原历史审批JSON（排序键序列化）SHA256为 `9f227547cf4353d08ca6b8f6105b233f9f1c80623bad1f78b487f07e8322531f`。

## 验证账

最终候选验证：

- `python -m pytest -q tests/test_quality_gates.py -k 'not approved_actual_history_findings'`：122 passed / 1 deselected / 115.34s，native0。唯一排除项正是对原仓库完整可达历史的实际扫描，留给Root统一执行。
- `python -m pytest -q tests/test_m3_scan_compat.py`：190 passed / 177.40s，native0；涵盖9条来源的完整行、字节修改、index、行位、其他/嵌套路径、历史变化、merge重复、邻接/同一行通用token、其他规则，以及72项provenance篡改拒绝和逐字符正则等价验证。
- Ruff检查通过；mypy检查3个变更Python文件通过；Markdown检查127files/errors0；Git差异空白检查通过。
- 固定官方上游配置按原SHA256核验后重新生成：222 rules / 26 exact-line exceptions；生成重现及原规则/例外/历史审批语义对比通过。

保留的开发失败与中断：首轮M3为180pass/1fail/184.16s；首轮既有quality为120pass/2fail/1deselected/124.20s。其一是生成配置中的两条公开SQL正则被自身再次误报，已由等价字节转义修复；另两项是把pytest临时目录放在真实仓库内，导致“缺少固定Git源”的测试向上找到父仓库，未能模拟源缺失。M3负例现显式初始化空仓库；最终既有回归使用仓库外临时目录。一次仍用仓库内临时目录的后续quality运行主动中断于13pass/1deselected/17.91s，保留KeyboardInterrupt，不算通过。首轮运行期间有开发修改，不作为最终冻结源码证据。

日志保留于本工作树 `.audit/m3-targeted-tests.log`、`.audit/quality-regression.log`、`.audit/quality-final.log`、`.audit/m3-final-tests.log`、`.audit/quality-final-external-temp.log`。本轮没有运行原仓库全历史扫描；Root应在独审精确提交后统一扫描集成候选。

公开行只是候选例外，须Root独审才可合入。业务作者后续若调整这些行或行位，当前/index会如实阻断，不能用本候选替变动后的行签字。保留Root已记录的3126pass/5fail与原native42事实，不改写成已通过。


## K2稳定行位增量（2026-11-03）

Root已转交bcf独审结论`ACCEPT_EXACT_ROW_EXCEPTIONS`（独立20项反例通过、9项源hash、222规则及原17/20保持均核）；完整集成扫描仍被后续业务源码行位变化阻断，不能写为scan通过。

本增量只将两项来源重绑定到精确已提交的 `e1a52d6bfe2739f5890bf04c4bf2aafc36c00fc8`：knowledge_copy_repository原257→271、0020 registry JSON原142→152。分别直接读取旧 `8a6c6ebb59abf451c810bb6aebcdf1b8f6510e9d` 与e1的完整行并逐字节相等，完整行hash、path与regex完全不变；原始来源仍由本段及bcf提交保留。采用固定新commit/path/line/hash，不引入无行号搜索或第二套定位机制。0020的另一条54行仍按原准确来源保留。

0021行位已被Root报告发生变化，但新fix尚未交精确提交，仍保留原72行pin并显式待最新源码稳定；不能据此增量声称当前全部集成scan畅通。本增量不重跑190项或主仓库全历史扫描，最终全source稳定后由Root统一scan。

增量定向验证：11 passed / 13.06s / native0（两条新行位的exact/index/moved/history-byte、逐字节正则及固定来源缺失拒绝）；日志`.audit/k2-pin-targeted.log`。直接用完整e1源文件生成dir/index两快照均无违规，分别追加一个字节均被拒绝。校验`.gitleaks.toml`与bcf字节完全相同，provenance仅两项source_commit/source_line改变；Ruff、Markdown127files/errors0及Git差异空白检查通过。原190/122测试账仅绑定bcf原候选，不转签本次新pin提交。


## 0021已审e2行位增量（2026-11-03）

Root在runtime实施放行中明确转交已独审接受的 `e2e50f53661a8b07e8bf62f1ad4afa6fe5c769da`。仅把0021会话身份/权限版本列比较的固定来源由原 `1a78d5a23fd888265cc8e30dde6c492d8b6c94cc` 第72行重绑定至e2第80行；直接读两份Git源，完整行逐字节相同，hash仍为 `47034fc2724e57435d98f01be94605e95af668f2f3c865c1bed96b5b9a0e401a`。path、完整行regex、所有规则和20项原历史审批不变。

本增量不改runtime交付，不把后续未由Root明确转交的提交作为批准来源；S3或后续业务源码若再变行位仍应阻断，待最终全source稳定后Root统一扫描。上一K2段“待最新0021”的标记为原时点，本节仅更新已审e2的pin。

增量验证：6 passed / 5.79s / native0，日志`.audit/0021-pin-targeted.log`；覆盖新80行exact/index/moved/history-byte、正则逐字节及固定源缺失拒绝。完整e2源文件的dir/index快照通过，分别追加一字节均拒绝；`.gitleaks.toml`仍与51逐字节相同，provenance只改此一项source_commit/source_line。Ruff、Markdown127files/errors0及Git空白检查通过。不重复190项或主库全历史扫描，不宣称最终集成scan畅通。
