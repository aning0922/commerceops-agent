# Mobile effect authority consumer 精确增量独审

2026-11-04（台北）。结论：`LOGIC_INCREMENT_ACCEPTED / PHANTOM_API_COUNT_GATE_REMOVED_WITH_DB_AUTHORITY_PRESERVED`，本增量未发现 P1/P2。精确提交 `7b43cba7d7ea80d4723711f6011e4c0f6f1fe6e9`，tree `63357b0f1430d740436185be4f3673bbd3c3e9e3`，base `25de479e134cc4e6ca98399fe2bd54e4fe320fcb`。仅 tests/e2e/v41/browser_shell.py 与对应 test_browser_shell.py 变更。Native dependency 仍 HOLD，本切片原 `6fa9663dfc3695c2e3caa4cc482776f7ad87d62f47cc811bbc7d91da77e83079` pin 不动；此逻辑接纳不是 Native、整个组合源码或 r9 的运行验收。

## 权威来源与最小修复

公开 ActionReceipt 不含 effect_count，严格 DTO 禁止额外字段；原 producer 的 `receipt?.effect_count ?? null` 正常产生 None。此前父层要求正整数、synthetic fixture 给非 preview 人工造 1，导致纯测掩盖真实契约不兼容。该漏项不能靠给 producer/DTO 添加假计数修复，也不能把 UI None 描述为数据库效果 UNKNOWN。原 r9 逐原 key SQL 校验和 consumer 诊断是不同层级，见下文。

本增量使用直接字段访问，非 preview 必须 status=COMMITTED 且 effect_count is None；preview 原 None 检查保留。缺字段产生 KeyError 并失败，不用 get 默认 None 把缺失伪装合法；0、1、True 等伪造计数均拒绝。移除的仅是不存在的公开 API 计数条件，status、before/after revision 不同、当前 scope/key、请求/持久 pending/resource、version+1、fresh readback revision 和 tags/fulfillment 值检查保持。没有引入新计数来源或把 None 填成 0/1。

import_confirm 改用真实 readback.row_count：严格 int 且 1–500，拒 bool、float、字符串、None、0、负数及超限；要求 discovery、mapped preview、import readback 三段计数一致，并保留原 parent job、job version、expected_job_digest、原文件字节 digest、scope、after revision 和 COMMITTED 状态绑定。严格 Snapshot DTO 校验继续约束 upload 来源及唯一 job/row；只计匹配该原 job/file 的 uploads，条数必须等于真实 row_count，不能借其他 job 或文件的条目补数。此次没有修改 producer、公开 DTO、final_facts、pg_observer 或 owned_driver；独立比较这些路径从原 fbb29a4 到本提交也无差异。

原 final_facts 的唯一原 key receipt、event once、effect_count 与实际 effects/digest、canonical request 和身份绑定完整保留，包括旧 tag 被新版本替换时的历史 receipt/event digest 分支。driver.checked 遇非零仍抛错；finally 中 final_facts 失败仍进入 cleanup failures，不能得到 SCENARIO_COMPLETED_PENDING_REVIEW 或主进程 exit 0。consumer 的 nullable 字段不取代或降低该 SQL Gate。

## 独立纯组件验证

Reviewer 从精确 Git blob 提取公开源码与本轮改正后的完整 fixture，使用固定 control Python。每个自选负例先验证同一未变异 positive 返回 9 keys/32 合成 PNG 条目、全部 effect_count 为 None，再实施变异：伪造 1 精确拒于 COMMITTED_EFFECT；删除字段为 KeyError(effect_count)；mapped row_count 不一致拒于 IMPORT_JOB_BYTES_CHAIN；移除本 job 的 upload 成员拒于 IMPORT_SOURCE_COUNT。每次校验前后 journal 字节相同。

另直接调用本冻结相关原纯测试函数及全部参数化组合，共 85 次通过：覆盖四种 operation 的伪造/缺失 count，三段 row_count 的 None/0/负数/501/bool/float/string、preview 链计数不一致、缺/多/错 job/错 file 来源，以及 22/500 行合法边界；此前 scope/CAS/version/digest/snapshot、job.version=999 和晚写 READBACK 的合法边界均保留。最终独立脚本 exit 0，私有材料 `.audit/v4-1/effect-7b43cba-review/verify.py` 与 result.safe.json。仅合成 fixture，没有重放原 registry、重跑真实副本 validator 或启动 browser/network/service/DB。

## 作者完整纯测与 r9 副本诊断原件

原件根为 `/Users/aipuli/.codex/worktrees/commerceops-v41-qa-effect-authority/commerceops-agent/.audit/effect-authority/`。freeze.safe.json SHA-256 `1b19cdb174aa6e354e293399f81e8dcd7df85c8ca46e7f26f108254c673e15ac`；两修改文件 hash 独立与 Git blob 匹配，分别为 `56ca9ddfb17f8c61e0b8cc473c8c5b598814d7ef991c5cc73f3fb1c17ae6185e`、`4fa6cd40f5d401dbee7e03f96f140514a5023a11195e79896c0bfbb045b1e282`。

full-pure.safe.json SHA-256 `12520d8f9ec6e587d6b3052c46389eb19c7465fb61819060e77cc784e1cbcdb7`，记录 native_exit=0、elapsed=12.958620375 秒；原 full-pure.log hash `7c7662a4bba9e036c905144bd7cf6ed3264a8123f7e3097b6c32e5ba94cc58a6` 匹配，末尾实际 235 passed in 12.39s。已读 full_pure.py：命令为当前 Python `-m pytest tests/e2e/v41 -m offline -q`，无重试循环。前后记录的两源码、锁/配置、Node 字节、Python/Node 路径及 96 项 Python 包名称/版本列表一致；这是所列文件与包元数据指纹，不冒称全部 site-packages 字节审计。Node 通过 QA 工具路径引用，固定二进制 hash 为 e4b5a3af…；不改称独立复制依赖。本轮未重跑全 235 或作者 Ruff/mypy。

freeze 原记录保留首轮 234 passed/1 failed（固定 Node 路径缺失）、补路径后单例通过及后续全 235 通过；本核收逐 hash 核的是末轮完整日志，首轮与单例按作者 freeze 记账，不补造其未随本包提供的原始 CLI 记录。作者另记首次 diagnostic 用 `-m` 传文件路径导致 Python 在脚本/validator 前拒绝，改 runpy 后只调用一次；未把启动错误算业务 validator 失败，也未抹去它。

diagnostic.safe.json SHA-256 `192c44781583663d5933798acb293b282016d59df9e79fd630b30bab6a99eb9d`，与 freeze 引用一致。已读 diagnostic.py：读取原 r9 完整 evidence-copy 的原逻辑 Case/source，保持原 report/路径字符串，将 private_bytes/private_subject_bytes 读取映射到副本；只调用一次 validate_business_mobile，没有调用 registry/import_journals/SQL 或 producer。脚本在调用前后对 case、business.safe、原 journal 与 32 PNG 共 35 件输入取 hash，原 receipt 记 inputs_unchanged=true；Reviewer 再逐件读 hash，与所有记录值匹配，另核输入确有 32 screenshots、11 唯一 keys 且所有 effect_count=null。诊断原结果为 CORRECTED_CONSUMER_DIAGNOSTIC_PASS、32 PNG/11 keys，mapped reads=34；本轮没有再次执行该真实副本诊断。

该诊断组合的是新 consumer 与原 fbb29a4 运行证据，只证明修正后 consumer 能核收此份 mobile 材料，不能将原 r9 native=1 改成 0、补签完整 validate_receipts 或绕过 Native 几何/依赖问题。此前只读核验 r9 final_facts 原 native=0、日志 hash 匹配，并按同七个非 preview key 对照 DB：四次 tags 与一次 fulfillment 的 receipt/event effect_count 各 1，两个 imports 为 22/1；其中两次 tag 保留历史替换分支，不宣称当前 effect 行仍在。UI None 与 SQL 已核效果不冲突，整案仍受原所有 Gate 约束。

原第 1 项 global journal order 建议继续撤回，不新增 sidecar、registry 状态或其他 Gate。原作用域/权限、timing、pending、CAS、fresh readback 与 SQL 约束不变。后续 Native 新 hash 及常量追加片、组合检查、实际运行与视觉/清理/阶段验收需按各自证据处理，本审查不提前签署。
