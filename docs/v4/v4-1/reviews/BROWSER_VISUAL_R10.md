# V4-1 r10 原图 AI 工程视觉审查

本次逐张通过 view_image 查看 r10 40 张原始 PNG（业务32、shell 3、原生缩放5），源码 `261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e`，tree `34da95131e04d7360ea8aa5250ea40215bcb0713`。逐个读取原字节核对清单 SHA-256、PNG IHDR 尺寸，40 个唯一路径均一致。下表尺寸为实际像素，哈希为完整清单对应值的前12位；完整哈希和路径保留在私有原始清单 ACTUAL_PNGS.json。

**图片范围内未发现 P1/P2 视觉阻断。** 原生200%两张顶部图显示完整横向视口内的演示空间，底部图可读商品末行、来源及分页；不再出现 r9 半幅采集与空白底图。顶部截图业务内容在视口下方，不据此声称已覆盖全部200%页面。390标签编辑、批量确认、履约确认和CSV/XLSX映射控件在图中可见；若干商品、订单及导入表右侧列不在静态图片可视范围，图片不能证明横向滚动的发现性、触摸操作或图外内容。

这是 AI 工程视觉审查，人工视觉审批 NOT_RUN；静态图不证明交互、键盘可用性、授权或生产行为。Root报告的r10 parent 0、两spec PASS、consumer/final SQL/driver cleanup是独立运行证据，独立资源闭合按Root核验状态为准。

| 原图（相对 r10 目录） | 像素 | SHA-256前12位 | 图中观察 |
| --- | --- | --- | --- |
| browser-business/anonymous_empty-390.png | 390×1877 | `bc3c2fe6113d` | 未选择授权店铺的空列表与体验入口可见；表格右侧未完整展示。 |
| browser-business/batch_confirm-390.png | 390×2346 | `be3c708bd3b6` | 已选两项的批量替换确认框、输入和取消/确认按钮可见；背景表格右侧被截。 |
| browser-business/batch_readback-390.png | 390×2346 | `da6c3e2e814a` | 列表恢复且显示八项，未见批量标签列；不能仅凭此图验证各项标签。 |
| browser-business/csv_mapping-1280.png | 1280×2621 | `ff23ef36f83d` | CSV 已发现预览、映射控件和样本表可见；映射尚未选择。 |
| browser-business/csv_mapping-1440.png | 1440×2621 | `7ea82ca672a5` | 同一 CSV 预览在宽视口展示，样本列可见；映射尚未选择。 |
| browser-business/csv_mapping-390.png | 390×2997 | `db525b126cc4` | 映射控件纵向排列；样本表右侧列不在画面内。 |
| browser-business/csv_readback-390.png | 390×1806 | `08c6903eba98` | 搜索结果显示一项 CSV 商品；SKU 行右端被截。 |
| browser-business/fulfillment_confirm-1280.png | 1280×900 | `b1e0323c905d` | 订单侧栏显示未履约、演示限制和取消/确认按钮。 |
| browser-business/fulfillment_confirm-1440.png | 1440×900 | `b23330296bd5` | 宽屏订单侧栏确认状态、说明和两个按钮可见。 |
| browser-business/fulfillment_confirm-390.png | 390×900 | `ddf956a6d2d4` | 移动宽度订单侧栏确认状态与按钮可见。 |
| browser-business/fulfillment_readback-390.png | 390×900 | `feee12b99117` | 显示已核对提示、演示已履约及禁用状态按钮。 |
| browser-business/order_detail-1280.png | 1280×900 | `3e624d79c49c` | 订单详情侧栏、时间线及标记演示履约按钮可见。 |
| browser-business/order_detail-1440.png | 1440×900 | `5f114c455eee` | 订单详情宽屏侧栏和关闭控件可见。 |
| browser-business/order_detail-390.png | 390×900 | `d0a12ae8611a` | 移动宽度订单详情、关闭控件和履约按钮可见。 |
| browser-business/order_list-1280.png | 1280×1465 | `c8aaa4acc3bc` | 订单筛选和七条记录可见，包括支付时间未知状态。 |
| browser-business/order_list-1440.png | 1440×1465 | `48ed83dfbf48` | 宽屏订单表与筛选项可见，未见明显表格截断。 |
| browser-business/order_list-390.png | 390×2283 | `ef999ab418c3` | 筛选纵向排列，订单表右侧支付及后续列未完整展示。 |
| browser-business/product_detail-1280.png | 1280×900 | `b8c0f68c268b` | 商品详情侧栏展示标签、两个规格、关联订单和编辑按钮。 |
| browser-business/product_detail-1440.png | 1440×900 | `1eb51813d11d` | 宽屏商品详情与关联订单链接可见。 |
| browser-business/product_detail-390.png | 390×900 | `cb2b02ce6410` | 移动宽度商品详情、规格和编辑入口可见。 |
| browser-business/product_list-1280.png | 1280×1695 | `7835d6405142` | 商品筛选与八项商品表、标签及来源列可见。 |
| browser-business/product_list-1440.png | 1440×1695 | `cdba16a44d7f` | 宽屏八项商品表与各列可见。 |
| browser-business/product_list-390.png | 390×2346 | `2ffe1e262c82` | 八项商品列表可见；SKU 内容及右侧列在画面边缘被截。 |
| browser-business/second_visitor_empty-390.png | 390×1877 | `bc3c2fe6113d` | 第二访客对应截图显示选择店铺空状态；图片本身不证明会话隔离。 |
| browser-business/tag_edit-1280.png | 1280×900 | `7127199ad934` | 标签编辑输入、待保存值及取消/保存按钮可见。 |
| browser-business/tag_edit-1440.png | 1440×900 | `02cb7f38f573` | 宽屏详情中标签编辑区和按钮可见。 |
| browser-business/tag_edit-390.png | 390×900 | `cf8abf4fb613` | 移动宽度标签编辑区与按钮可见。 |
| browser-business/tag_readback-390.png | 390×900 | `969b471079e5` | 已核对提示及更新后的标签文本可见。 |
| browser-business/xlsx_mapping-1280.png | 1280×1781 | `4e1a144b7f07` | XLSX 已发现一行样本，映射尚未选择，样本各列可见。 |
| browser-business/xlsx_mapping-1440.png | 1440×1781 | `eefd6470bf0a` | 宽屏 XLSX 映射与一行样本可见。 |
| browser-business/xlsx_mapping-390.png | 390×2158 | `9776dafc34fe` | 映射控件纵向排列；样本价格、币种列未在画面中展示。 |
| browser-business/xlsx_readback-390.png | 390×1806 | `9ee2266b5c32` | 搜索显示一项 XLSX 商品、规格价格及库存未知。 |
| browser-shell/shell-1280.png | 1280×931 | `03ff0d67eb90` | 演示设置页、桌面侧栏及六张规划中场景卡可见。 |
| browser-shell/shell-1440.png | 1440×931 | `d43bd1e0dda3` | 桌面宽屏演示设置和六张场景卡可见。 |
| browser-shell/shell-390.png | 390×1757 | `833ec3763c86` | 移动页首、演示设置及纵向排列的六张场景卡可见。 |
| native-zoom/screenshots/dashboard-100.png | 2880×1826 | `c3334c4eac14` | 2880×1826；桌面导航、演示空间、驾驶舱筛选和部分指标可见。 |
| native-zoom/screenshots/dashboard-200.png | 2880×1826 | `8e2b40d602e8` | 200% 顶部完整横向视口；页首与演示空间文字和控件可见，业务指标在视口下方。 |
| native-zoom/screenshots/products-100.png | 2880×1826 | `5adf628d84df` | 2880×1826；桌面导航、演示空间及商品筛选和表头可见。 |
| native-zoom/screenshots/products-200-bottom.png | 2880×1826 | `999fab5a49be` | 200% 底部可见商品末三行、SKU、标签、来源、分页及页脚；并非空白。 |
| native-zoom/screenshots/products-200.png | 2880×1826 | `f2e0e5650156` | 200% 顶部完整横向视口；页首与演示空间文字和控件可见，商品表在视口下方。 |
