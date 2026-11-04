# V41 DTO/schema 首片独立审查

日期：2026-11-04（台北）。source `62ab257fef65c5d7f237969ce901b69b2fd3fcdc`，tree `a1e5ce6e5abc28e6fd771c32e4a3a085ebc924e2`。读取本提交全部五文件：application/v41包及contracts、scripts/v41_schema.py、API_CONTRACT.json、tests/v41/backend/test_contracts.py。对照完整合同84db1ba；不将后续作者修订计入本次。

结论：HOLD_CONTRACT_ALIGNMENT，两个P2阻断将该schema作为完整V41接口冻结/交给WEB消费；独立纯查询或其他开发不必停止。未发现本首片新增可执行授权绕过：它未装配router/SQL，生成物也明确标记纯DTO而非运行路由。

## P2-A01：导出响应与冻结合同不符

`scripts/v41_schema.py:28`、`:45` 将两导出响应定义为普通Page商品/订单，`:112` 声明原始CSV transport；API_CONTRACT.json实际生成物同样如此。没有合同第4节冻结的 ExportEnvelope/csv_text/row_count/安全文件名，Page最多100行也不能表达最多500行导出。WEB无法按当前schema严格核验授权上下文后的CSV下载。

最小修复：新增有界严格JSON导出data/envelope，包含固定格式、安全文件名、csv_text、row_count及权威source/revision/context；两导出route统一指向该DTO并删除原始CSV transport声明。更新生成物与实际字段/边界测试，证明超500拒绝而非静默截断、普通Page不能冒充导出响应。文件名/CSV安全仍需服务实现验证。

## P2-A02：聚合来源无法表达fixture加多次upload

`contracts.py:118` 的SourceRef只允许fixture或单个upload，upload对应单一job；`:133`的Snapshot直接使用该类型。因此混合产品列表、导出、dashboard或read-context只能错误标成fixture或任意一个job。对象来源也没有合同要求的row/file digest定位。现有测试只证明单对象mode/job互斥，不能验证混合有效视图来源完整。

最小修复：区分对象来源与聚合快照来源，定义有界混合来源集合或等价严格结构，保留fixture version/digest及上传job/row/file digest；不将来源标签当权限。补fixture-only、upload对象、fixture+两个job混合及缺失/伪造来源字段拒绝用例，更新生成schema。不能仅放宽data_mode字符串而仍丢来源引用。

## 已核可保留内容及后续边界

- strict/frozen/extra-forbid沿用基类；请求不接客户端权威角色/租户，CAS整型、日期窗口、标签唯一性、mapping列唯一性、preview发现/恢复、三业务操作、已提交回执/UNKNOWN互斥均有明确结构或validator。
- Decimal wire为有界canonical字符串；部分指标禁止numeric value、成本/在途未知、退款网关UNKNOWN字段和not_used模型标签方向正确。Metric的metric/unit/settlement、Period端点一致性等跨字段语义仍须由纯服务金标及输出验证证明，当前DTO不代表完整经营口径已实现。
- BusinessEnvelope通用status包含UNKNOWN，消费者不得只因HTTP成功就渲染业务data；运行router需按具体端点约束状态，失败信封不能冒充已提交效果。
- preview与parser/schema/data revision保存/确认约束仍受合同审查P2-C02约束；本片没有持久模型，不能从WriteContext有expected revision推断已闭合。
- route元数据16项包含当前身份/POST CSRF及GET context要求，但不是运行middleware；实际GET Origin同源例外、能力校验、导出失败清屏、无越权恢复、HTTP限额均待router/SQL独审。

验证方式：精确git对象阅读，并用JSON读取已提交schema确认16路由、两个export response引用及Snapshot来源引用；没有运行作者测试或生成器，未声明schema再生成通过。作者测试源码包含严格输入与生成物一致断言，本次不将其当作已运行证据。无PG/API/browser/网络调用。
