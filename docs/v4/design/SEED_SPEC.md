# V4-0 联合演示种子、来源、reset 与回执细则

状态：`DESIGN_READY_FOR_SPECIALIST_REVIEW`。2026-11-03，Asia/Taipei。与 `IDENTITY_SQL_PLAN.md` 为同一专项冻结包；本文件是具体实现输入，不是已生成fixture/hash/PG验收回执。

## 1. 精确范围与原则

绑定B父提交 `eb82c9d626c210e8e982ba3d8889a4ffdd088c99`，业务基线M3 `952e6246deb01ec763f2541d9f316753987744f3`。只在ROOT指定foundation工作树编写；旧资产/密钥/私有runtime不读不启。实现后迁移为0024，准确parent0023_p6_copy_drafts。

V4-0只交欢迎/身份/双店seed摘要/切persona/reset/logout。六链仅是可定位fixture引用，不实现采购审批到货、CRM/RFM、工单状态机、营销发布、真实知识上传/embedding或Agent/Graph/Worker任务。原M3的接口不直接消费V4overlay；TWD不扩进旧commerce/daily枚举。

## 2. 固定生成器与时间

| 项目 | 固定值 |
|---|---|
| fixture_version | `v4-demo-seed-1` |
| generator_version | `v4-seed-generator-1` |
| PRNG | Python标准库 `random.Random(4000001)`，独立实例；禁止全局random、系统时间、环境变量参与内容 |
| 模板ID namespace | UUID `e6c28525-1dca-510b-9093-a52c23b93598`，UUIDv5(namespace, `shop_key/kind/template_id`) |
| 业务日锚 | `2026-11-01`（含该日） |
| 完整fixture日期域 | 各店local `2026-10-19 00:00:00` 至 `2026-11-02 00:00:00`（14天，右开） |
| snapshot_at | `2026-11-02T00:00:00Z`；不是会话建立时间/浏览器今天 |
| 店A | template_key=`v4-shop-a`，display=`台北合成演示店`，timezone=`Asia/Taipei`，currency=`TWD` |
| 店B | template_key=`v4-shop-b`，display=`上海合成演示店`，timezone=`Asia/Shanghai`，currency=`CNY` |
| 模式 | data_mode=demo_fixture / evidence_mode=synthetic_demo；标签model_mode=offline_stub / embedding_mode=synthetic_vector / delivery_mode=offline_fake，但V4-0实际调用均0 |

生成器纯函数输出不含tenant/org/principal/session IDs、密码或时钟；同版本同源字节相同。若改变任何生成规则/金额/日期/引用，升级fixture_version及受审manifest，禁止覆写v4-demo-seed-1。PRNG只用于非关键fixture取样；下节关键数量/关系由固定公式和显式覆盖确定，不能概率生成六异常。

## 3. 本轮固定最小规模

每店固定，不采用资料包的大规模容量目标；属于真实PG可持久验证的小种子。**这些实体是只读模板数组，不在旧M3业务表建同名产品/订单/采购状态行。** tenant拥有实际org/shops/personas/scopes/session，引用共享immutable模板及其digest。

| 模板实体数组 | 每店条数 | 两店总数 | 最小字段/约束 |
|---|---:|---:|---|
| products | 8 | 16 | template_product_id、title、synthetic source；不含品牌/真人资料 |
| skus | 10 | 20 | template_sku_id、product_ref、variant_ref|null、stock_pool_ref、price、currency；SKU00/01、02/03各共享一个product，其余六各一个 |
| inventory | 10 | 20 | sku_ref、available_units整数或null、inbound_units=null及UNKNOWN_INBOUND reason、pool_ref；不写Woo |
| orders | 12 | 24 | template_order_id、customer_ref、created_at、paid_at|null、currency；local日期域内，支付与创建分别保存 |
| order_lines | 18 | 36 | order_ref/sku_ref、quantity正整数、net_amount Decimal字符串；订单0–5各两行，6–11各一行 |
| refunds | 2 | 4 | refund_ref、order_ref、occurred_at、amount、currency、reason；实际付款/网关退款状态unknown |
| customers | 6 | 12 | customer_ref、display=`合成客户01`等；无电话、email、地址、个人身份 |
| suppliers | 2 | 4 | supplier_ref、synthetic display、currency；不是供应商管理状态机 |
| supplier_quotes | 3 | 6 | quote_ref、supplier_ref、sku_ref、version=1、MOQ、unit_cost Decimal、lead_days、valid_until固定锚后；没有采购执行 |
| knowledge_refs | 2 | 4 | document_ref/version、synthetic原创短文本、license=`self-created-demo-v1`、hash、固定有效窗；没有真实embedding或旧pgvector登记 |
| purchase_fixture_refs | 1 | 2 | 仅sku/quote/ref和`planned_stage=V4-2`，hint=purchase_pending；无数据库采购state |
| support_fixture_refs | 1 | 2 | 仅order/customer/document/ref和`planned_stage=V4-3`，hint=support_escalation；无客服外发/工单state |
| campaign_fixture_refs | 1 | 2 | 仅sku/document/ref和`planned_stage=V4-3`，hint=marketing_draft；无活动发布state |

schema_summary接口严格只返回已冻结counts `{products:8,skus:10,orders:12,order_lines:18}` 和fixture source/digest/snapshot_at；其余计数在owner manifest/测试读取中验证，不能往严格OpenAPI偷偷加字段。restricted_admin没有业务grant时不回任一店摘要。

### 3.1 关系与金额规则

- 两店均用模板SKU标签 `SKU-00`…`SKU-09`，用来证明标签不构成跨店身份；真正ref必须含shop template key和kind。tenant内部shop UUID不同于模板UUID。
- product归属：SKU00/01→P00，02/03→P01，04→P02，05→P03，06→P04，07→P05，08→P06，09→P07。每SKU独立pool，禁止无依据共享池；variant编号只在该product内有义。
- orders i=0..11，customer=i%6；created_local_date=anchor−(11−i)天，created time=10:00:00+i分钟；默认paid_at=created+1h。order11.paid_at=null，显式status_hint=payment_timestamp_unknown而非断言未付款。
- orders0..5两行分别sku=(i%9)、(i+1)%9；orders6..11各sku=i%9。因此SKU09没有订单行，稳定滞销；SKU00有需求。quantity=1+(line ordinal%3)，price按店币种固定Decimal`100+10*sku_index`，net=price*quantity；VAT/成本缺失不计算利润。
- refund0引用order3，occurred_at=paid_at+1local日，amount=该order商品net的80%精确Decimal；refund1引用order1，occurred_at=anchor local12:00，amount=该order商品net的20%。保留跨创建/支付/退款发生日差异。不用货币金额猜退款件数/已回库；quantity/restocked仍null+reason。
- available：SKU00=0；SKU09=80；其他SKU固定20+index。inbound全部unknown，不填0。cost默认null；quote仅是某供应商报价，不等于商品真实成本。
- knowledge原创文本只含内部合成退货流程和演示商品保管说明，不含真实政策、功效/销量claim。文档内容时间窗2026-10-01T00:00Z至2026-12-01T00:00Z，是fixture历史时效，不等于当前provider已检索。

## 4. 六个稳定fixture入口（不等于六链已运行）

| scenario_ref | 精确模板关联 | 预期种子条件 | 后续功能阶段 |
|---|---|---|---|
| stockout | shop-a / SKU00 / inventory00 / orders0&9 | available0且至少一条正quantity的已记录paid订单行 | V4-2库存模拟 |
| high_refund | shop-a / order03 / refund00 / customer03 | 80%商品net退款记录，发生日与paid日不同 | V4-1/2经营钻取 |
| slow_moving | shop-a / SKU09 / inventory09 | 最近14天无该SKU订单行、available80 | V4-2/3分析营销 |
| purchase_pending | shop-b / purchase-ref00 / quote00 / supplier00 / SKU00 | 显式fixture hint+quote MOQ/版本，尚无可审批采购实体 | V4-2采购 |
| support_escalation | shop-b / support-ref00 / order06 / customer00 / knowledge00 | 订单和合成客户、退货说明均同shop | V4-3售后客服 |
| marketing_draft | shop-a / campaign-ref00 / SKU09 / knowledge01 | 滞销SKU与同shop合成资料引用，未生成copy或发布 | V4-3营销 |

manifest scenario status 固定 `fixture_links_only_not_functional_flows`。UI可以展示规划说明和未开放状态，不展示假的“已审批/已送达/Agent成功轨迹”。全部ref解析必须恰一目标，跨shop、错kind、悬空ref或数量公式不一致让generator验证失败。

## 5. canonical hash / source / UUID映射

1. 生成模板content：schema/generator/seed/date domain/两店数组/全部refs/模式；按固定字段/数组排序（shop key、kind、template ordinal），时间全部规范UTC `Z`，钱是无指数规范Decimal字符串，禁止float/NaN/Infinity、bytes或无时区datetime。
2. 采用现有 `commerceops.domain.commerce_values.canonical_bytes(content)`；`SHA256(bytes).hexdigest()`为fixture_digest，content不含它自身。每entity digest同法，manifest含各数组count与有序hash，顶层digest覆盖关系和scenario_refs。
3. owner manifest包装 `content_digest`、generator、counts、snapshot和source commit。source commit属于构建/验收证明，**不进入跨tenant共享content_digest**，避免同fixture版本仅因文档SHA变化而改内容；generator byte变化仍需独审/版本策略。
4. 模板UUID按§2 UUIDv5。new tenant/org/session用新UUID4；tenant shop/principal/identity由受限provision函数gen_random_uuid()生成并持久登记映射，reset不重新分配；只有共享模板ID使用Python标准库UUIDv5，不要求新增PG扩展。不能将template UUID直接当旧business.shops.id；resource ref包含tenant/shop/kind/id/version/epoch。
5. neworg reserved marker name=`V4 synthetic demo <tenantUUID>`；为满足旧organizations/identities复合FK，app_id=`v4-demo-app-<tenantUUID>`、tenant_key=`v4-demo-tenant-<tenantUUID>`，只synthetic字符串，不是真飞书应用。shops adapter_kind=mock、environment=mock、external_shop_key各模板key、config_ref=`v4-demo:<tenantUUID>:<templateKey>:v1`。
6. `v4_demo_fixture_versions` owner-only登记canonical_content/json/hash，数据库原生SHA256同时核；同version同digest幂等无变化，不同digest硬冲突，不能UPDATE覆写。所有tenant复用该只读模板；tenant overlay必须独立当前epoch，查询不能混成原Woo已确认事实。
7. 本文件没有计算实际fixture_digest；实现后纯生成器+真实PG互证，才填写运行manifest。不可将设计例子hash预写为真实hash。

## 6. persona、scope与完整身份初始化

| persona_id | principal.roles | 初始scope与role_shop_grants | SessionData.shops |
|---|---|---|---|
| operator | `[operator]` | 店A/店B各enabled scope与operator grant | 两店（按实际当前grant核，不硬编码） |
| approver | `[approver]` | 仅店A enabled scope与approver grant；店B无scope无grant | 仅店A；对店Bseed-summary404 |
| restricted_admin | `[admin]` | 无业务scope/grant | 空数组；控制自己的persona/reset/logout仍允许 |

三个persona不是客户端授权的roles；server按tenant allowlist映射principal。首次固定operator。不授approver运营、不赋admin默认订单读。后续审批对象仍需指定reviewer，V4-0没创建审批实体。

credential：新不可公开login=`v4.<tenant uuid无横线>.<persona>`（小写<=100、满足旧regex），随机一次性secret用原scrypt编码后丢弃；只供旧完整credential enabled/identity检查，不向用户提供密码登录。roles/scopes/credential INSERT会触发旧p3 auth_version推进，因此**全部登记完成后读取最终auth_version，再建bound WebSession和DemoSession**，不能假定初始1。

Web identity provider=web，app/tenant对应新orgsynthetic值；external_subject是同一个opaque新login。所有API明文/日志不含credential/hash/bound token；username也不作为角色选择输入。详见IDENTITY_SQL_PLAN§5的完整JOIN与bound检查。

## 7. CLI、文件发布和事务原子性

唯一新CLI计划 `python -m scripts.v4_demo_seed`，不调用旧m3_* CLI或测试prepare，不读取旧私配：

- `init-fixture --directory <new absolute path>`：先核ROOT登记的新owned DB、当前实际owner、精确0024/PG17.11/vector0.8.7；纯生成并验证content后owner事务登记fixture。无现存目录覆盖、无未知符号链接；目录0600文件/0700目录，逐级no-follow。
- `grant-runtime`：独立显式调用新grant_v4_runtime，旧grant-runtime语义不变；只新十表/受限函数；旧database.py不修改。
- `verify-fixture`：只读核库中canonical/hash/count/ref，不创建tenant/Graph；可交QA。
- `gc --tenant <UUID>`：明确owner、DB时钟及retain_until、reserved新域、无旧业务依赖后按专项SQL计划清该tenant新V4行，绝不全表TRUNCATE；不是自动后台清理。

fixture导出采用全新临时目录，写manifest/content、安全config指引后逐文件fsync，最终 `MANIFEST.json`索引以原子rename发布并fsync目录。rename不覆盖已存在目标；不把普通Path.rename的覆写行为误称独占。可用同一filesystem下独占创建的目录及原子发布索引策略；若平台不支持no-replace，则先保留最终目录exclusive所有权，索引只在其中首次发布，不能跨任务路径复用。**DB COMMIT与文件发布不是一笔原子事务**：DB先COMMIT，后文件导出失败则保留该DB登记与未发布临时目录安全证据，状态EXPORT_INCOMPLETE，不自动重试/新建版本；重新运行先只读核同digest，用户/ROOT具体决定恢复。公开session/API不需要owner DSN或导出secret文件。

POST session的org/两shop/三persona/credentials/scopes/tenant/source assignment/session/receipt/event是同一PG事务；fixture预登记是共享不可变前置条件，不把每访客重复复制万条订单。session创建前任何DDL/owner失败没有业务tenant；runtime调用受限provision不可指向既有组织。新schema仅十张表，migrate(head)之后默认全空，seed由owner命令显式执行。

## 8. reset、保留期、幂等与并发cap3

- reset保持当前persona、原tenant/org/shops/principals与原30min绝对deadline，fixture版本/digest不变；**不修复/恢复被撤销grant**。restricted_admin reset后仍无业务shop。
- 锁顺序与SQL事务按IDENTITY_SQL_PLAN§6/7：tenant→session→sorted principals→bound→shops/grants→overlay/receipt/events；create之前另有固定容量锁。当前epoch CAS通过后，仅DELETE本tenant overlay，epoch+1、generation+1、旧bound revoke、新bound+CSRF、receipt/event同COMMIT；任何一步失败整笔不推进。
- 初始overlay为空。真实PG reset非空效果用该新域受控fixture_note作者夹具造行，不能假装已经有商品编辑/采购写接口。reset后summary四数仍8/10/12/18且source digest相同，B访客的canonical view/hash/epoch/overlay数完全不变。
- key namespace `(stable owner_session, operation, request_key)`；payload_digest覆盖固定method/path+全部body（含原expected_epoch/generation/persona/fixture_version）。同key异文409；原key回读不含旧业务payload；旧CSRF并发失败不能触发第二effect。
- tombstone/control receipt/event/mapping最短保存至**原session expires+24小时**；reset不延长。bootstrap owner行因session FK可保留相同期限，但它的恢复权限仍只有最初300秒、精确一个createkey。普通reset不删receipt/event；GC不能把UNKNOWN变回未提交。
- cap3按DB now下active tenant+session且未revoke统计；第4/5访客429，不踢旧session；已commit但cookie未收到的tenant仍占位，到期才释放。expired行未物理清理不占cap，仍保留tombstone。限流5访客测试与3active并发测试分开，不用首3成功掩盖第4/5被其他限制拦截的原因。
- GET bootstrap只复用未绑定create_request_key的有效匿名owner；已绑定者（consumed或未consumed）保留原行/原key恢复权，用户明确重新开始GET时签发新owner，不清空旧key。UNKNOWN不自动执行该分支；active仍拒绝新bootstrap。
- create的首次bootstrap-key reservation与rate attempt可独立已提交；它们不证明session创建。COMMIT前故障后GET原key可能UNKNOWN，不以缺tenant/缺receipt伪造ROLLED_BACK。
- 创建POST始终bootstrap-only：只接受有效原bootstrap+CSRF+原key，active cookie不得再次POST创建。create丢body但cookie应用：GET current核creation_request_key→GET operations查唯一receipt。整header/cookie丢：仍持bootstrap、精确原key且<=300s仅回最小COMMITTED/OWNER_RECOVERY_REQUIRED，不新发bearer；用户明确重新开始才新空间，旧space不是回滚。bootstrap过期后UNKNOWN，不自动重POST。
- reset/persona保留公开cookie，故丢ACK仍可用当前token只读GETcurrent+原控制回执；logout撤销后无恢复特权，current401不等于原logout可证明COMMITTED。

## 9. 可独审的seed验证清单（计划，NOT_RUN）

1. 纯生成器同seed/version两次字节相等，异fixture版本/内容同key冲突；Decimal/时区/关系/数组counts及六refs完整验证。不得在此设计文件预写pass或实际digest。
2. actual PG初始化fixture后原生hash与Python相等；migrate本身十表全空；owner重复seed同digest不增行，不同digest拒绝且原字节不变；runtime不可覆写fixture。
3. 两visitor各一新org/两独立shops/三principals；实际scope0/1/2店按表返回，跨tenant ref/跨shop relation拒绝；无所谓前端role替后端。
4. provision每步故障全rollback：无孤立组织/credential/tenant/session；保留独立匿名key reservation/rate事实而不混成成功；数据库成功但文件失败独立EXPORT_INCOMPLETE。
5. 同tenant两并发reset旧CAS/CSRF只有一次epoch+1；原key回读唯一receipt；异文409；current后再同key同payload无再次推进。与owner撤权/读/fixture-note写竞争线性化。
6. reset清该tenant非空overlay，保留原persona/期限/版本；旧bound actor_guard401，旧CSRF拒绝，admin仍空shops；另一tenant完整digest不变。
7. 5visitor竞争cap3及丢cookie占位、到期count释放、rate20/10窗口、bootstrapcap128；真实recorded拒绝原因与Retry-After，不伪造容量测量。
8. credential/current identity完整负例、改名bearer对/api/v1拒绝与秘密不泄露；完整旧M3/PG/G1G2/Web/N01不由seed局部通过代签。新增tests/v4节点纳入当前实际collect，普通PG模块命令300s不预放宽。
9. 六fixture refs只验证关系和hint，不调用采购/审批/客服/营销/Graph。报告实际external call=0、provider/embedding/飞书/Woo0，不把mode标签当真实调用。
10. retention前owner GC拒绝、runtime任何时间GC拒绝、到期后只清指定新tenant域且旧base登记安全保留；无旧卷/历史数据操作。

本次没有运行上述检查，也未启用实际资源。设计普通提交后交专项独审；ROOT下一次具体准入后再写代码与申请新owned PG窗口，完成V40-03→04，至V4-0本地Gate停止。
