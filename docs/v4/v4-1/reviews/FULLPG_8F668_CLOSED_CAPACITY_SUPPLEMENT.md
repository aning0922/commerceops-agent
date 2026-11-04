# V41 旧 FullPG existing-r1 闭合证据补充审查

日期：2026-11-04（台北）。结论：`ACCEPT_OLD_CASE_GLOBAL_DEADLINE_CLASSIFICATION_AND_INDEPENDENT_CLOSURE_NO_RUNTIME_GO`。旧案确认由 helper 总截止截断并已独立关闭，**不是 FullPG 通过**。已冻结的 [45/55 分钟容量方案](FULLPG_CAPACITY_E7AE_CONDITIONAL.md) 第一项旧案分类与关闭前置条件已满足；其余新案来源、镜像绑定、动态集合、资源和绝对 UTC 条件保持。Root 可据此决定新案准入，本回执不启动或授权运行资源，不保证新窗口必过。

## 来源与校验

旧案精确 source `8f6687560bb5c71804fd249068e2a9912fe35556` / tree `020b540b3684b277dd994752745a8b2779319671`，owned project `p123-1c0b9b89188c`。只读证据目录为 `/Users/aipuli/.codex/worktrees/commerceops-v41-gates/commerceops-agent/.audit/v4-1/full-existing-8f668-r1`。

独立读取并核 SHA256：

| 原件 | SHA256 |
| --- | --- |
| EXECUTION_RESULT.safe.json | `a6e53a6140de8c15f0b7da03fce50734d58540951e125a6b2d7a6a6f3c9a242b` |
| independent-cleanup.safe.json | `d2b6897158fd0f4009cd94756cf2ff199d5ec1da9a851e628771ba3e8760f3eb` |
| actual-runtime-images.safe.json | `ae46298c9cdfc86a6e6a73b8170bf8ce87ce94cdea3e8e5e827a1846ddacce8a` |
| checks.json | `003f734e7c86046cf13a39374da6049606b2855b9a9731a5aeb2b89a47ac71a4` |
| outer-receipt.json | `9e2617fd267cb32a5b0929c380ea4d0df81fe3e606b092a96dc3fe1d2a17cc04` |

前两份 safe 原件内容已审阅，后三份仅核字节 hash 与 provenance 一致。safe 所引用原 helper report hash `7b379df69fca7fc11b104ebf3d9b7b87978e28b50ecaeab8da146e1082a9aabd` 和早期 safe evidence hash `09a76c527785a23d9284b15784246ef8c456640af0ba992e334492fc820b3d01` 保留为来源引用，本轮未读取其原始日志或报告。未读取凭据配置、netrc/npmrc/pip.conf。

## 截止分类与未完成范围

独立重算 UTC 时间线：Root 起点 `06:08:00`，helper 截止 `06:43:00`，业务截止 `06:41:45`（expires−75），outer 截止 `06:58:00` / reserve300。helper 实际启动 `06:11:12.807789`，启动前耗时192.807789秒，启动时距硬截止1907.192211秒。

末组 `combined-existing-p4-create-and-template` 在 `06:40:11.153350` 启动，只剩93.84665秒有效业务预算；timeout 发生在 `06:41:45.018179`，即业务截止后0.018179秒。该组在 `06:41:49.908085` 结束，elapsed98.754735秒、native137、timed_out=true、stopping_confirmed=true。helper 在 `06:41:54.629716` 结束，parent 在 `06:41:55.146178` 结束；helper/worker/outer 均1，wrapper_wait_timeout、parent_timeout、parent_failure 均false。证据支持 helper 自身总截止截断，未耗尽该组名义300秒预算；native137不用于推断 OOM。

32条原生命令中31条完成且exit0/未timeout，一条被截断。24个计划测试组中20组完成、一组中断、三组未进入。已完成组最大耗时259.128855秒；collect native0/17.223121秒，小于原30秒。safe 未捕获已完成阶段的非通过或skip，不能据此推断被中断call会通过。

已复核节点列表长度和互斥关系：完整collection773，selected596；helper actual_node_ids577是模块收集数，**不是完成call或PASS数**。进入call568=567PASS+1中断；另28未开始，分别为template_results9、history14、read_reply_parent5。selected−helper actual=19，helper actual−call passed=10。V41新节点call通过28。此前565/31及摘要数字保留其时点，不作为最终计数。

中断节点为 `tests/test_p4_first_create_pg.py::test_c0_claim_denies_tampered_original_bindings_and_current_revocation`：有node_start、setup通过和call_start，没有call_end；结论保持 `UNKNOWN_INCOMPLETE_CALL_INTERRUPTED_BY_GLOBAL_DEADLINE`。G1 complete=false/count0，全部NOT_RUN。G2六项有实际记录：checkpoint_db_failure_recovered、cross_process_resume、graph_lock_loss_cancel、graph_noncooperative_exit、receipt_commit_checkpoint_gap、retired_probe_version_refused。G2记录不补签G1或整线。

## 独立关闭与新案边界

原cleanup exit0/stopping=true，elapsed4.674秒，owned_verified30/removed30。独立回执状态为 `INDEPENDENT_OWNED_CLEANUP_CONFIRMED_AFTER_ORIGINAL_FAILED_RUN`：精确project容器、网络、卷均空，临时pg_data已删除，runtime project目录不存在；35个注册进程组逐项ps native1且stdout/stderr为空、absent=true。独立Docker列表native0且为空，卷inspect1和30个容器inspect1均为预期对象不存在。

PG base image `sha256:bb26ccd46218e47cd66abecb2fc6ea36f3815584743b60e9b9eb9f7c1072d91f` 保留；safe确认source/tree干净未变、14锁/4runtime/3binary身份未变、other_assets_mutated=false及其他卷NOT_TOUCHED。这里核验的是独立采集回执，本轮没有再次调用Docker或进程探测。

最终旧案状态为 `FAIL_GLOBAL_DEADLINE_TRUNCATED_INDEPENDENTLY_CLOSED_NO_RETRY`。phase3仅准备、未执行；旧案重试未授权/未运行。旧失败与UNKNOWN完整保留。

新案仍应绑定已审 `e7aeeca90e98cc4af5b5f8f8ba0faddd33182bd6` / tree `4e8349cfeec323668be316426871bc310b6ce53d`，分别使用新独立checkout/audit/资源和实际镜像新binding，由Root登记helper45分钟/outer55分钟、reserve300及不可变绝对UTC。每命令300秒、collect30秒、expires−75停业务、cleanup最多60秒保持。新案标签existing-r2仍调用原 `--round 1`；不得复用旧round-1、续窗或只补未跑节点拼接结果。两线全量实际通过及同源pg_ci_evidence通过仍待新证据，工程、HTTP、browser和Native验收另计。

本轮仅safe文件只读、hash核对、时间及集合算术与审查文档检查；没有启动collection、pytest、PG、Docker、服务、浏览器、SDK、Full、CI或远端操作。
