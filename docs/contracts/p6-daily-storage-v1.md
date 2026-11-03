# M3 S2 日报来源、三表持久化与详情读取提案 v1

状态：**PROPOSED / REVIEW_REQUIRED**，2026-11-03（台北）。精确设计基线为 Backend
`e073e1bcf8978740c8d5363b71b78ed55befcac5`；S1候选独审结果由 Root 另行核收。
S1 display修复已独立提交 `e47a2e3f3b60a361b930962860429444889055c8`，须由Root另核收复审。
本轮只交付本设计和 [strict 日报详情 schema](p6-daily-read-v1.schema.json)，不是迁移或服务实施。
[总合同](p6-m3-v1.md)的指标/异常和身份约束继续；本文将其S2收窄为实际三个消费者所需的三表：
来源解析读 binding、Worker写 snapshot/report、Web读已完成事实。调度、推送、追问不在本迁移建表。

## 1. 来源注册与当前店铺绑定

拟新增 `business.p6_daily_source_bindings`，schema `p6-daily-binding-v1`；owner-only登记，runtime只读。
每条不可变记录含 id、organization_id/shop_id、config_ref、source_config_version、canonical_projection、
projection(jsonb)、config_digest、created_at；复合唯一 `(organization_id,shop_id,id)`、
`(organization_id,shop_id,config_ref)`、`(organization_id,shop_id,source_config_version)`。
config_digest 为 SHA256 UTF-8 canonical_projection；投影JSON与文本须等值，严格精确key集合及版本。

投影字段固定：org/shop、config_ref/version、adapter_kind、environment、external_shop_key、timezone、currency、
coverage_profile=`closed_test_manifest_v1`或`complete_fixture_v1`、manifest_ref/digest、earliest_business_day、
metric_version、status_mapping_version、limits，以及 Woo 分支的 origin、不可变 key/secret/CA 引用、private_pin_ref；
Mock分支为固定fixture_ref/digest，不接受Woo字段。类型/边界由strict分支DTO和SQL key/type checks共同核验。
source投影映射到S1 `DailySource`：source_binding_id=id，config_digest=登记digest，source_kind取adapter_kind；
Woo fixture_version=null，Mock fixture_version为版本化fixture。S1字段/指标不改名，不改旧commerce-v1。

当前性由 **shops.config_ref** 的owner版本指针及部署私有映射双重约束：
只解析同org/shop且config_ref与shops相等的唯一登记；实际部署映射还须指向该id/version/digest。
version-specific config_ref 每次轮换新值，禁止同ref多版本；owner原子登记新绑定并切换新owned shop指针。
运行时不能登记、更新或修复指针。不得修改旧M2店铺、记录、配置或秘密来获得日报资格。
新Woo店铺仅test、HTTPS loopback、精确外部店铺键/币种/时区匹配；Mock仅mock/test环境。

可信本地配置通过独立新部署入口显式注入（不自动复用P3旧配置或读.env）；
新私有目录0700/文件0600、同UID、非symlink、同FD有界读取，沿用 `WooFilePins` 的同字节使用/核验。
私有pin文件digest锚由本次可信部署配置提供，pin内秘密hash不进入DB/公开DTO/日志；
登记digest只覆盖非秘密引用/限额/策略，实际配置同版本内容变化拒绝。
解析元数据与权限成功后，factory才允许读本次key/CA；私有配置缺失不fallback Mock。
capability检查不读取秘密或访问Woo。API创建、Worker采集前/提交前分别核当前版本；
切换发生后旧任务needs_attention，不偷偷用新版本重采。历史报告读取校验原登记而不要求其仍为当前。

## 2. 采集算法、金额映射与覆盖证据

官方只读核对依据为 [Woo v3 Orders](https://woocommerce.github.io/woocommerce-rest-api-docs/#list-all-orders)
与 [Order refunds](https://woocommerce.github.io/woocommerce-rest-api-docs/#order-refunds)：
订单接口列出分页、status（含any/trash）、创建/修改日期过滤；订单含支付GMT时间，退款有发生GMT时间。
这些说明不提供严格快照或“所有历史数据均可见”的保证。本片**不依赖支付日服务器过滤**，
不采用较新全局refund端点，不由接口存在推断目标版本兼容；目标店路由/字段/状态行为仍待实际只读Gate。

拟新增窄 `DailyWooCollector`，直接使用现有 `WooHTTP` 的固定GET端点与 `scan/revalidate`，
不调用库存 `list_order_lines(window)`，不查询产品/库存，不新建通用同步仓库：

1. 冻结可信DB now、业务日和S1 window；分配task创建时已持久的snapshot UUID。
2. `scan("orders", {status:"any", dp:6})` 与独立 `status:"trash"` 全页读取，无after/before/product过滤。
   两查询可能重叠：跨查询同ID只允许规范源记录完全相同，确定性合并；单查询分页重复仍拒绝。
   未识别插件状态、权限导致缺对象或trash查询不可用，不声称全店完整。
3. 对合并后**全部**订单（含零行/很早创建/未支付订单），逐一 `scan("orders/{id}/refunds", {dp:6})`。
   退款时间不预裁剪；只在S1按occurred_at筛业务日。订单头refund引用集合与实际退款ID集合逐单匹配。
4. 所有原查询结束前 `revalidate()` 再读；保持原双扫描+末重读机制，任何变化、漏页、重复/计数冲突拒绝完整性。
5. 同一总截止内完成DTO映射/实体核验与S1聚合，才交store；关闭HTTP client。保存来源/采集起止与安全统计，
   不保存客户资料、响应body、headers、完整请求URL或秘密。

映射固定：order `date_created_gmt/date_paid_gmt`→S1创建/支付时间（null支付不由状态推断）；
`line_items.id/quantity/total/total_tax`→原商品行；`shipping_total/shipping_tax`→订单运费两项；
`fee_lines.total/total_tax`分别精确求和→费用两项；`order.total`→订单总额。
不重复减discount_total，先逐单六项对账；不存在fee_lines字段不是零，显式空数组才为零。
请求dp=6防止默认输出精度隐藏源小数；是否实际保留六位要用独立本地样本核对，不能仅凭参数宣称。
退款amount转非负，禁止再拿负总额扣支付；发生时间取date_created_gmt。
daily-status-v1在来源mapper明确：pending/on-hold/failed/trash若paid_at非null，标
`PAYMENT_STATUS_CONFLICT`使日报不完整；processing/completed/cancelled/refunded有合法paid_at才计支付，
paid_at缺失不补造，completed_at不代替。S1纯函数目前只消费显式quality标志，不自动检测这些状态冲突；
S2必须补四个冲突状态及取消/退款保留已记录支付的mapping测试。
退款行quantity仅在已验证原order-line关联和规范整数时记已知，否则保留unknown reason；
不从金额推数量，不从write-only restock选项推读到的已回库事实。无法证明restocked则null。
所有平台字段转换先脱离原响应，再经S1完整严格校验；不能丢弃坏行制造可用报告。

### 覆盖声明必须有独立锚

现有分页成功只证明当前凭据看见的集合；不能发现彻底删除、权限隐藏或插件排除的订单/退款。
因此第一片Woo完整报告**仅准入全新本地合成、已知封闭数据集**：
owner独立冻结manifest，列出全店订单ID/每单退款ID及业务日期范围、来源版本和无并发写前提，
正文及digest绑定本次注册。manifest不得由本次GET输出反向生成；正向金标另由独立样本给出。
scan合并ID与manifest全量精确比较，不能只验证expected是actual子集；退款逐单同样比较。
新增/缺失/永久删除任一对象、manifest过期或无法核封闭前提，标 `COVERAGE_UNPROVEN`，完整指标不可用。
Mock同样绑定显式完整fixture manifest。本地合成证据只证明该数据集，不外推商业店历史完整性。
没有manifest/可信源审计锚的普通Woo来源保持creation_enabled=false；不以用户口头“应该没删单”豁免。

安全receipt单独保存：query_profile_version、manifest_digest、expected/observed order/refund集合digest与计数、
每端点分页计数/两扫描及末重读一致性、HTTP status计数、请求数/字节数/耗时和fixed failure_code。
receipt不包含凭据、文件路径、body、自由错误文本；其canonical文本/digest纳入snapshot封存。
S1 `DailyCoverage`三个complete布尔只能由上述实际观察与manifest比较生成，不由API/LLM或runtime手工标真。
DTO的counter匹配不是外部覆盖证明；store校验receipt/profile/source/dataset绑定和S1声明一致。
若传输失败/数据非法以致不能构造合法S1输入，不造空订单snapshot；task failed+安全audit诊断即可。
已有合法但不完整的S1输入可封存质量报告，metrics=null；不把二者混记成正常零日。

### 限额与有界退出

保留现 transport GET白名单、固定原点、TLS CA、trust_env=false、禁重定向/跨源Link及URL认证，
复用 `WooDeadlineTransport` 同步I/O截止。新元数据limits显式给出且不扩大M2受限profile：
per_page≤100、max_pages≤32、max_requests≤256、单响应≤2MiB、单请求timeout≤10s、max_retries=0；
从factory解析/PG绑定起至全部HTTP/复核/映射结束共≤18s，并与外层绝对deadline取min。
另限全店orders≤1000、lines≤10000、refunds≤10000、封存canonical输入+receipt≤8MiB；
达到任一上限立即CAPACITY_LIMIT，不截断后标完整。多请求字节量上界由请求数×单响应上限保证，
本轮不宣称有现transport尚未实现的独立总字节实时闸门；计数receipt如实记录。
余量不足、401/403、TLS/分页/解析失败不延期；store事务另有显式短statement/lock timeout，
不得让同步线程或DB取消后的后台进程继续采集。具体owned服务/PG UTC窗口仍由Root另释放。

## 3. 三表 DDL/ACL 合同（拟下一空闲迁移，编号由Root定）

不修改0002/0018、旧FK/触发器/权限/590PG Gate，不新增schedule/delivery/question表。
来源表如§1；其余两表所有字段NOT NULL，除明确optional的错误信息外不靠null绕过约束。

| 表 | 必要列和约束 |
|---|---|
| `p6_daily_snapshots` | id/org/shop/task/source_binding_id；request_content/hash；schema_version=p6-daily-snapshot-v1；business_day、timezone、currency、window_start/end、collection_started_at/collected_at；complete；content/jsonb+canonical_content+content_hash；receipt/jsonb+canonical_receipt+receipt_hash；created_at |
| `p6_daily_reports` | id/org/shop/task/snapshot_id/source_binding_id；schema_version=p6-daily-report-v1、metric_version=daily-metrics-v1；report/jsonb+canonical_report+report_hash；canonical_facts+facts_hash；complete；created_at |

两表分别 `UNIQUE(task_id)`、`UNIQUE(org,shop,task,id)`；snapshot额外唯一
`(org,shop,task,id,source_binding_id)`，report用此五列复合FK绑定snapshot；
snapshot的 `(org,shop,task)` FK指business_tasks，`(org,shop,source_binding_id)` FK指来源表。
UUID域不复用旧snapshot/report ID；task预分配snapshot_id，store分配report_id并以task唯一回执重放。
只提供canonical JSON，不同时建行子表；订单/退款关联由S1验证，SQL不假装JSON数组具备FK。

SQL CHECK 必须逐个验证：canonical text可解析且等于JSON；所有hash为精确64hex并等于
`encode(sha256(convert_to(text,'UTF8')),'hex')`；schema/版本及org/shop/task/source与列完全一致；
JSON必需key存在且type正确（用`IS TRUE`关闭SQL NULL漏洞），window有序、采集起止在闭日后；
snapshot内snapshot_id=id、S1 source binding/version/digest/币种/时区等于登记与task；
report.snapshot_id/content_hash与snapshot同一行相等，source/window/coverage/rules与snapshot相等。
report的facts投影恰为S1 `canonical_facts()`：report JSON移除 `facts_hash/display`，
与canonical_facts::jsonb精确相等，内层facts_hash=列facts_hash；完整指标/null和quality finding关系须严格匹配。
完整store写入前还要重新validate S1输入、aggregate_daily，并精确比较计算report；
读取时重新核hash/DTO/源谱系，hash不是授权或业务正确性的替代品。
canonical_report使用S1序列化，report_hash覆盖display；facts_hash仍排除display，二者不得混用。

INSERT trigger绑定 `kind=daily_report / workflow_version=p6-daily-report-v1`、
`state=analyzing` 和当前job owner/running回执；封存后拒绝后加/换snapshot/report。
UPDATE/DELETE/TRUNCATE对三表均禁止（用新日报函数，不复用语义专属库存trigger名称）。
服务角色授权矩阵：来源表仅SELECT；snapshot/report仅SELECT+INSERT；三表无UPDATE/DELETE/TRUNCATE/REFERENCES/登记执行权。
PUBLIC全部REVOKE；新增任何SECURITY DEFINER函数固定search_path、REVOKE PUBLIC、最少参数与明确runtime EXECUTE，
不得接受SQL片段或变为任意登记入口。沿用原tasks/jobs/audit权限，不为日报扩大旧表列级更新范围。
DDL实际SQL、role/grant负例和升级旧态字节验证须先精确独审再由Root释放owned PG，本文不声称已通过。

## 4. 原任务/队列接线与提交恢复

**已核兼容约束**：0018 `p5_task_binding_guard`对所有带顶层source_binding_id的task执行M2注册核验。
日报normalized_request采用独立键 `daily_source`（S1 DailySource完整对象），
禁止顶层 `source_binding_id/source_mode` 及旧 `request.parameters.source_mode` 路径；旧trigger因此原样执行而不误绑M2。
新 `p6_daily_task_guard`只处理kind=daily_report，严格顶层key集合、版本及nested source、scope、业务日、规则验证；
旧任务若携带daily_source拒绝，日报若试图改kind伪装旧任务拒绝。来源元数据专用DTO与taskguard不会跨表跳过旧约束。

normalized_request固定：schema_version=p6-daily-task-v1、daily_source、business_day、snapshot_id、rules、
request_key(UUID)、request_hash、conversation_id、requester_auth_version；client不提供这些server绑定字段。
request_hash覆盖规范client原始shop/date（省略固定记null）/请求source-version与服务端规则版本；
实际解析后的日期/来源另作为不可变server绑定保存，默认日期在第一次受理时解析并持久化；
同key重试先读原记录，不能隔日把省略日期重解析后误报冲突或新建。显式不同正文409。
新增仅daily kind的partial unique index `(organization_id,requester_id,(normalized_request->>'request_key'))`，
实现同actor/endpoint跨店铺键冲突，不把shop放进unique从而允许同key跨店铺另建任务。

T1：当前session/CSRF/Origin+operator/shop及登记解析 → 锁定权限 → 同txn保存task +原analyze job +audit，
job dedupe=`p6-daily:{task_id}:analyze`、payload_ref固定任务引用；不创建审批/plan/执行/outbox。
身份不能只用旧 `lock_inventory_permission`（它允许的来源不等于日报绑定），新增窄daily授权函数/用例，
检查enabled principal/current auth、显式operator角色+shop grant/scope、shop/source匹配并锁定相关行。
API session过期后不得读写；Worker用原受理owner持久身份重新核当前auth/grants，不把checkpoint当授权。

同原单Worker注册日报runner、原analyze/recover job；已有串行槽/终止确认/旧版本runner保持。
提交：先同task锁内查回执；无回执且原owner/版本/权限仍有效 → 同事务写snapshot、report、task终态和audit。
完整报告task completed；合法质量诊断task needs_attention+DAILY_SOURCE_INCOMPLETE，不混成完成零日。
没有合法S1输入的源失败为failed且report=null，安全失败audit不含平台原文。
提交后ACK/checkpoint丢失直接读原report并核hash返回，不能重采覆盖；事务前失败可按原有界job策略另次采集，
未提交的snapshot UUID保持不变。权限/绑定变化为终止待处理，不做网络重试；未知旧Worker按原确认Gate停住。
GET历史只查当前owner operator+shop权限并读取已封存证据，配置轮换不重算历史、不修复原once。

## 5. 最小详情读取 DTO 资产提案

本片先定 `GET /api/v1/daily-reports/{task_id}`，无列表、创建UI或追问HTTP端点。
[JSON Schema](p6-daily-read-v1.schema.json)为Draft2020-12 strict资产提案，所有对象additionalProperties=false；
outer schema_version=p3-web-v1 / identity_mode=session / server_time / trace_id保持当前session envelope，
内层daily.schema_version=p6-m3-web-v1；task.kind/daily workflow固定，不复用inventory DTO。
state为queued/analyzing/completed/failed/needs_attention；report=null表示尚无合法封存报告。
report存在时显示report_id/snapshot_id/content_hash/facts_hash、日期/窗口/来源公开投影、coverage.complete及flags、
metrics/findings/display和证据条数。公开source只含kind/version/fixture_version/currency/timezone；
不返回origin、私有引用/路径、source binding投影或所有订单证据；显示受控数据集限制。

schema组合明确：queued/analyzing→report=null/failure_code=null；completed→完整report且metrics非null；
failed→report=null/固定failure_code；needs_attention→failure_code非null，可无report或有不完整质量report。
DTO/S1模型负责额外跨字段公式/hash，不能单凭JSON Schema声称验证金额正确。
GET无model/commerce调用、无task/job写入、无静默重新登录；401缺身份、403撤权/CSRF，
404跨org/shop/owner或不存在，503存储/谱系校验不可用，固定safe_message不吐SQL/原文。
错误schema同asset `$defs/ErrorEnvelope`，不存在“HTTP200但含error”兼容分支。
Web仅在Root独审核收此asset后消费；schema提交不代表端点存在。
四类追问enum仅作为后续type声明 `metric_definition/metric_evidence/finding_reason/data_quality`，
`question_creation_enabled=false`；本片不建question表、不创建伪答案或假可点击控件。
调度/投递能力同样false，不以尚无delivery记录显示sent。

## 6. 分段释放与验证

S2a：本文+schema精确独审；S1发现由原owner按Root指令修正，不绕开其DTO。
S2b：获批后写三表迁移/ACL、注册元数据/纯来源mapper、store与runner及详情只读接线；
先静态/纯FakeTransport，再按Root明确owned PG窗口验证，不在本设计轮执行。
源profile/manifest核验、DB触发器、store三层都必须有拒绝例，保留原M2/590PG及全Gate，不删失败求绿。
最低矩阵：source版本/配置/ref/pin漂移、旧M2保护未变、runtime登记/改证据/跨租户FK被拒、缺字段和JSON null攻击、
hash/事实/显示改写、事务回滚/提交后断线/新进程重放、撤权竞态/换绑定、页重复/漏页/总数变、隐藏/删除对象、
空全集与传输失败区分、18秒慢响应/不合作退出、早建今付/历史退款/无行/六项金额映射/精度/跨时区金标。
owned PG、真实HTTP服务、真实模型、发送、Web E2E、Hosted、迁移升级及完整CI均NOT_RUN。
真实业务资产和旧秘密无访问；未修改生产代码/迁移/锁/CI/frontend/Harness。本文不签S2实现或M3完成。

用户最新依赖裁定：SOP未准备、真实模型/embedding预算稍后、暂不实际推送；
此设计只接新owned合成来源，模型和实际发送保持关闭，不继承旧Secret/群窗口。

设计资产检查：Markdown 120文件/0错误，新增两文件敏感内容扫描native exit 0/no leaks，
Git差异空白通过。首轮schema结构检查要求全部声明属性必填，发现共享DTO默认字段未在required中，
实际AssertionError；已将所有对象属性列为required（可空字段仍须显式null），随后结构检查15defs/16strict objects/
全部local refs存在/金额仅string通过。该检查不是完整JSON Schema引擎或API运行验证，二者NOT_RUN。
