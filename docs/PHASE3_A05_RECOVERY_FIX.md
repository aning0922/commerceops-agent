# A05 实际 CI 失锁节点失败后的测试同步修复

2026-10-11，Root将恢复诊断派回原A/WT62c8/`codex/phase3-approval`/PR37。首步骤登记UTC21:20:41（北京时间05:20:41），固定30min截止UTC21:50:41/北京时间05:50:41，不重置；最多两轮定向PG、一次最小实现批次。本批已完成两条pytest命令及第一诊断轮一次确定屏障probe，资源提前停止，不继续追加PG。仅改一个恢复测试和A阶段证据文档，backend/Worker/Graph/三态恢复文法/sharedCI/B/Python锁完全不改，暂不push或编辑PR正文，等Root协调两个已审小修复为一次候选。

## 本次实际失败与未取得的证据

source972f98a/tree3d4f46的[CI38086696815](https://github.com/aning0922/commerceops-agent/actions/runs/38086696815)并未通过。Root核实际checkout `b4d837a56acf3bb15fd227d5f39cce3e20bfddb1` / tree同972，两安全artifact同源：quality旧236PG/G1三/G2六/cleanup0成功；phase3首审批模块28actual complete collection中27passed/1failed/265.02s，后73P3 not_run，pg-pair正确拒绝失败分区。失败节点为 `test_p3_lost_worker_lock_exits_and_requires_os_confirmation[before_prepare-False]`，call6.7587s，job114314619053，21:18:47UTC FAILURE，command_exit1/timed_out=false/stopping_confirmed=true，project p123-1ad34a6426b8 cleanup_exit0。不是300s超时，不诊断为已证实环境故障或旧Issue23根因。

GitHub安全日志只有phase/node/summary，**原CI具体assertion trace未捕获，根因仍unknown**。Root已核972最终增量[Review5480825374](https://github.com/aning0922/commerceops-agent/pull/37#pullrequestreview-5480825374)无阻断，不抵实际失败。frontend另在B04 offline beforeAll的Linux lsof3490失败，首项failed/其余7not_run、真实三stage未启动；由原B独占诊断，A不触其WIP/资源。748/052独审与两个历史337绿CI、2e0 before_graph旧失败和修复、原333/988、B旧失败/取消/Review fullcheck not_verified全部保留，不能以历史Gate代本次结果。

## 第一轮实际定位

新项目 `p3a05fix-b5b874dc4280`，owner phase3-A05-recovery-WT62c8/UID501，随机loopback63692，新0700目录/0600密码与ledger/独立新卷/空Compose env-file。没有读取旧P1/P2/B/Reviewer窗口或密码，也没有读取.env/模型key。ignored launcher首次相对模块名调用exit1、零资源；随后在同固定截止内从根以显式PYTHONPATH运行该私有薄driver，不改产品入口或依赖。

原失败node本地第一条pytest实际 **1passed/5.11s，command5.768s**；未复现原CI失败，不能据此解除。随后仅一次既有 `after_t2_commit` 受控probe（exit0），没有随机sleep或反复追测：

1. before_prepare官方sync输入CP真实created、next=prepare_approval/core三字段/0interrupt，plan/approval/card/execution均0。
2. 终止该旧Worker锁连接，等待确切barrier_cancelled、释放stdin线程、旧OS exit2/reaped；CP ID/values不变、task needs_attention/WORKER_TERMINATION_UNCONFIRMED。未确认的新Worker实际TerminationRequired/exit2，明确confirm后才重入。
3. 恢复Worker在既有after_t2_commit屏障：task awaiting_approval已提交、plan/approval/card各1、execution0，而官方CP仍同原prepare_approval/core三字段/0interrupt。原 `wait_state(...awaiting_approval)` 会返回，但后续 `after.next == (wait_approval,) and len(after.interrupts) == 1` 断言确定性不成立。
4. 释放屏障后等原after_ready，官方wait_approval CP/1interrupt/完整plan绑定已持久，原core/job/一次计划及卡片保持，execution0。

这是合法PG事务提交与checkpoint持久化之间的**已实证测试观测竞争**，未证明生产恢复不变量失效；也未证明就是原CI未记录的具体assertion。原972该正向断言实际line971，私有probe首输出误标line984，错误标签原log保留，安全证据明确校正，不改写历史。

## 一次最小修复与第二轮

只修改 `tests/test_p3_approval_pg.py` 同一参数化用例：正向分支恢复时使用原after_t2_commit屏障，先严格断言task提交/原prepare CP/core/0interrupt/ready_at NULL/execution0这个合法间隙；释放后改用原wait_ready（要求实际approval.ready_at及当前task状态），再保持原官方next/1interrupt/core/job和plan/approval/card各1的全部严格断言。异常收尾只释放自有测试stdin屏障后正常stop/reap，避免测试断言失败留下自有线程。

durable未知空next负例仍严格attention/CP不改/0副作用，缺CP可信首次初始化和prepare CP的None恢复仍分开；没有新增node/interrupt/状态/权限、退化empty安全判断、重试/随机sleep、扩大timeout或伪造完成。静态检查发现初patch误命中另一恢复用例，未运行该错误版本；即时移回指定用例后Ruff/format/mypy通过，最终diff仅本目标测试27+/1-。

第二条pytest实际 **19passed/88.27s，command88.830s**，完整覆盖三态失锁3、两孤立记录2、三坏CP3、R05–07三真实kill、R17两delivery边界、新版提交CP间隙三分支、T4整事务前/后kill三分支；actual collection/每call及teardown均完成，无过滤后的漏项/skip。另19纯决定/OpenAPI **passed/0.67s**，Ruff/format/mypy目标文件通过。全integration仅collect337，未本地执行全337或第三轮；不把定向通过当新Gate。安全节点集合与受控CP/PG证据见[作者证据](contracts/p3-a05-recovery-author-evidence.json)。

## 停机与下一裁决

两轮后马上提前停止本owned PG：停前temporary databases0、其他base连接0、app rolsuper/createdb/createrole全false；实际running=false/PID0，volume与ledger保留、目录700及四私有文件600，不称cleanup0。实际UTC停止时间/原截止/Docker回执见[停机证据](contracts/p3-a05-recovery-stop-evidence.json)，没有延期或再启。

新精确本地fix冻结SHA/tree由Root交原Core独立复审，最终合已审B minfix后一次正常push及当前四CI；原PR37正文不再编辑。最终恢复与frontend Gate、main/合后CI/Issue33关闭仍pending，A不合main/关Issue。Phase3来源Mock/真实PG+session/自动simulated_web，新paid/provider及平台业务写0；生产/飞书扩权/Phase4、多Worker/自然故障/p95/长期TTL不外推。D1=10-10/D30=11-08/300h/P3 A32+B18+Review10=60h及人工H/L not_reported保持。
