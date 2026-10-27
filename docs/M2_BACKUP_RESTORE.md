# M2 业务备份与还原交付合同

本文件是 [M2 交付](M2_DELIVERY.md) 的恢复方法与证据合同。`8ad436595794ef83f3a99bc80bd9ad4948b7117e` / tree `ea86b637190ec0ec42da771638a6c72b2853e82b` 的 e890 完整真实 owned Gate 已获 Root 与原 Reviewer 核收：真实本地合成 Woo→原待审批→新库恢复→同原审批续跑、十次原字节重放，以及独立撤权和真实到期负例均通过。当前0018 Mock Compose已另行核收，见 [Compose实证与边界](M1_OFFLINE_COMPOSE.md#当前-0018-mock-装配与公开复现2026-10-27)；最终文档、精确 CI/main/合后 CI 与正式结案以 [固定权威回执](https://github.com/aning0922/commerceops-agent/issues/49#issuecomment-6430237354)的后续实际更新为准，不由本页预签。

安全总索引 `M2-8AD-E890-FULL-RUN-INDEX.safe.json` / SHA256 `c128a20e86d45f4eacf826bf95e8e42fb686d52c2e1fa8bab0ee66dfec1a9c8a`（129 refs）；Root 独立 proof SHA256 `5ec89f65b372495f1051142cc81bb4815a8eefab6e5a02c6b4e189dfdaf59470`。B 校验并消费该安全索引，不展开私有原件。更早 c6 的正向已核但撤权误期待404/实际403、body code NOT_CAPTURED、expired 未跑与整体 failed 继续保留，不由 e890 回填。

## 已有装配与恢复实现

`compose.yml` 的固定 PG、owner/app 分权及 migrate/setup-checkpointer/grant-runtime/revision，`compose.m1-offline.yml` 的 loopback API/Web、单 Worker，以及 [M1 公开运行说明](M1_OFFLINE_COMPOSE.md) 可作为装配基础。它们当前的 Mock factory、权限和独占运行约束不能被页面直接扩成 Woo。原 M1 的保卷重启与 kill/restart 证据不是 dump 到新库/卷的还原证据；UX/Penpot 的数据库/assets 备份也不属于业务 PG。

A 负责冻结备份/还原方法、源与目标身份、schema/版本、角色授权、Worker/checkpoint 恢复和失败清理。B 只补 Web 读回、演示消费与交付记录，不手写恢复 SQL、修改 checkpoint、重置 job/approval/once 或开发通用调度平台。

## 恢复顺序与成功条件

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
| 已审恢复入口、精确源码与新资源登记 | 8ad/e890 精确 source/tree 及新资源登记已核 | 同 owner、scope、版本与绝对截止 |
| 还原前待审批与 writers 停止 | e890 已核 | API/PG/checkpoint 绑定及真实进程终止 |
| dump 与新目标还原 | e890 已核 | 原生退出、摘要、独立目标、实际版本/角色核验 |
| 还原后只读 Web/API 回验 | e890 已核 | 原绑定与质量事实不变；不凭内存恢复 |
| 当前授权下显式续跑、原键重放 | e890 一次批准/十次同字节重放、1 execution/4 items/219、1 decision receipt/1 consumed resume 已核 | 同一执行、内部项唯一、重复零新增 |
| 失败拒绝及最终清理 | e890 撤权403/ACCESS_DENIED、原期限后410/APPROVAL_EXPIRED，零业务副作用；完整清理已核 | 依实际影响核必要负例；未知不签成功 |

备份可读/能列目录不代表已经还原；进程重启不代表新卷还原；新卷启动不代表业务已安全续跑。本场景不承诺跨版本迁移、异机灾难恢复、RPO/RTO 或生产可用性。

## 稳定入口与当前可执行边界

公开 CLI 为 `scripts.m2_owned` 的 `prepare` / `run`，控制流已入 Git。`m2_backup` 和 `m2_state` 是该父入口有界子进程调用的 helper，不是独立场景 CLI；内部 `_child` 需要原父 PID、请求摘要、源码与截止绑定，不供操作者单独运行。以下只说明冻结源码的参数形状，本次 B 未执行；变量取 Root 本次批准的绝对 UTC、业务锚日与 prepare 返回目录：

```sh
.venv/bin/python -m scripts.m2_owned prepare \
  --deadline "$M2_STOP_AT_UTC" --anchor-day "$M2_ANCHOR_DAY"
# 将本次 prepare 返回的绝对目录绑定为 M2_RUN_DIRECTORY；仅 A 在同一原窗口 run 一次。
.venv/bin/python -m scripts.m2_owned run --directory "$M2_RUN_DIRECTORY"
```

执行前须使用已冻结的干净 Git source/tree 和仓库固定工具链。prepare 接受剩余 420–3600 秒的明确截止，生成新的 `runtime/m2-<run_id>` 私有目录，并登记 source/restored/revoked/expired 四个互异 PG project/database/volume 与六个独立 loopback 端口；端口选择后仍须核实际归属。run 只能开始一次，不支持失败续窗、resume 或重置原期限；总清理预留 180 秒。参数说明不构成本次资源运行授权，实际生命周期只由 A 父入口负责。

| 冻结实现 | 已有的控制与比较 | e890 实际结果 |
| --- | --- | --- |
| `m2_owned` | 固定两个 B selector、构建、源初始化与真实 Woo probe/绑定、source consumer、停 writers、dump、新目标 restore、restored consumer、独立撤权/过期 clone 与收尾；逐 child 原生退出和进程组回收 | 已核收 |
| `m2_backup` | PG 17.11 / revision `0018_p5_commerce_sources` 的精确 60 表、schema/ACL/owner、低权 role flags、checkpoint 版本及行内容摘要；无其他连接的只读一致快照比较 | 已核收 |
| `m2_state` | 新源两个独立角色/店铺初始化与来源登记；实际 PG 原 pending/报告/金标回执；官方 saver 只读 `aget_state` 核同一 wait_approval/唯一 interrupt/原绑定；完成后唯一执行/items/resume 回执 | 已核收 |

源 writers 全退出后先取完整快照，再由原生 `pg_dump --format=custom --no-owner` 保存私有 dump，并复核源快照不变；源 PG 停止保卷后，目标须先核空白及独立低权角色，再 `pg_restore --exit-on-error --single-transaction --no-owner`。恢复快照还要逐项等于源，包括 schema/ACL、官方 checkpoint 语义与原期限。这里描述已提交实现，不手工拼接绕过父入口的 dump/restore 命令，不用 seed 新任务替代原任务恢复。

原 pending dump 另恢复到 revoked/expired 两个空白新卷；撤权只改独立负例库，过期等真实 DB 时钟，不延 TTL。两例只启 API、无 Worker，各用原 decision 字节一次请求，按现有权限/过期合同预期分别 403/ACCESS_DENIED 与 410/APPROVAL_EXPIRED，并在停写后核零执行/items/resume/decision receipt。e890 实际返回上述两个目标状态码/枚举，停写后核零决定/resume/execution/items、原 nonce/expiry 不变；结果来自新总索引，不从静态分支推断。

B 可复用原 live read 的安全登录、指定报告/计划读取、全 SKU/null 展示、权限/指定版本只读和原 request key 回执；复用 live write 的完整假设与显式原版本批准。现有 live runner 的 Mock seed、owner 标记及输出目录不能直接切换为 Woo/恢复目标。实际执行顺序见 [M2 Web 验证顺序](M2_DELIVERY.md#真实-web-最小验证顺序与结果范围)；A/Root 负责资源编排及 PG/Worker 采集，B 不开发第二个父进程或恢复框架。

## 还原读回的最小对照（e890 已核收）

| 位置 | 还原前记录 | 还原后必须核对 | 状态 |
| --- | --- | --- | --- |
| 来源与报告 | canonical org/shop、binding/版本/digest、原 report/snapshot/facts_hash、全部 SKU/质量与窗口 | 读取同一冻结来源与业务事实；页面当前配置不覆盖历史 provenance；秘密引用不进公开材料 | e890 已核收 |
| 原待审批 | 同一 task、plan/version/hash、原 approval 状态/期限和确认键集合；checkpoint/thread 绑定 | 原对象仍存在且绑定一致；不造新任务，不延长 TTL、不改变确认集合 | e890 已核收 |
| 当前身份 | 独立 operator/approver 账号及 scope/auth_version 的安全摘要 | 新会话按恢复后服务端当前身份鉴权；旧 cookie/nonce 不是恢复授权 | e890 已核收 |
| 原键 POST 回执 | 原创建/已有决定的 request key 及 POST receipt 摘要 | 原 POST 回执、十次同键同字节 POST 重放返回同一决定，PG 核唯一执行与内部项 | e890 已核收；不含原键 GET |
| 明确续跑 | 恢复前该样本未执行；原业务计数/审计基线 | 正向显式批准一次，复核后仅一 execution/每 SKU 一内部项；独立撤权与真实到期 clone 按原规则拒绝 | e890 已核收，仅正向/撤权/真实到期 |
| writers 与目标 | 源/目标身份、schema、角色、dump 摘要、PID/容器/端口和原生退出 | 旧源停止、目标唯一活跃；最后所有 owned 资源停止并独立核验，源/目标卷保留 | e890 已核收 |

e890 的 source/restored API 日志中，`GET /api/v1/requests` 均为0；本次核收的是原 POST 回执、十次同键同字节 POST 重放与 PG 唯一性，不能写成 GET 已验。原键 GET 的六次实际读回另归 [当前 Mock Compose](M1_OFFLINE_COMPOSE.md)；UNKNOWN 先 GET 原键一次并停止是已有合同，不因 e890 成功而变成本次已触发的行为。物质变化拒绝/重新确认后重批归专项 PG 复用证据，不计入 e890 的正向/撤权/真实到期范围。

nonce、会话、凭据、dump 与原始标识仅留受保护原件；公开结果记录是否同一绑定和摘要，不打印这些值。还原后批准前必须重新读取当前完整披露；不能重用备份前页面勾选或内存 PreparedWrite 作为新会话授权。若恢复前已有提交结果 UNKNOWN，则保留原键/字节并先读回，不能新建替代键或把暂无回执判断为失败。

## 复现输入与独立待验项

- 已审入口的实际运行 source/tree、工具/数据库版本、四个源/目标身份、目标空白、角色/ACL 与同版 schema/checkpointer 的原生证据。
- Root 的新资源和 UTC 窗口、总截止与清理预留、写入/重放次数、API/Web origins/PID/build 以及秘密的私有路径交接。
- 同一 awaiting_approval 样本的实际 PG/checkpoint/报告与权限基线、独立备份摘要和 native exit；恢复后的角色/版本及 Worker 单实例事实。
- 最终真实 Web/PG 读回、明确续跑、必要拒绝反例、原键回放零新增和停止核验。

上述输入已在 e890 安全索引中闭合；未来新 run 仍须独立登记并生成自己的凭据/请求和证据，不能消费旧窗口。当前 `prepare/run` 参数与恢复方法已公开，e890 实际结果由 Root 按完整索引核收；历史失败、W01 AST 一致但非同字节、旧日志丢失及 Hosted CI 尚未通过的边界见 [交付地图](M2_DELIVERY.md#历史失败与源码对应边界)。当前Mock Compose已单独核收；最终文档/精确CI/main/合后及正式结案以固定权威回执后续实际更新为准，不预写未来通过。

本次父窗口 UTC 2026-10-26 23:12:14.944768 → 23:28:13.904003，native0 / 958.959235 秒，75 条命令 native0/reaped/无 timeout。清理 confirmed，四个 PG 与 Woo project 容器/网络均0、7端口关闭、10登记PID absent、四PG卷和两Woo卷共6卷保留；只签本次 owned 范围。
