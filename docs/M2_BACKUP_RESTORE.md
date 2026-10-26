# M2 业务备份与还原交付合同

本文件是 [M2 交付](M2_DELIVERY.md) 的最小恢复骨架。**当前 pending：本批没有执行业务备份、还原或还原后续跑。** 后续仅消费 A 冻结并独审的恢复核心与 Root 登记的新自有资源。本页不发布尚不存在的 CLI，也不允许照抄私有历史 launcher。

## 可复用与需要新增的能力

`compose.yml` 的固定 PG、owner/app 分权及 migrate/setup-checkpointer/grant-runtime/revision，`compose.m1-offline.yml` 的 loopback API/Web、单 Worker，以及 [M1 公开运行说明](M1_OFFLINE_COMPOSE.md) 可作为装配基础。它们当前的 Mock factory、权限和独占运行约束不能被页面直接扩成 Woo。原 M1 的保卷重启与 kill/restart 证据不是 dump 到新库/卷的还原证据；UX/Penpot 的数据库/assets 备份也不属于业务 PG。

A 负责冻结备份/还原方法、源与目标身份、schema/版本、角色授权、Worker/checkpoint 恢复和失败清理。B 只补 Web 读回、演示消费与交付记录，不手写恢复 SQL、修改 checkpoint、重置 job/approval/once 或开发通用调度平台。

## 最小成功场景（全部待执行）

1. 在已登记的新自有源环境，以真实 API/Worker 产生待审批任务，记录同一 task、plan/version/hash/nonce、报告快照、checkpoint/thread 绑定和当前权限。采用该场景实际来源，Woo/Mock 分别记账，不用 Mock 接线代签 Woo。
2. 停止 API/Worker 及其他 writers，取得精确子进程退出、OS absent、reap 与持久审计回执。源卷保留；不把关闭 Web 页面当作停写。
3. 按 A 的稳定入口捕获同一 PG 一致备份，覆盖业务数据、`checkpoints` 及恢复必需的依赖 schema/迁移版本。角色重建和授权策略必须明确。备份仅在新私有目录0700/文件0600，记录原生退出、长度和 SHA256，不输出正文或秘密。
4. 仅还原到另一个登记为空的新自有库/卷，拒绝覆盖已有或未知目标。核源码、镜像、实际 revision、schema 和绑定；不 seed 第二次，不手工 stamp、改 checkpoint 或延长原审批期限。新 DB 凭据独立生成，平台秘密只按明确引用注入，不写进备份清单。
5. 恢复后先只读回验原待审批对象及报告；新登录按当前服务端授权处理。不能自动批准或把恢复当授权。只有原权限、期限、数据新鲜度与物质变化复核均允许时，才对原版本给出一次明确意见；未知在途仍需该版本的完整显式确认。
6. 由单 Worker 继续原任务，核同一 execution/内部项与审计链；原 request key 重放返回同一结果且零新增。过期、变更或权限失效应按既有合同拒绝/重批，不能通过还原续命、换键或复活旧窗口。
7. 在原绝对截止内停服务并采集最终证据：源/目标身份不同、容器/网络/监听状态、精确进程终止及保留卷。失败、超时或清理未知逐项保留，不写成功或资源0。

业务 PG 备份与 Woo MariaDB 是不同资产。本最小场景不自动把 Woo 店铺数据库备份列为新 Gate；Woo 合成 manifest、平台 ID 映射和真实只读对账另留证据。原 P4、QuizForge、Penpot 和任何未知卷均保持。

## 证据清单与当前状态

| 证据 | 当前状态 | 通过条件 |
| --- | --- | --- |
| 已审恢复入口、精确源码与新资源登记 | pending A/Root | 同 owner、scope、版本与绝对截止 |
| 还原前待审批与 writers 停止 | pending | API/PG/checkpoint 绑定及真实进程终止 |
| dump 与新目标还原 | pending | 原生退出、摘要、独立目标、实际版本/角色核验 |
| 还原后只读 Web/API 回验 | pending | 原绑定与质量事实不变；不凭内存恢复 |
| 当前授权下显式续跑、原键重放 | pending | 同一执行、内部项唯一、重复零新增 |
| 失败拒绝及最终清理 | pending | 依实际影响核必要负例；未知不签成功 |

备份可读/能列目录不代表已经还原；进程重启不代表新卷还原；新卷启动不代表业务已安全续跑。本场景不承诺跨版本迁移、异机灾难恢复、RPO/RTO 或生产可用性。

## 稳定入口与当前可执行边界

当前提交没有公开 M2 dump/restore 场景 CLI。已存在的 `commerceops.entrypoints.database` 支持 `migrate/setup-checkpointer/grant-runtime/revision`，`commerceops.entrypoints.commerce_source` 支持显式 owned-test 来源登记；它们不是备份还原入口，不得用重新 seed 或登记新任务代替原任务恢复。A 冻结实际方法与命令后，再将精确 argv、角色/ACL、源/目标及退出码登记在本页或同源验收回执中。此处不拼接未审 `pg_dump/pg_restore` recipe，不发布旧私有父入口。

B 可复用原 live read 的安全登录、指定报告/计划读取、全 SKU/null 展示、权限/指定版本只读和原 request key 回执；复用 live write 的完整假设与显式原版本批准。现有 live runner 的 Mock seed、owner 标记及输出目录不能直接切换为 Woo/恢复目标。实际执行顺序见 [M2 Web 验证顺序](M2_DELIVERY.md#真实-web-最小验证顺序全部待执行)；A/Root 负责资源编排及 PG/Worker 采集，B 不开发第二个父进程或恢复框架。

## 还原读回的最小对照（全部待验）

| 位置 | 还原前记录 | 还原后必须核对 | 状态 |
| --- | --- | --- | --- |
| 来源与报告 | canonical org/shop、binding/版本/digest、原 report/snapshot/facts_hash、全部 SKU/质量与窗口 | 读取同一冻结来源与业务事实；页面当前配置不覆盖历史 provenance；秘密引用不进公开材料 | pending |
| 原待审批 | 同一 task、plan/version/hash、原 approval 状态/期限和确认键集合；checkpoint/thread 绑定 | 原对象仍存在且绑定一致；不造新任务，不延长 TTL、不改变确认集合 | pending |
| 当前身份 | 独立 operator/approver 账号及 scope/auth_version 的安全摘要 | 新会话按恢复后服务端当前身份鉴权；旧 cookie/nonce 不是恢复授权 | pending |
| 原键回执 | 原创建/已有决定的 request key 及 receipt 摘要 | GET 同一原键返回原对象；明确同键重放返回同一结果，PG 零新增 | pending |
| 明确续跑 | 恢复前该样本未执行；原业务计数/审计基线 | 允许时显式批准一次，复核后仅一 execution/每 SKU 一内部项；过期/撤权/物质变化按原规则拒绝或重批 | pending |
| writers 与目标 | 源/目标身份、schema、角色、dump 摘要、PID/容器/端口和原生退出 | 旧源停止、目标唯一活跃；最后所有 owned 资源停止并独立核验，源/目标卷保留 | pending |

nonce、会话、凭据、dump 与原始标识仅留受保护原件；公开结果记录是否同一绑定和摘要，不打印这些值。还原后批准前必须重新读取当前完整披露；不能重用备份前页面勾选或内存 PreparedWrite 作为新会话授权。若恢复前已有提交结果 UNKNOWN，则保留原键/字节并先读回，不能新建替代键或把暂无回执判断为失败。

## 交接前仍缺的输入

- A 已审恢复入口、实际工具/数据库版本、源/目标空白身份、角色/ACL 重建及原同版 schema/checkpointer 依据。
- Root 的新资源和 UTC 窗口、总截止与清理预留、写入/重放次数、API/Web origins/PID/build 以及秘密的私有路径交接。
- 同一 awaiting_approval 样本的实际 PG/checkpoint/报告与权限基线、独立备份摘要和 native exit；恢复后的角色/版本及 Worker 单实例事实。
- 最终真实 Web/PG 读回、明确续跑、必要拒绝反例、原键回放零新增和停止核验。

以上缺项不会由本次文档准备、B 前端独审或 M1 历史成功自动关闭。最终可执行命令与结果由 Root 按同一精确集成 SHA 核收后更新；M2 状态保持 pending。
