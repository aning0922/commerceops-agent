# V41 TERM忽略/KILL增量与模拟原件审查

日期：2026-11-04（台北）。候选 `5f5aaf58e578781c7305377fddc5f463ad4f6ad3` / tree `4173d19a6463e76fd3053585da29032d5ea7d873`，通过47e9006普通合入Root合同，549d67基础原样保留。

结论：ACCEPT_TIMEOUT_SIMULATION_INCREMENT；整体监督基础仍因P2-Q01保持HOLD。该增量不改process.py或runner.py，因此不会关闭身份探测/注册异常导致清理与最终回执缺失的问题（见QA_FOUNDATION_549d67c.md）。允许保留本增量与真实模拟事实，不把它签成PG槽位、解析器硬截止或业务StageGate通过。

## 精确增量

仅sleep模拟在等待前安装TERM忽略并输出ready标记；timeout测试由允许TERM/KILL改为必须native -9且有ready标记。QA_PLAN增加与84db合同对应说明，并明确本机短进程不能代签真实解析/PG slot生命周期。未扩任意命令、服务配置或资源权限。

## 原件核对

读取作者树 `.audit/v4-1/qa-ops-simulation-02/` 六组checks/outer/summary/launcher及相邻XML。JUnit实际7 tests、0failure/error/skip、2.319秒。六组记录的运行HEAD都是 `47e9006eb21d78e91df1e30b5cf25ad230c0b6d2`，不是后来提交的5f5aaf5；逐项比对记录的uv.lock和全部监督Python输入hash，均与5f5aaf5提交字节相等，前后binding相等。此为父HEAD加提交前输入字节证明，不改写实际运行HEAD。

- normal：probe/observer/cleanup native0，worker与launcher均0。
- nonzero：probe3，required失败，worker/launcher1。
- timeout：probe timed_out、native -9，ready标记存在、登记group_absent，worker/launcher1。
- observer_missing：observer native0但无观测原件，checks失败，worker/launcher1。
- cleanup_fail：required成功但cleanup4，worker/launcher1，不伪装整体成功。
- summary_fail：checks先持久化且通过，摘要KeyError另记FAILED，worker/launcher1。

六组outer均记录worker_reaped、无outer timeout、remaining为空；checks/summary/worker-log回执hash全部匹配。这里只核历史原件，没有再次探测当前PID或声称全机资源0。原增强changed-public预检run `0401a6a60a92-47e9006-1f6d13f26b2ad746`回执为dir/index各native0/0finding。

原件增强了六固定路径证据，不包含leader已死但后代存活、ps超时/非零、注册写失败等Q01场景。修复仍须作者另给精确SHA；不得读取或合入当前owned_manifest WIP。本次无受测进程/服务/PG/API/browser/network重跑。
