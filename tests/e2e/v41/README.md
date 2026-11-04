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
