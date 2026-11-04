# V4-0 四合同与计划独立审查

日期：2026-11-03（Asia/Taipei）。**当前结论：REVISE_CANDIDATE，1项P1合同澄清、1项P2待修；尚不签ACCEPT_CANDIDATE。** 仅阻止候选最终冻结与依赖身份/DTO的实施；不要求本轮代码、测试或资源操作。

首轮发现CR-01（DB失败响应时间矛盾）已由ROOT修正。随后按ROOT通知复审新字节，独立核实Terra的两项P1已在文档层面关闭。保留全部首轮记录，未覆盖Terra报告。当前剩余为CR-02身份桥接的安全不变量须进入合同、CR-03授权店铺基数冲突。

本轮仅写此文件；未修改ROOT合同/参考包/仓库，未执行工具链、pytest/collect/扫描器、PG/服务/浏览器、Git变更或远端写，未读历史秘密。审查包括标准库文本/JSON读取和精确git show，不是运行验收。未来B仅03–05本地候选，Hosted/Harness/下一阶段不在范围。

## 1. 精确文件快照与变更控制

路径均相对 `/Users/aipuli/Documents/Codex/2026-11-03/commerceops-v4-readonly-review/`。首次准备写报告时检测到ROOT文件哈希变化，校验在写入前中止，未把旧结论落为最终版本。下表本轮复审hash已在写入本报告前再次核一致。后续变更须新hash增量复审。

| 文件 | 本轮复审 SHA-256 |
|---|---|
| DOMAIN_SOURCE_CONTRACT.md | `303f187bf0acd604f5eb8260894bf57c2f739cfa9ae314e11fed3bbeaae4d0aa` |
| PERMISSION_DEMO_CONTRACT.md | `e195071d5faa33a25d0aebb97a9627d06f5f4589348e33cbeeaa1800fa5b4230` |
| UI_ROUTES_CONTRACT.md | `643b5f0903b5c6b8ceff763f709fcc5745f4fee062f00faa66f8dafc4adf1b2f` |
| API_EVENTS_CONTRACT.md | `3d413e86a883a6db164527b5a801af0594cc1cd81b9c6cf037840fa8c28546ab` |
| TASK_PLAN.md | `76660c9adf71e4aff7165f9a8fa0fa140c4bd1ce67467c3f369024827d41dc60` |
| v4-permission-matrix.csv | `139e04d028aae19b6f476e0f2f16c93f15ab9e649801c5138b96a896c9ab6cdd` |
| v4-demo-seed-manifest.json | `24fd9041ef6beae75a161b9fd9243bf085bcf4a2bae6fc2eed79307d56f0896e` |
| v4-public-openapi.json | `19f9585fc1db6de2c2037c369f50bd356d0f2e80599b0332ec49b14204ad5797` |

### 首轮hash（保留，不代表当前候选）

| 文件 | 首轮 SHA-256 |
|---|---|
| DOMAIN_SOURCE_CONTRACT.md | `9fb3f09a361e4ababa661a8efafdd5184e2911ca7b2fd02de33fc9a626e97321` |
| PERMISSION_DEMO_CONTRACT.md | `1a571724f3bf2c3349a8ef262ad6c52ea31555040c9b75deb8d5c9083397673b` |
| UI_ROUTES_CONTRACT.md | `360f9a0610f5d76177f61f6e1171e57ee8cd517aaba58dd1b13d3be09f6c3a3e` |
| API_EVENTS_CONTRACT.md | `e8e154f9f51ccc196da49bac932f9e461f64a5682cc952f12cc7a1cc38a90e44` |
| TASK_PLAN.md | `76660c9adf71e4aff7165f9a8fa0fa140c4bd1ce67467c3f369024827d41dc60` |
| v4-permission-matrix.csv | `139e04d028aae19b6f476e0f2f16c93f15ab9e649801c5138b96a896c9ab6cdd` |
| v4-demo-seed-manifest.json | `24fd9041ef6beae75a161b9fd9243bf085bcf4a2bae6fc2eed79307d56f0896e` |
| v4-public-openapi.json | `27009691a437a7a94e80414a50436fa5a0421b8fba580a3e11e924e42e3abadd` |

源码对照M=`952e6246deb01ec763f2541d9f316753987744f3`，原仓库 `/Users/aipuli/Documents/Projects/commerceops-agent`；M:path:line全部指该精确Git对象行号，不是工作树。其他文档行号绑定上表本轮hash。引用Terra首审的review文件只用于按ROOT要求核对两项P1，不把其结论当本审查的替代。

## 2. 仍需ROOT统一修订

### CR-02 [P1] 身份桥接必须明确禁止bearer跨旧API复用，并定义旧actor撤销

**定位：** `PERMISSION_DEMO_CONTRACT.md:11–13,19–23`；`DOMAIN_SOURCE_CONTRACT.md:11`；`TASK_PLAN.md:11–15`。

现文档选择独立cookie名称/Path、DemoSession绑定旧WebSession，并笼统“调用现有SessionStore/actor_guard”。但这些字句尚未排除直接将公开demo bearer写作旧web_sessions.token_hash或把公开token喂旧SessionStore；也未明确reset/persona的epoch更新如何让旧bound WebActor失效。ROOT在最新消息提出的精确限制正确，应写入受审合同，而非只停留在跨会话说明。

**可具体发生的错误实现：** 同一bearer既满足V4解析又被旧SessionStore接受。请求者可手工把该值放入commerceops_session，直接请求旧/api/v1；该路径不核V4 epoch/generation，cookie Path不同不能作为服务器端权限边界。另一种错误是只增加DemoSession.generation、保持内部旧session有效；旧WebActor不含generation，旧guard仍可能接受它。这里不是宣称代码已出现漏洞，而是当前允许的设计解释中存在能绕开拟定边界的一支，应在安全合同冻结前排除。

**精确源码证据：**

- M:`backend/src/commerceops/application/replenishment/contracts.py:132–140`：WebActor仅session_id/principal_id/identity_id/organization_id/auth_version，无V4 epoch/generation。
- M:`backend/src/commerceops/infrastructure/web_sessions.py:173–219`：_session按token_hash查询web_sessions并核credential/identity/principal、当前session与CSRF；authenticate:233–235接受明文token。
- 同文件actor_guard:59–110只核principal/auth_version及旧WebSession身份/撤销/绝对与idle期限；它不包含V4 epoch，且不等于_session中的完整credential校验。role_scope:113–126复用actor_guard。
- M:`backend/src/commerceops/entrypoints/replenishment_http.py:152–168`：/api/v1使用commerceops_session进入旧SessionStore，不受V4 boundary保护。

**A最小修订建议（可合成一个明确规范段）：**

> V4公开bootstrap/active bearer只能在V4认证命名空间验证，禁止作为business.web_sessions可接受token，禁止把它直接交旧SessionStore.authenticate；旧WebSession仅作为服务器私有WebActor证据引用，不能通过公开API换领其token。新窄resolver按可信映射核完整credential/identity/principal/session有效性与V4 tenant/epoch/generation；不得仅凭actor_guard省略原credential校验。内部session绝对期限不晚于DemoSession原绝对期限；persona/reset原子撤销或替换旧bound session并推进V4 generation，logout撤销所有当前bound会话。只保留稳定公开cookie定位，不保留旧actor授权。

再明确：所有V4写在同事务锁后复核；旧读响应使用新context屏障。旧bound session替换与receipt/epoch同事务，不能先给新身份而后异步撤销旧身份。`operator→approver→operator`、同persona reset、复制demo token为旧cookie、旧actor迟到、撤credential、TTL/idle边界列为未来B负例。

**Gate与授权：** 具体SQL/登记函数/低权ACL/锁顺序仍是PERMISSION:13已经声明的实施前窄桥接专项Gate；无需A设计全部SQL，更不批准改旧guard。TASK_PLAN:15、23的精确diff释放继续有效。这条P1针对需进入候选合同的安全不变量，不要求拿未写的代码证明实现通过。

### CR-03 [P2] strict SessionData强制两店，无法表示无业务grant的persona

**定位：** `v4-public-openapi.json:1227–1265`，`components.schemas.SessionData.properties.shops`尤其:1245–1248的minItems=2/maxItems=2；`API_EVENTS_CONTRACT.md:42`称session返回服务端授权shops；`PERMISSION_DEMO_CONTRACT.md:27`及`v4-permission-matrix.csv:2`规定受限admin无默认业务grant。

**触发：** 用户切换为无业务grant的restricted_admin，或后台撤销某一shop授权。当前会话仍可合法操作自己的reset/logout，但授权shops应为0或1。strict DTO强制两店会迫使实现泄露未授权店铺、给admin补grant，或返回不合法响应/错误地将整个会话判死，三者均违背候选行为。

**最小修正：** SessionData.shops表示“当前可读店铺”，允许0–2（空数组合法）；两店是tenant初始化的不变量，不是每一persona的读权限不变量。默认operator初始拥有两店的断言留在seed/初始化验收，而不是通用session响应基数。明确shops按shop_id唯一并与当前grants相符；无grant persona能看到身份/控制页，业务summary仍403/404且不回其他店铺资料。若选择返回两条纯控制目录而非授权shops，须另设严格非业务字段并修改语义，当前最小方案无需此扩展。

**关闭条件：** schema与API/权限/空态一致；未来B增加0店、1店、2店与撤权后current/summary负例。无需本轮运行测试。

## 3. 首轮CR-01保留与关闭

首轮 `API_EVENTS_CONTRACT.md:28`规定全部server_time为DB UTC并要求DB不可读503，首轮OpenAPI `Envelope.required/server_time:1027–1038`却只允许必需date-time字符串。PG连不上时无法同时满足，属于P2，不能填本机/旧时钟冒充DB时间。

本轮API:28明确“成功为DB UTC；DB不可读失败null”；OpenAPI `components.schemas.FailureEnvelope.properties.server_time`（FailureEnvelope起于:1437）已为string|null，描述禁止invent DB time。Bootstrap/Session/Create/SeedSummary/Control/Operation成功信封仍要求string date-time。**CR-01 CLOSED_AT_DOCUMENT_LEVEL**。这只是静态合同一致，不是实测503或UI解码通过。

## 4. Terra首审两项P1的独立关闭核验

原件 `reviews/UI_CONTRACT_REVIEW.md:11–17` 的P1-1/P1-2保持不变；其绑定旧四合同hash，见该文件:5–8。当前关闭只适用于本报告本轮hash。

### Terra P1-1：bootstrap丢cookie只读资格 — CLOSED_AT_DOCUMENT_LEVEL

- API:20明确仅session_create可走原bootstrap例外；:38固定PG owner/token_hash、单create key、300秒截止，提交后bootstrap不能再写或换key创建；只返回最小COMMITTED/UNKNOWN与recovery，不披露tenant/shop/principal/session_id、不发token/CSRF。
- API:40把“Set-Cookie已应用/body丢失”与“headers/cookie整体丢失、bootstrap仍在”分开；前者GET current核creation_request_key，后者受限GET只能确认最小状态，不能恢复bearer；bootstrap过期/丢失仍UNKNOWN，明确重新开始才建新空间，旧空间仍占cap至TTL。
- PERMISSION:35同步例外边界。OpenAPI operations:get的 `x-bootstrap-exception` :1037明确原token+key、<=300秒及最小OperationData分支；OperationData一分支是普通receipt，另一分支是仅session_create最小响应，两者strict无额外属性。bootstrap必须由运行时选择第二分支，不能因共享schema便返回普通receipt。
- UI:31已要求两种cookie状态按API恢复节分流，不自动POST或填假数据。

原问题的权威主体、期限、操作边界和失败退路现已写清。实现仍需跨bootstrap/key探测、过期、拒绝重放写及两类丢ACK负例。初始建立不能保证恢复到active是明确失败关闭选择，不再要求新增可还原token方案。

### Terra P1-2：敏感读context与多标签屏障 — CLOSED_AT_DOCUMENT_LEVEL

- API:42规定服务端tenant/organization/principal/shop/epoch/generation/authorized_at context；:50补seed-summary必须提交X-Demo-Epoch/Generation，与当前会话不符409，不返回业务data；GET current仅是当前身份控制读取。
- OpenAPI Context全字段required（:1051起）；SeedSummaryEnvelope必需context；seed-summary请求头在:604–619固定。没有把旧cookie存在等同于旧授权。
- UI:31控制开始即同步清状态、禁止新业务请求；响应按request_seq和context核对，Abort不等于服务器停止。
- UI:33 BroadcastChannel只发invalidate、不含身份token业务；hidden/offline清屏，恢复先GET current；可见active每5秒核current，失败清屏，丢通知负例明确。文档诚实声明已有像素/跨设备不能瞬间撤回、跨标签显示有验证时延，不把通知当服务器授权。
- PERMISSION:37同步边界。UI:37列启动失败、429、401/403、reset UNKNOWN等可验状态；API:44明确同源GET缺Origin与跨origin/写入策略。

该关闭认可“服务端即时拒绝过期请求＋客户端清屏/恢复/5秒收敛”这一明示合同，不承诺实时撤回已读内容。未来实现/浏览器Gate仍NOT_RUN。

## 5. 其他重点的审查结果与实施前Gate

**reset/旧CSRF：** PERMISSION:19–23将稳定公开cookie定位与授权代际分开；旧CSRF失效后用有效owner GET current取得新CSRF，原key仅查最小receipt，不重POST。logout401不代签COMMITTED，到期/撤权不保留普通恢复特权。DOMAIN:25事务CAS/tenant锁、保留tombstone、拒绝旧写提交新epoch与该策略一致。CR-02补旧内部WebSession生命周期后可形成完整桥接边界。

**seed/reset仍需细化但不是当前新增P1/P2：** manifest明确PROPOSED_NOT_GENERATED，counts/digest=null未虚报生成；DOMAIN:21要求03/04实施前冻结最小规模，不能把建议万条数据当已批准资源。需在seed_contract固定generator/seed/日期锚/每店实际对象关系、reset保持当前persona还是回operator、tombstone精确保留期、receipt提交时epoch与当前epoch的区别。digest必须生成后填真实值；不要求A伪造。实际表/迁移不得提前承载采购/CRM状态机。

**迁移/owner：** TASK_PLAN:10从0023新0024且head变化重签；:30明确03冻结后不改旧revision，04若需第二revision增量审；03/04同一SCHEMA/API串行，WEB/QA路径不重叠；database.py窄grant另释，原Worker/Compose/锁/workflow无owner默认受保护。03在创建session时已依赖最小seed接口，应先冻结共同schema再提交03，不通过后改旧0024。当前没有授权多人并写或偷偷改旧迁移。

**下阶段界线：** DOMAIN:13首次仅同源摘要/欢迎，六场景为fixture引用，不宣称可运行六链；新:33不启动per-tenant Worker或投递Graph。UI:11、13、35止于三条辅助/受限路径，不计作66业务页完成。API:34与TASK_PLAN:45止于V4-0；CSV未来草稿/审批能力是规划权限，不授权本批实现采购/审批端点。Hosted/amd64/Harness仍独立未授权。

**安全模式与资源：** V4专用cookie、服务端权限与Origin/CSRF/同源策略已明确；V4-0模型/embedding/飞书/Woo均0调用，模式标签不证明执行。新owned对象、绝对截止、cleanup与实际预算仍待B的TaskSpec；本报告不填这些未来值。旧M3回归与完整动态PG/G1G2按高风险Gate保留，历史719不作为新实跑常数。

**OpenAPI：** 新版已比首轮增加strict候选对象与响应上下文，本轮只读检查并不等于OpenAPI验证器、生成DTO或实际路由契约通过。源码未开工，尚不能宣称无运行问题。除CR-03外，未因已明示的实施前细化事项另造阻断。

## 6. 给ROOT的最小处理

1. A将CR-02所列不可跨域bearer、私有bound session、完整resolver与原子撤销规则明确写入PERMISSION（必要同步DOMAIN/API/TaskPlan的引用），仍保留实现前专项审查；无需改业务代码。
2. 修CR-03的SessionData.shops基数及相关文字，明确tenant双店与当前授权店铺不同。
3. 发送新的文件hash进行小范围增量复审。CR-01与Terra两项关闭记录保留，若修订未触及其边界不重复全套Harness盘点。

本报告不提前对未来字节签ACCEPT；用户B授权、身份桥接专项Gate、资源准入与实际测试均独立。只读审查不能代签API_PG_VERIFIED或V4-0完成。
