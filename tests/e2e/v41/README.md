# V41 QA 本机进程监督基础

当前只实现六个固定模拟 recipe：normal、nonzero、timeout、observer_missing、cleanup_fail、
summary_fail。入口 `python -m tests.e2e.v41.runner run --recipe <固定名称> --directory <新绝对路径>`
不接受 shell、任意 argv、API/PG/Web 配置或动态测试代码；不能作为业务 Gate/部署工具运行。
本片仅启动短命 Python 子进程，未知 recipe 或已有目录拒绝。

新目录 0700，日志、注册和 JSON 0600；同源 HEAD/tree 与实际输入/解释器 bytes hash 前后核验。
每个子命令实际 wait/reap，deadline 使用本机 monotonic cap；timeout 记录实际 signal/native，
finally 停止自建 group，登记 PID/birth 后只清理本次已注册身份。外层对 worker 有 25s 上限、
真实 wait/reap 和剩余注册 group 盘点，不接管未知进程。这个固定模拟上限不是未来服务资源
窗口；Root 的 UTC/reserve/镜像/容器权限仍须另冻结，不能拿当前入口启动实际服务。

`checks.json` 保存 required probe/observer、cleanup、绑定与剩余资源；information refs 单列，
没有 pass 字段。observer native0 但无观测原件也失败。checks_pass 只汇总明确 required schema，
cleanup 独立决定 worker 退出，不能被必需检查的通过掩盖。写盘采用新 0600 临时文件、fsync
和 replace，随后才输出摘要；摘要异常另写 `stdout_summary.json`，不改已持久化检查事实。
父进程实际 wait 后写 `outer.json`，包含真实 worker native exit、timeout、日志/hash、回执/hash。
测试端另保存实际 outer CLI native exit，不能由 checks_pass 反推外层退出码。

纯测试使用真实子进程，覆盖正常、probe3、timeout后终止/reap、observer缺失、cleanup4、
持久化后模拟 KeyError/worker1，另验固定入口拒绝；不伪造 integration 字典或 transport。
pytest 原始失败与复核结果应保存不同新证据目录；不得用这些模拟代替 V41 StageGate。
V40 wrapper1、031/446 及旧业务失败原件只读保留，本片未复制其私配或私有异常。


`owned_manifest.py` 是后续新 owned driver 的只读 admission 接口，不是启动器：固定五类
场景（Shell、同源 KPI、商品订单、CSV、XLSX），只接受新 V41 namespace/DB/目录、精确
source/tree、0025/合同/API导出schema/前端schema/锁摘要、exact images、UTC父子截止与
至少180s清理余量；复用原公共 subnet 校验。当前API导出目标见精确提交62ab257，前端schema
仍须WEB精确来源核收。输入缺失/脏源码/旧namespace/窗口不足直接拒绝，无0024或旧私配fallback。
只返回PUBLIC_BINDINGS_VALIDATED_ONLY，实际image/IPAM/ports仍NOT_INSPECTED、runtime NOT_RUN。
后续真实启动接缝、HTTP严格响应及业务golden待精确已审schema/资源窗，不接受任意命令扩展。

`owned_driver.py` 新增 prepare/execute 固定入口，复用 V40 公共随机输入、Compose拓扑/镜像/IPAM
校验及低层进程监督；使用独立 V41 Case/0025/input pins/once/回执，不调用旧 Case.validate、
旧 execute 或0024诊断。prepare 只创建新随机0700/0600配置并封存摘要；execute先核Root显式窗和
当前源的新runtime handoff，再做真实镜像只读检查、模型冻结、新namespace、PG/迁移/双grant、
seed、API/Web/probe。停止writers后才采final facts，采集/stop失败也继续scoped down/inventory，
资源清理、命令native和日志hash分别写execution.json。此代码尚未实际启动资源或签运行Gate。

新grant接口当前仅预留为 `commerceops.entrypoints.v41_database` 的 grant-runtime/verify-runtime；
必须与API owner最终SQL/router精确源对齐、独审，再由Root提交固定runtime_handoff.json后才准入。
该文件目前不存在；不能靠提供旧配置、创建占位handoff或使用0024通过来启动。HTTP/PG observer
业务recipes在独立后续切片补齐，缺模块同样在任何Docker调用之前拒绝。CLI不是常驻部署器，
实际运行还需Root父监督/绝对UTC/资源专属准入及退出采集，不从纯测或prepare继承授权。

`http_recipes.py` 只发固定路由的真实httpx请求，使用当前Demo身份/Origin/CSRF/epoch/generation，
JSON响应由 `validate_response.mjs` 对精确V41生成schema用实际Ajv严格验证，无自动POST重试。
CSV/XLSX recipe走预览→原preview key只读查询→确认→原action key COMMITTED核验→显式同键十次
→PG一次效果/receipt/event→SKU查询/同源product_count，并附错误行INVALID/confirm拒绝无部分
效果和另一访客404。catalog recipe含旧version拒绝零写、标签读回、列表/详情一致、订单商品
关联、受控履约与原键只读核验。解析/事务内部故障注入、权限竞争、全KPI金标与浏览器Shell
仍待后续精确接线，不用这些候选recipes冒签全部六卡矩阵。

`pg_observer.py` 仅schema/tenant两动作，显式new V41 DB/0025/六表校验、READ ONLY、5s statement/
1s lock上限及Root deadline；动态标识仅固定TABLES通过psycopg Identifier引用，tenant参数化。
最终schema元数据不等于业务回滚/提交证明；每个recipe必须另核实际tenant事实。
本切片纯测只验证合成CSV/XLSX bytes、真实Ajv/精确已审b723schema与拒绝漂移，不发HTTP/连PG。
Node依赖来自已锁公开工具字节，未装依赖或联网。API路由/SQL/grant的最终精确来源到达后仍须
对齐状态码和接缝、独审再准入；当前runtime handoff未发布，所有业务执行仍NOT_RUN。

Root8cb合入后的strict schema已同步：JobRef.data_revision/parser/import_schema版本参与首次
confirm预检，preview保存值/请求值/当前fresh读取三方一致；已提交原键十重放保留原请求。
`kpi_reference.py`从原始seed账目独立按店铺自然日/Decimal核八项指标，不调用V41聚合；HTTP
候选recipe接入fixture摘要、同源类型、八指标及导入仅增加商品/未知库存的金标检查。金标纯测
覆盖TWD/CNY、未知付款、退款事件非结算、空分母、跨本地午夜/来源窗口、导入不造销量。
这是金标代码与静态输入验证，真实HTTP/SQL及并发、权限竞争/事务中断等专项仍待实际来源接线。

针对GATES9eb/Astra7954的recipes增量：成功响应核tenant/org/principal/epoch/generation及实际请求shop，
不拿session的null shop比较业务shop；PG计数增加shop参数，版本表明确business.alembic_version。
跨访客先证明自己店铺正向读取，再拒原tenant shop；只有明确登记的tenant独有上传商品作为
foreign-object404，合法共享fixture ID不再一律期望404。履约使用合同fulfillment_version、
十次同键/读回状态版本/不变订单字段，标签和履约均额外核当前scope三表各一次增量。按原
operation/key关联到具体receipt/event的更细SQL、库存末态、runtime来源/监听/保卷等HOLD仍
需后续切片和最终API SQL对齐，不能以本片纯测试或总scope计数声明全部runtime审查关闭。

来源/监听/保卷HOLD的准备增量：execute在任何Docker调用前拒绝占用端口和Next隐式读取的
四类.env文件（repo/frontend两处），并要求新case内0600/本UID的image-build.safe.json。
Root必须提供真实build证据，至少source_sha/tree、test_image_id、test_build_native_exit=0、
`runtime_files_sha256`（当前Git所有backend/tests/scripts及Python/锁输入文件）、实际本地
Docker Unix endpoint/server ID/docker binary hash；后续固定选择增量见下段。不是用任意占位handoff解锁。

driver在初始空namespace后、PG启动前，对exact image运行固定只读Python哈希程序（network
none、read-only、drop caps、无host mounts），逐文件比对宿主/Root receipt/镜像真实bytes。
sourcecheck有专属标签，timeout残余进入scoped cleanup；普通ID inspect不再等于同源证明。
实际源镜像尚未准备或执行，此增量纯测不代签真实容器来源。

首次API HTTP前要求实际运行容器、exact image、project/service/UID、loopback发布和只读runtime
mount；首次Web HTTP前以lsof+ps核实际listener在本次process group且仅127.0.0.1端点。仅readiness
200或ComposeCLI活着不能通过。PG卷模型拒external/改名，创建后保存名称/driver/CreatedAt/labels，
结束时要求同一元数据、精确非空预期卷列表；Docker卷没有另一个不可变UUID，不将名称冒称UUID。
终态重核HEAD/tree/runtime files、五输入、私配seal、build receipt及.env拒绝；seed导出是输出，
不再被误作不可变配置。注册业务对象末态/按key关联SQL等剩余runtime HOLD仍需后续切片。

后续安全policy补充：schema精确集合改为六业务表加v41_security_policy；observer单独核owner
初始化前0/后1行，global policy不进入tenant/shop业务计数，不作为GC效果。实际secret/version/
fingerprint轮换与低权拒绝待API精确SQL/CLI源，不能由singleton行数推断安全接受。
subjects.py在业务请求前以私有锁登记scope/原operation-key，ACK与原键GET观察分开并保历史；
同进程并发登记不丢写的测试只证明本机元数据原子性，不是PG并发验收。import_confirm回执另核
resource_id=job.id、resource_version=原job.version、before_revision=preview保存值、after_revision
=确认后有效版本，不错误套用商品/履约的version+1。登记后的最终业务PG采集仍待driver接线。


针对daemon绑定顺序P1与终态来源P2的离线增量：Root receipt另须提供已批准的本机Unix
`docker_endpoint`、`docker_server_id`、`docker_binary_sha256`和公开Compose插件绝对路径/
`compose_plugin_sha256`。不继承全局context。`fixed_daemon.py`在任何daemon调用前创建专属
空HOME/DOCKER_CONFIG与固定shim；auths为空、只链接已pin公开Compose插件，每次调用复核
解释器/Docker/plugin/config字节并显式固定--host，拒绝调用者覆盖host/context/config。
父驱动、公共镜像/IPAM检查、adapter、子HTTP探针和finally清理均使用同一shim。首个daemon
调用只读info核server ID；静态不符时零daemon命令，server ID不符时一次身份查询、零资源/
清理命令；namespace初始为空的清理资格仅在身份核收后登记。未读取旧credentials或改全局context。

`source_seal.py`逐一核所有Git跟踪常规文件的真实bytes/可执行位与HEAD blob，包含宿主frontend、
Compose和全部跟踪锁文件；另保存实际Python、Node、Next入口、Docker和Compose插件的路径/
字节hash/权限。执行前后各自落盘并严格比较，不再将HEAD/tree或镜像COPY子集相等单独记为
全来源UNCHANGED。此seal不声称未跟踪依赖目录中每个包已做供应链审计。真实本机短stand-in
进程只证明argv/env和上述拒绝边界；Docker、PG、API、Web和业务Gate仍NOT_RUN。

catalog候选进一步增加两次双请求真实HTTP竞争：两独立CookieJar绑定同一当前session，屏障仅
同步客户端发起，不伪称控制了PG锁交错。同key同文要求两次COMMITTED回执完全相同；不同key
使用同一expected version/revision，要求恰一COMMITTED与一VERSION_CONFLICT/SNAPSHOT_CHANGED，
再GET两原key分别确认winner回执/loser UNKNOWN。每轮核商品version仅+1、赢家tags、原价/库存/
source不变及scope内receipt/event各+1；已存在tag行只更新，不能把tag行数再+1当作唯一效果。
细化到原key关联的实际SQL仍待最终0025列与apply接线，当前计数不能代签它。
每次POST使用独立私有request文件保存原payload与ACK，避免旧单一pending文件在并发时互相
覆盖；subject原key登记不变。transport异常保留原UNKNOWN并使场景失败，不自动POST/新key。
并发判定纯测只证明候选断言边界，未发HTTP/连接PG，不是并发运行或事务回滚证据。

精确772ecc6/c3c2a797后端接缝读取（取代先前猜测的v41_database预留）：实际router是
commerceops.entrypoints.v41_http.install_business，create_app在enabled DemoConfig时安装，
现有tests.e2e.v4.owned_api通过该factory可组装业务API。owner激活/grant只有
v41_security.activate_policy(db,config)与v41_runtime.grant_runtime(db,config)；精确提交内没有
policy/grant/verify CLI。runtime_definition.json绑定此快照八源码hash、实际helper和三个CLI=null，
明确HOLD P2-S02/P1-S04；不是可启动handoff。runtime_handoff.json仍未创建。driver移除不存在的
模块名并保留daemon前硬拒，不能靠手填READY或占位handoff跳过未实现owner setup。

最终业务采集准备已接入driver：stop_writers、API stop和所有owner oneoff退出确认后，将锁定
subjects原件导出为新私有owner/export/v41-subjects.private.json；PG关闭前运行固定subjects --final
观察器。全程READ ONLY/statement5s/lock1s；固定512KB有界、逐级no-follow/UID/0600文件边界。
final_facts按真实tenant/org/shop推导唯一owner session，再按完整scope+原operation/key查询
receipt/event/effect与job版本/parse_state/slot/pid/process/proof，不用中途scope计数或schema
元数据代替。旧tag行被后续版本替换时单独标记，按原请求重建历史payload/事件摘要；不把
“当前无旧receipt引用”误判重复或丢失效果。原ACK/读回UNKNOWN保留，与最终DB有无提交分列。
终态同时校验实际fixture完整摘要与固定seed来源，并采合成sku/库存/订单金额/退款原件；导入
价格等在实际effect内容中保留。这里只是实际SQL接线；未运行PG，stop_proof字段自洽也不证明
真实reap，S04必须另验内核Popen wait/真实低权攻击，不能由这份读取签安全接受。

审查c334的D04/R05准备修复：执行前后都遍历frontend/backend/tests/scripts实际文件集，拒未批准
的新源码/目录symlink；只明确排除frontend/.next、frontend/node_modules、__pycache__与
frontend/tsconfig.tsbuildinfo，根.audit/.venv/.tools不作为运行源码目录。普通业务GET要求顶层
status=OK；receipt/preview_lookup保留合法UNKNOWN语义。纯复现与断言测试不代签浏览器/HTTP实跑。
