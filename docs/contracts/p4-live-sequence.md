# P4真实窗口候选固定fixture/唯一open pool顺序

本文仅稳定合同/离线证据，actual平台0；用户新15列表仍待，旧P1 Probe表不得代替。真实SDK启动、表schema/资源验证、真人、method caps/整个窗口须Root另核。M1DemoFactory为test-only，不使生产CLI新增fixture选择平台。

## 固定数据与贯穿来源

tests/p4_demo_factory.py::M1DemoFactory严格复用既有tests/e2e/web/live_item_worker.py::twenty（不改其字节）：inventory-v1/baseline选择p3b02-owned-20，全部20SKU/每项Q100/总2000，最后1SKU在途null及完整专用假设确认；其余原manifest case走原MockCollectorFactory。P2 analysis、T2 plan和T4 fresh revalidation必须注入同一个factory，不能P2单SKU/T4突然20或仅改卡片。runtime注入完整PG证据待，当前2pure只核逐SKU完整report等于原twenty、20×100与单unknown、原known_inbound单SKUQ70及池集合不交叉，不能写平台已真发20卡。早期计划误记Q50，实际纯报告及既有goldens.known_inbound均Q70，保持原规则与fixture，不按计划猜数改金标。

每张正式卡由原frozen content/hash renderer全部逐SKU披露来源/窗口/数量/期限/hash/完整unknown集合；没有预览截断或技术probe。普通批准与联合确认动作复用原T3 DTO；未知必须联合本版本完整集合，不能普通approve绕过。Mock和simulated_feishu/Web与真人审批分层，P2旧实际解释/usage只沿原绑定来源读取，新任务不得伪造新模型选择。

## 同店有限顺序

1. 私聊known_inbound：新task/P2报告/P3计划/nonce，普通批准1项Q70，正式Base create+完整15字段唯一读回。T6 close该项并update/readback，保原execution/approval/task终态，不改库存。
2. 需要unknown拒绝证据时，群@baseline/twenty先新计划，明确reject_assumptions→rejected，0执行/0items/0Basecreate；其本身不占open pool。再新完整请求/new键用于群成功计划，不续答或热重算。
3. 群@baseline/twenty成功计划全部20项/完整集合联合确认，1永久T4/20items/Base20。approve/reject冲突和10重复尽量在同已决计划验证原回执或DECISION_CONFLICT，不另建同pool成功计划。纯/PG重投不是平台真人十次证据。
4. T6 complete群成功计划一项，version2/update/readback；其余19仍open不得同baseline再T4。AC11可从completed任务进入空新周期草稿，用户显式选择已关闭私聊池的known_inbound、新parameters/newkey，产生全新P2+P3/计划/nonce/报告，Base新1项。不得复制原plan/hash/nonce/ack/旧report或复活旧execution。

若真实race先reject，0items后可新完整group请求；若先approve，成功20即该group闭环，不再追加同baseline成功批。若Root要求两批都20，必须先T6终态第一全部20，成本40create+20update/至少120完整单页list要单独冻结；未经重新核cap不选择此方案。不新增shop/成员，不用不同stock_pool伪绕原唯一open约束。

## 容量与未知

最小私聊1+群20闭环21create/2update，单页假设至少46list（每写前后），含AC11第三known周期22create/2update/至少48list；每额外诊断/页/known拒绝retry/reconcile仍计原真实method上限。IM按每计划approval+最终result计算4或6create，拒绝计划及澄清/T6额外通知必须另列，不悄然扩cap。

v1create外成功而PG未知后即使T6已有v2，先以原UUID/完整v1快照只读reconcile，完整唯一verified v1才建立稳定record锚；v1观察不宣当前v2synced。再原v2 outbox UUID在同record受控update+全15读回。原快照/target/item/原键/unknown标记永久保留，unknown任何年龄不回pending/盲create；缺锚/不完整/冲突/remote更高版本安全hold/attention，不回滚内部items。IM超过1h原未知也不换UUID重发。实际平台资源/有界注入仍待Root源码Gate后，不以本合同替实证。
