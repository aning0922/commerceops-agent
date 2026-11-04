# V41 当前页批量标签源码独审

日期：2026-11-04（台北）。结论：`HOLD_ONE_P2_POST_READBACK_OUTCOME_CLASSIFICATION`。精确候选存在一项结果分类P2，修正后须重新冻结独审；不签Mock、真实browser或批量提交验收。本轮没有修改作者实现。

source `a7e5f9ff4b53a956390c0807c3efcad135c9047a` / tree `330b21d4ef7707b1a10bf493dc25b9fa76670961`，父 `bdafd0d94f83a26a209835f93687e9adbcd56c58`。六路径182+/29-，仅demo.tsx、business-pending.tsx/CSS、batch-tags helper/type/test。合同按澄清后 `ef0ae74906f424073ace07bec0bd93c5d69fd9e1` 的BATCH_AND_MOBILE_ADDENDUM.md，以及 `a66cb978ddf5a712d0cd54ee05ef387ca78b48a9` 的合同核收解释；不沿用bdafd旧REJECTED清pending措辞。

## P2：POST已返回提交结果后的读回拒绝被误记为写入拒绝

位置：精确候选 `frontend/components/v4/demo.tsx:194–202`，尤其202行的共同catch；结果消费在 `frontend/lib/v41-batch-tags.mjs:27`。

`performBusinessWrite`把POST和`settleWrite`的fresh GET放在同一try内，统一按任意 `V41Error.outcome==='REJECTED'` 返回rejected。若POST已经返回合法COMMITTED结果，随后详情GET因上下文冲突等返回明确REJECTED，该错误只说明读回被拒绝，不能证明原写入被拒绝。当前协调者却把pending减一、rejected加一，在原scope仍active时显示“明确拒绝1、待核对0”；存储内原pending仍存在，因而进度与原键事实矛盾。此处不报告pending被清除、重复POST或后项继续：本次复现均未发生。

独立纯复现提取精确demo中的 `settleWrite` 与 `performBusinessWrite` 原函数，搭配原 `applyBatchTags`、实际reserve/load pending及内存存储；仅用受控传输替身返回严格Ajv通过的完整COMMITTED ActionResult，再在fresh GET抛出 `V41Error(409,'REJECTED',...)`。两项目标实际调用计数POST1/GET1，结果 `{success:0,rejected:1,pending:0,unsent:1}`，实际存储仍pending。正确分类应为 `{success:0,rejected:0,pending:1,unsent:1}`，保留原键只读核对。该409是组件反例，不声称真实后端已发生此响应或真实提交。

**最小修改**：在原单项执行函数内区分POST失败与POST之后的闭合失败；只允许POST本身明确REJECTED返回rejected。一旦已有POST结果，后续fresh session/资源读取、标签/receipt/version/revision核对或pending闭合的失败均保持unknown/待核对并首停，不新增pending清除路径，不自动重发或续批。补一个执行实际单项函数的“COMMITTED POST→读回REJECTED”负例，并保留“POST直接REJECTED”与正常COMMITTED闭合的区别；无需修改accepted pending/context库或后端。

## 已核其他关键路径

当前页选择通过实际页items限定去重ID/version，空选、重复ID、页外ID和非法标签拒绝；确认时冻结targets、初始revision、标签副本、runShop和query，语义明确完整替换/空集清空。整段共享writeLock，原单对象入口复用显式target执行函数，没有循环依赖detail闭包或把void完成当成功。

每项先refresh(run)及operator检查，再独立recoveryGate ticket读取精确对象、冻结version和预期revision；第一项用确认页revision，下一项仅接已核success的after_revision。原key写前reserve/readback保持，严格POST和fresh回读经原finishV41Pending核身份/对象/版本/revision，另核目标标签集合；UNKNOWN/不闭合不进入下一项。REJECTED本身也未新增清pending代码。

关闭、正常外部refresh、路由/店铺/查询/分页变化及clear路径撤销batch token；active同时核token/query/身份/店铺/hidden/offline，下一POST前、读回后和publish前检查。内部refresh(run)不续外部已撤token；恢复入口仍仅原key只读查询，无批次持久队列或恢复后续行。已发项在取消后不被宣称回滚，原pending控制阻断保持。此为源码核对，不证明真实React/浏览器竞争已通过；本次P2以外未发现新的实质阻断。

## 验证与限制

新review-owned精确Git archive目录 `/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/v41-a7-review-_j2cryvj`。原batch-tags.test.mjs独立8/8通过、native0，约126ms；它主要测试helper及pending原语，未覆盖上述实际单项函数共同catch。独立函数复现及严格DTO强化版均native0确认反例；严格版 `review-post-readback-strict.mjs` SHA256 `2b582997396d0408eee631aa96b987c10be1b22d3ad3fb4fe5c88070aaf33f5b`。

首次临时archive未链接依赖，复现和原test均在导入ajv时ERR_MODULE_NOT_FOUND/native1，断言未执行；其后仅在该临时树链接现有WEB node_modules，未安装或改变依赖，才取得上述结果。Node stripTypeScriptTypes实验性提示保留。作者74项/TS/preflight是转交结果，不与本轮8项混计，也不以它覆盖此新P2。

未读WEB新Mock WIP、QA WIP或private auth；未启动浏览器、服务、PG、Docker、build、网络、Full或CI。仅此独立审查文档经指定changed-file/index预检后普通冻结，不push；所有此前review提交保留。

## Root要求的其余实际闭包补核

原分类P2仍HOLD，未读修复WIP。继续从同a7精确源码提取refresh原函数及settleWrite/performBusinessWrite/businessWrite/batchTags，使用原createV41Gate、guardV41Request、scoped storage及reserve/finish pending实现，React setters与API传输为资源无关替身；不是只测试新applyBatchTags helper。

8个独立场景native0：正常两项取得2 POST/4详情GET、独立key、revision1→2接续、最终success2/pending空；refresh期间取消与pre-read期间取消均0 POST；POST返回期间取消仅1 POST且原pending保留、不送B；B的revision或version漂移均只有A的1 POST，A已核成功、B未发送；A标签读回不符为1 POST/pending1/不送B；写前存储拒绝为0 POST。每案写锁在整个函数区间保持，finally释放；对传输调用点断言原pending已持久存在。正常链使用原finish核收回执/版本/revision和标签，不把异步返回当成功。

脚本原件保留于同临时树 `review-batch-closure.mjs`，SHA256 `55ca4f2b9887e0c0a653a450faf78ccd620072889e9e32c7d7034fe18ab19028`；上述场景没有发现第二项实质产品源码阻断。它没有模拟React render/effect调度、DOM或真实HTTP/PG，不能替代后续Mock/真实browser。原 `review-post-readback.mjs` 与 `review-post-readback-strict.mjs` 均保留，原P2不因这8项通过而关闭。

Root另转交UI-review在4427 Mock发现原key lookup断言不足，已由另一owner负责修正。本轮未读该Mock候选或其WIP；本报告不对4427签noP2，不把该独立测试缺口合并为本产品源码P2已修。等待新冻结仅增量复核。

## cc5c9a6精确增量复审：产品分类P2关闭

2026-11-04（台北）。结论：`PRODUCT_P2_CLOSED_SOURCE_AND_BOUNDED_PURE_ONLY`。原a7发现与HOLD事实保留。修复 `cc5c9a6b3a361c2c451c5652023b9e73b5488f9d` / tree `28443dd17a32045e81c5a40ed1393dd1e724f456`，父 `4427f347206bf55250d847d3fffcf76051006d29`；后续仅Mock增量 `6960d5666ba4fd51215aa54bef16058aab566052` / tree `cd6b884b4d39e84baa2f1078ab6ce4d622ca0cb2` 的demo.tsx与cc5字节相同。相对已审a7，产品源码唯一增量是单项函数拆分POST和readback错误边界。

POST的try/catch独立，只有该调用自身的明确REJECTED返回rejected；收到结果后仍核active/ticket/status，settleWrite及成功闭合阶段任何异常都返回unknown。原false闭合、取消、标签核对、pending reserve/finish、scope、锁、revision接续和单项包装函数未放宽。未新增pending释放或重发。该修复准确解决原反例，不把readback拒绝改写为原写入拒绝。

在新review-owned精确696 archive目录 `/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/v41-cc5-review-jbe4kt91` 复用既有函数提取和原gate/pending复现，四个限定场景均native0：

- 严格DTO合法COMMITTED POST→fresh GET409：POST1/GET1，success0/rejected0/pending1/unsent1，原pending保留、不送B。
- 同链GET403：分类同上；此例隔离单项分类，guard副作用为替身，不冒充真实403清scope的UI结果。
- POST本身明确REJECTED：POST1/GET0，rejected1/pending计数0/unsent1，持久pending仍保留，符合已澄清合同。
- 原两项正常链：POST2/详情GET4、两独立key、revision接续、success2及pending严格闭合为空，写锁覆盖至finally。

仅只读cc5新增Mock的409/403案例覆盖意图：409检查待核对1/明确拒绝0；403保留旧scope清除而不复活进度；两者核一POST与原key保留。没有运行这些测试体，也不代UI-review审签696的lookup强化；动态collect33/4spec不是33PASS。作者TS/74Node/preflight仍为转交结果，本轮未重复全范围。原a7纯复现脚本及失败记录均保留。

本次产品源码P2关闭不等于Mock、真实batch/mobile/browser或阶段验收通过；这些Gate仍按后续实际source回执。无浏览器、服务、PG、build或网络启动，仅本文件追加结论，指定预检后普通冻结、不push。
