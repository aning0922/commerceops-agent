# 新增六例：真实child与GC有限运行独立核收

2026-11-04（台北）。结论：`ACCEPT_ADDITIONAL6_OWNED_PG_SCOPE_ONLY`。精确source `e54c603b267c06bff851822b8c2fdaef8fad3230`，tree `f5cb64a2309d4fbe1ed8b35fa861bb49ba890eed`；实际测试镜像 `sha256:a9aab23bed7c42674b55c5bc5abefa65dff59552612bbfce8932413e2ef5751d`。此次只核收新增live-child1、live GC双向2、历史GC commit/rollback/unknown3，不签一次同源全28例、Full、HTTP或整个阶段。

## 原件、源码与退出码

只读核验 GATES `.audit/v4-1/additional6-root-r1/` 的receipt、closedfinal、JUnit、pytest_once、final_owner_facts及关联原件。closedfinal SHA-256 `20bdec92dbb8da932da5cd748777f447619852bfc61188f79a808dae8653c22e`，其九项证据摘要与61条命令stdout/stderr摘要均匹配。逐例核JUnit：**6 PASS / 0 failure / 0 error / 0 skip，12.812 s**；collect六、执行六，pytest仅一次，collect/pytest/outer记录native0。另有1个offline例被本次integration选择排除，不计入六例运行。

镜像来源另核 `owner-ddl-build-r7` 封存回执、archive及制品摘要：expected-runtime的699文件逐项与e54c603 Git archive相等，内含216个package Python文件；实际image sourcecheck命令native0，确认非editable安装的216文件与源相同。新增六例命令使用该镜像及Python `-I`，未用本地WIP覆盖。GC两文件与已审 [a3b66f7候选](GC_FIXTURE_a3b66f7.md) 字节不变；本Reviewer没有启动资源或重跑测试。

## 五个GC节点的已验范围

- **LIVE_NOT_RETAINED双向**：actual pg_blocking_pids记录actor-first `135:136`、gc-first-not-ready `167:168`；对应JUnit均PASS，全business前后指纹逐项相等。原GC在retain前返回NOT_READY，反向原actor在事务放锁后成功。此分支仍不称session删除锁序或物理删除成功。
- **历史commit**：fixture明确标 `SYNTHETIC_OWNED_HISTORICAL_FIXTURE`、shift48h。目标六V41表的tag/fulfillment/import_products各1、events3、receipts3、jobs1，提交后全部0；目标原V4 tenant/session/persona/shop/receipt/event/bootstrap按原逻辑删除，shared principals/credentials各3、web_session1保留并由源码断言禁用/撤销。JUnit包含 `CONNECTION_COMMIT_RETURNED` 与提交后独立重读计数；policy/fixture指纹不变，另一tenant及非Demo sentinel检查通过。
- **历史rollback**：先在原GC事务内检查目标行消失，再主动rollback；独立重读的目标计数和全business指纹与before相同。仅签完整删除事务的主动回滚，不扩大为每个SQL故障点注入。
- **历史unknown**：目标含已确认STOPPED job和另一独立UNKNOWN job，共2；原GC必须PROCESS_HOLD且零删除，前后全business指纹/计数相同。未把UNKNOWN历史fixture解释为本轮真实活进程或已reap。
- 三个历史节点均有 `COMMIT_AND_INDEPENDENT_VALIDATION_RETURNED`。该记录点在原restore成功返回之后；已核相同源码的无条件路径包含专用初始化事务replica→origin、连接关闭后新连接origin/catalog对比、完整复合FK/CHECK/NOTNULL/unique和canonical/hash/interval验证。以精确源码、实际成功执行和返回点证明这些断言走完；这不是额外逐条SQL审计trace，也不是过期runtime INSERT守卫通过。
- commit节点之后原resolver和V41 read_guard均拒绝旧token，且拒绝后全库指纹不变；token在GC前已经过期，不宣称有效actor自然跨24h。三个历史节点观察DB UTC分别为04:20:04.530263Z、04:20:07.054601Z、04:20:09.559872Z。

## live-child单例的已验范围

精确 `test_forged_unbound_and_live_child_stop_denied_real_reap_after_revocation` 实际PASS。源码路径先原reserve，再拒绝无bind时猜测lease的假stop；真实子进程bind后 `os.kill(pid,0)`证明当时存活，猜测lease bind/stop和无独立调用能力的伪publish均拒绝，job仍RUNNING/占slot/无stop_proof。owner正常撤权后，原run_parser实际wait/reap，stop回调检查该PID不存在，以原lease完成STOPPED/slot清空；撤权后的publish仍拒绝，preview_data为空，DB stop_proof与native proof相等。

此项签原随机lease和调用能力边界、撤权后仅资源清理仍可完成；不签已窃取raw lease的任意攻击、父亡全部变体或所有S04能力。该JUnit没有单独导出PID/proof属性，进程断言来自同源已执行测试，不能补造独立raw进程回执。

## 清理、警告与不能合并的证据

封存原件核namespace容器/网络为空、61个CLI组检查输出为空，数据卷与socket卷两者保留。final_owner_facts中随机测试DB已移除；仅postgres/templates及本次root管理DB保留，client_connections为空；随后PG容器停止删除。app role无superuser/createdb/createrole。组/不存在探测native1是探测语义，不改成全部操作exit0。预期23514共6条，原件无deadlock/lock-timeout/query-cancelled失败记录。

pytest保留5条record_property/xunit2兼容警告；本次XML实际含完整GC属性，已逐项解析，不删警告或补造属性。当前签的是这份实际XML，不保证其他JUnit消费器兼容。

独立核dc22be3与e54c603 backend tree均为 `db79f2b4669ed1ead0e41adcf251768d8d635dca`；该等价性不把旧22与本次6合写为本次全28运行。旧22未在此窗口重跑，新Full另源另核。自然24h/过期正常runtime INSERT、HTTP/SDK/外部系统、旧CLI与Full继续NOT_RUN；历史初步候选/失败原件保持原状。本报告只更新上述五GC和一个live-child的有限运行状态，不含临时秘密或原始凭据。
