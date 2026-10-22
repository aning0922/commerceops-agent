# M1 群真人操作窗口与累计额度（2026-10-21）

本批依据用户“批准统一调整，准备好后再协调真人”实施；[完整方案](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6310867104)。
总有效cap1140，新增180（A105/Review25/C10/Root40可总额内调配），所有旧用量不清零。
实现/owned验证不等于真实授权；真实须最终同源预演、原独审、新精确CI、Root对象/UTC与新真人就绪。

## 已发生事实

066首入口在消费once后、PG前因证明0644不满足0600而HOLD；原件/once/异常保留。
metadata修正仅使用byte-identical0600副本，不改身份/角色/权限。
06:32群窗因NEW_T1_TIMEOUT失败；首消息发错群，正确群补发14:37:03比截止晚63秒。
07:12群窗形成新Task/卡，B完整阅读；因无完整真人动作报告而REAL_CALLBACK_REPORT_MISSING_OR_LATE。
用户报告A/B/C均0点击；成功决定receipt0，原始拒绝/忽略callback数未采集。
最后库状态awaiting_approval/pending，原审批到期07:29:06.807772Z；不续旧卡或恢复旧消息。
最终8PID退出、容器/网络/挂载0、保卷。两真实群PG已使用，不复用其许可。

## 显式 group G2 准入

现有Gateway/Worker DTO增加可选group_operation_chat_id，缺省不输出该字段，旧claim/hash形状保持。
仅baseline/L3/R7/S2、max_workflows0的显式group-ready G2可用；当前唯一允许群精确匹配，至少两位允许用户，F02/external_sender关闭。
原默认、私聊、其他群、known70/F02/terminal等路径保持300秒。
Worker仅原approved_workflow同任务/receipt/plan/approval原生来源可用；原receipt必须group且目标精确相等，Gateway/Worker scope一致，Update0。
先完整准入后Secret/Factory。窄路径最大600秒，候选540；通用SDKWindow、迁移、角色、审批状态机、TTL900不改。

## 真人与固定时间

B先完整阅读20项及全部假设，随后C/B/A确认同一卡、设备及动作流程准备。观察时间真实且不晚于read-ready截止。
G2须实际WS ready、Worker/IM/Base就绪、旧进程停止与当前身份核验。
实际通知返回后至少360秒，包含14次动作、三人交接及报告；这是保证的时间机会，不是测得的真人容量。
原顺序C首次拒绝→B首次决定→B重复10次→B相反→A冲突保持；成功组不重复C。
报告目标比操作截止早30秒，硬截止不移动；缺失/迟到/unknown保留并停，不补写通过或自动重开。

每case候选相对PG T0秒：G1start30/card180/stop210/expiry330；完整阅读目标360；角色准备及read-ready420；
G2start450/ready480；实际通知返回最迟510；action870；SDKexpiry990；collect1020；PGhard1200。
业务完成须在SDK expiry-30前；最终采集在全部writers退出后、PG关闭前，清理≥180。

## 累计额度

旧SDK9：auth2/bot2/table2/field2/IM1，全部HTTP200/code0；Create0/Update0。
parent绑定已停止ledger的精确路径/hash/9条唯一记录，累计从9开始，剩余不因新run重置。
累计group caps auth6/bot6/table10/field10/IM5/Create20/list42合99；扣旧9后新群最多90；查询6，总105。
新回调许可≤30，历史许可上界16与raw frames unknown分列。真实群PG4已用2，两个新case先拒绝PASS且清理，再成功；success20后才新群两查询。

## 验证与发布

先离线DTO/结构/时序/默认拒绝与累计额度检查；最多两个新owned窗，各≤1800/cleanup≥180。
SQL/低权/once/原键/恢复/最终采集/清理真实；Fake仅owned底层外HTTP与明确合成人。
同最终源码完整外层须证明长G2 success20、拒绝/迟到/默认或非group拒绝、取消、冷重放与保留行。
保留旧565并新增必要回归；原45/43分区和保护不放宽。只普通本地commit；Root安排整包独审及精确CI。
A不push/改PR正文/CI/main，真实当前HOLD。


## 2026-10-22 完整新查询样本收口包

本段依据用户[完整方案批准](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6338628170)，
覆盖此前仅300秒接收窗口的当前新样本安排；旧文本、失败、once与所有预算用量保留。
未来新增240 Agent有效分钟（A140/Review55/C4/Root41可在总额内调配），总规划1720；
历史净余UNKNOWN，原300h、P4原50h、D1/D30与人工H/L不重置。C只用既有交付材料，
不重跑已完成的私聊/F02/T6/v2、两真实群或C4 Compose/media。

原真实群predecessor为source `2f13836344fef1624efbe7b60f786a5b1bba735d`、
tree `c512bd8a75e03273c68e51df389dcf19bebf7680`。旧outer本身没有tree字段；
只从已冻结真实index及本地Git对象核其tree，不反写旧outer的source。
整包新query源码及manifest独立固定新SHA；实际PG1/PG2均以原`group_read_subject`
核当前A身份、唯一群、原成功任务、report与完整ready模板，不接受操作者输入task/report。
旧群两结果必须恰一REJECT_ZERO_VERIFIED/0项及一SUCCESS20_VERIFIED/20项，
真实清理回执须容器/网络0、端口关闭、保卷；hash/source/tree/模式/结果数量不符均HOLD。
Owned的predecessor仅是该独立旧源码冷进程在新owned DB产生的原生合成fixture，
必须保存实际SQL、20项Base验证、原source/tree、模块来源、原生退出与清理，
不冒充真实平台群Gate，不借用旧SHA的通过代签新query。

新profile仅沿原read parent/entry/helper接线，Gateway显式唯一group、workflows0、
callbacks4、期限≤600秒；普通300秒/callback2分支保持。原不可变claim需包含精确
callbacks/group/expiry，跨PG saved-selection再核同一claim。parser、receiver、业务状态机、
迁移和权限不改。四槽为旧合法两条重投加新两条；receiver在message_id去重前计数，
到四次只拒绝后续admission，不主动终止SDK。父进程仍按原expiry提前10秒停止，
selector必须在该停止前运行，并保存父子存活及无termination_confirmed的实际回执。

两新文本只在原文法允许处加入固定内部空格：`查询任务 {task_id} 进度`及
`解释任务 {task_id} 的报告 {report_id}`。原PG规范subject经过固定投影后重新算原
`facts_hash(text)`（JSON字符串规范hash），PG2及arm时同样投影并严格比较；不换业务对象。
旧无空格文本继续HOLD，不重发/恢复。collector按原inbox/message_id/text hash区分新两条、
旧未选和unknown，保留全部记录；只向两条新且唯一、pending/attempt0的carrier派生原disabled
模板，发送仍用原ReadReplyWindow/Worker/Factory/once。多条、缺项、消费或unknown即HOLD。

以接收PG1开始为T，固定时间如下；不续窗、不改变旧profile。

| 动作 | 相对T秒 |
|---|---:|
| parent最早启动／最晚确认once | -300 / -180 |
| PG1开始／preflight截止 | 0 / 30 |
| Gateway启动 | 60 |
| Root实际ready工具返回后另读时钟最晚 | 270 |
| 通知实际返回最晚 | 360 |
| 真人发送截止 | 600 |
| 原生selector最晚 | 630 |
| Gateway停止/reap确认最晚（原父650起停） | 660 |
| PG1清理开始最晚／硬截止 | 720 / 900 |
| PG2开始／preflight截止 | 900 / 930 |
| sender1 / sender2启动 | 960 / 1080 |
| 两sender expiry与全局SDK截止 | 1260 |
| PG2清理开始最晚／硬截止 | 1320 / 1500 |

Root必须基于工具返回后的实际新时钟判断≥330秒余量（240真人＋90发布），
不能用ready工具开始时返回的旧剩余秒数。通知实际开始/返回先持久保存再验收，
开始≤T+270、返回≤T+360且保留≥240秒；缺失、迟到、Gateway异常均HOLD。
Root GO后的首工具直接启动已预核父入口，最晚T-180确认once；不在GO后重做hash检查而错窗。

一新owned45分钟窗口须Root另行绑定同owner/资源/具体UTC后才能启动。
固定阶段8分钟fixture/schema/roles/旧origin封存（含其停库）、5分钟父入口提前驻留、
25分钟完整PG1+PG2、3分钟核收、4分钟最终独立清理；冷重放在PG2内，无第三个验证PG窗。
fixture不能在8分钟内原生完成就HOLD；容量未实测，历史24分38秒群包不签本新查询链。
Fake仅owned最底层HTTP/WS；SQL/低权、claim/selector、SDK ledger/once、父子退出及保卷清理真实。

真实query PG总cap3已用1，后续接收≤900、回复≤600，各180秒清理。
已用SDK103/9窗口保留；本两回复auth2/bot2/IM2≤6，累计最多109≤114；
Create/Update/Base/model/history0。实际原库/Secret/SDK/真人仍须原独审、同源owned、
新功能精确CI、Root具体对象/UTC及fresh A readiness，不因本段合同自动开放。

旧566 PG节点及read-parent11=6+5不减少；新增必要节点独立collect并核两线并集/交集。
Hosted五jobs与既有容量/300秒命令/清理合同不变。当前功能精确CI是premerge第6/7次，
Root审核后另释放；最后premerge第7次与postmain一次保留，失败不自动重试。
源码自检只签实际离线范围，owned、真实、冻结独审、精确CI/main/Issue闭合均按实际回执另记。
