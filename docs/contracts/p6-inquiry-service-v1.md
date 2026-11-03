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
