# M3 后端只读基线审查与 V40-03/04/05 合同输入

日期：2026-11-03（Asia/Taipei）。状态：**A_READONLY_REVIEW_COMPLETE / B_NOT_AUTHORIZED**。

本报告仅对冻结 tracked 源码、资料包做静态审查；没有执行任何测试、服务、PG、API、Worker、浏览器业务流程、外部平台或模型调用。只写本报告和同目录 `M3_API_INVENTORY.json`。没有创建/切换分支、worktree，没有 commit/push/PR/CI/远端写，没有读取历史密钥、私有配置或 `.audit` runtime 原件。没有修改参考包。

## 1. 结论与来源边界

1. **已有 M3 可作为 V4 合同研究基线，不能当成现成多租户演示后端。** 已有真实 PG session、principal/shop scope、日报、持久调度/Fake、受限询单、synthetic pgvector 知识与指定审核内部 copy 草稿。V4 DemoTenant/epoch、persona、联合 seed/reset、可编辑业务 overlay 及商品/订单资源 API 尚不存在。
2. **V40-03/04 会涉及新的身份、来源和数据隔离边界。** 应新增明确的 V4 namespace/DTO/迁移，不把旧 `source_mode` 枚举全局改名，不修改历史迁移、nonce/hash、Graph checkpoint 或默认 Worker 锁来凑演示。
3. **最突出合同风险**：原 session 绝对 TTL 默认8小时（非30分钟）；同账号共享 principal 并不按 cookie 隔离对象；inquiry 固定一个内部 shop UUID/Mock baseline；Worker 数据库级单锁且默认队列全库消费；旧证据表不可 DELETE/TRUNCATE；询单 OpenAPI 缺鉴权声明。以下均区分已有实现事实与 proposed 应对。
4. **历史工程/PG结果不是本轮结果**：3684 offline/719 PG 受测 `532eefd...`；Web 受测 `3a184e9...`；当前审查 `952e6246...` 仅通过 git 对比确认后续文档差异，不改写受测 source。两次 native139 仍 UNKNOWN，外部验收未签。

所有下文仓库路径、符号和行号默认属于完整 commit **`952e6246deb01ec763f2541d9f316753987744f3`**，tree **`43e4e732824e23b991660a4f7882ba8f5a265df1`**。可用 `git show <commit>:<path>` 复核，行号为该 blob 的一基行号；不是工作树 WIP 行号。仓库只读位置 `/Users/aipuli/.codex/worktrees/commerceops-m3-control/commerceops-agent`，启动核对 HEAD 为该 SHA、status --short 无输出。ROOT 提供的实时远端快照：main `6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265`，M3 为上述 SHA，远端 Harness `684e645feb1dbe0a27864ca2308fe1afd9fa948d`。本任务未额外网络查询或 fetch；未读取本地 Harness b9ceaf3 的 WIP。

资料包路径 `/Users/aipuli/Downloads/CommerceOps_V4_Codex_Development_Package`。已读 `00_README_开始阅读.md`、全部 `02_architecture/*.md`、`05_quality/TEST_AND_ACCEPTANCE.md`、`03_delivery/TASK_CARDS.md`、`03_delivery/RISK_AND_DECISION_REGISTER.md`。它们是 planning-v1 提案，里面的 B 实施指令不构成本任务授权。M3 `AGENTS.md:1–9` 的既往托管开发/提交节奏也不覆盖当前 A 只读范围。

## 2. 主应用及 API 完整清单

主应用：`backend/src/commerceops/entrypoints/api.py:create_app:30`。默认 health 与 legacy resolver 路由始终注册；Web 仅在 web_config + replenishment_store 明确传入时安装（84–87）；daily（88–104）、inquiry（105–114）、copy（115–124）分别有显式条件。`main:152–190` 消费配置开关，不读取本次未授权 runtime 文件。`FastAPI(...docs_url=None, redoc_url=None, openapi_url=None):50`，所以没有默认公开 `/docs` 或 `/openapi.json`。

**授权不是 FastAPI Depends/角色装饰器。** 下表的 `@router.get/post` / `@app.get/post` 是路由装饰器；没有额外 `@requires_role` 或 `Depends`。真实共同门禁是 `replenishment_http.py:152 web_boundary`，具体对象还需 store 内授权；inquiry/copy 自带 actor/protect。JSON 清单逐端点保留完整 decorator、函数签名、请求/响应 schema、参数、源码及合同位置。共 **46 个 method+path：39 个 `/api/v1`，7 个 legacy/health**。这不是全部都在默认部署开启的数量。

- `WEB_MIDDLEWARE`：`/api/v1/*` 的 Origin/HTTPS → session.authenticate → 非auth路径 capability → POST Origin/CSRF（`replenishment_http.py:152–210`）。admin 路径查 admin，其余先要求 operator/approver（176–184）；对象和具体动作再查对应 role/shop。
- `BOOTSTRAP`：csrf/login 是 session.authenticate 的例外（166）；POST login 仍须 bootstrap token 的 CSRF 和允许 Origin。login 有 PG 限流/密码验证，不能拿 UI persona 替代。
- `TRUSTED_RESOLVER_DEFAULT_DENY`：`inventory_http.py:25–44` 和 `explanation_http.py:176–182`，默认 resolver=None 返回401。主 `main` 未注入该可信 resolver，不能把这些无 `/api/v1` 路径当作已公开旁路或 V4 的现成登录 API。
- 各 versioned HTTP adapter 返回 JSONResponse/Any 的地方，下面响应名来自已保存 OpenAPI；不是虚构 Python 返回注解。错误 DTO 与状态见 JSON 的完整 responses。

| 方法及完整路径（已有） | 请求 → 成功响应 | 位置/授权 |
|---|---|---|
| `GET /health/live` | 无body → Liveness | `api.py:79 liveness`；PUBLIC_LIVENESS |
| `GET /tasks/{task_id}` | 无body → TaskRead | `inventory_http.py:57 task`；TRUSTED_RESOLVER_DEFAULT_DENY |
| `GET /tasks/{task_id}/report` | 无body → ReportRead | `inventory_http.py:61 report`；TRUSTED_RESOLVER_DEFAULT_DENY |
| `GET /tasks/{task_id}/events` | 无body → EventsRead | `inventory_http.py:69 events`；TRUSTED_RESOLVER_DEFAULT_DENY |
| `GET /tasks/{task_id}/explanation` | 无body → ExplanationRead | `explanation_http.py:200 get`；TRUSTED_RESOLVER_DEFAULT_DENY |
| `POST /test/route` | RoutingInput → RoutingRead | IntentQueuedRead | `explanation_http.py:219 route`；TRUSTED_RESOLVER_DEFAULT_DENY |
| `GET /test/routes/{task_id}` | 无body → IntentRead | `explanation_http.py:229 route_result`；TRUSTED_RESOLVER_DEFAULT_DENY |
| `GET /api/v1/auth/csrf` | 无body → 200: CsrfBootstrap | `replenishment_http.py:255 csrf`；BOOTSTRAP; POST Origin/CSRF; login credential/rate limit |
| `POST /api/v1/auth/login` | LoginInput；header:X-CSRF-Token, header:Origin → 200: SessionRead | `replenishment_http.py:271 login`；BOOTSTRAP; POST Origin/CSRF; login credential/rate limit |
| `GET /api/v1/auth/session` | 无body → 200: SessionRead | `replenishment_http.py:280 session`；WEB_MIDDLEWARE |
| `POST /api/v1/auth/logout` | LogoutInput；header:X-CSRF-Token, header:Origin → 200: LogoutReceipt | `replenishment_http.py:284 logout`；WEB_MIDDLEWARE |
| `POST /api/v1/tasks/preflight` | N01PreflightInput / P5WooPreflightInput；header:X-CSRF-Token, header:Origin → 200: P5PreflightResponse | `replenishment_http.py:293 preflight`；WEB_MIDDLEWARE |
| `POST /api/v1/tasks` | CreateTaskInput；header:X-CSRF-Token, header:Origin → 202: CreateTaskReceipt | `replenishment_http.py:299 create`；WEB_MIDDLEWARE |
| `GET /api/v1/tasks` | 无body；query:limit, query:cursor, query:state, query:kind → 200: TaskList | `replenishment_http.py:314 tasks`；WEB_MIDDLEWARE |
| `GET /api/v1/tasks/{task_id}` | 无body；path:task_id → 200: TaskRead | `replenishment_http.py:330 task`；WEB_MIDDLEWARE |
| `GET /api/v1/tasks/{task_id}/report` | 无body；path:task_id, query:report_id → 200: ReportRead | `replenishment_http.py:334 report`；WEB_MIDDLEWARE |
| `GET /api/v1/tasks/{task_id}/plans/{plan_version}` | 无body；path:task_id, path:plan_version → 200: PlanRead | `replenishment_http.py:343 plan`；WEB_MIDDLEWARE |
| `GET /api/v1/approvals/{approval_id}` | 无body；path:approval_id → 200: ApprovalRead | `replenishment_http.py:351 approval`；WEB_MIDDLEWARE |
| `POST /api/v1/approvals/{approval_id}/decision` | DecisionInput；path:approval_id, header:X-CSRF-Token, header:Origin → 200: DecisionReceipt | `replenishment_http.py:355 decide`；WEB_MIDDLEWARE |
| `GET /api/v1/requests/{request_key}` | 无body；path:request_key, query:operation → 200: RequestRead | `replenishment_http.py:365 receipt`；WEB_MIDDLEWARE |
| `GET /api/v1/replenishment-items` | 无body；query:limit, query:cursor, query:state → 200: ItemList | `replenishment_http.py:378 item_list`；WEB_MIDDLEWARE |
| `GET /api/v1/tasks/{task_id}/execution` | 无body；path:task_id → 200: ExecutionRead | `replenishment_http.py:389 execution_read`；WEB_MIDDLEWARE |
| `GET /api/v1/replenishment-items/{item_id}` | 无body；path:item_id → 200: ItemRead | `replenishment_http.py:393 item_read`；WEB_MIDDLEWARE |
| `POST /api/v1/replenishment-items/{item_id}/resolve` | ResolveInput；path:item_id, header:X-CSRF-Token, header:Origin → 200: ResolveReceipt | `replenishment_http.py:397 item_resolve`；WEB_MIDDLEWARE |
| `GET /api/v1/config` | 无body；query:shop_id → 200: ConfigRead | `replenishment_http.py:404 configuration`；WEB_MIDDLEWARE |
| `GET /api/v1/admin/operations` | 无body → 200: OperationsRead | `replenishment_http.py:411 operations`；WEB_MIDDLEWARE |
| `GET /api/v1/tasks/{task_id}/plans` | 无body；path:task_id, query:limit, query:cursor → 200: PlanList | `replenishment_http.py:415 versions`；WEB_MIDDLEWARE |
| `GET /api/v1/tasks/{task_id}/events` | 无body；path:task_id, query:limit, query:cursor → 200: EventsRead | `replenishment_http.py:426 events`；WEB_MIDDLEWARE |
| `GET /api/v1/approvals` | 无body；query:limit, query:cursor, query:state, query:view → 200: ApprovalList | `replenishment_http.py:437 approvals`；WEB_MIDDLEWARE |
| `GET /api/v1/tasks/{task_id}/explanation` | 无body；path:task_id, query:report_id → 200: ExplanationRead | `replenishment_http.py:449 explanation`；WEB_MIDDLEWARE |
| `GET /api/v1/daily-reports/{task_id}` | 无body；path:task_id → 200: DailyRead | `daily_http.py:46 daily_report`；WEB_MIDDLEWARE + DailyReadStore/DailyOperations owner+operator |
| `GET /api/v1/daily-capabilities` | 无body；query:shop_id → 200: CapabilityRead | `daily_http.py:70 capabilities`；WEB_MIDDLEWARE + DailyReadStore/DailyOperations owner+operator |
| `GET /api/v1/daily-reports/requests/{request_key}` | 无body；path:request_key, query:shop_id → 200: CreationReceiptRead | `daily_http.py:74 report_receipt`；WEB_MIDDLEWARE + DailyReadStore/DailyOperations owner+operator |
| `GET /api/v1/daily-reports/{task_id}/questions/requests/{request_key}` | 无body；path:task_id, path:request_key, query:shop_id, query:report_id → 200: CreationReceiptRead | `daily_http.py:80 question_receipt`；WEB_MIDDLEWARE + DailyReadStore/DailyOperations owner+operator |
| `POST /api/v1/daily-reports` | CreateDailyInput → 202: AcceptanceRead | `daily_http.py:92 create_report`；WEB_MIDDLEWARE + DailyReadStore/DailyOperations owner+operator |
| `POST /api/v1/daily-reports/{task_id}/questions` | QuestionInput；path:task_id → 202: AcceptanceRead | `daily_http.py:99 create_question`；WEB_MIDDLEWARE + DailyReadStore/DailyOperations owner+operator |
| `GET /api/v1/daily-reports/{task_id}/questions/{question_id}` | 无body；path:task_id, path:question_id, query:cursor → 200: QuestionRead | `daily_http.py:108 question`；WEB_MIDDLEWARE + DailyReadStore/DailyOperations owner+operator |
| `GET /api/v1/daily-reports/{task_id}/evidence` | 无body；path:task_id, query:report_id, query:cursor → 200: EvidenceRead | `daily_http.py:116 evidence`；WEB_MIDDLEWARE + DailyReadStore/DailyOperations owner+operator |
| `POST /api/v1/readonly-inquiries` | CreateInquiry → 202: InquiryReceipt | `inquiry_http.py:81 create`；WEB_MIDDLEWARE + inquiry_http.actor + authorize_entry/operator |
| `GET /api/v1/readonly-inquiries/requests/{request_key}` | 无body；path:request_key → 200: InquiryRead | `inquiry_http.py:123 receipt`；WEB_MIDDLEWARE + inquiry_http.actor + authorize_entry/operator |
| `GET /api/v1/readonly-inquiries/{task_id}` | 无body；path:task_id → 200: InquiryRead | `inquiry_http.py:127 task`；WEB_MIDDLEWARE + inquiry_http.actor + authorize_entry/operator |
| `POST /api/v1/copy/candidates` | CreateCopy；header:Origin, header:X-CSRF-Token → 202: CandidateResponse / UnknownCandidateResponse | `knowledge_copy_http.py:151 create`；WEB_MIDDLEWARE + knowledge_copy_http.protect + store object authorization |
| `GET /api/v1/copy/candidate-requests/{key}` | 无body；path:key → 200: CandidateResponse; 202: UnknownCandidateResponse | `knowledge_copy_http.py:177 candidate_request`；WEB_MIDDLEWARE + knowledge_copy_http.protect + store object authorization |
| `GET /api/v1/copy/candidates/{identifier}` | 无body；path:identifier → 200: CandidateResponse | `knowledge_copy_http.py:187 read`；WEB_MIDDLEWARE + knowledge_copy_http.protect + store object authorization |
| `POST /api/v1/copy/candidates/{identifier}/review` | ReviewCopy；path:identifier, header:Origin, header:X-CSRF-Token → 200: DecisionResponse; 202: UnknownDecisionResponse | `knowledge_copy_http.py:206 review`；WEB_MIDDLEWARE + knowledge_copy_http.protect + store object authorization |
| `GET /api/v1/copy/candidates/{identifier}/review-receipts/{key}` | 无body；path:identifier, path:key, query:candidate_hash → 200: DecisionResponse; 202: UnknownDecisionResponse | `knowledge_copy_http.py:236 receipt`；WEB_MIDDLEWARE + knowledge_copy_http.protect + store object authorization |

合同文件：`backend/src/commerceops/assets/{p3-web-v1,p4-n01-web-v1,p5-m2-v1,p6-daily-read-v1,p6-inquiry-web-v1,p6-copy-web-v1}.openapi.json`。旧 P3/N01/P5 的 paths/components 在 `entrypoints/web_openapi.py:9–32 export_web` 按 P3→N01→P5 合并，因此 **P5 覆盖 CreateNewCycle 的 parameters，实际支持 MockParameters 或 P5WooCreateParameters**；不能只读旧 p3 文件就断言 runtime 不支持 Woo。M3 三套合同独立导出，`api.py:125–148` 不把它们混入旧公开合同。legacy DTO 来源为 `application/commerce/read_models.py`、`explanation_read.py`、`inventory_routing.py`，详见 JSON 符号表。

### 合同差异，不能直接复用规划名

- **OpenAPI 漏鉴权元数据**（已有差异，未修改）：`inquiry_http.py:133–200 inquiry_openapi` 没有 securitySchemes/security，三个已提交 inquiry asset 操作也缺 security/Origin/CSRF 参数。但运行时 `actor:65–78` 和主 middleware 强制鉴权。这是文档/客户端生成风险，**不是证明匿名可访问**。V4 新合同须明确鉴权并对真实路由做负例；若修 M3 合同需单独有界切片，不能借机改其权限语义。
- daily POST 的 OpenAPI 没有显示 Origin/CSRF header 参数（`daily_http.py:155–178` 只设 SessionCookie、请求和错误），真实 middleware 仍检查。V4 合同应完整描述 cookie/Origin/CSRF，客户端不得从缺参数推断免验。
- 当前没有 `GET /api/v1/products`、`/orders`、`/inventory` 资源中心，也没有 `/api/v4/*`、demo session/reset/persona API。已有 Product/OrderLine/Inventory 是 adapter/冻结快照 DTO，受限 Tool 是程序端口，不能宣称它们是公开 CRUD API。
- 当前 inquiry `context_report_id` 绑定 `business.analysis_reports`（`readonly_inquiry_store.py:70–80`），不是任意 daily report。日报追问是另一组固定模板和自己的报告引用（`daily/questions.py:52–59`、`daily_http.py:98–119`）。V4 全局助手不能把两种 report UUID 互传。
- 当前知识检索/owner登记不是用户上传API；copy 只有候选/指定审核/原键回读。没有营销发布、客服发送、采购、到货接口。

## 3. 现有 DTO、领域和 source 不变量

| 已有符号和位置 | 当前准确含义 | V4 合同必须处理的差异（proposed） |
|---|---|---|
| `application/replenishment/contracts.py:132 WebActor` | session_id/principal_id/identity_id/organization_id/auth_version；服务端解析，无tenant/epoch | V4可信上下文新增 demo tenant/session epoch/persona binding，不能让客户端填这些权限事实；不要直接加可选字段后让旧调用静默绕过 |
| 同文件 `Parameters:28`、`WooCreateParameters:41`、`CreateNewCycle:75` | mock+inventory-v1+fixture_case 或 woocommerce_test+config version；L/R/S；Woo bind 从已登记来源补org/shop/binding | 保留旧联合类型；V4 demo写域与真实只读外部源由服务端操作路由选择，不能靠body自称demo就获写权 |
| `application/commerce/contracts.py:44 Provenance/:58 Source/:79 Product/:97 OrderLine/:126 Refund/:147 Inventory` | 来源mock/woocommerce_test；Source.shop_id是外部 Identifier字符串；Money是Decimal序列化字符串；未知库存/在途可null，allocation unresolved | 定义内部shop UUID↔外部key映射、canonical SKU/variant/pool身份；不能把外部key当内部UUID、同SKU跨shop合并、未知当0 |
| 同文件 `Capabilities:286` | read_only=true，observational，refund_scope=order_cohort | V4不得把受测只读Woo适配器变成商品/库存/订单写API；日报退款口径也不能从inventory的cohort推断 |
| `application/commerce/source_binding.py:26 WooSourceMetadata/:90 RegisteredWooSource` | 元数据org/shop/config_ref/version/digest/origin/external key/currency/timezone；注册binding可信 | 新SourceRef至少含domain/binding/fixture version/snapshot+overlay epoch，公开DTO不带key/secret/CA/pin文件路径 |
| `application/daily/contracts.py:80 DailySource`、`source.py:126 MockMetadata/:139 WooMetadata` | 带UUID组织/店铺/binding/config digest/时区币种；覆盖证明依赖manifest；不是泛化任意实店日报 | 两个数据域可引用同baseline，但overlay合并快照要新hash/版本及完整性；不得把覆盖后的数据伪装成Woo原始快照 |
| `daily/contracts.py:306 DailyMetrics/:431 DailyReport` | 创建/支付/退款发生时间分别统计；金额Decimal；精确平均值分子分母；incomplete metrics=null/display空 | V4经营看板以相同时间/币种/来源/口径和金标复算；缺成本不造利润；没有退款记录不推断实际付款退款成功 |
| `daily/read_models.py:100 PublicSource` | coverage_scope=controlled_test_dataset | 新公开DTO展示来源层级，不移除controlled标识去暗示真实商店 |
| `commerce/readonly_inquiry_service_contracts.py:23 CreateInquiry/:142 InquiryReceipt/:158 InquiryRead` | shop UUID、question、可选库存report、key；receipt source_mode=mock、evidence_mode=offline_stub | V4多店/持久会话不是现成能力；新增Conversation/Run合同，保留旧inquiry字面和上限 |
| `commerce/readonly_inquiry_contracts.py:47–71 ToolCall` | 精确工具名commerce.read_products/read_orders/read_inventory、reports.read | 包里read_products等是规划别名，需显式映射，不能重复注册/让模型改名获权 |
| `knowledge_copy/commands.py:12 CreateCopy/:23 ReviewCopy/:38 CopyReceipt` | 创建选shop、registry+digest、product_source、query_ref、reviewer、key；review绑定v1+candidate hash；saved/rejected/UNKNOWN且publication_allowed=false | reviewer_id是请求选择对象，服务端仍核当前指定审核资格；不能升级成客户端批准事实，也不能把内部草稿等同活动已发布 |

**source字段不是一个全局开关。** `web_sessions.py:129–156 deployment` 默认旧config `source_mode=mock`；`replenishment_read.py:755–803 config_read` 对已登记Woo改为woocommerce_test；daily使用source_kind+完整binding；knowledge `source_kind=synthetic`、chunk/product citation kind又是sop/product；P4 `source_mode=feishu` 是消息通道（`replenishment_read.py:59–69`），与商务adapter模式不同。V4 domain+source合同应分别命名：业务域/数据来源/模型模式/投递模式/embedding模式，不把这些字段拼成一个布尔“真实”。

## 4. 0019–0023 schema / ACL 实查

准确线性链：`0018_p5_commerce_sources → 0019_p6_daily_reports → 0020_p6_knowledge_copy → 0021 → 0022 → 0023_p6_copy_drafts`。对应每个 migration 文件的 `revision/down_revision:5–6`；0021/0022 的实际 revision 不是文件全名。新增migration应指向真实head `0023_p6_copy_drafts`，下一编号由唯一owner分配，不能从资料包简写拼错parent。

| 迁移路径（backend/migrations/versions/） | 新表与关键不变量 | 授权/隔离含义 |
|---|---|---|
| `0019_p6_daily_reports.py:22–107` | p6_daily_source_bindings/snapshots/reports；org+shop+task复合FK，binding/version唯一，canonical JSON/hash，业务日时区窗口，complete必须覆盖与receipt集合一致 | source_valid:117锁定shop来源，current_permission:140锁principal+scope+grant；task_guard:155禁止kind/请求变更；snapshot/report guard:206/234；不可变及no_truncate:333–347；request unique:348 |
| `0020_p6_knowledge_copy.py:11–94` | knowledge_ext vector 0.8.7；p6_knowledge_documents/authorizations/chunks/embeddings/registries；synthetic限定，文档hash/许可payload、版本/有效期、chunk evidence hash、embedding f32/profile/dimension/digest | 无全域任意upload；status_guard:160只许owner授权approved/revoked与registry enabled；p6_lock_knowledge:179核operator+registry并锁授权；PUBLIC revoke:198–210；immutable/no_truncate:216–227 |
| `0021_p6_readonly_inquiries.py:13–50` | readonly_inquiries；principal/key唯一，session FK及org/principal/identity/task FK；source_binding hash、source_domain、offline_stub、精确workflow；严格JSON result≤1MiB | guard:51禁止delete/truncate和终态改写；版本+1/精确状态转换；当前session/scope验证，窄safe failure例外只允许已有running job写安全失败；task_guard:102持久result才可完成；窄grant:129–134；大型JSON validator:142起 |
| `0022_p6_daily_operations.py:11–118` | p6_daily_destinations/schedules/schedule_runs/questions/deliveries/fake_receipts；schedule/version唯一+一个active；schedule/due_at唯一；report/destination和provider_key唯一；delivery attempts≤1 | destination仅fake；source/owner/current permission验证:122–163；delivery guard:298要求blocked outbox、sender_enabled=false、完整报告及原payload/hash；状态pending→sending→sent/unknown，不能重发unknown；immutable/no_truncate:338–371 |
| `0023_p6_copy_drafts.py:11–103` | p6_copy_products/candidates/decisions/drafts；产品synthetic；候选registry/product绑定、owner/key唯一、≤15min；指定reviewer；candidate一decision/一draft；draft复合FK绑定approve | p6_lock_copy:154核当前reviewer+原owner权限并锁全部来源；commit_guard:236–253延迟检查session/时效与approve恰1draft/reject0；PUBLIC revoke:286–294；immutable/no_truncate:298–325；审计trigger:328–333 |

合计 **19张M3新业务表**（3+5+1+6+4），不是19个接口。`knowledge_ext`是扩展schema，不是tenant schema。上述五迁移没有启用 RLS；真实边界是应用过滤、权限锁、复合FK和触发器。**不能宣传数据库已提供通用行级租户隔离**。V4选择新增tenant列/复合FK还是独立映射/受保护source resolver，要在合同明确，并用真实PG跨tenant负例证明；本报告不修改旧表。

runtime授权入口 `backend/src/commerceops/entrypoints/database.py:38 grant_runtime`：

- readonly inquiry SELECT/INSERT + 仅state/result/canonical/hash/version/updated_at UPDATE（75–86）。
- daily binding只SELECT；snapshot/report SELECT/INSERT（87–112）。schedule/destination只SELECT，run/question/delivery/fake_receipt SELECT/INSERT；schedule仅enabled/pause/last_created_day/updated_at、delivery仅status/attempts/external_id/failure/claimed_by/updated_at UPDATE（114–139）。这不是任意规则管理API。
- 原 `commerce_snapshots/snapshot_products/snapshot_order_lines/snapshot_refunds/analysis_reports` SELECT/INSERT且禁止UPDATE/DELETE/TRUNCATE（165–170）；audit append-only（171–174）；checkpoints拥有专用CRUD（175–178）。不要把checkpoint CRUD用于demo reset。
- 知识/copy **另有明确owner bootstrap** `grant_knowledge_copy_runtime:250–264`；`knowledge_copy_repository.py:40–76` 核实际表owner、仅knowledge SELECT+窄vector函数；`knowledge_copy_draft_store.py:67–82` copy product只SELECT，其余SELECT/INSERT，无UPDATE/DELETE/TRUNCATE。普通grant-runtime不自动开放copy。
- 原 runtime 对 organizations/shops/principals/identities 等基础表有既往SELECT/INSERT/UPDATE（database.py:69–73），**不是**全库read-only账户；因此V4公开session创建与seed若共用该角色，要做真实授权/约束和入口隔离，不能只以“低权app”三个字代签。

## 5. Session、principal、shop scope 与权限风险

已有机制：

- `web_sessions.py:173–219 _session`：43字符opaque token → PG token hash；每请求重核当前principal、web identity、enabled credential、auth_version；锁session、DB时钟判断absolute/idle/revoked、CSRF key version，idle最多延到absolute。`_create:243–280` token随机、仅hash存PG；`login:330–360` 轮换session并撤销bootstrap；`_record_attempt:300–328` PG account/peer限流。
- `replenishment_http.py:238–267` cookie HttpOnly、SameSite=lax、Secure按transport=https；local_http仅本地模式不能当公网Secure证据。`web_config.py:44–60` 默认absolute=28800s、idle=1800s，bootstrap=300s（web_sessions:246–252）；idle30min不等于演示绝对30min。
- `web_sessions.py:59 actor_guard` 对principal当前auth版本+有效session核验；`role_scope:113–126`调用DB permission lock。`replenishment_repository.py:71 has_capability` 是“有某店该角色”的入口能力，不是任意shop权限；`:85 visible_task` 仅本人operator或当前approval eligible approver，错误404。
- `0005_p3_approval.py:153–194` 的scope/role/credential变更锁principal并增加auth_version，锁权限函数核role、scope、identity。该函数在 `0008_p4_feishu.py:12–32` 被 CREATE OR REPLACE，为当前迁移链最终定义：核principal enabled/auth_version/角色、同org+shop的enabled scope/grant，并要求当前web identity+enabled credential，或当前Feishu identity与organization app/tenant匹配；没有让admin默认拥有业务权限。
- 日报 `daily_read.py:29–40` 与创建回执 `daily_operations.py:42–57` 核requester+operator当前scope；inquiry `readonly_inquiry_store.py:241–283`按org/principal定位并再核shop/report；copy `knowledge_copy_draft_store.py:530–587`仅owner或未审前指定reviewer，且read会核来源，已审核reviewer不能继续用旧read路径看候选。

**proposed 合同必须冻结：**

1. 每访客DemoTenant的真实session/principal关系。不能让全部浏览器使用同一预置M3账号并声称session隔离：M3回执按principal/key、任务按requester，不按cookie分租户。也不能仅加tenant_id客户端query。
2. persona选择只能命中服务端tenant内的allowlist身份；可用专属demo principals/identities或受限persona授权映射，但要解释如何满足旧web credential/identity验证。不要在旧session行直接改role/principal复用token；切换应轮换token/CSRF、绑定新persona，旧cookie失效，清浏览器和服务端缓存。
3. 定义 `demo_tenant_id + reset_epoch + persona/principal + organization_id + shop_id + source_ref` 的不可伪造关系。新对象、幂等回执、游标、异步job/Tool结果、Agent上下文、缓存键和导出都要带完整域。每个请求读取当前绑定，提交/展示前再核epoch和权限。
4. 明确reset与角色切换/退出的差异、原key保留期、UNKNOWN查询语义。reset不能将旧UNKNOWN误当未提交并自动新POST；旧epoch回执可返回安全tombstone/失效状态，不返回原敏感payload，也不再触发执行。
5. TTL从DB时钟定义绝对30min；是否滑动以及重置后是否新session由产品裁决，默认不延长原绝对期限。并发/创建限流是独立于旧密码登录限流的新要求。

## 6. Graph、Worker、审批、Tool 不可被 V4 隐式扩大

- `entrypoints/worker.py:103–159 serve`：一个WorkerSession，一个 InventoryCompositeRunner，日报/询单作为已注册runner串行接入；copy为同步PG模板路径，不注册第二Worker。`:183–209` 在原maintenance和单Worker loop调度；`infrastructure/worker.py:83–110` 只有无在途Graph时维护、一次一个runner。
- **数据库级固定锁** `infrastructure/worker_lock.py:15 LOCK_KEY=7412438461303`，`:163–215 start`固定pg_try_advisory_lock、旧进程/孤立running的termination门禁。organization参数用于登记，不是锁key的一部分。`queue.py:47–85 claim` 默认task_ids=None时不按organization限制，具体RunRequest带行本身org/shop。**因此不能假设每访客新org就能启动各自Worker，也不能默认旧runner已支持动态任意tenant。** V40应先确定一个受控单Worker部署及租户resolver方案，适配前做全链PG负例，不改锁扩大并发。
- `workflows/replenishment.py:100–240`：prepare→wait（唯一interrupt）→revalidate→execute→finish；`:153–170` 明确Command/callback值不是批准，读取PG持久决定；`:518–539` workflow/task/org/shop/thread_id/request hash绑定、PG checkpointer；不可用V4 agent plan或对话记忆替代。
- `infrastructure/approval_decisions.py:59–94`核pending/current plan/TTL/eligible approver/disclosure/hard blocks/nonce；`:136–219` 原key事务锁、payload冲突、nonce、plan id/version/hash、当前权限、DB时钟与过期410。采购若新领域，应定义自己的审批对象/状态合同；不能复用旧approval_id让原库存execution误跑。
- `application/commerce/readonly_inquiry_executor.py:69–110` 固定60s、100 SKU、窗口并集≤30天；`:132–177`最多3次model、4次Tool、第三次不能再发Tool；`:181–240`整批先验白名单effect=read、10,000行上限、source/shop/call id与facts/refs一致、调用前后和最终展示前重鉴权。是已实现的受限单用例，不是V4任意多步Agent。
- `infrastructure/readonly_inquiry_config.py:13–24`明确mock/baseline/offline_stub/actual provider=false/external=false；`readonly_inquiry_store.py:65–99`绑定**一个**配置shop UUID+来源；`readonly_inquiry_runtime.py:78–89`用MockReadFacade。给V4两店可变source重用需要新适配，不是打开现有开关即可。
- 知识DB限定synthetic；向量排名/引用验证是实际PG，不能称真实embedding质量已验。copy internal draft publication=false无发布outbox；daily delivery transport=fake，unknown/attempt1不得自动重发。

## 7. 原始验收来源、失败和外部未验边界

本次找到的**tracked权威结论/原件索引**是 `docs/M3_LOCAL_ACCEPTANCE.md`（当前精确M3 commit中的1–80行）与 `docs/M3_LOCAL_DELIVERY.md`。原始运行日志主要在各独立工作树`.audit`，不是tracked源码；按当前授权没有打开这些私有runtime原件，故这里为“已提交回执转述+源码索引”，**不声称本轮独立重算或重验原始日志**。

| 历史证据（不是本轮执行） | 精确受测source | tracked位置及保留事实 |
|---|---|---|
| 完整工程scripts.check | `532eefd83e4b1d0e6ddc6e44e89c0d806021eb1e` | Acceptance:21：native0，3684 offlinepass/719排除/4warning/539.16s；type496/format640/MD140/strict46，无skip/retry；dir/index0，git20旧approved/0blocking但nativegit1保留 |
| K2 owner fixture修复后30 | 同532 | Acceptance:22、36、51：30/30/51.49s；旧完整542中owner test SQLSTATE0A000失败及原全文未捕获保留；CASCADE fixture修正不改变不可变保护 |
| 最终完整PG | 同532 | Acceptance:23、64–73：existing542+phase3177=719 actualpass、交集0/无缺项、G1三/G2六/严格工具锁源配对/cleanup0；先existing结束09:29:47.495685Z，再phase3结束09:59:19.433781Z；本机40min诊断/42min外层容量例外，Hosted35/33未验 |
| 实际M3 API/Worker/Web | `3a184e9a74c1db524d58228ed90b7ea20388a722` | Acceptance:24、30：3pass/47.1s，7POST各一次，harness实际丢7次HTTP响应后原key GET；同org两个shop、指定审核approve/reject、跨身份404、至少51引用分页/390px；Worker0/API-15/Web143是owned TERM，不能改全0 |
| 原离线Web | 同3a18 | Acceptance:25、32：六配置90+13+8+22+9+3=145pass；skip/retry0；Next个体exit UNKNOWN |
| 原实际API Web | 同3a18 | Acceptance:26、55：read7/write10/items7，父与supervisor0；14产物hash；新容器/网络0，各保留1卷 |
| 原N01 | 同3a18 | Acceptance:27、56：6pass/49.366s/helper/PW/supervisor0；cleanup0/保卷；browser个体exit NOT_CAPTURED |
| 独审/文档核收 | `22b924f0549c2740f1330ce755454934d3d92954` | Acceptance:28、78–80：ACCEPT_M3_LOCAL_DELIVERY_DOCS_22b924f，无剩余P1/P2；不替代外部验收 |

原件安全索引（只转录tracked路径，不读内容）：Acceptance:48–58 的control `m3-post-fixture-fullcheck.log`、`functional-equivalence.safe.json`；final-sql-probe `issue23/round-1.json`；final-existing-serial/final-phase3-serial `issue23-ci/round-1.json`与ci-evidence；validation-complete `m3web-3da9458c2dd4/root-ledger.json`和operations ledger；offline-web `final-3a18/run.json`；final-web-live `original-web-delivery.safe.json`；final-n01证据目录。它们未因本报告变成已提交/可公开原件。

**失败保留**：Acceptance:36记录3a18首scripts.check exit1/后段NOT_RUN、首修6pass1fail、旧52525 existing245pass1fail/295NOT_RUN、3a18 existing387actual=386pass1fail/155NOT_RUN、3a18 phase3 169/177与8NOT_RUN及native139。Acceptance:62另记532并行existing535/542+7NOT_RUN（command137/总deadline）、phase3 169/177+8NOT_RUN/第二次139。均外层1，不能拼成719。CPython158200仅外部线索；官方最小程序当前3次native0/OOMfalse不能定位本项目根因。Acceptance:40、64明确最终串行通过不等于139已修复，复现先取native栈，不能无限重跑。

`git diff --name-status 532eefd..952e6246` 本次静态输出仅 AGENTS.md、README.md、M3_LOCAL_ACCEPTANCE、M3_LOCAL_DELIVERY、ROADMAP、STATUS、M3_MANAGED_DEVELOPMENT 七文档；不含backend/frontend/test/compose/PG pipeline。该证据说明审查HEAD在这些执行文件上未偏离532，不将历史测试source签为952。

**未验/未交付**：Acceptance:3、38、46、75：真实SOP/商品许可与质量、真实provider/model/embedding、真实飞书接收/外发、人工业务质量、amd64/Hosted、生产/公网部署/main均未由M3本地验收签收；M2备份工具仅支持0018并拒绝0023，M3备份扩展未实现。即使ROOT后来更新远端分支，也不能推导main/Hosted/部署已验。

## 8. V40-03/04/05 最小改动映射（全部 proposed，待B明确授权）

主控本次明确的 V4-0 收敛边界：**不创建每tenant Worker，不接新Graph任务，不新增Agent或调度执行链。六条业务链在V4-0仅为fixture ref/种子场景与后续验收规划，不是六链功能完成或运行证据。** 下列迟到job/Tool/Graph情形是现有安全不变量和后续阶段的隔离验收输入；V4-0本身不因此获得提交新Graph任务的授权。

| 卡 | 可复用已有内容 | 最小新增/适配合同 | 不应顺带修改 | 后续必须真实验证 |
|---|---|---|---|---|
| V40-03 短期演示身份/租户 | SessionStore的opaque token/hash/PG时钟/Origin/CSRF/撤权、principal及role_shop_grants模型；当前M3业务API仅在绑定成立时消费 | 新demo session/tenant/persona/epoch可信关系、30min绝对TTL、创建并发限流、session轮换/退出/安全bootstrap、公开当前会话DTO；独立V4 prefix middleware，不能只注册路由就继承仅/api/v1的旧middleware | 原cookie真实账号行为、旧web credential验证、scope/nonce/hash、Graph/worker锁；未经审查不能全局缩短旧会话TTL | 两cookie/多persona/跨shop/admin无业务grant、到期/退出/CSRF/Origin/撤权/并发创建、业务事务提交前epoch变化、迟到响应零泄露 |
| V40-04 联合seed/六场景/reset | 旧commerce/daily金额时区SKU约束、synthetic知识模式、fixed fixture；三个m3 demo入口仅作守卫/来源参考 | 新版本化seed manifest、两店统一商品/订单/退款/客户/供应商等基线；tenant overlay+immutable events/receipt；source resolver；reset_epoch事务与幂等回执；导出失败恢复策略 | 不把旧测试prepare当正式联合seed；不改旧受保护表为可DELETE；不对旧PG/真实Woo写；不把demo override塞入旧Woo snapshot hash | 重复seed无增量/同版本digest稳定、两tenant互不影响、同key异文409/丢ACK原key查、reset与并发写/旧job竞态、source混淆拒绝/真实适配器零写 |
| V40-05 首次体验/权限/reset E2E | 已有API客户端UNKNOWN恢复、安全错误态、严格DTO、390px经验与原M3 smoke清单 | 消费明确V4session和source DTO；一键体验/角色体验/reset/退出/到期引导；服务端角色/当前epoch决定菜单/读写；清query/tab缓存；测试网络须真实API/PG | 不复制prototype demo1234/localStorage权限；不伪造Tool Trace；不在浏览器浮点重算权威hash/钱；不把菜单隐藏当权限 | 1440/390、至少两个独立browser context、跨tenant猜ID404/只读scope、角色降级清屏、reset后刷新及旧异步结果、原M3 smoke不变 |

需唯一SCHEMA/API owner串行管理迁移/授权/根API/shared DTO与seed transaction；WEB/QA只消费冻结合同，不能自定义role/tenant/source真假。拟触及文件为新的V4 application/infrastructure/entrypoints模块和新的migration；`api.py`仅做显式装配，原store修改若确需tenant桥接必须先专项审查。当前没有创建任何这些实现文件。

**联合seed现状证据**：`scripts/m3_daily_demo.py:13–59`只接受新空m3_daily_demo库；`scripts/m3_inquiry_demo.py:20–45/87`只接受独立m3_inquiry_demo库；`scripts/m3_copy_demo.py:127–155/212–230`是受限附加synthetic登记，使用原账号scope/双角色。`docs/M3_LOCAL_DELIVERY.md:155–167`明确联合双店private assembler仅验证、无公开一键seed。copy exporter先owner COMMIT后逐文件fsync（m3_copy_demo:60–70/223–230），不具备三文件原子发布；V4不能默默用文件存在当seed整体成功。

### domain+source 合同应冻结的最小内容

- 区分 `organization_id`（业务组织）、`demo_tenant_id`（访客隔离空间）、内部 `shop_id UUID`、`external_shop_key`、原source binding。明确映射唯一约束以及session创建/切换不可由body伪造。
- `SourceRef={domain, adapter_kind, environment, binding_id/config_version, baseline_fixture_version/hash, snapshot_id/hash, demo_tenant_id, reset_epoch, overlay_version, timezone,currency}` 是建议形状，字段可裁剪但不得丢掉来源和隔离。不得把demo_overlay标为woocommerce_test确认事实；domain不是现有source_mode的别名。
- 新实体ID来自服务端，跨shop SKU/订单/客户/报价不能只凭外部字符串联表；库存池、variant、报价版本与币种时区要冻结。钱用Decimal字符串，数量严格整数，unknown单独null/reason。
- 新写入只允许demo域，PG事务在tenant+epoch内同时写对象、事件、审计、原key回执；key要含租户/动作/actor/epoch语义，不抹除旧receipt以复用key。source/schema/expected_version/hash变更返回冲突，不能悄悄降级为新任务。
- 新快照明确baseline+overlay observation版本；读期间reset/源变化要返回失效而非混合事实；导入/Agent后续只能消费这种可信快照。知识文档的synthetic许可、profile、有效版本和引用不因demo被省略。
- 每run四维模式：data_mode/model_mode/delivery_mode/embedding_mode；兼容M3原字段时做明确映射并保留原义，不能用真实PG掩盖离线模型/Fake外发。

### permission+demo 合同应冻结的最小内容

| 动作 | 建议授权语义 | 最关键负例 |
|---|---|---|
| 进入demo | 公共受限bootstrap、限流，服务端生成tenant/epoch/persona，随机cookie | body带role/admin/tenant/approved/auth_version拒绝；超限不挤掉他人 |
| 查看商品/订单/日报/Tools | 当前demo session+tenant+shop read grant+同source | admin无shop业务grant403；其他tenant object/key/cursor404；相同外部sku不串店 |
| 生成内部草稿 | operator对应shop+demo write域；请求key/hash/版本 | approver/admin不因角色名获写；payload标Woo或篡改tenant拒绝零业务增量 |
| 审核草稿 | 指定/eligible approver+当前shop+有效版本/来源，独立明确动作 | operator自升role、模型说“已批准”、过期/撤权/报价改版均拒绝；approve一次，reject零draft |
| persona切换 | 仅当前tenant allowlist，rotate cookie/CSRF，新的current principal | 旧cookie/CSRF/异步结果失效；真实企业账号不可进入demo角色切换 |
| reset/logout | session owner绑定；当前epoch事务原子递增/撤销；旧key安全回读 | reset其他tenant/旧epoch写/迟到Tool结果不可提交或披露；同key重复只一个reset |
| 调度/通知 | 明确启用、tenant/epoch/owner/source current，Fake receiver | 同rule/version/due_at仅一run；reset后旧due/未知sent不得新key重发；真实channel调用0 |

### 后续验收例子（计划，NOT_RUN）

1. **两个访客同persona**：A/B各独立cookie，A建草稿并reset；B基线/覆盖/receipt与报告hash不变。B持A资源ID/request_key/cursor均无payload；A旧epoch job提交计数=0。
2. **角色变化竞态**：operator开始Tool读取或草稿事务，中途scope撤销/切persona，返回前/提交前检查拒绝；旧CSRF失败；admin只有管理grant不能看订单，不触发额外模型/Tool。
3. **reset丢ACK**：同request_key POST reset提交后丢响应；GET原key返回唯一reset receipt/current epoch；不重POST、不换key。相同key异文409；原DB不可读UNKNOWN。
4. **来源隔离**：演示overlay改库存只改变当前tenant有效读视图，原Woo读取fixture/hash/原snapshot未变、Woo HTTP写次数0；使用原Woo binding携带demo action也拒绝。
5. **联合数据一致**：同店经营日报/订单/退款/库存按固定fixture version和明确snapshot读取；跨日退款不计入错误cohort，缺成本无利润，缺在途null；两店相同sku_label不能合库存池。
6. **审批与异步**：candidate引用资料到期/撤权或报价变版后approve拒绝；10次同key/相同hash仅一个receipt；reset发生在Tool/计划/审批之间旧批准不能搬到新epoch。
7. **并发能力**：先2–5 session目标只是计划，真实容量测量后定上限；单数据库Worker锁不变、不启第二Worker。慢任务/取消/termination不确认仍HOLD，不从139历史后续通过推出并发安全。
8. **迁移低权**：新库从真实0023head线性升级；历史表/触发器/ACL/checkpoint/已验字节保持；runtime不能owner seed、不能改source注册和旧audit，reset只影响指定新demo域。覆盖完整动态PG/G1/G2及受影响Web，719不是永久常数。

## 9. 待 ROOT 冻结的决定与可执行计划边界

| ID | 需先决定的合同问题 | 本报告建议 | 依赖/不确定性 |
|---|---|---|---|
| D1 | tenant与org/shop/principal如何映射 | 新demo隔离域+服务端绑定，每tenant/persona独立可信身份；旧M3 mutating接口不默认向新tenant开放 | 不能用共享principal隔离；新org也不能自动让单shop询单/全库Worker适配 |
| D2 | session实现复用方式 | 保留旧Web语义，新增明确demo session策略/可信适配；30min绝对TTL、新cookie命名/CSRF旋转合同 | 若桥接旧SessionStore，需满足web credential/identity检查；若独立则所有V4路径需完整middleware和store权限 |
| D3 | reset清理与receipt保留 | epoch失效+新overlay清理/归档；保留旧immutable审计及防重复回执 | receipt/tombstone TTL、原keyGET状态需产品合同，不能选择性丢旧unknown |
| D4 | M3与V4 source桥接 | 单一SourceResolver输出独立模式+snapshot；先复用只读计算/DTO，不更改Woo写能力 | inquiry只一个shop/fixed baseline、daily manifest完整覆盖、copy registry/profile均需显式适配 |
| D5 | schema/ACL/Worker范围 | 单owner新migration+窄授权；单Worker/原锁/原checkpoint不变 | 若任何旧安全机制必须改动，按参考包紧停条件单独报告并专项审查，不在A批准B |
| D6 | 备份/部署与native139 | 后续真实M3/V4备份支持、amd64/Hosted/容量另Gate；保留139未知 | 0018备份不可对0023假成功；没有本轮服务/测试/CI容量证据 |

建议 B（未来明确授权后）的顺序：先冻结domain+source、permission+demo和精确OpenAPI/seed manifest → 实现并独审V40-03 → 增量V40-04及真正PG隔离/reset/幂等 → V40-05实际浏览器联调与原M3 smoke → ROOT按变更风险释放完整动态PG/独审/远端CI门禁。本报告只提供A的源码事实和合同输入，没有承诺B完成时间、节点通过数或发布状态。

本轮结果：**静态审查文档已交付；实现/测试/迁移/新资源/CI/发布均未执行、未由本报告授权。**
