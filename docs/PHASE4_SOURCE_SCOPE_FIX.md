# Phase4 首真人 Source 装配修复

## 范围与实际失败

本批从已审 `8425a93b352ed2e91287583a58e3bdcc2ade8e7e` 出发，仅修改 A 的受控 Mock/test 装配校验与 P2 安全错误码。B 的 Base adapter/strict readback、C 的 Web/npm、SDK 上限14、原幂等键和业务事务不改；不启动新真人或真实 SDK，不修复原库终态。

首 known70 真人私聊实际入库一次，原 T1 与 Gateway/参数/当前 A 权限匹配，Worker auth/bot/table/field各一次 returned HTTP200/code0，唯一目标与15字段核实。完整闭环未完成：没有新卡、批准、plan、执行项或 Base delivery。WS endpoint/handshake/frame/ACK 仍 not_verified，业务消息实际接收单独成立。

2026-10-11 新 PG-only 只读收证显示：

- P2 source 先在 `14:36:07.289773Z` 进入分析，随后 `ANALYSIS_CHECKPOINT_UNSAFE` / needs_attention / version3。
- T1 继发 `DATA_INCOMPLETE` / failed / version2，两 analyze job 均 done/attempt1/last_error null。
- reports/snapshots/plans/approvals/executions/items/outbox/card bindings 全部0、inbox1；checkpoint schema、usage和四张表均存在。
- 原 Worker SDK4次，全历史 SDK windows4/calls14（含旧3/10）；低权限3false/tempDB0。
- 首读取助手 SQL.format 把正则大括号解释成占位符，构造阶段 KeyError、未读取业务证据；失败 result 与更正后的 evidence 分文件保留。第二次读取成功，`14:50:27.075678Z` stop/down0、容器/网络0、no-v/保卷，不再使用追加收证额度。

`InventoryRunner.run` 的旧通用 catch 将所有 AnalysisUnsafe/PersistenceConflict折叠为 checkpoint unsafe。原本地 seed 使用的 Mock 外部店铺键与冻结 known_inbound fixture 不一致。新隔离 PG 沿同 Feishu 身份类型、同参数 L3/R7/S2、同新 cycle/未完成P2来源、同单Worker路径，实际在原 InventoryStore.save捕获固定 `ANALYSIS_SOURCE_SCOPE_MISMATCH`，随后复现与首真人一致的 P2 generic checkpoint码与 T1 DATA_INCOMPLETE。原 live 的下层 exception 未直接保存；不回填当时未捕获的原始 trace。

## 最小变更

1. Gateway claim 在记录 claim/构造 WS/读取 AppSecret 前，比较当前 Mock/test shop 的 external_shop_key/currency/timezone 与冻结 fixture 的来源。错配返回固定 `P4_CONTROLLED_FIXTURE_SCOPE_REQUIRED`，不改店铺或fixture、不填充来源值。
2. Worker trusted_scope 重新比较同三字段，仍核原 active Gateway/唯一T1/参数/无Fake历史；失败发生在 PersistentSDKLedger/Factory/Graph 构造前。
3. P2仅将准确的固定 `ANALYSIS_SOURCE_SCOPE_MISMATCH` 保留为同名安全码和 needs_attention；其他 checkpoint/持久冲突仍沿原保守处理，任意 exception 内容不输出。

队列/Graph未修改。强制 P3 比 P2 更早 eligible 的新 cycle 回归在旧代码已经成功；外层 ApprovalRunner._run 对未完成source返回原 retry，source完成才prepare。此前静态竞争候选漏看此检查，不能作为本次根因或无必要调度修复。

## 实际回归

新自有隔离项目 `p4-source-repro-aa1715ad345e` 使用现有已核 test image，当前 backend/tests/scripts 只读挂载；新私有凭据、原 live 保留卷完全不写。所有 SDK/Secret/真人次数0。

| 批次 | 实际命令/结果 | 释放 |
| --- | --- | --- |
| 旧码复现 | `pytest -q tests/test_p4_new_cycle_source_pg.py --tb=short`，1 failed/1 passed，pytest9.90s/命令13.035s；失败精确为来源scope码被误标checkpoint，P3先eligible完整等待成功 | `15:06:27.587332Z` stop/down0/容器网络0/no-v |
| 修复后相关PG | `pytest -q tests/test_p4_new_cycle_source_pg.py tests/test_p4_controlled_worker_pg.py tests/test_p4_gateway_window_pg.py --tb=short`，8 passed/0failed/0error，XML cases累计14.510s/suite19.398s/命令21.927s；完整新Feishu T1→未完成P2→不可变Q70 plan→pending card outbox，三类错装配无claim/SDK | `15:18:33.177756Z` stop/down0/容器网络0/no-v；low role3false/tempDB0 |
| 相关纯测试 | `pytest -q -m offline tests/test_p4_mock_shop.py tests/test_p4_fixture_preflight.py tests/test_p4_controlled_worker.py`，53 passed/2.95s，Gateway Secret reader仅config/window两读、socket未构造，Worker Ledger/Factory/Graph未构造 | 无PG/SDK |
| 全offline | `pytest -q -m offline`，1454 passed/383 deselected/102.39s；完整check内同suite1454/383/93.07s，SDK/fork DeprecationWarning保留 | 无新增真实SDK |

完整 `scripts.check` exit0：dir/index/完整可达历史扫描各0、uv锁0、Markdown94/errors0、Ruff0/format364文件、mypy266文件0；本地Node24.21工具链/typecheck/audit0及Python95包audit0。精确源码独审与新CI仍待Root回执，不预填未来SHA或CI。不宣称隔离 card outbox已真实发送，不将本批替代真人闭环、全M1、跨窗口或20SKU正式Gate。

第一次静态入口因调用PATH缺项目mypy而在typecheck前FileNotFoundError退出，先前dir/index/history扫描0、锁/文档/Ruff/format通过分别保留；后以项目`.venv/bin`显式PATH运行完整检查。此环境失败不计产品/PG失败。

## 原现场与后续配置/恢复边界

原真人 SDK截止 `14:36:51.681789Z`，Gateway child -15/reaped、Worker child0/reaped且原完整持久/同namespace终止确认 true。API/Web/PG watchdog 在 `14:38:34.661632Z` stop/down0、listeners/network0，但留下两个已退出 SDK orphan容器；最终全容器清除确认 `14:39:10.154634Z`，比服务保底晚约7秒。原false/晚扫尾/最终PG_read1和所有旧失败均保留。

原 live shop、failed T1/source、两原job、checkpoint、inbox/原键不改。后续若Root裁决修正测试配置，方案是同一org/shop/身份/角色下，对旧 `config_ref` 与旧来源三字段作精确前置比较，记录新配置版本ref及安全审计（版本、三字段匹配boolean、旧任务不变boolean），再更新到冻结fixture来源；不将新配置或新错误码倒写为旧失败事实。当前仅提出，未执行任何原库UPDATE。

旧 source needs_attention/T1 failed/job done 不允许普通审批或直接SQL复活。新 Worker不能借旧已过期 Gateway claim：原trusted_scope要求Gateway active且入站receipt在该claim之后。若Root选择原键恢复，必须先单独冻结显式失败恢复/跨窗口合同，绑定原message/T1/source/input与原终止回执、当前权限、新配置版本及新active Gateway；独审裁决后安排。若选择新正式任务，同样需要明确创建合同，不自动换键，也不要求真人再次发原句来定位。

本批child源码字节变更，旧已审私有list observer的original-child SHA pin不能直接复用。下一运营窗口须保留旧observer原字节，制作仅更新到新冻结child hash的自有副本，并核原返回/异常保持；不得为了启动绕过hash校验或使用旧映像。当前未运行新SDK窗口。

原D1/D30/300h/P4 50h及人工H/L not_reported不重置，M1设计18页/原资产/凭据/卷保留；无新增paid、生产、Woo或Phase5授权。
