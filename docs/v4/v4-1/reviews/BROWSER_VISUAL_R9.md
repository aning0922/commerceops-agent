# V4-1 r9 原图 AI 工程视觉审查

## 范围和结论

本审查逐张使用 `view_image` 查看 r9 清单中 40 张原始 PNG：业务 32、shell 3、原生缩放 5。清单绑定源码 `fbb29a429b7f680328ab4451a717adb3ad2d99c1`，tree `ef6d8230ac4b58401af2771d722064aadacc5eed`；40 个路径互异，按清单核对文件 SHA-256 和 PNG 尺寸均一致。原图与完整哈希留在 r9 私有证据清单 `ACTUAL_PNGS.json`；下表使用该清单的相对文件名，避免复制原始数据。

**结论：原生 200% 视觉证据不足，不能签通过。** 两张顶部图仅覆盖放大的页首及演示空间，右侧文字截断；商品底部图全为空白。100% 两图可见正常页面区域，但不能替代 200% 内容。原生回执中 100% innerWidth 1440 / DPR 2 / PNG 2880×1826，200% innerWidth 720 / DPR 4 / PNG 1440×912；采集代码使用 `page.screenshot` 的 `fullPage: false`、`scale: device`，底部截图前对末行执行 `scrollIntoViewIfNeeded`。这些事实提示需要调查截图范围与缩放的关系，但不能据此排除产品布局问题或认定根因。需要修复采证或产品问题、在授权窗口取得可审的原生截图并重新视觉审查。

移动端商品、订单和导入预览表的若干右侧列未出现在静态图中，截图本身不能证明横向滚动是否可发现或可操作；需要在另行授权的交互验证中核查。其余下表只描述可见状态，不等于对图外内容、功能、键盘、无障碍或视觉一致性的完整通过。

这是 AI 工程视觉审查，**人工视觉审查 NOT_RUN**。r9 两个实际业务 spec PASS 与 40 张图片存在，不改变父收验因 ValueError 失败的事实；该包不是最终阶段验收。未启动浏览器、服务、数据库或新运行，也未改动产品。

## 逐图观察

表中 `390`、`1280`、`1440` 为文件名中的视口标识；原生图片以实际像素尺寸另列。可见确认/回读文字仅为截图所示，不能独立证明后端写入或交互完成。

| 原图（相对 r9 证据目录） | 可见状态与限制 |
| --- | --- |
| browser-business/anonymous_empty-390.png | 未选择授权店铺的空列表与体验入口可见；表格右侧未完整展示。 |
| browser-business/batch_confirm-390.png | 已选两项的批量替换确认框、输入和取消/确认按钮可见；背景表格右侧被截。 |
| browser-business/batch_readback-390.png | 列表恢复且显示八项，未见批量标签列；不能仅凭此图验证各项标签。 |
| browser-business/csv_mapping-1280.png | CSV 已发现预览、映射控件和样本表可见；映射尚未选择。 |
| browser-business/csv_mapping-1440.png | 同一 CSV 预览在宽视口展示，样本列可见；映射尚未选择。 |
| browser-business/csv_mapping-390.png | 映射控件纵向排列；样本表右侧列不在画面内。 |
| browser-business/csv_readback-390.png | 搜索结果显示一项 CSV 商品；SKU 行右端被截。 |
| browser-business/fulfillment_confirm-1280.png | 订单侧栏显示未履约、演示限制和取消/确认按钮。 |
| browser-business/fulfillment_confirm-1440.png | 宽屏订单侧栏确认状态、说明和两个按钮可见。 |
| browser-business/fulfillment_confirm-390.png | 移动宽度订单侧栏确认状态与按钮可见。 |
| browser-business/fulfillment_readback-390.png | 显示已核对提示、演示已履约及禁用状态按钮。 |
| browser-business/order_detail-1280.png | 订单详情侧栏、时间线及标记演示履约按钮可见。 |
| browser-business/order_detail-1440.png | 订单详情宽屏侧栏和关闭控件可见。 |
| browser-business/order_detail-390.png | 移动宽度订单详情、关闭控件和履约按钮可见。 |
| browser-business/order_list-1280.png | 订单筛选和七条记录可见，包括支付时间未知状态。 |
| browser-business/order_list-1440.png | 宽屏订单表与筛选项可见，未见明显表格截断。 |
| browser-business/order_list-390.png | 筛选纵向排列，订单表右侧支付及后续列未完整展示。 |
| browser-business/product_detail-1280.png | 商品详情侧栏展示标签、两个规格、关联订单和编辑按钮。 |
| browser-business/product_detail-1440.png | 宽屏商品详情与关联订单链接可见。 |
| browser-business/product_detail-390.png | 移动宽度商品详情、规格和编辑入口可见。 |
| browser-business/product_list-1280.png | 商品筛选与八项商品表、标签及来源列可见。 |
| browser-business/product_list-1440.png | 宽屏八项商品表与各列可见。 |
| browser-business/product_list-390.png | 八项商品列表可见；SKU 内容及右侧列在画面边缘被截。 |
| browser-business/second_visitor_empty-390.png | 第二访客对应截图显示选择店铺空状态；图片本身不证明会话隔离。 |
| browser-business/tag_edit-1280.png | 标签编辑输入、待保存值及取消/保存按钮可见。 |
| browser-business/tag_edit-1440.png | 宽屏详情中标签编辑区和按钮可见。 |
| browser-business/tag_edit-390.png | 移动宽度标签编辑区与按钮可见。 |
| browser-business/tag_readback-390.png | 已核对提示及更新后的标签文本可见。 |
| browser-business/xlsx_mapping-1280.png | XLSX 已发现一行样本，映射尚未选择，样本各列可见。 |
| browser-business/xlsx_mapping-1440.png | 宽屏 XLSX 映射与一行样本可见。 |
| browser-business/xlsx_mapping-390.png | 映射控件纵向排列；样本价格、币种列未在画面中展示。 |
| browser-business/xlsx_readback-390.png | 搜索显示一项 XLSX 商品、规格价格及库存未知。 |
| browser-shell/shell-1280.png | 演示设置页、桌面侧栏及六张规划中场景卡可见。 |
| browser-shell/shell-1440.png | 桌面宽屏演示设置和六张场景卡可见。 |
| browser-shell/shell-390.png | 移动页首、演示设置及纵向排列的六张场景卡可见。 |
| native-zoom/screenshots/dashboard-100.png | 2880×1826；桌面导航、演示空间、驾驶舱筛选和部分指标可见。 |
| native-zoom/screenshots/dashboard-200.png | 1440×912；仅见放大的页首和演示空间上部，右侧文字被截，指标未见。 |
| native-zoom/screenshots/products-100.png | 2880×1826；桌面导航、演示空间及商品筛选和表头可见。 |
| native-zoom/screenshots/products-200-bottom.png | 1440×912；整图浅色背景，无商品表或其他可读内容。 |
| native-zoom/screenshots/products-200.png | 1440×912；仅见放大的页首和演示空间上部，右侧文字被截，商品表未见。 |
