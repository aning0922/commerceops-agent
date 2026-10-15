# P4 验收工具准备合同 v1

本合同属于[完整准备包](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6184152897)，
版本 `p4-acceptance-preparation-v1`。它定义 A/C 工具接口；源码存在或局部测试不表示准入完成。
总上限12 Agent有效h、A初分配5h、北京时间2026-10-15 22:01:35硬停不变。
Root在C交付432后调配其已确认空余：A cap为5.75h、C3h、Review2.25h、Root1h，
总额仍12h；A接近5.2h须报告，计入原预算，不续旧机器窗口。

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
def consume_stage(
    stage: str, handoff: Mapping[str, Any], *, handoff_ref: Mapping[str, str]
) -> dict[str, Any]: ...
```

stage仅 `t6`、`restart`、`page`。函数失败抛异常，调用方固定stage分类，实际最外CLI非零；
成功返回阶段证据，不生成整体PASS。若已有C内部函数，consumer可窄封装，不新建业务launcher。
handoff_ref独立携带原文件path及已校验原bytes的sha256，由共用loader交给C；不能用重新
json.dumps(mapping)的hash替代原文件hash，不能把自引用hash写回原JSON。
A在同一入口中执行native v2投影/外部原记录读回，不由C伪造Base已同步状态。

handoff固定顶层字段如下，实际值仅本轮合成资源的私有文件中存在：

| 字段 | 必需结构/来源 |
| --- | --- |
| contract | 精确 `p4-acceptance-preparation-v1` |
| candidate | source_sha、tree、manifest_file、manifest_sha256；actual_images各自id/source证明；lock及toolchain指纹 |
| resource | run_id、project、owner_label、volume、container_ids、registration_ref、runner_namespace、deadline_utc、cleanup_reserve_seconds |
| private_refs | web_config、app_database_config、web_credentials、external_records；每项path/sha256，配置内仅引用本轮新凭据；不得原env/Secret |
| fixture | case_kind及绑定预期item_count/quantity_total；organization_id、shop_id、principal_id、feishu_identity_id、web_identity_id、auth_version；task_id、source_task_id、plan_id、approval_id、decision_id、execution_id；item_ids、target_item_id、checkpoint_threads；schema_revision为完整revision |
| baseline | core=immutable_business(snapshot)原rows；checkpoints=checkpoint_fingerprint(snapshot)精确三表原rows；thread集合、排序/bytes编码合同固定，migration metadata另列 |
| base_ro | typed_result原生产ProjectionResult序列化；window_id、outbox_id、item_id、version=1、client_token、projection_hash、request_hash；pg_proof含target_key/external_id/verification_mode、delivery状态/完整唯一/observed_version、稳定anchor及真实SDK method counts；证据ref/hash |
| worker | epoch="base_ro"、owner、pid、namespace、process_started_id、termination_id、claim_id/claim_hash、reaped；来自原持久audit及实际OS/wait，这是已结束RO epoch，不代表当前app Worker活跃 |
| web | api_origin、web_origin、expected_item_path；仅loopback且必须符合本轮登记；实际服务image/container证明 |
| t6 | request_phase="unprepared"、request_key=null、action="close"、reason、expected_version=1；初态固定目标/语义，原生UI生成request key |
| candidate.toolchain | node_executable/node_version/node_sha256/playwright_root/playwright_version/playwright_package_sha256/browser_executable/browser_sha256/frontend_node_modules/read_schema_path/read_schema_sha256/ui_helper_sha256；均为实际冻结来源 |

app_database_config字节是实际app角色的原生DatabaseSettings JSON；C独立校验path/hash并按该对象连接，
禁止从Web配置猜派生连接或退回owner。该对象user必须commerceops_app，runtime_password_file必须null。
external_records引用不可变v1读回证据快照，实际Fake传输的可变存储由A continuation独立绑定使用；
native v2正常更新同一record后，不重写handoff或原v1快照。新v2仍须原SDK/ledger及PG typed读回核对。
PG不publish任何host端口，app连接host为postgres。Host阶段consumer通过共用窄桥接调用：

```python
def capture_bridge(
    kind: str,
    handoff: Mapping[str, Any],
    *,
    handoff_ref: Mapping[str, str],
    phase: str,
    owner: str | None = None,
    request_key: str | None = None,
    sdk_window_id: str | None = None,
    sdk_subject_ids: tuple[str, ...] = (),
) -> dict[str, Any]: ...


def app_lifecycle(
    action: str, handoff: Mapping[str, Any], *, handoff_ref: Mapping[str, str]
) -> dict[str, Any]: ...
```

capture kind仅snapshot/worker；phase为显式证据阶段，worker必须传当时app epoch owner，
不得fallback到base_ro。resource.runner固定container_id、namespace、python、entry、manifest_ref、
host_private_dir、container_private_dir、uid/gid和该context启动时登记的runtime期限。
共用桥接核immutable ID/image/owner/mount与manifest，再docker exec同一入口/hash；不启动RPC/服务器，
不从C WIP导入。Host与runner分别登记相同UTC截止对应的monotonic值，不跨OS复制monotonic绝对值。
resource.runtime为host固定期限，resource.runner.runtime为runner期限；resource.postgres_container_id
显式绑定PG，桥接复核其无PortBindings及同一volume/image。web.api_internal_port显式绑定API内部监听端口。

runner入口绑定app_database_config后新建真实app连接；snapshot将精确完整revision、fixture的Web身份/
auth_version/CP threads及实际请求key/SDK refs构造为C的CaptureContext，调用capture_snapshot(db,context)。
同时传三个必需keyword：case_kind=fixture.case_kind、expected_item_count=fixture.item_count、
expected_quantity_total=fixture.quantity_total，禁止默认或按观察值倒填预期。
worker另开app连接，仅调用capture_worker(db,organization_id,owner)。返回原typed安全结果及phase，
连接关闭后落本轮新私有结果ref，query失败固定分类且非零；不会退回owner或业务快照签cleanup。
app_lifecycle action仅start/stop/restart，在同runner内正常启动/停止原生API和单Worker进程，
返回该app epoch的owner/organization/pid/host/pid_namespace、started/termination及wait/reap证据。
其Worker不dispatch业务jobs，T6仍为原Web/API事务；v2由A在app Worker停止后单独原生受控投影，
不得同时再起第二Worker。restart使用相同PG卷与新app epoch，不借base_ro历史回执。
capture_bridge直接返回原collector dict并加phase。app_lifecycle返回：

```text
start:   {epoch:{owner,organization,pid,host,pid_namespace,process_started_id,reaped:false,...},
          active_workers:实际1,reaped:false,api_ready:实际true,volume,container_ids,stopped_epoch:null}
stop:    {epoch:{旧epoch及termination_id,reaped:true},active_workers:实际0,
          reaped:true,api_ready:false,volume,container_ids}
restart: {epoch:新active epoch,active_workers:实际1,reaped:true,api_ready:实际true,
          volume,container_ids,stopped_epoch:旧已回收epoch及termination_id}
```

顶层restart.reaped指旧epoch，新的epoch.reaped仍false。stopped_epoch为旧epoch的新终止证据副本，
不重写原start回执。当前正常restart范围为原生API及
单Worker进程、同一runner/PG卷；不冒称PG或Web已重启。Web重启由C原owner执行并另记。
active_workers来自原审计未确认计数，api_ready来自实际Server startup/进程状态，不补默认成功。

业务/claim ID为UUID标准串、artifact SHA256为64位小写hex；Git SHA/tree为40hex，image ID保留
sha256:前缀，container ID、UID、PID等使用各自原生类型，不能套UUID规则。
路径必须canonical且落在登记的新私有目录。
缺字段、跨candidate/resource/fixture、bool冒整数或未证明source必须拒绝，不能补默认成功值。
private_refs的hash是私有文件字节绑定，公共报告仅输出计数/布尔/hash，不输出登录内容/nonce/DSN/URL参数。

`t6`结果包含contract/stage、同candidate/resource/target引用、request_key、semantic_payload_hash、
typed_response、receipt_ref/hash、PG验证的request/actor/identity/auth_version/audit/outbox关联，
以及绑定case中仅同target从open/v1到closed/v2的实际计数；20项case另核其余19open。
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
父边界重建child固定安全字段；dto/dto_errors仅有界loc/type，cleanup_failure仅一层固定诊断，
不透传input/ctx/body/message、未知键或嵌套cleanup。实际stage/C固定code/SQLSTATE与非零退出保持。
实际负例CLI必须非零；suite的expected rejection另字段，不把负例进程exit0包装为成功。

## 完整正向与必要矩阵

Root已确认保留approved_first_create的单item execution规则，分列同一候选的两个新合成case：

- recover_single_item：主完整正向，新1item execution（冻结known_inbound数据，quantity_total="70"）。
  原C0→sender→explicit RO一次持久消费、verified/anchor→同target真实页面T6/原key GET→
  native v2同记录读回→正常restart/page→cleanup/exit和cold replay，对应未来原key真实恢复路径。
- batch_twenty_items：独立20items/quantity_total="2000"，使用原本支持该execution的普通
  approved_outbox原key RO及20项披露/一致性；不能标成explicit恢复通过，不降低M1的20SKU Gate。

fixture.case_kind只能取以上两值，item_count分别精确1/20，quantity_total必须显式正数字符串。
两case均不复制旧known70或真实身份。初始20项走C0被拒的实际失败保留；单item谓词是充分阻断，
未捕获完整异常位置时不将其写成该次或更早失败的唯一原因。

主链native加载/低权SQL/DTO/preflight/arm/一次持久消费/原Factory与ledger/恢复协调→verified/anchor→
C同item真实T6一次/原key GET→native v2原记录读回→正常重启/页面→独立stop/reap/cleanup。
SQL、权限、DTO、ledger、once和协调器都真实，Fake仅外部HTTP transport；不手工verified或写ledger。
计数分列native_factory_invocations、native_ledger行数、fake_transport_calls和真实network/secret/provider；
官方SDK纯内存对象构造单列，不把它当真实网络认证或WS启动，也不把Fake transport写成真实平台成功。
original/sender/reader/current来自新PG真实流程与同namespace的新Python进程，不复制真实历史。

必要失败覆盖来源污染/撤权/窗口混同/错hash/已消费/并发重复；数字串、nullable/required、
重复key、分页、内容和超时；加载/SQL/DTO/调用/采集/超时的安全诊断、非零退出与独立清理。
原键cold-process replay不得再arm、再POST或另造key，检查原ledger精确计数。
整体PASS仅在全部required阶段、reap/cleanup/归属和exit一致后生成；阶段通过不得提前签整包。

每个新UUID数据库在CREATE前进入同一冻结resource/registration的四项清单：legacy schema、
negative matrix、twenty fixture、single fixture/replay，明确owner、用途及保留关联。
CREATE成功立即写本轮O_EXCL回执；最终owner只读比对实际pg_database集合/owner及业务连接，
明确排除自身PID、随后关闭自身连接。已创建缺失/未登记库/owner错位/残留业务连接均拒绝整体PASS；
未进入的预登记步骤不倒填created。证据/replay库保留于自有卷，不DROP、不down-v。
load/SQL/DTO/call/capture/timeout固定子case均在同一entry/hash的实际新进程执行；
SQL42501、collector不匹配schema的42P01、实际callee签名拒绝、PG语句57014取消分别分记。
受控保持新legacy库app连接的inventory拒绝及连接释放后复核独立记录，不用组件DEV代签整体。

MATRIX阶段顺序使用新fixture运行原生准入与wire；两规范正例与预期拒绝分列，负例子CLI实际非零。
DTO或并发锁拒绝发生在Worker started前时，必须真实查询0 started并已OS wait/reap，
单列no-start，不补造stopped/termination。并发once使用同window/私有输入的两新进程，
原锁只容一个Worker；成功一次与拒绝一次、SDK/持久once精确计数及后续冷重放分别核实。
源码/字段/列/权限/调用/采集失败保留原固定code与实际外层stage，不以PREPARE覆盖T6等阶段。

收尾向登记的immutable容器ID显式发送SIGTERM并记录命令exit与发前running、wait/reap、
actual exit、OOM/error、端口关闭和资源归属。仅本工具确实发送信号的Web143可分类
expected_owned_SIGTERM；保留143，不伪装0。意外143、无信号证据或未知停止均拒绝。
API由工具持有停止handler，原Uvicorn正常serve结束后应先形成真实result/exit，不能补成功文件。

截至2026-10-15 06:45:27Z，run4五PG及run8两wire正例/13预期拒绝是已执行DEV证据；
run5资源reader、run6复制源码权限及run7 T6/停止失败均保留。
最终组合源码的完整成功/竞争once/冷重放/独审与精确CI以新冻结回执为准，当前不预写。
真实SDK/AppSecret/provider/manualRO关闭，原attempts3/Create SPENT1/旧资产和失败事实保持。
