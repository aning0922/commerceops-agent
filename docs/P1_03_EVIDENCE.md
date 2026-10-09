# P1-03 持久任务与单 Worker 证据

日期：2026-10-08，时间为 Asia/Shanghai。任务 [Issue #4](https://github.com/aning0922/commerceops-agent/issues/4)。实施会话 `01a11ba9-e456-7e93-9b5d-4f02c7731e23`，Worktree `/Users/aipuli/.codex/worktrees/778c/commerceops-agent`，分支 `codex/phase1-03-worker`。基线为已验证 G1 的集成 `662fb575c377b174135bcf4755ba6d866dfe6cbb`；main 基线仍 `a0d521ed79505287fa61bb6ddf82640e97824257`，本任务未自行合并或关闭 Issue。阶段事实由主控记录。

## 实现和证据边界

- application T1 技术 test 上下文 + PG adapter；inbox/task/首 job/audit 原子提交。成功回执在 commit 后，event/message 逻辑键去重并核对语义。
- `queue.py` 使用真实 PG 短事务领取、续租、完成、延期、dead；状态更新校验 scope/task/status/owner，同一 job UUID 重排而不复制 job。数据库时钟用于 available_at 和 lease。
- `worker_lock.py` 专用 session advisory lock + 既有 audit append-only 生命周期。锁丢失不等于进程结束；未确认 started 或未知 running owner 阻止启动。正常 stopped 也须经同 namespace OS PID 已消失核对，再 termination_confirmed 才允许重排。
- `Worker` 串行执行所有 analyze/resume/recover，15 秒心跳/60 秒 lease，单槽、有限重试、取消预算及非合作调用硬退出；`RunnerPort` 留给 P1-04 接入真实 Graph。
- 仅新增 Worker/application/测试文件和 DEVELOPMENT/本证据页；无 migration、新表/字段、依赖锁、共享 DatabaseSettings/TaskRepository、Compose/.github 或主控状态文档变化。

证据标签固定为 `source_mode=postgres_technical`、`model_mode=not_used`、`approval_mode=not_applicable`。所有 P1-03 runner 是受控替身；interrupted 不表示真实审批或 LangGraph interrupt。未验证真实 LangGraph/checkpoint 恢复、G2、平台 SDK ACK、正式 T2–T6、库存/审批/补货/outbox/多 Worker/fencing；不将这些记为通过。原 G1 checkpoint 读写/卷恢复是既有 PG smoke，不是新增 Graph 恢复证据。

## 实际测试

环境：macOS arm64 的隔离 Worktree，Docker daemon 29.6.2 / Compose 5.3.1；测试在 Linux aarch64 容器里执行，Python 3.12.13 / uv 0.11.25 / psycopg 3.3.6 / pytest 9.1.1。PostgreSQL 17.11-bookworm，镜像 digest `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826`；business revision `0001_task_foundation`，runtime 使用受限 commerceops_app，无 PG host 发布端口。

实际命令：

```sh
uv run --frozen python -m scripts.check
uv run --frozen python -m scripts.pg_smoke
```

首轮 21:33:22–21:34:08，项目 `p102-26a4c218688b`：25 real PG 通过/1 失败。非合作 runner 忽略取消后 asyncio.run 收尾仍等待，外层退出无法发生；已将硬退出移到协程启动层、在事件循环收尾前处理。该失败未记通过，清理 exit=0。

修正后 21:35:06–21:36:05，项目 `p102-eeac0824dce7`：29 real PG / 6.65 秒通过，无 skipped；完整原 G1 空库/重复初始化/持久卷重启/同卷重建/停库非零失败和恢复通过。持久样例 task=thread `38e5c47a-d4ed-4741-adfc-a977206a1c61`，三次回读 inbox/jobs/audit=1，checkpoint marker 一致；只清理自建项目/卷/构建镜像/秘密文件，exit=0。随后补充双去重键拼接拒绝、未知 running owner 阻塞、终止确认幂等及同 PID namespace OS 死亡校验；最终结果见下方补齐记录，不以本轮替代新代码测试。

正常 stopped 路径收紧前本机 21:41:22–21:42:22，随机项目 `p102-62c0cbddcdc2`：该轮代码 **31 real PG / 7.41 秒通过**（原 G1 13 + P1-03 18），42 offline 被正常 deselect，不是 skipped；新双键冲突/未知 owner/终止确认幂等/同 namespace OS PID 校验均执行。完整原 G1 流程仍成功，task=thread `f9f45b81-756a-43f6-96cd-f0ab699339d4` 三次回读 inbox/jobs/audit=1 与 checkpoint marker 相同；清理 exit=0，未删除未知资源。构建镜像由冻结锁安装，未改依赖。

同轮 `scripts.check` 实际成功：42 offline / 47.44 秒（31 integration 正常 deselect，无 skipped）、20 Markdown、ruff/format、mypy 40 文件、项目 Node 24.21.0 工具链及 TypeScript、85 Python runtime/dev/build 包和 npm 已知漏洞 0；当前/index/完整可达历史敏感扫描均 0。本地 `.audit/p103-check-final.log` / `.audit/p103-pg-final.log` 和 `pg-smoke.json` 是忽略的运行记录，不提交秘密/完整环境。阶段证据不以 check 脚本旧的笼统末行文字替代此逐项结果。

正常 stopped 路径也要求同 namespace PID 已消失，新增 OS 退出 barrier 测试。最终本机代码 21:45:28–21:46:33，项目 `p102-eac16da8abcd`：**32 real PG / 9.14 秒通过**（原 G1 13 + P1-03 19）、**42 offline / 44.94 秒通过**，均无 skipped。完整 G1 初始化/重启/重建/故障恢复仍成功，清理 exit=0。最终 lint/format、mypy 40 文件、20 Markdown、三层敏感扫描、Node tooling typecheck、85 Python 包和 npm 已知漏洞 0。最终正常停机路径也不凭 stopped 回执猜测进程死亡，OS 退出 barrier 后才重排原 job。

精确提交 CI 在 PR 创建后核对并记录，未运行前不称通过。

## 关键不变量与测试定位

| 合同 | 实际测试与断言 | 能证明的范围 |
|---|---|---|
| T1 | after_inbox/after_task/after_job/before_commit 四个钩子回滚，别的连接看不到部分结果；commit 后丢 ACK 返回同 task/job；重复入站双线程 barrier；disabled actor 与两个既有去重键拼接拒绝 | 真实 PG 技术用例，不是 SDK 投递 |
| owner / lease | 非 owner、DB 内 owner 被改变、状态已延期均拒绝完成/续租；短事务领取后其他连接 NOWAIT 锁行；默认 lease 约 60 秒；延期到期后同 UUID/attempt+1 | 单 Worker 所有权和事务，不是多消费者 fencing |
| S01 | 第一 OS 子进程在 entered barrier 持锁；第二 OS 子进程 WorkerBusy/非零，attempts 仍 1 | 真实 PG 启动互斥 |
| S02 | analyze/resume/recover 三任务最大活跃数 1；interrupt 后下一任务进入；SIGTERM 取消当前调用后 wait OS 退出，重启取回原 job / attempt=2 | 受控 runner 串行、中断释放槽、进程重启队列持久性 |
| S03 | 只 pg_terminate_backend 本测试 lock PID；合作调用取消/退出，非合作调用退出 75；过期 lease 仍阻止未确认恢复，task needs_attention；确认后同 job 重排 | 真实锁连接故障 + 受控调用取消，不证明真实 SDK 取消 |
| 正常 stopped | 已追加 stopped 后，受控旧进程仍在退出 barrier 存活，新 Worker 拒绝；OS wait 后自动核对 PID 已消失，追加确认才重排 | stopped 不是死亡证明 |
| S03 活进程 | SIGSTOP + waitpid(WUNTRACED) 确定旧进程仍活，锁释放/lease 过期后新进程拒绝，终止确认也拒绝；SIGCONT 后取消退出再 wait | 无 lease 热接管、无未证实死亡自动恢复 |
| 有限失败 / 版本 | retry 三次后 dead，新任务可运行；不支持的 workflow_version 不调用 runner、不修改原版本 | 调度合同，不是业务状态机/旧图迁移 |

测试代码为 [test_worker_pg.py](../tests/test_worker_pg.py)，OS 进程受控 runner 为 [worker_process.py](../tests/worker_process.py)。每个测试随机建独立数据库并 finally 删除自己的库；进程只 signal/kill 本测试 Popen PID，stdin/stdout 和 OS/事务 barrier 不使用随机 sleep 猜竞态。等待已知 job done 提交采用有界条件轮询，未用轮询推断进程死亡。

## 交接与限制

启动/停机/终止确认/恢复命令及 P1-04 port 合同见 [DEVELOPMENT Worker](DEVELOPMENT.md#p1-03-t1-技术入口与单-worker)。`job done` 与 `task completed` 分开；业务状态和 checkpoint 均由真实 runner 持久化。重新排队不改 kind/payload_ref/thread/workflow_version，终止确认必须先 OS wait 且同 namespace PID 已不存在；PID 复用或跨 namespace 不可证明时保守阻塞。跨容器 supervisor adapter、官方 Graph 取消及持久恢复须后继验证，不能用确认参数文字绕过 OS 检查。

初期 lifecycle 在 append-only audit 里查询，未新增索引/迁移；小规模启动查询可接受，未来性能变更须协调 migration 所有者。未关闭、未删除或覆盖旧 lifecycle 回执。技术 CLI 信任本机部署操作者及受限 DB 配置，未开放业务 HTTP 入口；不能称为生产租户 RLS/DBA 安全方案。尚未验证真实业务的 needs_attention 恢复解释或 Graph 节点副作用幂等；本 PR 等待精确 SHA CI、独立审核和主控集成核对，不自行推导阶段 Gate 通过。
