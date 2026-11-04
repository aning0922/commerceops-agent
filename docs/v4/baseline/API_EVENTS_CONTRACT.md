> 状态：PROPOSED / A阶段候选合同；V4-0代码NOT_STARTED。冻结的是文档内容，须用户审核并另发B授权后才允许实施。绑定远端M3 `952e6246deb01ec763f2541d9f316753987744f3`；不修改旧业务合同。

# API + events · v4-v1 候选

## already_existing 与 proposed分界

已有真实接口均在/api/v1（含既有库存/解释测试路径）及其专属OpenAPI，完整清单见reviews/M3_API_INVENTORY.json与M3_BACKEND_AUDIT.md；旧DTO/errors/schema版本不被新统一信封替换。新/api/v4端点本轮只是候选，代码NOT_STARTED。

## V4-0精确候选端点

| 方法/路径（全为proposed） | 请求 | 响应与鉴权 |
|---|---|---|
| GET /api/v4/demo/bootstrap | 无业务参数 | bootstrap CSRF+绝对到期，短期opaque cookie；限流/受信Origin（同源GET缺Origin例外见后文），不能创建业务数据 |
| POST /api/v4/demo/sessions | request_key UUID, fixture_version | Origin/CSRF/bootstrap；201或同key原结果；生成当前tenant默认operator及两店；禁止tenant/role/principal字段 |
| GET /api/v4/demo/session | 无 | 当前demo身份、权限、两店、TTL、epoch/generation、CSRF；401/403不泄漏旧数据 |
| POST /api/v4/demo/persona | request_key, persona_id, expected_generation, expected_epoch | 当前会话+Origin/CSRF；只允许服务器allowlist，200回执与新generation；冲突409 |
| GET /api/v4/demo/seed-summary | shop_id | 当前scope下同源数量/fixture digest，无经营KPI伪造，跨店404 |
| POST /api/v4/demo/reset | request_key, expected_epoch, expected_generation, fixture_version | 当前会话/Origin/CSRF/CAS；200回执；原子清当前tenant覆盖并推进epoch |
| POST /api/v4/demo/logout | request_key, expected_generation, expected_epoch | 当前会话/Origin/CSRF；撤销/清cookie；200最小回执 |
| GET /api/v4/demo/operations/{operation}/{request_key} | operation白名单、原键 | 有效owner会话下查最小控制回执；仅session_create允许对应未过期bootstrap作最小状态查询；原key无记录仍UNKNOWN；不暴露跨persona业务数据 |

创建会话丢ACK：必须保有仍可核验的bootstrap owner和原key以只读获取已提交的最小session建立状态；禁止按原POST重发。若无法安全恢复bearer cookie，返回OWNER_RECOVERY_REQUIRED且保留旧tenant记录，待TTL清理；用户明确重新开始才建立新tenant，新tenant不是旧操作已回滚的证明。不得通过GET把数据库token_hash还原成明文。实施必须测试cookie已应用而body丢失，以及header/cookie整体丢失两种情况。

所有请求strict extra=forbid，内部标识/当前roles/organization/auth_version均服务端推导；shop_id只是请求目标，必须核当前授权。读不要求CSRF但拒绝不受信Origin，写Origin+CSRF强制；禁GET业务重置。Session cookie安全属性及CORS方案见permission合同；生成OpenAPI必须声明cookie/CSRF安全要求，不能因独立inquiry旧文档未声明security而推断它公开。

## 新信封与错误

schema_version=v4-demo-v1，status, server_time(成功为DB UTC；DB不可读的失败为null，不用宿主时钟冒充DB事实), trace_id，data，以及source证据字段。成功写入包含operation/request_key/payload_digest/receipt_id/committed_at/epoch/generation，不返回session token。error包含code/safe_message/retryable=false；401 SESSION_INVALID/EXPIRED，403 ORIGIN_DENIED/CSRF_INVALID/ACCESS_DENIED，404 RESOURCE_NOT_FOUND，409 EPOCH_CHANGED/GENERATION_CHANGED/IDEMPOTENCY_CONFLICT，422 INVALID_REQUEST，429 CAPACITY_LIMIT/RATE_LIMITED及Retry-After，503 SERVICE_UNAVAILABLE。DB不可读/HTTP失败均保留UNKNOWN，503不自动重试POST；响应不可把业务错误伪装空集合。

## PG内事件（不是新队列/Worker）

proposed事件名 demo.session_created / persona_changed / reset_committed / session_revoked / seed_materialized。与状态变化、幂等receipt在同一PG事务提交，包含tenant、actor、epoch/generation、原key/hash、DB时间和最小对象引用，不含token/CSRF/PII。不可变审计与receipt不被普通reset删除；之后按已登记tenant+绝对截止清理安全保留记录。无需SSE/WebSocket/event bus或第二Worker。

ACK未知、缺行、401和新会话不能伪造COMMITTED。暂不扩采购/Agent/自动化接口；这些为后续全量66页提案，必须各阶段再冻结而不抢跑。

## A独审修订：精确恢复与响应上下文（此节为上文细化）

创建前bootstrap是PG owner行，独立随机token_hash与create_request_key绑定，TTL300秒、同cookie名/Path=/api/v4，权限仅bootstrap CSRF及单个session_create key的状态查询。POST创建提交后保留原bootstrap owner/创建receipt到该300秒截止，不能再以bootstrap写入/换key创建。只有当前owner哈希及精确key匹配且未到期才允许GET operations/session_create/{key}；其他operation或其他bootstrap key统一404，不披露tenant、shop、principal、session_id和数据。返回最多 {operation,request_key,status:COMMITTED|UNKNOWN,recovery:OWNER_RECOVERY_REQUIRED|WAIT_READ_ONLY}，不返回明文cookie/token、CSRF或可用新身份。此专例不是普通session认证、不允许其他业务读取/写入。

若Set-Cookie已应用、body丢失：GET current返回active身份和creation_request_key，核对原key再GET原回执；若cookie/header整体丢失、bootstrap仍在：上述受限GET只证明创建的最小状态，不能恢复bearer；显示OWNER_RECOVERY_REQUIRED，不自动POST。bootstrap也过期/丢失时保持UNKNOWN，401不能推断原事务状态。用户明确点击“重新开始新空间”才允许新bootstrap/new key，旧空间仍保留至TTL回收且计并发cap。拒绝bootstrap跨key探测/重放写/到期恢复必须测试。

所有敏感成功读取和写入均带 context={tenant_id,organization_id,principal_id,shop_id|null,reset_epoch,auth_generation,authorized_at(DB UTC)}；session级shop_id=null且返回服务端授权shops，seed-summary必须为请求的shop UUID。context由服务端当前权限检查后生成；epoch/generation过期时不返回data。GET current还包含creation_request_key、persona和CSRF。客户端请求快照+递增request_seq和context比较才渲染；切换/重置开始即清敏感数据，不能等响应后才清屏。跨标签规则见UI合同；客户端通知只是清屏提示，不能授予权限。

GET：显式Origin存在则必须精确allowlist；缺失Origin只在同源部署、校验Host/配置的可信origin且Sec-Fetch-Site= same-origin（或明确同源非浏览器测试配置）时允许。cross-site/same-site但非同源拒绝；跨origin Web/API的实际浏览器GET必须传受信Origin并credentials。写始终要求精确Origin+CSRF，不接受缺省Origin。代理不能信任任意转发Host/Proto；新owned配置明确可信反代，既有API不因此放宽。

同key原结果是服务器抵御并发重复/网络重放的幂等保证，不意味着客户端可自动重发POST。reset/persona后有效会话只回安全控制receipt；旧persona业务receipt受当前授权/epoch重新检查。logout/到期/撤权后不再给业务或控制恢复特权，只显示未登录/UNKNOWN，绝不虚构原操作COMMITTED。

## 严格候选OpenAPI附件

v4-public-openapi.json现列8端点、strict request/response对象、cookie+CSRF/Origin说明与bootstrap只读例外；所有success/failure DTO为候选，不声称已生成或执行。seed-summary必须带X-Demo-Epoch和X-Demo-Generation，服务端与当前session比较不符即409；GET current是恢复当前身份的最小控制读取，无旧业务payload。写body的expected_epoch/generation作CAS。读取控制回执不返回旧业务内容，因此无须伪装当前数据context；业务成功读写必须context。bootstrap匿名无业务context，失败无敏感context。登出成功response的context仅是提交前权威身份与原epoch证据，不授予后续读取。

角色可见店铺与联合seed规模分开：每tenant seed固定登记两店，SessionData.shops仅含当前persona已授权的0–2家；受限管理员可能无业务grant，不能为满足“两店”而默认赋业务权限。默认operator fixture可显式授予两店，跨店负例使用有意移除grant的另一persona或撤权，不把两店seed误读成所有角色均有全店访问。
