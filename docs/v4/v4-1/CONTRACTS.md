# V4-1 增量实施合同

Root 冻结版本：V41-1e（独立调用能力与Demo绑定不可变候选）。依据用户完整阶段授权、已批准四合同、API_PLAN / WEB_PLAN / QA_PLAN / REVIEW_PLAN / GATE_PLAN 及 UI_SLICE_01。旧四合同原文和权限 CSV 的归一化回执保留。本文件是本阶段可实施的增量；具体 SQL、DTO 和生成 schema 的代码需精确提交独审，运行证据仍待实测。

## 1. 已有与新增

V4-0 认证、两店 fixture、四种控制 receipt、旧 overlay 窄权限、M3 单 Worker/Graph 及旧路由是已有能力。V41 不扩旧控制操作枚举、不假装已有 overlay 可业务写。新增经营/商品/订单/导入数据域、六张窄业务表、一张窄安全 policy 表及新 API，均只在演示租户生效，外部 Woo/飞书/模型/embedding 调用为零。完整范围为 V41-01—06；V4-2 不启动。

## 2. 领域、权限与事务

采纳 API_PLAN 六表：v41_product_tags、v41_order_fulfillments、v41_import_jobs、v41_import_products、v41_action_receipts、v41_action_events；版本串行 0024→0025，不修改旧迁移。tenant/shop/owner-session/receipt 的复合关联，来源不可变、版本/状态/金额/效果数约束以及低权固定 apply 函数由唯一 API owner实现，必须 SQL 独审后才准入真实 PG。不能仅靠 Python 检查而让低权直写或直调绕过。

新增第七张 singleton business.v41_security_policy，只存当前 active key_version、可信 config_fingerprint、单调 policy_generation 和 DB activated_at。仅 owner/migration 初始化或原子轮换可写，PUBLIC/app 无 DML；未激活缺行、配置 fingerprint 不一致及同 key_version 换 secret 必须拒绝，调用者传入的 expected key 不是权威。Python V41 guard 与 SQL actor 都核 DB 已激活 policy，磁盘更换配置不等于激活。owner 初始化在 API 启动前完成；轮换先以稳定顺序锁所有 owned demo tenant/session，再更新 policy 并永久撤销旧 demo bound sessions，同事务，不能修改旧 M3 非 demo 身份。actor 读取 policy 的共享锁保持到提交，credential/identity/principal/permission 参与路径必须提供统一锁图与真实并发证明，不能以单独重复 SELECT 代替线性化。owner GC 不删除 singleton，current-head 精确新增集合改为七表；迁移后初始无 policy，owner 激活后恰一行，原固定历史升级段不改。此增量关闭方案层 S01，实际 SQL、低权拒绝、旧会话两行同 key 而 policy 已切换及并发轮换/撤权仍待独审与真实测试。

完整沿用当前 DemoSessions.resolve_locked、旧 bound WebSession 及 credential/identity/principal/auth_version/current grant核验。新 business API 不能靠 URL 前缀默认受旧 demo middleware 保护，需显式安全边界。单店 read/export/read-context 允许当前 operator 或 approver grant，tags/fulfillment/import 要当前 operator；restricted_admin 无默认业务读写。所有对象、cursor、job、receipt均先 current shop/tenant 归属和权限，不把 UUID 当凭据。客户端不得提供 role/tenant/principal/auth_version/server_time 权威字段。

统一锁顺序为 tenant/session→身份/权限→稳定顺序资源/作业；实际 SQL 锁顺序与撤权路径逐项给审。身份/CSRF/epoch-generation/当前权限先核，原 key 同文已提交回执在业务 revision/resource CAS 之前查；仅新效果检查 expected_data_revision 与 expected_version，避免自身第一次推进版本导致同文重放失败。异文409、旧 epoch/gen/撤权/TTL先拒；effect/receipt/event同事务，提交前/deferred guard再核 DB TTL和当前权力。未知提交只读原 key，缺回执不推断回滚，不自动换key重发。

reset继续原控制事务推进 epoch；V41所有读写、preview和receipt业务展示强制当前 epoch，旧效果立即不可见，保留证据到安全retention。owner GC先准确清V41子表再旧tenant清理，不全表TRUNCATE，不改旧去重记录。精确释放 API owner 修改v4_demo_seed.py的require_owner为明确0024/0025 allowlist及V41子表GC接点；其余身份/owner/fixture/hash/环境校验不变。旧M3当前head表集合期望只有新迁移代码独审后才窄释放，历史固定迁移段不可改。

## 3. 有效数据、KPI与版本

所有 KPI/列表/详情/钻取/导出/read-context 使用同一验证fixture和当前tenant/shop/epoch覆盖及已确认导入的有效视图。每次读取同一tenant锁下完成，不能多SQL混入另一次写；业务data_revision独立于身份auth_generation，包含fixture/epoch/有序有效效果。分页绑定filter/sort/revision/snapshot及稳定UUID tie-breaker；新数据或筛选不符要明确冲突/重读，不混页。

单店币种取server shop设置（TWD或CNY），不换汇、不跨币种合计；Decimal权威运算和字符串wire，不用JS浮点求和。按店铺IANA时区解释from_date/to_date半开区间，默认fixture锚定最近7完整自然日，允许14日或显式≤90日，超出14日来源窗口标质量不足。固定snapshot与DB read_at分开，不展示为实时外部同步。

计量采纳API_PLAN：created_count按created_at；paid_count/amount按已知paid_at与订单net_amount；refund_event按occurred_at的独立事件/amount；average_paid为已知paid小计/已知count，零分母null。缺支付日标PARTIAL及unknown/excluded数量；源窗口不完整或不可定义时value=null、known_value保留已知小计和reason。退款网关/退款数量/回库未知，禁止称到账退款/净收款/退款件数或库存回补。缺成本不出毛利，无可比期不造增长率。趋势/排行/异常均能定位同源明细；规则版本/阈值明示，规则不称真实AI。导入只增商品，不生成销量或已知库存。

## 4. HTTP与只读来源

采纳API_PLAN新路由：GET dashboard、dashboard/drilldown、products、products/{UUID}、orders、orders/{UUID}、products/export、orders/export、read-context；POST products/{UUID}/tags、orders/{UUID}/fulfillment、imports/previews、imports/{UUID}/confirm；GET imports/{UUID}、actions/{operation}/{request_key}。静态export/import等保留字优先于UUID。独立strict V41 DTO/schema_version v4-business-v1；共享Context字段、no-store及错误语义继承，不放宽V4-0 schema。业务 GET 带X-Demo-Epoch/Generation，POST强Origin+CSRF。新增受保护只读 preview恢复路径见下节。

分页默认20/max100，q≤80，cursor≤2KiB，排序固定枚举+唯一键，金额按Decimal排序；export上限500行，超限拒绝不静默截断。冻结export为严格JSON ExportEnvelope（含权威context/source/revision、固定csv格式/安全文件名、csv_text、row_count），WEB核对当前上下文后才创建CSV下载Blob并及时撤URL；复用同filter/snapshot/权限，不只导当前页。CSV writer引用并防公式注入，表头/金额/源字段可追；已下载文件不承诺撤回。这样避免生CSV绕过现有严格响应/迟到边界。

来源保留fixture version/digest及baseline snapshot；上传对象有job/row/file digest与demo_upload标记，不冒充fixture原对象或外部Woo事实；混合有效数据需source明确包含fixture与upload（可用单独demo_mixed标签/来源集合），UI不能一律声称纯fixture。source label不作为权限。read-context只从白名单已授权对象出，Copilot容器仅上下文/规则解释/已开放只读跳转，模型未启用明确，不模拟对话/轨迹/工具成功。

## 5. 允许演示写

标签仅0—8项、各1—24字，去重规范化，不改原商品价格/成本；产品覆盖expected_version=0初值后严格递增。履约仅known paid_at订单的demo_unfulfilled→demo_fulfilled，状态名明确是演示，不代表真实物流，不变库存/钱/外部数据。付款未知409；同key返回原效果，异key重复状态拒绝。三业务operation为product_tags/order_fulfillment/import_confirm，独立业务receipt/审计，旧控制receipt保持四项。

## 6. CSV/XLSX与preview合同补充

仅商品导入，一行一新product+SKU，闭集sku/title/price/currency/tags，不导订单/客户/退款/库存/多变体。SKU裁剪空白后ASCII casefold比较唯一，保留展示值；与fixture/已导入一起查重，不upsert。金额严格非负十进制，最多6小数，拒bool/指数/NaN；本店currency匹配。未知成本/库存保持未知。

JSON body≤3MiB，base64严格decode后文件≤2MiB；500行、24列、单cell≤512字、title≤120；每tenant/shop/epoch最多500导入SKU。CSV只UTF8可BOM、严格逗号引号、表头不可重复/空、列宽一致、非法控制和公式样单元格拒绝，export同样防公式。XLSX受限单sheet无宏OOXML：≤32 entries，实际解压≤8MiB/单entry≤2MiB/ratio≤100；拒加密/路径穿越/符号链接/重复entry/嵌套档/宏/外链/公式（包括缓存值）/DTD实体/非允许节点/外部PI。XML在增量读取/建节点时控深度/节点/字符串/属性，不整包不受限fromstring；仅string/inline/shared string/decimal，复杂格式明确拒绝。解析硬预算2秒，必要独立子进程kill并wait证明停止；不能把async/线程取消当实际终止。

持久配额与CPU解析并发是两回事。解析前完整身份/Origin/CSRF和准入，解析不持tenant/业务行锁；同tenant最多1个在跑、全局最多2个，建议独立app连接的窄PG advisory slots跨process非阻塞准入，命名空间与旧Worker锁隔离，失败429。槽位到实际解析子进程退出/reap后才释放；后置写job前新事务再核当前权力/context/TTL。父进程异常退出、持锁连接失联或身份无法核实后，不得仅因 advisory lock 已释放而重新发放仍可能存活解析的容量。允许最小持久 fail-closed admission：未知槽位保持占用，确认实际解析已终止并完成回收前拒绝新准入；不要求新增通用自动回收框架。真实代码和低权直调、父进程/连接失联、超时强停及随后重新准入需专项实测，不能以preview行数替代并发。SQL statement 5秒/lock1秒，不为容量升原安全上限。

初次mapping可null仅发现表头/安全sample/质量，随后重传同file、mapping及parent_job_id创建不可变子版本。parent必须当前owner/tenant/shop/epoch/gen、同file digest/同链；创建子版本与supersede旧版同事务，旧版不可confirm，confirmed终态不得再扩链。每链最多5版本，每tenant最多12jobs，最多3未过期active heads；superseded/confirmed不占active，不能释放仍在跑的解析槽位。每preview10分钟且不晚于session期限。原始file不持久化，只有有界normalized rows、headers/安全sample/quality/digests，最多20sample/100错误，不回显公式或完整文件。

preview本身也owner+原preview key唯一、canonical request digest幂等；相同key同文返回同job、不重复配额，异文409。新增 GET /api/v4/imports/preview-requests/{request_key} 在当前身份/shop/epoch/gen/权限下返回最小job_ref/UNKNOWN；缺行不推断回滚，不自动换key再POST，不回原file。无需扩大旧控制或三种business receipt枚举，临时job承担自己的key约束。

preview 保存创建时 data_revision、parser/schema version 及文件/映射/normalized 摘要；confirm 的新效果必须让 preview 保存值、请求值与当前有效数据版本三方相符，数据变更须重新预览，不能只换请求 revision 确认旧预览。confirm仅job id/version/digest和预期context/revision，不信客户端rows；新事务锁tenant/session/权限/shop/job，复核未supersede/未过期/文件映射normalized摘要/所有重复/币种/总量。effect/receipt/event同事务，任一失败整批回滚；并发同SKU一胜一拒；已确认job换key也不能重复导入，同原key十次只一次。确认后SKU在列表/详情/export/商品数/read-context同源可查。import_confirm 回执的 resource_id 是 job UUID、resource_version 是不可变的 preview job.version；COMMITTED 只改变状态，不推进内容版本。before_revision 为 preview 保存的版本，after_revision 为确认后有效数据版本；商品标签/履约仍各自 old_version+1。UI 以当前授权下的已提交原回执、同 job/version/digest 的 COMMITTED 回读及 after_revision 的有效数据回读完成核对，不将产品/订单的 +1 规则套在导入 job。

## 7. 切片、所有权与Gate

API独占StageSpec所列production/schema/0025/共享api.py以及批准的v4_demo_seed.py兼容和新scripts/v41_schema.py导出器；WEB独占UI和生成的frontend/lib/v41-schema.json；QA独占独立runner/E2E，不代写shared DTO/SQL。API先纯DTO/视图/KPI/解析金标，再真实SQL/store/router候选；SQL低权/锁序 code独审后Root释放新owned运行窗。WEB先Shell再消费已审DTO schema接真实Dashboard/商品订单/导入，不用假API代签。

当前放行：纯服务/DTO/导出schema、Shell/UI、QA监督基础、以及API SQL候选编写供独审；实际PG/API/browser仍需Root精确source/UTC/资源准入。端到端Gate、原Full动态PG严格双线/G1三G2六、完整工程及旧相关回归按StageSpec，不以本文件或作者自检签完成。

## S04 独立调用能力补充（候选准入，非运行核收）

2026-11-04 Root 依据精确后端独审6208ba9增量准入：保持七表，在既有 singleton policy 增加一项32-byte owner-only invocation_verifier私有派生能力。原始配置秘密不得入表；派生须独立domain与当前key_version。runtime撤销policy表级SELECT，仅对原六项公开metadata列授列级SELECT；PUBLIC/app不得读私有列、写policy或执行私有计算helper。所有SECURITY DEFINER固定search_path，私有helper和新表默认全撤权。缺能力、长度错误、配置错配、旧版本复用一律拒绝。

V41私有binding保留旧bound-session校验并增加独立V41调用MAC，采用无歧义的规范消息绑定bound-session ID与当前policy版本。SQL必须以受保护能力独立重算，不能以app已可写的web_sessions.csrf_digest作唯一权威。浏览器、公开DTO、错误、日志和测试回执不得输出能力或私有binding。只追加调用者自证的reaped/PID/摘要不能修复S04。低权仍不能铸造reservation或lease；实际server持随机lease、实际wait/reap后才允许持久stop。失联/父亡槽保留UNKNOWN，不按时间自动释放；撤权后只准以真实lease完成资源清理，不准业务发布。

允许候选以标准HMAC-SHA256固定block实现避免新增extension，但必须提供Python金标、PG实际向量、错误长度/分段/跨session/跨version拒绝。低权组合攻击必须覆盖改写旧csrf_digest、自选binding/lease、未bind假stop、活child假reap与伪输出，证明无slot释放或数据发布。owner能力保密ACL、rotation及同版本换secret拒绝均需实际验证；源码或纯测试通过不能授runtime。

S02最小修复限定V41私有permission/write_guard，不修改原p3撤权trigger、旧lock_p3_permission或原Resolver。完整当前身份/凭据/角色/店铺及auth_version谓词必须保留；principal共享锁作为旧强制撤权trigger提交栅栏，不反向锁credential/scope/grant tuple，identity仍显式锁。必须用真实PG屏障证明业务先/撤权先两种ordering，deadlock、lock-timeout、503或撤权回滚均FAIL，不能当正常线性化。最终代码精确SHA仍须独审，runtime继续HOLD。

## S05 Demo绑定不可变补充（候选准入）

Root准入0025新增专用BEFORE UPDATE函数与trigger，仅禁止owned Demo关联行的organization/principal归属原地改绑；OLD或NEW任一为Demo均适用。同主体的identity/login/role/shop/password/enabled变动继续旧principal提交栅栏，INSERT和GC DELETE不拦。可信归属仅取私有v4_demo_personas live行；旧baseline对organizations/principals/identities存在app UPDATE，故公开组织marker/identity来源不能当不可改权威，本轮移除该兜底。helper仅MVCC读取，不新加principal或scope tuple锁。actor与支持的GC均先tenant/session锁，锁保持到提交，必须用双方屏障证明有效actor期间GC无法移除persona。GC先结束则tenant/session缺行，actor拒绝；不承诺GC后遗留disabled行永久不可改绑，不新增旧组织/identity保护或持久锚。合法换绑必须显式DELETE旧行再INSERT新行，原撤权trigger保护OLD主体；系统不自动执行替代操作。归属判断、GC竞争和新trigger顺序须给完整锁图与真实PG负例，不能靠app仅有SELECT就代签owner撤权线性化。

此触点仅限Demo行，不修改旧P3函数、历史迁移或非Demo M3行为；新增函数默认PUBLIC/app全撤权，独审精确SHA后才执行运行Gate。须保留旧业务回归、低权改绑42501、owner改绑明确拒绝、同主体enabled撤权两种ordering及GC清理。S02/S05源码候选不等于真实数据库核收。
