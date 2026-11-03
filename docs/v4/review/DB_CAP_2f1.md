# V4 provision并发DB容量2f1专项审查

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_PREPARED_DB_CAP_COMPONENT，0 P1 / 0 P2。** 当前单节点可交ROOT在新owned窗口执行；只验证原provision数据库容量竞争，不证明完整DemoStore/create HTTP五并发吞吐，也不代替原串行五访客或QA并发reset。

candidate `2f1e98d26e466bcb1d0c287aedfb43c2536af62b` / tree `052eabc3fc5229bfaa479acd27033a0a1345649a`。实际直接parent是`bb601d01e019451ac34b22148e9f1e3b7b92ca27`，不是dc439；链上还有1c192d4/7ff538c/b9e293b等已提交切片。本提交exactstat只有`tests/v4/test_demo_sessions_pg.py`和`docs/v4/design/IDENTITY_SQL_PLAN.md`，未改SEED_SPEC或seed_pg。本次只接受当前替换后的DBcap测试和对应口径，不顺带签中间其他身份/ACL增量。旧bb601完整create竞争测试尚未执行的事实及ROOT纠正保留。

## 分层与实际连接路径

新增节点为`test_five_runtime_provisions_commit_three_and_reject_two_at_db_capacity`。独立比较Git blob确认Store、Sessions及0024与dc439源码均未变；没有改_HASH_SLOT(1)、rate限制或SQL advisory锁，也没有monkeypatch hashing/连接/锁。

测试先用真实scrypt算一次新随机credential hash，随后五次真实bootstrap，每个owner/key用demo.app独立事务UPDATE并完成COMMIT后才加入worker列表。五个bootstrap UUID及原key分别唯一。credential预计算和直接SQL调用是此次明确的provision层测试隔离，不是替换完整create路径来制造HTTP吞吐承诺。

每worker用自己的connect(demo.app)，设置原bounded SQL/lock timeout，查current_user必须commerceops_app并记录pg_backend_pid，在六方barrier（5worker+caller）前保持连接打开。Barrier释放后直接调用原SECURITY DEFINER provision，由其内部原advisory xact lock排他；线程中没有owner连接或手工获owner权限。这里低权指函数的runtime调用者；受限provision本身按已审设计以owner权限登记新对象，不能描述为runtime拥有任意直接INSERT权。真实rolsuper/createdb/createrole等仍应由ROOT同窗口角色事实核定，不能只凭role名扩签完整ACL Gate。

只有离开真实connect事务上下文、COMMIT成功后才返回committed Outcome。唯一捕获是CheckViolation，保留sqlstate/message，最终精确要求两个(23514, demo capacity limit)；其他CHECK消息、锁timeout、连接失败、BrokenBarrier或Python错误都无法算容量成功。不会把RATE_LIMITED转换CAPACITY_LIMIT；该直接SQL路径没有测试HTTP429或Retry-After。

## 成功、失败预约与物化核对

执行前要求15个物化表全0。执行后要求3COMMIT、2精确容量拒绝及5个不同正backend PID；所有成功bearer再经真实Sessions.current核原tenant/creation key和epoch/generation0。失败owner的原key通过真实operations返回精确UNKNOWN/WAIT_READ_ONLY，runtime重读bootstrap要求原key保持、consumed_at为空，没有自动重试或换key。

15表精确基数：3 organizations、6 shops、9 principals/identities/credential、9 scope/role-shop grants、3 bound web_sessions、3 V4 tenant/session/receipt、6 V4 shop映射/events、9 persona映射、overlay0。另核活跃tenant/session各3、独立org3/shop6/principal9/identity9；tenant/session/creation receipt集合对应真实winner，receipt key和owner_session与winner一致，每tenant2shop/3persona。这样不仅数出3个返回值，也拒绝失败尝试留下额外物化或误踢成功tenant。bootstrap/rate独立admission不在15表中是有意保留，不把其存在当业务rollback失败。

## 线程与外层截止

Barrier各方10秒、wait(futures)45秒；超时有pending即断言失败，future.result(timeout=0)不会等待未完成任务。finally abort barrier、取消未开始future并shutdown(wait=False)，不在测试异常展开中无限join。连接仍用原connect_timeout5秒及statement5秒/lock1秒，未放宽全局role时间。

**45秒只是协调等待上限，不是强制杀掉运行中线程。** Future.cancel和shutdown(wait=False)不能终止已经进入psycopg的线程，Python进程退出也可能等待worker。异常时新库fixture的FORCE DROP是清理尝试；ROOT仍必须保留原测试子进程绝对截止/资源监督并记录pending、native和cleanup实际结果，不能把wait=False当“线程已全部退出”。正常通过路径要求所有future已完成才进入结果断言。此边界与当前有ROOT外层监督的新owned组件运行一致，不需为本case新增通用线程框架。

## 独立验证与交接

精确2f1源码快照下，仅collect该节点并把psycopg.connect设为禁止调用：**1 test collected / 0.88s / native0**。未执行fixture、scrypt、barrier、SQL或PG；所有临时文件已清理，无服务/外部调用。没有用纯替身模拟并发结果冒签3/2。

ROOT可以在已审组合source及新ownedowner/runtime环境运行该单节点；任意其他失败必须保留，不能自动重试或归为容量拒绝。原Store/HTTP串行五访客、完整create突发≤3且RATE/CAP分记、QA真实并发reset均独立。旧M3 Full、实际HTTP/Web/TTL未由此覆盖。APFS export发布EEXIST17及待交INDEX修复仅为ROOT转交背景，本轮未读该WIP、未修CLI或复用旧case。
