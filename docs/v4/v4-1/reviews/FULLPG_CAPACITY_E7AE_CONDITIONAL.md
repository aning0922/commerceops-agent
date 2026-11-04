# V41 新独立FullPG窗口容量方案条件审查

日期：2026-11-04（台北）。结论：ACCEPT_CAPACITY_PLAN_CONDITIONAL_NO_RUNTIME_GO。拟议新案helper45分钟、outer55分钟/300秒reserve可保持当前本地V41 Gate与权限边界；本回执不是资源GO，也不判断尚未闭合旧案的最终根因。实际closed满足下列条件后，由Root登记新对象和绝对UTC再决定。

权威依据：精确 `e7aeeca90e98cc4af5b5f8f8ba0faddd33182bd6` / tree `4e8349cfeec323668be316426871bc310b6ce53d` 的FULL_GATE_RUNBOOK第33/41/67/69/73/75/77行：Root按动态分组和实测开销分别给新窗口，不共享短窗续期；原每命令300秒、collect30秒、截止前75秒停止业务、cleanup最多60秒保持。helper只消费预登记--deadline，没有固定本地35分钟上限；本次仅改变新案总窗口参数，不改helper代码、测试分组、Hosted/workflow或历史P4的窗口合同。

已核来源：8f668→e7ae的非文档差异仅Shell spec、tests/test_quality_gates.py和tests/test_v4_scan_compat.py；后两者pytestmark均offline。backend、所有scripts、PG测试、14项LOCK_FILES、workflow均同字节；两个扫描期望测试已有04b547c精确独审，不能据此削弱生产scanner。pg_diagnostic SHA256 `5256f926724113f9cfb7efc138551492fd4a09f57b9ec530fa404fb0ba46dfe8`，pg_ci_evidence `379c302ca0e57163740a37f5bba2034aaf2f878ef3a2c96f9ec01f0bdbfb7b7d`，均与8f668相同。

容量只作规划：按Root转交06:08起算、06:11:13实际helper启动、06:43截止，启动前消耗193秒，旧业务余量=2100-193-75=1832秒（30分32秒）。已归档旧existing总用时1947.500秒含cleanup5.227秒，本身就高于该余量；新28项约20秒是Root估计，不是本轮测量。若新45分钟仍有同样启动延迟，业务余量2432秒（40分32秒）；若实际helper启动时完整余量45分钟则为2625秒（43分45秒）。更大总窗有容量依据但不保证必过，单条命令超过300秒的问题不会由总窗修复。必须分别登记准备起点、实际Popen起点、helper绝对stop与outer绝对stop，不再把GO到Popen的准备耗时隐去。

冻结前Root新增转交旧案结束摘要：项目p123-1c0b9b89188c，helper/outer1、cleanup0，独立容器/网络/临时卷0、35组消失、source identity不变；helper actual577，call568=567PASS+1deadline中断，另28未开始，G1未运行、G2六项有记录，create-and-template137/timed_out、此前已完成命令0。actual577不等于577PASS，不能拼成完整existing通过。此处明确为Root摘要，最终closed hash和末组实际预算/秒数尚待GATES封存，本轮未独立读取原件；565/31是更早快照，不覆盖新摘要。该摘要支持继续准备新窗，尚不替代下面的具体GO证据条件。

Root GO之前的明确条件：

1. 旧existing实际helper/outer终止并封存原round-1、日志/JUnit/collection、每组expected/actual/passed和未call列表、G1/G2状态及独立cleanup。565PASS/31未call/first-create259.18秒等当前数字只是Root转交的运行中快照，本轮未读取旧案raw或定因。须由原生时间线确认是总deadline耗尽、没有独立业务断言失败；被总截止截断的末命令非零/timeout仍单列。若发现单命令完整300秒超时、业务断言失败或停止UNKNOWN，本容量方案不能代替该项诊断/修复。
2. 新existing-r2用新独立checkout/audit/owned资源，仍按原CI入口--session ci --round 1运行；r2是新案标签，不是把CI改为--round 2或删除旧round-1。不续旧窗、不改旧once、不补跑剩31项来拼旧565；新案完整运行自身全部selected。旧案临时owned卷按原canonical cleanup删除，其他保卷/私有资产不受影响，关闭不明不得当作已清。
3. existing与phase3统一同一精确候选SHA/tree、工具/锁/镜像平台和新binding；复用PG image须Root核实际ID及六项inputs并批准新binding，不复制旧source receipt。预留清晰不可变：helper45分钟业务仍在其截止前75秒停；outer55分钟减300秒后的监督截止应晚于helper硬截止，同起点时相差300秒。外层额外时间只用于监督/取证/清理，不允许业务越过helper截止；准备过慢则在启动前HOLD或另登记未启动的新窗，不能运行中重锚截止。继续遵守Root既定第二线等待engineering与第一线闭合的编排。
4. 新候选重新动态collect，预期现有完整773节点及原分区（当前预计596+177）须以实际节点ID/hash核定；不靠数量相同替代全量集合。新发现差异先核来源/工具，不删节点凑数。G1三项、G2五required加retired-probe负例共六项原样保留，phase3不重复认领smoke。

最小验收依据：两线各自原始helper/outer native0、所有模块expected=actual=passed且exit0、完整collection/hash与工具/14锁一致、G1/G2原件完整（预期负例非零不改0）、cleanup0/stopping confirmed、独立标签容器/网络/临时卷与进程关闭证明；再由同SHA/tree checkout运行原pg_ci_evidence并实际native0，证明完整并集773/交集0。保留所有旧失败、未跑和容量事实；新FullPG不代替独立工程/scanner、HTTP、browser或Native验收，也不把工程旧SHA结果改挂新SHA。

本轮仅只读合同/精确Git/静态预算计算，未运行collection、pytest、PG、Docker、服务、SDK、镜像准备、Full或远端操作。待actual closed后才可进一步给Root具体窗口GO判断。
