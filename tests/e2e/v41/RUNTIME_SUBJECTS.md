# V41 额外 PG／HTTP 主体清单

当前 H/S 定义增量：H02 ca69b83 已补四 GET 实际调用路径和原 job 独立 GET，恢复与 imported
绑定的 demo_fixture/demo_mixed 金标。闭集 16 为 12 GET + 4 POST；集合相等不能证明实际执行。
S01 固定 Shell/business 双标题与 2 passed/0 skipped/0 retry 报告、原请求 journal/末态接线；
实际运行仍 NOT_RUN。Shell 迟到成功响应在 logout 后清屏专项尚未实现，原生 200% 由 GATES
独立 owned headful/profile 路线承担；不能由三宽截图或 logout 基本清屏代签。完整当前文件卡与
一次单案 execute 路径见 QA_PLAN 正文前部。下方原 AST/DDL/HOLD 清单保持其历史时点。


2026-11-04（台北）。只读来源为 Root `7f1667a14059a2ea4ae00dcc19811d6a22a06526`，后端
`55ce78b841df0513e09d4e013d2857475fe64bf7`；精确测试路径、行、矩阵参数与文件hash见同目录
`runtime_subjects.json`。只用AST盘点，没有pytest collect、fixture、PG、HTTP或服务执行。

本清单不是运行授权或可执行handoff。runtime_definition保留772历史来源与HOLD；旧无条件
OWNER_POLICY_GRANT_VERIFY_SEQUENCE_PENDING不动；不猜CLI路径/参数、不填READY、不提供新窗口。
`9f10c8c5ad1a44fd487159b9f19955cab24af9b2`的T01单片后经50590a5源码核收；不在本次盘点的7f测试快照内，不能改写7f原字节。

Root报告的DDL旧案单列：0025中的JSONB reaped:true冒号被SQLAlchemy解释为bindtrue；事务已
回滚、version表值null、V41表0，资源已关闭、卷保留。SQLSTATE原值为空且NOT_CAPTURED，不能
补猜PG SQLSTATE。随后已精确读405f5e3及8928830：仅reaped JSON冒号后加空格，业务谓词不变；源码/编译回归已核收，不等于实际PG成功。本包尚未收到新DDL/7PG实际回执，NOT_RUN栏仅指本QA包无运行证据，不覆盖Root后续独立回执。
修片后必须绑定新source/tree，旧失败与当前7f清单不能代签新DDL。

## 已有 PG 主体与精确边界

`tests/v41/backend/test_business_pg.py`在7f与55ce内容相同，15个顶层测试函数声明22个参数化
实例；这是源码盘点数，不是本轮collected/selected/actual/passed。具体selector和参数值已在JSON
逐项列出，未编造pytest参数化node ID。

| 批次 | 精确函数及参数 | 声明实例 | 尚待实际证明 |
| --- | --- | ---: | --- |
| Root最小7 | `test_revocation_commit_order_and_tuple_principal_crossing_no_deadlock`：三表×revoke_first两值 | 6 | 正反先后、pg_blocking_pids、两事务原生提交、末态0/1；原1s lock/5s statement不放宽，超时/deadlock/503不算成功 |
| Root最小7 | `test_sql_current_policy_rejects_two_old_consistent_session_rows` | 1 | 两旧行同key且未撤、DB authority已换版时SQL/Python拒绝 |
| 既有追加 | `test_seven_tables_private_helpers_and_low_role_no_dml` | 1 | 七表ACL、runtime闭集EXECUTE、policy六列可读而private verifier/整表不可读、禁止DML |
| 既有追加 | `test_sql_python_canonical_text_corpus` | 1 | 实际PG文本/NFC/Unicode与Python闭集一致 |
| 既有追加 | `test_golden_reads_tags_receipt_replay_original_after_later_effect` | 1 | 同源金标、十次同键、后续版本后仍读原receipt；不能只看当前tag行数 |
| 既有追加 | `test_paid_unknown_fulfillment_and_atomic_rollback_on_audit_failure` | 1 | 未知付款拒绝；event插入故障后fulfillment/receipt/event零增量，fixture故障hook清理 |
| 既有追加 | `test_real_native_preview_confirm_same_job_version_sources_and_all_result_export` | 1 | 真child、原preview key、confirm原job.version、全结果export、原source链与slot；本节点为CSV，不是XLSX实跑 |
| 既有追加 | `test_changed_revision_cannot_confirm_old_preview_and_reset_hides_effects` | 1 | revision冲突、reset后旧效果不可见且物理证据仍保留，不推断GC |
| 既有追加 | `test_parent_mapping_chain_supersedes_and_disallows_old_confirm` | 1 | DISCOVERED→子版v2→原版SUPERSEDED；非完整链/配额压力矩阵 |
| T01源码已核后追加 | `test_missing_policy_wrong_config_old_version_and_no_implicit_reactivation` | 1 | 9f10先验ACL拒绝，再只给已审两列SELECT保空policy，验证缺authority；随后激活/换版/版本复用拒绝，不给额外DML |
| 既有追加 | `test_durable_reservation_survives_connection_release_without_expiry_reuse` | 1 | 分配连接退出后slot仍占用、同tenant拒绝、原lookup UNKNOWN；连接退出不是父进程死亡 |
| 既有追加 | `test_actual_parent_death_keeps_running_unknown_slot_without_auto_replay` | 1 | 当前fixture为实际parent os._exit(17)，不是SIGKILL；真实child/PID bind、slot仍占。仍需同案原key只读UNKNOWN与child末态见证 |
| 既有追加 | `test_two_actual_children_global_slots_and_reap_before_next_admission` | 1 | 2实际child占全局槽、第三tenant拒绝、真实run_parser wait后再准入；不能以JSON reaped单字段作独立OS证明 |
| 既有追加 | `test_private_verifier_hmac_goldens_and_forged_writable_binding_no_admission` | 1 | 私有列/签名helper拒绝、SQL/Python HMAC标准向量、legacy锚可写但八种伪binding不能reserve；不能替已有job错误lease stop负例 |
| 既有追加 | `test_demo_binding_reassignment_denied_before_original_new_principal_trigger`：三表 | 3 | owner与app改绑拒绝、trigger顺序、auth_version不变；只覆盖同tenant operator→approver，非所有live/non-demo/GC边界 |

最小7与既有追加15必须分别保留计数、原失败、选中/实际/未跑和退出码；不能将最小7成功写成
全22或本清单新增场景成功。T01源码已核收，DDL新实际回执仍须Root独立登记；不得因本清单或单片代码核收启动完整22。

## 真正新增、现有22不能代签的 PG 主体

以下是主体ID，不是已存在pytest节点；无可执行fixture者明确写待实现，不增造通过数。

| 主体ID | 实际主体／入口 | 必需原件与硬拒判据 | 当前接线 |
| --- | --- | --- | --- |
| QA-PG-L01 | 实际RESERVED job；app只知job/process/PID/hash，分别无lease、空/错lease、错process | 可信fixture保存正确lease但不交给攻击连接；V41_PARSE_LEASE_INVALID、原state/slot/proof不变。正确私有lease持有者不属于此负例 | 需新fixture；NOT_RUN |
| QA-PG-L02 | 真实RUNNING child存活时同类无能力伪stop | PID/birth存活与bind COMMIT、错误lease拒绝且slot仍在，随后同Popen实际wait/native与受信stop COMMIT才清slot | 需新fixture；不能拿reserve拒绝或自编proof代签 |
| QA-PG-L03 | child运行中credential/grant撤权先COMMIT，再真实reap cleanup，再publish | 撤权native0、正确私有lease的cleanup可提交、原job STOPPED/NULL slot；publish重新actor拒绝，preview未发布、业务effect/receipt/event零增量 | 需owner撤权与parser同步fixture；NOT_RUN |
| QA-PG-L04 | child运行中owner policy轮换，再真实reap与旧API publish | owner版本/verifier/generation同事务换版并撤旧bound；清理与业务发布能力分离、旧API不复活或自动激活 | CLI仍未审/fixture未交付；NOT_RUN |
| QA-PG-P01 | 实际父亡＋同一原key恢复 | 保留现有exit17模式；如另测SIGKILL单列原生-9/137；核真实child在死亡点存活，原lookup UNKNOWN、slot不因child退出/过期/GC消失，无自动重放 | 既有父亡节点需补同案见证；NOT_RUN |
| QA-PG-S05A | live demo↔non-demo、跨org主体改绑；纯non-demo→non-demo对照 | demo涉及改绑由私有live persona锚拒，owner/app分别记；纯non-demo旧P3语义不被误禁，不触旧真实M3资产 | 22只覆盖demo→demo三节点；需新合成主体 |
| QA-PG-S05B | 可写organization/principal/identity属性变化与私有persona锚 | 不因可写名称/属性把非demo判demo或让live demo绕保护；app不能改/删private anchor，正向读与auth_version据实际变化核 | 需新合成主体；NOT_RUN |
| QA-PG-GC01 | 受支持retention fixture中的官方gc_tenant与actor交错 | tenant/session锁先后、活parse HOLD、六子表按序清理、policy不删、旧actor拒绝；GC后遗留disabled主体不永久冻结是live-only已审语义，不能误判新安全承诺 | 需官方GC fixture与新owner窗口；不得全表TRUNCATE/直接删job |
| QA-PG-T02 | 导入多行中途真实SQL故障，以及event/deferred失败 | 真READY预览后，在受审fixture故障点失败；新事务原job/version/digest未冒称COMMITTED，import_products/receipt/event零增量，原key UNKNOWN，价格/库存/原fixture不变 | 现有fulfillment审计故障与QA标签apply后rollback均不能代签；待实现 |
| QA-PG-T03 | 原import confirm与reset／撤权的真实屏障交错 | 原expected revision/job version/digest与双方COMMIT、PG blocker证据；只接受明确线性化顺序，deadlock/55P03/57014/503不是正常撤权，原操作不重试 | 最小7是tags，不自动覆盖confirm；待实现 |
| QA-PG-Q01 | 同tenant1/全局2的持久slot，链5/作业12/active heads3与SKU500边界 | owner/tenant/epoch/gen绑定、临界值与越界真实零增量；UNKNOWN/到期不释放slot，错误输入不能借配额错误掩盖鉴权 | 已有两槽/单tenant候选仅部分覆盖；其余待实现 |

资源scope、父/子绝对UTC、Root精确GO、清理余量及预算在后续具体窗口登记，不在本清单猜容量。

## 真实监听 HTTP 主体

初次历史盘点时，16条实际路由已逐项与QA闭集映射对照写JSON，http_recipes只定义12条，缺：
GET `/api/v4/dashboard/drilldown`、`/api/v4/products/export`、`/api/v4/orders/export`、
`/api/v4/read-context`。这四项现已由 ca69b83 的配方覆盖，job GET 与 source 金标另补；
定义/调用路径不代表已运行或完整断言，以下表格保留初次盘点状态，实际新案回执另计。

| 主体ID | 必需实际请求／主体 | 成功／拒绝与末态要求 | 当前准备边界 |
| --- | --- | --- | --- |
| QA-HTTP-01 | 真实loopback listener的16路由、静态export优先UUID、方法/未知路径、OPTIONS | 当前schema、no-store、Vary Cookie/Origin、成功当前context；普通GET顶层OK，POST动作COMMITTED，合法原key lookup内层UNKNOWN保留 | 12路由候选；4缺定义；16 ASGI stub不是监听证明 |
| QA-HTTP-02 | TWD/CNY各店14自然日仪表盘、drilldown、product/order/context/export | 同source/revision、独立八指标金标及金额UNKNOWN原因；分页无漏重、CSV为全筛选结果且防公式注入、库存/订单钱不被标签/履约/导入修改 | 部分KPI/catalog/import候选；drilldown/export/context与全日期矩阵待接 |
| QA-HTTP-03 | 当前operator、approver、restricted_admin和另一tenant | approver合法读且写ACCESS_DENIED；admin无默认shop；foreign shop/object按真实归属RESOURCE_NOT_FOUND。共享fixture UUID在自己tenant合法，不一律预期404 | 当前跨访客部分准备；完整角色/16路由矩阵待接 |
| QA-HTTP-04 | 真实Origin、CSRF、规范/重复epoch/gen headers、重复query/body keys、JSON大小/格式、错误method | 指定INVALID_REQUEST/ORIGIN_DENIED/CSRF_INVALID；不刷新/重登/自动create，不启动parser或写job/effect；HTTP原响应+DB零增量分开保存 | ASGI覆盖不转签监听HTTP；需固定负例调用与最终subjects |
| QA-HTTP-05 | 同标签key同文/异文、异key同version/revision双client | 原receipt同一、异文IDEMPOTENCY_CONFLICT、版本/快照竞争单赢家；请求原生区间保留；client barrier不证明PG临界区 | e427双client与原key候选；异文/区间等仍须实际补证 |
| QA-HTTP-06 | CSV与XLSX各自完整preview→原key恢复→confirm→GETjob／product／dashboard | 实际native parser、原job版本/三版本字段、来源链、同键十次、已确认换key拒绝；无ACK时先只读不重发。CSV Store PG候选不替代XLSX HTTP | 两格式候选；HTTP均NOT_RUN |
| QA-HTTP-07 | 错mapping/重复SKU/币种/价格/无效行/超界输入，supersede/expired job与quota | 明确INVALID/拒绝及零部分导入；parser资源边界、错误数量/样本上限、原UNKNOWN不隐藏；配额拒绝不能代签权限拒绝 | 部分INVALID候选，完整真实输入/权限矩阵待接 |
| QA-HTTP-08 | 已打开商品/导入读上下文后persona switch、reset、credential撤权或policy换版 | 清旧context/cursor/job/action、epoch/gen拒绝、旧receipt不冒当前；cursor篡改422 INVALID_REQUEST、已绑定snapshot变化409 SNAPSHOT_CHANGED；无自动create/retry | 旧控制入口真实API复用，fixture/CLI与完整Web旧响应交错需各owner接线 |
| QA-HTTP-09 | 固定SQL attack／rollback后真实GET原preview/action key | app角色与实际SQL证明独立保存，再HTTP内层UNKNOWN；新subjects SQL_ROLLBACK_VERIFIED原key在终态不得出现持久行 | 4f候选已接，按c696校准legacy锚与双MAC；HOLD未运行 |
| QA-HTTP-10 | 全部writers/API/oneoff退出后、PG down前末态采集 | 每scope/key/job/version/slot、receipt/event/effect、fixture库存金额和原日志；已COMMITTED_READBACK预览缺失/未发布硬拒。未知不默认回滚，GC清除须事前登记 | ef6采集已接；不得schema final/中途counts冒终态接受 |

## S04探针校准与后续合批条件

已审c696/55ce保留legacy csrf_digest可写；新独立私有invocation_verifier不授app读，binding为
43+点+43。QA攻击现在将合法legacy锚写入作为信息，以格式合法但第二MAC无能力的binding
尝试reserve，必须SESSION_INVALID且零job，随后最终ROLLBACK恢复锚/六表。缺EXECUTE、配额满或
任意SQL错误不作为该攻击通过。已有正确私有lease的监督器能报告stop是已审能力边界，SQL不
独立证明OS停止；错误/无lease攻击与真实Popen wait见证必须分开。

下一次具体运行前仍需：405修片实际DDL/原失败回执分列、T01实际执行、owner activation/grant/verify
实际CLI精确交付及独审、源镜像实际bytes桥、QA/Web组合freeze、Root新owned对象/UTC与独立
清理。清单与代码准备不解除旧unconditionalHOLD，不用READY元数据旁路、不重放旧失败窗口。

正式50590a5的QA准备修正另交独立源码commit：预览ACK_COMMITTED和COMMITTED_READBACK均要求
末态已published job，ACK_OK不升级；schema版本由实际owner只读catalog回执提供，app探针不
SELECT受保护alembic_version，不扩大app权限。该host回执仍须与本次source/tree/新DB、owner
current_user、七表集合及policy初始化态一致；不把缺前置权限42501当攻击通过。
