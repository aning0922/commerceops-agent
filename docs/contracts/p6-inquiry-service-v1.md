# P6 只读查询任务与 Web 服务接线 v1 候选

2026-11-03（台北）。状态 `DESIGN / REVIEW_REQUIRED`。本文件消费已提交的 [执行器合同](p6-readonly-inquiry-v1.md)及[Mock facade/答案合同](p6-readonly-tools-v1.md)，只设计持久化、单 Worker 与 Web API 接线；不表示已有 API、迁移或真实模型。本批没有改 `3cab0c98f6c679f9d53fdcd2c83d7bfe70f314f9` 的源码。

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

Root 待 0020 知识迁移父链冻结后，统一分配 0021、唯一后端 owner 与 API/Worker/迁移文件；0022 留给日报调度。本合同不预占迁移实际 revision，也不假设 0019 日报已经合入本工作树。建议先冻结 Pydantic 请求/响应/OpenAPI 与 migration/ACL；再完成新 owned PG 下的 POST 原键并发、commit 后回执丢失读原键、同 Worker `analyze` dispatch/重启/持久完成、撤权/跨店/报告对象拒绝、partial 页与候选澄清；最后以本地显式 offline_stub/Mock 完整 Web 请求闭环核 DTO、审计、来源标签和清理。无真实模型时 D05/provider、实际飞书和 Woo、生产部署、完整 M3 Gate 一律 `NOT_RUN`。自有 PG/API 服务、精确独审和 CI 的实际证据由 Root 后续记录，设计提交不代签运行。
