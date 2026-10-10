# Phase3 A03 独审失锁边界的两项最小修复

2026-10-11，WT62c8/`codex/phase3-approval`/同[Draft PR37](https://github.com/aning0922/commerceops-agent/pull/37)。本批由Root在原A03独审真实PG阻断后派回，最多两项针对性修复；已实施两项，不合B/main、不第三修复，不扩大原预算。新冻结SHA以PR37下一head/Root回执为准；新独审/精确CI/Root Gate仍待，Phase3 in_progress。

## 独审失败与实际定位

原source `2e0d3ed5ba82dc98516a88e1edce5fc2e6a72deb` Core新自有PG首模块`tests/test_p3_approval_pg.py`实际23passed/1failed/157.75s；失败节点`test_p3_lost_worker_lock_exits_and_requires_os_confirmation`原line837期待next精确prepare_approval/无interrupt，实际空next。其余10模块/wire未执行，不存在原source独审通过结论。Reviewer容器ExitCode1/PID0，PG已停止保卷；A只读其指定approval.stdout，不读借Reviewer秘密或窗口。原作者333PG/988offline/32wire及原CI均不抵这项失败。

源码位置明确：旧测试屏障before_graph在compiled.ainvoke之前，不能保证已有durable input/prepare CP。释放stdin后锁丢失取消与ainvoke初始保存存在竞争。独审日志未记录created_at/values，不能凭空next判该次是缺CP还是未知持久终态。fix1新自有PG的安全边界观测（基线2e0的修复WIP，before_graph逻辑未改）before.created_at=null、next/values空；该次释放后after出现真实prepare CP，exit2/needs_attention、plan/approval0。这是时点保证不足的证据，不谎称复现独审的同一after空状态。

## 三态合同与修复

第一项修复只新增prepare节点入口默认no-op观测hook，无状态/业务写，无新节点、channel、interrupt或框架。可恢复失锁用例先实读官方sync初始CP：created_at非空、next精确prepare_approval、workflow/task/request绑定正确且无interrupt，PG active_plan/plan/approval为0，再终止专用锁连接、OS exit2/reaped；旧OS未确认前替代Worker TerminationRequired，确认后None续同CP，同原analyze job/一个plan/approval/card。

before_graph无CP是独立边界。私有测试barrier在CancelledError时仅输出安全cancelled marker；测试先证实runner已取消before_graph，再释放stdin线程使进程退出，不随机sleep赌input checkpoint抢先保存。恢复仍保留原registered analyze job/scope/lease/session/旧OS确认/active_plan NULL及无副作用等guards，允许受保护的trusted expected首次初始化。与已持久空next分开；后者通过官方update_state构造，created_at非空、next空、core值不变，严格attention、CP不改、plan/approval/outbox/T4为0，不盲回START。

第二项修复针对Core指定的真实DB缺口：既有FK只约束task指向plan，没有反向强制plan必须被active引用；runtime角色可把非终态task.active_plan置NULL，保留pending plan/approval/card。outbox只有task FK，card-only亦能无aggregate实体存在。实际负例未停用或削弱任何约束，证明两类孤立状态可在本自有PG提交。

原TermUnconfirmed/activeNULL恢复UPDATE因此增加同task `NOT EXISTS replenishment_plans/approvals/outbox`，替代只排除decided approval。缺CP与prepare gap均不能把已有副作用宣称未开始；孤立状态维持attention/原记录数量，不新建CP或T4/业务。合法零副作用缺CP初始化和精确prepare None接续不变，不新增恢复API/表/调度器，也不自动修补孤立记录。

## 实际复验与未执行项

| 检查 | 实际结果 | 边界 |
|---|---|---|
| 首次三态失锁专项 | 3passed/23deselected/15.38s | 入口hook/cancel marker/持久空next负例；随后按Core补精准孤立guard |
| 最终targeted PG | 19passed/17deselected/91.33s | 三态失锁、两个runtime孤立负例、R05–07三项、R17两项、三种持久CP错绑、replacement pre/post/early新版T3三项、T4 pre/post三项 |
| 决定/完整runtime export纯测试 | 19passed/0.66s | 不是PG/浏览器运行证据 |
| Ruff/format/typecheck/docs/secret gate | Ruff通过，mypy177通过；最终format/docs/提交前后scan按实际收口回执 | 不把旧988/full333替代新全量 |
| 全integration实际collect | 337/1325 collected，988deselected/2.74s；337=236旧+101P3 | 新lost拆三态+两个孤立用例使原333增加4；不是337执行通过 |

精确19节点、所测三个运行/测试文件指纹、原失败和当前待核项见[安全作者证据](contracts/p3-a03-fix1-author-evidence.json)。Root明确不要求作者再无理由重跑本地完整337；新独审将完整101P3/迁移/actual22wire，精确新CI承担337回归，分别记账。原333/988只对历史2e0候选；原CI38076119191继续至terminal，不重复触发，也不抵独审失败。新source冻结后保持clean，后续仅Root集中派回问题。

## 新自有窗口与停机

项目p3a3fix-9b442ebfe1f9，owner phase3-A03-fix1-WT62c8、UID501/loopback62279；Docker前2026-10-11 02:39:53.662268+08登记，原绝对截止03:39:53.662268、60min不延期。fresh密码/ports/ledger600、目录700、ignored，仅此owned postgres；未借用原A03/Reviewer/B停止资源或旧secret/.env。全PG串行，未提高每条300/CI全局23min/job25min/cleanup75s。

实际02:50:38.460900835+08停止，02:50:38.727113观察false/PID0、tempDB0/其他base连接0、app superuser/createdb/createrole全false、base正常init至0007，700/四600，保卷ledger，不down-v/cleanup0。见[停机回执](contracts/p3-a03-fix1-stop-evidence.json)。本批实际provider0/平台业务网络写0、Mock/session/simulated_web；未用可见浏览器、OS键鼠或系统焦点。预计Agent墙钟20–35min是事前估计，实际登记/诊断/测试/停机时间按回执；人工H/L not_reported，D1/D30/300h/A32+B18+Review10/60h不变。


## 原CI完整负证据与新的容量裁决

原[CI38076119191](https://github.com/aning0922/commerceops-agent/actions/runs/38076119191) source2e0自然terminal FAILURE，未取消/重复触发。Root核988offline/129.66s和完整325PG（旧236/289.60s；P3 89，含旧approval24/247.03s，其余完整模块见[安全负证据](contracts/p3-a03-original-ci-failure.json)）通过；这说明原失锁观测竞争在本CI未失败，不抵独审失败。

projection于18:53:00.276811Z开始，18:53:19.735107Z因固定全局expires−75预算仅约19s耗尽而timeout，确认stop/exit137/cleanup0；第1项call+teardown通过，第2项在途，模块3项未完整。revalidation5及后续G1未跑。没有projection死锁或旧Issue23根因证据，不能以单命令300s不足解释或提高23/25/300/75。父merge c47f122仅Root已报短SHA，完整SHA/tree待核。

本两项business minfix正常commit，按Root直接指令暂缓push；独立受限CI容量批次由Root另裁决，属于后续CI工作，不冒作本批第三同源business修复。当前PG已停，无新资源；不减少测试/降低恢复Gate/触发已知容量不足的新CI。
