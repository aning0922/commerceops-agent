# V41 DTO修订与有效视图/KPI独立审查

日期：2026-11-04（台北）。source `b72331fa572d9d67ad176902283da721aeda4cf1`，tree `4abcec5376c4f2ce61cbacc7934dfccca134c0a0`。按62ab257→本提交差异及全部新增effective/analytics、测试、schema读取；未读作者WIP。

结论：ACCEPT_PURE_DTO_EFFECTIVE_KPI_SLICE；此前P2-A01/A02在本精确候选关闭。没有发现阻断此纯服务/DTO切片的新P1/P2。允许WEB消费修订的DTO/schema继续候选接线，不签运行API、权限、SQL或全V41通过。

## 两项修复核验

- ExportData具有Snapshot、固定csv格式/两个安全文件名、受限csv_text及0—500行数；生成器与实际API_CONTRACT.json的两个export响应均指向BusinessEnvelope_ExportData，transport改为JSON。此前Page100行/原CSV响应偏差已关闭。实际CSV转义、行数一致性和500行超限拒绝仍待服务实现。
- Snapshot改用DatasetSource，区分纯fixture与demo_mixed并含最多500条上传来源。SourceRef的上传对象强制job/row/file digest，fixture禁止这些上传字段；聚合检查fixture digest/snapshot一致并拒重复job-row。build_view对导入来源按job/row稳定排序，详情保留对象来源；已提交schema引用与源码一致。此前单来源模型无法表达多job的问题已关闭。

## 纯服务审查

build_view先核fixture digest并重新严格校验fixture，核所有效果scope一致、输入数量上限、商品/SKU标识冲突、canonical SKU冲突及币种；标签和履约只作用于当前有效对象，未知付款日不能履约。输出商品与订单按ID排序，业务revision基于有效视图，含scope/epoch与效果，独立于read_at和身份代次；product_detail拒不匹配revision/source。导入只增加目录对象，不创造订单、销量或已知库存。

KPI用Decimal局部precision50，平均值明确六位HALF_EVEN；shop时区转UTC半开区间，默认固定fixture最后业务日之后零点。未知付款时间仅在created_at早于区间结束时计可能影响；超来源窗口/缺付款日/零分母保持不可用或部分值。退款按事件日独立聚合，UNKNOWN结算标签不变成净收款或回库。成本/在途保持未知；低库存阈值3且已知/未知分列。趋势复用同一有效视图及单日区间，未造同比或外部模型事实。

测试源码含独立手工金标：7日已知支付小计2140、14日4520、退款事件90/418、跨日及未知值，低Decimal环境、来源/效果版本及导入仅增商品等。审查读取测试逻辑，不将作者报告的25pure视为本次独立执行；本次没有重跑测试/生成器。

## 尚未实现或仍需验证

本片没有列表过滤/稳定分页/cursor签名、drilldown接口、实际export生成或read-context服务装配，不能因定义了DTO就签这些行为完成。read-context DTO新增对象/指标事实及kind关联校验，可供后续服务实现；权限始终由调用者当前解析和锁保护，ViewScope输入不构成能力。SQL低权直调/撤权锁序/导入预览版本及解析失联两项合同P2继续独立跟踪。

静态检查不代表schema生成命令或25pure在该SHA已由Reviewer运行。实际JSON已读取核两个导出route与Snapshot来源引用；无服务/PG/API/browser/网络。旧62ab结论保留其时点。
