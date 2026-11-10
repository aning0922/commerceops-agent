# R4 phase3及pair终态独核

2026-11-05（台北）。结论：`PHASE3_FAILED_ABSOLUTE_WINDOW / PAIR_REJECTED_FAILED_PREREQUISITES / HOLD_NEW_CI_PENDING_SEPARATE_CAPACITY_DECISION`。quality拆组fba只修existing首组，不影响本独立phase3窗口；不得因此认为R4所有阻断已关闭。

run41864322517 attempt1，phase3 job126694464997、pair job126722298773均failure。本轮直接gh api actions/jobs/{id}/logs下载终态原件，不使用Root早期gh run view的1.3MB缓存。phase3原件1817916bytes/4056行，含完整18组命令；hash1b509b08ead562858c22fded04aa93ed292aa3f4b16eaf2e7a2edda6f5f279c4。pair log hash3f7df4b9753d2e8fbb6f255864cb3869a0e042b119fc5088e35707812ca5ff1c。

phase3及pair checkout原日志均305d0d2e3547c3d11cc42ca8da4bb2b51485cd5e；phase3 artifact同source/tree8f62a8a5e443916f55bf552e52276f641a8c3eab，与quality/候选树一致。artifact id13344189472，文件hash e6748b398404b2c5e259095a079fb4b902c9a22fe6ddd9a655ddcb743e3c6dba。

完整collection773，phase3 selected/actual collection177。18组中前17组全部expected=actual=passed/native0；末combined-phase3-test_p4_terminal_recovery_pg-part-3 expected4/actual4/passed2/exit137/resultfalse，总passed175。nullable_digits-0015已开始setup并通过、call未捕获结束；nullable_digits-0016没有node_start。不是两个已记断言失败。G1completefalse/count0、G2=[]符合phase3不承担existing smoke的分区边界。

## 末组真实窗口与累计证据

末part1实际16:45:12.769824→16:48:40.262518，207.492694s/native0；part2 16:48:40.290148→16:51:49.180402，188.890254s/native0。part3于16:51:49.209337记录command_start、声明limit_seconds300；16:54:41.102531 command_timeout，实际可用171.893194s；随后16:54:44.645170结束exit137/timed_outtrue/stopping_confirmedtrue/sample_errortrue。

原workflow在16:07:56附近登记48分钟绝对截止；原run通过budget=min(命令cap,expires-75剩余)分配实际duration。末组提前于自身300秒在16:54:41停止，与登记绝对截止减75秒一致，说明本案耗尽总窗口，不是末组独立跑满300秒。日志command_start字段记录请求cap300而非当时实际duration，不把它冒称获配300秒。精确ci-deadline文件未在artifact中另取，以上期限对应关系来自登记日志、执行代码及实际timeout时刻。

nullable_digits-0015 node_start16:54:07.959353，setup passed0.000473s，call start16:54:08.003457，距timeout约33.099s。0016未开始。无证据说明0015卡死或业务断言错误，未运行完的单项需求时长UNKNOWN。

前17命令实际start→end合计2447.152332s。18组command_start→首node_start累计217.352019s，单组5.290011–14.502674s，末组13.963528s；这是启动/收集等合计观察，不把它全部归为pytest collection或可消除开销。原已完成phase duration总计setup644.149863s、call1693.363914s、teardown4.659775s，含末组已完成部分，未完成call不补值。逐组派生表保存phase3-timing-derived.json，均来自同原日志，不执行测试。

## 清理与pair实际拒绝

phase3 cleanup_exit0/stopping_confirmedtrue。原最终project p123-a2ee62f8bfb1、cleanup stagecomplete/errornull、elapsed6.078s/remaining50.367s、owned_verified23/removed23。按本helper原回执核，不签全主机资产。sample_errortrue与失败保留，不抹为纯绿。

pair实际成功取得两份本run/attempt artifacts，然后Verify步骤执行第一个test 'failure' = success便exit1；未执行Python严格checker。不能把pair失败写成artifact下载缺失，也不能冒称checker已实际运行并给出特定错误。两artifact source/tree/fingerprints/full_collection_hash/full_node_ids逐项相同；实际收集并集467/773、交集0，quality只有268通过且G1未完成，phase3只有175通过。因此即便离线评估也不具备严格配对通过条件，不另运行checker制造新门禁回执。

## 最小下一步范围

当前只修改quality分组不足以解决phase3总窗口耗尽。先由Root决定新phase3容量候选：利用已有逐组/逐phase时长，审查是否能在原节点与顺序/锁/cleanup合同下削减重复启动或安排完整分区负载；不得猜测单节点性能或删除/跳过nullable用例，也不自行扩大超时/总窗口。若原期限内无法给出可信安排，应将所需容量作为明确新授权边界，而非直接用fba候选再碰运气。当前没有证明任何新方案必过。

本轮仅只读API、冻结源码、原件及时间派生；未取消、rerun、启动PG/服务或修改业务。R4quality原失败与Web/N01另审通过分别保留；原R2镜像UNKNOWN不能由本轮镜像成功倒推关闭。
