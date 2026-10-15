# P4 验收工具准备合同 v1

本合同属于[完整准备包](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6184152897)，
版本 `p4-acceptance-preparation-v1`。它定义 A/C 工具接口；源码存在或局部测试不表示准入完成。
总上限12 Agent有效h、A初分配5h、北京时间2026-10-15 22:01:35硬停不变。

## 唯一入口与源码

A的新私有 `candidate-A/run_once.py` 是唯一最外入口。准备、历史合成与当前RO子进程均由该入口
加载同一冻结manifest；最终隔离与后续Root明确释放的真实RO使用同一入口/hash。`scripts/p4_acceptance.py`
仅为共用helper，没有第二业务CLI。C的driver仅作为阶段consumer被调用，不独立签发业务成功。

入口命令固定为：

```text
<pinned-python> -I <entry> --manifest <private-manifest.json> --manifest-sha256 <sha256> --request <private-request.json> --request-sha256 <sha256>
```

manifest冻结解释器及实际binary hash、CWD、host/container合法package_root、全部本库Python模块、
uv.lock/pyproject以及入口hash。正式命令的hash由Root冻结，不能从同一未核输入自取期望值。
父子均使用新isolated解释器；禁止PYTHONPATH/PYTHONHOME和预加载的本库模块。固定loader执行
已经校验的同一份bytes；检查实际module origin和cache。容器的installed包可在/app/.venv，
scripts/tests可在/app；不能用host路径规则拒绝合法容器，也不能因venv路径正确就接受另一WT的editable包。

每个新logical run启动前登记新project/owner/labels/volume/不可变image/container IDs、
UTC及monotonic期限。通常≤20min，完整链必要时≤30min；预留≥180s独立清理。
prepare/preflight不消耗arm后的SDK≤300s；arm后的原角色/时窗/hash/once重核保持。

## A/C文件与函数接口

A生成一个600模式的handoff文件，父目录700；路径与sha256通过外入口绑定。
C只消费已提交并由Root统一集成的源码，不从A未提交目录导入。
C的 `tests/e2e/web/m1_acceptance_driver.py` 提供同步函数：

```python
def consume_stage(stage: str, handoff: Mapping[str, Any]) -> dict[str, Any]: ...
```

stage仅 `t6`、`restart`、`page`。函数失败抛异常，调用方固定stage分类，实际最外CLI非零；
成功返回阶段证据，不生成整体PASS。若已有C内部函数，consumer可窄封装，不新建业务launcher。
A在同一入口中执行native v2投影/外部原记录读回，不由C伪造Base已同步状态。

handoff固定顶层字段如下，实际值仅本轮合成资源的私有文件中存在：

| 字段 | 必需结构/来源 |
| --- | --- |
| contract | 精确 `p4-acceptance-preparation-v1` |
| candidate | source_sha、tree、manifest_file、manifest_sha256；actual_images各自id/source证明；lock及toolchain指纹 |
| resource | run_id、project、owner_label、volume、container_ids、registration_ref、runner_namespace、deadline_utc、cleanup_reserve_seconds |
| private_refs | web_config、app_database_config、web_credentials、external_records；每项path/sha256，配置内仅引用本轮新凭据；不得原env/Secret |
| fixture | organization_id、shop_id、principal_id、feishu_identity_id、web_identity_id、auth_version；task_id、source_task_id、plan_id、approval_id、decision_id、execution_id；item_ids、target_item_id；item_count=20、quantity_total="2000"；checkpoint_threads |
| baseline | core scoped row fingerprints；CP_DATA_TABLES精确三表的rows/digest、thread集合、排序/bytes编码合同；migration metadata另列 |
| base_ro | typed_result原生产ProjectionResult序列化；window_id、outbox_id、item_id、version=1、client_token、projection_hash、request_hash；pg_proof含delivery状态/完整唯一/observed_version/external_id、稳定anchor及真实SDK method counts；证据ref/hash |
| worker | epoch="base_ro"、owner、pid、namespace、process_started_id、termination_id、claim_id/claim_hash、reaped；来自原持久audit及实际OS/wait，这是已结束RO epoch，不代表当前app Worker活跃 |
| web | api_origin、web_origin、expected_item_path；仅loopback且必须符合本轮登记；实际服务image/container证明 |
| t6 | request_phase="unprepared"、request_key=null、action="close"、reason、expected_version=1；初态固定目标/语义，原生UI生成request key |

app_database_config字节是实际app角色的原生DatabaseSettings JSON；C独立校验path/hash并按该对象连接，
禁止从Web配置猜派生连接或退回owner。该对象user必须commerceops_app，runtime_password_file必须null。
业务/claim ID为UUID标准串、artifact SHA256为64位小写hex；Git SHA/tree为40hex，image ID保留
sha256:前缀，container ID、UID、PID等使用各自原生类型，不能套UUID规则。
路径必须canonical且落在登记的新私有目录。
缺字段、跨candidate/resource/fixture、bool冒整数或未证明source必须拒绝，不能补默认成功值。
private_refs的hash是私有文件字节绑定，公共报告仅输出计数/布尔/hash，不输出登录内容/nonce/DSN/URL参数。

`t6`结果包含contract/stage、同candidate/resource/target引用、request_key、semantic_payload_hash、
typed_response、receipt_ref/hash、PG验证的request/actor/identity/auth_version/audit/outbox关联，
以及20项中仅同target从open/v1到closed/v2、其余19open的实际计数。
必须真实页面/API一次POST，再原request_key GET；HTTP200/text/v2单独不足。
真实ResolutionDialog在prepare时通过crypto.randomUUID生成key，工具不得预造UUID、修改crypto或请求体。
C在prepare后、send前将原生key和canonical wire-body hash写入O_EXCL新私有receipt，绑定
原handoff digest/candidate/resource/target；原handoff不重写。可读prepared DOM或在network-send前
observer读取后原样continue，严格一次原始POST。返回actual request_key及receipt ref/hash供后续原键
GET/replay；server semantic_payload_hash由真实PG/native规则另核，不与wire-body hash混同。
新v2 outbox/key只由原T6产生，不由工具写入。A读回必须使用该outbox原key和同一Fake外部record。

`restart`结果分列正常stop前、停止后、same-volume up后：actual IDs/ownership/health、
单Worker、PID/namespace、停止与回收证据。中途Worker1与最终Worker0属于不同阶段。
BaseRO epoch必须在handoff前停/reap；C的t6/restart按各自app epoch记录实际active/started/termination，
历史reaped=true不能签当前app活跃或停止，也不得并行运行两个Worker。
`page`结果含同target可见状态、实际严格DTO关联和相同CP/core readback；录屏只是证据展示层。

## SQL、角色和安全失败

0016/56是共同正向；0015/55在同candidate的另一全新资源验证兼容，禁止拿旧known70试错。
owner只核schema metadata且关闭连接，再以actual app运行数据/权限查询；
app读alembic_version的42501为预期拒绝，不能为collector扩权。
版本化SQL固定queryID/参数/列/OID/返回shape，禁止不存在的outcome/max_attempts列。
精确table集合；列/约束/trigger/函数只核工具实际链相关范围，不新增全库审计平台。

阶段从NOT_RUN开始，进入前记ENTERED，实际结束才PASSED/FAILED；未进入保留NOT_RUN。
公开失败只含固定stage/code、queryID+SQLSTATE或DTOloc/type。禁止原异常message、SQL/参数、
DTO input/ctx、secret或未过滤业务值。数据快照失败不能阻断独立lifecycle/OS/归属/清理。
实际负例CLI必须非零；suite的expected rejection另字段，不把负例进程exit0包装为成功。

## 完整正向与必要矩阵

同一冻结候选、新合成20item/2000 fixture：native加载/低权SQL/DTO/preflight/arm/
一次持久消费/原Factory与ledger/恢复协调→Base v1 complete verified+anchor→
C同item真实T6一次/原key GET→native v2原记录读回→正常重启/页面→独立stop/reap/cleanup。
SQL、权限、DTO、ledger、once和协调器都真实，Fake仅外部HTTP transport；不手工verified或写ledger。
计数分列native_factory_invocations、native_ledger行数、fake_transport_calls和真实network/secret/provider；
官方SDK纯内存对象构造单列，不把它当真实网络认证或WS启动，也不把Fake transport写成真实平台成功。
original/sender/reader/current来自新PG真实流程与同namespace的新Python进程，不复制真实历史。

必要失败覆盖来源污染/撤权/窗口混同/错hash/已消费/并发重复；数字串、nullable/required、
重复key、分页、内容和超时；加载/SQL/DTO/调用/采集/超时的安全诊断、非零退出与独立清理。
原键cold-process replay不得再arm、再POST或另造key，检查原ledger精确计数。
整体PASS仅在全部required阶段、reap/cleanup/归属和exit一致后生成；阶段通过不得提前签整包。

当前仅接口冻结；完整成功/必要失败/重放/独审与精确CI仍pending。
真实SDK/AppSecret/provider/manualRO关闭，原attempts3/Create SPENT1/旧资产和失败事实保持。
