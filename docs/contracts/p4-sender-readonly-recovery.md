# P4 原来源与后续 sender 分离的 v1 只读对账合同

2026-10-14（Asia/Shanghai）。原 A/WTfd38/PR43 的合同修复候选，基线3f9b3aeb。单original Gateway同时约束旧receipt与后续005 SDK，是原Core确认的准入P1。真实RO、最新源码PG、精确独审和新CI尚待，不宣称M1或Phase4通过。

## 可信来源与 sender

`ApprovedOutboxRecovery` 保留原入站Gateway id/hash/终止、receipt/source/actor与原task/plan/approval/execution/hash，新增可选 `sender_gateway={gateway_id,gateway_hash,termination_id}`。省略该字段时保留旧sameGateway与v1/v2恢复；新路径只接受唯一原v1 projection，origin/sender/new Gateway互不相同。

三段claim均来自同org/shop的实际不可变audit，核hash、原Mock参数、完整started/process/reaped/int-exit终止。origin终止先于sender claim；sender Gateway started、旧Worker started、持久授权、SDK创建、C调用按实际时间相连；sender Gateway/Worker终止均先于新reconcile claim。旧child OS须不存在。Worker确认按owner/明确事件ID、同host/namespace和显式原因验证；其PID可属于执行确认的parent，不能错误按child PID遗漏。

`approved_workflow_claimed.id`须等于实际sender SDK window ID，其中完整窗口必须是enabled的approved_first_create，绑定sender Gateway、SDK caps/expiry、唯一原task/projection、origin claim/hash/终止、receipt/approval/decision/execution。当前task binding与不可变approval/decision hash重核。不能用任意Gateway、caller声明或仅C回执补链。

sender SDK须真实controlled/enabled、同org/shop、完整hash相等；创建/expiry在sender Gateway有效跨度，实际创建和C调用须早于sender Gateway停止。sender auth须唯一returned200/code0并在旧Worker生命周期内。C历史须全局唯一returned200/code0，同outbox/task/scope/window，处于SDK及Worker跨度。源SDK cap不得超原first-create ceiling，C上限仍1。

## RO 准入与落库

当前原operator/approver身份、App/Tenant/白名单、角色/auth版本/shop scope继续原可信检查。task completed、plan executed、approval approved且consumed、execution completed、item open/v1，完整原payload/15字段projection/request hash/client_token不变。首次RO需unknown/attempts2、原sender owner、无external ID、C1/anchor0。

当前caps仅auth1、bot1、table-list≤2、field-list≤2、record-list≤4，总≤10，C/U/IM方法缺席、provider0。只分派原outbox，Graph/job/IM不执行。完整分页、唯一原key、15字段及SyncVersion1相等后，原Base adapter仅reconcile，PG协调器写anchor/verified与ledger/audit；task/plan/approval/execution/item/CP不变。这是远端API只读，包含正常PG对账落库。不存在/多行/不同record/不完整/unknown/429/5xx/权限失败即停，不create/update、不换key。消耗attempt3，失败后不追加窗口。

private bridge保留C0原mode/profile/caps/C0/anchor0，增加显式readonly_reconcile的DTO/profile/只读cap/C1闭合分支。复用R13 pinned observer、canonical Worker/Factory/单child/Graph与late Secret；只刷新必要源pin metadata，原R13实现不改。RO terminal须完整唯一PG验证、parent/child reap、owner生命周期、Gateway停止、disabled恢复及owned down保卷；程序切片result/exit不代签M1。

## 实际证据与验证边界

原005六方法各一次HTTP200/code0、原key Create1/upper ACK-drop1；PG unknown attempts2/BASE_WRITE_UNKNOWN、C returned1/anchor0，是受控故障而非完整读回。真实parent确认已按owner核实；旧child PID收口查询遗漏、旧verification_failed、binding准备时间HOLD、提取字段错误、closed-window/once原字节保留。

首轮新owned合成PG前12节点通过、末个C-history夹具回退attempts被既有保护拒绝。既有diagnostic helper清理实际删除本轮合成首卷，先前保卷说法已更正。第二轮同project/同09:02:09Z截止重建合成资源，14必要节点通过，08:53:58Z停止PostgreSQL；18已退出one-off核完整ID/project/stopped后普通rm，08:57:45Z容器0/网络0，重建卷保留。不能称首卷保留或同卷续测。

最后auth/decision/历史cap/时间补强、SDK-span负例与13拒绝子例合并后的最终两个节点未跑最新PG。旧12/14仅签当时字节；当前源码与运行时hash证据缺口按最终freeze分列，原Core与新精确CI须补齐。当前真实准入HOLD，无PG第三段。本批SDK/AppSecret/provider0，原known70/P1/P2/P3资产0访问。

D1/D30、300h、P4 50h估计、18页冻结、人工H/L not_reported不重置。B/C/前端/CI/锁/迁移/Gateway/审批状态机/Worker Graph/生产/Woo/P5不扩写。Root源码窗口08:22:06Z→09:52:06Z，不续期；本批不push/main/关Issue。最终纯检查、候选SHA与未测项以冻结回执为准。

作者当前完整offline1806通过/480 integration排除/4 warnings/103.19s，Ruff/format417/type310/Markdown103通过；与最新PG待核分开。敏感扫描与最终private Fake/源pin/候选SHA以freeze记账，未执行平台RO。
