# Phase 4 / M1 交付与验收准备

状态：**准备中，所有 Phase 4 实现和真人平台验收均为 `not_run`**。本文只整理交付路线、证据形状和演示顺序；它不创建业务能力，不证明 Compose、飞书、Base 或 Web 已通过。

## 1. 基线、范围和使用方式

- 本文基线为 `9d97c19009d932036809ac3e2638bb68f4b7f765`。该 main 的四项 CI 为 [38093693335](https://github.com/aning0922/commerceops-agent/actions/runs/38093693335)（quality、frontend、phase3、pg-pair 均 SUCCESS），并继承 [Phase 3 验收](PHASE3_ACCEPTANCE.md) 和 [Issue #33 最终回执](https://github.com/aning0922/commerceops-agent/issues/33#issuecomment-6103315682)。
- M1 退出合同是 PRD AC01–07、AC09–11，外加 AC08 的干净 Compose 离线复现和真实飞书部分；Woo 真实店证据属于 M2，不能在 M1 演示中暗示已接入。
- 日历和容量保持 `D1=2026-10-10`、`D30=2026-11-08`、总计 300 小时；Phase 4 是 D13–D17（10 月 22–26 日）的 50 小时容量。本准备批占交付流 8 小时容量；人工有效工时仍为 `not_reported`。
- P1 的 G3 只证明受限技术探针。P3 的 PG/Web Gate 证明正式服务端规则。两者都不替代本阶段的真人飞书正式业务、Base 投影或完整 M1 演示。

Phase 4 实施完成后，由阶段 owner 把实际源码 SHA、命令、开始/结束时间、`source_mode`、`model_mode`、`approval_mode`、环境版本和脱敏证据路径填入本文引用的运行报告。不得把模板的空格或待办改写成“通过”。

## 2. 交付依赖和冻结点

| 项目 | 唯一 owner / 输入 | 交付流的使用限制 |
| --- | --- | --- |
| 正式飞书入口、回调到 T3、正式卡片和异步通知 | P4-A | 必须调用 P3 当前服务端授权、版本、nonce、hash、假设确认和恢复规则；卡片的已送达/已点击不是业务状态真值。 |
| Base 投影、对账、版本顺序和 outbox sender | P4-B | PostgreSQL 是真值；外部 unknown 先按原键对账，不能换键重发，不能让 Base 反向改变批准或内部项。 |
| migration、共享 outbox 合同、Worker/Graph、根锁和 CI | P4-A 指定的单一 owner | 本文不定义或猜测接口、表、环境变量或执行命令；稳定合同冻结后才接线。 |
| Next.js 状态接线与端到端页面 | P4 Web owner | 只能在后端稳定 DTO/错误语义发布后把 mock 标记替换为真实读取/动作。 |
| 证据、演示、录屏和阶段收口 | 总控 + 本交付流 | 只消费已冻结的结果；不读密钥、不操作旧 PG/Compose/飞书资源。 |

当前需要冻结、但尚未在本基线中声明为 Phase 4 稳定运行合同的接口至少包括：飞书入站请求到正式任务创建的最小 payload、卡片回调与 `DecisionReceipt` 的对应、正式通知投递/回执语义、Base projection 的原键和版本比较规则、sync 状态读模型，以及 Web 对这些对象的 DTO 与错误码。它们均标为 **待 P4-A/P4-B 合同冻结**，不能由演示文档代为实现或用 mock 冒充集成。

## 3. 最短干净 Compose 离线闭环（待实际验证）

这是一条受限离线演示路线：仅使用仓库内 MockCommerce fixture、本次自有随机 Compose project/卷和本地受控身份；不读取或加载飞书、Base、模型或 Woo 配置。实际可运行前，实施 owner 必须确认 P4 后的启动、迁移、Worker、API、Web 和 fixture 入口；下面现存命令仅是已核静态入口，未在本文工作树执行。

1. 在新、空的项目 checkout 中校验锁和工具：`uv sync --frozen`、`uv run --frozen python -m scripts.bootstrap_tools`。现有技术检查入口是 `uv run --frozen python -m scripts.check`，前端静态入口是 `PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend ci --ignore-scripts` 与 `npm --prefix frontend run typecheck`。
2. 创建仅本次使用的 PG secret 目录：`uv run --frozen python -m scripts.prepare_pg`；目录保持未跟踪、0700，文件 0600。不得输出文件内容、DSN、容器 inspect 的环境全文或任何密钥。
3. 用唯一 Compose project 名启动 PostgreSQL，且不发布宿主机端口：`docker compose -p <owned-project> up -d --wait postgres`；运行 `db-init`、官方 checkpointer setup、runtime grant、revision。现有 compose 文件只静态确认了 `postgres`、`db-init` 与 `pg-test` profile；Phase 4 的长期 Worker/API/Web 编排还没有在本基线被证明可运行。
4. 使用冻结 Mock fixture 创建分析和正式 workflow，等待 Worker 产生不可变报告、plan、approval 和 card/Base outbox 意图。展示任务、报告、plan、审批、execution、internal item 与 sync 状态的关联；没有正式 sender 回执时只显示 pending/unknown，不能写成 synced。
5. 通过同一个正式服务端路径完成：无未知在途的批准或未知在途完整键集合的联合确认；等待内部 execution 与 item 创建；完成或关闭一个 item 并记录原因。此段只能在 P4 接线和真实 PG 验证后演示。
6. 重启自有 Compose 应用进程并只读取持久状态；同一 request key/回执回放不再创建任务、决定、execution、item 或 projection。最后仅对明确定义为本次 owned 的 project 执行 `docker compose -p <owned-project> down`；是否删除卷由实际测试合同决定，禁止广泛 prune 或操作旧项目。

离线闭环最低实测记录：输入 fixture 与版本、身份/店铺范围、DB revision、source/model/approval mode、每个持久 ID 的脱敏关联、命令 exit、PG/Worker stop 证明、屏幕或 API 脱敏摘要。任何无法启动、不可复现或运行到 mock-only 的步骤都要原样标 `not_run`/`blocked`，而不是缩短流程。

## 4. 四个崩溃窗口演示（待实际验证）

| 编号 | 受控位置 | 演示动作 | 必须留下的结果 |
| --- | --- | --- | --- |
| R01 | inbox 事务提交后、平台 ACK 前 | 在自有受控入站处理进程 kill，再启动同一版本服务并投递相同事件 | 一个正式 task、一个首 job；重投只得到原持久回执。 |
| R05 | plan/card outbox 提交后、checkpoint 中断前 | 在提交钩子 kill，完成旧进程终止确认后恢复 | 不新建 plan/card intent；真实卡片仅在 ready 后发送。 |
| R11 | execution/item 事务提交后、checkpoint 前 | 在 T4 commit 后 kill，恢复同一 workflow | 原 execution 和每 SKU 单一 item 被回读；没有第二次内部补货创建。 |
| R13 | Base 创建成功但响应未知 | 以原 projection key 模拟/记录外部 unknown，然后只做受控原键查询对账 | 状态为 unknown 后进入对账；确认已有行时绑定原记录，未确认时停下，不换键重建。 |

所有 kill/restart 只能作用本次自有进程、容器和随机数据库。每个窗口要记录 injection 点、PID/容器终止确认、重启后数据库断言和清理/保卷事实。P1/P3 的历史故障证据可作为解释背景，不能替代 P4 正式业务路径的重新验证。

## 5. 真人飞书与 Base 录屏分镜（待 P4 代码审核后执行）

执行前的最小核验：测试应用已发布且仍具既有 scope；目标是已授权测试企业、测试群、A/B/C 三个既有测试身份和指定测试 Base；Gateway 使用受保护的本地配置，不把 secret、token、ID、连接 URL 或原始回调内容录入 Git、聊天、日志、截图或 Actions artifact。无法把目标限定为这些资源时，停止外部步骤并继续离线工作。

| 段落 | 真人动作 | 屏幕/服务端应验证的事实 | 不能据此声称 |
| --- | --- | --- | --- |
| F1 私聊闭环 | A 在机器人私聊发起正式分析，合资格审批人按通知操作 | 新正式 task、可信 report/plan/approval、callback actor 与 PG 决定/执行/item/Base projection 可关联 | 接收 ACK 已完成补货；真实采购或库存更新。 |
| F2 群 @ 闭环 | A 在唯一测试群 @ 机器人发起另一正式分析 | 同一正式入站合同、群/组织/店铺范围、20 SKU 全量披露（不可截断）与关联记录 | 普通非 @ 消息或 bot 自身消息已被业务过滤验证，除非本轮另有受控证据。 |
| F3 联合确认与拒绝 | 对未知在途计划由 A 或 B 一次点击完整确认键集合；另一个新计划由合资格用户拒绝 | `approve_with_assumptions` 精确键集合与当前 hash/version；raw null 保留、effective=0；拒绝为零 item | 普通 approve 可以代替确认；已拒绝计划可执行。 |
| F4 冲突、重复、过期、撤权与跨店 | 两个 approver 并发相反决定；同一点击重放十次；受控过期/撤权/跨店/篡改卡片值 | 只有一个决定；十次不重复审计/resume/execution；其余均被当前服务端角色、scope、nonce、hash、expiry 拒绝 | 卡片 value 或客户端时间被信任。 |
| F5 Base 投影与恢复 | 观察已创建内部 item 的 Base create/read/update；注入 timeout/429/5xx/unknown 之一并对账 | PG state 与 sync state 分开；原键、记录锚点和投影版本读回；旧投影不覆盖新版本 | Base 可反向批准/完成；unknown 等于失败或可安全换键重试。 |
| F6 T6 与通知 | 同店 approver 对一个 open item complete 或 close，提供原因；观察异步结果通知 | item version/audit/PG 状态/投影依次一致；通知明确为异步结果 | 已采购、已入库、真实库存已变化。 |

录制时每段开头显示脱敏后的场景编号、客户端（桌面/移动）与版本、操作者角色和时间；每段结尾显示脱敏关联摘要而非内部 ID 或秘密。F1–F6 由真人点击才标 `approval_mode=human_feishu`；自动化浏览器只能标 `simulated_web`。如果卡片客户端提示文字未被观察到，记录“未观察到”，不要用服务端结果反推 Toast。

## 6. 脱敏证据索引模板

每次真实或故障验证生成一条记录；索引可提交，但原始秘密、原始 token、完整 URL、聊天文本、open_id/chat_id/app_token、数据库密码和连接串不进入索引。

| evidence_id | Gate / AC | source_mode | model_mode | approval_mode | frozen SHA | command / scenario | started / stopped | safe ID links | outcome | artifact digest / owner | limitations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `<P4-...>` | `<ACxx/Rxx>` | `mock|postgres|human_feishu|controlled_fault` | `not_used|existing_p2_evidence` | `human_feishu|simulated_web|not_applicable` | `<sha>` | `<redacted>` | `<UTC>` | `<opaque task/plan/item/projection relation>` | `passed|failed|unknown|not_run` | `<sha256/path access restricted>` | `<what it does not prove>` |

运行报告另列五维时间账本：

| 日期 / 工作包 | 人工有效工时 | Agent 墙钟 | 机器执行 | 机器等待 / CI | 外部测试窗口 | 说明 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `<YYYY-MM-DD / P4-A|P4-B|delivery>` | `not_reported or actual` | `<actual>` | `<actual>` | `<actual>` | `<actual>` | 不把等待、真人协调或未发生工作计为人工开发。 |

## 7. Web 接线清单（不等于已接线）

冻结的 18 页和 P3 当前 Next.js 已提供布局、权限状态、20-SKU 展示、窄屏及键盘验收基线。Phase 4 Web owner 在 API/DTO 冻结后逐项确认：

1. task/report/plan/approval/item/event/sync 读取全部来自当前服务端且遵循 P3 同一身份、店铺和可见性谓词；列表 count 不能泄漏隐藏对象。
2. 页面同时显示业务状态与 Base/通知同步状态；`pending`、`failed`、`unknown` 不冒充已同步，callback receipt 不冒充 execution 成功。
3. 审批详情实际渲染 `item_count` 全量（上限 20），展示 hash/version/期限/质量/未知在途 raw null 与 effective=0；响应不完整时禁用决定。
4. 普通 approve 与联合确认是不同操作；后者仅提交服务端给出的完整键集合。保留原 request key/body 用于 unknown 回读，不产生新键或反向动作。
5. 决定和 T6 resolve 的 duplicate/conflict/expired/revoked/cross-scope/unknown 错误按冻结安全文案呈现；不回显隐藏对象或原始响应。
6. 对 1440、1280、390 宽度、键盘焦点、登录/撤权、20 SKU 长列表和异步状态重新做真实 Web 验收。Playwright 证明页面/API 行为，不能替代 `human_feishu`。

## 8. 逐 AC 待验表

| AC | M1 必要证据 | 已有可复用前提 | Phase 4 缺口 / 最短下一步 |
| --- | --- | --- | --- |
| AC01 | 私聊与群 @ 各一正式闭环，PG task/approval/execution/item/Base 行关联 | P1 G3 技术探针、P3 服务端规则 | P4-A/B 审核后在限定测试资源执行 F1/F2/F5。 |
| AC02 | 固定 fixture 金标，模型不改数 | Phase 2 金标与 P3 report 绑定 | P4 流程引用同一可信 report，做关联回读，不重新改计算。 |
| AC03 | 拒绝零 item；并发相反决定唯一生效 | P3 PG Gate | 真人卡片拒绝/冲突与正式 callback→T3 对应记录。 |
| AC04 | 重复十次、提交边界 kill/restart 后单一 item | P3 受控恢复 Gate | 正式飞书入口重放 R01、正式 execution R11、投影不重复的 P4 证据。 |
| AC05 | 未授权/跨店/hash 篡改/过期/撤权不执行 | P3 角色/hash/nonce/expiry Gate | 通过正式 callback/Web 入口做受控负向证据，不能仅借离线 unit。 |
| AC06 | timeout、429/5xx、sync failed/unknown 状态和安全恢复 | P1 Base probe、P3 outbox 逻辑意图 | P4-B 对 Base 真实限定写入及对账；R13/R14–R16 适用部分。 |
| AC07 | 待审批跨进程恢复，过早决定不丢 | P3 checkpoint/worker Gate | P4 card callback 与恢复路径的正式关联演示。 |
| AC08（M1） | 干净 Compose 离线复现与真实飞书证据 | 现有 Compose/PG 技术基线 | 按第 3 节实际跑通；F1/F2 留真人证据。Woo 留 M2。 |
| AC09 | 来源、规则、模型、token/耗时、工具、审批轨迹可查 | P2/P3 事实、模型受限历史一次调用 | P4 将正式入站、卡片、outbox/Base 轨迹接到只读展示；无新 paid 调用。 |
| AC10 | 当前版本完整未知键联合确认；漏/多/篡改/跨版本拒绝 | P3 A01–A08 PG Gate | F3 真人卡片 + F4 负向正式入口证据。 |
| AC11 | 有权单项 complete/close、原因/审计、重试幂等、新周期 | P3 C01–C05 PG Gate | F6 正式通知/Base 投影和 UI 关联；不重放旧 execution。 |

## 9. 最小外部条件与完成判定

P4-A/P4-B 通过独立审核、精确 SHA CI、真实 PG/Compose 后，才安排有限真人窗口。窗口前只需核验：测试应用/群/成员/Base 仍可用且属既有授权范围、长连接配置已发布、Gateway 和 Base target 指向受保护的本地配置、每个写入对象可被唯一限定为测试对象。若任一项不可核验，暂停那条外部线并记录最小解锁条件，不扩大 scope、成员或测试资源。

本文自身的合入前检查应为：路线、模板、待验表通过普通文档检查和项目敏感扫描，且只变更本文件。本批已完成文档检查和项目敏感扫描；它不构成 Phase 4、M1、任何 AC 或真实平台 Gate 的验收。
