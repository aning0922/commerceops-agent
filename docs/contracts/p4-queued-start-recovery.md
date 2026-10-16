# 原 T1 已受理、Worker 未启动的单任务恢复合同

## 本批与状态

2026-10-16，用户批准原任务恢复整批，Root 从原 P4/300h 内登记新增上限
8 Agent 有效小时，建议 A5.5/Core1.25/Root1.25；旧 9.5h、追加 3h 的实际估算、
全部失败与 SPENT 不重置。机器等待及人工 H/L 分列。当前为实现/审核候选，真实运行 HOLD。
不创建新会话、分支或任务；原 A/WTfd38/codex/phase4-feishu/PR43 接续，C 文件独占不变。

真实准备不得重开实际 PG、读取 AppSecret/Token 或启动 Gateway/SDK。
旧唯一只读窗口已经 SPENT。新 owned PG 与 HTTP/WS 传输 Fake 可验证同一实际入口代码，
SQL、权限、DTO、审计 once、原 Worker/Graph 及 Web close 不作替身。

## 固定原对象与唯一变更面

新增受控验收 profile `approved_queued_start`，只接续已存在的一个原 inventory task。
其原 source task、两个原 job、原 inbox/receipt、原 Gateway claim/hash、原生 started/
termination/OS 生命周期、原参数/config_version 及原 A auth_version 必须逐项绑定。
旧 `known70`、`approved_workflow`、outbox/terminal profile 的保护和历史解释保持。
不伪造原 Worker/SDK 历史，不以新 Gateway 的新 receipt 冒充原 T1，不重投消息或新建 T1。

最小源码面：recovery/worker_window DTO、独立 queued-start SQL validator、
feishu_worker_child 窄准入与逐轮原权限重验、原 Gateway child 的最小就绪回执适配，
必要纯测试/PG 契约与事实导航。无迁移、schema、业务状态机、角色权限或 C 产品改动。
实际父入口沿用现有私有 `local_services_cli` 与 V2 共享 handoff，
补 Root 单次 permit→本机 arm→原 native Gateway→最小就绪→原 native Worker；
不添加 wrapper、通用调度框架、CI job 或协议验收 Gate。

## 原任务准入与当前身份

初次 Worker 准入须同时满足：

- 原 claim 属于同 App/Tenant/org/shop，完整 immutable JSON/hash 匹配；
  原 started/termination 唯一且 PID/host/namespace 完整，child 已 wait/reap，时间顺序成立。
- 原 inbox/receipt 唯一、原 principal/identity/requester 绑定不变；
  receipt 在原 claim 之后、原 Gateway expiry 与 termination 之前。
- 原 inventory/source 两 task 都是 queued、v1、无 plan/failure；原参数/config_version/hash 相等。
  两个 job 的 id/task/kind/dedupe/payload 绑定固定，均 ready/attempts0/no lease/no last_error。
- 原 Gateway claim 至新 Gateway claim 之前无 Worker 启动或 SDK window；
  两原 task 无 analysis/approval/execution/item/outbox/Base/IM delivery 等业务副作用。
- 新 Gateway active、max_workflows=0，参数等于原参数，组织店铺仍为原 mock/test 范围；
  新 Worker 仅原 inventory task，原 source job 只能通过现有 controlled_task_ids 收入。
- 重新核当前 A principal enabled/auth_version、原 Feishu identity、当前 App/Tenant/allowlist、
  operator/shop 权限；queued v1 初准入必须无 approval，不要求不存在的旧审批。
  原任务正常推进至原生审批阶段后，绑定该阶段产生的 approval/version/nonce/TTL，
  并重验当前 approver 权限，不预造或重开审批。
  原白名单 A-only/group0、known_inbound L3/R7/S2 与 SDK 14 上限不放宽。

初次状态验证与 once 授权在原单 Worker 锁内执行，先于 SDK Factory/秘密读取。
后续每轮重验原不可变绑定、当前身份权限、新 Gateway active/就绪与已授权同一窗口，
允许原 Graph/Job/审批状态正常推进，不重新要求已完成的 job 仍 attempts0。
未知发送或未知 Base 状态沿既有停止规则，不新增盲重试。

## 独立 once 与失败 SPENT

Root permit 的消费先以独立持久文件提交成功并 fsync，不与后续 DB/进程工作回滚。
父进程在该消费和本机 arm 后、真实 Gateway 读取 AppSecret 前，
以原 org/task/inbox 派生固定 UUID，在原 immutable audit 表持久插入 `queued_start_attempted`。
该 attempt 使用独立 DB 事务，commit 成功后才可启动 Gateway/读取 Secret；
记录绑定唯一新 Gateway/Worker window、原对象清单与本机固定 expiry，跨新窗口也不可再 claim。
父 permit 与 DB once 均失败 SPENT，不删除、不改写、不补造旧历史。

Worker 初次入口在同一单 Worker 锁内，使用独立 DB 事务提交同 window 的 admission attempt，
确认 commit 后才执行完整 validator。全验通过后写 `queued_start_authorized`，
该事务 commit 成功后才允许构造 Factory/读取 SDK Secret/发出调用。
validator、ready、spawn 或 SDK 异常不得 rollback/delete/reclaim 已提交的 permit/attempt/admission；
失败只留已消费事实、无 authorized 时 SDK0。
同 Worker/window 冷重放、不同窗口重投、并发 second claimant 都拒绝。
后续 claim=False 只能消费已存在且完全匹配的 authorized，不能再授权。
输入在许可消费前结构拒绝与消费后 SPENT 分列，不把未执行准入写成通过。

## 最小可靠就绪与父协调

原 Gateway child 已有 started 在 AppSecret 读取之前，不能代签就绪。
使用锁定 SDK 的窄连接适配：原 `_connect` 完成、实际 WS State.OPEN、
原 message/card 两 handler 已装配且同 client receive task 已调度后，
在原 audit 表持久一次 `ready`，绑定同 window 与原 PID/host/namespace。
不记录 endpoint URL、Secret、connection id、payload 或 raw frame，不新增 observer 进程。
该回执只表示连接/handler 运行就绪，不新增 subscription/raw-wire/ACK 形式验收 Gate。
该最小就绪适配由本受控恢复入口显式选择；其它既有已验收 Gateway 继续原行为。
本恢复入口无自动重连；连接/适配/持久失败由原 parent terminate/wait/reap，
业务 SDK0、once SPENT。

Root 后续统一实际对象、ledger 与绝对 T0，唯一父窗口最多 1500s，末尾至少 180s 清理。
页面 ready 后必须留下至少 600s 登录机会；本机收到绑定本窗口的 Root ready 确认后才 arm。
页面 ready 最晚须满足 hard_deadline-1080s，latest_arm 不晚于 hard_deadline-480s；
余量不满足即拒绝，不以 dispatch 时间差续窗。本机只捕获一次 arm，expiry=arm+300s。
新 Gateway/Worker 同 expiry、各最多 300s；Worker 绑定/启动时余量至少 180s。
父进程连续等待/观察/绑定/启动/停止，不能依赖 Agent 工具轮询拼接。

业务 SDK 八方法上限 14：auth1/bot1/table2/field2/IM2/create1/update1/list4。
旧定位2、metadata4、旧 WS 与旧 permit 另记，不重置总账。
仅原 A 批准一次及同 item 原生 Web close 一次，原 record v1→v2；无新 DM、扩权、
paid/provider、生产/Woo 或旧 known70 库访问。真实失败/unknown 即停，不自动续窗或重试。

## 同源验证与冻结

最终同候选实际 outer 在新 owned PG + HTTP/WS 传输 Fake 验证：
正常原任务审批→v1→同 item 原生 close→same record v2；撤权、绑定篡改、
并发 once、冷重放、停止、未知故障。真实 SQL/权限/DTO/once/进程路径不替身。
先保存脱敏 facts/SQLSTATE，再判断；未查询、查空、不唯一、找到、余量不足分列。
业务 exit、cleanup exit、容器/网络/端口/PID 与保卷分别记录，失败也保留。
真实资源的纯绑定检查不得冒称实际执行，实际平台证据须新窗口另核。

合同/功能由原 Core 独审。源码先本地 commit 冻结，不提前 push 或编辑 PR43 正文；
PR synchronize/edited 均会触 CI，由 Root 核收后统一释放唯一 push/精确 CI；
原 506 PG 与新增必要节点、G1/G2/Web/截止/配对保持，不削弱门禁。
准备/owned/独审/CI 不签真人或 M1 完成；真实具体 UTC/对象/ledger 准入仍 pending。
