# R4 quality末段时间与最小分组映射建议

2026-11-05（台北）。仅从原quality.log派生，不运行测试或修改分组。原日志hashdf5d948362776446a743af13e0e21639e23a22fc5d3d001fdb369c104895d0ef；精确源码bcebf10及实际merge305d/tree8f。保留首组失败、sample_error及清理原结果。

command_start事件at16:11:27.579739Z，limit300；command_timeout16:16:27.583620Z。下表余量按外层事件at相对16:16:27.579739预算线计算，不将它冒称跨进程时钟精确同步；原pytest独立monotonic及phase durations另保留在quality-timing-derived.json。

| 序号 | business_pg用例后缀 | node_start UTC | 记录时预算余量 | call duration/outcome |
|---|---|---|---|---|
|264|sql_python_canonical_text_corpus|16:16:22.398598|5.181141s|0.019369s passed|
|265|golden_reads_tags_receipt_replay_original_after_later_effect|16:16:23.039307|4.540432s|0.902466s passed|
|266|paid_unknown_fulfillment_and_atomic_rollback_on_audit_failure|16:16:24.513703|3.066036s|0.631090s passed|
|267|real_native_preview_confirm_same_job_version_sources_and_all_result_export|16:16:26.151040|1.428699s|1.298652s passed，结束at16:16:27.997279|
|268|changed_revision_cannot_confirm_old_preview_and_reset_hides_effects|16:16:28.047640|-0.467901s|0.961577s passed，结束at16:16:29.546876|
|269|parent_mapping_chain_supersedes_and_disallows_old_confirm|16:16:29.612333|-2.032594s|setup0.571743s passed；call start16:16:30.163266，未捕获call end|

完整第269node为tests/v41/backend/test_business_pg.py::test_parent_mapping_chain_supersedes_and_disallows_old_confirm。它在已记录command_timeout之后才进入；call start距预算线已过2.583527s。因此不能用它未完成来解释此前300秒耗尽，也无单节点卡住证据。停止流程期间测试仍短暂推进，不能把268通过都描述成预算线前完成。

按原phase duration求和：全部记录268通过项setup124.938702s、call156.433128s、teardown6.476665s，合287.848495s；其中在timeout事件前已有call passed的266项setup123.785442s、call154.172899s、teardown6.433592s，合284.391933s。不是命令总wall time，也不是将各进程monotonic与host UTC直接相减；启动/collection/传输等剩余时间没有逐项归因。各phase均已记录passed，无已记assertion fail；未开始21项与已开始未完成1项分列。

## 最小映射候选及文件边界

现有scripts/pg_diagnostic.py:81的combined_groups先将P5/M3完整自然模块移出ordinary；V40/V41尚在combined-existing中。该首组290=legacy236+四自然模块54。可评估仅从ordinary抽出下面完整路径，在legacy组之后、原P5/M3组之前依既有collection模块顺序插入，每模块内部保留输入node顺序：

1. tests/v4/test_demo_seed_pg.py：7节点。
2. tests/v4/test_demo_sessions_pg.py：19节点。
3. tests/v41/backend/test_business_pg.py：23节点。
4. tests/v41/backend/test_gc_pg.py：5节点。

如此原首组变236，四新命令为7/19/23/5；全部原290节点保留，原后续306节点与其组不动，existing仍596，phase3仍177，全773/交集0。数字仅为当前collection映射检查，不应硬编码为忽略未来节点的筛选。应按完整自然路径派生该模块全部collected nodes，明确且唯一label；不要让含斜杠的label意外成为容器名称或文件层级，应沿既有规范label命名方式核下游。

最小生产文件边界为scripts/pg_diagnostic.py的分组函数，必要测试优先tests/test_pg_diag_partition.py；若加专用新分组测试文件由Root指定单owner。scripts/pg_ci_evidence.py的partition与validate/verify_pair可保持：既有checker已调用combined_groups核精确模块映射、同源集合和全覆盖，不需放宽校验。既有tests/test_m3_gate_coverage.py及P4 partition/evidence契约是受影响回归范围，是否仅执行现有定向pure由Root决定。

须保持G1/G2、每命令300秒、job绝对截止/cleanup reserve、无重试、完整collection/顺序合同。增加四次命令启动会增加总开销；原剩余306项和G1在本run未测，因此本建议不证明新分组可在总job预算完成。先纯映射完整并集/顺序/无重叠/旧组不变，再按Root单owner与新运行授权推进；本轮仅只读建议，不开新PG或CI。
