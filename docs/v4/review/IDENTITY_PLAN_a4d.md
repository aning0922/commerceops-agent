# V4-0 身份SQL与seed专项设计独立审查

日期：2026-11-03（Asia/Taipei）。**结论：P2_REQUIRED_CHANGE，0 P1 / 1 P2。** 新身份/SQL方案主体在设计层面覆盖了冻结不变量；需先统一创建端点的cookie用途，再对修订精确SHA给专项准入结论。本报告不批准业务代码、真实PG窗口或旧测试更新；具体放行由ROOT执行。

## 1. 精确审查对象

- candidate：`a4d8336caa160abba6efdf0cfaae1a87e71e95e5`。
- tree：`a657c3b794de0e9a2d066750137404f997daa535`。
- parent：`eb82c9d626c210e8e982ba3d8889a4ffdd088c99`。
- 唯一两变更：`docs/v4/design/IDENTITY_SQL_PLAN.md`（467行，SHA-256 `ca100a0c3a67fa1a3995c4cc7c4bdff88b22c39108ff67c29d28f84352be6d22`）；`docs/v4/design/SEED_SPEC.md`（135行，SHA-256 `19441d46ac32a2976a3e06cf8d44103d5aada2f0ae5b01be6e5a77b8bb0e95d5`）。

全部从精确Git对象读取；未读Backend WIP，未执行模块、SQL、测试、PG/服务或旧runtime，没有代作者修改。另仅核相同commit内冻结OpenAPI创建操作的cookie用途以确认合同差异；未重复A全量审计。下文I=IDENTITY_SQL_PLAN、S=SEED_SPEC，行号均绑定本候选。

## 2. IDPLAN-01 [P2] POST sessions的active-cookie分支违反冻结bootstrap-only接口

**定位：I:329–335、355；相同commit内 `docs/v4/baseline/v4-public-openapi.json` 的 `paths./api/v4/demo/sessions.post.x-cookie-purpose` 与 `x-authentication-phase`。**

冻结操作用途是 `bootstrap only` / `anonymous_bootstrap_cookie_and_origin`。设计I:329–335也先要求bootstrap CSRF、bootstrap owner行和key reservation；但I:355另允许activecookie+creation_request_key+当前CSRF通过POST返回200当前session和原receipt。于是同一端点出现两个不一致的前置认证路径：按冻结严格boundary实现会在active分支前拒绝；按355实现则新增未冻结的active认证用途，客户端/QA无法依原合同给出唯一预期。

这不是已发生的提权或写入漏洞：分支意图是零新增effect。但它确实改变冻结安全接口，且本身与本设计入口顺序冲突，应在设计准入前消除，不能留到实现时任选。

**最小修正：** 删除active-cookie再次POST可200返回的分支；active持有者统一走现有GET current（核creation_request_key）与GET operations/session_create/{key}恢复。POST sessions保持bootstrap-only；consumed bootstrap不能发新cookie、不能返回含身份的CreateEnvelope，按现设计409 OWNER_RECOVERY_REQUIRED/原key只读处理。服务端唯一约束仍保证并发重复不会创建第二tenant，不能把“幂等”误解为必须支持两种认证阶段POST成功。

若作者坚持引入active POST，需要ROOT显式裁定合同增量、同步OpenAPI/边界/测试而不能改A历史原件；本轮无功能必要性，建议走最小删除方案。原OpenAPI列200不自动授权新增cookie用途。客户端UNKNOWN从不自动重POST的规则保持。

**关闭验证：** 两设计中无active POST成功路径；入口用途、consumed bootstrap处理和两类丢ACK恢复一致；在未来实现测试分别验证active POST安全拒绝、active GET原回执成功、consumed bootstrap最小GET恢复与并发create一次effect。当前仅需文档修订，不为此开PG。

## 3. 设计已落实的关键边界

以下是对设计可行方向的静态判断，不是SQL已执行/ACL已实测的证据。

| 检查点 | 具体依据与判断 |
|---|---|
| 公开bearer跨旧API拒绝 | I:20–23的v4b_/v4d_+43字符随机尾部共47字符，公开hash不写旧token_hash；旧43字符解析域拒绝改名cookie。私有bound token生成hash后丢弃，不提供旧密码登录。实际401仍待ID-01。 |
| 完整identity/credential映射 | I:258–288给唯一resolve_locked和明确JOIN，包含credential enabled、identity/provider/principal/org/auth_version，另核完整bound四元组、kind、撤销、key/CSRF与时限，最后复用actor_guard/role_scope。没有只调用窄guard冒充完整认证。 |
| 撤销旧actor | I:290、374–395要求persona/reset同事务撤旧bound、新bound、current binding/CSRF/generation及receipt；reset保persona且epoch+1，persona不变epoch；旧bound不会原地换主体。S:112–120同步。 |
| 时间与锁等待 | I:31、260–271采用DB clock_timestamp；tenant/session/内部bound不续原30分钟，bootstrap300秒；锁后与序列化前重核时钟。I:305限制statement/lock/客户端事务预算，异常UNKNOWN不盲重试；失败响应时间可null（420）。 |
| 锁序 | I:294–303规定create容量锁→bootstrap→tenant→session→排序principal→bound→shop/grants→overlay/receipt/events；不持bound再取principal。I:266明确不新增credential行反向锁，依旧触发器auth_version与新READ COMMITTED statement复核；实际旧触发器锁交互须在代码/PG Gate核对，不能由伪码签无死锁。 |
| cap3 | I:296、309、334–349要求固定事务advisory锁内统计live tenant+session并原子provision。丢cookie已commit仍占位，expired未清理不占位；credential撤销但未明确revoke保守占位。peer限制、scrypt semaphore与bootstrapcap128分层，不把其他429冒称cap证明。 |
| 初始化原子性 | I:337–349含全部新org/shops/personas/credentials/scopes、最终auth_version、bound/DemoSession、receipt/events及consume；独立key reservation/rate记录不被称为COMMITTED业务。失败不允许残留半个tenant。 |
| bootstrap丢ACK | I:324、355、407–411及S:118–119区分仍持bootstrap与已持active两状态；原owner/key300秒仅最小提交状态、不回token/CSRF/业务标识，过期UNKNOWN。IDPLAN-01只要求统一POST用途，不推翻此GET恢复设计。 |
| 幂等与旧CSRF | I:375–393先完整当前auth/CSRF，查stable owner+operation+key并核完整canonical digest，未命中再CAS；旧CSRF并发可403，GET核原键；当前CSRF重放原body无第二effect。不以历史receipt绕到期/撤权。 |
| 十表/跨表关系 | I:33–218列完整表/关键FK/unique/check、不可变/单调与deferred guard责任；receipt owner/tenant、bound身份与before/after、事件、两shop/三persona必须同tenant绑定，不是全表存在性。trigger SQL尚未实现，后续逐函数核谓词与DELETE/GC例外。 |
| ACL边界 | I:222–254明确迁移不自动grant，单独owner helper；PUBLIC revoke、新表显式列级授权，provision固定参数且只创建函数生成的新synthetic对象，SECURITY DEFINER固定search_path、无dynamic SQL。无旧org目标和UPDATE existing credential分支。 |
| 角色店铺 | S:85–95固定operator两店、approver仅A、admin零店，全部依据当前scope/grant；登记trigger完成后才读取最终auth_version。reset不恢复撤销grant或为admin补业务权限。 |

**关于“独立runtime”的准确口径：** 设计I:24、252–254明确沿用既有commerceops_app，独立的是V4 grant入口和新表权限；没有新增数据库隔离角色/RLS。因此只能接受为可信后端固定SQL、身份guard和数据库约束边界，不能宣传runtime凭据本身实现每tenant隔离或全库只读。当前设计已经诚实写明这一限制，不要求本轮另造角色架构。

## 4. Seed/reset/GC专项

S:13–26冻结生成器/独立PRNG、UUIDv5 namespace、日期域、两店币种时区；:32–58明确每店8 products/10SKU/12 orders/18 lines及可核公式，金额为Decimal、未知inbound/cost保留，退款不假定件数/回库。模板UUID与tenant真实shop UUID分离。

六异常是引用条件与后续阶段hint（S:60–71），不新建采购/CRM/营销状态机或投Graph。唯一业务摘要保持四计数字段（S:48），未给旧M3接口直接读未适配overlay；TWD不要求放宽旧DTO。

canonical content固定排序/UTC/Decimal，source commit作为manifest证据不混入fixture内容digest（S:75–81）；同版本不同digest拒绝，实际digest未生成不预填。DB登记与文件原子发布分别记账，EXPORT_INCOMPLETE不误称DB回滚，no-replace/目录owner明确（S:99–108）。

reset只清本tenant overlay，保留persona/ID/fixture/原期限及receipt；非空overlay由受控新域fixture_note测试夹具产生，不假装已有商品编辑API（S:112–116）。控制记录保留至原expires+24h，bootstrap物理保留不延长其300秒权限；GC仅owner显式tenant、确认过期与旧业务无依赖，不删除旧base对象，禁止GUC提权和全表TRUNCATE（I:440–446）。

GC实际trigger例外、deferred guard处理删除集合、外键删除顺序和旧bound历史枚举在代码Gate验证即可；设计已明确需要这些守卫，不因尚未编写完整函数另报“无实现”的阻断。

## 5. 旧测试精确更新与后续边界

I:448–463仅是七旧测试文件的释放申请，**本独审不替ROOT释放**。方向可接受：只同步current head/完整精确十表增量及对应fake；固定0012→0013历史闭包、旧行/Checkpoint字节、旧ACL/不可变拒绝和M2只支持0018不得放宽。实际75→85、79→89与26→36等数字仍应在最终迁移源码/当前collect核验，不因设计写出就预签实际schema。

新tests/v4纳入现有动态集合（I:438），可能进入combined-existing普通组；没有授权为新节点改300秒timeout/分片。若实测容量阻断，由ROOT另裁，不能减覆盖。旧139根因UNKNOWN与全部首失败保留。

未来代码审查需核：DDL/definer运行时完整权限、真实trigger旧锁交互、锁等待后到期、cap并发、旧actor撤销、COMMIT前后故障、每operation strict DTO、日志secret边界；既有矩阵ID-01—10足以指导首批，不在本轮追加无关功能。真实新owned运行由ROOT单独给对象/UTC，不自动开窗。

## 6. 交接裁定

请Backend仅先修IDPLAN-01，普通提交精确SHA交ROOT，避免把active POST分支与冻结boundary双轨落地。其余设计方向无需重做A审计；修订不扩大范围时可做小增量关闭，再由ROOT裁定专项准入。作者尚无业务代码/PG执行，本报告的审查接受或待修均不等于实现、资源授权或本地Gate完成。

## IDPLAN-01关闭：c4c484增量

最终设计candidate `c4c48401494b00308cc5a2022e4a8fcb0e3f8195` / tree `cd974e5cdd6085816cf2514c9f4d7b612809e542`，parent为上述a4d。仅两设计文件各一行段落替换，无业务/测试变化。

I:355已明确POST sessions只接受原bootstrap+CSRF+原key，active cookie拒绝；active只走GET current/operations。consumed bootstrap并发/重复不发新cookie、不返回敏感CreateEnvelope，原事务未知保持UNKNOWN，300秒最小GET恢复保留。S:119同步bootstrap-only。与原冻结OpenAPI用途及I:329–335入口一致，未增加认证分支，原body/hash冲突与唯一effect守卫仍保留。

结论：**IDPLAN-01 CLOSED_AT_DESIGN_LEVEL；ACCEPT_IMPLEMENTATION_DESIGN，当前该精确设计无未关闭P1/P2。** 保留上文首审P2；其余未变设计沿用前轮检查。此结论供ROOT释放受审范围内实现，不签代码/SQL已执行、旧七测试修改或实际资源窗口；后续精确实现及PG/API/Web Gate仍需独审/实测。本增量只读git diff，未运行工具链或服务。
