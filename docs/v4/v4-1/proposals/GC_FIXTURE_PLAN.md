# GC 专项候选：最小受控历史 fixture

2026-11-04（台北）。测试 owner 仅写本文件及 `tests/v41/backend/test_gc_pg.py`、
`gc_fixture.py`；不改生产 guard、迁移、旧测试或系统钟。基线 `0f0e5a3`，已核
`49077566c9ad8f3b1696aa3d8fc46b7ef1d57fbf` 的两个 GC helper、0024/0025
及独立报告 `3f71e85:docs/v4/v4-1/reviews/GC_SCOPE_4907756.md`。
当前合同 V41-1f 仅准候选准备；**实际 PG / restore / GC 均 NOT_RUN**。

## A：正常有效会话屏障

复用正常新 owned schema/fixture/provision 与 policy/runtime 初始化骨架。
两个方向均通过独立连接的 `pg_blocking_pids` 确认真实 tenant 锁等待，在原
statement=5s/lock=1s 内及时释放：actor 先持有原 resolve/read_guard 的 tenant/session
锁，原 `gc_tenant` 随后等待并返回 `V4_GC_NOT_READY`；反向原 GC 返回该拒绝后
保持事务 tenant 锁，actor 等待，GC 事务结束后 actor 按当前权限成功。
逐表确认零删除。此 GC 分支在 retain 检查时退出，**没有取得 session 锁**；
不能描述为活会话与合格物理清理同时成功。

## B：SYNTHETIC_OWNED_HISTORICAL_FIXTURE

仅正常 fixture 创建的全新随机 `v4_demo_*` 测试库；不读旧库/配置/数据。用正常
DemoStore/BusinessStore 构建目标和另一 tenant 的合成图，至少各覆盖六 V41 子表，
V4 creation receipt/两 events、两 shops/三 personas、bound identity/session 完整。
preview 使用真实正常本地 parser 并结束/reap，全部 writer 返回后才进入一次初始化。
此外放置独立合成非 Demo organization 对照。

**恢复是初始化期受控时间变换，非正常 runtime UPDATE/INSERT。** 单独 owner 连接，
校验新库名、0025、PG17.11/vector0.8.7、owner 及当前 origin；记录原目录后在显式事务
`SET LOCAL session_replication_role=replica`，仅目标完整图的时间列统一减48h。
包括 tenant/session/bootstrap、bound web session、V4 receipt/event 与 V41 receipt/event/job。
CHECK/唯一/NOT NULL 始终启用。同步 preview 内 expiry、session-expiry 参与的 job_digest，
及 import_confirm request 的 expected_job_digest/payload_digest；不改 fixture snapshot/policy。
恢复 origin 后关闭此连接，再用新连接确认 origin 和全 business trigger（含内部 FK）状态、
定义、函数/search_path/ACL、表/列 ACL、约束/索引目录逐项与恢复前一致。
初始化异常回滚并关闭；不能给 app replication 或 owner 权限。

UNKNOWN 变体在初始化时另添一项从未发布的合成历史 UNKNOWN job（独立 key/process_ref，
无 preview_data，slot占用，stop_proof为空），不把已确认 job 倒改为 UNKNOWN。
它仅表示 fixture 历史不确定事实；不冒充本轮运行进程、kill/reap 或自然24h。

恢复后独立验证：全 business FK 按完整 conkey/confkey 配对 anti-join 无孤儿（含复合
session/tenant/shop/owner/principal/receipt/event/job关系），所有 CHECK 重算、NOT NULL
与唯一索引保持；canonical JSON、request/payload/file/mapping/normalized/job digest、
receipt/effect/event绑定、fixture身份/两店三persona/bound session 与历史生命周期区间。
用原数据已成立的正常写图及显式变换前后允许差集校验，不对过期图重跑当前 commit_guard。
`convalidated` 或恢复 trigger 本身不算数据验证。所有验证失败均保留原错误且不调用 GC。

被测阶段仅新连接、origin、原 trigger/约束/权限/TTL：原 `gc_tenant` 真 COMMIT 后，
目标六子表与预期 V4 行归零，原 shared 身份保留但禁用/撤销，fixture/policy/另一 tenant/
非 Demo 对照不变；旧 token 的原 resolver 与 V41 actor 均拒绝，零新效果。
独立实例同事务清理后主动 ROLLBACK，核完整目标/对照恢复；UNKNOWN 实例应
`V41_PROCESS_HOLD` 且零删除。过期 token 在删除前已不合法，不称自然跨24h验证。

## 验证与交付

只执行 Ruff、mypy、离线纯变换检查、pytest collect-only；collect 不实例化 DB fixture。
不启动 Docker/PG/HTTP、不读 Secret、不调用远端。Root 后续精确源码独审、合入已审
API tag 修复和新 owned UTC/资源后才运行。任何构造/约束冲突精确回报，不放宽规则。
标准 expired receipt INSERT 被0024 guard源码拒绝的初方案保留为 SOURCE_REJECTED，
未冒称已跑 SQL。此文件与代码、检查回执不代签真实 GC / HTTP / Full Gate。

## 本地候选自检事实

5个 integration 节点仅收集（A双向2，B commit/rollback/unknown3）；另1个 offline 金标
实际通过，验证变换结果与生产 `prepare_preview` 在独立历史时间输入构造的完整preview
相等，原对象不变；不连接数据库。Ruff 与 mypy `--follow-imports=silent` 两文件通过。
早期 Ruff 有34项格式/行长错误，格式化后余3项，修正后通过；未运行失败PG或伪造JUnit。
fixture只有显式执行测试时才读取Root新owned环境，导入/collect不实例化连接配置。
未来实际测试以 pytest `record_property` 保存不透明逐表前后指纹/目标计数、时间前提、
实际阻塞PID及真实COMMIT返回点；不输出token/binding/credential/policy内容。
5个PG节点的restore可行性、物理清理、并发与完整Gate当前继续 **NOT_RUN**；
提交前原生公开文件preflight另以工具真实回执为准，不在此预填通过。
