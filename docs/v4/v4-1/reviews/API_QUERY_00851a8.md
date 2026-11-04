# V41 纯查询、游标、导出和钻取独立审查

日期：2026-11-04（台北）。source `00851a8c87191de52ab127d6ff46a6c56e892981`，tree `4f2979159f62e3317e6953ea63699d684f7860d3`。完整读取queries.py、五项测试、RefundReference DTO及schema生成增量。无作者WIP或实际SQL/HTTP调用。

结论：HOLD_EXPORT_CONTROL_PREFIX_P2。一项P2限于CSV安全；查询/cursor/钻取纯切片未发现其他阻断，可继续独立集成准备。此报告不签权限、服务或全部业务Gate。

## P2-E01：控制字符前缀绕过CSV公式字面化

queries.py::_safe_csv只使用lstrip后判断公式起始字符；NUL及部分非空白控制字符不被lstrip移除。当前SetProductTags/TagEffect/Product允许这些字符。以精确源码构造NUL前缀加等号算式的标签，DTO接受、有效视图接受，export_products生成的CSV tags单元格仍以该控制字符开头且没有单引号转义。导入parser拒控制字符不能保护独立标签编辑入口。

最小修复：在全部可导出文本的统一安全边界拒绝不支持的控制字符，或按冻结规则将其安全字面化并处理公式前缀；不要只为导入新增校验。补NUL及其他控制前缀、空白/制表/回车前缀、普通公式起始字符和正常Unicode/CSV引号分隔文本反例。不能把csv.writer加引号当公式防护。实际spreadsheet执行未运行；本P2证明的是固定安全合同缺口，不声称发生了公式执行。

## 已核可保留机制

- product q匹配title/SKU、tag/origin过滤，价格按最小SKU Decimal排序，UUID tie-breaker；order按created/paid时间窗、payment/fulfillment/q过滤，拒paid基准加unknown组合，金额按Decimal而非字符串排序。
- HMAC带域分离、至少32字节secret、constant-time比对、2KiB上限；cursor绑定scope(tenant/shop/epoch/template)、身份generation、有效revision、除limit/cursor外完整query摘要及末ID/排序键。篡改拒绝，scope/过滤/generation/revision变化不继续混页。cursor仍不是权限，当前身份/角色须store每次重核。
- 页面snapshot材料排除limit/cursor，因此相同筛选的各页/全结果导出snapshot一致；导出遍历全部过滤结果而非当前页。商品按SKU行输出，row_count与商品数不同是明确结构；大于500行或UTF8输出1MiB拒绝，不截断。固定文件名、来源/fixture/revision列保留。
- RefundReference在退款事件基础增加原order_id，钻取按事件时间且结算UNKNOWN保持。read-context从同有效视图挑真实对象/相关规则，kind/resource一致，无真实模型或执行能力。

后续口径注意：low_stock_count现有KPI按SKU计，而本drilldown按含低库存SKU的Product分页；应明确total为商品行数、SKU明细/已知小计如何核对，不把不同计数单位画成同一指标。当前固定seed金标不证明多低库存SKU同商品情形。该点作为后续DTO/UI口径核验保留，本次不凭推测扩大P2。

## 独立验证

git archive提取00851a8的backend/src和test_queries.py，locked Python隔离执行：5 passed、0.23秒、native0。测试覆盖cursor不同过滤/身份代次/来源版本/跨scope/篡改、Decimal排序、同源全结果导出、退款订单关联及read-context。隔离offline marker未注册的一项warning保留，未重复测试。

另运行上述控制前缀真实DTO→build_view→CSV导出反例，输出原始控制前缀、formula_escaped=False。作者累计79pure未当作独立全量复跑。secret仅测试本地临时字节，无凭据或网络。

新RefundReference改变drilldown schema，WEB/QA必须同步最新生成契约并检查引用字段，不继续按旧RefundEvent签联调。分页权限/签名key配置、版本锁序、CSV下载上下文和SQL数据来源均须后续代码/真实Gate。未运行服务、PG、API、browser或远端操作。
