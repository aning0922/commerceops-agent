# Phase5 / M2 分层验收

## 文档冻结时点与正式状态

事实截止：2026-10-27（台北 D18）的最后文档合批。Root 与原 Reviewer 已核收本阶段必要业务及部署技术 Gate，
状态为 `business_and_deployment_gates_passed / awaiting_final_review_and_CI`。
**正式 M2 结案只以[固定权威回执](https://github.com/aning0922/commerceops-agent/issues/49#issuecomment-6430237354)
后续登记的实际 main SHA、同提交合后 CI 和结案记录为准。** 本文件是该时点的事实快照，
不预填未来 SHA、CI pass 或 complete；后续发布状态由同一回执承接。

已验运行源码为 `8ad436595794ef83f3a99bc80bd9ad4948b7117e`，
tree 为 `ea86b637190ec0ec42da771638a6c72b2853e82b`。
本地完整检查、实际 Woo/恢复与新 Compose 均绑定该源码；最后文档合批须另核非文档文件与其逐字节相同。
文档冻结时 main 仍为已验 M1 基线 `e7cf790`，PR50 仍为待最终集成候选；最终完整 Hosted CI、
正常合 main 及同 main 合后 CI 尚待 Root 实际执行，旧 CI 或本地通过不替代这些 Gate。

## 已核技术证据

| 范围 | 实际结果 | 证据层级与限制 |
| --- | --- | --- |
| 当前工程检查 | 完整 `scripts.check` native 0，226.945 秒；3368 collected、2778 offline passed、590 integration excluded、4 条既有 warning；398 文件 mypy、518 文件格式检查，Node/Python 审计 0，Python 审计95包；期间源码 hash 不变 | 本地工程证据；590 被排除不等于已在此命令执行 PG。最终 Hosted 五作业、全量 PG、G1/G2、Web/N01、配对及清理仍须完整通过 |
| Woo 正向来源与业务 | 新本地实际 Woo 合成店，完整只读采集与独立金标匹配；4 SKU/4 库存池/4 订单行/0 退款、总建议219、金额 CNY994；四项在途未知按本版本完整确认；唯一 execution、4 items | 实际 HTTP、PG、API 和自动化浏览器；不是商业实店数据、采购或库存写入，也不是新增真人飞书验收 |
| 新卷备份恢复 | 源 writers 全部停止，官方 checkpoint 语义核验；原生 dump、空目标 restore；60 表及 schema/ACL/数据摘要、官方 checkpoint 摘要与原 tuple 一致；原 nonce、版本/hash/期限保持 | 真实新自有 PG、同版本恢复；不 SQL 修补 checkpoint、不重seed、不延长审批 TTL |
| 恢复后显式批准 | 同原计划与审批明确批准一次，10 次原字节/原 key 重放；最终 PG 核唯一决定、consumed resume、execution 和4项/219件 | `resume_state` 合法前进与不可变回执分开核验；consumed 本身不代替 execution/items 读回 |
| 撤权与到期恢复负例 | 独立恢复 clone 实际403/ACCESS_DENIED；另一 clone 等原 DB 期限后实际410/APPROVAL_EXPIRED；两者均零决定/resume/execution/items，原 nonce/expiry 不变 | 各一次原请求，无自动重试；HTTP安全观测先保存，writers退出后再采实际PG；未调整时钟或TTL |
| 完整 Woo 父入口与清理 | 父 native 0、logical passed、cleanup confirmed；129项索引引用；五项目容器/网络0、六卷保留、七端口关闭、十个登记PID不存在 | 父起止回执差958.959秒，含真实expiry等待；旧失败run/once/卷保持各自失败事实，不恢复复用 |
| 当前 clean Mock Compose | 新项目实际build、0018/60表/低权；原Mock20各100共2000，完整20项与实际全部未知假设确认；唯一execution/decision/resume；原item一次关闭v2、原因/key、offline_fake v1/v2同锚 | 19项在途可靠为0、1项未知，不预造20个未知键；三个业务POST各1；本机新环境实跑，不宣称另一机器或全冷缓存 |
| Compose恢复、页面与清理 | 同父容器SIGUSR1产生两个唯一Worker owner，均有完整started/stopped/termination_confirmed；API/Web重启后原IDs与六次原key读回保持；隐藏Web真实只读交互通过，无额外业务写入；父/UI/86命令退出0，容器/网络0、两端口闭、精确卷保留 | 自动化、非真人；浏览器实际PID退出探针通过，但具体PID值未单独归档。108.492秒是启动/结果文件时间差，不冒作完整外层命令测量 |

实际执行只创建 PG 内部补货项；当前来源/配置由服务端绑定，当前身份/店铺/版本/hash/nonce/完整假设和
执行前重观测保护保持。Woo factory 的同步I/O截止、原 T4 20秒、单 Worker/单 Graph、低权、幂等和
UNKNOWN 原键核对未放宽。完整约束及逐次开发证据见[业务合同](contracts/p5-m2-v1.md)。

## AC01–11 的影响映射

下表是必要技术 Gate 的核收映射，不是提前宣布最终 M2 发布完成。M1 历史证据以
[原固定结案回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6360314990)
及[Phase4验收](PHASE4_ACCEPTANCE.md)为依据；仅在对应合同未改变的范围复用。

| AC | 本阶段依据 | 复用边界 |
| --- | --- | --- |
| AC01 私聊/群完整闭环 | 已验 M1 真人飞书及 Base 关联有限复用；新增 Woo 同源 T1/F02 有新 owned PG/Fake 入站回归 | M2 没有重新执行真人飞书或新 Base 写入，Fake 入站不标真人 |
| AC02 金标/事实稳定 | 新 positive Woo 的219/CNY994与完整来源；mixed质量负例；当前Mock20/2000 | 模型不得改数沿用既有合同；本阶段未追加真实模型调用 |
| AC03 拒绝/竞争唯一决定 | 原 M1 并发拒绝、唯一决定证据及受影响 PG 回归保留；本次撤权/到期恢复clone零业务副作用 | 撤权/到期零写不能代签全部并发case；旧专项与最终全量CI分列 |
| AC04 重复/提交边界恢复 | 当前恢复后10次同字节重放唯一决定/执行；既有提交边界与Worker恢复回归有限复用 | 本次dump/restore不冒称重跑全部kill故障矩阵 |
| AC05 权限/篡改/期限 | 新来源绑定、nonce/hash/版本与身份负例；实际恢复clone撤权403和真实到期410 | 其他既有租户/角色隔离按原专项和最终全量CI覆盖，不新增授权能力 |
| AC06 外部失败与UNKNOWN | Woo超时/缺页/变化阻断；HTTP失败安全观测与原键保护；原M1外写失败/恢复合同有限复用 | 当前Fake投影不是新远端Base/429/ACK-loss证明；旧UNKNOWN不被后续成功抹除 |
| AC07 待审批跨进程恢复 | 官方wait_approval/唯一原interrupt/原tuple语义；真实新卷还原与显式续跑；当前Compose单Worker恢复 | 不是多Worker、生产容灾或任意跨版本升级承诺 |
| AC08 干净复现/飞书/Woo | 新本地实际Woo只读对账与恢复、新当前Compose部署已核；真实飞书部分沿用M1 | 新机器全冷缓存未测；自动化Mock与真人、真实平台分层 |
| AC09 来源/轨迹/用量 | 当前Woo配置版本、快照/报告/规则/审批/执行关联；原模型证据有限复用 | 未发生的模型/SDK调用不补造Token、费用或耗时；未知仍UNKNOWN/null |
| AC10 完整未知确认 | Woo四在途确认及10次原字节重放；Mock完整20项中实际一个未知键确认；漏项/跨版本/物质变化重批有专项PG | 确认集合以当前完整计划为准，不把UI可读或complete直接视为可执行 |
| AC11 内部项关闭与新周期 | 当前Mock新周期/T6原因/v2/原key和重启保持；既有权限、幂等及同SKU新周期合同有限复用 | 当前Woo正向为新内部项；不称发生真实采购/库存变更或新增Woo真人关闭 |

## mixed、专项PG与历史失败

- 原一日 mixed 实际 Woo 对账为9商品/8订单行/3退款/9库存，包含原质量问题；首批整秒样本与
  后续微秒修正的等价请求/离线证据分列，不改写成最终源码的再次实店运行。
- 七日 W01 为9商品/9订单行/3退款/9库存；原 before_start 样本落入七日窗，故订单行多1。
  这是实际PG/ASGI加Fake HTTP，原坏SKU/未知库存/共享池问题保留，requires_review且零执行项。
  原 W01 测试文本与6eeb仅签名换行不同，AST等价已核；**AST等价不等于字节相同**。
- 新来源/截止/旧T4/T6/历史schema等26PG，以及完整history7+7/read-parent尾5共19PG均按各自索引
  核收；定向通过不替代完整590 PG。历史0016→0017和当前0018分段断言、旧payload/unknown/attempt保留。
- 40360468031原失败、40373408272命令外层300秒截止、40385815629旧三新增表断言失败，以及
  本地权限42501、format、类型、夹具与敏感扫描失败均保留。旧CI无具体断言原文的部分仍UNKNOWN。
- d97错误lab模块入口、e13停止分类、f7动态resume回执比较、c6撤权HTTP预期错误均保留整体failed。
  f7实际execution未采仍UNKNOWN；c6实际HTTP403，但旧response body未保存，error code仍NOT_CAPTURED。
  新e890通过不追认这些旧run，也不复用旧once、请求或卷。
- 882完整check在新测试的7处类型错误中退出1，源码未变；8ad仅修3处测试类型/局部变量，生产helper
  字节相同，随后完整2778offline/590excluded/native0。不能把先行局部type通过写成882全量通过。
- 七份旧日志缺失的非敏感原始字节不可恢复；脱敏替代或后续日志不冒充原件。旧HOLD/UNKNOWN、Issue23
  未定位风险及M1原失败/保护资源保持。Docker全协议egress未被完整捕获，不宣称全协议零出网实测。

## 安全证据索引

下列仅登记受保护安全索引的文件名与SHA256。原件由Root/原Reviewer核收，私有配置、原请求、
凭据、真实业务标识、连接地址和原始响应均不入Git；文件名不是仓库内可执行入口或公开下载承诺。

| 索引 | SHA256 | 归属 |
| --- | --- | --- |
| `M2-8AD-FULL-CHECK-INDEX.safe.json` | `ca2217e583a8ff6b29d53a345bd8c3d7fb176cf144bc4257733d972f987885a9` | 最终运行源码完整本地检查与882失败 |
| `M2-8AD-E890-FULL-RUN-INDEX.safe.json` | `c128a20e86d45f4eacf826bf95e8e42fb686d52c2e1fa8bab0ee66dfec1a9c8a` | 129引用；实际Woo/备份/续跑/两负例/清理 |
| `M2-CLEAN-1A7C-FULL-RUN-INDEX.safe.json` | `8605407495b98c06b742d323c0a719b68c59b07819d53c83f28e411340a7c24c` | 111引用；当前Mock20 Compose/恢复/Web/清理 |
| `P502-CI-FIX-087-REVIEW-INDEX.safe.json` | `cc9a0561a09699fc14fb3c593b37074b4b484ac583e7280a0dd9b35e9ceb9624` | 26项新owned PG及原失败分层 |
| `M2-PARENT-6EEB-REVIEW-INDEX.safe.json` | `90267bd17acf1d9c36f61599bbcdbb31d55cb9033d073e1da12d3c5084c8140f` | 历史19PG/CP语义/旧全检查 |
| `M2-MIXED-1945-6EEB-AST-PROOF.safe.json` | `f0923cec6e1e1578b4da0e513fac562e0577f0c2a4631aeab046b1e949c64230` | W01原件与AST映射，不是字节等价 |
| `M2-PARENT-882-NEGATIVE-REVIEW-INDEX.safe.json` | `f9e6933a89fa993d89f1a94c7878c9d9bc50d964d929867587cdc3080c2a4f46` | 真实handler离线负例、HTTP安全观测；不是新PG |

交付使用说明由原B维护：[M2交付](M2_DELIVERY.md)、[备份恢复](M2_BACKUP_RESTORE.md)、
[当前Compose](M1_OFFLINE_COMPOSE.md)。本轮实际仅本机新自有资源；全冷缓存、其他机器/系统、商业实店、
生产SLA/灾备和新增真人体验未测，不由当前通过推导。

## 预算与最后合批

原D1=2026-10-10、D30=2026-11-08、D18–20目标、总300h及18页设计冻结不重置。
M2阶段总cap1800 Agent有效分钟含首批和所有修复；当前角色规划A823/B307/Review370/Root300。
A在本次最终文档批开始前累计估595–778分钟，规划上限不是实际耗尽；Root历史精确净用量、人工H/L
和历史净余UNKNOWN，机器/CI/真实expiry等待另记，等待期间做的准备仍计Agent有效工作。

最后仅A/B事实文档普通合批、原Reviewer增量审查及Root统一发布/精确CI/正常合main/同main合后CI。
不减五作业、完整PG、G1三/G2六、Web/N01、配对和清理；不自动重试失败CI。
正式结果写入固定权威回执，不在文档中预填未来提交。停止于M2，不自动进入M3/Phase6、生产或扩权。
