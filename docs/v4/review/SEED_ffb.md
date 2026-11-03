# V4纯DTO/seed组件独立审查

日期：2026-11-03（Asia/Taipei）。**结论：P2_REQUIRED_CHANGE，0 P1 / 1 P2；暂不签ACCEPT_PURE_COMPONENT。** 仅引用校验存在一项具体缺口；不要求本切片提前实现SQL、HTTP或授权。

## 精确范围

- candidate：`ffb07ec16374a1565df3a4833ed899a275f77b6d`。
- tree：`e4db26e43b1462833da6c36096e077c89a2ea8f0`。
- parent：`c4c48401494b00308cc5a2022e4a8fcb0e3f8195`。
- 五个新增文件：application/v4_demo的`__init__.py`、`contracts.py`、`seed_contract.py`，tests/v4的`__init__.py`、`test_demo_seed_contract.py`。无SQL/HTTP/迁移/旧测试修改。

全部通过精确git show只读，未读取作者后续WIP、未运行模块/测试/生成器或服务。另核既有canonical_bytes/facts_hash入口，未改共享代码。本文代码行号均绑定候选SHA。

## SEED-01 [P2] variant_ref不参与商品/店铺引用完整性检查

位置：`backend/src/commerceops/application/v4_demo/seed_contract.py:119–128`（SKU.variant_ref）、`:355–375`（ShopFixture.relationships）、`:655–665`（生成器正确的variant构造）。

TemplateRef字段会通过当前shop catalog校验，stock_pool_ref也按SKU UUID重算，但variant_ref只是UUID|null，没有任何归属/确定性检查。静态可推导：在合法生成content中把店A SKU00.variant_ref替换为店B SKU00的variant UUID，或任意UUID，FixtureContent.model_validate_json仍没有拒绝它的谓词。shop/catalog校验只处理TemplateRef，其他关系/金额/六场景校验均不读variant_ref。将SKU00的product_ref换为同店别的合法product，也不会验证该variant是否仍属于目标商品。

这违反已准SEED_SPEC:53“variant编号只在该product内有义”和:71错误引用拒绝的要求。生成器本身构造正确，缺口在作为反序列化/持久化前验证入口的内容模型；不是现有外部数据已经进入系统的证据。

最小修正：对冻结SKU00–03核variant_ref等于由其固定product_ref及SKU序号确定的uuid5，SKU04–09按冻结设计为null；同时核固定SKU→product映射或至少确保variant生成与当前合法product一致，避免跨商品拼接。可采用简明独立关系校验，不需新增variant表/状态机。

回归应直接修改content的variant_ref为跨店、同店其他商品、随机UUID及不允许的null/非null，调用FixtureContent校验并拒绝，而不只依靠旧manifest hash不同。现test_cross_shop_wrong_kind_duplicate_and_missing_links_rejected:213–241不含variant；黄金输出hash只锁正常生成字节，不能证明输入引用守卫拒绝上述变化。修正后以精确commit增量复核。

## DTO与冻结接口静态对照

`contracts.py:33–40`统一strict/frozen/extra=forbid、hide_input_in_errors和revalidate_instances；Context:66–73全部身份/代际与aware时间必填，生成响应的ContextEnvelope强制context。FailureEnvelope:203–208允许server_time=None而无业务data；Error.retryable有before validator拒绝0冒false。SessionData:114–126可0–2店且shop ID唯一，Shop grants重复拒绝，admin不被模型强制赋两店。

CreateSessionInput无role/tenant/principal字段；PersonaInput以三persona literal收窄自由字符串，与已准预登记allowlist方向一致。UUID、Counter非负严格整数、Digest及currency格式约束保持；Timestamp将aware时区规范UTC，不代表模型自己生成了可信DB时间，真实DB来源由后续service保证。

匿名BootstrapEnvelope、最小OperationEnvelope与敏感ContextEnvelope分开；BootstrapOperation只含operation/key/status/recovery，并约束COMMITTED→OWNER_RECOVERY_REQUIRED、UNKNOWN→WAIT_READ_ONLY，无token/tenant/shop字段。控制Receipt/Context的请求key、tenant归属、当前角色与epoch相容仍属后续服务端事务职责，DTO不会单独授权。

测试:362–402只比较properties/required/extra，不是完整JSON Schema等价或真实Ajv交叉验证；源码字段/格式已人工核读，不能把该测试名提升成已跑的全接口合同验证。实际生成OpenAPI/客户端及HTTP边界须在后续Gate核对，不为此重复修改A原件。

## 固定生成与业务语义

- seed_contract:25–63固定版本、独立Random seed、日期锚/namespace/店铺参数；generate_seed:803–811不接tenant/凭据/当前时钟。只quote lead_days用局部PRNG，未污染全局Random。ZoneInfo用于固定日期与固定时区，不使用浏览器今天。
- ShopFixture:272–284精确约束每店8产品/10SKU/12订单/18行及其他数组数量；_shop:650–800按冻结SKU/product、订单分配、数量/价格、日期公式生成，店间UUIDv5 namespace输入含shop，实体目录按kind+ordinal去重。
- 金额使用规范字符串与整数生成，关系校验采用局部Decimal精度50；80%/20%退款在当前固定整数价格/数量下可整除（所有价格为10的倍数），没有本切片实际舍入损失。将来生成规则变化不能继续假定整除，须版本/独审，不需本轮引入新算法。
- cost/inbound/退款数量与restocked保持None及对应UNKNOWN reason；order11 paid_at未知不误称未付款。不同currency强制与各店一致、不跨店合计、不凭报价推真实成本。
- SKU池UUID按SKU来源重算；订单/客户/行/refund/quote/support/campaign引用逐域检查。六scenario refs只指向fixture，不产生采购/审批/客服/营销workflow；stockout/滞销/退款比例及相关对象关系有独立语义断言。SEED-01是此引用覆盖的剩余缺口。
- 知识正文限定两条自创合成文本并核hash，客户/商品/供应商名限定合成模式，无手机号/email/地址字段；源码无网络、PG、外部模型或业务runtime依赖。模式标签只是合成状态，不当作真实调用证据。

## canonical与测试证据边界

`_manifest:559–578`按内容生成摘要及按kind/key排序实体hash；SeedBundle:585–593重验证content和manifest后输出既有canonical_bytes。既有commerce_values.canonical_bytes:122–125为sort_keys/compact UTF-8/allow_nan=False，facts_hash:128–129计算SHA256。manifest不把source commit混入跨tenant内容hash，符合设计。

测试包含固定独立常量GOLDEN_CONTENT_DIGEST与60412字节、两次生成一致、打乱字典键顺序、global PRNG/Decimal context隔离、精确counts/未知值/时间金额/跨店/错kind/额外权限字段/实例绕过/错误manifest等负例；不只是“调用生成器再与自己比较”。不过_scenarios与内容期望共享helper以及_manifest重算本质上不能替代语义断言，已据此检查variant漏项。

本轮未执行测试或生成器，黄金hash只是测试里已有预期值，不称Reviewer测得实际fixture digest。无作者运行日志作为本轮独立证据。SQL/HTTP/API_PG/Web/身份真实授权、同版本入库冲突与实际持久化不可变Gate均NOT_RUN/待后续源码，纯组件结果不能代签这些层次。

## 交接

作者仅修SEED-01并补独立引用负例后交精确SHA，无需重做整份设计或扩迁移。原SQL设计准入仍按c4回执保持；此项只影响纯seed内容验证接受，不重新打开已关闭IDPLAN-01。Reviewer不改实现/测试，当前只提交本报告。
