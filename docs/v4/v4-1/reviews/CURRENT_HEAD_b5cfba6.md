# V41 current-head 七文件兼容片独立审查

日期：2026-11-04（台北）。source `b5cfba6b2fa632276f69cecc2a6d450a0c154ce7`，tree `7357e3f1f0599ea7056e358b38dfbb2302a48fab`，parent `d3fc9109a2c6fe37ba2a563095a261afb1625861`。

结论：HOLD_CURRENT_HEAD_COUNT，一项 P2 待窄修；其余六文件和 F02 revision 更新未见新增 P1/P2。不能按作者 pure/collect 结果签本片完整可进入 Full。

P2 H01：`tests/test_p4_f02_pg.py:176-181` 已期待当前 revision 0025，但同一 owner 连接随后统计 business+checkpoints 的 pg_tables，仍断言 `{"n": 89}`。0025 在旧 89 表上新增七表，正确当前总数为 96；同提交 test_postgres 的完整 business 集合 AST 实数为 92，加既有四张 checkpoint 表即 96。正常迁移到 0025 时，F02 此测试会在这项旧常量失败。建议仅同步 89→96，保留精确等值断言、角色限制与业务前后计数；不改变历史 schema 数量。这是精确源码矛盾判断，本轮未启动 PG，也不声称已捕获实际失败。

其余变更核对：first-create 的固定 d97/0012→0013 阶段保留，只有后续 migrate(head) 增七表、空表集合和 36→43，旧所有行/检查点字节相等与 F02 列权限检查仍在；history 的原 0016→0017/unknown 原件保持，只有后续 head 集合与空表增加七项；diagnostic Fake 对应调整且固定 d97 隔离目录排除 0025，不修改旧闭包；read-reply 只增加当前 revision 到既有允许集合；M2 backup 的实际 0018/60 合同保持，仅 current-head 非 M2 拒绝路径更新至 0025；test_postgres 保留完整表集合精确相等，没有改成子集。

独立验证：从精确 archive 提取并以 archive backend/tests 导入。`tests/test_p4_migration_diagnostic.py` 33 passed，11.94s，native exit 0（两条既有依赖 DeprecationWarning）；七文件 collect-only 107 tests，2.93s，native exit 0。collect 未运行 fixture/PG，Fake 不覆盖 H01 的实际表计数。

只读审查及上述 pure/collect；无 Docker、PG、SDK、服务、浏览器、Full、CI 或远端写入。Root 新报专项 22/22 不替代本片或未来全仓 Full 的验证，旧失败回执不变。
