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

## 47a 收敛性诊断与严格 merge-copy 候选

Root 的非最终完整扫描 `.audit/v4-0/scan-after-api-47.log` 实际 dir/index 各 5 blocking，git 原生 381 = 132 既核 + 249 blocking。各 refs 当时继续推进，此日志用于发现，不签 Gate。独立按真实 Git parents 拆分：249 = 5 个单父 author finding + 244 个真实多父 merge finding。244 项全部属于下表 12 个精确 path/blob；未逐 merge 追加 244 个 source 指纹。

5 个 author 来源分别是：`31d11cc76c13a7a56afc5fec541b1657dc747cab` 的 `tests/v4/test_demo_sessions_pg.py:151,170,197`（测试参数类型及固定 fixture_version 引用）、`b726949b670153d9b5393225f890f0c919ee6ea5` 的 `docs/v4/review/SCAN_a4f.md:28`（公开 SQL 字段集合说明）、`d57808f0627821ab202e054e7d464fa2d4b9798c` 的 `backend/src/commerceops/infrastructure/v4_demo_sessions.py:133`（capability 派生调用的固定用途标签；csrf_secret 是变量引用，没有读取实际值）。原生有限目录扫描确认 5 项，完整源码用途核为公开非秘密。它们仅作为本提案五个精确新增快照/author 历史条目；尚待 Root/Astra 独审，不自动批准其它 author。

提案保持原 222 rules、79 原精确目录例外及旧全部精确回执，新增 5 后目录共 84。既有 preflight 历史89保留，新增5后该组94。历史临时配置仅移除39个V4目录 blocks，仍与旧222规则/45原生例外语义完全相同，完整 `--all --full-history -m` 不变。

| 固定锚来源 | path | 完整 Git blob |
|---|---|---|
| `63a5a4f08bad6b98fe95942598291e0714bc09da` | `frontend/app/v4/[[...path]]/page.tsx` | `60e878cab70e13abc4e827af83eebdb3ad159ad7` |
| `ea48a13943d269484a4ebe59ca75803bcafe429f` | `tests/e2e/v4/test_strict_response.py` | `1cf5844b8b0f46fc5d0b5e298a28a031b9ca139c` |
| `b726949b670153d9b5393225f890f0c919ee6ea5` | `docs/v4/review/SCAN_a4f.md` | `2150dfeb4328fad138da3dd2636bae8cf81fbdf6` |
| `ea48a13943d269484a4ebe59ca75803bcafe429f` | `tests/e2e/v4/test_supervisor.py` | `b7b18721733539fd615fbef891bac12dc710d27a` |
| `534844a848b7e4412a6b4b2ff178f7d0aa56c82e` | `backend/src/commerceops/infrastructure/v4_demo_sessions.py` | `bf11ab994c683019b83bcf6510daa5ffd9be62a3` |
| `63a5a4f08bad6b98fe95942598291e0714bc09da` | `frontend/lib/v4-context.mjs` | `c05c82b186f1e52f26657fd03ce817472074936c` |
| `534844a848b7e4412a6b4b2ff178f7d0aa56c82e` | `tests/v4/test_demo_sessions_pg.py` | `44bc08da5e49b83563ed8c987ea7e6017ccef0df` |
| `ea48a13943d269484a4ebe59ca75803bcafe429f` | `docs/v4/design/IDENTITY_SQL_PLAN.md` | `b23e358dd29b065ce2229be8a1870c702a5f6e71` |
| `ea48a13943d269484a4ebe59ca75803bcafe429f` | `tests/e2e/v4/http_probe.py` | `d2f7dd62c119b0f1141f26e1786cfa47273a3743` |
| `534844a848b7e4412a6b4b2ff178f7d0aa56c82e` | `docs/v4/design/IDENTITY_SQL_PLAN.md` | `831194f4e26a5ae554e89e1d0d297a64cc863f17` |
| `534844a848b7e4412a6b4b2ff178f7d0aa56c82e` | `backend/migrations/versions/0024_v4_demo_foundation.py` | `018748c90bc4145e3147454052296ea4a8119071` |
| `ea48a13943d269484a4ebe59ca75803bcafe429f` | `backend/migrations/versions/0024_v4_demo_foundation.py` | `2a833ba4021fd76f3ed08b235b802701a1765d4d` |

`approved_v4_merge_copy` 是独立的 git-only 分类分支：先核原生 source SHA 与原生 fingerprint 自洽，再从 Git 对象验证至少两个真实 parent；对相同 path 核 merge blob、固定 anchor source 的真实 blob、清单 blob 三者完全相同。随后仅匹配已登记 rule/path/起止行列/完整 span hash/原生 redacted Match hash，并在 anchor 源文件同位置重核完整 span。未知路径/作者/文件变动/位置与内容变化拒绝，不按任意祖先、相同列名或相同局部值泛化。完整 blob 相同使后续普通 merge 复制相同文件时可收敛，author 或文件修改仍须另审。

固定元数据同时保留先前真实捕获的历史和快照列位置；同一文件在原生 author diff 与 snapshot/merge diff 里的列值可能不同（page 行曾出现42与43），本实现只接受各已登记精确项，不使用±1容差或重新推算列号。首轮只匹配 author 历史列号时，该项被拒绝，保留失败后补用原已审 snapshot 精确列绑定；未改原生报告。

每条 merge 原生 finding 继续完整输出其 merge source/fingerprint，classification 为 reviewed_public_merge_copy，附 merge_anchor.source_commit/blob、finding_source、binding_kind 与精确 finding 绑定。旧 exact finding 分类不减少。既有全历史测试改为保全原 exact 指纹集合、逐一要求所有额外原生 finding 满足新严格 merge-copy 分支，未知项仍使测试失败；不按总数判绿。

候选的收敛性只针对固定锚的完整文件复制；未来 author、新 blob 或未覆盖源始终 blocking。完整freeze全扫 NOT_RUN。本次是兼容 code proposal，Root/Astra 精确核收前不构成批准。没有业务、旧 Harness、PG/API/Web/Docker/Hosted/push 操作；actual cost UNKNOWN。

实际验证记录：首次有限收敛测试 1 FAIL / 4 PASS / 3.99s（author列与snapshot列差异）；下一次1 FAIL / 13.47s为测试误把全refs原日志的244期望用于仅0ca..47祖先范围（实际185），没有未知命中被放过。修正精确范围期望后，真实有限历史185个merge-copy与真实双父Git测试1 PASS / 16.51s；覆盖单父拒绝、错误位置/Match、不同blob、secret追加、锚source错误。另新5 literal及全部快照测试6 PASS / 2.33s。没有重命名或覆盖旧失败。

为验证原日志剩余非47祖先merge，另外只枚举原244条的精确merge source，以每个source^!重取原生发现；244/244精确指纹全部被copy分类，原生输出与各锚绑定保留在 `.audit/v4-0/convergence/`；没有再跑全--all。完整freeze全扫仍NOT_RUN，未捕获的未来author或blob不获任何准入。

补充锚source/path/blob三种篡改的真实Git测试后，单项1 PASS / 15.30s；原244记录对应12个merge来源的限定原生重捕获244/244，18.861s。旧79目录例外、132条既有exact历史记录、全部222规则均逐项与parent核为不变。七文件提案快照自检首遇新增测试参数类型声明误报（仅元数据，无秘密），通过等价的局部MonkeyPatch上下文替代fixture签名消除，没有新增第六个例外；该开发扫描exit1保留。

最终等价测试签名下：收敛/真实Git正负例1 PASS / 16.06s；最终四文件Ruff check/format及mypy均exit0，rules/source/provenance验证0，七文件提案快照原生扫描exit0。以上不等于最终完整dir/index/allrefs扫描，后者仍NOT_RUN。

## 2330 discovery 实际残余及后续 QA 元数据收敛

Root 授权一次 discovery，实际入口源为 `2330bca2e657a236ba5355b940e2f641763d026d` / tree `ddc4d00cc92f4b878e03cd170f8067af7e3aaf88`（目录名保留最初72b标识，不表示扫描固定72b）。唯一实际全扫描 exit1 / 76.601s；dir/index各9原生命中并另有3个固定位置guard失败，git987=777已分类+210blocking。首次包装模块路径 invocation error 在原生扫描启动前失败、零native报告；原失败及本次exit1均保留，不改写为通过。

原证据位于 Root `.audit/v4-0/discovery-72b5143-20261104/`，含native-dir/index/git完整redacted报告、classified.log、before/result、REF_CHANGES。扫描前后Root HEAD/index相同、tracked均干净；全局refs_stable=false，差异为三个Codex临时turn-diffs引用移动，未据此伪签最终Gate。实际manifest `RESIDUAL_METADATA.json` SHA256为 `e2ac056a3341b8015c5c577c89a33379f3d80f002ff425e0b62f4239c631d326`。

Root逐项亲读后仅释放9个dir/index精确span、9个单父author精确history、13个wholeblob候选锚；201个merge残余不逐SHA枚举。全部不同内容核为公开代码/类型/fixture/状态标签/合成输入，未见实际秘密。9个author来源为：385c355 ttl137、2332f7 seedcli72、0476f82 waiter9、8196e62 fixes19/112、1c192d4 sessions262、ce51c42 negatives34/driver484、dc439e9 seedpg380；完整SHA/行列/hash均落固定清单。

| 当前候选目录位置 | 用途 |
|---|---|
| frontend/v4-tests/lifecycle.waiter.mjs:9 | 规范creation request key与tenant比较 |
| tests/e2e/v4/owned_negatives.py:44 | 请求key变量与固定fixture字段 |
| tests/e2e/v4/test_ttl_probe.py:137 | interruption测试内Visitor stub合成key，不是实际身份 |
| tests/e2e/v4/owned_driver.py:666 | 静态pg_api结果标签，原2330位置557 |
| tests/e2e/v4/test_owned_review_fixes.py:19,112 | 固定UUID请求键与pytest类型声明 |
| tests/v4/test_demo_seed_cli.py:72 | 大小写别名负例的pytest类型声明 |
| tests/v4/test_demo_seed_pg.py:380 | 请求键变量与固定fixture_version |
| tests/v4/test_demo_sessions_pg.py:266 | auth_version标识符相等比较 |

原sessions目录绑定151/170/197已独立核完整span哈希不变，仅固定位置更新155/174/201；未删旧author/history记录。新九项后目录93、exact历史146（既有137+9），规则仍222、历史原生例外45，原所有history不可变。只更新三个目录来源/位置，其余旧目录例外不变。

Root另精确补批 a990 owned_driver：source `a990be0d5ac2fc9252adb77cb104d90face9c1ce`，wholeblob `f6838353c14be59c1ae101faf3dda43dd4bb22ae`，file SHA256 `d72e7d3349bfae9256c8b54e0d650bad502ee7a53c6c6842a64a398fef257400`。原557静态span哈希 `257d31b06b9ca99bcf1d666842c5dd8771b960a3aec485e029f620614fe3b267` 不变，现666行10–44；有限单文件原生输出核位置，不做全扫。本锚必须等Astra接受a990代码后才可普通冻结，当前只实现为候选元数据，未声称网络代码已审。

保留2330@557及原manifest中8196@540（blob `767731bd7b730e9bab486339c77ee11b30050370`）为两个明确copy-only绑定，行列10–44及同span/Match hash固定；不增加这两位置的dir或author豁免。其余copy机制不改，必须双父/固定完整blob/固定rule/path/行列/span/Match；新作者、不同blob或secret mutation继续拒绝。13原manifest锚追加a990后为14新增，总26锚。未自动吸纳legacy wrapper或其它未来文件。

增量初步11PASS/3.50s；补540/557边界后13PASS/4.94s。复用原native-git.json作classifier回放210/210=9exact+201copy，无新allrefs扫描；中间191copy/10拒绝结果保留，10均为缺少old540离散绑定而安全拒绝，Root补批后才接入copy-only。最终freeze全扫仍NOT_RUN。当前未commit，等待a990接受条件；actual token/cost UNKNOWN。

### 最终准入与 1684 精确元数据

上段a990@666属于等待独审时的历史候选，已被替代，不在最终锚清单。Astra正式普通回执 `68a0cc3a83fe5a571c55da5620d46944e2e371ba:docs/v4/review/SUBNET_a990.md` 接受 `1684e0455978b46ddad607e09d85a1af5657ab1a`，结论 ACCEPT_PREPARED_EXPLICIT_SUBNET_MODEL / 0 P1 / 0 P2；原a990 P2和失败不改写。Root据此允许本元数据ordinary冻结。

Root最终补批的当前目录记录：owned_driver标签735行10–44，完整span及Match hash与原557/666完全相同，wholeblob `9f168bab0b31f627843d05d65e391b99bc4ca438`；test_owned_review_fixes两个原span完整hash不变，UUID行19列2–45、类型行105列18–48，wholeblob `0b51b2c3775c0052a9f009f857a1cf317d2aaebb`；两者来源均精确1684，不增加其作者提交豁免或新guard测试例外。93个目录例外、146个exact历史、27个wholeblob锚（旧12+manifest13+latest2）及两个557/540 copy-only绑定；a990@666未发现需分类的actual历史，因此不登记copy-only或anchor。

原生单文件/两文件有限定位只发现上述原3项，不据此替代全扫。当前候选有限测试13 PASS / 4.91s；再用原discovery native-git报告回放，210/210=9exact+201copy，UNKNOWN 0，无再次运行allrefs。原history及旧固定scope保持，三项sessions目录移行与两项QA最新位置均以原完整hash不变为前提，不采用模糊找行或未来自动跟随。

功能受测源码 F1 为 `047a43dafef90edea2eb532c2a03b6f850da0b9a` / tree `5c0699edb2d30889ce770ca9b05b56dab957ce10`，由Root另开PG/HTTP/Web窗口。本元数据提交与后续delivery文档是不同source；这里的有限扫描/测试不宣称F1业务已运行，更不宣称F1+未来HEAD全部运行。未为legacy4e文件或未来unknown添加规则；最终freeze full dir/index/git仍由Root统一，NOT_RUN。

ordinary冻结前最终有限验证：13 PASS / 5.53s；四文件Ruff check/format、mypy、规则/source/provenance验证均exit0；仅本提案七变更文件快照原生scan exit0。该结果不是full仓库/refs扫描，也不把原discovery exit1改写为绿。
