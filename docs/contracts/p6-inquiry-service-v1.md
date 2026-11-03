# P6 只读查询任务与 Web 服务接线 v1 候选

2026-11-03（台北）。当前状态 `IMPLEMENTATION_CANDIDATE / REVIEW_REQUIRED / PG_NOT_RUN`。本文件消费已提交的 [执行器合同](p6-readonly-inquiry-v1.md)及[Mock facade/答案合同](p6-readonly-tools-v1.md)。原设计提交 `832c7d12097f4688c3416b078f8407b420e6c6a5` 只规划持久化、单 Worker 与 Web API；独立 P2 修复后已有未注册的服务实现候选，见末节。真实迁移、共享 API/Worker 接线和实际模型仍未验收。

## 现有约束与接入位置

[business_tasks/jobs](../../backend/migrations/versions/0001_task_foundation.py) 已有组织、店铺、请求人、持久 job 与审计外键。[JobQueue](../../backend/src/commerceops/infrastructure/queue.py) 只在持久终止确认后恢复 running；[Worker](../../backend/src/commerceops/infrastructure/worker.py) 只接受 `analyze/resume/recover`，且按 runner 的 `workflow_versions` 拒绝不认识的版本。因此新任务使用 `kind=readonly_inquiry`、固定 `workflow_version=p6-readonly-inquiry-v1`、一个 `kind=analyze` job，由现有串行 Worker 的 composite runner 按精确版本分发；不增加第二 Agent、Worker、调度器或旧 P0 图节点。运行中版本保持固定，不能把旧任务改成新版本重放。

现有 [Web 任务入口](../../backend/src/commerceops/entrypoints/replenishment_http.py) 先核当前会话能力再解析 body，POST 返回 202；[web_requests](../../backend/migrations/versions/0005_p3_approval.py) 的 `operation` 仅允许 `create_task/decision/resolve`。M3 使用独立 inquiry 请求记录，不能把读询问伪装成原 `create_task`，也不改旧操作约束。原 [请求回执读取](../../backend/src/commerceops/infrastructure/replenishment_read.py) 核当前 principal 与可见任务；新回执遵同一安全性质、独立路由。根 API/Worker/共享权限属于 Root/Backend 后续单 owner 接线，不由本候选文档触发更改。

## API 与严格 DTO（候选）

| 操作 | 请求/响应 | 服务端边界 |
|---|---|---|
| `POST /api/v1/readonly-inquiries` | strict body：`schema_version=p6-inquiry-web-v1`、`shop_id`、`question`（1–2000 字）、可选 `context_report_id`、UUID `request_key`。202：`task_id/request_key/state=queued/duplicate=false` | 当前 Cookie 会话、Origin、CSRF、body 长度/字段、请求人启用状态及该店铺读权限先校验；报告 ID 如提供，先按当前对象权限核验。不得提交 `actor/role/source_url/model/key/budget/worker_owner` |
| `GET /api/v1/readonly-inquiries/{task_id}` | 当前任务状态、固定 workflow/source/evidence_mode、安全结果或澄清候选、逐 claim 的 Fact 引用与来源/`as_of`、只读轨迹、可用 usage/耗时 | 当前 principal、组织/店铺与任务对象资格每次重查；`queued/analyzing` 不装作结果已生成；失败只给安全码。无权与不存在同一 404 安全形状 |
| `GET /api/v1/readonly-inquiries/requests/{request_key}` | 同 principal 原请求回执：`task_id/state/duplicate`，结果未知时给当前已持久事实；未找到以安全 404 表示 | 跟 POST 完全同一 operation 命名空间与当前身份/对象范围；不会根据前端是否等待过来创建新任务 |

首片只要一个显式只读查询入口，不更改现有 P0 五意图 [GuardedRouter](../../backend/src/commerceops/application/commerce/inventory_routing.py) 的合同。Web/飞书未来可由服务端识别同一 `readonly_inquiry` 用例，但飞书外发需另绑对象和权限，不随本次 Web API 自动开放。候选路由最终交 Backend 按 Pydantic strict DTO 生成精确 OpenAPI；前端用现有锁定的 Ajv/schema 同步方式校验响应，不手写假 API 或绕过旧 schema 版本。状态枚举、错误码及 URL 只有代码与 OpenAPI 同源后才冻结。

前端页面应明确标“本地演示数据 / 离线模型替身”以及报告窗口/来源；排队时显示“正在查询”，缺证据或来源不完整时给安全原因和下一步，不用 `HTTP 202` 宣布已有答案。产品文字展示库存、销量、证据与时间，不暴露原始 token、完整 prompt、内部预算 Gate、凭据、订单客户信息或任意来源 URL。深链每次重验登录和对象资格，撤权后清缓存及准备提交状态。

## 持久事务、一次性回执与结果

拟在 Root 协调的 **0021** 迁移增加一张专属 `business.readonly_inquiries`：以 `task_id` 关联同组织/店铺的 `business_tasks`，保存 `principal_id / identity_id / auth_version / request_key / request_hash / source_binding / evidence_mode / prompt_version / context_report_id / state / result / safe_error / created_at / updated_at`。`UNIQUE(principal_id,request_key)`，请求身份、原问题摘要/规范 body hash、来源/模式不可变；只有受控状态、结果和安全错误可按版本 CAS 更新。结果必须保存规范 `Outcome` 的脱敏 Fact、强类型 Claim、各来源 `as_of`、窗口、完整性和安全 trace；数字保持精确字符串。对结果 schema/大小、组织/店铺一致性、模型模式与唯一来源引用设 DB/应用双层校验，并记录相应 `audit_events`。具体 DDL、ACL 和触发器需与 0020 父迁移真实冻结后审查，不在文档假写 SQL 结论。

POST 在同一短事务：按 `(principal_id,request_key)` 串行化 → 重查会话身份与 role/shop scope、报告对象资格和服务端来源能力 → 计算与路径/规范 payload 绑定的 `request_hash` → 若原记录存在，核 payload hash 与可见任务，返回原 task；否则创建原 Web 会话关联的 `business_tasks`、一条 `business.jobs(kind=analyze,dedupe_key=固定task)`、一条 inquiry 请求记录与审计。提交前任何失败全部回滚；commit 后回执丢失时前端只读 GET 原 key，不换 key 自动 POST。相同 key/同 payload 返回同 task；相同 key/不同 payload 为冲突；另一个 principal 的 key 不串读，也不能从 URL 猜结果。结果读取和重投均复核当前授权，历史受理不授永久阅读权。

Worker 认领后在同一 owner 下取不可变任务输入，重查当前 principal/auth_version/组织/店铺和 `context_report_id` 当前读取权，按固定 source binding 构造 [MockReadFacade](../../backend/src/commerceops/application/commerce/readonly_inquiry_tools.py) 与 [execute](../../backend/src/commerceops/application/commerce/readonly_inquiry_executor.py)。读工具内部每次调用的身份资格继续由 `IdentityPort` 核实；最终持久结果前再次核当前授权。`execute` 的 60 秒 deadline 包含全部模型/Tool 和来源分页，不从队列等待起算。停止/取消后须等底层同步来源调用退出并确认 Worker 终止，不能仅因 lease 过期重投。若已持久完成，冷重放只读原结果并将 job 正常结算，不再次调用 ChoicePort；未完成离线 Fake 可按同 task/同版本安全恢复，实际 provider 未有独立不确定回执/预算核实前一直关闭。

任务状态、inquiry 结果状态与 job 状态分开：`business_tasks.completed` 仅在规范结果/引用与终态审计同事务保存后设置；`job done` 本身不是成功答案。`clarify` 保存完整且当前有权的 SKU/安全标签候选与原因，但不替用户选 SKU。`insufficient_evidence/source_incomplete/timeout` 保留原任务、扫描计数和安全错误，不能伪称完整。API GET 可以从同一事务已提交的 inquiry 记录取出安全结果，不读取半写模型文本。失败或权限撤销后不披露旧 Fact。业务数值与用户文案由确定性 [renderer](../../backend/src/commerceops/application/commerce/readonly_inquiry_render.py) 从持久 Claim+Fact 得出；若异步展示或缓存，必须重新鉴权。

## 来源、模型开关与版本互锁

默认 `readonly_inquiry_enabled=false`，实际 provider 模式也默认关闭。唯一受控本地 demo 可由服务端显式选择 `offline_stub ChoicePort`、已有完整 Mock fixture 的固定 shop/source binding 和只读当前会话；同一个 `execute` 运行，响应和 UI 明确区分替身与真实模型。服务器配置决定 `source_kind/source_binding/provider_mode/workflow_version`，POST 不带这些字段。原 Mock fixture 的时间域、可用商品与订单快照是上限；“查询过去 30 天”只是执行器硬上限，不使 fixture 凭空拥有新日期。请求超出 fixture 完整时间域或来源能力时先澄清/返回不完整，不能挪用旧 Woo 测试店配置、旧凭据或放宽其原 18 秒/请求/页限制。真实来源能力、模型预算和 Secret/付费调用均需后续 Root 单独准入。

当前 [模型解释适配器](../../backend/src/commerceops/adapters/model_explanation/deepseek.py) 拒绝 `tool_calls`，旧 P204 预算又绑定旧 prompt/task；本片只用离线 Fake，同链演示“商品名→按真实匹配 SKU 选订单和库存→确定性答案”。真实 tool calling、usage/价格版本、独立不可释放预留、结果未知读前恢复和冻结 D05 必须另行接线与验收，不把替身 3 次模型循环记为实际 provider 调用。

## 实施顺序与最低真实本地 Gate

原设计要求 Root 统一协调 0020 知识迁移父链、0021 询单、唯一后端 owner 与 API/Worker 文件；本片实施前 Root 已明确分配 `0021/down_revision=0020`，0022 留给日报调度，当前树尚未合入 0019/0020。先冻结 Pydantic 请求/响应/OpenAPI 与 migration/ACL；再完成新 owned PG 下的 POST 原键并发、commit 后回执丢失读原键、同 Worker `analyze` dispatch/重启/持久完成、撤权/跨店/报告对象拒绝、partial 页与候选澄清；最后以本地显式 offline_stub/Mock 完整 Web 请求闭环核 DTO、审计、来源标签和清理。无真实模型时 D05/provider、实际飞书和 Woo、生产部署、完整 M3 Gate 一律 `NOT_RUN`。自有 PG/API 服务、精确独审和 CI 的实际证据由 Root 后续记录，设计提交不代签运行。

## 首片服务候选与共享接线清单（2026-11-03，待独审/PG）

本批在独立 P2 修复 `22b60150add80f59613445260e1e2851b5d0b86f` 之后实现服务片，未混入该修复提交。新增严格 service DTO、默认关闭的 `InquiryConfig`、专属 `InquiryStore`、当前 PG 权限与报告读取 runtime、同一 `analyze` runner 及独立未注册 `inquiry_router`。POST 只接规范问题/店铺/可选报告/原键，服务器决定固定 Mock fixture、来源摘要、七个完整店铺自然日覆盖域及 `offline_stub`；GET 回执/结果公开这个域和“本地演示数据 / 离线模型替身”标签。DemoChoice 仅支持明确演示语法“库存 <精确名称/SKU>”“销量 <精确名称/SKU>”“解释报告”（需服务器已绑报告），实际工具与结果依旧通过同一 execute；它不是实际 LLM 或通用语言理解验收。

`0021_p6_readonly_inquiries.py` 的 `revision='0021'/down_revision='0020'` 按 Root 正式分配，含专属表、请求不可变/单次终态结果、当前 operator/会话资格、任务绑定与终态结果保护触发器、`valid_readonly_inquiry_result` 及有限 ACL。当前树没有 0020，未运行 Alembic 或 PG；真实迁移、并发幂等、同事务原键受理、commit 后失回执、真实撤权/对象读/冷重启与资源退出均 `NOT_RUN`。本地默认 disabled，只在后续 Root 明确配置/owned PG 窗口下开启。旧 web_requests operation、原 P0 Router、共享 API/Worker/Compose/锁/CI 未改。

Root/Backend 后续最小接线：在原 API 壳构造 `InquiryStore(web_config, inquiry_config)`，以真实 `SessionStore` 挂 `inquiry_router`；合并同源 `p6-inquiry-web-v1.openapi.json` 到原导出并保证全局 middleware 对 P6 身份/CSRF错误使用 P6 错误形状，不能让旧 P3 envelope 穿透。Worker composite runner 需按精确 WORKFLOW 分发 `ReadonlyInquiryRunner(store,session,runtime_factory(store,session))`，仍同单 Worker/一个槽与现队列终止确认流程。现有 `worker_lock.mark_attention` 的终态特殊排除尚无 P6；集成前必须对本片 `completed/failed` 且经 `business.valid_readonly_inquiry_result` 核验的持久结果增加窄排除，并真实验证完成至 job 结算间的异常退出，否则新终态保护会拒绝覆盖且影响共享扫描事务。不能删除原终态保护规避此项。运行角色若在迁移后才创建，原 grant-runtime 需显式调用本表的最小权限授权；本片没有写共享权限入口。

作者离线测试仅为 strict DTO、内存替身 ASGI、安全来源时间域、实际 Mock facade/renderer 的 runner 生命周期和完成重放，以及取消时等待有界数据库线程退出；不把 MemoryRunnerStore 或 HTTP Store double 当 PG 权限/事务证据。初轮 HTTP 测试配置的重复密钥/非法本地主机名导致 7 项未进入接口，修正为两组独立运行期测试值及 localhost 后通过。OpenAPI 资产由 `python -m commerceops.entrypoints.inquiry_http --export ...` 从真实 Pydantic DTO 生成，测试精确比较资产。全量 CI、真实模型/平台与 Web 页面仍待集成，不在本候选宣称完成。

报告读取只支持当前有权的 `analysis_reports` 原始报告，不混入 P3 重观测/日报。读取沿同一个有 SQL/锁超时的事务验证当前 job/来源/对象、持久报告绑定和既有 `_stored` 重算校验；旧报告窗口显式映射 start/end，不向新严格窗口 DTO 透传旧 schema 字段。新增回归首轮 23 pass/1 fail 捕获这个 schema 差异，修正后相关合计 **103 pass**（原 P2/Mock 79 + 服务 24），9 个 Python 文件 Ruff、format、mypy 通过。四项报告事务替身测试覆盖正常、无效持久绑定、报告篡改与未完成状态；不证明实际 SQL 权限或锁。执行器仍按原 60 秒 deadline 取消调用，取消后等待数据库线程真正退出；真实 PG 下截止后的排空耗时/进程终止须由后续 owned 窗口量测，单测不代签墙钟上限。未启动 Alembic、PG、API、Worker、真实 SDK 或模型。

提交前只对 22fix 加本服务片的 18 个文件做隔离内容扫描，没有运行全历史扫描。Gitleaks 8.30.1 对 working/index 各报告 3 个 `generic-api-key` 原始命中：0021 中的身份字段 SQL、询单 receipt 路由操作名，以及 22fix 中的 stock_pool_key 比较表达式。作者检查对应行均为代码标识符，没有凭据字面值；原始退出码 1 与三处命中保留，扫描策略的独立复核仍 pending，不宣称完整扫描 Gate 通过。未修改扫描规则或已冻结的 22fix。

## 精确父 revision 更正（2026-11-03）

直接从 K2 精确提交 `e1a52d6bfe2739f5890bf04c4bf2aafc36c00fc8` 读取 `backend/migrations/versions/0020_p6_knowledge_copy.py`，实际 `revision='0020_p6_knowledge_copy'`。原服务候选 1a78 的短 `down_revision='0020'` 是错误占位，本独立修复更正为 `0020_p6_knowledge_copy`；本片自身 revision 保持 `0021`。上文短父值仅记录原设计/首候选时点，后续运行以这个精确父值为准。K2 自身父链由知识 owner/Root 另修至 `0019_p6_daily_reports`，本树没有复制该迁移或读取其他工作树 WIP；未运行 Alembic/PG。

## 1a78 两项 P2 修复候选（待复审与真实 PG）

原独审 `HOLD/2P2` 保留，原 103 pure 不抵该阻断。0021 现嵌入冻结请求/结果 DTO JSON schema，专属 SQL 校验拒绝缺必需字段、错误类型/枚举、JSON null、额外字段及不合法嵌套结构；返回值和 CHECK 显式 `IS TRUE`。表与 `valid_readonly_inquiry_result` 复用同一请求及结果有效性函数，包含规范内容/hash、schema/mode/workflow、状态映射、调用轨迹、来源、事实 SKU/窗口和引用约束；正确 hash 不授予不合法 JSON 有效性。SQL 解析/实际约束仍未运行，不能仅据 Python 检查撤销 HOLD。

`owned_row` 先验证当前 running job 的 owner/attempt/scope/payload、同任务不可变请求及原请求 hash。已有持久终态走严格 decode、共享 SQL 有效性及 renderer 后可结算 job，无需原会话仍有效或 fixture 仍存在，也不创建模型/来源 runtime。非终态继续原当前鉴权和来源验证；撤权/会话失效或来源文件不可用时，runner 仅通过当前 owned job 将固定 `access_denied`、零模型/工具/扫描、零事实/claims/options 的安全失败持久化并结算。触发器对此失败提供窄例外，成功保存/正常执行/用户 GET 仍要求当前授权。commit 回执未知时重新读已持久终态，不把成功结果覆盖为失败。纯测新增拒权后不创建 runtime 的控制流回归，合计 104 pass；这不证明真实 SQL、冷重启或截止退出。

## 独立 PG 测试矩阵候选（只收集，NOT_RUN）

`tests/test_p6_inquiry_pg.py` 与私有路径输入的 `tests/p6_inquiry_process.py` 新增 36 个 integration 节点，`--collect-only` 已成功，模块导入/收集不读取数据库设置或连接 PG。实际执行将使用独立临时数据库、真实 `commerceops_app`、真实 Web 会话和本服务 store/runner/queue；不在 fixture 额外补授本表权限，Root 的实际最小授权遗漏会直接失败。数据库清理仅针对测试自身创建的库，所有测试和子进程运行目前均为 NOT_RUN。

覆盖低权 ACL、SQL NULL/JSON null、提交前回滚、同 key 并发/异文、提交后失回执读原键、有效同店其他 operator 的原回执隔离及同 key 独立命名空间、跨身份/组织/店铺拒绝、角色/scope/凭据/会话撤销、正确 hash 的空对象/缺字段/null 结果反例和缺字段/null 请求 SQL 校验、撤权后无事实失败及幂等结算、结果 commit ACK unknown。SQL 阻塞两例保留真实行锁/原键 advisory 锁，取消调用后确认同步线程退出再返回；该测试断言短取消截止及最多 8 秒排空，不代签完整 execute 的 60 秒墙钟。

四个独立进程恢复变体在实际结果 commit 与 job 结算之间屏障停止，父进程确认子进程 kill/wait 后才调用原 `confirm_termination`，新进程经原队列恢复并以禁止创建 runtime 的 factory 冷重放；比较同 task/request 的结果规范内容/hash/version 不变及 job 第二 attempt 结算。变体包括原会话过期、fixture 不存在、主体撤权；这些只允许内部结算，用户 GET 仍被拒绝。该用例直接调用原 `mark_attention` 并要求持久终态保留，当前树缺 Root 的窄排除时会失败，不能跳过或删掉断言。测试覆盖真实 runner/session/queue 协议，完整共享 Worker/API 壳注册与端到端进程测试仍由 Root 集成承担。

本批最终静态检查涵盖 6 个 Python 文件 Ruff/format/mypy；原 3 个扫描命中继续保留，按 Root 指令未再扫描、未添加 allowlist。完整迁移父链/SQL 执行/真实 PG/服务/CI 仍未运行。

## 18a297 复审新增两项 P2 的最小修复候选（待复审，PG_NOT_RUN）

独审已确认原两项 P2 实质关闭，但新发现 CASE 解析与安全失败用量归零，继续 HOLD。原 104 pure 不抵独立探针：真实 execute 用 model3/tool2/scanned3 后，finish 撤权进入 fail_safe，18a297 会把三项错误写成 0。原提交及该失败事实保留。此前“固定零模型/工具/扫描”的描述仅属于该有缺陷候选，不能作为恢复后的准确用量。

本次把 migration 全文件两个 CASE 表达式均加括号，claim 的 fact/compare arity 仍为 1/2；全文件静态检查为 CASE 2 个、未包裹 0 个。它不替代实际 PL/pgSQL 解析/执行。runner 在 execute 返回后保留 typed payload，finish 失败时交给实际 store 的 fail_safe；store 再严格验证并仅复制已知 model_calls/tool_calls/scanned_rows 和允许的 tool id/name/args_hash trace，清除所有结果、facts、claims、refs、候选。SQL 窄安全失败谓词允许原范围内计数和相应 trace，共享严格 payload 校验与零披露条件继续适用。

计数明确只代表**本次 executor 尝试的已知用量**，不作为跨 job attempt 累计；历史尝试用量为 **UNKNOWN**。execute 尚未开始的本次尝试才可记录 0；普通 executor 失败仍返回带已知计数的 Outcome，不能回到默认 0。DTO 字段描述、同源 OpenAPI 与 migration 冻结 schema 同步标明这个边界。已有终态及 commit ACK unknown 的重读路径继续保留原结果，不由新安全失败覆盖。

新增离线回归运行真实 runner/execute/DemoChoice/Mock facade/实际 store 的 load→mark→finish→fail_safe，只有数据库 transport 和鉴权边界为 double：确认 finish 前 complete 结果已有 3/2/3，撤权后 SQL 写入仍为 3/2/3、两条相同安全 trace、零 facts/claims/refs/options，原失败回执重放不再次调用或写入。相关离线总计 **105 pass**。这是服务路径回归，不是 PG 权限或 SQL 通过证据；独立 36 节点 PG 矩阵 `9d79388d9c45cc8e7bdbec3e771832e19c8c4483` 保持不变且 NOT_RUN。未启动 PG、未全扫或添加 allowlist，原 3 个扫描命中保留。
