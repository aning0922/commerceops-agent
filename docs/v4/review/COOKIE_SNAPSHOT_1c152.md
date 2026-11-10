# V4 ACK 探针 Cookie snapshot 1c152 窄审

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_PREPARED_COOKIE_SNAPSHOT_DELTA，0 P1 / 0 P2。** 仅签验收探针增量；新HTTP ACK场景实际运行仍待ROOT，不追认原HTTP03异常根因。

candidate `1c1525088708e12b552973ba9d0ab1b7cd6f1ec6` / tree `6fb5606f37b82555f524cae63db5adbd55de6f0a`，parent `1684e0455978b46ddad607e09d85a1af5657ab1a`。精确delta仅 `tests/e2e/v4/http_probe.py` 与新增 `test_cookie_snapshot.py`，无server/schema/frontend或其他文件修改。

## 实现与原流程保持

新增 snapshot_cookies 构造全新 httpx.Cookies，遍历源jar并对每个 Cookie 单独 deepcopy，再加入新jar；不复制CookieJar自身的RLock。源Cookie对象的全部字段（含domain/path及其指定标志、secure、expires、discard、HttpOnly/SameSite等_rest字段）完整复制，不改成简化name/value字典；同名不同path/domain仍由原CookieJar键结构保留。此探针使用httpx默认jar策略，本增量不承诺复制任意自定义CookiePolicy。

create_ack_loss仅替换bootstrap保存点和headers_and_body恢复点。保存的是独立快照，恢复再复制成另一独立容器，避免后续client赋值/变更污染保存值。body分支保留POST应用后的活动cookie，headers_and_body分支恢复POST之前bootstrap cookie。原真实POST、response.close丢弃响应、同原key GET receipt、body current.creation_request_key校验、COMMITTED要求、PG一次receipt/两事件及tenant/receipt关联、最小OWNER_RECOVERY_REQUIRED响应和current401判据全部保持；没有重发POST、新建key、放宽UNKNOWN或伪造响应。

独立AST比较：去掉唯一新增helper、将两处snapshot表达式还原后，整个http_probe AST与parent完全相同。修改前该文件blob `d2f7dd62c119b0f1141f26e1786cfa47273a3743` 也与F1完全相同；修改后为 `d9579c346d2d035f7df06ccfef1eb003cc74260f`。

## 独立纯验证

精确git archive临时快照运行 test_cookie_snapshot.py 与 test_http_criteria.py。首轮 **20 PASS / 2 FAIL / 0.28s / native1**：两项旧strict-response测试因快照未挂接 `.tools/node/bin/node` 而FileNotFoundError，未执行到schema断言；两项新cookie测试已通过。随后仅在新临时快照挂接既有Node及锁定依赖，没有修改源码或安装依赖；同一精确候选最终 **22 PASS / 0.51s / native0**。

真实httpx.Client空jar的旧deepcopy确定抛TypeError cannot pickle RLock；新空snapshot成功。属性测试从合成HTTP Response提取两个同名不同scope cookie，核所有vars一致、Cookie及_rest对象独立；活动cookie value/SameSite修改、清空替换及恢复后再次修改均不影响保存快照。所有Response仅本地构造，没有HTTP传输、PG、harness、browser、scanner或资源启动；临时目录已清理。

## 源码与证据复用边界

此提交相对parent只改探针及测试，不能笼统说其整个tree与F1业务相同：独立 `git diff F1 1c152 -- backend frontend` 仍有父分支尚未整合的差异，包含migration、v4_demo_http及前端文件。这不是本两文件补丁引入的业务修改，也不需要在此改回作者分支。ROOT合入最终候选后应重新核最终backend/schema/frontend相对F1的完整blob/目录差异；满足字节相同后，F1 Full/TTL只能保留其原受测source并说明复用范围，不改写为新SHA实际重跑。

原HTTP03的0tenant失败内部exception仍NOT_CAPTURED；本次RLock纯复现仅证明旧探针存在确定可触发的问题，不能反推当时已捕获此异常。接受本修复不等于body/headers ACK实际Gate通过，新HTTPcases及source需分别以真实运行回执记录。
