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
