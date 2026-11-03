# V4-0 身份设计两行增量独立审查

2026-11-03，Asia/Taipei。结论：**ACCEPT_IMPLEMENTATION_DESIGN_DELTA**，本增量 0 P1 / 0 P2；原唯一 P2 `IDPLAN-01` 在设计层面关闭。可由 ROOT 据此安排身份代码实现，不代签实际业务、SQL/ACL 执行、PG、本地验收或资源窗口。

## 精确对象与范围

- 候选：`c4c48401494b00308cc5a2022e4a8fcb0e3f8195`。
- tree：`cd974e5cdd6085816cf2514c9f4d7b612809e542`。
- parent：`a4d8336caa160abba6efdf0cfaae1a87e71e95e5`。
- 原完整独审：`ad402ecebe446bd823793b156f44e1031cea86a0:docs/v4/review/IDENTITY_PLAN_a4d.md`，原结论 0 P1 / 1 P2，保留不改。

独立读取精确 Git 对象，确认 parent 到 candidate 仅两个文件、各一行替换：`docs/v4/design/IDENTITY_SQL_PLAN.md:355` 与 `docs/v4/design/SEED_SPEC.md:119`。无其他代码、SQL、DDL 或文档变化。候选两文件 SHA256 分别为 `30c52f609c7c23fc6833427f0fdd13cbe4a04caa87f76102dd0415a1c849f5d4`、`5ada986b8d2eb2384fb7195b9bc117469ebad32e520e379677e6e591f43ab5ca`。

本次只核唯一 P2 的关闭条件及其直接合同边界，没有重新审查十表 DDL，没有读取作者 WIP，没有运行测试、PG、服务或敏感扫描，没有修改产品或扩大扫描批准。actual token/cost UNKNOWN。

## IDPLAN-01 关闭依据

| 关闭条件 | 精确证据与判断 |
|---|---|
| 创建入口仅 bootstrap | I:355 明确 POST 仅接受有效原 bootstrap、其 CSRF 与精确原 key，active cookie 在该入口拒绝；S:119 同步。原 active-cookie POST 可成功返回的兼容分支已删除。与未变的 I:329–335 bootstrap 入口顺序一致。 |
| active 丢 body 恢复 | I:355 / S:119 仅允许 GET current 核 creation_request_key，再 GET 原 operations 回执；未把当前有效会话扩成第二种创建 POST 认证路径。I:409 当前认证与 owner 限制未变。 |
| consumed bootstrap 重复/并发 | I:355 返回 409 OWNER_RECOVERY_REQUIRED，不发新 cookie 或旧敏感 CreateEnvelope；原事务未提交时依原锁序等待或安全 UNKNOWN，不产生第二效果。重复请求的幂等性不要求 active POST 成功。 |
| 原 key 与只读最小恢复 | I:355、未变 I:410 与 S:119 保留原 bootstrap + 精确原 key 的最小状态 GET；只有已提交时返回最小 COMMITTED，未提交/不确定仍 UNKNOWN。不能从数据库摘要还原 bearer，也不能由缺回执推断回滚。 |
| 两类丢 ACK 与时限 | S:119 分别覆盖 cookie 已应用/仅 body 丢失，以及 header/cookie 整体丢失；后者在原 300 秒内仅最小回读、不新发身份，过期 UNKNOWN、不自动重 POST。I:355 明确保留该边界，I:410–411 未放宽。 |
| 一次效果与原保护 | I:355 明确同 bootstrap 并发最多一个 tenant；原 cap 锁、事务、唯一键、原子 receipt 与 bootstrap consume（I:329–349）完全未改。此为设计保证，真实并发效果仍待代码及 PG 证明。 |

## 四合同未倒退

候选内以下四文件与 parent 字节完全相同，并核对了此次相关约束：

- `PERMISSION_DEMO_CONTRACT.md:15,23,35`：Origin/CSRF、仅原 bootstrap owner 单 key 的 300 秒最小恢复、无新身份或普通业务恢复特权。
- `UI_ROUTES_CONTRACT.md:17,19,31`：仅显式首次创建，UNKNOWN 保原 key 只读恢复，两类丢 ACK 不自动重新创建。
- `API_EVENTS_CONTRACT.md:14,20,22,38–46`：创建 bootstrap 用途、consumed bootstrap 不再写入/换 key、原 key 最小 GET、active 仅 current 与原回执恢复；同 key 原结果不授权自动重发。冻结 OpenAPI 的 sessions POST 用途仍为 bootstrap only，200 声明不构成 active-cookie POST 授权。
- `DOMAIN_SOURCE_CONTRACT.md:29`：COMMIT 前回滚与 COMMIT 后按原 key 只读核对、原 tenant 隔离及旧业务保护不变。

本增量将设计统一到原独审要求的最小删除方案，没有引入新认证阶段、token 恢复能力、自动重试或合同改写。原完整独审对 SQL/锁序/ACL/seed 的其余判断及其未执行限制继续适用；未来实现仍须验证 active POST 拒绝、active GET 回执、consumed bootstrap 最小恢复、到期拒绝和并发一次效果。本报告仅关闭设计 P2。
