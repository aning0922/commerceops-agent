# V41 GET读取R01/R02关闭回执

日期：2026-11-04（台北）。source `ca69b83404c4270bfd9cef09a58a343c148769fb`，tree `27c3d274cc200c30201b94cab009e7fdc68499c1`，parent `05d208636d90e43c4b43bf7c27dcba3a902ec84b`。

结论：ACCEPT_05D_PLUS_CA69_READ_RECIPE_SOURCE。两项P2在源码层关闭；结合前次其余审查，本次三文件组合未见剩余P1/P2。可由Root合入后冻结新source/tree/image，再实际验证；不签16路由已经真实HTTP通过。

R01：import_flow在preview、原key lookup和只读数量核验后、confirm前，实际调用read_original_job；该helper调用Business.call('job',原preview.job.import_job_id)，因此经过原真实client、strict schema/status/context/cache验证链。完整返回data必须等于原preview，而非只核id或少数字段，覆盖job version/revision/parser/schema/digest、mapping、文件/预览内容。当前已审后端job GET返回同ImportPreviewData，未确认且未派生新版本时_display_job保持READY/confirmable，与此完整比较相容。新增调用轨迹测试核确切别名和原ID，并对version/revision/parser/schema漂移拒绝；没有构造替代key或恢复旧动作。

R02：readback_shop的实际golden分支现调用assert_expected_source，固定fixture_digest仍精确相等，data_mode必须是imported=0的demo_fixture或imported>0的demo_mixed。所有现有main调用保持golden默认true，故不能靠各响应彼此一致绕过预期来源；新增两个参数化节点分别验证两方向错标拒绝。原独立raw seed/Decimal指标、分页、CSV、detail/context与隔离代码未改。

独立验证：精确ca69 Git archive、锁定Python环境及archive导入，test_read_recipes、test_kpi_reference、test_scope_semantics共31 passed，0.23s，nativeexit0。作者46pure/type3/Ruff/preflight仍按作者证据，本轮没有重复全部46或type。只有源码/组件证明；无实际HTTP、浏览器、SQL、owner、Docker、服务、Full/CI或远端写入。旧05d反例和HOLD回执保留，Root9e1实际API案与后续新组合不能混签。
