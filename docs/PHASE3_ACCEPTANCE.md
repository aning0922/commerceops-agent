# Phase3 分层验收与剩余收口

当前导航（2026-10-11 A05）：Root已核A03 source052/Core5480529395/精确CI38079599247三job成功，以及B最终a65/Web5480795768完整24Web/native200/PG不变量/精确CI38085161901三job成功；完整337PG=236+101、G1三/G2六/cleanup0及精确配对已核。Root释放原A WT62c8/PR37正常集成及唯一共享frontend CI/阶段文档批，已普通合已审B，无冲突；最终增量独审、精确四job frontend Gate、main/合后CI/Issue33结案pending，不能预写阶段完成。main仍59b350cb719a9d2fed3f68b1ee598fa0a9b97875，Phase2已正式结案/CI38041779219 SUCCESS/Issue29 CLOSED。原333/988/旧失败/取消run/Review fullcheck not_verified/Issue23 not_identified/risk_accepted和M1设计18页冻结保留。D1=10-10/D30=11-08/300h/P3 A32+B18+Review10=60h不重置，人工H/L not_reported；新增paid0/平台业务写0，扩权/生产/Phase4未授权。见[STATUS40](STATUS.md#40-phase3-a05-正常集成与最终四作业候选)及[A05交接](PHASE3_A05_INTEGRATION.md)。下方原333/988/2e0待核表为历史；当前剩余仅最终集成增量Review/精确四job CI/Root main和合后CI/Issue33正式结案，平台边界不扩。

历史39节导航：748 business minfix原Core全101PG/32wire22/pure69已核无新P1/P2；Root另批两个独立PG CI job与安全metadata配对，仍需统一新source字节继承/CI delta/精确337CI，未以旧2e0失败或作者333替新Gate。见[容量批](PHASE3_CI_CAPACITY.md)及[STATUS39](STATUS.md#39-a03-business独审与独立ci容量批)。

历史独审修复导航（2026-10-11）：原2e0d3ed首模块独审23pass/1fail/157.75s（失锁before_graph/初始CP观测竞争），后续模块/wire未跑；原作者333通过和原CI不抵此阻断。Root派回本批两项最小修复，三态失锁/孤立记录/必要恢复邻接19实际PG通过；新collect337=236+101P3，未宣称新337作者执行通过。当前事实与新freeze/独审/CI待核见[PHASE3_A03_FIX1](PHASE3_A03_FIX1.md)。下方原333/988及原source候选为2e0历史证据，保留不覆盖新门禁。

2026-10-11作者收口候选；Phase3 in_progress，A03作者完整333PG/988offline/wire22/3G1/6G2通过，新freeze独审/精确CI待回执，B未合入A。main实时核为 `59b350cb719a9d2fed3f68b1ee598fa0a9b97875`。下表区分作者实际验证、已冻结历史Gate及剩余验收，不能据PR创建或测试通过提前称全阶段完成。实施/失败/资源/时间见[PHASE3_A03](PHASE3_A03.md)。

## 已冻结前置Gate

| 范围 | 冻结与独审 | 精确CI/Root事实 |
|---|---|---|
| A01 T1/T2/session | aeaa916a59341a6ffa4a89f863d065580599f6d3，独立39业务/40增量 | [38055767391](https://github.com/aning0922/commerceops-agent/actions/runs/38055767391) SUCCESS，actual9226da3/tree3dde1cde；952offline/236旧PG/35P3/3G1/6G2/cleanup0；[Root放行](https://github.com/aning0922/commerceops-agent/issues/34#issuecomment-6098087434) |
| 扫描策略批 | 9f4aee5afaa83b9999ef190eec778584efd988c4，独立14专项 | [38061513830](https://github.com/aning0922/commerceops-agent/actions/runs/38061513830) SUCCESS，238e/tree3dc37257，222规则与原四精确例外；不含A02/A03 |
| A02 T3/恢复 | 24856555fe23975fb19cd67ddcc033f6cac3905c/tree5306496d，Core无阻断，新独立24实际PG/155.72s+migration1/pure19/wire21；旧12/8 not_verified不替换 | [38064613062](https://github.com/aning0922/commerceops-agent/actions/runs/38064613062) SUCCESS，actual196d824ca2b3238d5491c494a3b813062587fcb1、main59+248/tree同源；978offline/236旧PG/59P3/3G1/6G2/cleanup0；[Root](https://github.com/aning0922/commerceops-agent/issues/34#issuecomment-6099399935) |
| B02只读会话 | source8365abf8bb40973964d7381345a244c78511bc16，无阻断Review，实际7PW/22Origin/17contract | [38063196793](https://github.com/aning0922/commerceops-agent/actions/runs/38063196793) SUCCESS；未合A，不证明写页面或A03 |
| B03决定接线 | sourceed34a7277bb792504180251a8960200ee80493e6，Root核独立10功能/200% headless/keyboard | [38068569167](https://github.com/aning0922/commerceops-agent/actions/runs/38068569167) FAILED，1000offline/122.84s、236旧PG/240.75s通过；聚合59P3在300s exit137。52started/51call+teardownpassed、1started未完成、7未开始，无已记录assert fail；不能诊断为已证实deadlock或旧#23根因。Gate未通过，不重跑旧head替新候选 |

## A03作者证据映射

当前运行源码基线248，A03为同WT未提交候选；最终freeze SHA从PR37新head/Root回执核，不在提交内部自指未来SHA。各完整模块的实际collection、命令、时间和结果已在最终收口表追加；本表节点名可直接定位测试，历史Gate不替代新候选回归。

| Gate | 实际节点/命令 | 已有实际结果及剩余 |
|---|---|---|
| migration/P2保留 | `tests/test_p3_migration_pg.py::test_current_p3_preserves_real_completed_p2_and_checkpoint_bytes`；新material三用例`original_hashes` | A01/A02冻结已核；A03最终迁移1passed/0.77s，material原P2十组行/CP哈希保持 |
| R01/from_report/new_cycle | `tests/test_p3_pg.py::test_r01_commit_before_ack_real_sigkill_replay` 两mode；T1并发/十次重投两个原task/job/receipt | A01已冻结真实kill；A03最终对应完整模块通过，精确时间见后表 |
| R05/R06/R07 | `tests/test_p3_approval_pg.py::test_r05_r06_r07_real_kill_old_process_gate_and_same_checkpoint_resume` 三barrier/early | A02已核；A03恢复后真实completed/T4消费，不再期待临时static pending；最终完整24passed/163.31s |
| R08/A05–06 | `test_r08_t3_commit_before_ack_real_sigkill_ten_replays`、`test_two_current_eligible_actors_approve_reject_race_has_one_winner`、语义同/异键测试 | A02已核；A03最终对应完整模块通过，精确时间见后表 |
| R09/A07–08 | `tests/test_p3_revalidation_pg.py` material三分支；`tests/test_p3_execution_recovery_pg.py::test_r09_replacement_commit_checkpoint_gap_reuses_one_version_and_early_t3_waits` 三分支 | 5实际PG/17.36s与恢复组8/40.92s，qty90/112/100、新approval/nonce/full确认、原P2不变；最终组另核 |
| R10 | `test_r10_r11_real_kill_whole_t4_transaction_or_permanent_replay_after_item_closed[after_first_t4_item]` / `[before_t4_commit]` | 初始单项真实全事务回滚通过；增强为两items/两intent，最终两item增强恢复8passed/40.21s |
| R11 | 同上`[after_t4_commit]` | 初始commit后CP前kill/关闭项/None原execution重放通过；最终两item增强恢复8passed/40.21s |
| R12/C04–05 | `tests/test_p3_pool_pg.py::test_r12_two_approved_two_item_plans_same_pools_second_whole_plan_has_no_effect` | 实际PG联批3/14.42s含此项：两计划已批准、单Graph串行、第二整批0items/exec/consumed；关闭两项后新cycle/newapproval/newitems；旧resolve只回旧receipt |
| R17 | `test_r17_delivery_boundary_kill_restores_none_and_one_permanent_execution` before/after delivery；`test_actual_pg_static_checkpoint_none_continuation_skips_start_and_second_decision`只读官方CP兼容probe；三个持久CP损坏/失锁prepare gap | A02真实旧shape+None probe已核；A03实际delivery kill重放completed，最终完整24passed/163.31s。兼容probe不冒称T4 |
| S01 | `tests/test_worker_pg.py::test_s01_two_os_process_startup_mutex`；`test_second_worker_is_rejected_while_waiting_releases_graph_slot` | 原Worker回归本次236整体实际通过；P3组最终待结果，不升级多Worker |
| S02 | `test_s02_serial_kinds_interrupt_and_queue_restart`；P3等审批释放slot/继续另一thread | 原Worker回归通过；全局串行约束不变 |
| S03 | `test_s03_lock_loss_unconfirmed_blocks_then_confirmed_recovers`、`test_s03_old_os_process_alive_blocks_without_lease_takeover`；P3实际失锁exit/reaped/TermRequired/confirm | 原Worker本次236整体通过、A02独审/CI已核；A03新增kill闸门通过，无热接管 |
| A01–04/T3 | `test_plain_approve_and_partial_unknown_ack_never_write_decision`、两unknown完整集合/277键、bad nonce/hash/version/strict bool、当前role-bound/eligible | A02已核，A03同原合同回归；普通批准绝不替联合确认 |
| A01–04/T4 | `tests/test_p3_execution_authority_pg.py::test_a01_a04_last_revalidation_checks_current_identity_auth_version_and_role_scope` 五分支 | authority组9实际PG/95.14s含此项；撤权后0execution/0items/oldapproved未消费 |
| A05/expiry/freshness | `test_a05_actual_db_expiry_after_historical_approval_has_no_t4_effect`、`test_r12_stale_fresh_observation_recollects_without_second_human_interrupt`；A02锁等待越真实TTL | 真60s过期0T4、重观测过期重采1approval；最终模块结果另核 |
| A07–08/参数来源 | `test_frozen_lrs_survives_private_deployment_config_version_change`、`test_legitimate_new_cycle_changed_lrs_same_quantity_requires_new_source_and_confirmation`；`tests/test_p3_evidence_pg.py`来源/rule/config/数量伪造 | 9/95.14s及联批3/14.42s；LRS只有原冻结链/显式new_cycle。同task hot edit not_implemented，不假装触发不可达路径 |
| C01–02/T6 | `tests/test_p3_execution_pg.py` complete/close+strictversion/blank；`tests/test_p3_items_authority_pg.py` late same-shop非eligible、hiddenSourceLinks、operator/admin/cross-shop | 初始5PG/22.62s、items专项5已通过；最终完整模块全部通过，精确时间见后表 |
| C03/幂等恢复 | Unicode10次原键、GET原receipt、同键异payload/新键终态409；`test_t6_actual_sigkill_atomic_or_original_receipt` before/after commit | 基础5/22.62s、恢复8/40.92s已实际通过；PG回执/版本/audit/outbox一次 |
| C04/竞态与新周期 | `test_c04_complete_close_two_current_actors_real_transaction_race_one_winner`；R12/new LRS cycle | items专项5通过、一赢家/另一409、audit/intent一次；新cycle需新source/plan/approval/nonce |
| C04–05/投影故障 | `tests/test_p3_projection_pg.py` failure/unknown/repair/stale/currentversion/original intent改写负例 | 3实际PG/18.69s，controlled_stub；不改业务terminal，无网络sender/false synced |
| Evidence/DB负例 | `test_actual_pg_observation_wrong_ids_lineage_discriminator_hash_mutation_delete_rejected`；`test_actual_pg_source_parameters_rule_config_or_balanced_forged_quantity_fail_authority` | 实际联批3/14.42s，双namespace冲突/错scope/错来源hash/generationFK/不可改/delete/exclusive evidence；deterministic arithmetic不可由平衡hash伪造 |
| Contract-runtime/正缓存 | `tests/test_p3_openapi.py`、`tests.p3_wire`、安装wheel导出 | 实际wire32响应/22唯一op，正向P2 offline_stub缓存、GET调用数不变/actual0；安装wheel及最终pure已通过，精确结果见后表，原DTO唯一delta Receipt300 |

## 完整收口及未来Gate

Root批准B03 CI容量修复仅将完整actual collection的P3按既有测试模块自然派生串行组，旧236组保持；每条300s、全局23min/job25min/cleanup75s不扩大，union精确覆盖/无重复或遗漏/实际各组collection重核。`test_pg_diag_partition.py`原测试加未来模块覆盖；41partition/shutdown/0.11s、67相关纯组/0.43s。不是硬编码cardinality、挑node、重置deadline或新框架。本次作者完整PG已使用同函数/完整collection逐组执行，333全部通过，sum607.14s及每组时间见后表并报告Root；精确新CI只能由GitHub回执认定。

A03冻结独审/新精确CI/B04与前端共享typecheck/build/contract/实际PW集成、Root最终核收/main合并及同main合后CI仍待。B03原failed CI保留，A不合B、不在脏目录接线或改其npm/E2E。人类H/L not_reported；D1/D30/300h/A32+B18+Review10/60h保持。human_feishu、真实Card/Base/Woo业务写、生产/Phase4、多Worker R02–04、自然故障/p95/40×3/95%/长期TTL仍not_run。


## A03最终完整回归与停机

完整actual collection333=236旧回归+97P3（旧59+新38），从真实collection自然派生12个串行组，union无漏重、各组实际collection重新核对；全部exit0。下表pytest时间与命令墙钟分开记录，最大命令163.82s，合计607.14s；保持每条300s、CI全局23min/job25min/cleanup75s，没有提高预算。完整安全摘要与运行/测试文件指纹见[作者证据](contracts/p3-a03-author-evidence.json)。源码/测试29个文件从本轮完整回归前固定指纹到收口无变化；SHA/tree从新freeze/Root回执核。

| 模块 | 实际passed | pytest时间 | 命令墙钟 | 结果 |
|---|---|---|---|---|
| `既有六模块` | 236 | 142.47s | 143.421s | exit0 / actual collection精确一致 |
| `tests/test_p3_approval_pg.py` | 24 | 163.31s | 163.82s | exit0 / actual collection精确一致 |
| `tests/test_p3_evidence_pg.py` | 2 | 5.97s | 6.458s | exit0 / actual collection精确一致 |
| `tests/test_p3_execution_authority_pg.py` | 9 | 93.8s | 94.282s | exit0 / actual collection精确一致 |
| `tests/test_p3_execution_pg.py` | 5 | 19.28s | 19.753s | exit0 / actual collection精确一致 |
| `tests/test_p3_execution_recovery_pg.py` | 8 | 40.21s | 40.676s | exit0 / actual collection精确一致 |
| `tests/test_p3_items_authority_pg.py` | 5 | 21.07s | 21.542s | exit0 / actual collection精确一致 |
| `tests/test_p3_migration_pg.py` | 1 | 0.77s | 1.206s | exit0 / actual collection精确一致 |
| `tests/test_p3_pg.py` | 34 | 69.57s | 70.075s | exit0 / actual collection精确一致 |
| `tests/test_p3_pool_pg.py` | 1 | 6.72s | 7.176s | exit0 / actual collection精确一致 |
| `tests/test_p3_projection_pg.py` | 3 | 18.24s | 18.703s | exit0 / actual collection精确一致 |
| `tests/test_p3_revalidation_pg.py` | 5 | 19.55s | 20.028s | exit0 / actual collection精确一致 |

最终`python -m scripts.check` exit0：988offline/84.99s、333integration deselected、2既有SDK弃用warnings，Ruff/245format/mypy177、64Markdown/0error、Node24.21.0原tooling/typecheck、95Python和Node已知漏洞0，dir/index/git0。389合同checks/21paths/22ops/67schemas；实际安装wheel核全部22approved操作/输入/响应/components/security及asset原字节。actual wire32响应/22唯一operation、positive cached P2 offline_stub一次、两个GET不增加调用、actualprovider0；新P3 report解释NOT_READY且调用0包含在完整5revalidation组。

原236回归保留6实际G2 process records（包含cross-process、receipt/CP间隙、失锁取消、noncooperative exit、checkpoint故障恢复、retired版本拒绝），不升级为P3人工/平台Gate。自有项目再执行两轮migration/setup/grant/revision幂等及G1 fixture：restart前、同volume restart后、同项目同volume force-recreate后三次PG task/inbox/job/audit/checkpoint持久化断言全部exit0。所有生命周期仍在原窗口内，不借用旧资源。

实际2026-10-11 02:25:52.739376426+08:00停止postgres，02:25:53.065748观察running=false/PID0，早于03:01:30.390967原截止；tempDB0、其他base连接0、app superuser/createdb/createrole全false、revision0007、700目录/四私有文件600，volume及ledger保留。安全字段见[停机回执](contracts/p3-a03-stop-evidence.json)，只stop、不down-v、不称cleanup0。A03作者已收口，独审/精确CI/Root Gate及B集成仍pending，Phase3未完成。
