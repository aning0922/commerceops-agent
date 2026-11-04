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
