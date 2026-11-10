# QA business mobile 父收验独立源码审查

2026-11-04（台北）。结论：`HOLD / THREE_P2_BINDING_GAPS`。精确提交 `9726885d101c6bdcee6c2ac052d489b3dbefca83`，tree `33e0da1b6d9cbc278341852312f77474d0b5f638`，parent `2ae73562effbabbee2092a1ff249fc43fe5f288c`。仅两路径变更：`tests/e2e/v41/browser_shell.py` 与对应 `test_browser_shell.py`。本审查聚焦新增父校验及必要原始 request/subject/final_facts 接点，不重复 Main 的业务 mobile spec 全审，不读取后续 QA WIP。

## P2-1：批量串行证据未与原 journal 跨 key 顺序绑定

定位 browser_shell.py:1129–1159、1444–1476。mobile_journal 只保留每个 key 自己的三个状态；batch 后续检查的是 safe receipt 自报 post_ordinal 与 timing 大小关系，没有保留和比较原 journal 的跨 key 行序。独立反例将第二个批量 key 的 ATTEMPT_STARTED 从原位置移到第一个 key 的 COMMITTED_READBACK 之前，其余 request/hash、每 key 状态及 safe serial_evidence 不变，validate_business_mobile 仍接受并返回 confirmed_keys=9/png_count=32。

这使原始追加日志已经显示“前项读回完成前启动后项”时，父层仍能确认串行读回；不需要伪造新 key 或修改 counts。应只读保留原 journal 行序/事件索引，将 batch keys、post_ordinal 与实际 dispatch 顺序交叉核对，并要求前 key 的 COMMITTED_READBACK 早于后 key 的 ATTEMPT_STARTED。原 timing 不等式继续保留，但不能抵消原 journal 中的矛盾。新增这一相反顺序拒绝用例；不得重写或二次消费原 journal。

## P2-2：导入链的文件与 preview 状态可内部自洽但违背原请求

定位 browser_shell.py:1305–1315、1331–1360、1482–1522。CSV/XLSX 检查主要在 mobile 回执自身的 file_digest/job/upload 字段之间比较，未把这些 file_digest 与原 journal 请求 body.file_base64 的实际字节 hash 相连。独立先把原 synthetic fixture 的各 file_digest 统一归一为原文件字节的真实 SHA-256，再把 mobile 内全部 digest 一致替为另一个合法 64 位摘要；原 journal 及 request_body_sha256 不动，仍获接受。另一个独立否例只将一个 preview operation.status 改成 UNKNOWN，原 journal 保持 ACK_OK/COMMITTED_READBACK，也仍获接受。

父层不能因此证明截图/读回属于原上传文件，或证明 preview 自报状态与实际 ACK 一致。应从已核原 request 计算文件 digest，绑定 discovery→mapped→confirm 的同 scope、原 parent/job/version、原文件 digest 与需要的 job digest，再交叉绑定 readback/upload/screenshot。逐 operation 状态应与 journal ACK 语义匹配：preview 的 ACK_OK 可以合法，但不得把 UNKNOWN 或业务 COMMITTED 混为同一事实。增加合法格式但错误文件 digest，以及 preview status/ACK 矛盾拒绝用例。原 final_facts 对 DB canonical request 的核对仍在；该 SQL 核对没有接收 mobile 回执，不能替上述 mobile 字段完成绑定。

## P2-3：截图来源可跨已注册 scope，部分 snapshot 可为空

定位 browser_shell.py:1230–1236、1507–1522。通用 screenshot source 只要求 scope 属于某一个已注册 scope、snapshot 或 job 是 dict；mapping 的特定检查只比 job id 与 file digest，没有比该截图 scope 和对应 import chain scope。独立在同 journal 加入第二个合法 scope 登记，仅把 CSV mapping 三宽截图 source.context 改到该 scope，operation/readback/job/digest 保持原 scope，仍获接受。另一个否例将 product_list 三宽 source.snapshot 全改为空对象，也仍获接受。

因此已有合法 scope 不能充当另一业务画面的来源，空 snapshot 也不足以证明真实列表读回。应按 state 核必需来源形状及真实 snapshot/revision/source 字段，并将截图的 scope、route/resource 与该状态对应的同一次业务读回绑定；CSV/XLSX mapping 和最终 readback 均需同链 scope/revision/job/digest。不要只加一个“来源已核”boolean，也不要靠同 source_sha 将多次或不同 scope 证据求和。增加“另一合法 scope”和空来源拒绝测试，保留原三宽覆盖与唯一 state/width 要求。

## 已核保留项与证据边界

新增校验按 business 标签接入 validate_receipts，先有原 source SHA/tree/scope 检查。mobile_journal 读取原 private journal，不调用 registry，不消费新业务操作；独立复现逐次比较调用前后 journal 字节全同。原 request 必须为对应严格 DTO 的 POST，path/key/scope/epoch/generation 与 canonical request hash 核验保留；重复 dispatch、每 key 不完整或 UNKNOWN journal 被拒绝。原 subject import、final_facts、SharedSupervisor、config、fixture、backend 未被这次差分修改；原 SQL 逐 key 的真实 receipt/effect/canonical request 校验不能降低，也不因新增 mobile counts 而被替换。

源码确实要求三宽各 8 state，加 390 的 8 extras，共 32 个唯一截图条目；路径固定到本 case，canonical/private 文件、PNG 签名/IHDR/hash、DPR 与像素几何受检。这里是文件头及来源约束，不是视觉验收；原 pure fixture 明确使用 24 字节合成 PNG 头，不能把其通过当作真实图像或显示内容证明。anonymous 标记必须声明非 403/revocation；本次没有把 anonymous 扩大为撤权验收。keys/pending/proofs 精确集合、counts 从已列 operation 动态推导、mobile 子集、selected 两唯一 ID/current-page membership/CAS 链和四类进度已有检查，但不足以弥补上述交叉绑定反例。旧 Native pin `3d71…` 在本切片所属 base 合法，未列为缺陷，也未修改 guard。

独立验证使用固定 control Python 与从精确 Git 对象提取的公开源码。直接导入冻结 browser_shell；仅从原测试 AST 取 fixture 和两个纯测试函数，未载入测试框架 fixture 生命周期。原 1 个正例及 18 个参数化拒绝分支共 19 次直接调用通过；额外 baseline 与上述 5 个缺口变体全部接受，最终复现 CLI exit 0，表示缺口成立。私有材料为 Reviewer `.audit/v4-1/mobile-9726885-review/repro.py` 与 `result.safe.json`。首次准备误列不存在的包 initializer 导致 archive exit 128；首次整测试模块 import 因未提取 scripts 依赖 exit 1；改为列举现有路径并仅 AST 提取必要纯 fixture 后验证完成，这些是 reviewer 准备错误，未伪装产品失败或丢弃最终否例。

作者报告的 52 focused pure/Ruff/mypy/preflight 属作者证据，本轮未冒称独立重跑全套。浏览器、profile、CDP、网络、服务、PG 与信号均 0；合成目录仅在 Reviewer scratch 创建和清理，没有访问原运行资产。此报告只阻断本新增父收验源码的接纳，不声称真实业务运行已经出现反例；整改后需新的精确 freeze 与增量复审，未来真实窗口、视觉及阶段验收均另核。

## Root 澄清后的第 1 项解释更正

2026-11-04 同日追加。当前结论修正为 `HOLD / TWO_CONFIRMED_P2 / SERIAL_PROVENANCE_PROPOSAL_PENDING`；上方 THREE_P2 是原审查时点记录，第 1 项的反例解释和修复建议以下文为准，第 2、3 项已证缺口不变。保留旧反例、脚本与原文，不改动冻结组件、原 journal 或 Native timing。

独立核对精确 `2ae73562effbabbee2092a1ff249fc43fe5f288c` 的 business.live.spec.ts:130–147 后确认：先 `await Promise.all(batchPosts)` 与 `Promise.all(batchReads)`，然后在逐项验证循环末尾写 COMMITTED_READBACK。该 subject 事件是事后核验记录，日志写入顺序不等于对应网络请求/响应的发生顺序。因此正常串行执行也可能在 A 的 COMMITTED_READBACK 日志之前已有 B 的 ATTEMPT_STARTED。原变体仍确实被 validator 接受，但不能据此判定网络非串行；原“原日志显示前项真实读回前启动后项”的解释与强制 A.READBACK 行索引小于 B.ATTEMPT 的建议正式撤回，不得据此新增 gate。

同冻结 spec:140、146 等待真实 response.finished，并直接从前项 read.request().timing() 与后项 raw.request().timing() 取 startTime/responseEnd，检查 responseEnd 非负及下一 POST 起始不早于前 GET 完成，再保存 serial_evidence。这些是源码定义的真实 Request/Response 观测值，不应描述为任意硬编码计数；本轮没有实际浏览器证据来否定其真实采集。当前独立反例没有构造“已绑定真实网络时间顺序相反但整个采集仍通过”的证明，故不再将第 1 项计作已证 P2。

若 Root 要求父层可从原始材料重算串行关系，最小方案建议仅增加本 case 的窄私有采样材料，供 QA 提案后冻结独审：

1. 在现有真实 Request/Response 观测点保存对应对象的原 timing 快照，保留原 startTime/responseEnd 数值与缺失/失败状态；以实际 Request 对象关联 POST 与 GET，不使用 subject journal 行序或异步 callback 写文件顺序推断网络时间。可以在请求自然完成后收集，无需等待该文件写入才放行下一业务操作。
2. 原始记录绑定 source SHA/tree、同 case、scope/shop、POST operation/key/path/request_body_sha256，以及 GET method/path/query、resource id、严格 schema 核验后的 readback version/data_revision 和响应内容摘要。绑定应复用原 request witness、已验证 receipt/readback 对象，保存必要原始安全字段，不能仅再复制一份 serial_evidence 或“已完成”boolean。不得包含凭证/headers/cookies。
3. 父层只读核材料路径/权限/摘要及唯一对应关系，从原 POST key/bodyhash 和 readback resource/version/revision 找到同一对请求，再重算既有时间不等式，并与 summary 一致；缺失、重复、不同 scope/case、未知/非有限 timing 或无法唯一匹配一律不接纳。原始材料 hash 仅证明字节未漂移，真实性仍依赖精确受审的采样代码及后续真实 owned 运行，不称其为独立网络见证器。

这是一份未实施方案，不自动扩展 QA 改动范围；待 Root/QA 确定精确材料契约。保持原 subjectWriter/registry 状态、journal 时点、业务 dispatch/读回、超时及运行窗口不变，不通过延迟、重放业务或改日志时点迎合校验。原 pending-before-POST 与批末 pending 为空继续保留；若另需逐项 pending 闭合证据，应另绑定实际边界采样，不能从事后 subject 事件推导。此次更正没有重跑组件或启动任何资源。

## Root 最终核定：仅两项实证 P2，不新增串行 Gate

2026-11-04 同日追加。当前有效结论为 `HOLD / TWO_CONFIRMED_P2_ONLY`：仅原第 2 项的原文件字节摘要/preview status 绑定和第 3 项的精确 scope/snapshot 来源绑定必须修复。原第 1 项的全局 journal 索引建议已正式撤回，不另立串行 Gate；前段 sidecar 提案未获采用、未实施，不再列为 pending、阻断或新增计划。保留前文仅为完整审查与纠错历史，不据其扩大验收范围。

按 Root 核定，原 spec 的真实 Request/Response NativeTiming 严格不等式、精确受审采样代码、原 pending/CAS/fresh readback 以及最终逐 key PG 回执，共同作为本地串行证据。既有 NativeTiming 断言与父层字段校验继续保留，未知或不合法字段仍失败；不将这些证据表述为外部 wire 或独立网络抓包，也不以本次源码复核预签未来实际运行。原合同没有要求额外 raw sidecar，不能因已撤回的错误建议新增材料或门槛。

QA 可专注第 2、3 项最小加固；未来实际运行如出现新的时序异常，再按新事实处理。本轮只追加这一核定记录，未更改组件、原 journal、既有 timing、业务流程或原始反例，未执行测试或启动资源。

## d410097 第 2、3 项精确增量复审

2026-11-04 同日追加。当前结论：`HOLD / P2_3_CLOSED / P2_2_ONE_JOB_VERSION_BINDING_REMAINS`。冻结提交 `d4100975c770abf5efdf85fda9344c4ece4d4bb9`，tree `954ed2cbe4717656150de5d8aa0f42dc398f4a84`，parent `ec7b6717f5a4421f494b91c9eed803178e7039cd`；差分仅 browser_shell.py 与 test_browser_shell.py。原第 1 项维持正式撤回，不新增 sidecar、全局顺序 gate 或采样计划；原报告及纠错历史完整保留。

严格按新完整 fixture 先正后负：每个独立变体均先调用同冻结 validate_business_mobile，正例返回 9 keys/32 PNG 条目后才实施单类变异。没有使用旧简化 snapshot fixture 来制造预先 schema 失败。原四个有效反例现分别被拒绝：整体替换 mobile 内文件摘要触发 `BUSINESS_MOBILE_PREVIEW_ORIGINAL_BYTES_DIGEST`；preview UNKNOWN 对 ACK_OK 触发 `BUSINESS_MOBILE_STATUS_ACK_MISMATCH`；借另一真实已注册 scope 的 mapping 截图触发 `BUSINESS_MOBILE_SCREENSHOT_MAIN_SCOPE`；product_list 三宽空 snapshot 由冻结 Snapshot DTO 报 data_revision、snapshot_id、read_at、source 四项 missing。另改原 file_base64 并正确重算 witness body hash，仍在 `PREVIEW_ORIGINAL_BYTES_DIGEST` 被拒，证明没有只依赖旧 request hash 或报告内部摘要相等。

源码核对确认：server_request 从经过原严格 request 校验的 preview body 独立解码并计算文件摘要；operation.status 与实际 journal ACK_OK/ACK_COMMITTED 配对；discovery/mapped/import 的文件、原 parent job、expected_job_digest 和 job 对象已有新增交叉绑定。非 anonymous 截图必须属于唯一实际业务 operation scope；Snapshot 直接调用冻结后端 DTO，额外/缺失/错误字段受其约束，fixture 来源链、三宽 source 相等、列表/批量确认来源及 tag/fulfillment/import 截图的对应修订有具体检查。因此原第 3 项以及第 2 项的摘要/status 反例在源码与纯组件层面关闭，但第 2 项尚留以下版本矛盾。

**剩余 P2：job.version 仅彼此相等，没有绑定已核的 operation/readback/原请求版本。** 定位本冻结 browser_shell.py:1335–1342、1365–1378、1615–1620。preview 分支检查 job id/data_revision；import 分支检查 job id/job_digest；链尾比较 imported.readback.job 与 mapped.readback.job 相等，但两边的 job.version 都未与已核 read.version/operation.version 或原 expected_job_version 相连。

最小独立反例从新完整正例出发，只改同一个 mapped preview 及其 import_confirm 的两个 `readback.job.version` 字段，由 2 改为 999。两者的 operation.version、readback.version 仍为 2，原 journal expected_job_version、pending、job_digest、文件摘要、截图、counts 和其他字段完全不改；校验仍接受。另将所有 job.version 一致替换的较宽变体也接受，但剩余结论以两个字段的最小反例为准。这属于原第 2 项已要求的 job/version 链，不涉及串行证据或新增验收范围。应将 preview/import 的 job.version 绑定对应已核 resource/readback version，并在 import 路径保持与原 expected_job_version 的语义一致；增加上述两份 job 对象一致错误、但与原请求版本不一致的拒绝测试，保留合法正例。

独立使用固定 control Python、精确冻结公开源码与新 fixture，直接调用原新增/相关纯测试函数（包括参数化分支）共 35 次，全通过；其中已有晚写 READBACK 标记的合法正例通过，确认未恢复错误的全局索引 gate。另有上述 baseline、五个具体拒绝变体和两个版本缺口变体，最终脚本 exit 0 代表这些预期观察成立，不是父收验整体通过。私有复现为 `.audit/v4-1/mobile-d410097-review/repro.py` 与 `result.safe.json`；每次校验调用前后原 journal 字节相同。作者 68 focused/185 offline、Ruff/mypy/preflight 未在本轮冒称独立全量重跑。

该差分未改 business spec、producer、subjectWriter/registry、journal schema/时点、final_facts 或 config；Native pin 保持已核 `295bf2c61e7cd30e7a47d7368d93fbadb40764fb41072a9119b5d78ed925689e`，未放松旧 focus/header、NativeTiming、pending/CAS/readback 或逐 key SQL 门槛。未读取后续 WIP；浏览器、服务、网络、PG、信号均 0。合成 PNG 条目仍仅纯校验 fixture，不是实际截图。整体 r9 实际运行 NOT_RUN；等待剩余窄版本绑定的新精确 freeze，不能提前签该父层候选完整接纳或阶段验收。

## d36a514 剩余 job.version 绑定复审关闭

2026-11-04 同日追加。当前源码结论：`SOURCE_INCREMENT_ACCEPTED / P2_2_AND_P2_3_CLOSED`。精确提交 `d36a514e307107e61834e1722739252f94902cd8`，tree `4a32dae83a84832b3d3baeae0cdaacf0f4be569a`，直接 parent 为上述 `d4100975c770abf5efdf85fda9344c4ece4d4bb9`。仅 browser_shell.py 新增 8 行 guard、对应 test_browser_shell.py 新增 43 行测试；未发现本增量的新 P1/P2。原报告、有效反例、误判更正及 Root 最终范围裁定全部保留。

新增 guard 在 preview/import_confirm 两分支之前，要求 readback.job 为 dict，job.version 为严格 int（不接受 bool），且与 operation.version、readback.version 相等。import 原 RESOURCE_VERSION 分支继续将 operation.version 绑定原 request.expected_job_version，因此此前“mapped/import 两 job.version 同为 999、原请求与 operation/readback 仍为 2”的缺口不能再通过；原 discovery/mapped/import 文件摘要、job_digest、scope/snapshot 绑定未减少。

独立对每个变体先使用本冻结的新完整 fixture 验证正例，均返回 9 keys/32 合成 PNG 条目，再实施变异。单 preview job、单 import job、同 mapped/import 两处 job，以及全部 job.version 一致改为 999，四种情形全部精确触发 `BUSINESS_MOBILE_JOB_PROJECTION_VERSION_BINDING`。前轮整体伪换文件摘要、改原 base64 并重算 witness hash、preview UNKNOWN、另一合法 scope 借用、空 snapshot 五种否例仍在原对应原因拒绝，没有依赖更早的不相关 schema 失败冒签版本修复。

固定 control Python 直接调用本冻结相关纯测试函数及参数化分支共 39 次通过，包括单 mapping screenshot 版本漂移拒绝和事后 READBACK 标记的合法正例；最终独立复现脚本 exit 0。私有材料为 `.audit/v4-1/mobile-d36a514-review/repro.py` 与 `result.safe.json`。每次校验前后 journal 字节一致；未读作者 WIP，也未运行浏览器、网络、服务或 PG。该结果是精确源码/纯组件关闭，不是实际图像、真实业务或 r9 执行证据。

原第 1 项仍正式撤回，不恢复 global journal order 或 sidecar gate；原真实 NativeTiming、pending/CAS/fresh readback 与逐 key SQL 的本地串行证据边界保持。第 2、3 项在本冻结范围内全部闭合，可交 Root 后续组合与运行安排；实际全 r9 仍 NOT_RUN，视觉验收、运行清理及阶段完成不由本次代签。
