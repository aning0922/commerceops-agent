# eb30范围缺口与最小验收边界

2026-11-04（台北）。基于冻结source `eb30d7b7ad26da95dcf1c03ea55c5b424fbd536d`、tree `c4283496c3546169e4f24037731aa0fea949eb9e`的只读范围审计。Root随后明确接受“批量标记未交付”和“真实业务移动端证据不足”为本阶段必须补齐的缺口，不静默延期、不标六卡complete；当前r8保持原案，后续修复/专项用新冻结与新证据。本文件记录依据和必要边界，不改原合同、不授权代码或资源，具体增量由Root另冻结后交唯一owner。

## 精确依据与当前缺口

原包根为 `/Users/aipuli/Downloads/CommerceOps_V4_Codex_Development_Package`。已将PRODUCT_SCOPE、TASK_CARDS、PHASE_ROADMAP及TEST_AND_ACCEPTANCE与冻结PACKAGE_MANIFEST_OBSERVED逐项核hash。PRODUCT_SCOPE.json摘要 `529ac5775cadf9af6864eab1f6565a9346c1880ada0c40708f553a93e35a0da9`，TASK_CARDS.json摘要 `7aa2da8c979fcd35d3746e01b3c64db569767745e7b9377dc2c5fb087e137440`；TASK_CARDS.md摘要 `b39f1c893f98f9f195e97b1207c93752967aa87031f987b2bf4cdad91bf51a03`。原PRODUCT_SCOPE:1–8为planning_only，01/04/05模块目标V4-1共6+7+6=19项；241–242列V4-F04-06批量标记。FEATURE_REUSE_MATRIX:497–511仍为批量标记/租户隔离缺口、NOT_ESTABLISHED，不能宣称19项全完。

原TASK_CARDS.md:24–25、PHASE_ROADMAP:32–34及冻结STAGE_SPEC:10–12要求商品订单受控编辑、列表/详情及管理UI；V41-1f CONTRACTS:31,39只冻结单UUID tags/fulfillment与三种operation，未定义批量事务。UI_SLICE_01:3,13,17只是首片Shell和后续业务接线边界，不构成批量排除或单对象等价替代。eb30 business-pending.tsx:67–71无多选/批量入口，SetProductTags及ActionReceipt保持单对象版本与resource_id。历史判断“当前实施合同未覆盖”不是已获准延期；Root此次明确将该未交付项纳入补齐，旧规划与缺口事实保留。

原TASK_CARDS.json:126–137的V41-05 Gate明写移动端；STAGE_SPEC:34–36要求真实API/PG/Web与1440/1280/390；CONTRACTS采纳的API_PLAN:150明确1440/390下列表/详情/标签/履约/导入。eb30 business.live.spec.ts:27只有1440；Shell:149–176导航循环后在当前设置页做三宽菜单/助手截图，不能代业务390。已核R6 Mock报告WEB_3342968_R6:13只证明390/1440商品drawer焦点/Esc，:18明确业务Mock、真实API/PG未跑且截图关闭，:24排除最终真实产品视觉/阶段验收。原生200%也不替代390 viewport。

## 批量最小边界及必须防止的错误

沿Root拟定范围，只对当前已授权商品页显式选择的去重product IDs操作，不扩为全查询、跨页或全店；不新增backend/schema/API/operation。确认时冻结所选对象、各自版本、当前店/身份、列表revision和统一规范标签，明确复用SetProductTags的**完整替换**语义（空集合即清标签），展示选中数量及逐项生效、可部分成功、无全批原子承诺。不得把“批量标记”暗示为追加标签或后端原子批处理。

CONTRACTS:17,23规定新效果同时核expected_data_revision和expected_version；每次成功都会推进共享data_revision，不能将最初列表revision用于全部项，也不能在409后自动换版本重发。逐项发送前以当前权限GET核精确对象和所确认版本；revision衔接上一个**已核收receipt.after_revision**，出现非预期版本/数据变化即停并要求新确认。只有原COMMITTED回执、fresh同身份/店铺/对象读回、after_revision、资源版本和目标标签一致后，才能计成功并进入下一项。未知回执或读回不完整不得清pending或放行下一项。

eb30 demo.tsx:177–195的businessWrite读取React detail闭包，返回void且catch只写待核对消息；不能直接for-await循环它并把Promise完成当逐项成功。应由WEB在原单对象reserve/dispatch/settle边界内窄复用，向批量协调者返回明确已核成功/明确拒绝/UNKNOWN/已中止结果，避免重复写前一个详情对象。原v41-pending.mjs:25–64的写前存储/回读确认、当前operator及严格receipt/resource核验、UNKNOWN不清除必须保持；一个时刻只允许一个持久pending和一个发送，不能覆盖前项未决key或存储自动恢复队列。

首个UNKNOWN/401/403/409或其他不能证明成功的结果即停止后续；refresh/关闭/导航/切店/身份变化/reset/logout/hidden/offline立即撤销本次运行许可，所有await返回和下一次发前重核。原已发POST不因Abort或关闭被当作回滚，原key继续只读核对；迟到响应和恢复后的COMMITTED也不能自动复活剩余队列。用户改变筛选/排序/页码必须清当前页选择并中止当前批次，不隐式扩大选择。正常同身份轮询和本批预期读回不产生新确认或新POST。保留原控制按钮阻断，不借批量绕过pending。结果分已核成功、明确拒绝、待核对、未发送；UNKNOWN不归失败，不给含未决项批次显示全完成。

## 最小验收，不扩成新阶段

- **批量正常链**：至少两个当前页对象，真实串行单对象请求，各自写前原key持久；第二项使用正确revision衔接，逐项receipt/详情/标签读回一致，已选集合之外写入0。标签替换/清空、选中数量和部分成功文案准确；旧单对象标签与原pending恢复继续可用。
- **首错与中止**：必要纯/fixture覆盖中途UNKNOWN、401/403/资源或revision409、存储失败、在飞期间关闭/切店及迟到ACK。首错后剩余POST0；未决key不换、不重发、不被后项覆盖；恢复GET不自动继续。原越权/跨店/幂等与后台CAS不放宽，真实专项保留可核请求/回执与本案效果证据，不重复无关矩阵。
- **真实业务手机**：390下商品/订单列表、详情、标签确认、既有履约/关联及CSV导入表单按原六卡路径实际操作；CSV选择/映射/预览/确认入口不能只靠空表单截图，沿已冻结导入闭环核真实响应与回读。当前权限空态、局部表格滚动、抽屉焦点/Esc/关闭回列表及关键控件不遮挡须有实际证据。
- **布局证据**：同冻结组合补390及1280/1440相应业务列表、详情/操作与导入表单的可读布局截图，记录viewport/source/真实API来源及视觉判断；复用同一流程分段取证，不要求把全部后端安全矩阵按每个宽度重跑。Shell旧三宽、Mock旧交互及原生200%各自保留边界，不能互相顶替；未跑r8不得预填通过。

WEB仅在Root新冻结路径内实现；QA真实spec由独立唯一owner处理。新代码须精确源码独审与受影响验证，再依Root资源窗口取得真实手机/批量证据；当前工程、PG、browser不同source分账。本Reviewer没有修改任何业务/合同/测试代码，没有执行资源或读取QA WIP、旧Cookie/private；本次仅此范围缺口文档普通冻结。

## bdafd0d补充合同及ef0ae74窄修核收

2026-11-04。结论：`ADDENDUM_ACCEPTED / PENDING_CLOSURE_P2_CLOSED`，仅方案合同层。原补充合同提交 `bdafd0d94f83a26a209835f93687e9adbcd56c58`、tree `b2d8e7dfe4740ddf03b8234d5512c7062ca6840b`只新增BATCH_AND_MOBILE_ADDENDUM.md；随后 `ef0ae74906f424073ace07bec0bd93c5d69fd9e1`、tree `b02faa1f87010a7f8e84b5596c57c90b94205312`直接继承bdafd0d，唯一修改第15段一行，其他条款保持。

原第15段引用并不存在的“原严格COMMITTED/REJECTED清除路径”，曾作为窄P2保留：现v41-pending.mjs的finish仅在COMMITTED回执及fresh读回核验后移除，ActionLookup仅COMMITTED/UNKNOWN。ef0ae74现明确REJECTED仅用于显示并停止，已reserve pending只准原严格COMMITTED闭合后清除，不新增REJECTED释放；UNKNOWN/无回执不证明未提交，发送前未reserve/dispatch的本地拒绝才记未发送，原键恢复后不自动续批。与现accepted pending库边界一致，该P2关闭。

其余合同已将本报告必要边界落为当前页IDs/版本/标签完整替换、单写锁与显式单项结果、逐项revision衔接、首错停、run token撤销/迟到拒绝、部分成功分账及原pending控制阻断；明确WEB/QA单owner、未释放accepted pending库改动。真实手机与桌面业务Gate、原两标题/workers1/retries0/240秒及原offline/hidden/Native/lateACK保持，真实请求/journal/effect动态核算，不硬填旧数量。未发现其他实质合同漏洞；不保证原240秒内新增全链必然有容量，实际不足仍按原失败边界处理，不自动延长。

本次只在原范围文档追加精确合同接受段，原5ca7b6dc8f66ab8a3c453bf1482a10054e8178ed及其历史判断不覆盖、不amend。未读WEB/QA WIP、未改实现/合同、未运行测试或服务；批量与移动端的实现、真实Gate及六卡complete仍待各自精确源码和实际证据，合同接受不代签。
