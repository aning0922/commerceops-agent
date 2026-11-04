# V4.1 本地演示流程

状态：**LOCAL_STAGE_GATE_ACCEPTED**。当前代码为
`261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e` / tree `34da95131e04d7360ea8aa5250ea40215bcb0713`。
同源受影响检查235 Python、74 Node、Native40组件、TS及Mock33已通过；Root转交r10实际
parent/probe0、两spec通过、consumer11 keys/10 mobile keys/32业务PNG、最终SQL命令0及独立关闭。
Main运行/SQL/closure已由4e4741ad正式独审核收。AI视觉审查 `c7f508dc596878a327fbc8e175b4e9b369f538a6`
实际逐张查看40原图并核hash/IHDR，图片范围内无P1/P2；人工视觉审批NOT_RUN。

**所有临时服务已关闭，没有持续有效演示URL，产品未发布。** 以下步骤只在Root新授权owned案
建立、readiness与端口归属核准后使用该案实际URL。具体程序与资源/清理要求见
[本地复现说明](../../v4-1/proposals/LOCAL_DEMO_REPRODUCTION.md)，不能重开旧窗口、once、身份或卷。

1. **经营指标/规则/钻取**：从 `/v4` 建立演示空间，选择已授权店铺，打开 `/v4/dashboard`。
   核币种/时区/期间/来源，切换期间，从指标进入 `/v4/dashboard/drilldown`。
   `/v4/insights` 是确定性规则，模型未启用；未知支付时间、成本与库存保持未知，不造毛利或结算。
2. **商品与当前页批量标签**：在 `/v4/products` 搜索/筛选/分页，从当前返回对象进入详情。
   单项标签仅完整替换。批量先显式选择本页至少两个不同商品，再核选中数、ID/version和目标标签；
   空集合即清空，不是只追加。每项串行以原key发送，只有COMMITTED回执与同身份fresh详情的
   version/revision/标签闭合才计成功并进入下一项。结果分别显示成功、明确拒绝、待核、未发送。
3. **停止与核对**：UNKNOWN、存储/读回失败、401/403/409或关闭/切页/切店/切角色/hidden/offline
   均停止后续项。已发请求不因Abort回滚；COMMITTED后读回拒绝仍待核并保留原pending。
   只读核对原operation/key，不换键重发；核成COMMITTED也不自动续批，必须重读本页、重选和确认。
4. **订单与演示履约**：在 `/v4/orders` 筛选并打开实际UUID详情，核商品关联与已知时间线；
   仅有已记录支付时间的订单可确认演示履约。`/v4/orders/anomalies` 仅支付时间未知筛选，
   不是持久异常标记；履约不改钱、库存或真实Woo物流。
5. **CSV/XLSX**：在 `/v4/products/import` 分别使用合成小文件，映射SKU/名称/价格/币种，核质量
   后显式确认。按唯一SKU读回job/version/来源及商品相关指标；preview不等于已导入。
   支持受限单sheet XLSX，不以改扩展名代替格式；CSV导出核同scope/筛选与实际bytes。
6. **移动布局/缩放**：真实浏览器分别操作1440/1280/390商品列表/详情/标签和批量确认、订单
   列表/详情/履约、CSV/XLSX映射及读回。390表右侧列需要横向滚动，静态图不能证明其发现性。
   390 viewport不是真机硬件或touch测试；Native200核同案原生zoom及截图，不用CSS模拟。

本期14导航是范围入口，12业务视图不是规划全部66页已交付；99原功能中仅19阶段项在受控合同内
评估，其他80未重评，不声明原19/19或99/99完整覆盖。阶段实现/运行不等于真实模型、平台或生产。

原4fec完整工程4601、e7严格FullPG773和54ab四HTTP案仍保持原来源；当前261只拥有其自己的
受影响与实际浏览器证据。r9 parent失败、r8 Native失败、Mock r1–r3失败均保留；最新通过不回写旧案。
截图40=32业务+3Shell+5Native，支持该组页面/状态，不推导全部12/66页面每个状态均已验。
详见 [风险](RISKS.md)、[功能状态](FEATURE_STATUS.json) 与 [最终矩阵](../../v4-1/proposals/FINAL_GATE_MATRIX.md)。


本地阶段 **V41-01–06 已完成并核收**，仅限合成owned环境与原合同受控范围。最终runtime独审
`4e4741ad56e5ee8d3a22bc9f4ac6564715d92955` / tree `85f0293eb07d3d648949df47674d7965c6294f18`，
[正式原件审查](https://github.com/aning0922/commerceops-agent/blob/4e4741ad56e5ee8d3a22bc9f4ac6564715d92955/docs/v4/v4-1/reviews/FINAL_RUNTIME_R10.md)采用该文件后续“完整实际运行追加核收”段；早期build-only/pending原文保留其时点。
r10同261/imagee834：2spec、11keys（10mobile子集）、4preview、7receipt/event、26当前effects及
2个历史替换tag分记，最终SQL0；source/tools与唯一允许next-env生成差异已核。原API清理130、
execution summary NOT_WRITTEN、Native browser exit NOT_EXPOSED、human审批NOT_RUN不改写。
旧4fec Full/e7 FullPG/54ab HTTP继续只属各自SHA；阶段接受不等于99功能、66页面、真机触摸、
外部业务、Hosted或生产发布通过，V4-2 NOT_STARTED。
