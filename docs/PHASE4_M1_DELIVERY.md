# Phase 4 / M1 剩余验收地图

## 唯一当前验收清单（2026-10-20，台北时间）

本节按[用户已批准的 M1 收口方案](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6286638856)及[9h 整包授权](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6286688465)接续原 A/C/Reviewer；以下原五项为唯一现行状态；[原AC01–11](PRD.md#7-p0-交付验收)与M1范围不变，④继续闭合，不新增设计、展示或通用框架 Gate。原两条私聊保留 HOLD 并停止专项恢复；查询/解释转为原定新群任务的独立样本，不要求用户重发，不称原私聊已经恢复。下方旧“不得替换/必须恢复原两条”的安排仅属旧合同历史，不能据此继续专项恢复或阻塞新样本验收。

已核公开候选为 `877da961afb26a73460ce5af2661582fd2a304ea` / tree `f2f09ebb1aa6d7988fed2a78a497d64de1a7a928`；[CI39386976160](https://github.com/aning0922/commerceops-agent/actions/runs/39386976160)五 job SUCCESS、563 PG、4个安全 artifact 的核收见上述 Root 最终方案回执。它只证明该精确源码和已跑范围，不代签本包未来群/查询/真实负向或后续候选。main 仍为 P3 基线 `9d97c19009d932036809ac3e2638bb68f4b7f765`，M1 未完成；31a6 采集器的0015/0016/0017兼容已正常集成，当前四个 C acceptance 文件与877逐字相同，未发现必须修改consumer的来源差异。

真实原私聊/批准、F02三轮原T1、真人原T6、同record Base v2及原 `persisted_real_v2_readonly` page/replay 已核收并复用。原只读Web为automatic、各原key GET1/业务POST0/该轮SDK与平台写0，不冒称真人连续录屏或本轮新平台验证。旧history第二条差异、strict pair=false、旧child UNKNOWN及原HOLD按各自回执保留；停止专项恢复不是把失败改为成功，也不把新群样本的结果回填给旧私聊。

群工具既有089/037准备、6337 owned正常/权限两例独审和925 owned全20项/Q2000/完整读回/冷重放/cleanup按已核范围复用；外层testdriver exit1及全部旧失败不改写。合成B/C预演不是真实角色部署或真人群准入证据；当前角色/店铺绑定和最终准入仍由A/Root在冻结原对象与时限内核实。新群、同新群任务的独立查询/解释、必要真实负向及最终main/结案均为 **PENDING**。

| 原五项／当前状态 | 原 AC 映射 | 复用证据 | 仅缺项 | Owner | 依赖 | 完成判据 |
| --- | --- | --- | --- | --- | --- | --- |
| ① 真实群完整20项未知联合确认及独立拒绝：PENDING | AC01/02/03/10 | 原私聊/F02、P2金标、089/037准备及925 owned全量确认/拒绝；不冒充真人群 | 原定新群完整20项/全部未知键联合确认、独立拒绝；PG task→approval→execution→item→Base唯一关联 | A执行与关联；Root统一准入；原Reviewer独审 | 最终源码冻结/影响核验，当前合资格身份与同店scope、原计划与有限窗口；沿9h批准方案，不由C另造任务 | 正向20 items/Q2000逐项对回冻结事实/版本/键与Base；独立拒绝零执行/零内部项/零新增Base；原回执及cleanup核收，同一计划不兼作批准和拒绝证据 |
| ② 同原计划重复/冲突、必要真实负向与恢复：PENDING | AC03/04/05/07/10 | 已核PG过期/撤权/跨店/篡改/kill矩阵、C Web/N01权限负向、6337 owned两例；合成B/C结果仅为预演 | 同原计划真人10重复、双合资格人冲突和批准方案内仍缺的真实负向/跨进程关联；不伪造callback、不重跑整套矩阵 | A正式通道/恢复；C仅复用既有权限材料；Root/原Reviewer核收 | 与①共用冻结计划/角色/原事件/等待点；先核已有证据，只补最终受影响链 | 同原plan/decision/callback精确关联，仅一个决定/一组执行生效；跨进程不丢早决定、不增项；负向不产生越权业务，不把技术覆盖说成平台全负向实测 |
| ③ 新群任务查询/既有结论解释独立样本：PENDING | AC09/BC02 | 877现有read-reply/来源/权限/重放能力与已核解释材料；旧DM调查结果仅作历史，不作本项成功前提 | 在原定新群任务中冻结独立进度查询/既有结论解释样本及实际回复；原两条私聊停止专项恢复、不要求重发 | A查询/解释与原回复链；Root冻结样本/准入；原Reviewer核收 | 依[新整包授权](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6286688465)限定task/report/actor/chat/消息来源与回复次数；不得把新样本称原DM已恢复，不新增付费模型调用 | 新样本自身的message/event→task/report→只读结果→回复ledger/平台回执闭合，各按冻结范围一次；无新业务写/重复回复，缺已有解释仍明确NOT_READY，不伪造已有结论成功 |
| ④ 原T6/v2只读Web与原key GET：已闭合、复用 | AC06/11 | 原真人T6/同record Base v2；9ee下af731 automatic page/replay实际通过并独审无P1/P2；877保留同consumer | 无新增执行缺项，不重做人类登录/批准/关闭或增加展示Gate | A原运行、C展示核对、原Reviewer独审；Root已核收 | [原④正式回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6247929850)继续有效；后续只按源码实际影响复用 | 原closed/v2/原因/处理人/时间、当前Base v2/unique/controlled_sdk、原key GET各1、业务POST0、当轮SDK0和cleanup均按原证据；技术认证单列，不冒成本轮新SDK核实 |
| ⑤ 最终交付/独审/精确CI/main合后/Issue结案：PENDING | AC08/09及整体 | c460新owned Compose四场景与原键/恢复/cleanup、既有分步运行说明、私有素材；877五绿563 PG与4安全artifact | 最终候选只补受影响链，回填新群/新查询/真实负向原件，再完成同批增审/CI/main/结案；不新增一键完整验收Gate | C原交付文件；A主体/公共接线；原Reviewer独审；Root统一集成/CI/main/结案 | ①–③必要证据到齐、④复用、最终source冻结并核影响；私有媒体不随clone分发或上传raw，不以剪辑补造过程 | 无未解决P1/P2；最终精确CI、Root逐Gate签收、正常main合入及合后同SHA CI、对应Issue结案；C不自行发布/触CI/合main，未完成处保持PENDING |

本9h包为540 Agent有效分钟，初分A330/C60/Review90/Root60，由Root总额内调配；本页准备不构成整项M1按时完成承诺。旧用量、风险、SDK/attempt/once与失败均保留，不清零；D1=2026-10-10、D30=2026-11-08、项目300h/P4原计划50h、人工H/L unknown及冻结18页/Penpot/备份不因本包重置。

## 历史材料（仅当时状态，原文保留）

<details><summary>展开旧运行说明、交付工作稿、逐 AC 地图与历史证据</summary>

以下原文中的“当前”“待验”“唯一下一步”仅指其记录日期，不覆盖上方唯一五行清单；旧失败不改写为成功，已核事实也不因旧 pending 重开。

## 新 clone 运行包的交付范围（2026-10-18，静态增量）

现有公共 Compose/CLI 足以说明人工启动 Mock 核心服务的路径；可重现的公开分步命令就是本次交付选择，不新增“一条命令完整验收”必要 Gate。详细参数、顺序和源码依据见 [新 clone 启动说明](M1_OFFLINE_COMPOSE.md)。本次只读源码并补文档，没有安装或运行服务，没有改变 c460 冻结或 A 当前验收。

| 交付层 | 已有材料 | 最小未完成项 |
| --- | --- | --- |
| 人工运行 Mock 产品 | 两份 Compose、公开 prepare/seed/api/worker、四个数据库动作；新环境生成合成账号与私有配置 | 已补源版本、非秘密参数生成、有限 expiry 和全服务停止说明；未实际做本次新机器复验。静态未发现需要 A 新增代码才能启动的不可替代配置缺口 |
| 四场景自动采集的复用限制 | 已审 consumer/capture/UI/cleanup 构件；私有 c460 四场景成功及原键/重启证据 | 私有具体调用者和输入未公开，不宣传 clone 自带一键自动验收；不复用过期 DTO 或把 helper 导入当实际运行，也不因此要求 A 新建 launcher |
| 求职展示和验收资料 | 原片、七图、三文档与本地候选；原 Reviewer 仅核收为 `PRIVATE_UNPUBLISHED_CANDIDATE_ONLY` | 资料不随 clone 自动分发，也不是执行环境；不公开原目录，不从候选视频推断当前机器已经验收 |

不把已有公共服务误报成“缺全部装配”，也不把私有整批自动采集器不便携升级为新产品 Gate。只有实际分步启动暴露不可替代的配置/装配缺陷时，再将准确工程依赖集中交 Root/A；本批未发现此类静态阻断，不开发新框架或修改 A/shared 文件。真实渠道、投影及全部核心 AC 仍按下方各自证据核收，旧失败与旧工时保留。

## 当前交付工作稿（2026-10-17，待合批审核）

本节沿用 Root 的 Issue39 裁决及评论 6233059628、6234076316、6234301886，并纳入随后已独审的 RO140200 与 Root 事件日志只读记录（观察时间 2026-10-17 14:16:09.975121Z，北京时间 22:16:09）。此前 13:21:29Z 的“原消息持久状态 UNKNOWN”是当时事实，后续只读结果不倒填旧失败。当前只整理原三份文档和只读核对本地媒体，不修改业务源码、素材或其他阶段文件，不启动服务或平台动作。下方旧地图、失败及当时的 pending 原文保留；旧“F02 待验”“干净 Compose 待验”等表述不覆盖本节已经核收的限定事实。

| 当前事实 | 交付可引用的范围 |
| --- | --- |
| 真实 F02、原私聊任务/审批、真人 T6 与原 Base v1/v2 已核收 | 复用各自原对象、回执和 Review；不重发 F02，不重复批准、T6 或 Base 写入来补镜头 |
| c460 有限离线核心复现已独审 | 四场景、3 executions/22 items、11 POST、84 GET、原键完整回读、受控重启和停止证据；独审 `a6d70d4d8ad7ee82e5166518d33d997c5e6e0212d3330da952f0e07d1b0babeb` |
| 同源码既有 CI39015392794 已核收 | 五项成功、541 PG；本次三文档工作不产生新 CI 或合后验证 |
| 原两条精确绑定查询的本地 inbox/carrier 为 0 | 原 actor/chat 与文本 hash 谓词下的只读结果已独审；不扩为所有消息均为 0。平台近时两个失败事件与原文本的精确关联仍 UNKNOWN，真实查询回复 Gate 未过 |
| main 仍为 P3 核收基线，M1 in_progress | 群、必要负向恢复、查询回复与最终交付/合后验收尚未齐，不能关闭 M1 |

c460 源码为 `c460d6f63f95060a2b25ae9418ca6e3020f89169`，本次完整实际索引 SHA256 为 `cbf5da8b111a6b76f2eb3d0edf2906e882aea9d9fc17158f57ba5f43d9768791`。原命令、私有索引定位、解包权限和清理说明集中于 [Compose 说明](M1_OFFLINE_COMPOSE.md)；原片和演示时间轴工作稿集中于 [Web 交接](ux/phase4-implementation.md)，避免重复建立另一套验收账本。

### 查询 Gate 的新增只读证据

| 原件 / 固定校验 | 新事实及不能外推的部分 |
| --- | --- |
| `independent-actual-RO-140200-review.safe.json`；SHA256 `355ee2f3e4e3a1e0fc17c15109fd45b69fc7aa3ead28ac1536605c184e67800d` | 原 Reviewer 核 72 引用无差异；原两文本 exact hash、原 actor/chat 匹配的本地 inbox/carrier 为 0，三段 RO rollback、I/U/D=0，F02 保护行不变，清理完成。该结果是指定快照和谓词下的本地零行，不是用户未发送，也不是所有平台事件均不存在 |
| `Root-feishu-event-log-readonly-complete-20261017.safe.json`；SHA256 `b8a39d7b07579b5676fd3ced01f805266bcbf854058c33c51d8ed746c0e1eafb` | Root 在专用测试应用后台只读看到北京时间 21:02:10、21:02:21 两个 `im.message.receive_v1` 事件；首推为 app not online，retry 1/2/3 均 FAIL，旧 Gateway 已于 21:01:45 停止。日志无正文，不能证明这两个事件就是原两条文本，不能把时间接近写成精确关联或旧异常唯一根因 |

当前能够收口的是“指定原消息未在该本地快照受理；平台存在两条近时失败事件”。尚未收口的是原文本到平台事件的精确关联、可靠通知交接与真实回复成功；发送者阶段未执行的事实不等于完成了最终 ledger 测量。后续恢复由 A/Root 依这些只读事实制定，不重复本次 RO 来补文档，不直接要求用户重发，不自动复活旧窗口或打开真实平台。

### 逐 AC：现有证据与最小剩余交付

以下是证据映射，不是逐项重新签发 PASS。自动化与真人、内部业务与外部同步分别记账；原 PG、契约、性能和故障材料只按已核范围复用，不为补摘要重跑矩阵。

| AC | 已取得、可复用 | 仍待的最小交付 |
| --- | --- | --- |
| AC01 私聊与群 @ 闭环 | 原真实私聊任务/审批及 Base v1/v2；真实 F02 已核收 | 真实群 @ 的完整 20 SKU、审批/执行/内部项/Base 关联；查询回复另按 A 的原消息核验结果收口 |
| AC02 金标与事实 | 已核 P2 金标；c460 的 20×100 与 known 70；事实不交模型改写 | 将最终群计划/报告逐项关联到冻结事实、参数和全量 20 行，不新增模型调用 |
| AC03 拒绝及唯一决定 | 既有 PG 并发/相反决定矩阵；c460 原生拒绝后零执行/零项 | 最终正式卡片拒绝/冲突与原 task/decision 的配对；独立拒绝计划不拿批准计划代替 |
| AC04 重放与提交边界 | 已审 Gateway/Worker/PG 重放、恢复矩阵及原键技术证据；c460 重启后 11 原键结果一致 | A/Review 先核正式通道已有回执是否足量，只补经审定的缺失关联或恢复点；不在已终态原项上重做业务 |
| AC05 身份与权限 | 已审身份/跨组织/hash/期限/撤权 PG 和 Web/N01 拒绝 | 当前正式卡片的必要未授权/范围负向与业务记录配对；不把技术覆盖称作所有平台负向已实测 |
| AC06 外部故障与恢复 | 原真实 v1 unknown 同键恢复及同原 record v2 唯一读回；既有 Fake 故障矩阵 | 当前真实同步事实的展示/观察及其来源串联；不重复平台写，不称自然 429/5xx 均已观测 |
| AC07 跨进程等待与早决定 | 已审 checkpoint/ready/恢复矩阵；c460 的受控恢复与版本等待 | 正式待审批/恢复后的原决定关联由 A/Review 盘点，只补未覆盖的正式点 |
| AC08 干净环境与真实飞书 | c460 新 archive/new owned Compose 四场景、正常恢复、原回执和清理已有限核收 | 真实查询、群及正式通道证据仍需并入最终验收；Woo 留 M2，不借本工作稿提前签整体 AC08 |
| AC09 来源、模型与轨迹 | 原 P2 actual provider 解释/usage、既有模板/缓存与 Web 轨迹；c460 运行来源索引 | 原两条查询及已有解释的真实回复/同任务绑定；最终来源/版本/审批/SDK/同步轨迹串联。无缓存保留 NOT_READY，不新付费生成 |
| AC10 完整未知确认 | 原 PG 的漏/多/篡改/跨版本矩阵；c460 全集合显式确认及独立拒绝 | 正式群卡片完整确认和独立拒绝的配对证据；普通 approve 不替代联合确认 |
| AC11 原因、幂等及新周期 | 原真人 T6/Base v2；c460 显式 close/v2/原因、同池新周期、独立执行及原键回读 | 最终展示中补当前原结果的只读观察与证据链接；不复活旧执行、不重复原 T6 |

**29 条 outbox 仍 pending、attempts 0。** 本次 c460 调用者没有 SyncRead/drain/投影验证；`offline_fake` 标签不等于 Fake 投影完成，更不能算真实 Base 同步。11 笔非重复 POST 和七张截图不能替代缺失的投影回执；84 次 GET 中包含 11 次原键回读，也不构成投影验证。

### 最小接续顺序与可并行材料

1. A/Root 按已核 RO140200 的精确本地零行、平台投递失败及仍未知的文本关联制定恢复。旧查询窗已关闭，不直接要求用户重发；不能把本地零行等同于平台无事件，也不能把后台 FAIL 等同于原文本的完整投递诊断。PG-only 和后台只读都不证明回复成功，真实动作仍由 Root 另行准入。
2. A/Root 将真实群全量确认、独立拒绝、冲突、必要权限负向及恢复缺口合成有限对象清单。技术矩阵、已过 F02、T6/v2 和 c460 四场景不重新开题；一个计划不能同时证明拒绝零项和批准 20 项。
3. 当前三份文档可先完成来源/证据映射、运行说明缺项、时间轴与字幕文字工作稿。A 稳定事实到齐后再补真实查询/群的原件链接和结论，经合批审核后纳入最终 source、Review、精确 CI、正常 main 合并、合后同 SHA CI 与 Issue 结案。C 不自行发 GitHub、合 main 或触发 CI。

### 成片、运行包与验收的不同完成条件

- 本次完整 post-login 原片和七图已核存在、哈希相符；有限机器可见内容核对发现五图为加载/会话核实态，两图可识别 closed/v2/70 但仍有定位标识。45.80 秒原片可作私有技术证据，现状不适合直接公开为求职主片。具体采样、缺镜头及脱敏限制见 Web 交接；全 20 行可读、真人观察与公开成片仍未签发。
- `runtime/m1-clean-c460-batch-88094ef275/` 是原 C 私有证据目录，不在公开 clone 中。原窗口和输入已过期，工具链绑定原机器位置；不能把现有私有 launcher 宣传成可分发一键包。最终可移植运行说明须由原 owner 在审核中补齐装配取得方式、工具链核验与新私有输入生成边界。
- Issue42 与 PR45 的旧状态/旧 head/旧 checks 是历史材料。当前核收以 Root 在 Issue39/PR43 对精确 source 的裁决为准，不因旧失败导航重复实现或追加 UX；本工作稿不改写远端状态。

本次只作已授权的并行文档准备，估计 0.5–0.75 Agent 有效小时不是已花工时；实际用时交接时另记。原 C 16/24 分钟、此前只读核对约 0.17 小时及全部旧失败/用量保留，人工 H/L unknown；D1=2026-10-10、D30=2026-11-08、项目 300h 与原 P4 计划不重置。

## 历史验收地图与交付路线（以下原文保留）

更新：2026-10-17。**私聊任务/审批、已提交的原 T6、真实 Base v1/v2 已由 Root 核收；P4 / M1 整体仍为 partial。** 本页是交付作者稿，待本功能批独审及正式集成；不代替逐项验收，不授权新平台动作，不表示真人已看到当前 Web v2 页面。

## 当前证据基线

- [Issue39 正式核收](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6229884679) / [PR43 回执](https://github.com/aning0922/commerceops-agent/pull/43#issuecomment-6229884891)：source `0c90880761f7065b33ccf6b1ffc1c3a9ba5dc597` / tree `6cf9bdd26ad596443df522919b8b87fcb01d4e62`，私有 `sealed-e30306c7`；[CI38953939340](https://github.com/aning0922/commerceops-agent/actions/runs/38953939340)五绿、530 PG / G1 / G2 / Web / N01。main仍 `9d97c19009d932036809ac3e2638bb68f4b7f765`，PR43未合并；新 F02/read_reply 父流程功能批不由旧 CI 代签。
- 实际北京时间 **12:49:00–12:49:46**：SDK7（auth1/bot1/table1/field1/list2/Update1）全 returned/HTTP200/code0，Create/IM/provider0；同原 key/item/outbox/record 的 v2 verified、attempts2、observed_version2，15字段及完整分页唯一读回成立。原 T6 已 COMMITTED，本次未重复登录、批准或关闭；此前失败/SDK9/Create1 保留，该链累计SDK21/Create1/Update1不含其他独立探针。
- CLI/operation/cleanup均0，writers退出后、PG down前取最终快照；原关联 task/approval/item/关闭请求/item audit/outbox/link **七类原对象行**与前态相等，不扩为全库 execution 或逐表计数不变。资源0、端口关闭、保卷；Root与独立Reviewer回执SHA `5b52d7861ec6fe1b5eab5730170275f71d669e106c27b81567a0b4576972c22c`。原始HTTP wire未采集，不主张网络 exactly-once，也不把服务端/平台读回当真人页面观察。

<details><summary>10月15–16日基线、失败与只读诊断历史（仅当时状态）</summary>

- 旧源码 `049874ea` / [504 PG CI](https://github.com/aning0922/commerceops-agent/actions/runs/38734359318)、`0da42295` / [506 PG CI](https://github.com/aning0922/commerceops-agent/actions/runs/38834680327)保留。以下 NOT_RUN/NOT_VERIFIED、待恢复与 HOLD 是当时范围，不推翻10月17日单记录核收，也不倒改原失败回执。
- 历史 049 LAB full12、原 v1 RO `verified / complete_unique`及 manual SPENT / Create1 / attempts3 保留。旧密码未找回，旧库零操作；[fresh 新链批准](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6208312714)已允许新 task/item/record，当前不再要求恢复旧项后才能继续，也不重跑旧 RO。
- [locator/SYN 回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6208430056)：locator auth1+wiki1，fresh metadata4/6成功且额度已 SPENT。[首 business-ready 窗失败](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6208832737)发生于 Gateway/Worker 前，business SDK/T1/item/outbox/Base/IM 均0，已 down、资源0、保卷；失败窗不得复用。
- [readiness 修订回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6209264870)已独审：同实际 entry 的 API、hydrated、CSRF/session、实际 synthetic login → native Worker → v1 → 同 browser close → 同 record v2 与失败 cleanup 的合成证据成立（索引 `7e3464…` / final `7c1a47…`，27 refs）。仍为 Fake/合成，真人和真实 v2 **NOT_RUN**，不外推未冻结增量已被上述 CI 覆盖。
- [最新真实窗口回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6210030852)：新本地 arm 实际成功，服务通过 hydrated/CSRF/session 检查，真人确认登录并发送一次 DM；没有批准卡片或 Web close。Gateway 启动且有外向 TLS443，**不证明 WS 认证、订阅或入站就绪**。当时两次 watch 均报告未取得合格 T1；后续离线核实第二次未执行 SQL，不能解释为 SQL 查空；终核“业务表全零”断言失败且未先保存 counts，故最终 T1/inbox/receipt/job/item/outbox 均为 **NOT_VERIFIED，不得写0**，也不能断言消息永远未入库。Worker 未装配/启动，卡片、业务 SDK、Base create/update 均0；Gateway 网络请求总数未独立采集，不能写0。实际回执 SHA256 `d3a7ab800467d3c383600976dd0c7c0902310aaf9aafc484b0be262dd66770ee`。所有父/子进程已停并 reap，PG down0、容器/网络0、端口关闭、保卷；不重发、不重开，历史 locator/metadata 消费不重跑。
- [后续唯一 PG-only 只读核验](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6210671544)已 exit0、独审通过并停止保卷：inbox1/receipt1，原合同 tasks2（queued）/jobs2（ready、attempts0），无 clarification/item/outbox/Base/IM，仅历史 metadata4。规范原指令 hash、当前 actor/auth3、参数及窗口谱系匹配，**已解除最终是否受理的不确定性，业务尚未执行**；不得把这些后续事实倒写成旧失败当时已核实。receipt 在原 arm 后115.816652秒落库，前120秒准入仅余4.183348秒，Worker未启动；WS认证/订阅ack仍无独立证明，不将时间缺口称为全部唯一根因。
- A 离线核实际旧入口已确认：第二次 watch 剩余约145秒，`while remaining>=180` 未进入，`T1_unique=false` 是初值；旧“第二次 SQL 成功但未查到”表述已纠正，旧文件保持。第一次 watch 因 `remaining>190` 条件提前结束，异步 shell 返回后 bind/Worker 未自动接续；receipt 在首次观察后约5.70秒持久化。原因索引 SHA256 `06007693c5942d29e07ab5f1de2a5ef8d498002a260ec1ca9d116eae87ed9a43`，待整批 Core 独审；修正仍进行中，不预写修复 Gate 通过，也不把准入时间缺口说成全部唯一根因。
</details>

- C 原工作区 `phase4-web` / `codex/phase4-web` / HEAD `432f3c2`；本轮仅在已有已审文档补丁上更新状态，原四采集文件保持已审字节，不并改 A 源码。main 最后已核仍为 P3 的 `9d97c19009d932036809ac3e2638bb68f4b7f765`；P4 未合 main，未结案。
- 依据为 [PRD AC01–11](PRD.md#7-p0-交付验收)、[TEST_PLAN](TEST_PLAN.md)、冻结 18 逻辑界面的 [screens](ux/screens.yaml) / [交接映射](ux/ux-freeze-candidate.md)。冻结设计不等于 18 页均有当前真人证据；不新增设计批次。
- 原交付路线、故障分镜和历史结论保留于 [本页旧版](https://github.com/aning0922/commerceops-agent/blob/432f3c273fb94e820d8c9cabd55fa968e0efa279/docs/PHASE4_M1_DELIVERY.md)、[历史验收](PHASE4_ACCEPTANCE.md)、[Web 与原片 QA 记录](ux/phase4-implementation.md#既有证据怎样使用)。历史失败不改成通过，旧 pending 不覆盖当前已核事实。

## 逐 AC 证据与最小缺口

“已证实”指表内限定证据；“范围有限”不等于整项 AC 验收。真人缺口不要求重做已经通过的全部技术矩阵。

| AC | 已证实 / 可复用证据 | 范围有限 / 仍缺证据与最小补项 |
| --- | --- | --- |
| AC01 私聊、群 @ 闭环 | 私聊 task/审批/原 T6 与 Base v1/v2 已核收；原单用户链与049等隔离PG历史保留。 | **私聊限定范围已证实，群仍缺**：真实群 @ 全20 SKU、完整假设确认及Base关联仍待；同任务F02/查询解释属于新功能批，不由该单项成功外推。 |
| AC02 金标、事实不漂移 | P2 已验收金标；known70、twenty 20×100、raw null / effective 0 的 PG 与 Web；确定性规则不交给模型。 | **已证实限定技术范围**：把最终实际群报告逐项对回冻结 fixture / 参数 / 完整 20 行；无需新增模型调用或重算旧金标。 |
| AC03 拒绝零项、相反决定唯一 | `test_p4_a08_group_pg` 的联合确认/拒绝、十重放、相反 actor；P3 真实 PG 并发与 Web 决定场景，049 完整回归可复用。 | **范围有限**：缺当前正式真人卡片拒绝/冲突结果与原 task/decision 的配对；安排到同一有限群/审批批，拒绝分支不生成 item，不重复整个 PG 并发矩阵。 |
| AC04 十重放、提交边界恢复 | `test_p4_gateway_pg` 事件/ACK 重放；`test_p4_a09_workflow_pg` 跨 Gateway 五边界；单 Worker/执行唯一与 049 LAB 持久恢复。 | **范围有限**：技术矩阵不是真人点击十次或真实跨窗演示；核已有正式入站重放/kill 回执是否足量，再只补未覆盖的正式路径。不得在已终态原项上重做业务。 |
| AC05 身份、跨组织、hash、过期、撤权 | P3 authority、P4 group/identity/preflight/撤权 PG、真实 Web 权限和 N01 零业务拒绝均有可复用技术证据。 | **范围有限**：真实卡片的未授权人/当前范围拒绝与已审业务记录仍需配对；最少安排既有未授权测试身份的一次负向操作。其余完整组合用已核 PG/契约证明，不能声称平台全部负向已实测。 |
| AC06 外部故障、unknown 恢复 | Fake故障矩阵、真实v1 unknown同键恢复与10月17日同原record v2 Update1/完整唯一读回均已核收，旧失败和SPENT不变。 | **平台恢复限定范围已证实**：不能称自然429/5xx等全部真实观测；当前Web同步展示仍缺一次只读观察，不为镜头增加写入。 |
| AC07 待审批跨进程、早决定不丢 | P3 checkpoint/ready、P4 A08/A09 五边界和同原 workflow/nonce/plan 恢复 PG 已覆盖；早期 SDK 重启未核事实保留。 | **范围有限**：正式真人卡片等待/恢复后原决定的关联演示未齐；可与群审批批共用一个已登记等待点，不重开同 pool 成功批。 |
| AC08 M1 干净 Compose、真实飞书 | 多次自有 Compose/真实 API+PG/Mock Web 部分闭环；049 LAB full12 / CI 的资源停止和不变量证据；旧录像有只读完成态补证。 | **缺最终交付证据**：最终稳定 SHA 在新空 checkout/新 owned project 的原始统一命令、成功新周期与重启/原回执回放、停止清理，以及对应真实私聊/群证据。LAB 进程 restart 不等于干净 Compose 重建。旧 source43 AC08 整体 failed/partial 保留；Woo 真实店只读属于 M2。 |
| AC09 来源、规则、模型/usage、工具与审批轨迹 | P2 一次 actual provider 解释及 usage/耗时已验收；P4 模板/冻结结果、read reply、events 来源绑定与真实 Web 只读可复用。 | **范围有限**：最终运行的来源/版本/审批/SDK 方法/同步轨迹和已有解释展示需串联；历史模型调用仅沿原绑定引用，不冒成本次新调用，无缓存显示 NOT_READY。P1 动态 Tool Agent / 40×3 不扩大为本次 M1 新 paid Gate。 |
| AC10 完整未知键、版本绑定、拒绝与幂等 | P3 A01–A08 与 P4 group20 的漏/多/篡改/跨版本/撤权/十重放 PG；Web 完整集合与 null/0 显示已有技术证据。 | **范围有限**：至少一次正式真人完整确认及拒绝的卡片/PG 关联未签；与群成功 20 项和独立拒绝计划合批。普通 approve 不代替联合确认，不能截断到前几项。 |
| AC11 T6、原因审计、新周期 | P3 C01–C05及旧Mock技术证据保留；原真人T6已提交，原对象真实v2恢复已核收且未重复T6。 | **当前单项T6/v2已证实**：仍缺本次Web结果只读观察与最终新周期/旧执行不复活的交付证据；七类原对象相等不冒充全库execution计数已采。 |

## F02、查询解释、群与恢复的实际边界

| 能力 | 当前可复用事实 | 仍需补的最少证据 |
| --- | --- | --- |
| F02 参数澄清 | [F02 合同](contracts/p4-f02-clarification.md)有默认关闭、原请求/轮次/当前身份、完整候选、显式确认同事务原 T1；049 包含正式 child 装配和 `test_p4_f02_pg` 的实际 Gateway-selected / Worker ledger 链（外 HTTP Fake）。 | 真实飞书“缺参→补参→确认→同原 T1”及原 UUID 回执仍缺；不能沿用首包“未接 child”旧状态，也不能以源码/PG 宣称真人已过。可作为后续一条群或私聊正式请求的前置步骤，避免额外成功业务批。 |
| 查询同任务、解释已有结果 | `test_p4_template_results_pg` / `test_p4_read_reply_pg` 已有真实 PG：固定来源、并发/十重放、零新业务、当前权限、不可变载体和 unknown；原 P2 actual 解释、Web 已有解释/NOT_READY 均可复用。 | 当前正式飞书原任务的进度查询与已有结论解释回复未有完整真人/SDK闭合证据；并入同一现场批，不新增模型付费调用。不得用 NOT_READY 冒充已有解释成功。 |
| 群 / 负向 / 恢复 | 049 group20 / callback / 原workflow / Base恢复已实际走隔离 PG、Fake 与 Web；原真实单用户窗口明确 group_count=0。 | 真人群 @、真实完整卡片/确认拒绝及必要权限负向；non@/self-bot 若平台不投递，只能证明平台行为，收到后的应用过滤仍按源码/受控测试记账。真实跨窗恢复与 PG kill/restart 分记。 |

## 最少现场批与可并行离线项

当前原记录恢复窗口已完成并关闭；剩余额度不转作新业务，不重跑T6或v1/v2、不增加登录/批准/关闭来凑镜头。

1. **当前唯一下一步：A 在原PR43完成 F02/read_reply 父流程最小生命周期接线及真实模板实际入口的合成全链，再经同批独审、精确CI和Root统一准入，安排有限真实窗口。** 当前只是功能批实施/准备，不预写真实F02、查询解释或群业务通过。
2. 后续现场将F02补参、同任务进度/已有结论解释、群@完整20项联合确认、独立拒绝、重复冲突及必要负向恢复配成有限对象清单；一个计划不能同时证明拒绝零项和批准20项。Root限定对象、pool、次数及清理，既有成功私聊链只读引用，不另造管理体系或重复平台探针。

## 最短演示路径与唯一 Web 只读观测

| 演示段 | 复用已核证据 / 路径 | 当前仍需的观察或镜头 |
| --- | --- | --- |
| 私聊业务与同步结果 | S09任务→S04原审批→S11原项/原因/版本→同步事实，关联10月17日同record v2核收。 | **一次统一授权的Web只读会话**：在现有Web/API读取同原task/item、原key GET、closed/v2、原原因/actor、当前Base v2 verified/complete_unique及历史v1；不新建T1/T3/T6或平台写。登录属于认证单列，业务POST应0。实际入口/source/build/身份refs由A/Root供给，本轮不开页。 |
| 来源、模型与说明 | S03/M03报告事实→S06事件→M04已有解释；[P2一次真实模型证据](PHASE2_ACCEPTANCE.md)按原report/usage/耗时绑定引用。 | 新P4模板说明明确 template/not_used，不伪造成新模型调用；无既有解释显示NOT_READY。真实查询/解释reply由A新功能批补验，CI页面能力不冒充已被真人看见。 |
| 群、未知确认与拒绝 | F01/F02渠道材料→S03完整20行/null→S04完整键确认或独立拒绝→S09执行。 | F02/查询解释/群20与负向真实证据仍待，补完整20行可读、未知键全量、意见受理与执行分开画面；不能重剪旧partial当本次群成功。 |
| 新周期、复现和收尾 | S11结果→M05/M02新草稿→新分析审批→独立执行；原回执只读回放。 | 最终新空checkout/干净Compose全链、新周期/持久重启、清理与最终录屏仍待；LAB进程restart不等于AC08干净Compose。 |

现有Web/N01实际CI证明已审源码下页面/API行为；`simulated_web`、真人点击报告、真人对最终页面的实际观察分别记账。上述只读会话是当前单项成果的最低补充观察，不等于所有18页或全部M1已验收。优先在Root后续统一演示窗口一次完成，不为文档另开服务、浏览器或第二套工具。

可在正式现场前并行完成：最终新 checkout/Compose 的离线完整复现及录制、C 消费者/DTO/采集契约交叉核对、证据逐 AC 关联、说明文案/脱敏字幕准备、旧 P2 模型来源与性能报告的范围核对。已通过的当前 530 PG/Web 与金标不为填摘要重复运行；后续源码变化仍须必要回归和精确 CI。性能复用 [P4 固定 100 事件/20 分析/扫描报告](contracts/p4-performance.md)，不能把 Mock 本地 p95 外推平台/供应商 SLA。

## 干净 Compose、18 页与录屏的剩余交付

- 最终 Compose 演示固定同一 source/tree/build/命令和新 owned project/volume：完整 20 SKU/未知键、拒绝零项、批准/执行、单项 T6、新旧周期隔离、持久重启与原键只读回放；结果按实际记录，失败保持 partial。只使用 MockCommerce，Fake/模型模式逐段标明；不能启动旧 profile 意外创建另一套 seed/API/Worker。
- 页面沿 S01/S02/S09 → S03/M03/M04 → S04 → S05/S11/M01 → S06 → M05/M02，F01/F02 采用相应真实渠道材料。18 逻辑页是设计范围，无须另造 18 次业务写入；S07/S08、390px、键盘/焦点、登录撤权的既有 Web 证据可作附录，缺当前展示则标缺镜头。
- 旧影片只有部分 20 行/投影标题与完成态，不是完整当前同步卡/close 原因/全链新周期录像。既有盘点中，旧 QA 文档记载的两份私有 QA JSON 与三帧之一在原 C 路径未找到，**仅记当次路径缺证，不删除资产、不推断已丢失，也不把历史索引当现存文件证明**；由 Root 从既有保留包定位，若无法定位就明确缺素材。
- 最终录屏须完整可读地覆盖 20 行与 unknown/null、原因/版本、业务终态和独立同步、来源/usage/模型模式；真人与 simulated_web 分段，认证输入不录，原值/URL/标识/密钥不公开，不把旧 Fake 画面剪成真实 Base 过程。先保存私有原片和来源/hash，再脱敏 QA；片长不构成延长窗口理由。
- 最终 Root 汇总逐 AC 证据、剩余限制、无未解决 P1/P2、新精确 CI、正常 main 合并/合后同 SHA CI及 Issue 结案。P4/M1 未因本地图或原记录 T6/Base v2 单项 PASS 而完成；原 300h / P4 计划 50h、H/L not_reported 及全部旧资源/Penpot/失败保留。

</details>
