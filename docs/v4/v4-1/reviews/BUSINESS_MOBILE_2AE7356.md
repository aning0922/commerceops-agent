# V41 真实业务移动首片源码独审

日期：2026-11-04（台北）。结论：`HOLD_ONE_P2_DISABLED_BATCH_TRIGGER_FOCUS_EXPECTATION`。本片有一项首次批量提交前的源码接口冲突，须最小修正后再冻结；未运行browser，不声称已观察实际超时或phone通过。

source `2ae73562effbabbee2092a1ff249fc43fe5f288c` / tree `6715747ab163a9524142f136e296b00d26df8ec2`，父 `bdafd0d94f83a26a209835f93687e9adbcd56c58`。唯一差分 `frontend/v41-e2e/business.live.spec.ts`，145+/12-。产品接口按冻结 `23f37fc` / tree `c7e6387c7641d35f709af618411b586ea5bd3231` 核对，未读QA Python WIP或父receipt新predicate候选。

## P2：取消清空选择后要求已禁用触发按钮获得焦点

spec精确126行在批量dialog按Escape后执行 `expect(batchButton).toBeFocused()`，127行随后又要求已选数量为0。冻结产品 `business-pending.tsx:58` 的closeBatch明确清selectedProducts，78行的“批量设置标签”按钮在selectedProducts为空时disabled。关闭modal的effect在该状态渲染后执行。取消后已禁用按钮不能成为可用的回焦目标；该断言与现产品状态相冲突，位于真正批量POST之前，会阻断后续业务验收。

独立纯检查直接提取23f37产品closeBatch及该按钮disabled表达式，模拟其状态更新：selected=0、batchOpen=false、stop调用1、batchButtonDisabled=true；同时确认2ae源码保留toBeFocused要求。仅证明源码状态冲突，不冒充浏览器DOM焦点实验或实际失败回执。

最小处理：保持Escape关闭、清选择及零POST断言，不要求disabled触发器获焦点；针对已批准的实际关闭后焦点行为作准确断言，并从可用列表控件正常重选/重新打开。若验收要求自动回到明确可聚焦控件，应由WEB独立实现稳定可用回焦目标后再由QA核验；不能为满足旧断言保留选择、启用无选中批量按钮，或用测试手动focus冒充产品自动回焦。Root按现合同确定该窄接口，不在本审查中改产品或测试。

## 其余源码核对

- 三宽views覆盖8类状态：product_list、product_detail、tag_edit、order_list、order_detail、fulfillment_confirm、CSV mapping、XLSX mapping；每类依序1440/1280/390，记录PNG字节hash/尺寸、viewport/DPR、route和来源引用。检查document/body无横向外溢，指定控件滚动至可见并核水平边界。该记录不等于人工视觉已验，也未证明截图期间未发生自动刷新；最终实际PNG与来源/当前状态仍需核收。非dialog mapping的tab_controls记录只表示执行了Tab动作，不应提升为完整键盘焦点顺序已验证。
- views末宽390之后，原首个单标签保存、履约确认及CSV/XLSX mapping/预览/confirm/来源读回均实际调用原UI操作、等待原Response并严格DTO/scope/key/version/revision核对；不是仅改viewport截图。第二个原单标签仍1440，保留最后v41-live-b隔离sentinel。新增读回截图不替代响应/原键事实。
- 批量仅最初授权商品页前两去重ID，UI全选/取消后明确重选两项；冻结页ID/version/初始revision记录，逐项核原不同key、完整标签、预期version/revision、回执资源/前后revision及fresh详情。按实际POST ordinal排序，核前项read.request startTime+responseEnd不晚于后项POST startTime；raw/read均finished=null。成功进度必须2/0/0/0且pending槽为空，POST增量严格等于selected数，不扩大scope或靠数量替代对象核验。
- pendingProof wrapper在既有route拦截放行前只读本tenant原namespaced pending，核五身份、shop/key、operation、revision及非preview资源/version；随后await原writer.operation。冻结live-business.fixture的dispatch确实await该writer成功后才route.continue，异常abort；原browser-subjects同步append执行file fsync与inode/dev/owner/mode/bound检查。没有以晚到的readback日志冒写前fsync，也没有额外POST或伪造响应。此为接线顺序核验，实际持久化/SQL对账待新案。
- CSV/XLSX保留发现→映射→原preview key lookup/job→confirm→dataset来源及SKU查询，CSV22行真实分页/集合/上页回读断言未删。记录operations按实际POST Request对象和key，最终与业务POST集合/pendingProofs/counts对应；mobile_keys是width390的原operations子集，没有第二次加算。effect_count缺字段时为null，不据此代签最终SQL一次效果。
- 初始及另一visitor空态明确标ANONYMOUS_ONLY_NOT_403_REVOKED，未冒撤权/403测试。原第二visitor/另一shop隔离保留。config、fixture、Shell均无差分，原14导航由Shell承担；两原标题、workers1/retries0/240秒及offline/hidden/Native/lateACK未削减。新增步骤是否能在原窗口内完成仍需实测，源码不保证容量。

## 本轮验证边界

新review-owned只读源码副本目录 `/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/v41-mobile-review-09h9g32q`，纯状态脚本 `review-mobile-boundaries.mjs` native0；另执行精确progressCounts的正常/重复标记拒绝检查。没有运行spec测试体、TS、collect、浏览器、服务、PG、build、网络或CI。父receipt与Native pin的后续新冻结仍需其独立review，不能以本片或未来r9名义预签。

仅新增此审查文档，经指定changed-file/index预检后普通冻结、不push；P2修正前不签本片source接受，旧各案和原P2历史保留。
