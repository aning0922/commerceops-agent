# P4 C0 首次创建前向迁移候选

2026-10-13（Asia/Shanghai）。Root 对 d6b7b4620befd2ed43926c4216fc9fff0b972995 / tree f80a9e568b01ba9c9824d9aee76e39fc886cc998 安排原 Core 只读定位后，授权 A 单 owner 完成 ≤60min 源码、前向迁移和定向纯测试批。实际起点 2026-10-13 23:20:50，硬止 2026-10-14 00:20:50（UTC 15:20:50→16:20:50）。本批不启动 PG/API/Worker/平台，不读取 AppSecret 或原 known70 业务库，不与 BC02 产品实施混批。

## 已定位阻断与保留事实

d6 的显式 C0 准入将原 unknown/reconcile 改为 create，随后 dispatch 的 UPDATE 申请 sending/create。0010 的 status=unknown 与 unknown_since 两条 guard 均禁止非 reconcile，第四轮自有 PG 因此在持久发送申请时触发 CheckViolation，未进入 Fake adapter/create。Root 转达 Core 的精确独立定位及其 48 项新 offline / 2.82s 通过；不将此结论倒填到前两轮未捕获具体异常、第三轮仅捕获预期 dispatch AssertionError 的记录。

原四轮失败/停止资料留在 Root 私有证据目录，既有标准诊断 runner 已清理它新建的测试卷。原 known70 卷保留、原库未操作。d6 本地冻结与已有已审 2a/精确旧 CI 事实保留；本文件不以旧 CI 验收新候选。Phase4/M1、真实 R13 与实际平台 C1/读回仍未验收。

## 迁移与准入

新增 0013_p4_first_create，down_revision=0012_p4_preflight_methods。仅 CREATE OR REPLACE 原 p4_base_delivery_identity 触发器函数，不改 0010/0012 文件，不新增表、列、宽权限、session 开关或 SECURITY DEFINER。原插入、身份快照、终态、锚、first_attempt_at、unknown_since、attempts 不回退等 guard 全部保留。两条 unknown 非 reconcile guard 共用默认 false 的 first_create 谓词；其它请求保持原行为。

例外同时要求：OLD 为 controlled_sdk / v1 / unknown / attempts1 / last_operation=create / INCOMPLETE_READBACK，无 external_id、已有 first_attempt_at 与 unknown_since；NEW 仅申请 sending/create/attempts2，claimed_by 非空，原 outbox/org/shop/task/item/target/token/version/snapshot/hash/created_at/first_attempt_at/unknown_since/external_id 完全不变。

该谓词核对唯一持久 approved_first_create claim 与当前 SDK window：窗口 UUID/组织/店铺、单原 task、原 outbox/item/client_token/projection_hash/request_hash、原 task version/approval/decision/execution/target 与期限一致；当前原 execution 有效且只含该 item，item 仍 open/v1，原业务任务 completed。当前 creator/approver 通过原 lock_p3_permission 重新锁验身份/版本/逐角色店铺授权。

SDK window 必须 enabled、controlled_sdk、期限未到、cap 与 claim 完全一致，create=1、无 IM/额外方法，auth/bot/table/field/list/update 各符合原有限上限；当前窗口须已有 Fake 或实际模式明确标识的 preflight returned HTTP200/code0 账本证明。这里只消费持久事实，不调用 SDK，也不把 Fake auth 视为真实认证。

当前 Base sender 必须绑定同 window expiry、当前 Worker owner 与实际 dedicated backend PID；该 PID 须持有原全局 Worker advisory lock，当前 App Gateway advisory lock 也须仍存在。当前 Gateway 是同组织/店铺、enabled、max_workflows=0、期限覆盖 Worker 的新已登记窗口，不能借例外接新 T1。所有其它同组织/店铺 SDK window 均失效；精确原 outbox 在任意窗口存在任何 create 账本状态（started/raised/returned/not_called）即拒绝。

所有旧 Worker/Gateway 的 started/termination receipt 必须唯一、时序正确；Gateway 明确 child_reaped 与整数退出值，Worker 保留必要 namespace/reason 与可选干净 stopped 配对。Python 在原行锁内再次复核全旧发送进程 OS absence，并严格比较当前 Ledger/window/target 与 claim。SQL 重核持久终止证明、当前锁与权限。两层不能以 lease 到期或锁可获取替代旧进程死亡。

显式例外只授权原键的首次 create 请求。原 adapter 仍必须完整分页、total 一致、record ID 唯一且零原 item 匹配才调用 create；合法 fields={} 空白行仅是无 item key，不成为 anchor。15 字段匹配与三个 nullable key 严格要求不变。create 预占后即失去 C0，未知继续 reconcile；不存在 pending/unknown_since reset、换键、新执行或计划复活。

## 应用顺序与可复现命令

1. Root 对新冻结 SHA 安排 Core 增量独审。本批未通过前不运行第5PG，不开平台窗口。
2. Core 通过后，Root 另登记一次 ≤20min 的全新自有 PG namespace、截止和 owner。正常新库从迁移链建至 head；升级验证在同测试 namespace 的另一随机 0012 测试库准备原 C0 事实，再升级并比对全部业务表/checkpoint 的 count/hash。原 known70 库不参与这一验证。
3. 使用已登记测试库的 owner 配置执行 migrate，然后原 setup-checkpointer/grant-runtime 或已有权限核对。函数 replace 与 Alembic revision 同事务；失败不制造已升级回执。先确认 revision，再使用低权 runtime。既有持久行、键、版本、快照、审批及 CP 不更新。
4. 新发送窗口与显式原键 claim 必须重新受 Root 授权。当前 Factory preflight 成功、持久当前窗口且原 Worker/Gateway 锁在位后，才由原 BaseDeliveryStore 申请一次发送。C/U/IM/模型额度均不能从迁移或旧诊断继承。

源码批可复现的无 PG 检查：

```sh
.venv/bin/python -m pytest -q tests/test_p4_first_create.py tests/test_p4_first_create_migration.py tests/test_p4_blank_records.py
.venv/bin/python -m pytest -m offline -q
.venv/bin/mypy
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m scripts.check_docs
.venv/bin/python -m scripts.scan_secrets
```

以下是后续 Root 窗口的候选命令，不是本批执行回执。migrate 只能消费当次新自有数据库的显式 owner 配置，不能套用默认/旧环境；不读取旧 .env。

```sh
.venv/bin/python -m commerceops.entrypoints.database migrate
.venv/bin/python -m commerceops.entrypoints.database revision
.venv/bin/python -m pytest -m integration -q tests/test_p4_first_create_pg.py tests/test_p4_first_create_negatives_pg.py
```

实际容器/守护/停止仍由 Root 既有有界 harness 管理。标准 pg_diagnostic 会清理它自身新临时项目的卷；若 Root 要保留某次新库，须使用已登记的保卷装配，不向原资源执行 down --volumes。全回归与精确 CI 的原分母不减少。

## 回退限制

downgrade 明确拒绝自动回退。不能删除 SDK/claim/audit 历史、归还已预占 create cap、把 attempts2 变回1、清 unknown_since 或改 pending 来实现“回退”。操作回退应先停止发送进程、确认 reap/终止及窗口关闭，保留 0013 与全部账本，再回退应用源码或禁用该窄 profile。旧源码仍只能按原 unknown 规则对账，不因函数存在自动获得首次创建权限。已申请发送而未能证明结果，沿原恢复合同保持 unknown/reconcile。

## 本批实际验证与待验证

定向纯测试修正后 91 passed / 2.68s，加入 SQL 分隔符检查后最终 92 passed / 2.75s。首轮 3fail/88pass 保留：新 target 绑定检查暴露两个测试 Gate 占位目标；原 SQL 等价检查受换行空格影响。修正测试装配/比较后通过，不放宽生产准入。全 offline 实际 1707 passed / 451 integration deselected / 103.25s / exit0；mypy 295 文件通过，ruff 与 format 当时398文件通过，补文档后399文件通过。Markdown100/errors0；敏感扫描及最终 freeze 以随批 manifest 的实际回执为准。

纯迁移合同证明前向链、单函数 replace、两条 guard 共用谓词、其余旧函数 SQL 等价、全状态 C 账本拒绝、无 reset/SET LOCAL/宽权限，并做词法分隔符检查。它不证明 PostgreSQL 已接受或执行这段函数。

下一轮新 PG 已准备但未执行：合法 C0 一次 create 与 Fake 成功 ACK-drop 后只读锚恢复/T6 同行更新；四个 C ledger status；相邻 token/item/hash/v2/attempt/history/anchor/owner 拒绝；撤权；不改原窗口的真实时间到期；原 0012 行/CP 升级 count/hash 保留。Negative fixtures 只在新测试库人工追加明确标识的可能调用账本，不改已有行；SQL 正控使用事务回滚，不冒充实际 SDK create。原各回归、Core 新增审核、精确新 CI、真实 SDK/真人/R13/Base 业务 Gate 均仍待执行与核定。
