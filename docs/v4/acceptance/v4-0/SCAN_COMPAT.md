# V4-0 精确公开字面量扫描兼容

2026-11-03，台北。本切片仅处理 ROOT 首次日志中 A 原件的 13 个公开非秘密命中；独立审查与 ROOT 核收仍待精确提交回执。actual token/cost UNKNOWN。

基线为 `7c262fbf6fa48412cbd80a9afb65147e93a7033e` / tree `d11a2cc2714abae1a2f66e2f7567802f19446155`。只普通提交，不改 A 原件、业务、前端、workflow 或锁文件。

## 来源与分类

固定导入来源 `fa96764cf2b8e3ab9adbb579b764f600a7d17e60`。首次 `.audit/v4-0/initial-docs-scan.log` 在 ROOT control 工作树，dir/index 各 13 blocking；git 33 = 原已核 20 + 本次 13 blocking，均保留。独立原生目录重捕获确认 13 项为：请求字段名 1、费用 UNKNOWN 说明跨两行 1、公开文件摘要 2、OpenAPI 认证阶段枚举 2、API 清单权限枚举 6、合同文件名 1。没有凭据。

下表 SHA256 为完整行或完整 span 的 UTF-8 字节哈希；多行以 LF 连接。每项还固定 Gitleaks redacted Match 哈希、起止列、源提交与精确历史指纹，详见生成器固定清单及 `scripts/gitleaks_rules.json`。

| path（相对仓库） | span | SHA256 |
|---|---|---|
| `docs/v4/baseline/API_EVENTS_CONTRACT.md` | 14–14 | `528898a328812d86eb33d61c91e19abeded3af2a10f3f704e8a08e4ed37bca2d` |
| `docs/v4/baseline/evidence/A_EXECUTION_RECEIPT.json` | 5–6 | `56ac6716fc7063f773d8f0bdfa2c06e127018b85e8145add1b2f96ec05825be0` |
| `docs/v4/baseline/evidence/CONTRACT_REVIEW_CANDIDATE_HASHES.json` | 5–5 | `856cb9d6ff038755db512d1f403343e4edd2582bd34d31327e83a34bf8f30830` |
| `docs/v4/baseline/evidence/CONTRACT_REVIEW_CANDIDATE_HASHES.json` | 9–9 | `73132a728480edc215e784b5a744c975d92faa6d5fc8b59dc3f08f7774b712b2` |
| `docs/v4/baseline/reviews/M3_API_INVENTORY.json` | 42–42 | `980ed41784decd653ab8f0c989e736cc46433f8370327eb52007dabe73cf9020` |
| `docs/v4/baseline/reviews/M3_API_INVENTORY.json` | 64–64 | `980ed41784decd653ab8f0c989e736cc46433f8370327eb52007dabe73cf9020` |
| `docs/v4/baseline/reviews/M3_API_INVENTORY.json` | 86–86 | `980ed41784decd653ab8f0c989e736cc46433f8370327eb52007dabe73cf9020` |
| `docs/v4/baseline/reviews/M3_API_INVENTORY.json` | 108–108 | `980ed41784decd653ab8f0c989e736cc46433f8370327eb52007dabe73cf9020` |
| `docs/v4/baseline/reviews/M3_API_INVENTORY.json` | 130–130 | `980ed41784decd653ab8f0c989e736cc46433f8370327eb52007dabe73cf9020` |
| `docs/v4/baseline/reviews/M3_API_INVENTORY.json` | 152–152 | `980ed41784decd653ab8f0c989e736cc46433f8370327eb52007dabe73cf9020` |
| `docs/v4/baseline/reviews/M3_API_INVENTORY.json` | 18512–18512 | `d85fa80d9bbc30593eca344f3779926519709f713c5fec429acde709c30ac6aa` |
| `docs/v4/baseline/v4-public-openapi.json` | 99–99 | `8be6f4bca3a1da670fce95c06c6934451902ee33de2192f7eaa5b3a2c124be87` |
| `docs/v4/baseline/v4-public-openapi.json` | 251–251 | `8be6f4bca3a1da670fce95c06c6934451902ee33de2192f7eaa5b3a2c124be87` |

## 实现约束

沿用原 generator/provenance/source 机制：222 条规则与原规则定义不变，旧 45 个精确例外及旧 20 个历史回执原样保留。dir/index 增为 58 个 path AND 完整行/span 例外；同时核固定行号与完整 span 哈希，原行保留但另处复制同字面量也阻断。Unicode 整行采用确定 codepoint 转义生成，避免配置自生误报。

历史原生扫描使用临时派生配置，仅移除新 13 个 V4 例外；解析后的完整配置必须等于保留全部规则和旧 45 例外的预期，否则拒绝运行。`--all --full-history -m --text --no-textconv --no-ext-diff`、空 ignore 与 `--ignore-gitleaks-allow` 保留。fa 原 13 个原生 finding 继续输出，只在精确 source/path/起止行列/Match/span/hash/fingerprint 全一致时标为 `reviewed_public_false_positive`；新来源或变化仍 blocking。原旧历史列表定义不变，新增 V4 回执放在独立字段。

## 验证与限制

工具为 ROOT 本批已 bootstrap 的公开 Gitleaks 8.30.1 副本，两边 SHA256 均 `ba52fb1bfabbcde42f032afad3d6e0b19dff8ed105229a16e7caa338bbc0e84f`；依赖按现有锁 `uv sync --frozen --group dev` 安装。

实际全仓扫描 `.audit/v4-0/compat-scan-corrected.log`：dir 0 / index 0；git 原生 43，reviewed 33（旧 20 + fa 13）、blocking 10，整体 exit 1。并行提交新增的 10 个历史 finding 不在本切片批准 13 内，安全 metadata 已交 ROOT，仍阻断。不能以本切片宣称全扫描或 V4 Gate 通过。

开发中保留：首派生配置表边界错误与 redacted Match 哈希不匹配造成的失败；已修为完整配置语义等价检查及原生 redacted 哈希。首次测试在生成文件更新期间运行，保留 92 FAIL / 72 PASS，后续稳定源码复验另记，不能覆盖旧失败。

纯测试覆盖每项改内容/移行/重复行/仅 index 变化/同一行新 key、其它路径/嵌套路径/相邻新 key/其它规则/相同文本不同提交来源、provenance 篡改与缺来源、两行 span 任一行变化、派生配置完整规则与旧例外保留。类型和 lint 检查仅四个受影响 Python 文件。PG/API/Web/Docker/Hosted/真实业务调用未运行。

稳定源码复验：V4 主矩阵 164 PASS / 246.58s，加派生配置与双行 span 补测 4 PASS / 0.70s（合计 168 PASS）；Ruff check/format 与四文件 mypy 均 exit 0。旧扫描兼容回归运行中，完整实际历史断言因上述未知项仍不核收。本切片不代签独立审查及 ROOT 整体应用 Gate。

## ROOT 追加的十个历史精确回执

原 13 切片冻结于 `8ab1c1b17c81b28806047756c916d69b28f3e3c7` / tree `124066476b1ce88b19c080a02dca0384475ab116` 后，ROOT 明确追加这 10 个位置的只读核验及非秘密精确兼容。先前全扫 10 blocking 的事实不变。已逐一原生扫描各提交 diff，核实其完整行/span 与 redacted Match 哈希：UI 局部 storage 槽位命名及 Context 比较表达式 2，三次 Ledger 提交的授权标签/工作树名称 6，公开 OpenAPI 认证阶段枚举复制 2。均为公开元数据或代码，非凭据。

| source | path | span | 完整 span SHA256 |
|---|---|---|---|
| `c5f4d101339fed02c463c6dc8058bb92b15881ca` | `frontend/components/v4/demo.tsx` | 7–7 | `321c40305b3977373aa33cad247d66eccb91a9af3b6d5ef861d390d49d221456` |
| `c5f4d101339fed02c463c6dc8058bb92b15881ca` | `frontend/components/v4/demo.tsx` | 10–10 | `717bd4cc248808ee824f89a7f1ee644900867102a54b02047a819e046f802327` |
| `75dc6d55e386d85713943df0fb7a0b3ba5fef053` | `docs/v4/acceptance/v4-0/ROOT_LEDGER.json` | 3–3 | `b534727572b8f90d8e830a2426d3f752ce045406e215feea1448ccded811170a` |
| `75dc6d55e386d85713943df0fb7a0b3ba5fef053` | `docs/v4/acceptance/v4-0/ROOT_LEDGER.json` | 16–16 | `6bac7811165742126d23b6f218b46bc50a1444074921788996ae76230be0f9b6` |
| `772f95927546dc3c648b58cd3906f91cae64c2f4` | `docs/v4/acceptance/v4-0/ROOT_LEDGER.json` | 3–3 | `b534727572b8f90d8e830a2426d3f752ce045406e215feea1448ccded811170a` |
| `772f95927546dc3c648b58cd3906f91cae64c2f4` | `docs/v4/acceptance/v4-0/ROOT_LEDGER.json` | 16–16 | `6bac7811165742126d23b6f218b46bc50a1444074921788996ae76230be0f9b6` |
| `46e44e5548d720bdb735e2a0f4673bdc73854de4` | `docs/v4/acceptance/v4-0/ROOT_LEDGER.json` | 3–3 | `b534727572b8f90d8e830a2426d3f752ce045406e215feea1448ccded811170a` |
| `46e44e5548d720bdb735e2a0f4673bdc73854de4` | `docs/v4/acceptance/v4-0/ROOT_LEDGER.json` | 16–16 | `6bac7811165742126d23b6f218b46bc50a1444074921788996ae76230be0f9b6` |
| `48c30d224529319d5a9ff203429eeff86060fc00` | `frontend/lib/v4-openapi.json` | 99–99 | `8be6f4bca3a1da670fce95c06c6934451902ee33de2192f7eaa5b3a2c124be87` |
| `48c30d224529319d5a9ff203429eeff86060fc00` | `frontend/lib/v4-openapi.json` | 251–251 | `8be6f4bca3a1da670fce95c06c6934451902ee33de2192f7eaa5b3a2c124be87` |

这 10 项仅增加独立的 `v4_additional_historical_findings` 固定回执，不增加目录/索引例外；仍为 222 规则、58 目录例外、45 历史原生例外、旧 20 + fa 13 + 追加 10 个精确历史分类。当前 UI/Ledger/DTO 的等价写法修正由原作者负责，本会话没有修改其原件。

增量验证只跑对应提交的真实原生扫描与相关边界：每项准确识别、不同 scope、任一报告字段变化、缺失源、来源/行/span/hash/fingerprint provenance 变化均拒绝。最终完整全仓/全历史扫描由 ROOT 在冻结集成源码上统一执行；本增量不以限提交扫描代签完整 Gate。

追加验证实际结果：17 PASS / 8.81s（原生五个新提交 + 边界与配置），fa 原 13 项的原生历史字段验证另 1 PASS / 0.81s；四个受影响 Python 文件 Ruff check/format 与 mypy exit 0。全仓历史实际断言仍交 ROOT 冻结后执行，未把限提交结果记作全扫通过。

旧扫描回归一轮：342 PASS / 1 FAIL / 1 deselected / 384.70s，日志 `.audit/v4-0/existing-scan-tests.log`。排除项是实际全可达历史严格断言，已由此前真实全扫的阻断结果分列；没有删除或放宽该断言。唯一失败 `same_line_generic-4` 实际捕获被抑制的 scanner 异常及 exit 2，发生于生成文件曾更新的运行期间，具体异常 UNKNOWN，不能冒称已定位根因。仅该节点后续稳定复验结果另列，未重跑整套。

唯一失败节点稳定复验：1 PASS / 2.93s，日志 `.audit/v4-0/existing-single-recheck.log`；原失败仍保留。

## ea48 / WEB63a 差异预检的限定兼容提案

ROOT 后续明确释放本节 code proposal：只处理本批 `.audit/v4-0/diff-preflight/SAFE_METADATA.json` 中已核公开的 21 个快照 span 与 89 条未批准历史指纹。候选来源严格限定 Root `ea48a13943d269484a4ebe59ca75803bcafe429f` / tree `4c9b6a4721510e631a8e76484890c163e482d5c8` 与 WEB `63a5a4f08bad6b98fe95942598291e0714bc09da` / tree `97425fb41939d9dfe7d5df74cd6889ae14c8e094`。不自动吸纳后续提交；ROOT/Astra 独审核收前不构成批准放行。

限定差异预检实际结果：Root 相对 0ca 的 43 个变更文件快照 16 blocking；限定历史原生 90 = 既批 6 + 新增 84。WEB 相对 eb82 的 18 个变更文件快照 5 blocking；限定历史原生 9 = 既批 4 + 新增 5。原生每次约 0.3–0.5 秒；相对路径模式复核仍为 16/5，保留最初绝对路径报告。最初 helper 的相对模块调用失败亦保留，无扫描结果，不计通过。

所有新增命中均核为公开 SQL 列名/字段集合/身份版本比较、代码参数或测试声明。`test_strict_response.py:12` 的 KEY 是固定 UUID 形状的请求键测试输入，不是认证密钥；`http_probe.py:394` 位于 security_negatives，以错误 CSRF 验证拒绝路径，明确是 wrong 类负例而非有效凭据。两者均按完整字面量所在行及固定来源哈希绑定，未来输入变化或复制到新行仍拒绝；不因“测试”目录或 UUID 形状普遍放行。

| source | path | span | 完整 span SHA256 |
|---|---|---|---|
| `ea48a13` | `tests/e2e/v4/test_supervisor.py` | 122–122 | `41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada` |
| `ea48a13` | `tests/e2e/v4/test_strict_response.py` | 12–12 | `5169b3e622b57a31fd6f1c0ed6d30dc248ff619f8ad27cf1194650cdedd5c086` |
| `ea48a13` | `tests/e2e/v4/http_probe.py` | 147–147 | `f0a75f3531c1a6d29e73bd06c38c0ee551bc3a843a5076f375c084aaa945ff60` |
| `ea48a13` | `tests/e2e/v4/http_probe.py` | 259–259 | `ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad` |
| `ea48a13` | `tests/e2e/v4/http_probe.py` | 364–364 | `ae7a43d4ee06372ed185ad4903d4027b019261c2b1a440d17f3c6f7c723bafad` |
| `ea48a13` | `tests/e2e/v4/http_probe.py` | 394–394 | `98343f326c7a7ac310fdaebc46b4d8e5bf4a16ce59378d93cef92ae78d737ae0` |
| `ea48a13` | `docs/v4/design/IDENTITY_SQL_PLAN.md` | 139–140 | `d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04` |
| `ea48a13` | `docs/v4/design/IDENTITY_SQL_PLAN.md` | 264–264 | `94d8b49b7c0e29f1e51727b7403ee56ef0505b714e81b7dced8b039e318849e9` |
| `ea48a13` | `backend/migrations/versions/0024_v4_demo_foundation.py` | 118–119 | `d32e643a41e2c46dd09b827f2c1af13fbc734453ed5cb1d5826873b0908ffd04` |
| `ea48a13` | `backend/migrations/versions/0024_v4_demo_foundation.py` | 220–220 | `717aecdd18fac4e6cc7b9a057f6cf59741beb662440a475f267c9cdabe243e8c` |
| `ea48a13` | `backend/migrations/versions/0024_v4_demo_foundation.py` | 222–222 | `04a90c4bd9c229c2d68c406fa4d367e18912ab5a1e357e9526792100866429ae` |
| `ea48a13` | `backend/migrations/versions/0024_v4_demo_foundation.py` | 351–351 | `0385f1ec491185e384352946f893e8aed2373023b7ac5c2967d1da50068d1273` |
| `ea48a13` | `backend/migrations/versions/0024_v4_demo_foundation.py` | 367–367 | `b40316de11ee2760c5bca9ed70dfdf7885f89ec90d8db77d8e4d76fdc3bd3987` |
| `ea48a13` | `backend/migrations/versions/0024_v4_demo_foundation.py` | 385–385 | `0f62de7a54e402563bc2e792481dc68b87b6b034d6cf6d9175d5f508b4d9c967` |
| `ea48a13` | `backend/migrations/versions/0024_v4_demo_foundation.py` | 406–406 | `f14569df8150ea3f77d091db08ed46777d518c2cb3eb7ca7ed14861bcec3a7e3` |
| `ea48a13` | `backend/migrations/versions/0024_v4_demo_foundation.py` | 430–430 | `0953ddca366332aa9054120e733607b99fefbbcff21e510141df6b51a46caf29` |
| `63a5a4f` | `frontend/app/v4/[[...path]]/page.tsx` | 9–9 | `87405b72cf4ecad5f2e883918142fa6809f7b0c973fc89881eb429f190a5b64b` |
| `63a5a4f` | `frontend/lib/v4-context.mjs` | 77–77 | `10276796f6bda05e7e2bcdb7ba240bc70434b286e424249179685824a34a3363` |
| `63a5a4f` | `frontend/lib/v4-context.mjs` | 83–83 | `18359ea69216630545f3f39be29b1adf9b5e072e691c5fe13c9165dd8778589e` |
| `63a5a4f` | `frontend/lib/v4-context.mjs` | 89–89 | `18359ea69216630545f3f39be29b1adf9b5e072e691c5fe13c9165dd8778589e` |
| `63a5a4f` | `frontend/lib/v4-context.mjs` | 112–112 | `a8b7d2dab131363a39ecd7bb344cb3be1b99800aff98441d94b6e669bb0ff97d` |

固定清单 `V4_PREFLIGHT_SNAPSHOTS` 另存起止列与 redacted Match 哈希；89 条历史记录在 `V4_PREFLIGHT_HISTORY` 逐条绑定完整源 SHA、路径、起止行列、完整 span/Match 哈希，并从固定字段构造精确指纹。它们包含 merge -m 重复与一个旧 SQL 字段集合语法变体，均未按同值归并成未来来源豁免。

原 222 条规则、58 个旧目录例外、旧 45 个历史原生例外、旧 20/fa13/追加10 历史回执全部保留。新增目录提案合计 79 个例外，仍逐路径 AND 完整行/span，并在 dir/index 快照检查固定行与完整内容哈希、拒绝新增重复位置。历史临时配置只移除 34 个 V4 目录例外，其解析结果必须与旧 222 规则/45 例外相同；`--all --full-history -m --text --no-textconv --no-ext-diff` 不变。任何未列来源/新秘密仍 blocking。

增量仅验证限定提交/快照和相关负例，不重复前批数分钟完整矩阵。最终 freeze 后完整目录/索引/allrefs 扫描 **NOT_RUN**，仍由 ROOT 统一；本提案不代签整体 Gate。未改业务/DDL/前端/锁/workflow，未运行 PG/API/Web/Docker/Hosted，actual token/cost UNKNOWN。

本增量实际验证：33 PASS / 16.84s，日志 `.audit/v4-0/preflight-compat-tests.log`。包括 21 项逐 span 改内容/移行/重复位置拒绝与真实原生 secret-mutation、两组限定历史原生 90/9 精确分类及来源/行列/Match/指纹篡改拒绝、altered-source 拒绝、provenance 变动拒绝、完整规则与前 58 例外/既有历史原件保持。开发首轮 Ruff 长行与测试类型检查失败已修；最终四文件 Ruff/type 结果另据实际记录，不覆盖失败。

精确授权输入 SAFE_METADATA.json 的 SHA256：`858a31d5b0987091e0cd82a2fdfcd10a03097ca1c68ed3d1cb368445044f4d73`；89 指纹集合与生成器固定清单逐项相等。最终四文件 Ruff check/format 与 mypy 均 exit 0；rules/source/provenance 验证 exit 0；本提案七个变更文件组成的独立快照实际原生扫描 exit 0（不代表完整仓库）。
