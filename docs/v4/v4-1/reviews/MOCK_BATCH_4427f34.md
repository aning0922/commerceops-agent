# 批量React Mock spec 4427f34独审

2026-11-04（台北）。结论：`HOLD / ONE_TEST_P2`。冻结提交 `4427f347206bf55250d847d3fffcf76051006d29`，parent `a7e5f9ff4b53a956390c0807c3efcad135c9047a`，tree `fff82bfbcad23a2cd2e65b783129f9bb7380fc10`；唯一新增frontend/v41-tests/batch-tags.spec.ts。仅审该spec及必要固定产品接点，不重复Main产品六路径审查，不读取后续WIP。

P2定位spec:46、71–73：actions Mock接受任意路径末段作为request_key并返回UNKNOWN，原两个UNKNOWN/409用例点击恢复后只核pending中的旧key、POST总数及“仍需核对”提示，未核真正发出的lookup请求。若产品错误地生成新key查询，响应仍是合法UNKNOWN，旧pending仍保留，现有断言可以通过，不能证明“只读原键恢复”。应在独立假后端对lookup严格断言GET方法、product_tags、首POST原key及原shop/query，并记录实际lookup；恢复后核精确原键查询及无额外POST。不从待测URL复制key作为唯一预期，不改已接受pending规则。

独立无资源反例：从精确spec提取源，经固定Node24 stripTypeScriptTypes在VM注册7标题，只调用其setup路由handler；注入一个错误恢复key，原handler接受、生成响应通过精确4427的ActionLookup schema，原pending-key相等及POST数1断言仍通过。CLI0只表示该测试漏洞反例成立，React测试执行0、浏览器/CDP/网络/服务/PG均0。私有复现为Reviewer `.audit/v4-1/batch-spec-4427-review/recovery-key-repro.cjs`，不是业务或UI运行证据。

其余有限源码观察：成功Mock不预写sessionStorage，也不替产品清pending；POST到达时先读持久key/resource及独立version/revision，之后才更新假商品并生成receipt，精确read/post顺序和两个不同key有外部断言。held分支在释放后等待写锁对应控件可用，并检查不续发/原pending和清选择；390只核Mock模态文案、可用性/边界/焦点/Esc和零发送，不是完整真实移动端验收。作者TS/collect7/preflight0属于其静态证据，测试体NOT_RUN，不写7PASS。

Root另转Main发现a7产品“POST已COMMITTED后GET REJECTED误计rejected”问题，本审查不重审该产品P2，也不签其修复或拟新增第8例。待精确新freeze后只复核相关测试增量；旧4427缺口保留，不放松测试或用Mock代真实后端权限/持久化/手机Gate。

## 6960d56 精确增量复审与原测试 P2 关闭

2026-11-04（台北）。追加结论：`MOCK_SOURCE_INCREMENT_ACCEPTED / ORIGINAL_TEST_P2_CLOSED`。最终审查源码 `6960d5666ba4fd51215aa54bef16058aab566052`，tree `cd6b884b4d39e84baa2f1078ab6ce4d622ca0cb2`，parent `cc5c9a6b3a361c2c451c5652023b9e73b5488f9d`。cc5 的 spec 增量新增 COMMITTED 后读回 409/403 两例；6960 仅修改同 spec 的原键恢复检查。本轮只审相对 4427 的 Mock 增量及必要固定客户端/UI 接点；demo 分类修复由 Main 独立复审，本报告不代签。上述旧 P2、反例及当时 HOLD 原文保留。

actions handler 现在以首个实际 POST 的保存记录为独立预期，先检查请求数 1、GET 方法、完整 product_tags/原 request_key 路径，以及只含一个原 shop_id 的 query entries，全部通过后才记录 lookup 并返回 UNKNOWN。响应 key 来自首 POST，不再照抄待测 URL。原 unknown/conflict 两例在点击恢复后检查精确单条 lookup 数组、POST 总数 1 和原 pending key，因此错误 key 不能再被合法 UNKNOWN 响应包容。

独立复现提取最终 spec、schema 与 readV41 客户端的精确 Git blob。固定 Node24 在 VM 注册 9 个标题但不调用测试体；仅调用原 setup 的假后端 handler。注入原 wrong-key，以及错误方法、operation、shop、多余 query、重复 shop_id、缺失 query，共 7 种不合法 lookup，全部断言拒绝且未记录 lookup；正确原键 GET 返回严格 ActionLookup schema 合法 UNKNOWN，lookup 数为 1、POST 数为 1。私有脚本 `.audit/v4-1/batch-spec-6960-review/increment-repro.cjs`，最终 CLI exit 0；该结果关闭原测试 P2，不是 9 个 React 测试通过。

新增两例先观察实际 Mock POST 响应 HTTP 200/COMMITTED，再以首商品已发生一次假提交后的 detail GET 为读回 barrier；handler 等待 release 后分别返回 HTTP 409/403 与严格 REJECTED FailureEnvelope。假后端只维护商品和传输状态，不写 UI 计数或 sessionStorage，不替产品清除或制造 pending。独立注入验证了两种 FailureEnvelope 和提交 receipt 的 schema，并将这两个响应送入同冻结 readV41 的注入 fetch：确实抛出 status=409/outcome=REJECTED/code=VERSION_CONFLICT 与 status=403/outcome=REJECTED/code=ACCESS_DENIED，未变成 HTTP 200、无效响应 UNKNOWN 或成功返回。没有真实网络请求。

UI 断言源码也核清：读回暂挂时两例都要求成功 0/拒绝 0/待核 1/未发送 1；释放后，409 等待仅在 writeBusy 结束后出现的“取消”按钮，再检查同一组计数，不能仅凭暂挂期间中间状态通过。403 要求原有身份/店铺验证失败提示、进度消失及对话框关闭，没有为测试恢复失效 scope。最终都核仅一次 POST 与原 pending key 保留。这是可执行断言与假后端设置的源码证据，实际 React 行为仍 NOT_RUN。

独立复现首次 CLI exit 1 原因是 reviewer 使用 strip-only 编译真实客户端时不支持 TypeScript constructor parameter property；改用 Node 自带 transform 模式后原客户端无需修改，最终 CLI exit 0。该复现工具失败与产品/测试失败分列保留，ExperimentalWarning 亦未隐藏。Root 转交的全配置 collect 33/4 specs、TS、74 Node 和作者 preflight 属作者证据，本轮未重复执行。浏览器、profile、CDP、服务、PG、真实 UI 测试与网络均 0；真实权限、持久化、Native/移动端和阶段验收不由本报告关闭。后续 owned Mock 实际窗口仍由 Root 单独安排。
