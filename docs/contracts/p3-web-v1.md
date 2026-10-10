# Phase 3 Web、身份与业务接口合同 v1

状态：A 首批合同候选，待总控安排冻结 SHA 独立审核；接口尚未实现。本文件和 [OpenAPI](p3-openapi.json) 是 B typed client 的候选输入，审核冻结前只能做醒目标识的 Mock，不能接正式操作。

2026-10-10（Asia/Shanghai），基线 main `59b350cb719a9d2fed3f68b1ee598fa0a9b97875`。本轮授权来自 [Issue #33](https://github.com/aning0922/commerceops-agent/issues/33)、[A #34](https://github.com/aning0922/commerceops-agent/issues/34) 及总控直接派单；旧文件的“Phase3 未授权”是历史。A 负责本合同、后端和迁移；B 负责 frontend、npm lock 与 Web E2E；共享 CI/Compose/scripts/阶段文档经总控协调。没有通用 RBAC、新调度器、外部采购/库存改动、付费模型调用、飞书业务写入、生产部署或 Phase4 实施。

设计依据：[PRD](../PRD.md)、[ARCHITECTURE](../ARCHITECTURE.md)、[DATA_MODEL](../DATA_MODEL.md)、[AGENT_DESIGN](../AGENT_DESIGN.md)、[TEST_PLAN](../TEST_PLAN.md)、[30天计划](../plans/30_DAY_EXECUTION.md)、[冻结 UX 交接](../ux/ux-freeze-candidate.md)、[最终 UX 索引](../ux/m1-ux-final-freeze.md)。18 页/47 语义控件/0.4.1 冻结不追加视觉批次。

## 1. 传输、账号和会话（BC01/05）

全部新 Web 端点在 `/api/v1`，JSON UTF-8，输入对象 `additionalProperties=false`；整数拒绝 bool/float，UUID/UTC 时间/hash 严格校验。GET 无业务副作用。响应 `Cache-Control: no-store`、`Vary: Cookie, Origin`；浏览器 fetch 使用 credentials，认证/CSRF/nonce/密码不写 localStorage、URL、console、访问日志或审计正文。浏览器直连 API，Next 仅呈现/同源代理，不运行 Graph 或业务写逻辑。反向代理不得缓存会话、替换当前 actor，转发 Origin 不改写成可信源。现有 `entrypoints/api.py` 全局 validation handler 的 p203/p204/400/analysis_only 仅用于旧路径；新P3入口须先做缺身份/CSRF/对象授权校验，再按下述p3错误envelope/422严格校验，禁止套用旧handler。旧端点/DTO/原错误合同保持；P3运行时与导出schema差异作为后续必测。

账号预置到 P3 自有库，固定 login → web identity → principal。login 仅ASCII小写字母/数字/点/下划线/横线，1–100字符；输入外层trim和ASCII lower后匹配固定账号（不改密码正文）。无注册、角色选择器、客户端 actor/role、JWT 自授权或 localhost 后门。账号配置只在私有资源生成流程进入本阶段库；不读取 P1/P2 `.env`、凭据或旧数据库。密码只存 scrypt 哈希，随机至少 16-byte salt，`N=131072/r=8/p=1/dkLen=32`，带算法参数版本；运行时容量明确支持此内存成本，不能默默降低。验证 constant-time，未知用户做同成本 dummy 验证，错误统一 `LOGIN_FAILED`。预置过程不在源码/迁移/样例/PR 保存真实密码或哈希。

认证采用 PG 服务端会话，Cookie 仅不可预测至少 32-byte 随机 opaque token，库仅存 SHA256 token digest、identity/principal、auth_version、创建/最近活动/绝对与空闲期限、撤销状态。登录成功轮换 session/token 和 CSRF，旧/匿名会话撤销；logout 撤销并清 Cookie。会话不存决定授权；每请求重查 identity/principal enabled、auth_version 和当前逐角色 scope。auth_version 变化使旧 session 失效，返回通用 401，不泄漏对象。scope 变更也递增 principal auth_version；T3/T4/T6 与撤权锁协调见第 5 节。

Cookie `commerceops_session`：HttpOnly、SameSite=Lax、Path=/、无 Domain；HTTPS `Secure=true`。仅显式 `local_http` 配置允许自有 loopback HTTP 测试 `Secure=false`，仍认证/CSRF/Origin，日志/UI显示 local_http，不能外推生产。`https` 配置遇非 HTTPS/空或通配 Origin 不启动；Cookie/token 不作为 OpenAPI examples。会话绝对期限初值 8h、空闲初值 30min，均为部署配置，读取端显示实值而非承诺；匿名 bootstrap 会话最长 5min。账号和密码哈希只在 gitignored 私有配置/数据库，不进入 fixture/docs/frontend。

`GET /auth/csrf` 建立/复用匿名 bootstrap 或当前 session，返回与该 session 绑定的 synchronizer CSRF token、server_time，identity_mode区分anonymous_bootstrap/session；仅对精确允许 Origin 的跨源读启用 credentials CORS，同源可无 Origin。token 为 HMAC-SHA256（P3 私有专用 csrf 密钥、固定用途前缀、session 随机 ID），base64url 无 padding；session 保存 digest 和 key_version，刷新可安全重建，session 轮换使 token 改变，不放 Cookie。`POST /auth/login` 也须 bootstrap Cookie、`X-CSRF-Token` 和允许 Origin，JSON body；登录 CSRF 同样被拒绝。`GET /auth/session` 回当前 actor、按角色 scope 形成的 capabilities、csrf_token、会话/配置实值；`POST /auth/logout` 同样校验 CSRF 与 Origin，JSON body仅schema_version=p3-web-v1。

所有 POST 都拒绝 missing/`null`/非允许 Origin；比较完整 scheme/host/port，不用后缀或 substring，不信任请求 Host 构造 allowlist。CSRF constant-time 比较当前 session 的 digest；SameSite 只是附加保护。只接受 `application/json`，不允许 form/text/plain 降级。允许 header 仅 Content-Type/X-CSRF-Token，method GET/POST/OPTIONS；credentials CORS 不使用 `*`。OPTIONS 无业务副作用、无登录成功语义。preflight 通过不代替写操作校验。

登录速率由 PG 持久滑动窗口按规范化 login +可信客户端来源分别限制，初值每 5min 各 5/30 次，429 `RATE_LIMITED` + Retry-After；未知用户也计数。不接受任意 X-Forwarded-For，单机直连用 socket peer，仅显式可信反代名单可解析代理链。不通过账户存在性差异暴露账号；无全局内存计数器、无永久锁号。

上述安全参数选择参考 [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) 的 scrypt 基线与 [CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) 的 session-bound token/精确 Origin 校验。这是文档依据，尚非本项目实际安全测试。

## 2. 当前授权、对象范围与无泄漏

复用现有 principals/identities/organization/shop/`principal_shop_scopes` enabled 事实及 P2 owner 查询。P2 scope 表只有 enabled，P3 补充固定 `principal_role_shop_grants`（organization/shop/principal/role/enabled，role 仅 operator/approver/admin）；不做可配置权限目录、组织树或通用 RBAC。P3 授权必须同时满足 principal 当前具有该角色、该角色 grant enabled、基础 shop scope enabled。不得以旧基础 scope 默认补齐所有角色 grant；预置时显式写每个 grant。

| 动作 | 当前角色及对象条件 |
|---|---|
| 新分析/新正式 Workflow | operator 在目标 shop 自身 grant 内；shop_id 仅选择已授予范围，组织从 session 得到 |
| P2 analysis task/report/events | operator 在该 shop 且 requester=当前 principal；沿用 P2 owner 隔离 |
| P3 task/报告/轨迹/plan/item 读取 | 同店 operator 的本人 task；或同店 approver 且在该 Workflow 审批 eligible 冻结集合中；item 沿关联计划校验 |
| 历史审批/决定回读 | 上述业务查看权，历史只读；eligible 不绕过当前 role/scope |
| 当前审批决定 | 同店当前 approver + pending/current plan + eligible；nonce/hash/期限/质量全校验 |
| 完成/关闭单 item | 同店当前 approver（不要求原审批人），且有该店固定 approver grant；读取 item 详情对该 grant 可见以便跟进，历史 item 同范围可读 |
| 运维摘要 | admin 自身 grant；仅脱敏配置/Worker恢复摘要，不含任务编号、SKU、金额、跨scope计数、identity或秘密 |

兼任是各角色已授权动作和对象集合的并集。例如 operator@shopA + approver@shopB 不能 approve shopA，也不能读取 shopB 上未 eligible 的任务；admin 不带业务读权或批准权。item 跟进的同店 approver 读权是明确独立规则，不能向上展开成未 eligible 源任务完整业务读取；其 SourceLinks 只提供当前身份有权读取的链接（不可见源不返回编号）。

列表 total、按状态 counts、page items 使用同一事务一致快照、同一当前 actor/角色scope/owner/eligible 谓词及过滤条件。count 不含不可见对象，不从全店数扣不可见数，不用前端隐藏行。`as_of` 为数据库观测时间；下一页重新授权，数据可变化，不承诺跨请求快照。cursor opaque、签名，绑定 actor/auth_version/endpoint/scope/filter/order/最后键；错误或撤权统一拒绝，禁止任意 query shop_id 扩权。列表排序 created_at DESC、id DESC；limit 默认 20、范围 1–100，完整审批详情不分页。

无 session → 401；无此类业务能力的账号 → 通用 403 `ACCESS_DENIED`；有此类能力但对象不存在/跨组织/跨店/非owner/非eligible → 相同 404 `RESOURCE_NOT_FOUND`。同错误 response body/shape，不含请求对象 ID、当前 plan/version/nonce、SKU、隐藏计数或其他 actor。格式错误的对象 ID 同 404；业务对象授权先于 payload 绑定错误回执。已认证可读对象的 409 可携既有决定/回执；无查看权不能用冲突错误泄漏对象。状态/决定回读也重新授权，原 actor 撤权后不能凭旧请求键拿回业务结果。

## 3. P2 证据、正式 Workflow 与 DTO（BC03/05）

P2 `inventory_analysis_only / p203-inventory-analysis-v1` 的 completed、immutable report/snapshot/checkpoint 原样保留。P2 DTO `p203-read-v1`、`p204-read-v1` 和 `inventory-analysis-v1` 不改 schema/事实/hash；旧模拟 read DTO 不标为真实 session。新 `/api/v1` p3 envelope `schema_version=p3-web-v1, identity_mode=session` 封装服务器读取的既有 InventoryReport；其中 `analysis_only=true/execution_available=false` 仍表示分析事实。正式执行权来自独立 `Plan/Approval`，不从 report 的布尔值推断。

`POST /tasks` 是明确 operator 操作、202/T1 持久回执，有 principal+endpoint+request_key 持久去重。此处endpoint是固定operation（create_task/decision/resolve），不是含对象ID的具体URL；同一键不能因换approval/item_id被复用。两种严格互斥 input：

1. `mode=from_report`：source_task_id/report_id/snapshot_id/facts_hash + request_key。服务器在原 owner/scope 下读取完整可信 P2 结果，绑定同组织/店，不能接受客户端 SKU/数量/quality/eligible。只创建新正式P3 task UUID/thread_id及首个P3 job/回执/audit，**不新增源P2 task/job**，不恢复或改写源 task。同actor/operation/key重复10次/ACK丢失只回原P3回执，源task/report/snapshot/checkpoint不变。无完整报告/硬质量错误不能创建可执行 plan；零建议为 no_action，>20 正式候选为 SCOPE_REQUIRED，不能截断。
2. `mode=new_cycle`：shop_id/request_key/结构化 mock parameters（fixture_case/L/R/S）。显式提交才创建新的 P2 analysis task 和独立 P3 task；两者与各自首个job/audit/T1 请求回执同事务绑定，Worker 串行完成新 P2 分析后再绑定可信新 report/snapshot 到 P3。同actor/operation/key重复10次/ACK丢失回原两个task及原job的绑定回执，不再创建第二轮；原key异payload409。默认仍最近七个完整自然日；不调用新的付费模型。源 completed 页面 B46 只复制本地参数到草稿，无旧 approval/hash/nonce/request_key/assumption 继承；B01 生成新键提交。fixture_case 仅来自自有 Mock inventory-v1 固定目录允许名单，不接受路径/URL。参数在创建时冻结，整数 0–365；自然语言草稿需先明确结构化参数，不新增模型预解析端点。

P3 固定 `kind=inventory_replenishment / workflow_version=p3-inventory-replenishment-v1`。state：queued/analyzing/awaiting_approval/executing/completed/rejected/expired/needs_reapproval/failed/needs_attention。T2 绑定 source P2 task/report/snapshot/facts_hash、参数/质量、不可变 plan_version/plan_hash；plan/status 分离，历史 immutable 内容不可覆盖。拒绝/过期不重新开启旧 task；执行后 items 生命周期不改变 completed。

`GET /tasks` 同时返回有权 P2/P3 摘要，kind/workflow_version 显式区分；详情包括 business_status、approval、execution、items 与独立 sync 汇总、允许动作和禁用原因。`GET /tasks/{id}/report` 返回可信 source IDs/facts_hash/观测时间/完整性 + 原 InventoryReport，默认当前，`report_id` 可选但只允许关联同 task 的冻结报告。`GET /tasks/{id}/plans` 以同limit/cursor合同分页列冻结版本摘要/total/as_of；`GET /tasks/{id}/plans/{version}` 读取完整历史，历史 `can_decide=false`/nonce=null。approvals view默认visible=当前全部可读，mine=当前可决定，history=可读终态；state筛选也进入counts谓词。events另按occurred_at/event_id升序分页（limit默认20），不使用task的created_at排序。没有重算、retry、续答、手工发送、重启 Worker 或权限管理端点；M05/B36、F02/B47、B32/B34 保持禁用说明。

解释 M04 仅读 `GET /tasks/{id}/explanation?report_id=...` 中既有 P2 explanation；指定 report 不匹配拒绝，没有则 NOT_READY，可展示确定性模板但必须说明原 explanation 缺失。禁止 GET 调模型，禁止动态查数/RAG/重算。

审批详情单次完整披露 ≤20 items、item_count/total_units、全部 hard_blocks/quality_flags/required_assumptions、来源/窗口/规则/LRS/期限/version/hash。`disclosure_complete` 只来自服务器输出完整性；B 校验实际渲染数=item_count，响应部分/未知/历史时禁用决定。未知在途 raw null 和 effective=0 同列，不默认勾选。客户端声称完整或 eligible 均不能授权。

## 4. 决定、resolve、hash 与原请求恢复

`POST /approvals/{id}/decision` input：schema_version、request_key、approval_id（必须等于 path）、plan_id、plan_version、plan_hash、action、acknowledged_assumption_keys、nonce。action 仅 approve/reject/approve_with_assumptions/reject_assumptions。actor/role/approved/eligible/source/组织字段禁止输入；来源固定为 session/human_web 的显式 Web 操作，自动化 Gate 记录 simulated_web 而非真人点击。API来源审计=web，不以客户端报模式认定真人验收。

普通 approve 仅无假设集合，keys=[]；有未知在途返回 ASSUMPTION_ACK_REQUIRED、pending、不建 resume job。approve_with_assumptions 仅计划存在该类型且请求去重后集合**完全相等**、无重复键；漏/多/未知/重复拒绝 ASSUMPTION_SET_MISMATCH。所有拒绝 keys=[]；reject_assumptions 必须计划存在假设，保存 INBOUND_ASSUMPTION_DECLINED。无确认复用阶段。任一库存/分页/共享库存硬错误返回 DATA_INCOMPLETE，不允许确认绕过。

nonce 是本计划审批专用 capability，HMAC-SHA256（独立 P3 私有 nonce 密钥、固定用途前缀、approval 随机 UUID/plan_id/version/hash/expires_at 的 canonical bytes），base64url 无 padding；approval 存 digest/key_version，可服务器重建以便有权当前 approver 刷新回读，不入 checkpoint/审计。approval_id/version/hash/expiry 固定绑定，独立于 CSRF。只在当前有决定资格的详情返 nonce；operator/历史/终态返 null。当前原 actor 决定成功后 raw nonce 从响应消失，但浏览器持原请求可以重试；不需再取新 nonce 或重做决定。密钥不可用不能新造 nonce替换已有绑定，needs_attention。

计划 hash：SHA256 canonical JSON UTF-8、sort_keys、无空格、无 NaN/float，复用 `canonical-facts-v1` 编码；Decimal规范字符串、比值 numerator/denominator、UTC Z、null 保留。P3 hash version=p3-plan-hash-v1，覆盖 schema/hash版本、组织/店铺/币种、source task/report/snapshot/facts_hash、plan_id/version、rule_version/LRS、冻结销售窗口/库存需求事实、items按sku_key排序（pool/quantity/quality/raw inbound/effective）、完整假设对象按key排序（type/sku/估算0/disclosure_version）、expires_at。nonce/actor/决定、显示文案/模型修辞不进入 plan_hash。输入参数/假设/库存事实即使数量巧合相同变化仍使旧 plan 失效。

decision_payload_hash=p3-decision-hash-v1 canonical {approval_id,plan_id,plan_version,plan_hash,action,acknowledged_assumption_keys排序}；不含 nonce/request_key/投递事件。request_key 另按 principal+endpoint 绑定原规范 body 的 request_hash（包含 nonce 与 path，排除 request_key本身）。同 key 异 payload → IDEMPOTENCY_CONFLICT；同 actor 同计划同 action/语义确认集合且有效 nonce 的不同 key 重投也回原决定，不重复审计/resume；相反决定/另一 actor/不同集合 → DECISION_CONFLICT（仅有权读者可见原决定）。先重查当前身份/查看权，再查持久原回执；原决定有效同 actor/hash/nonce 重放可在期限/role变化后回读（仍需当前查看权，不重新批准）；新决定须当前 approver/eligible/当前 plan/有效期。approval expired 的新动作返回 APPROVAL_EXPIRED。

POST 回 200 DecisionReceipt：decision_id、原 actor/time/source、action/精确 keys/hash、approval_status、resume_state=queued/waiting_checkpoint/consumed、duplicate、task_id；批准文案为“意见已记录，执行处理中”，无内部成功保证。有效不同键语义重复在同事务保存新request_key→既有decision的回执关联，响应request_key为本次键，decision_id/actor/time/hash始终原值；没有新audit/resume。拒绝仍创建同键 resume job以便图收敛，内部项为0。既有决定/执行回执只按授权回读，不重新执行业务。

`POST /replenishment-items/{id}/resolve` input：schema_version/request_key/action=complete|close/reason/expected_version。reason 外层 trim 后 1–1000 Unicode 字符、禁止空白，原规范化 reason 纳入 hash；仅单 open item。原 key（principal+endpoint）+原语义 hash {item_id,action,reason,expected_version} 返回原 item/resolution_receipt，version只加1、审计和投影只写1次；原 key 异payload → IDEMPOTENCY_CONFLICT，新key对终态 → ITEM_STATE_CONFLICT，陈旧版本 → ITEM_VERSION_CONFLICT。返回 actor/time/reason/before_version/after_version/state/独立 sync，不表示采购或入库。

浏览器请求超时/响应丢失显示 unknown：保留原 key/原 body（含原nonce/expected_version），同键重投或读取 `GET /requests/{request_key}?operation=create_task|decision|resolve`。receipt scope=current principal+operation，仅按当前查看权返回 succeeded +严格 tagged result 或 404 RESOURCE_NOT_FOUND；404 仅表示该键无可见持久回执，不证明之前写入失败。无法确认不换键、不发相反动作、不重新建 task/item，展示“待核实”。错误 envelope `schema_version/server_time/trace_id/error{code,safe_message,retryable,receipt?}`，safe_message 固定中文白名单，validation 不回显原输入/SQL/密码/连接URL。

| HTTP | 固定错误语义（同类型不得含隐藏对象信息） |
|---|---|
| 400 | INVALID_CURSOR/INVALID_FILTER/INVALID_JSON；无法解码请求，固定错误无原输入 |
| 401 | SESSION_INVALID（缺失/过期/撤销/auth_version不匹配一致）；LOGIN_FAILED；不得带对象回执 |
| 403 | ACCESS_DENIED、CSRF_INVALID、ORIGIN_DENIED；无业务能力与安全边界，通用内容 |
| 404 | RESOURCE_NOT_FOUND；不存在或当前不可见完全相同，包括非法对象ID/不可见原请求 |
| 409 | PLAN_CHANGED/APPROVAL_SUPERSEDED、DECISION_CONFLICT、IDEMPOTENCY_CONFLICT、ITEM_STATE_CONFLICT、ITEM_VERSION_CONFLICT、ASSUMPTION_ACK_REQUIRED/SET_MISMATCH、DATA_INCOMPLETE、SCOPE_REQUIRED、NOT_READY；仅有权对象可获绑定错误/已决定回执 |
| 410 | APPROVAL_EXPIRED；当前可见审批新决定到期，不改变已决定的有效重复回执 |
| 415/422 | UNSUPPORTED_MEDIA_TYPE/INVALID_REQUEST；422严格字段/类型/范围/空原因，不回显字段值；业务写先认证及对象授权再校验绑定 |
| 429/503 | RATE_LIMITED（Retry-After）；SERVICE_UNAVAILABLE（DB/配置故障）；未知提交不能自动新键重试 |

scope撤销若令session失效统一401；重新登录后的其他对象scope不足按403/404上述谓词，不能借REVOKED错误泄漏隐藏对象。duplicate成功200/202且duplicate=true；conflict返回409；expired=410；superseded=409且历史只读。server_time正常取DB；DB不可用时error.server_time=null，并禁止客户端据此判断已过期或执行失败。

## 5. 事务、时钟与恢复事实（BC04/07）

T2：plan+approval+blocked card outbox 同事务，库存建议只来自可信确定性事实；全量零项 no_action，不建可批准空计划。固定单一 wait_approval interrupt，官方 AsyncPostgresSaver + durability=sync。checkpoint匹配 task/workflow_version/approval/hash 中断真正持久后置 ready_at，意图可从 blocked→pending，但 Phase3 sender 永久 disabled，不联网。ready_at 不是 T3 接受前提：过早决定先持久 T3/resume，再延期 job 直到匹配 interrupt；不丢弃，不注入第二决定。

T3/T4 统一 task→plan→approval→principal→库存池排序锁；T6 principal→item，不回锁task。固定 role grant/scope 撤权必须先锁 principal，再更改scope/递增auth_version；session检查不能代替事务内重查。权限、有效期以取得所需锁后的 DB clock_timestamp 为准，不用事务启动 now() 或浏览器钟。过期定义 db_time >= expires_at，边界等号拒绝。

T4 外部重新观测事务外；执行前最新一次完整受影响 SKU/必要销量事实、质量/库存池/原假设和当前授权全部复核。新鲜度配置上限默认 900s，但用实值；无法取完整新数据不执行。数量/风险/在途含 null→known/参数/开放项实质变化 → needs_reapproval，保存新的不可变 plan版本并生成新的 approval/nonce/hash，旧 pending审批 superseded；已 approved历史不改。新版本需要重新决定，不能继承旧确认。开放库存池冲突整计划拒绝创建，不部分执行。重观测事实仅时间刷新且实质一致可以继续，持久 revalidation_snapshot_id。

T4 transaction 写永久 operation_key=`restock:{shop_id}:{plan_id}:{version}`、request_hash、execution、全部 items、consumed_at、task completed、outbox与audit，全有或全无。post-commit checkpoint落后按原 execution 返回，不因原 item终态再创建；不存在回执才做新执行权限复核。永久执行回执不是短 TTL session/request缓存。

T6 单项终态释放 `(shop_id,stock_pool_key) WHERE status=open` 唯一约束，新周期必须新 task/采集/plan/approval。旧请求/旧 execution 保留且只作用原 item，不能重新打开。unknown 同步不回滚完成/关闭。

单 Worker/全局单 Graph，既有启动互斥、串行 analyze/resume/recover/outbox、等待中断释放槽、失锁停止与旧进程终止确认全部复用。不设多Worker、热接管/第二协调进程。GET events只返回脱敏已发生的步骤/attempt/checkpoint匹配结论/旧进程终止证明/receipt引用，不返回内部思维链、完整checkpoint或秘密；没有真实记录就空/未知，不伪造恢复成功。

业务 state 与 sync 独立。Phase3 outbox只持久化逻辑 intent/projection/reconciliation事实，不发送；SyncRead `{state:not_requested|pending|synced|failed|unknown, sender_enabled:false, projections:[version/status/error/as_of]}`，新 pending不是已同步；T2 blocked独立呈现。synced/sent只有已有持久外部回执才能显示，Phase3新意图不得凭替身标 synced。C05 本地受控失败标 source_mode=controlled_stub，不冒称飞书网络故障；unknown 不自动转 pending。

配置 GET /config 面向有业务能力当前 shop 只返回实际规则/时区/审批期限/新鲜度/最大条目/时钟；admin运维另只读脱敏摘要。默认配置初值 approval_ttl_seconds=86400，revalidation_max_age_seconds=900，max_plan_items=20，recovery_scan_seconds=30（Worker忙到下一调度点），session_absolute_seconds=28800/session_idle_seconds=1800；部署启动校验审批TTL 60–604800s、新鲜度1–3600s、扫描1–30s、绝对会话60–86400s、空闲会话1–绝对期限、max_plan_items1–20。缺配置 fail-closed，不用0模拟未知；null显示“未知”。同创建 plan 固定当时 config_version/expires_at，不随环境热改历史；新TTL只作用新计划，执行重观测使用当前配置。所有 p3 envelope server_time 从 DB UTC，UI使用 shop_timezone 显示，倒计时仅辅助，服务器再次决定有效性。

## 6. 前端映射与本批退出

| 冻结控件/页面 | 本合同动作 |
|---|---|
| S01、B30/B31、S07/S08 | csrf/login/session/logout；server capabilities决定有权落点；admin-only运维摘要 |
| S02/S09、B01/B46/M02 | scoped task list/detail；新周期草稿→显式 new_cycle；from_report创建独立正式Workflow |
| S03/M03/M04/B33 | report/provenance/existing explanation、plans版本读取；历史只读 |
| S04/S10、B02–B05 | approval列表/完整详情、普通或联合确认决定、同键回读；不隐式确认 |
| S05/S11/M01 | scoped item列表/详情、单项原因/expected_version/原键resolve |
| S06/S09 | events/recovery/execution/sync独立事实；无手动retry/重启/重发 |
| M05/B36、F02/B47、B32/B34、F01 | 未批准重算/续答保持禁用；F01真实容量与业务回调留Phase4 |

机器合同包含完整 path/schema/response/error/CSRF需求。冻结后B可生成 typed client；A实现必须与OpenAPI做差异检查，不以文档候选当作运行端点。首批检查仅证明 schema/绑定/禁用边界，不能证明 session/PG/T2–T6/真实 Web。后续必要 Gate 按 #33/#34 逐项源码/命令/时间/结果留证：R01/R05–R12/R17、S01–S03、A01–A08/C01–C05 的本阶段部分、当前内容/历史敏感扫描、原离线金标/真实PG/CI、冻结独审和集成。额外固定真实PG迁移前后P2completed task/report/snapshot及官方checkpoint字节/hash/ID原样断言；同源与精确允许跨源登录/读/写/OPTIONS、未允许Origin/缺CSRF/logout/撤权拒绝。R01使用自有受控入站/入口恢复，不新增飞书业务。human_feishu/外部Base/R13–R16/Phase4保留未跑。

人工有效工时 not_reported；32h是原60h内A容量分配。首批Agent墙钟/机器等待与实际合同检查在 [交付记录](p3-contract-delivery.md) 分别记录。合同提交、push、同一Draft PR（Refs #33/#34）后停止主体实现，等待总控独审冻结/放行；A不合main、不自审代独审。
