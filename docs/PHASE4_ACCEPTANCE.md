# Phase4 / M1 分层验收（实施中）

2026-10-11，Asia/Shanghai；[阶段39](https://github.com/aning0922/commerceops-agent/issues/39)/[A40](https://github.com/aning0922/commerceops-agent/issues/40)/[B41](https://github.com/aning0922/commerceops-agent/issues/41)/[交付42](https://github.com/aning0922/commerceops-agent/issues/42)。基线 main9d97c19009d932036809ac3e2638bb68f4b7f765，同 SHA 四 CI38093693335 SUCCESS，P3 Issues33–35 CLOSED；[P3结案](https://github.com/aning0922/commerceops-agent/issues/33#issuecomment-6103315682)及[历史证据](PHASE3_ACCEPTANCE.md)保留。用户已直接授权Phase4持续开发，本页不宣称M1通过。

## 当前范围与责任

A唯一共享合同/迁移/业务/outbox/Worker/Graph/Python锁/CI/Compose/阶段文档owner；B新Base三模块/测试/文档按Issue41独占，前端沿原owner。共享[p4-v1候选](contracts/p4-v1.md)与机器DTO/Protocol须Root独审后冻结。第一批仅offline/全新自有PG，真实平台0；资源有效性后续由Root受控诊断，不把旧probe存在/权限scope当作当前可用证明。

固定D1=10-10/D30=11-08/300h，P4 D13–17/50h，A18+B14+交付8+审核集成10是估计分配，人工H/L not_reported，Agent墙钟/机器等待另记。旧1057offline/337PG/24Web、旧失败/风险/资源/18页设计保留；无Phase5/Woo/生产/扩权/新成员/新增paid/强推/破坏清理。

## 必须证据矩阵

| Gate | 必需证据 | 当前P4状态 |
|---|---|---|
| 合同/身份 | strict DTO、可信平台桥接、锁后当前权限、Web共用T3 | 首d75独审5481706893有P1；绑定修复待复审 |
| AC01 | formal私聊+群@ task/approval/execution/item/Base关联，真人另列 | not_run |
| AC02/09 | 金标/事实约束/P2实际解释与usage引用/轨迹 | P2/P3事实保留，P4集成not_run |
| AC03/04/05/07/10 | 批准拒绝/全20SKU/完整unknown集合/10重复/冲突/期限/撤权/跨店租户/篡改/提交边界kill/CP | not_run |
| AC06/R13–16 | Basecreate/readback/T6update/ACK丢失/429/5xx/code/写冲突/旧版本/IMunknown超过1h | not_run |
| AC08 M1部分 | clean自有Compose离线与真Feishu；Woo留M2 | not_run |
| AC11 | 完成关闭/原因审计/同步/新周期，不复活旧执行 | P3事实保留，P4集成not_run |
| Web/性能 | 20SKU/角色登录撤权/390px/键盘焦点/真实服务权限/100受控入站p95/离线分析/恢复调度 | not_run |
| 回归 | 既有1057offline/337PG/24Web完整保留，新测试另计 | 新source全回归not_run |
| 交付 | M1复用P2actual1轨迹/降级（40例/三轮留M3）、配置挂载/资源清单/演示/真人与PW分记 | not_run |
| 独审/CI/main | 精确冻结SHA无P1/P2/CI/Root普通合main/合后同SHA CI/结案 | not_run |

## 证据记账规则

各结果写source、command、实际exit/count/time、source/model/approval_mode、固定窗口/owner/停止证据。offline Fake、真实PG、SDK源码/官方文档、真人/平台、CI与main分层，不将作者自检记独审或将部分运行记全通过。当前没有新增P4正式真人/平台/provider证据；首提交与后续source/CI以原PR和Root回执绑定，不自指未来提交。
