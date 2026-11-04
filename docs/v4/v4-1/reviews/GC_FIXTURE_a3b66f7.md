# GC 历史 fixture 首候选独立源码审查

2026-11-04（台北）。结论：`ACCEPT_CANDIDATE_FOR_ROOT_GATED_5PG / RESTORE_NOT_RUN`，未发现阻断P1/P2。精确source `a3b66f736851bba70a083a4a60c6b3badb1d670a`，tree `3a3088286f56df24d19054f4166eb3ecf4326e4a`；parent `0f0e5a3`。仅三个新文件1213行：`gc_fixture.py`、`test_gc_pg.py`与GC_FIXTURE_PLAN。已独立比较其backend Git tree与Root `49077566c9ad8f3b1696aa3d8fc46b7ef1d57fbf`相等。实际运行须使用Root冻结的最新已审组合，不能把本候选的源码基线默认为已含后续tag等修复。

本审查仅精确提交对象，不读作者WIP、不合入其源码、不调用PG/restore/服务/解析子进程，不直接派任务给GC owner。范围依据 [GC最小边界](GC_SCOPE_4907756.md)。

## 初始化与受测权限边界

正常源图由复用的随机新 `v4_demo_<uuidhex>` fixture创建，migrate/initialize_fixture后由正常DemoStore/BusinessStore产生tag、fulfillment、confirmed import与parser停止回执。restore不接受外部导入档案或任意SQL，调用点只有历史测试初始化；新库名约束只是附加检查，真正来源绑定来自该fixture的CREATE DATABASE及正常populate链，不能将函数单独接到旧库工具。

`gc_fixture.py:433-509`仅一个专用owner事务使用 `SET LOCAL session_replication_role=replica`，只更新明确目标图中的日期及依赖preview/request摘要，UNKNOWN变体独立插入新reservation。每条更新核rowcount1；不改主键、角色grant或生产函数/trigger。正常源图先验证，初始化异常由连接context回滚并关闭；成功恢复origin、校验并COMMIT后，再用新owner连接核origin、目录、实际图和全部约束。GC与actor在新的连接中调用原逻辑；没有在replica模式下执行被测GC/actor或放宽原保留期。

原目录验证包含全部business trigger（含内部FK）、函数定义/search_path/ACL/definer、表列ACL、约束和索引；初始化前所有trigger必须O，前后目录相等。基线来源仍依赖Root按精确组合迁移的新库；不是任意既有库的安全认证。若Root配置的初始化owner不能设置replica，应按实失败返回，不给app扩权、不自动修改权限或旧guard。

## 独立数据核验与复杂度

`constraints:242-331`对实际行逐项重算完整有序复合FK反连接，含MATCH FULL混合NULL拒绝，CHECK的IS FALSE语义、NOT NULL与非NULL唯一键/部分索引重复检查；不是仅看convalidated。该检查器限定当前冻结business schema，不是生产恢复框架。本轮冻结迁移未发现NULLS NOT DISTINCT唯一索引；其普通NULL-distinct假设不能外推给未来schema。

`historical`先深拷贝，统一减48h；preview内expiry、session-expiry参与job_digest和confirm request/payload摘要同步更新。`_same_graph`比较实际图与完整预期图的摘要；`validate:512-762`另核关系、寿命/保留期、两店三persona、bound身份、canonical/request/effect/normalized/mapping/job/file摘要及receipt/event/effect绑定，并与原SQL preview_digest/effect_summary互验。新验证连接从实际PG重新取图；它不是只验证内存expected。对照tenant和全库其他表指纹另有核验。

部分纯变换与检查共享canonical/preview helper，所以不能只凭自洽摘要证明正确。候选已有独立历史时间输入调用生产prepare_preview的离线金标；源图又须先经正常生产路径提交。本审查确认这两层能作为候选防护，但它们仍不证明实际SQL恢复可执行。1213行主要由上述目录/复合约束/历史关系检查与五用例构成；未发现新增生产通用框架或无关范围扩张，不要求为压缩行数删掉独立验证。

## 五个PG用例的实际证明范围

- A双向2例：原resolve/read_guard与原gc_tenant分别先占锁，独立连接通过pg_blocking_pids观察阻塞，释放后核actor成功或GC_NOT_READY及全库零变更；保留5s statement/1s lock边界，不将timeout或deadlock当成功。GC未到retain分支只取得tenant锁的事实明确。成功路径等待future完成；任何线程/连接异常仍须由Root窗口完整清理，不以测试断言替代资源回执。
- B commit：目标和对照均正常populate后才历史初始化；实际执行原gc_tenant，离开连接context完成COMMIT后独立重读。六V41表及预期V4目标行归零，shared身份按原逻辑保留禁用/撤销，policy/fixture/对照tenant/非Demo sentinel及不在允许变化集合的其他表保持。
- B rollback：原完整删除路径在事务内先核目标行归零，再主动rollback；之后全库fingerprints与before一致。证明该删除事务回滚能力，不冒称覆盖每个SQL点的注入故障。
- B unknown：另添独立key/process_ref、无preview/stop_proof且占slot的UNKNOWN job，保留原已确认STOPPED job；原GC必须V41_PROCESS_HOLD并全库不变，不把手工UNKNOWN冒作本轮活进程/reap证据。
- commit后的旧token由原resolver及原V41 read_guard分别拒绝，拒绝后全库指纹再次不变。该token在GC前已经过期；这只是历史删除后的顺序拒绝，不是有效actor自然跨24h或合格GC与活跃actor同时成功。

## 验证事实及准入限制

独立检查两个Python文件AST/compile成功，未执行模块、DB fixture或测试。作者报告5PG仅collect、1offline shifted prepare_preview金标PASS、Ruff/mypy通过，本Reviewer未重跑，不转成实际restore/GC通过。PG数据装载、privileged初始化能力、全目录查询兼容/耗时、真正COMMIT/rollback/UNKNOWN阻断、并发屏障与清理均待Root精确新owned窗口。

可将此三文件候选交Root组合到最新已审头，再进行新的精确运行准入。窗口须分记正常populate/parser与历史初始化/受测阶段，保留origin/目录/数据验证、实际退出和资源清理事实。实际失败不放宽guard、FK、canonical或时间约束，也不把旧UI/其他22专项结果代签这五节点。本报告不授予生产恢复、旧库访问、自然24h等待或app复制权限。
