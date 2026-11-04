# 批量React Mock spec 4427f34独审

2026-11-04（台北）。结论：`HOLD / ONE_TEST_P2`。冻结提交 `4427f347206bf55250d847d3fffcf76051006d29`，parent `a7e5f9ff4b53a956390c0807c3efcad135c9047a`，tree `fff82bfbcad23a2cd2e65b783129f9bb7380fc10`；唯一新增frontend/v41-tests/batch-tags.spec.ts。仅审该spec及必要固定产品接点，不重复Main产品六路径审查，不读取后续WIP。

P2定位spec:46、71–73：actions Mock接受任意路径末段作为request_key并返回UNKNOWN，原两个UNKNOWN/409用例点击恢复后只核pending中的旧key、POST总数及“仍需核对”提示，未核真正发出的lookup请求。若产品错误地生成新key查询，响应仍是合法UNKNOWN，旧pending仍保留，现有断言可以通过，不能证明“只读原键恢复”。应在独立假后端对lookup严格断言GET方法、product_tags、首POST原key及原shop/query，并记录实际lookup；恢复后核精确原键查询及无额外POST。不从待测URL复制key作为唯一预期，不改已接受pending规则。

独立无资源反例：从精确spec提取源，经固定Node24 stripTypeScriptTypes在VM注册7标题，只调用其setup路由handler；注入一个错误恢复key，原handler接受、生成响应通过精确4427的ActionLookup schema，原pending-key相等及POST数1断言仍通过。CLI0只表示该测试漏洞反例成立，React测试执行0、浏览器/CDP/网络/服务/PG均0。私有复现为Reviewer `.audit/v4-1/batch-spec-4427-review/recovery-key-repro.cjs`，不是业务或UI运行证据。

其余有限源码观察：成功Mock不预写sessionStorage，也不替产品清pending；POST到达时先读持久key/resource及独立version/revision，之后才更新假商品并生成receipt，精确read/post顺序和两个不同key有外部断言。held分支在释放后等待写锁对应控件可用，并检查不续发/原pending和清选择；390只核Mock模态文案、可用性/边界/焦点/Esc和零发送，不是完整真实移动端验收。作者TS/collect7/preflight0属于其静态证据，测试体NOT_RUN，不写7PASS。

Root另转Main发现a7产品“POST已COMMITTED后GET REJECTED误计rejected”问题，本审查不重审该产品P2，也不签其修复或拟新增第8例。待精确新freeze后只复核相关测试增量；旧4427缺口保留，不放松测试或用Mock代真实后端权限/持久化/手机Gate。
