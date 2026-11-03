# V4-0 四合同最终增量独审

日期：2026-11-03（Asia/Taipei）。**结论：ACCEPT_CANDIDATE。当前冻结八文件无未关闭P1/P2。**

接受范围为A阶段候选合同文本及其一致性，不是代码实现许可、用户B授权、资源窗口、API/PG/Web验收或V4-0完成。原首审及复审报告保留，本文件仅对新的冻结hash集给出增量结论。实际实现、SQL/低权ACL/锁顺序专项审查、必要完整回归均待后续独立Gate。

## 1. 冻结来源

目录：`/Users/aipuli/Documents/Codex/2026-11-03/commerceops-v4-readonly-review/`。

权威候选清单：`evidence/CONTRACT_REVIEW_CANDIDATE_HASHES.json`，SHA-256：`655c7e1f99fbc604752f0a84348e307cf193294603aeb9f69e25552985373640`。实际逐文件哈希与清单全部相符，且在写本报告前再次核对一致。

| 文件 | 接受的实际 SHA-256 |
|---|---|
| DOMAIN_SOURCE_CONTRACT.md | `303f187bf0acd604f5eb8260894bf57c2f739cfa9ae314e11fed3bbeaae4d0aa` |
| PERMISSION_DEMO_CONTRACT.md | `66d59617a8315111e70de5377b49ed4504960e103442d4449e374d57a81de885` |
| UI_ROUTES_CONTRACT.md | `79dccfd7285d5f9f35b8c12c2c940888db87480c97387eb9bffc16ee7f19ee7d` |
| API_EVENTS_CONTRACT.md | `03712031fea631c115af4a6c1c3efae053d5785f89adc3d62bba9a99baeb9711` |
| TASK_PLAN.md | `76660c9adf71e4aff7165f9a8fa0fa140c4bd1ce67467c3f369024827d41dc60` |
| v4-permission-matrix.csv | `139e04d028aae19b6f476e0f2f16c93f15ab9e649801c5138b96a896c9ab6cdd` |
| v4-demo-seed-manifest.json | `24fd9041ef6beae75a161b9fd9243bf085bcf4a2bae6fc2eed79307d56f0896e` |
| v4-public-openapi.json | `1bc8800309a52ecab119c0f202e1386c2393c301e7b91249bb47c7f9421d28be` |

保留的前轮报告：`reviews/CONTRACT_REVIEW.md`，SHA-256：`61fa7631321b7b3b8df84d44ee4860a5300353b5a3691247c69a4013dba5315d`；其中旧hash、CR-01历史、CR-02/03待修与Terra两项的关闭记录原样保留，不改成“从未发生”。

本次仅读上述候选与静态JSON语义，未重复Harness盘点，未运行工具链、测试/collect/扫描器、服务、PG、浏览器、远端写或Git变更；没有读取历史密钥。唯一新增产物是本报告。源码事实基线仍为M3 `952e6246deb01ec763f2541d9f316753987744f3`，前轮精确源码引用继续有效。

## 2. 两项剩余发现关闭

### CR-02 [原P1] 身份桥接冻结不变量 — CLOSED_AT_DOCUMENT_LEVEL

`PERMISSION_DEMO_CONTRACT.md:13`已消除“公开demo bearer交旧SessionStore.authenticate”的歧义；:39–47新增明确且可验的边界：

- :41要求V4 bearer hash不命中旧web_sessions.token_hash，改名旧cookie请求/api/v1必须401；bound旧session仅供私有WebActor证据，token不得公开，absolute/idle上界不超过原DemoSession绝对截止。
- :43要求完整credential/identity/principal/session及V4 tenant/epoch/generation核验，不能只用actor_guard；禁止裸WebActor绕过V4上下文，不开放旧业务mutating路径或Graph任务。
- :45要求persona/reset在同一事务撤销旧bound、建立新绑定并更新代际/CSRF；receipt、撤销和当前绑定原子，旧actor因旧session撤销而拒绝；logout/到期/撤权有对应失效规则。
- :47保留真实SQL/锁顺序/低权ACL及映射的实施前专项Gate，触及旧web_sessions.py必须ROOT另行精确释放，不能把候选接受当作改旧auth授权。

OpenAPI `components.securitySchemes.demoCookie.description`（:1055）同时声明V4专用、旧/api/v1拒绝改名cookie，bootstrap/active按独立DB权限区分。这些条款与DOMAIN的旧WebSession引用、TASK_PLAN单owner/旧路径默认只读没有冲突。

因此已排除前轮指出的两种错误解释：公开bearer跨域复用，以及只更新V4 generation却让旧bound actor继续有效。这里关闭的是规范缺口；SQL实现正确性与实际401/撤销行为尚未执行验证。

### CR-03 [原P2] 授权店铺基数 — CLOSED_AT_DOCUMENT_LEVEL

OpenAPI `components.schemas.SessionData.properties.shops`（:1253–1260）已改为minItems=0、maxItems=2，描述限定当前授权店铺。`API_EVENTS_CONTRACT.md:52`明确tenant seed两店与当前persona可读0–2店分开，restricted_admin不为满足两店而获得业务grant；默认operator可以由fixture显式授予两店。

与PERMISSION:27、权限CSV:2及空态/撤权约束一致。API端点表和UI首次进入中的“双店”应按此细化解释为默认operator的初始化路径，不是每次current响应必须包含两店。实现时shop_id去重、当前grant匹配及0/1/2店负例仍需正常验证，不因schema接纳空数组就签实际权限通过。

## 3. 已关闭事项无回退

| 项目 | 当前文本证据 | 本轮结论 |
|---|---|---|
| CR-01 DB失败时间 | API:28；OpenAPI FailureEnvelope:1446起，server_time允许string/null且禁止host时间冒充DB UTC；成功信封仍为DB时间 | 保持关闭 |
| Terra P1-1 bootstrap恢复资格 | API:20,38–40；PERMISSION:35；OpenAPI operations:get的x-bootstrap-exception:1044及x-cookie-purpose | 保持关闭：300秒/原owner+单key/最小状态，不能换领token或进入业务读取 |
| Terra P1-2 敏感读/多标签屏障 | API:42,50；UI:31–33；PERMISSION:37；seed-summary必需epoch/generation请求头及context响应 | 保持关闭：服务端即时拒绝过期请求，客户端清屏/恢复核验与显式5秒收敛，未承诺跨设备即时撤回像素 |
| context适用范围文案 | UI:31区分敏感成功数据与匿名bootstrap、最小控制回执、错误；API:50列同样例外 | 一致，无须为匿名/错误伪造context |
| GET缺Origin与写入边界 | PERMISSION:31明确无Origin拒绝限写；API:44规定受信同源FetchMetadata/Host例外 | 一致，不向POST传播例外 |
| 每operation cookie用途 | OpenAPI八操作均有x-cookie-purpose；bootstrap/session_create用bootstrap，current/persona/seed/reset/logout用active，operations仅对session_create加受限bootstrap例外 | 一致；仍须运行时按用途强制，扩展字段本身不执行鉴权 |

原`reviews/UI_CONTRACT_REVIEW.md`保持旧hash下的两P1首审事实，不在此覆盖其内容或代签Terra本人审查。这里是本审查人对最终冻结字节的独立关闭核验。

## 4. 仍保留的正常实施前Gate

接受候选不消除已经明确的后续工作：

1. 用户另行批准本地B03–05；TaskSpec绑定实际base/tree、owner、资源/绝对UTC/预算与清理，不从A或旧窗口继承。
2. SCHEMA/API先交身份映射、完整credential校验、bound会话撤销、事务锁顺序/低权ACL专项设计。未过即停止身份桥接依赖；旧WebActor/guard、旧grant-runtime等受保护路径不自动可改。
3. 在03/04实施前冻结最小seed生成器/随机seed/日期锚/对象关系与规模；manifest仍PROPOSED_NOT_GENERATED，counts/digest未知保持未知，实际生成后再给内容digest。reset persona默认、receipt/tombstone保留和线性化细节纳入该切片冻结，不先改旧迁移再补。
4. 0024仅在head仍0023时新增；03冻结后不编辑旧revision。03/04同一SCHEMA/API串行，WEB与QA各自独占路径；不新per-tenant Worker、不投Graph、不提前采购/CRM/营销状态机。
5. strict DTO/生成客户端、真实API/PG/浏览器、跨tenant/shop/代际/撤权/丢ACK、完整动态PG与原G1/G2/Web/N01等只由实际执行证据签收。Hosted/amd64/Harness合并及后续V4-1不在本候选授权范围。

没有把以上明确待完成Gate重复列作A的未关闭P1/P2。本次结论允许ROOT将这八份确切字节作为**待用户批准的候选合同**汇总交付，不能宣称代码已开始或业务Gate已通过。
