# HTTP 11场景按原受测源码独立核收

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_LOCAL_HTTP_11_SCENARIOS_WITH_SOURCE_PARTITION。** 11个场景各自实际成功及清理证据可核收；不是同一R3源码重新运行全部11项，不签所有Q01–Q18、完整PG、Hosted或发布。

只读运行目录 `/Users/aipuli/.codex/worktrees/commerceops-v4-http-20261104-047a43d/commerceops-agent/.audit`。依据原HTTP_EXECUTION、HTTP02D_EXECUTION、R2_HTTP03_11_EXECUTION、R3_HTTP08_11_EXECUTION安全汇总，逐case核case.json、driver.outer.log中的结构化结果、probe成功JSON、ROOT_OUTER、final_pg及observer安全记录。未读取私有异常正文、cookie、DSN、owner/API私配，未重跑服务或外部调用。

## 来源与逐场景结果

F1=`047a43dafef90edea2eb532c2a03b6f850da0b9a` / tree `5c0699edb2d30889ce770ca9b05b56dab957ce10`；R2=`c6abe0528f05b458331f270d758317c1d7b38843` / tree `73e987375e2b6a2f06ac5aabaaab1499d78207d0`；R3=`0636d3c9c70500f12b5f73de45217513ff38e93a` / tree `dd0c81bb5928219d87c713c8956b05aadb1fec9c`。

| 原case目录 | 场景 | 实跑source | 最终tenant行数 | 独立核收的固定判据范围 |
|---|---|---|---:|---|
| cases/HTTP01 | lifecycle | F1 | 2 | 两访客/两店、跨tenant拒绝、A reset不改B、persona/logout |
| cases/HTTP02D | capacity | F1 | 3 | 5独立访客前三创建、后两CAPACITY_LIMIT与正Retry-After、原三会话保留 |
| cases-r2/HTTP03B | ack_body | R2 | 1 | 丢body但保cookie，原创建键/current/receipt与PG提交关联 |
| cases-r2/HTTP04B | ack_headers | R2 | 1 | 恢复原bootstrap cookie，原键最小恢复回执、owner recovery且current401 |
| cases-r2/HTTP05B | security | R2 | 1 | Origin/CSRF403、额外role422、身份不变、V4 bearer改名不能进入旧API |
| cases-r2/HTTP06B | same_key_reset | R2 | 1 | 并发同键一次效果、当前CSRF同文回放、异文409、原receipt/event与epoch |
| cases-r2/HTTP07B | persona_stale | R2 | 1 | persona切换后旧generation/旧CSRF拒绝、当前身份读取 |
| cases-r3/HTTP08C | bootstrap_restart | R3 | 3 | 确定REJECTED后显式新bootstrap、旧绑定不变、原键UNKNOWN、安全只读、容量仍3 |
| cases-r3/HTTP09C | identity_scopes | R3 | 1 | operator两店→approver一店→restricted_admin零店，reset不恢复隐含权限 |
| cases-r3/HTTP10C | credential_revoke | R3 | 1 | 实际owned credential撤权后current及reset401 |
| cases-r3/HTTP11C | grant_revoke | R3 | 1 | 实际owned grant撤权触发旧actor失效，current及两原店summary401 |

全部原case的source/tree/project/deadline与外层回执一致；driver与scenario native0，probe为完成状态。各observer实际native0/FACT_OBJECT_RECEIVED，未以pure代替PG。每案最终PG行数与driver记录一致；最终tenant行数不是active数。HTTP08C的active3另由实际capacity断言支持，09–11不补称active1。并发reset接受已审“至少一成功，另一可为旧CSRF拒绝”的原合同，不宣称两请求都200。

全部核清理顺序为writers stopped→API stopped→owner oneoffs inventory→final PG→down keep volume→containers/networks gone。外层namespace初始为空、forced=false、cleanup_confirmed=true，登记组live成员/leftover IDs为空、端口关闭，各案保留各自卷。原API停止阶段非零值保留，不等同scenario失败。各HTTP响应逐条wire未另外持久化，本次依据精确执行源码、native0、结构化成功及PG/observer回执核断言执行，不补造具体响应原文。

## 失败保留与代码复用

旧HTTP02服务前失败保持causeUNKNOWN；HTTP03R原内部异常NOT_CAPTURED；HTTP08B R2在main传播边界捕获TypeError/RLock但具体内部抛错行未记录，保持FAIL；当时09B–11B未运行不改写。R3 08C–11C为独立新case成功，不覆盖旧行。原image preflight失败同样保留。

审查时HTTP运行tree HEAD仍为R3；ROOT HEAD为 `cbd1c4e31569bf84f065fd38dd18448d438f6225` / tree `68efd8feb282430e5eb950661bae07a19db6f0d9`。独立比较F1/R2/R3/此ROOT的backend、frontend/app、frontend/components、frontend/lib及docs/v4/baseline子树均完全相同。backend tree `a050fd49f1195e9bd6522c297491289f82d1773e`，三个产品前端子树依次 `76d95320fc01101b444e41b76a8a32c0435e8f3b` / `981168b8abe62d27b97506585d9845d5cbf01b4f` / `ca1b6d070fc13ad1ce22f5b8898fb31528e5a2f0`，冻结合同子树 `11ef0fd51f9ea0ec0630c4d080b0be9d498d3f8c`。R3→该ROOT仅两份LOCAL_RUN文档差异。

因此可按相同业务字节引用这些分源证据，但工具修复有明确差异：R2使用ACK snapshot修复，R3再修bootstrap snapshot；不可写“F1工具已全通过”或“cbd1/R3实际跑了11案”。ROOT工程全检与PG双线未在本报告独立核收。

## 证据指纹

以下SHA256为各case按case.json、driver.outer.log、ROOT_OUTER.json、final_pg.safe.json顺序拼接原字节计算，未公开身份/操作标识。

| case | SHA256 |
|---|---|
| HTTP01 | 5d670a9f597f7f672307a9d60743d242753b592e38ec6fac5bccaee0b92ce465 |
| HTTP02D | f9060f58ea1480182b3f97dfde4fa75f0ac25bb33a8736cd73fa8eeb822d1ce5 |
| HTTP03B | ee607d712f21bfa8449577dd4b421d78276be04fc09250ea08d6d93aec2e4832 |
| HTTP04B | 6f59d6e75be9f0af81f0df0a4c19d1e37074ea61e84b2be181d3eeeedc0ee8f6 |
| HTTP05B | 1bc74cbc1f192edd3073be99e1f4265b4dc5372e65ac244bca5f36aadf2e2719 |
| HTTP06B | 86a033835786c92b5c8d9d431e4b4482faf460d9e942ee5c81cbe9347c5eece3 |
| HTTP07B | a0cfdf33fc9fe3da385ba7ba8792ad40e7485c1d0380446d474aea8cc0f7c4ab |
| HTTP08C | a7cb2418693c41b337ca519446fe28f008f4fde75eaf1ed90df67933669d264e |
| HTTP09C | 5d415a93c5d019e3cb2adc981097664118442754e453338502e20f562ee4309c |
| HTTP10C | cfc1e77058272174ee5462a7243e785ab4de910d6452ecaf5d3b2f37a9e1a47e |
| HTTP11C | 1a0a887c7ebbdda54ac60dafe18f2ae6e7248de793507f995e5ab20b7ffa7fad |
