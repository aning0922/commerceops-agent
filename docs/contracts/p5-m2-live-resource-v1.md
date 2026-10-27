# M2 新自有资源与 Web 消费机器合同 v1

当前仅合同与脱敏结构模板，**真实资源 not_started**。原1800有效分钟总额、旧用量与各历史失败
不重置。衔接[业务合同](p5-m2-v1.md)及[备份合同](../M2_BACKUP_RESTORE.md)。
本次具体化d2的资源约定，不增加API、环境变量、父调度框架或新的金标schema。

## 1. 固定入口与所有权

A唯一拥有Woo/PG/API/Web/单Worker及父生命周期；B唯一拥有Playwright consumer源码。
所有consumer在开资源、开始900秒业务TTL之前冻结、独审并普通合入同一A候选。
A按下列argv直接启动子进程、传私有目录、wait/reap/采集/关闭；运行中不依赖聊天接力。
B不seed、不建PG、不改DB、checkpoint、权限或生命周期，不新建父编排。

- `COMMERCEOPS_WEB_BATCH=p5-m2-live`。
- 沿用 `COMMERCEOPS_B02_PRIVATE_DIR`（本次phase目录）和 `COMMERCEOPS_LIVE_WEB_URL`。
- cwd固定为最终A checkout的 `frontend`。
- source argv：`["npm","exec","--","playwright","test","--config","playwright.live.config.ts","--grep","M2 source$"]`。
- restored argv仅将末项换为 `M2 restored$`。retries=0，每段cap=240秒。
- M2配置只收集m2.spec.ts；开资源前两段各加`--list`验证exact1，固定标题与phase guard均保持。
  grep匹配含文件名的完整title，不能加前导`^`；旧锚定表达式实测0测试/native1，不作消费通过。
- window.owner固定 `phase5-M2-live`；window.phase仅 `source_ready` 或 `restored_pending_verified`。

模板：[source](p5-m2-live-source.example.json)、[restored](p5-m2-live-restored.example.json)。
两文件的 `template_only=true/files` 是文档容器，不是运行输入。全零hash、示例UUID/PID、过期时刻
和redacted账号均为占位，不代表已分配资源；任何模板不得直接传给consumer。
实际运行时只从已核真实事实生成各独立文件，逐项核实际Git/构建/监听/当前API身份，不能只验格式。

## 2. 六类文件的严格形状

模板中每个file对象及其嵌套对象的**全部键均required，禁止extra**；下表定义类型和唯一允许null。
除结果文件外，A以0700目录/0600文件、无symlink、exclusive create发布五个输入，发布后不可改写。
B只读输入。第六类结果文件及§4列出的输出由B用`wx`新建，A不得预建空输出。
source、restored、canonical使用不同子目录；两consumer各收到对应phase目录，绝不覆盖前阶段原件。
所有 `run_id/source_sha/source_tree` 逐文件相等；同源还须核locked依赖、实际镜像和BUILD_ID。
SHA为小写40hex、digest为64hex、UUID为规范字符串、时间为带UTC时区的RFC3339。
整数不接受bool/小数字符串，布尔不coerce；日期D为YYYY-MM-DD。

| 文件 | 精确字段/类型及null约定 |
| --- | --- |
| `window.json` | schema_version=`p5-m2-live-resource-v1`；run_id/source_sha/source_tree；owner/batch/phase固定值；build_id非空串；api_origin/web_origin只允许显式端口的127.0.0.1 HTTP；api_pid/web_pid/worker_pid为正整数；organization_id/shop_id；started_at_utc/stop_at_utc/consumer_started_at_utc/consumer_stop_at_utc；cleanup_reserve_seconds=180、consumer_cap_seconds=240；original_expires_at只在source为null；active_database仅source/restored并与phase对应；source_database对象含project/database/volume非空串；target_database在source为null、restored为同形对象且与source不同；resource_registration_ref为FileRef；stop_owner=`A` |
| `web-accounts.json` | schema_version=`p5-m2-live-accounts-v1`及共同三绑定；operator/approver各含login/password非空串、expected_principal_id、expected_organization_id、expected_shop_id、expected_role。两个principal不同；role分别operator/approver，org/shop与window一致。所有字段非null；登录值仅在该私有文件，不入window/结果/日志 |
| `m2-source.private.json` | schema_version=`p5-m2-live-source-v1`及共同三绑定；organization_id/shop_id/binding_id/config_ref、source_kind=`woocommerce_test`、source_config_version、registration_digest；profile=`positive-v1`、anchor_day/business_now、window.start/end、timezone=`Asia/Shanghai`、currency=`CNY`；parameters.L/R/S=3/7/2；expected_ref、golden_ref、seed_result_ref为FileRef；两个schema_version字符串见§3；sku_map为恰好4个闭合对象。除sku_map.variant_id允许null外，其余非null |
| `m2-facts.private.json` | schema_version=`p5-m2-live-facts-v1`及共同三绑定。source的canonical_source和restore_binding均必须null，B不得等待A在运行中补写；restored两者均必须为模板列明对象，禁止null。canonical_source的每个ID/hash/版本/期限/4假设/5个FileRef均来自source真实回执与A核PG；restore_binding的三停止/核验UTC、dump_sha256、schema_revision=`0018_p5_commerce_sources`、restore_receipt_ref均为A实际记录 |
| `consumer.private.json` | schema_version=`p5-m2-live-consumer-v1`及共同三绑定；phase匹配window；cwd=`frontend`；argv严格等于§1对应数组；retries=0、cap_seconds=240、business_revalidation_seconds=20、exit_and_evidence_reserve_seconds=40、mutation_reserve_seconds=60、restored_min_ttl_at_start_seconds=300；allowed_output_files严格等于模板中的对应完整列表，不允许动态路径或任意命令 |
| `source-results.safe.json` / `restored-results.safe.json` | schema_version=`p5-m2-consumer-result-v1`及共同三绑定；phase；logical_outcome仅passed/failed/unknown/not_run；started_at_utc/finished_at_utc在实际结束时均非null，模板not_run时可null；checks为`{name,outcome}`数组，outcome仅passed/failed/not_run；artifact_refs为FileRef数组；error_code仅null或固定大写安全码。禁止native_exit/exit_code/reaped/cleanup或原始异常字段；B不自签进程0 |

FileRef严格为 `{file,sha256}`：file是同一phase目录内的固定basename，无斜杠、`..`或symlink；
sha256是该文件实际字节摘要。A复制到restored的source原件须逐字节一致，不能重算或改写内容。
账号、Cookie、Authorization、Woo key/secret/CA/pin不通过FileRef或safe结果传播；B无需这些Woo秘密。
resource_registration_ref与两个parent事实引用仅指A的脱敏资源/SQL/restore回执，不给B DB凭据。
当前监听PID和BUILD_ID必须通过现有owned-listeners核验；端口通不等于owner匹配。

## 3. 原金标、SKU映射与证据归属

直接消费已审 `analysis-golden.private.json`，schema_version=`woo-positive-golden-v1`；
EXPECTED仍是 `expected.private.json`，schema_version=`woo-local-expectations-v1`，不新增金标格式。
A从新source PG分配org/shop后把真实shop UUID交lab prepare；D不晚于实际当地日期，serve不滚动D。
metadata的business_now/window须与原金标和EXPECTED一致，source版本/digest登记后不可变。

sku_map每项键严格为logical_key/product_id/variant_id/sku_key/stock_pool_key。
logical_key集合固定simple_a、simple_b、independent_red、independent_blue；platform ID为规范正整数字符串，
simple的variant_id=null，variation的product_id指parent且variant_id非null。
映射取自本次 `seed-result.private.json.mapping.products`，再按原expectations.identity规则推导，
必须分别等于golden.facts按logical_key匹配的sku_key/pool和EXPECTED.products对应行；禁止按排序配对。
四sku_key、四stock_pool_key均唯一；shop段须为同一实际shop，不用合成UUID冒充登记。

B只核公开页面/DTO可见的4SKU、需求/数量/库存、未知在途、四假设、Q=100/40/60/19及总219、
来源和质量事实。报告DTO没有订单金额/退款总计，B不填这些通过项。
税前CNY994、4订单行、0退款及完整4/4/0/4归A的真实Woo probe+独立EXPECTED/PG证据；不扩API。
全部先按原完整DTO验证再比较，不能仅比较计数或删掉mixed质量坏项拼金标。

## 4. 固定输出与持久请求

source输出仅模板allowed_output_files中的9个basename；restored仅对应21个basename。
创建/decision请求文件是**实际HTTP JSON body原始UTF-8字节**，使用原公开CreateNewCycle/DecisionInput，
不是新wrapper。B在首次实际route.continue前以wx/0600落盘并核字节；失败立即abort且非0退出，不发送。
每phase只有一个新创建/decision key；不改原key、body、nonce或版本。输入与输出文件存在即拒绝覆盖。

`*-receipt.private.json` 与可选 `*-lookup.private.json` 采用相同闭合wrapper：
`schema_version=p5-m2-receipt-v1,run_id,phase,operation,request_key,via,http_status,outcome,response,error_code`。
operation只create_task/decision，via只post/lookup，http_status为实际整数或传输不明时null；
outcome只confirmed/rejected/unknown；response为实际公开DTO对象或未取得时null；error_code为null或安全码。
confirmed必须有实际http_status与完整验证后的response且error_code=null，不能以空响应确认成功。
正常receipt保存实际POST回执。UNKNOWN只允许GET原`/api/v1/requests/{key}?operation=...`一次核对并另存lookup；
不重发，不把原UNKNOWN覆盖成成功；本次consumer仍非0退出并保留原件，由父按失败分支收尾。
只有首个decision已明确成功时才做10次技术幂等重放：读取同一原始decision字节，逐次另建
`restored-replay-01.private.json`至`-10`的receipt wrapper；任一不明立即停POST，只核原key，非0退出。

`*-task/report/plan/approval/execution-read.private.json` 保存对应实际公开DTO原件，先完整严格验证。
source-observed.private.json的闭合键固定为：
`schema_version=p5-m2-source-observed-v1,run_id,source_sha,source_tree,observed_at_utc,organization_id,shop_id,`
`operator_principal_id,approver_principal_id,create_request_key,task_id,source_task_id,report_id,snapshot_id,`
`facts_hash,plan_id,plan_version,plan_hash,approval_id,expires_at,required_assumption_keys,`
`create_request_ref,create_receipt_ref,task_read_ref,report_read_ref,plan_read_ref,approval_read_ref`。
所有值非null；四假设为唯一字符串集合；各ref为实际文件FileRef。没有nonce字段，nonce只在运行后的
source-approval-read.private.json中；A核当前PG/原approval关联后引用该原件。

restored-observed.private.json闭合键固定为：
`schema_version=p5-m2-restored-observed-v1,run_id,source_sha,source_tree,observed_at_utc,organization_id,shop_id,`
`task_id,source_task_id,report_id,snapshot_id,facts_hash,plan_id,plan_version,plan_hash,approval_id,expires_at,`
`decision_request_key,execution_id,item_ids,total_quantity,decision_request_ref,decision_receipt_ref,`
`before_approval_read_ref,after_task_read_ref,execution_read_ref,replay_receipt_refs`。
所有值非null；item_ids为4唯一UUID，总量219，replay_receipt_refs恰好10个，其他ref规则同上。
该结果只代表consumer核读，不替代A的业务SQL/checkpoint/一次执行核账。

B关闭trace/video/HAR与密码截图；账号只在消费者内存，沿原DOM赋值/清空机制；401/403不自动重登。
恢复段是父明确启动的新phase/new context，登录一次按当前principal/org/shop核验，不沿用源浏览器内存。

## 5. 无聊天接力的固定顺序

1. A发布source目录五个输入，m2-facts两个字段均null，且输出均不存在；直接启动source child。
2. B从真实CreateTaskReceipt.task_id读task→report→plans，并以receipt.source_task_id核原任务对；
   当前approver只读原审批/nonce，**不批准**。B独占写source-observed及source-results后关闭浏览器退出。
3. A wait/reap并取得实际native0后，核source-observed与当前PG/官方checkpoint；发布新的
   `canonical/m2-facts.private.json`。不改source目录原空facts，不让child等待它。
4. 停并reap API/Worker及全部writers，再取含DB UTC的最终快照并实际dump。源PG随后停机保卷。
   对另一个登记为空的新目标restore，核schema、角色/ACL、同一task/thread/plan/hash/expiry/source绑定。
   不重新seed，不SQL修CP/job/approval/once，不延长原TTL；源与target不同时写业务。
5. A发布新的restored目录，复制必要source原件并填canonical_source/restore_binding、真实新PID；
   核§6余量后直接启动restored child。B先只读核原绑定，再四项明确确认并批准一次、原key十次重放。
6. B输出仅逻辑结果；A记录自己的source-parent.safe.json/restored-parent.safe.json，含实际wait/native
   exit/reap/PID/时长/截止/子树状态。只有consumer逻辑、父进程回执及A业务核账均满足才签该Gate。
7. 任一失败/UNKNOWN走固定停止与取证，不等聊天决定是否重发。最终按writers→API/Web→PG/Woo
   清理，源/目标卷保留，UNKNOWN不签资源0；负例目标另行预登记空库，不破坏正向原审批充数。

## 6. 两层截止与不可压缩余量

总owned窗口计划<=3600秒，cleanup至少180秒；已审lab serve原90秒自身cleanup不变。
source consumer启动须总stop剩余>=240+180秒。
restored启动还须原真实expires_at剩余>=**300秒=240消费+20业务重观测+40取证/退出**。
其consumer_stop取 `min(启动+240秒,总stop-180秒,原expires_at-60秒)`；source不含expires项。
source首次创建前也须在consumer_stop前保留60秒，并核总stop-cleanup预留，尚无original_expires_at；
restored每次decision/同键重放前须在consumer_stop及当前API原expires_at之前各留至少60秒（20+40）；
余量不足HOLD/非0，不继续发送。父按同一绝对deadline终止/wait/reap，不能把外窗60分钟当900秒业务期。
首次创建前新部署TTL固定900秒，dump/restore全程保持，过期用真实时钟，不改expires_at或冻结DB时间。
源码build/consumer准备先完成；当前这些是固定预算而非测得容量，实际运行/备份/完整M2仍pending。
