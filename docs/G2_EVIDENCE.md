# P1-04 G2 技术探针证据

日期：2026-10-08，全部时间为 Asia/Shanghai。任务 [Issue #5](https://github.com/aning0922/commerceops-agent/issues/5)。实施 Worktree `/Users/aipuli/.codex/worktrees/102d/commerceops-agent`，分支 `codex/phase1-04-checkpoint`。

当前状态：技术源码与本机真实 PG/Graph 探针已有实际验证，**独立审核、精确提交 CI 和主控 Gate 裁决待完成**。不自行合并、关闭 Issue 或标记 Phase 1/main 完成。初始依赖为 P1-03 集成 `003d34b1cc9d02764feba3f4dcb298e3b5dd7422`；锁窗口交接后普通 merge P1-05 已验收 `a7005bd530b5983c60a447c2bd805e2f0906bd82`，最终控制文档基线另按主控通知核对。main 基线仍单独由主控记录。

## 修改边界

- 技术 Graph 使用既有 RunnerPort、Worker/队列与终止验证；没有修改其 port/lifecycle、正式 migration/业务状态机、共享 DatabaseSettings/PG grant、Compose 或 CI workflow。
- `checkpoint_probe` schema 只在测试随机隔离库创建。runs 保存冻结身份与启动标记；decisions 是仅测试管理端写入的 simulated 决定；receipts 使用 operation_key PRIMARY KEY、task_id UNIQUE、request_hash、result_ref。runtime 对决定只有 SELECT，对 receipt 只有 SELECT/INSERT；不将技术 schema 部署到正式业务库。
- 稳定 task UUID/thread、固定 `p104-checkpoint-v1`、固定单个 interrupt、官方 AsyncPostgresSaver、`durability="sync"`。可信 context 从 RunRequest/WorkerSession 及当前 PG task/principal/test shop 构造；不从 checkpoint、CLI organization 或 card/payload 取得角色授权。
- 仅从持久且绑定 task/scope/current principal/version/hash 的 simulated decision_ref 构造 Command(resume=...)。执行节点和终态恢复再查 PG 决定，不能把 checkpoint approved 字样当授权。
- 所有 Graph 节点为 async，串行 START → prepare → wait_decision → execute → END；不会启动额外业务线程或图内并行。receipt 提交与 checkpoint 是不同连接/事务，不能称 exactly-once。
- `scripts.pg_smoke` 仍运行原全部 integration/G1 流程，增加 passed stdout 的结构化 G2 证据收集；缺少必需 OS/crash/checkpoint 记录即失败。原 G1 标签 approval_mode=not_applicable 保留，新增 g2_process_evidence 各记录明确 approval_mode=simulated。

测试数据与结果统一标记 source_mode=postgres_technical、model_mode=not_used、approval_mode=simulated。没有真实模型、真实飞书/G3、正式 T2–T4、A01–A08 或补货 R11 通过结论。

## 锁定版本及兼容依据

新增唯一直接依赖 `langgraph==1.2.14`，`uv lock` 只新增 langgraph 1.2.14 / langgraph-prebuilt 1.1.0 / langgraph-sdk 0.4.6。保留 lark-oapi 1.7.3、websockets 15.0.1、langchain-core 1.6.7、checkpoint 4.2.0、postgres saver 3.1.2、psycopg 3.3.6 等原锁版本，没有全量升级，也未使用 uv --with 或项目外安装。

[LangGraph 1.2.14 元数据](https://pypi.org/pypi/langgraph/1.2.14/json)要求 checkpoint >=4.1.0,<5；[SDK 0.4.6 元数据](https://pypi.org/pypi/langgraph-sdk/0.4.6/json)要求 websockets >=14,<17，与已审 lark-oapi 的 >=11,<16 交集包含 15.0.1。实际 uv 冻结解析/安装、全部飞书离线 SDK 测试及真实 Graph/PG 测试已执行；不是仅凭交集判断兼容。

环境：macOS arm64 独立 Worktree；Docker 29.6.2 / Compose 5.3.1；容器 Linux aarch64，Python 3.12.13、uv 0.11.25、pytest 9.1.1。PG 17.11-bookworm digest `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826`，business revision `0001_task_foundation`。官方 checkpoint schema 为独立 checkpoints，迁移表 max(v)=9；沿用官方 setup，未手改其内部列/迁移号。runtime 是受限 commerceops_app，没有 PG host 发布端口。

## 实际命令与结果

可重复执行（从仓库根目录，Docker daemon 已可连接）：

```sh
python3 -m scripts.bootstrap_tools
uv sync --frozen
uv run --frozen python -m scripts.check
uv run --frozen python -m scripts.pg_smoke
```

首次准备回合仅 AST/差异检查，不计 Graph/PG 测试。锁交接前将准备源码保存为本地新增 commit 552ff41；提交前 dir/index/完整可达历史敏感扫描均为 0，再普通 merge a700，没有 amend/rebase/force。

第一轮（23:02:49–23:04:05，p102-5e4ee62ee2a4）：61 real PG（既有 58 + 初期 3 个 G2）/17.66s 通过。第二轮（23:07 起，p102-d3cd07a17c39）：74 real PG/32.83s 通过，补齐冲突、等待/终态和真实 Graph 不合作取消矩阵。两轮完整 G1 流程及 cleanup_exit=0；只能证明各自当时源码，不能替代后续改动的复验。

新增 checkpoint 写失败用例的下一轮曾 **76 passed / 1 failed**：测试错误等待已成功 prepare 的再次 barrier，实际恢复可跳过已持久成功的节点；超时不代表通过。保留 `.audit/p104-pg-final.log` 失败记录，自建资源清理成功。改为单次确定注入 barrier，断言 checkpoint 写失败不报告中断、恢复以 None 继续且最终可等待；另增加首次 checkpoint 前 resume 持久延期。

已确认复验：23:14:59–23:16:40，随机项目 p102-ae52f3f275b6，**78 real PG /44.52s 通过**（原 58 + G2 20），112 offline 正常 deselect，无 skipped。完整 G1 空库/重复初始化、约束、卷重启、保留卷重建、停库非零失败/恢复全部通过；仅清理该次自建项目/卷/镜像/秘密文件，cleanup_exit=0。

同期统一检查实际通过：112 offline/46.73s（78 integration 正常 deselect）、ruff/format、mypy 59 文件、23 Markdown、Node 24.21.0 工具链/TypeScript、Python runtime/dev/build 90 包和 npm 已知漏洞 0，dir/index/全部可达历史敏感扫描 0。保留 P1-05 SDK 两个 DeprecationWarning，未隐藏或当成真实平台验证。首次 lint 行长和 mypy 类型问题已定向修正；失败不抵作通过。

最终源码本机复验：23:17:27–23:19:04，项目 p102-6939dd8c6308，**79 real PG /41.47s 通过**（原58 + G2 21），112 offline正常deselect，无skipped，完整G1及cleanup_exit=0。新增已知退役v0保留版本并needs_attention，未建立checkpoint/调用START；之前的PG测试阻断共发生1次，定向修复1轮后78/79两轮实际通过，未增大timeout或绕过注入窗口。最终结构化记录见 [G2_PROCESS_EVIDENCE.json](G2_PROCESS_EVIDENCE.json)。最后统一检查23:20:45–23:21:36 exit0：112 offline/43.11s（79 integration deselect），其余lint/format、mypy59文件、23 Markdown、Node/TypeScript、90 Python包/npm漏洞查询与dir/index/history扫描再次通过。独立审核及CI结果另外回填本页/PR/Issue，开发者自检不代替独立审查。

## OS / checkpoint 结构化证据

`tests/test_checkpoint_pg.py` 使用 OS Popen PID、stdin/stdout async barrier、短事务和 supervisor wait；不以随机 sleep、租约或锁可获取猜测死亡。条件轮询只等待已知 job 提交，不用于定位 kill 窗口。每个用例随机创建 p104_* 独立 DB，finally 只删除该库；只 signal/kill 自己的子进程。

smoke 捕获五类必需记录并保存到忽略的 `.audit/pg-smoke.json` 中 g2_process_evidence。23:14:59 复验实际样例：

| 场景 | 真实记录和断言 |
|---|---|
| 正常中断/同 thread 跨进程恢复 | task/thread a17116f1-aacb-4e50-957c-0dbed89191c4；旧 PID10 exit0/OS wait，新 PID17；checkpoint 1f1c32b1-c85e-6068-8001-947de9e1fee8 有真实 pending interrupt；另 thread 0581bfe8-2a55-4f92-9179-de1b63effa85 可运行，Graph active 最大1；wait 重跑2次，prepare共1次 |
| receipt COMMIT 后/checkpoint 前 SIGKILL | task/thread b3b4bf36-2ea3-4a4c-a363-049845a44aa1，原 job 28bdb4bc-f3e1-489d-9eea-8de2e01b7c27；PID23 exit-9/OS wait，确认持久终止后 PID35 从已有 next 继续；原 result_ref ad0229df-547c-4b9a-a618-34c1a6d9aea9 重放不变，receipt数1，原 job attempts2；未再次 START |
| checkpoint 对照 | kill 前 checkpoint 1f1c32b1-d780-68bd-8002-96325851fcd9 有持久 decision_ref、没有 result_ref；receipt 已能从另一连接读取。恢复后 checkpoint 1f1c32b1-e147-64ce-8003-53f72946335c 保存同 result_ref |
| S01/S03 | 实际持锁时第二进程 WorkerBusy；锁连接失效后 async node 取消，runner_left 后原进程退出；过期 lease/未确认生命周期仍拒绝新进程，OS确认后已有 checkpoint继续。SIGSTOP 活进程用 waitpid(WUNTRACED) 核对，禁止确认或接管 |
| 不合作 Graph | async node 故意拒绝取消，runner未返回；Worker取消预算耗尽后 PID196 exit75，OS wait 后仍须持久确认才能启动，receipt数0 |
| checkpoint/receipt DB失败 | 对本测试库受限角色定点撤销写权限，实际 InsufficientPrivilege，不报告持久中断、不产生部分receipt；恢复授权后沿已有 next 继续，checkpoint中断真正落盘才返回 |

固定 key 的不同 request_hash 实际抛 PersistenceConflict；版本/task/hash 异常、丢失 started 后 checkpoint、伪造 approved payload、当前 principal 撤销均拒绝并持久 needs_attention。已有 receipt 或图终态从 PG决定/回执核对后收敛，不再执行节点。所有 IDs 为随机技术测试资源，不涉及真实平台数据。

## 恢复合同与后续限制

- pending interrupt 无决定：保持等待；未见首 checkpoint 的早到 resume 或决定先到：持久延期重读。pending 有决定：只用 Command(resume=decision_ref)。未完成 next：以 None 继续，不重复注入决定。终态：核对匹配的决定、outcome 和 receipt。started 后无 checkpoint、已完成无匹配 receipt 或身份/版本不能解释：needs_attention，禁止删 checkpoint 后重建。
- 已知退役技术版本 p104-checkpoint-v0 仅识别并拒绝，保留旧版本，不构建旧图/迁移 interrupt。未知非探针版本仍由既有 Worker unsupported/dead 门禁处理；本任务没有修改共享 Worker 合同，不能宣称通用版本迁移。
- [官方 interrupt 文档](https://docs.langchain.com/oss/python/langgraph/interrupts)的中断节点重跑/固定顺序、同 thread Command 恢复已用锁定版实际验证。[官方持久化文档](https://docs.langchain.com/oss/python/langgraph/persistence)与锁定版源码分别作为语义和实现依据，不用最新文档替代实际版本证据。
- 已读 LangGraph1.2.14 的 AsyncPregelLoop.__aexit__/AsyncBackgroundExecutor：取消可产生独立 exit_task，executor会等待底层 tasks。runner在返回前保守等待本调用期间新增的 async tasks，若不合作则交既有 Worker 硬退出和终止门禁，避免取消主协程后遗留 PG写入。该策略面向本单 Worker 技术进程，若未来增加长期后台任务须重新设计任务归属，不能直接放宽。
- saver3.1.2 的 to_thread 只执行纯 dump/load 序列化；SQL写入仍在 async psycopg/cursor 中。本图没有同步业务节点、自定义 serializer、外部发送或后台业务线程。不能据此承诺任意同步工具都可取消；未来引入此类工具须重新证明线程停止或进程终止。
- 正式计划/outbox ready、真实审批、补货多项原子事务及外部 unknown 窗口留给 Phase3/4；多 Worker/fencing、跨 namespace supervisor adapter 不在本任务证据范围。业务 receipt 幂等与 checkpoint 重放是分开的技术不变量，不提供外部 exactly-once。
