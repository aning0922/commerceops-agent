# P1-04 G2 技术探针证据

日期：2026-10-08（Asia/Shanghai）。任务 [Issue #5](https://github.com/aning0922/commerceops-agent/issues/5)。

当前状态：**prepared，尚未执行 Graph/PG 测试，G2 未通过**。实施 Worktree 为 `/Users/aipuli/.codex/worktrees/102d/commerceops-agent`，分支 `codex/phase1-04-checkpoint`。依赖基线为主控验收的 P1-03 集成 `003d34b1cc9d02764feba3f4dcb298e3b5dd7422`；main 状态由主控独立记录。

## 依赖协调窗口

P1-05 当前拥有 `pyproject.toml` / `uv.lock`。本准备回合未改这些文件，未在项目外安装依赖，也未使用 `uv --with` 绕过锁。收到主控交接后，须普通 merge 已验收的新集成基线，再更新依赖并实际运行。

候选最小 manifest 增量为 `langgraph==1.2.14`。2026-10-08 从 [PyPI JSON 元数据](https://pypi.org/pypi/langgraph/1.2.14/json)读取：Python >=3.10；langchain-core >=1.4.7,<2；langgraph-checkpoint >=4.1.0,<5；langgraph-prebuilt >=1.1.0,<1.2；langgraph-sdk >=0.4.6,<0.5。当前锁已有 Python 3.12、langchain-core 1.6.7、checkpoint 4.2.0、postgres saver 3.1.2。

[SDK 0.4.6 元数据](https://pypi.org/pypi/langgraph-sdk/0.4.6/json)要求 websockets >=14,<17，与 P1-05 的 lark-oapi >=11,<16 交集为 >=14,<16，15.0.1 可满足两者。**这只是元数据兼容依据，未完成 resolver/锁一致性、漏洞检查或实际运行验证。** 当前 P1-03 锁的 websockets 17.2 不能作为新 Graph runtime 兼容基线。

## 源码准备与边界

- 新增技术 Graph 和 PG probe adapter，直接实现既有 RunnerPort；未改 runner port、Worker/lifecycle、正式 migration、共享 DatabaseSettings/PG grant、CI workflow 或阶段状态文件。
- 所有节点为 async，固定 workflow_version、单个固定位置 interrupt、同 task UUID/thread，使用官方 AsyncPostgresSaver 与 sync durability。Graph 不调用模型，不执行正式业务审批、补货、外部平台或库存修改。
- 技术 schema 仅由隔离测试库初始化，receipt 使用唯一 operation_key、request_hash 和 result_ref；业务 receipt 事务与官方 checkpoint 连接分开。决定是受控 fixture 持久化的 simulated decision，runner 从可信 RunRequest/WorkerSession 构造 test context，并再次校验 scope、身份和所有权。
- 恢复源码区分首次调用、pending interrupt、未完成 next、终态/已有 receipt；无法解释、版本或 hash 不一致标记 needs_attention。图开始后的 checkpoint 缺失不能从 START 重建。决定先于中断观察时持久延期重读。
- 第一批 OS harness/test 源码覆盖：中断落盘后其他 thread 运行、正常 OS wait 后同 thread resume、receipt COMMIT 后 execute 输出/checkpoint 前 barrier SIGKILL 并重放同 receipt、第二进程启动拒绝、真实 Graph 在锁连接丢失时取消和未确认终止的启动阻断。
- 测试 fixture 的 seed 新增可选 workflow_version，原默认 g1-fixture-v1 保留；没有修改已创建 task 的不可变版本。

## 实际执行记录

本准备回合只执行 Python 标准库 `ast.parse` 检查六个改动 Python 文件的语法，以及 `git diff --check`；均成功。**未执行 imports、lint/typecheck、pytest、真实 Graph、PostgreSQL、Docker smoke 或敏感扫描。** 未提交、推送或创建 PR，不用源码/设计推导测试通过。

待锁窗口后完成必要的失败/冲突/版本/恢复测试与真实 Graph S01–S03，运行固定敏感扫描、统一检查和完整 PG smoke，记录实际时间、版本、checkpoint schema、DB 断言、独立 OS 进程/barrier 及自建 Docker 资源清理结果。随后提交精确 SHA PR/CI，交独立审核和主控裁决。

## 官方语义依据与待补范围

[官方 interrupt 文档](https://docs.langchain.com/oss/python/langgraph/interrupts)说明同 thread 使用 Command(resume=...)，中断节点从头重执行；[官方持久化文档](https://docs.langchain.com/oss/python/langgraph/persistence)提供持久恢复语义。准备源码采用这些合同，取消/checkpoint 的锁定版源码与实际行为仍待核验。

后续实际结果须标记 source_mode=postgres_technical、model_mode=not_used、approval_mode=simulated。技术 receipt 探针不证明 exactly-once，不计作正式 T2–T4、A01–A08 或补货 R11；正式计划/outbox ready、真实审批权限、内部补货多项原子事务和外部未知结果窗口仍留在 Phase 3/4。多 Worker/fencing 与跨 namespace supervisor adapter 不在本任务范围。
