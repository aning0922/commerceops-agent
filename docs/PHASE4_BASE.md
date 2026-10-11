# Phase4 B：正式共享接口适配与 Base 离线投影

当前导航（2026-10-11）：Root已冻结A共享合同source `d039aa1e1ffc28120afdf546c29a4e910c44a528` / tree `c1915bdf3d33a998621937f7538a0440f04ffbb4`，[精确Review5481721958](https://github.com/aning0922/commerceops-agent/pull/43#pullrequestreview-5481721958)无P1/P2、独立49pure通过。B在首批cb1已提交后，按Root指令普通merge精确d039为 `20ae3fcec534a69563107e06e37b32607d9a318c`（parents cb1+d039），无冲突/历史改写。共享九文件按d039原字节继承，B没有直接编辑A文件。A精确CI38107924795读取时仍in_progress，不从本地merge宣称正式包/PR集成Gate通过。

当前B适配完整批在原分支/原[PR44](https://github.com/aning0922/commerceops-agent/pull/44)：已删除临时ProjectionFields与重复的输入校验；projection_contract显式re-export共享ItemProjection/ProjectionRequest/ProjectionResult/BaseProjectionAdapter、唯一normalize/bind函数。BusinessBaseAdapter实际实现 `async project(request)`，返回前调用唯一binding，所有字段来自共享immutable ItemProjection.fields()，Quantity/SyncVersion为int，终态空值为null，时间带时区文本。下方全text/本地DTO/未获freeze/113–121测试是首批历史，不能覆盖本导航和末尾当前适配表。真实schema/空列省略风险仍not_run，strict15不放宽；PG/SDK真实认证/平台/provider/.env读取仍0。新完整批源码/实际检查由原PR下一freeze绑定，当前独立B增量Review与精确CI待Root核收。

## 首批cb1历史证据（冻结前输入建议与失败原样保留）


2026-10-11（Asia/Shanghai）。任务 [P4-B #41](https://github.com/aning0922/commerceops-agent/issues/41)，阶段 [#39](https://github.com/aning0922/commerceops-agent/issues/39)，共享接口 owner [A #40](https://github.com/aning0922/commerceops-agent/issues/40)。本轮用户持续授权优先于旧文档的历史未授权标记。

本会话 `01a128eb-edfb-7a30-9ebf-a2718604a014`，独立 Worktree `fb24`，分支 `codex/phase4-base`；接单 clean、detached HEAD 精确为 `9d97c19009d932036809ac3e2638bb68f4b7f765` 后普通创建分支。GitHub 已实时核该 SHA 的 [CI38093693335](https://github.com/aning0922/commerceops-agent/actions/runs/38093693335) quality/frontend/phase3/pg-pair 四 job SUCCESS，Issues33/34/35 CLOSED。这是继承基线，不是本批独审或 CI。

当前只完成适配器纯模块/离线 Fake 候选。共享 PG DTO/outbox 合同尚未收到 Root 的已审冻结 SHA，PG/sender 集成、真实 Base、独立 Review 与本批精确 CI 均 not_run。`ProjectionFields` 是 B 本地已序列化文本字段快照，`RecordTransport` 是 B 本地异步协议建议，二者**不代表共享合同已冻结**。收到 A 已审提交后普通同步该提交，re-export 共享契约并适配；不能从 A 未提交目录采用稳定依赖。

## 归属与已有源码保留

本批仅新建 [business_base.py](../backend/src/commerceops/adapters/feishu/business_base.py)、[projection_contract.py](../backend/src/commerceops/adapters/feishu/projection_contract.py)、[projection_rules.py](../backend/src/commerceops/adapters/feishu/projection_rules.py)、`tests/test_p4_base_*.py` 与本文。旧 `feishu/base.py`、probe、repository、SDK/config/contracts，以及所有 migration/outbox/Worker/Graph/sharedDTO/API/锁/CI/Compose/frontend/阶段导航原样继承。调用既有 `restrict_sdk_logs`，不修改 SDK 全局 Encoder、不增加消费者/调度器。

固定 D1=2026-10-10、D30=2026-11-08、300h、P4 D13–D17/50h（A18+B14+交付8+独审集成10）保持；B14h 是初始容量估计，人工 H/L `not_reported`。Agent 墙钟和机器命令运行另账，不把提前实施加成额外人工预算。历史 P1/P2/P3 失败、Issue23 `not_identified/risk_accepted`、旧原键/资源/卷/凭据与冻结18页资产保留。

## 十五字段和 PG 映射建议

以下是供 A 冻结输入 DTO 使用的建议与已有 P3 列对应，**本批没有实现数据库 SELECT 或 shared DTO**。十五列暂建议专用表全部用文本，数量/版本使用规范十进制 ASCII，时间使用 UTC ISO 文本；当前测试表实际列类型/权限未核，不申请建表权限或扩 scope。若 A 冻结类型或 Root 核资源后类型不同，须按已审合同适配，不在真实窗口静默转换。

| Base 技术字段 | 可信来源建议 | 离线序列化/回读约束 |
|---|---|---|
| CommerceOpsItemID | `replenishment_items.id` | 原规范 UUID，完整原键精确查询，不按 SKU 替换 |
| TaskID | `replenishment_items.task_id` | 原规范 UUID，参与内容匹配 |
| SKU | `replenishment_items.sku_key` | 原文本，不展示名替代稳定键 |
| Quantity | `replenishment_items.quantity` | 正整数文本，拒绝 bool/float/前导零，不重新计算 |
| Risk | `approved_plan_id` 绑定冻结计划/事实的本 SKU 风险 | A 冻结如何从原冻结链取得；不是重新观察风险 |
| Window | 同批准计划绑定的原销售窗口 | A 冻结唯一规范字符串，不改成发送时窗口 |
| SourceMode | 原业务来源/任务证据 | A 冻结枚举；不能把 Mock 商品数据因真人审批改为真实电商 |
| ApprovalStatus | 已消费 execution 对应原 approved 决定 | 只有已创建内部 item 的 approved 事实，不从 Base 反向授权 |
| ApprovedBy | `replenishment_items.approved_by` 的冻结文本映射 | A 冻结 UUID/显示名取舍；不需人员列或通讯录 scope |
| BusinessStatus | `replenishment_items.status` | open/completed/closed，终态来自真实 PG T6 |
| ResolutionReason | `replenishment_items.resolution_reason` | open 为空；终态原原因，不造“已入库” |
| ResolvedBy | `replenishment_items.resolved_by` 的冻结文本映射 | 终态必需；不从回调客户端指定 |
| ResolvedAt | `replenishment_items.resolved_at` | 终态原 UTC 时间，不能用发送时钟填补 |
| SyncVersion | item `version` / outbox `aggregate_version` | 原不可变版本，必须相等；不使用重试次数 |
| UpdatedAt | 该 item 版本原 `updated_at` | 固定 UTC 文本，重试不得刷新 |

P3 现有 item open/v1 与 T6 terminal/v2 已有数据库约束；outbox 原 payload 只有 schema/item/version/state，不能把该最小 payload 冒作完整十五字段 DTO。A 需要冻结按每一版本持久化完整内容的时点、原 UUIDv4 create token 与 item 稳定映射、旧 v1/current v2 的选择及外部 row link。T6 后不能用当前终态行重新拼装旧 v1 内容。B 本地快照拒绝额外/缺必需字段、可变容器、非法数量/UUID/时间、open 带终态原因或 terminal 缺原因，但不能据此证明 PG lineage 或授权正确。

## 官方合同、锁定 SDK 和 null 修正

[创建记录](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/create.md)、[列出记录](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/list.md)、[更新记录](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/update.md) 官方 Markdown 已通过 HTTPS 下载全文读取。网页工具对 `text/markdown` 返回 unsupported-content-type，未将网页工具失败冒称成功读取。另读公开官方数据结构概述及记录数据结构正文，并做官方站点搜索；没有平台认证或业务调用。

官方创建合同要求标准 UUIDv4 `client_token`，本批不生成或换 token，不假定永久远端幂等。官方 list 提供 `has_more/page_token/total/items`，查询全表并指定十五字段，不设置 view/filter、不请求自动人员字段，文本数组开关为 false。官方 update 为增量写，清空字段需显式 `null`；1254290/1254291 是限流/同表写冲突，1255006 是 token 冲突，1254608 是重复请求，均不能把 HTTP200 当作业务成功。[官方错误说明](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/create.md)

源码核验的依赖为项目已有 `lark-oapi==1.7.3`，未改依赖锁。其 `core/json.py` 的 `Encoder.default → filter_null(model.__dict__)` 会递归删掉模型字段中的 `None`；直接 `AppTableRecord.fields(...None...)` 未实际传出 null。新适配器保留官方 request builder、认证、resource 和异步 transport，仅将公开 `request.body` 设为普通 `{"fields": ...}` 字典，普通 JSON 字典的 null 不被模型过滤器删除。捕获到的真实 SDK HTTP 构造已断言 create/open update 的三个空终态列为 null，terminal update 保留原原因/人/时点。

锁定 SDK `BaseRequest.add_query` 把 bool 序列化成 `"False"`；离线按捕获的真实字节断言，不声称已验证真实平台对该大小写的接受。当前 SDK 测试只用合成 token `REDACTED`，HTTP 层全替身，未验证真实认证。

## 回读、异常和调用预算

完整回读要求：每页 HTTP2xx 且严格整数 code=0；items/list、has_more/bool、total/int 类型正确且 total 跨页不变；继续页非空、cursor 非空且不循环；最终行数等于 total、record_id 非空且全局不重复，完整原 item 键必须恰好一行。同一 record_id 出现在多个页视为不完整；不同 record_id 的同原 item 键视为冲突。超过100页/10,000行、缺页/total不符/超时均不恢复 external_link，不采用第一页局部命中。

十五字段完整意义是对十五个**语义值**做比较：当前十五键均须实际存在，任意缺键均 incomplete/unknown；仅 `ResolutionReason/ResolvedBy/ResolvedAt` 的明确 null 在期望 open 空值时可规范为空，空字符串与原空字符串匹配。若远端仍有旧非空原因或 actor/time，则与期望空值不符，不能假造空值通过。terminal 三列必须有原值。Quantity/SyncVersion 严格文本，其他字段精确原字符串比较；既有 external_id 存在时 row id 必须相同。只有同版本/全内容匹配返回 `matched` 和 row id；零行 missing、多行 conflict、不完整 incomplete、旧版本 older、新版本 newer 均不返回可恢复 link，也不触发 create/update。

写结果为本地事实分类：ACK `acknowledged` 仍需完整回读；明确限流/写冲突 `deferred` 不自行重试；明确业务拒绝 `rejected`；1255006 `conflict` 不换键；timeout/5xx/ACK缺失/1254607/1254608/1254002内部错误/125500x内部或序列化错误/未知code/无有效业务code 为 `unknown`；只有明确已知参数/类型/权限拒绝码进入rejected白名单，不从未知非零code推导无写。unknown 不提供 retryable=true 或无写证明，必须按原键对账；完整零行也不推断先前写失败。SDK异常原文、字段、row id 不输出日志，结果 repr 隐藏内容。消息 R15 超1h停止由 A 消息 sender 负责，本包未实现或验收 R15。

本包没有循环重试。单 SDK create/update 调用各至多1次，query 每页至多1次。每次整操作绝对截止最长10s，使用当前 asyncio loop 的 monotonic `time`；多页共用同一个 `asyncio.timeout_at(deadline)`，不按页重置；截止前未开始的调用0次，截止取消在途写保持 unknown、取消读保持 incomplete。A 在唯一 Worker/同表锁内为**写+所有回读页**创建一次 `operation_deadline()`，把同一个 deadline 传给 create/update 和 reconcile；不能分开调用默认截止凑成20s，也不能在重试时续原操作截止。Root真实批另需冻结总次数/cap/批绝对截止，B不能用本包默认10s替代Root窗口授权。

| 离线场景 | 方法次数与结果 |
|---|---|
| R13 Fake create 已成功 ACK 丢失 | create1/query2/update0，同原token、原item，两页完全匹配后 matched |
| Fake update 已成功 ACK 丢失 | create0/query1/update1，同原row/terminal v2，全字段匹配 |
| 零行/重复/内容错/旧新版本/缺页 | create0/update0；query有界，link为空，不盲重建 |
| SDK请求构造 | POST1/GET1/PUT2，全部HTTP替身；固定token/十五字段/null/分页参数 |
| SDK timeout 三method | 每method1次、无重试、unknown、原异常不回显 |
| SDK在途截止三method | 每method1次并确认协程取消，无重试；expired deadline三method各0次 |
| 两页deadline用例 | 两query同绝对deadline，第二页取消，incomplete/零写 |

已执行的单次离线全回归命令有240s进程超时上限；首批所有离线 Fake 不消耗真实平台次数。真实 batch 尚未开放，实际真实 SDK认证/长连接/Feishu Base create/query/update/provider/PG/旧DB/秘密/.env文件读取均0。本包不启动PG/Docker/browser、不占桌面Chrome焦点。

## 实际验证、失败保留与后续 Gate

安装只在本 Worktree `.venv/.tools`，`uv sync --frozen --all-groups` 使用既有锁，项目bootstrap按固定SHA校验 Node24.21.0/Gitleaks8.30.1；未改全局环境。必要验证结果在冻结交接时记同原 PR，作者自检不替代独审。

已发生失败保留：首次 targeted104 为103pass/1fail/9.70s，原因测试误期望SDK bool小写；第二次103pass/1fail/2.20s，实际请求暴露模型null被删，修正request body；同步修正后104pass/2.24s。新增共享绝对截止/取消用例并改用官方异步SDK后当前 targeted113pass/2.73s、两条既有SDK deprecation warnings，6文件strict mypy和Ruff通过；下方最终冻结检查追加精确结果，不能删掉这两次已发生失败。

未跑/待核：A共享DTO已审freeze/re-export、持久token/十五字段版本snapshot、真实PG/Worker同表串行/外部状态映射、旧不覆新的集成证明、R13/R14真实Base和R16 PG Gate、全部Web/Compose回归、独立Review、当前精确CI、正式Base资源权限/列型核实、Root有限真实窗口以及最终main与Issue结案。纯 `is_current` 比较不替代A的持锁PG版本复核；低层transport不具备业务授权或防并发CAS，禁止被第二sender直接使用。P4/M1整体未验收，B不合main/不关Issue。


### 空字段公开证据与暂定限制

额外核查 [数据结构概述](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/bitable/development-guide/bitable-structure.md) 与 [记录数据结构](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/bitable-v1/app-table-record/bitable-record-data-structure-overview.md) 全文。它们定义 fields map 与文本值形状，list 参数定义 text_field_as_array，却未取得“指定字段列表时合法空文本列可以省略”的明确合同证据。锁定 SDK `core/construct.py` 对读取的 Dict 逐个实际 key 解析并保留 None，不能据其自行推出服务端一定省略或一定包含空字段；本适配器直接解析 raw.content，不把响应 model 再 marshal 后丢 null。新增回归区分实际 present-null、present-empty、present-old-value 与 absent-key。

按 Root/Reviewer 本轮要求，未证实空列省略语义前已移除原宽松缺键填空：十五键必须实际存在，三终态列仅明确 null/空字符串可作空值，旧残值不能匹配，缺键 incomplete/unknown。不声称当前合同已能验证所有真实合法 open 行：若实际官方合法 list 省略空列，该行会安全保留待核，正式 Base Gate 阻断，不能据缺键盲写或宣布成功。A/Root 须在已审共享合同中解决该适用性缺口（补充权威省略合同证据/受控 readback 证据后再冻结规范化），不会把暂定严格策略永久当作不可修订外部事实。本批未为补证据调用真实平台。

### 冻结前检查与敏感扫描历史

首轮完整离线1170=既有1057+本批113，337integration deselected、两条既有SDK warnings，100.34s/exit0。全仓Ruff、274文件format、199文件strict mypy、uv锁check通过；文档72文件0error、git diff --check通过。后续空字段收紧和四项raw解析边界为新候选，最终结果另记原PR，旧1170结果不冒作新源码结果。

第一次 current/index/fullhistory 扫描实际 current 1命中，index/history各0，定位新测试第8行同一import中的 两个类型名列表，generic-api-key 把 Api 前缀后的逗号及长类型名误识别为赋值；该行仅Python import，没有实际凭据。第一次误认为别名导致并缩短为scan后，同一行仍命中、current1/index0/history0。查规则后已改为导入contract模块并用限定类型名，没有改扫描器、规则、allowlist或排除测试；第三次测试import已无命中，但本文直接引用同类型名列表又触发current1/index0/history0；已改为描述其语法形状。修正后三scope需实际重核0后才可push。三次扫描历史保留，不称早先扫描通过。


### 当前首批冻结复现命令

```bash
uv sync --frozen --all-groups
uv run python -m scripts.bootstrap_tools
uv run pytest -q tests/test_p4_base_*.py
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv lock --check
uv run python -m scripts.check_docs
uv run python -m scripts.scan_secrets
```

完整离线回归用 `.tools/node/bin` 前置 PATH、项目Python执行 `pytest -m offline -q`，外层 `subprocess.run(..., timeout=240)` 限单批命令，337真实PG仅deselected。新候选targeted121pass/2.84s，72MD0error/275format/199strictmypy/Ruff/锁检查通过。敏感误报调整后实际 current/index/fullhistory 各0，七新增文件owner精确核对、旧全部tracked文件未改；最终完整离线1178=既有1057+本批121，337integration deselected、两条既有SDK warnings，107.98s/exit0，在240s批上限内；source/tree由原PR冻结回执绑定。未运行全scripts.check中的npm/install/build/audit或本地frontend/PG/Compose，不以这些未跑项标通过。


## d039共享合同实际适配批

当前唯一路径是A共享Protocol→BusinessBaseAdapter→锁定官方SDK异步transport。共享normalize要求实际15键严格集合且Quantity/SyncVersion必须int；三个终态列明确null/空文本同义，缺键unknown，不允许宽松推导空。readback直接解析raw JSON，保留null/省略/旧非空值差异。B没有第二份字段DTO/共享binding；A在持久标sent前仍须再次调用唯一binding，并复核当前PG版本/唯一Worker/同表锁。B不能用源DTO构造测试证明PG lineage/T6真实事务。

一次project在入口重验同一共享DTO，按可信target_key从构造时传入的目标别名映射取表，不读配置/env。整个操作用同一≤10s的monotonic绝对截止，含写前扫描、至多一次create或update及写后扫描；两次扫描共用同一max_pages总预算，最多100个实际query＋1个实际write，Root真实窗口总cap另外约束。预扫消耗完预算则不开始写；循环不重置deadline、不自行延期/重试/生成token。异步取消写结果为unknown，不从取消推导未发生写入。

| 共享operation | 实际离线规则/调用次数 |
|---|---|
| reconcile | 永远仅query；完整原键零/多/缺键/内容版本不符保持unknown/conflict/stale；只有共享bind核过才能verified |
| create | 先全扫；同内容同版本已有行直接verified/零写；高版本stale/零写；只有A明确create且完整原键零行才至多create1，然后完整回读。unknown恢复必须另走reconcile，不能将零行重新造行 |
| update | 必须原external_id；原行更高版本stale/零写，当前完全一致直接verified/零写；较旧完整原行的不可变字段匹配才至多update1，再全扫。缺行/错row/不可变内容不符/缺键不写，不create |
| ACK丢失 | 本次立即unknown；下一原request/reconcile只读恢复，原token/item/row不变；不隐藏重试或用新adapter实例重置外部幂等 |
| 429/code | HTTP429或未知code单独不作无写证明；只1254290/1254291具体供应商拒绝合同分类可给write_rejected=true/retryable，A最多3尝试另控；5xx/timeout/ACK/内部错误/未知code仍unknown |

共享bind接收实际observed_fields/observed_version/原record。低于request版本、same-version内容不符、缺字段均unknown；高于目标stale只读；错误record冲突。观察到的row/fields只是结果事实，只有verified可被A恢复external_link/标sent。不会以content_matches布尔或SDK ACK替代binding。

新增test_p4_base_adapter覆盖Protocol实例类型、唯一bind实际调用、create/update全生命周期、open→completed/closed、same/higher版本只读、immutable冲突、缺/多行与空列、SDK异常归一、原键ACK恢复、跨预扫/回读共同页预算、model_copy绕过阻断与target未配置零调用，以及预扫/写/回读三个绝对截止取消边界。全部HTTP/记录存储为Fake；新adapter实例恢复不冒称实际进程/PG重启。

适配首轮实际168pass/2fail/4.11s：两个旧临时测试仍期待内容不符conflict及unknown不带观察record，实际共享合同要求unknown并可保留观察事实。按已审合同修正后170pass/4.11s；完整适配新增全操作用例后A/B199pass/4.78s（A49+B150），7文件strictmypy/Ruff通过。再次扫描在新测试target别名的合成高熵字符串上current1/index0/history0，已经缩短合成alias，没有改规则/allowlist；新完整批最终扫描与全回归另记。

资源边界不变：没有读A未提交源、改共享九文件、第二消费者、PG/SDK真实认证/Base/WS/provider/secret/.env/Docker/browser，也未合远端PR/main或关Issue。首批cb1精确CI38108175771属于旧临时DTO包；不能替当前共享适配源码CI或Root独立增量Review。首批1178offline/历史失败/敏感误报保留，当前新source必须另核完整回归与三scope扫描。


### 当前完整批作者验证与独审分层

完整A/B离线回归1256=既有1057+A共享49+B150，337integration deselected、两条既有SDK warnings，105.96s/exit0，在240s单批上限内。最终定向A/B199pass/3.80s、全仓Ruff/282format/203strictmypy/uv锁/75MD0error/diff通过；A九文件与精确d039逐字节相同、B仅8个独占文件有增量，current/index/fullhistory最终暂存与新提交扫描随freeze另核。

首批cb1已有Root发布的[独立Review5481738304](https://github.com/aning0922/commerceops-agent/pull/44#pullrequestreview-5481738304)：121pure/10.59s，Ruff/275format/mypy199/72MD/锁/diff/三扫描通过，锁定SDK transport确认为单次httpx调用无retry，首纯模块无P1/P2。该审核明确只覆盖临时DTO首包，不替代当前d039共享接口/全project操作批；当前新source须Root whole-package增量独审与精确CI。B没有自行安排代替Root的作者审核。
