# V4 owned driver ce51精确接线独立审查

日期：2026-11-03（Asia/Taipei）。**结论：P2_REQUIRED_CHANGES，0 P1 / 5 P2；暂不签该driver的execute资源准入。** 问题影响范围逐项分列，不撤销已审backend/API/SQL组件；自然TTL专项和旧M3 Full未交付/未运行不作为本提交缺陷。

candidate `ce51c42d629da4db339f0100ad60879fd2a465fc` / tree `267181bf3f88c542369f9347ca45c97282e3db3e`，parent `d9b1600b0fc3151e51947dad7a2e6aa4cbec19f1`。只审7个QA新增文件及其实际调用的已提交supervisor/HTTP/PG事实/schema模块；另以已审WEB63a核本次启动环境。未读取WIP、未启动容器/PG/API/Web或执行真实case。

## DRV-01 [P2] API foreground包含PG依赖，退出生命周期未隔离

位置：`owned_adapter.py:101–112` launch_spec及`owned_driver.py:362` stop_writers。

实际launch为attached `docker compose up --no-build --pull never v4-api`，而合并后的v4-api明确depends_on postgres，未指定--no-deps。停止supervisor的api进程组会SIGTERM这个Compose up；attached up收到SIGTERM会停止它所管理的容器，不能用“PG此前由另一条up -d启动”推导它不会被当前依赖生命周期接管。当前组合因此不能保证后续final PG inventory/snapshot之前PG仍在线。Compose进程存活也不独立证明API容器存活，默认up未要求返回所选API容器的退出码。此结论来自命令/合并模型及官方生命周期语义，**没有声称已经实测PG提前停止**。[Docker Compose up官方说明](https://docs.docker.com/reference/cli/docker/compose/up/)

最小修正：PG明确先healthy后，API foreground只管理v4-api（例如--no-deps并明确API退出码传播），不能把PG纳入writer停止集合；补启动argv/停止顺序检查，并在ROOT实际窗口用容器状态证明API已停而PG仍在、最终只读事实完成后才down。不要以SIGTERM后Compose native0签业务成功。影响所有需要最终PG取证的case，故当前整套execute尚不准入。

## DRV-02 [P2] bootstrap_restart把合法200 UNKNOWN当成错误404

位置：`owned_negatives.py:64–66`。

确定CAPACITY_LIMIT后，原bootstrap仍未过期、create_request_key已绑定但没有receipt。已审DemoStore.operation对此返回最小data={operation,request_key,status:UNKNOWN,recovery:WAIT_READ_ONLY}；HTTP operation经reply返回200/OperationEnvelope（外层OK），不是404/FailureEnvelope。新scenario却只接受404，并检查外层status=UNKNOWN，必然拒绝正确后端。

独立从ce51精确源码的真实HTTP route+StubStore复验同形状最小恢复响应：HTTP200、外层OK、data.UNKNOWN/WAIT_READ_ONLY，native0/未调用DB。这与已审store实际分支静态一致，不是为了配fixture改后端合同。最小修正：对原key接受200并严格核原operation/key/data.UNKNOWN/WAIT_READ_ONLY以及无敏感字段；错key/错operation才另测404 UNKNOWN。影响仅bootstrap_restart，不能把此假失败归为真实PG恢复错误。

## DRV-03 [P2] WEB缺少显式local_http，实际Demo收到null origin

位置：`owned_driver.py:333–337` Web进程environment。

driver仅传COMMERCEOPS_API_ORIGIN=http://127.0.0.1:<port>，未传COMMERCEOPS_WEB_TRANSPORT=local_http。已审WEB page只有该变量精确等于local_http才允许http origin；否则approvedApiOrigin返回null，页面虽然HTTP200但展示服务未配置、入口禁用。独立用WEB63a精确origin函数执行纯Node探针：当前环境条件返回null，加显式local_http后才返回配置origin。

最小修正：在该明确owned loopback WEB环境中补准确transport变量并加配置接线断言；不得放宽前端origin安全函数。影响实际Web可用性/readiness含义，不代表当前httpx API场景本身全部失败，也不因此要求本driver实施尚未交付的浏览器验收。

## DRV-04 [P2] owner observer失败的实际native/安全结果未保留

位置：`owned_adapter.py:22–57` _facts，对照driver.checked的records处理。

observer subprocess非0只抛固定RuntimeError；实际returncode及安全stdout被丢弃。TimeoutExpired同样没有记录该observer的action/name/native=None。父probe main最终仅输出FAILED_OR_UNKNOWN，driver最多留下scenario进程的native1，不能恢复真实observer是1、137还是超时；final采集observer同样会丢其原退出事实。这里“不泄漏raw”与“保留native/UNKNOWN”可以同时满足，不能用统一unknown覆盖已经观测到的native。

最小修正：按每个具名observer保存限定字段记录（case/action/容器name、native_exit或null、TIMEOUT_UNKNOWN/安全结果状态），非0/JSON解析失败先持久记录再抛；不保存stderr、secret或未经验证任意payload。让父case最终回执可引用该记录，禁止失败后自动重试。影响全部observer及负例写夹具失败的可审计性；旧结果不回填猜测。

## DRV-05 [P2] owner/observer run未显式约束no-pull与本地镜像存在

位置：`owned_driver.py:295` owner命令及`owned_adapter.py:26–42` observer命令。

PG/API的up明确--pull never，而两类pg-test `compose run`没有此限制。独立Compose config显示pg-test继承原build配置，pull_policy为空；Case仅核image ID字符串形状，没有确认本地存在。若Root绑定镜像缺失/被清走，不能保证这两条命令仅拒绝而不按Compose策略尝试获取/构建，违背本driver声明的no-build/no-pull。此为缺失镜像失败分支的防护缺口，**未发生实际拉取或构建**。[Docker Compose run选项](https://docs.docker.com/reference/cli/docker/compose/run/)

最小修正：执行前只读核两精确本地image ID存在且符合ROOT绑定，并对所有run显式never pull；确保继承build配置不能作为缺失镜像的fallback。镜像缺失应在任何case服务/owner action前固定失败，不能换tag、build或pull补齐。补所有launch路径及missing-image拒绝的纯测试，不改旧Dockerfile。

## 已核安全边界及正向结构

Case固定project/database模式、source/tree/clean、0024实际hash、本地digest形状、当前UID、不同loopback端口与180–1800秒窗口；prepare独占新canonical目录700及文件600，生成新owner/app/CSRF/nonce，runtime只有app密码副本和新web/demo配置。env-file不含秘密值且拒绝shell/Compose元字符。execution.once独占，已有label对象（含停止container/network/volume）拒绝且不清理旧对象。root-opened-window标志是ROOT意图，不是凭标志自动授资源预算。

独立解析真实三文件Compose合并模型（只运行`docker compose config`，无daemon资源操作）：PG ports=[]、网络internal；API宿主host_ip=127.0.0.1，只挂/run/v4_api，secrets=[]且没有COMMERCEOPS_DB_* owner环境。pg-test独立挂owner路径和本批secrets；API配置600+同UID不应为Linux挂载便利改成世界可读，实际读取仍待ROOT核验。prepare不复用旧M3 runtime目录；Docker context的HOME仅用于本机客户端连接，不向API传owner环境。

driver预先登记project后只清它的资源；supervisor管理自建进程组，stop_writers之后另stop API容器并查停pg-test遗留oneoffs，避免只杀Compose CLI就假称容器退出。随后设计意图是tenant inventory+snapshot，再down不-v、查容器/网络空并列保留卷。异常不自动重试，状态区分FAILED_OR_UNKNOWN/WRITER_OR_FINAL_COLLECTION_FAILED/CLEANUP_FAILED；DRV-01/04修复前不能签此顺序与失败证据完整。外层SIGKILL不会保证finally运行，ROOT外层绝对截止清理仍必需。

observer使用固定SQL/UUID参数，无任意SQL入口；snapshot/read facts真实只读事务、DB UTC和shape核验。credential/grant撤销是明确owner负例夹具写入，不是“只读observer”整体都只读；它们限本tenant映射、固定对象数量、SQL/lock timeout，final标志拒绝两种写分支。API不拿这条owner连接。当前设计最终facts用reserve0的子budget、外层timeout仍限制cleanup；不会把最后采集当新业务窗口。

HTTP Visitor使用真实httpx/CookieJar、trust_env=false、无POST重试；strict_response调用锁定Ajv验证冻结baseline，无放宽schema。部分ACK丢失是实际请求后丢弃body/恢复旧jar的明确测试模拟，不是网络硬故障；并发same_key_reset与串行capacity范围分列。driver启动WEB但browser字段明确NOT_RUN，不能据Web200签视觉/键盘/跨tab Gate。

## 独立验证与范围

精确ce51快照下定向 **13 pure PASS / 0.21s / native0**；这些测试主要覆盖prepare/配置/部分命令失败，不覆盖本文5项实际接线缺口。另有上述纯ASGI200-UNKNOWN探针、纯Node origin探针及Compose配置展开。首轮配置展开未启用test profile，Reviewer检查pg-test键时KeyError；随后只补--profile test重新展开成功，未启动服务、不是运行Gate失败。未复跑不相关QA测试。

当前源码父链只含d578，真实执行必须先由ROOT集成已审534解析、1208 SQL修正及准确WEB来源；不能直接拿ce51独占分支当最终运行源码。Root转交身份PG进行中的结果不写成QA执行。自然TTL45分钟只是NOTIMPLEMENTED计划，现driver30分钟上限与180秒reserve保持，不因该缺项要求本包扩窗。旧M3 Full/动态PG/Web/N01另行准入，不以此11场景替代。

请QA局部修复上述5项并普通提交精确SHA。当前可继续代码/driver准备；实际execute待修复复审与ROOT具体source/image/project/端口/UTC回执后再准入。Reviewer仅提交本报告，未修改作者源码或启动资源。


## 8196增量复审：DRV-01—05关闭

日期：2026-11-04（Asia/Taipei）。candidate `8196e628213a9ec5f8ed8c6542f89c213bf60914` / tree `8f2401abea10c96ff692f3b9080bd17434020d4c`，parent ce51。**结论：ACCEPT_PREPARED_11_HTTP_DRIVER，增量0 P1 / 0 P2，五项均关闭。** 可以交ROOT为这11个既定HTTP场景登记精确集成source/image/project/端口/UTC并开新窗口；本结论不自行产生资源授权，也不签任何实际case成功。TTL/browserMode/200%真实GUI不在此代码接受范围。

DRV-01 CLOSED：launch_spec实际API argv为up --no-deps --exit-code-from v4-api --no-build --pull never v4-api，PG仍先独立启动healthy；没有把postgres作为API foreground目标。--exit-code-from的终止语义只限该次无依赖API服务，不得以Compose正常SIGTERM退出冒签业务结果。原stop_writers→显式API容器stop→遗留pg-test停止→final PG facts→project down顺序保留。真实API已停/PG仍活及最终停止仍需窗口证据，本轮未启动容器。

DRV-02 CLOSED：bootstrap_restart实际check改为HTTP200，再以精确dict相等核data的session_create、原request_key、UNKNOWN、WAIT_READ_ONLY；额外tenant等字段也拒绝，原strict validator仍先执行。正确原key最小200不再被误判404。DRV-03 CLOSED：实际Web启动使用web_environment，明确加入COMMERCEOPS_WEB_TRANSPORT=local_http且保留精确loopback API origin，不放宽WEB函数。

DRV-04 CLOSED：prepare新增独占700 observers目录，所有运行/最终采集adapter均明确传该目录；_facts对每个具名observer在finally写独占600 JSON。记录case/action/container、实际native_exit（137不丢）、timeout时null/TIMEOUT_UNKNOWN、坏JSON时0/INVALID_FACT_JSON和有限safe_status，再向上传播失败；不写stderr/raw payload，父receipt引用observer_records路径。FACT_OBJECT_RECEIVED只表示收到JSON对象，后续各facts模型/数量断言仍负责验证，不能把记录标签当业务PASS。没有自动重试。

DRV-05 CLOSED：任何服务前verify_images只读inspect两精确image并核.Id；缺失/不同即失败。展开test profile的原三文件模型，只保留postgres/pg-test/v4-api、删所有build并设pull_policy=never，独占保存内容hash；后续compose重新核hash并使用该冻结文件。所有owner及observer统一owner_run，明确--no-deps --pull never；up仍--no-build，无缺失镜像的build/pull fallback。未修改旧Dockerfile/共享compose。

独立精确快照运行原13项+新增15项：**28 passed / 0.14s / native0**，涵盖新/旧准备边界、Q18错误key/operation/status/敏感extra拒绝、Web环境、APIargv、missing-image停止、137/timeout/坏JSON先落盘且无哨兵。另独立将实际三文件Compose展开后交精确no_build_model函数，再用Docker Compose config重解析其输出：native0、恰三个服务、build映射0、全部pull_policy=never。全部是纯测试/配置展开，无daemon资源启动。

首次独立模型验证脚本受Reviewer当前tests包遮蔽，import精确快照模块失败（ModuleNotFoundError），未触及服务；随后改为从精确Git AST提取同一纯no_build_model函数完成上述重解析。原28测试结果没有重跑或覆盖。真实Linux UID600挂载、image/source一致性、driver完整异常清理仍须ROOT实际记录；本轮并未验证whole E2E、自然30minTTL或浏览器视觉。原ce51五项发现与失败边界完整保留。
