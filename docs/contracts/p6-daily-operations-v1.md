# M3 / S3 日报操作候选 v1

本包延续S1/S2，父源码为两个独立修正后的 `89d1d8604b3b4c8627e44e04d398cd37465138b2`。
这里记录候选和作者离线结果，不代签SQL、HTTP服务、UI、独审、CI或发布。
0022实际 `revision='0022' / down_revision='0021'`；0020/0021精确提交由Root组合，
本owner不读取其他owner未提交文件，不修改Compose、镜像、锁、CI或旧迁移。

## 1. 精确操作和wire

外层沿用原session envelope的 `schema_version=p3-web-v1`，业务内层 `p6-m3-web-v1`。
独立OpenAPI仍由 `python -m scripts.export_daily_schema` 生成docs/backend两份同字节资产；
真实类型在daily/http_models.py、read_models.py和questions.py。
原P3/P4/P5完整OpenAPI在只启用日报GET和启用全部新增操作两种情况下均保持等值。
旧任务列表的kind范围不扩展；新建返回task_id后由日报详情路径导航。

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/api/v1/daily-capabilities?shop_id=UUID` | 当前operator shop scope；source完整公开投影嵌套在source，失效enabled=false，无Mock回退 |
| POST | `/api/v1/daily-reports` | CreateDailyInput，202 accepted.task_id/state；原子原任务键冲突409 |
| GET | `/api/v1/daily-reports/{task_id}` | 原冻结报告；新增可空schedule_run和delivery，报告完成和Fake投递状态分列 |
| POST | `/api/v1/daily-reports/{task_id}/questions` | QuestionInput，202 accepted.task_id即question_id；四类enum，无自由SQL/工具/模型 |
| GET | `/api/v1/daily-reports/{task_id}/questions/{question_id}?cursor=...` | 原缓存answer与最多50条citations，总数与next_cursor |
| GET | `/api/v1/daily-reports/{task_id}/evidence?report_id=UUID&cursor=...` | 原冻结脱敏证据页，最多50条，总数与next_cursor |

CreateDailyInput字段：schema_version、shop_id、source_config_version、request_key、business_day（可省略/null）。
QuestionInput的schema_version为 `p6-daily-question-v1`，字段为request_key/report_id/snapshot_id/
content_hash/facts_hash/question；question有kind/metric_key/finding_id三个必填键，未用目标显式null。
日报POST和追问POST显式按JSON模式校验UUID/date，拒绝重复键、非finite常数、额外字段与超过32KiB正文；
不能把strict DTO的JSON wire dict当Python输入强制转换。handler返回真实已验证模型。

身份、Origin/CSRF、当前session/auth_version、operator shop scope沿原middleware；
GET详情、追问和证据均限同owner，其余对象404。admin/approver不自动获得业务读取权。
错误复用原固定安全envelope/code：PLAN_CHANGED409、IDEMPOTENCY_CONFLICT409、NOT_READY409、
INVALID_CURSOR409、INVALID_REQUEST422等；没有改旧Error枚举或默认错误原文。

capability不读Woo秘密、不访问Commerce。无private deployment时只安装S2 GET；显式deployment才安装新增操作。
`schedules_enabled=false`、`fake_delivery_enabled=false`为新增私配默认；
model_requests_enabled与external_sender_enabled仍strict literal false，数值0/1不作为bool接受。

## 2. 0022六张窄表与同Worker调度

新增p6_daily_destinations/schedules/schedule_runs/questions/deliveries/fake_receipts。
destinations和schedule配置仅表owner可登记；runtime只能SELECT配置、插入run/追问结果/投递意图/Fake回执，
schedule只可窄更新enabled/pause_reason/last_created_day/updated_at，禁止runtime重新enable；
delivery只可窄状态更新。证据/结果/run/Fake回执append-only，owner也不能UPDATE/DELETE/TRUNCATE。
旧outbox约束完全保留，不开放sender或sent/sending。

schedule一版本一行，配置canonical/hash和身份/来源/规则/时区/delay/first_due/destination冻结；
同stable schedule_id最多一enabled版本。配置CLI须同owner当前Web session且admin+operator shop scope。
first_due须未来、版本单调；暂停或换版本不删除旧run或换绑旧任务。
新版本不能复活旧row；未开始的旧run在load、已开始的旧run在save均由当前版本/启用/权限/来源检查阻断，
保留needs_attention/DAILY_SCHEDULE_CHANGED。已完成报告仍只读，不因停止调度被重采。

纯算法按业务日结束的当地午夜分别转换UTC，再加0–1439 elapsed分钟，覆盖DST的23/25小时日。
原Worker的maintenance无在途Graph时扫描，沿用≤30秒周期，每轮最多32个已到期配置。
事务锁schedule，以DB UTC now只新建最近到期一期；UNIQUE(schedule_id,due_at)与单调游标固定一期。
run/task/analyze job/audit同事务；记录missed_periods和skipped边界，保留之前已存在未完成run。
不按lease过期接管，无第二Worker、独立cron、后台Graph或模型。
run的due_at、queued_at和持久audit实际started_at分列；显示不承诺准点。
实际SQL、竞争、撤权、回滚和停止恢复仍须Root实际矩阵，不以纯算法推导替代。

## 3. Fake投递与unknown

只有完整报告且原schedule绑定登记的Fake destination才生成意图；
snapshot/report/task completed/旧outbox意图/新delivery在同save事务提交。
旧outbox始终status=blocked、sender_enabled=false、external_id=null，operation=daily_report_fake；
新delivery明确transport=fake，其sent仅表示PG Fake receiver回执，不能称飞书实际发送。
payload由程序从同报告生成日期、币种、显示指标及report/snapshot/content/facts引用，含受控来源和模板标签。
发送前复核原owner/当前权限、schedule版本/启用、source版本、目的地和原outbox/payload/provider key。

网络前原则在这里表现为：先独立提交sending/attempt1，再由独立PG事务提交Fake接收副作用。
接收表以provider_key主键持久去重并核destination/hash；不是依赖checkpoint。
reply丢失后unknown，不回pending、不换key/正文/目标、不自动再发；旧owner退出经原termination_confirmed gate核收后，
遗留sending也仅转unknown。已接收后的配置变化不能撤回Fake效果，保留真实Fake回执。
本轮没有实际网络sender；真实模型、embedding、飞书推送和旧窗口均关闭/NOT_RUN。

## 4. 模板追问和证据页

规范问题和request_key绑定原task/report/snapshot/content/facts；同键同正文原子返回原question task，冲突409。
复用原PG jobs和DailyRunner的同一个Composite槽，注册p6-daily-question-v1，无新模型/采集/发送。
结果先于ACK持久化；读取重算模板及证据引用、canonical/hash，GET不启动任务。
四类为metric_definition/metric_evidence/finding_reason/data_quality。
金额、公式和cohort只来自原确定性事实；缺指标拒绝指标问题，质量问题明确不足，不当0。
每个metric证据按原日期cohort筛选；原始订单ID以脱敏hash投影，无客户字段/来源路径/凭据。
answer标template/not_used，程序metric引用与原证据citation_id可区分；不称为真实模型解释。
cursor用当前Web配置密钥作带独立domain的HMAC，绑定actor/auth/org/shop/task/report/snapshot/content/facts及question_id。
换权限版本、跨报告或跨question页失败，不自动切最新。页≤50，并给完整total_evidence_count。

## 5. 新owned本地演示入口（尚未执行）

仅Root新具体UTC窗口执行以下命令。新PG须先由Root组合0020/0021/0022并migrate/setup-checkpointer/grant-runtime；
使用Root固定pgvector镜像，不复用旧库/卷/凭据。此owner未启动PG或HTTP服务。

`python -m scripts.m3_daily_demo --directory /ABS/NEW_PRIVATE_DIR`
读取显式COMMERCEOPS_DB_* owner连接，数据库名必须为m3_daily_demo_开头且business.organizations为空。
目录必须新建；种子复用本地合成测试构造器，按DB当前时区昨日生成新fixture/manifest/source登记和新Web凭据。
仅写新目录0700/文件0600，登录材料在local-login.json、session在local-session，不输出凭据。
输出demo.json和两条配置路径；不启动服务、不创建日报、不实际发送。

API使用COMMERCEOPS_P3_CONFIG_FILE指向输出configuration.json，
COMMERCEOPS_M3_DAILY_CONFIG_FILE指向daily-deployment.json，运行 `python -m commerceops.entrypoints.api`。
Worker同两配置，COMMERCEOPS_MODE=test，运行
`python -m commerceops.entrypoints.worker test-run --organization OUTPUT_ORGANIZATION_UUID`。
前端先登录新local-login.json中的凭据，再读capability、POST日报、轮询详情、POST追问并读缓存和证据页。
服务与Worker停止/native wait及PG清理保卷仍由Root父窗口执行，不在此脚本自动长期托管。

`python -m commerceops.entrypoints.daily_source --deployment FILE --organization UUID --shop UUID`
可对同登记原样幂等核对；不能覆盖已有source。
schedule CLI为 `python -m commerceops.entrypoints.daily_schedule`，必填web-config/deployment/session-file/action；
configure另需schedule-file，pause另需schedule-id/version，register-fake另需destination-id/shop-id/version。
--enable必须显式；CLI的actor须当前admin+operator。默认演示账号只有operator/approver，不暗自升admin。

## 6. 作者证据与待核收

最终作者纯测试S1/Read/source/questions/scheduling **262passed/2.05s/native0**；
包含实际ASGI GET响应序列化和POST JSON UUID/date受理、启用全部操作旧OpenAPI等值。
全仓Ruff通过、mypy432文件通过；Ajv Draft2020 strict原Read wire **35cases/native0**。
后者只签Read schema案例，不冒充新增各操作的完整Ajv语义覆盖。
新S3 PG模块仅collect **5节点**：追问事务/回执/冲突/撤权、真实session POST/CSRF/UUID、
调度补最近/去重/暂停保原任务、Fake成功及接收后reply丢失unknown/不重发。
本owner这些PG节点均NOT_RUN；0022实际SQL、完整父链、HTTP服务+Worker+UI、独审与CI全部pending。

开发中保留：首调度测试import不存在rules导致collect error；修正为真实DailyRuleConfig后43pure通过；
广静态首mypy因三新增测试缺注解及Optional未收窄报51项，已补真实类型/断言；
首S3纯批260pass/1fail为旧单GET路径集合，随后38pass/1fail为漏导PATH；两处精确断言同步后通过。
大量初始长SQL字符串Ruff失败均在未冻结WIP，换行后规则不放宽。
S2原迁移/HTTP失败、旧2830pass/165fail离线工具事实与Root所有窗口结果继续分账，不被此包覆盖。

提交前changed-content扫描首2项均为非秘密：SQL provider字段比较、metric字段名条件。
以等值SQL的IS NOT DISTINCT FROM及语义明确的metric变量修正误报形状，未改扫描规则/豁免或编码隐藏内容。

冻结后自查补强：question失败分支也必须同时匹配原job/lease owner/kind/payload、
task workflow/thread及Worker organization/owner，避免在拒绝不合法RunRequest后按裸task_id写失败态。
这是单独后续修正；尚无实际PG签收，不回写首候选为已通过。
