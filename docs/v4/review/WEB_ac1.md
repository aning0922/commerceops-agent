# V4前端ac1完整准备代码独立审查

日期：2026-11-03（Asia/Taipei）。**结论：P2_REQUIRED_CHANGES，0 P1 / 3 P2；暂不签ACCEPT_PREPARED_UI。** 原WCTX-01在当前实际使用路径已关闭。未运行浏览器/测试，不把UI_FIXTURE结果当真实鉴权。

## 精确范围

candidate `ac1d18e23d3235b23fad90ecfe1e4caf051f72bd` / tree `b44577aa2578281ceb042fd4a1e351c2d3f9da42`，相对eb82为18个新增V4前端/测试文件。全部读取精确Git对象，不读WEB WIP。实际入口为`frontend/components/v4/demo.tsx`，其长行以函数/JSX符号定位；本文行号均绑定candidate。源码检查与标准库JSON派生比对不等于工具链/运行验收。

## WEB-01 [P2] 管理员选项发送未登记的persona_id

位置：`frontend/components/v4/demo.tsx:26`的体验视角select及`:24` control(persona)。

选项值为operator/approver/**admin**，而已准SEED_SPEC persona为operator/approver/**restricted_admin**；ffb的PersonaInput也只允许这三个精确值。用户从运营选择“管理员”会发送persona_id=admin，严格后端应422，UI随后落UNKNOWN。已处于restricted_admin的用户虽然有额外“当前视角”option，却仍无法从其他角色正常切入受限管理员。

最小修正：展示文案可继续“管理员/受限管理员”，请求值与当前persona集合统一为restricted_admin；补operator→restricted_admin成功、shops为空且可reset/logout、未向admin发POST的fixture契约。不能为了UI改后端allowlist扩成别名；schema persona_id是宽字符串不代表任意值均已授权。当前测试只切approver，未覆盖此路径。

## WEB-02 [P2] 控制回执只比较不倒退，可把无effect的reset显示成功

位置：`frontend/lib/v4-context.mjs:55–73` matchesControlBoundary，尤其66/73；`demo.tsx:24`成功消息。

对于persona/reset，helper只要求receipt代际等于response context且after不小于before，没有核操作的精确转换。一个schema合法reset回执若返回原epoch/generation和原principal，helper返回true；后续GET current若仍为原context，UI会显示“当前演示空间已重置”，虽然没有epoch/generation推进。reset响应也可更换principal；persona可跳epoch，仍被接受。这不是服务器提权结论，而是前端已有成功边界检查漏掉已冻结的操作语义。

最小修正：reset必须同tenant/org/principal、epoch=before+1、generation=before+1；persona必须同tenant/org、epoch不变、generation=before+1，并在GET current后核persona_id等于本次选择的目标（principal由服务端可信结果给出，UI不推导授权）。logout保留现有严格不变代际/主体与LOGGED_OUT。失败保持原key/UNKNOWN，不重POST。补“零推进/跳跃/错误reset主体/错误目标persona”的拒绝用例，而非只对租户错位作负例。

已准c4方案允许同persona控制也generation+1，但UI可选择禁止无操作切换；该取舍不需要放宽上述成功断言。

## WEB-03 [P2] 店铺读取失败未立即失效已显示的身份边界

位置：`demo.tsx:22` chooseShop的catch及非OK结果分支，相比`:20` refresh的clear。

seed-summary收到401/403或schema/传输无法验证时，当前实现只setSummary(null)并提示，仍保留session/current/selected及角色、店铺、CSRF控制界面；依赖后续5秒current轮询才可能清屏。若schema合法但status为UNKNOWN，成功条件不成立却无明确失效动作。用户在这段时间仍能用已失效/未验证context发控制POST，这与UI合同“401/403清屏、无验证不复用旧context”不一致。

最小修正：对最新请求的401/403及无法验证身份的响应统一clear/invalidate当前敏感状态，不自动登录/POST；UNKNOWN明确提示并只走current重新核验。对确定的404店铺无权可保持会话但清该店结果和选择（不能泄漏）；不要把所有业务404都强制登出。补当前seed read返回401/403/UNKNOWN后立即无敏感身份/控制按钮与无后续POST的用例，不能只测试current端点过期。

## 原WCTX-01关闭及实际上下文接线

`v4-context.mjs:7–19`加入完整strict Context格式/required/extra校验，sameIdentityContext:22–28先验证两边，再比较身份与代际。createContextGate:37–49也拒绝缺字段、错误shop与错误响应。

主UI并非依赖未使用的createContextGate来声明安全：它从v4-client对整个Envelope做strict验证；refresh:20维护递增seq、当前session、hidden/offline拒绝；chooseShop:22实际调用sameIdentityContext比较请求快照、current与响应，另核shop/选择/序号；control/create使用matchesControlBoundary/matchesCreateBoundary。故旧“undefined===undefined”路径已关闭，现WEB-02/03是独立语义缺口，不回写WCTX首审。

## schema/client/origin检查

独立标准库JSON比对确认：`v4-schema.json`精确等于冻结OpenAPI全部18个components.schemas仅将内部ref改为$defs后的对象，无删字段、extra放宽或格式丢失。生成脚本仅作该映射；OpenAPI测试也要求deepEqual及18个均可编译，但本轮未执行Ajv。

v4-client:10–15采用Ajv2020 strict+formats；allowUnionTypes用于冻结union，不关闭additionalProperties/format规则。失败必须FailureEnvelope，成功按指定schema验证；fetch credentials=include/cache=no-store，15秒AbortSignal封顶且合并parent信号，不自动重试POST。成功HTTP状态使用response.ok而不是operation/status枚举，当前主流程还需语义判据，上述WEB-02必须补齐；不宣称已有完整HTTP状态合同测试。

origin来自服务端COMMERCEOPS_API_ORIGIN，不接受URL参数/浏览器任意地址；approvedApiOrigin要求纯origin、无userinfo，HTTPS或显式local_http loopback，无默认fallback。浏览器自发Origin、后端CORS/Host/CSRF仍需真实Gate，客户端不伪造Origin权限。没有新真实provider/Woo/外发调用。

## UNKNOWN、bootstrap及多标签

pending storage仅保存operation/key，不存token/CSRF/身份，坏JSON/不可读storage失败关闭；写请求前remember持久key、actionLock防连击。创建/控制失败不自动重新POST，恢复仅GET current/operations并核原operation/key；logout不能因401本身写COMMITTED。确定429/REJECTED才清pending并允许用户再次进入，新key不自动发送；后端Q18的新bootstrap细化仍需精确实现和真实运行，不由fixture成功代签。

创建使用bootstrap CSRF后POST，active恢复使用GET；最小bootstrap恢复不展示tenant。放弃核对按钮明确用户动作且不宣称旧事务回滚，实际是否能新建取决于后端当前cookie阶段，不能由文案承诺旧active已撤销。

BC只作为invalidate信号、清屏后GET current，不从消息授予身份。hidden/offline清敏感状态，focus/visible/online恢复先核current；已知active且无pending才每5秒核验。控制开始清屏/关闭dialog/广播，延迟读用seq挡住。首次开发React重连可能额外GET是只读现象，不等于自动POST；保持Root首22pass2fail、后定向2pass与trace作为分层事实，不预写正在运行的完整ac1结果。

## 路由、视觉与测试范围

App Router入口只允许/v4、/v4/demo、/v4/settings/demo，其他notFound；未替旧catch-all、未抢14模块导航/经营KPI。六卡明确规划中，不计业务页/六链已完成。

native dialog使用showModal、labelledby、默认Esc和onClose焦点回归，失效clear关闭dialog；CSS有focus-visible、窄屏sidebar隐藏/单列、select宽度约束及reduced-motion。未据此声称实际1440/1280/390或200%缩放/Tab陷阱验收，截图和实际操作仍由本次明确来源证据证明。

welcome.spec使用route.fulfill/abort+fixture CORS，属于UI_FIXTURE；冻结数据/任意status不是真实鉴权。已有fixture覆盖迟到店铺、跨tab、UNKNOWN、reset/logout、focus/Esc、current失败与边界错租户；尚未覆盖本报告三个真实源码问题。client/context/openapi纯测试也不代替真实cookie/服务器/PG。Root转交的trace与局部运行结果未在本审查复跑，原失败保留。

## 交接

请作者修WEB-01/02/03后普通提交精确SHA；仅改WEB独占路径及对应验证，不为过fixture放宽后端或冻结schema。Reviewer只提交本报告，未改实现/测试、未运行服务。实际SQL86三项阻断与seed验证待修独立保持，UI准备接受不能代签这些Gate。


## 63a增量复审：WEB-01/02/03关闭

日期：2026-11-03（Asia/Taipei）。**结论：ACCEPT_PREPARED_UI（静态准备代码范围），本次增量0 P1 / 0 P2。** 首审三个P2逐项关闭；保留上文ac1时点的发现与运行缺口，不把本结论记成真实鉴权、API/PG或整阶段验收通过。

精确链：`ac1d18e23d3235b23fad90ecfe1e4caf051f72bd` → `bb4d6e48b6413f3b3735efa6f05e2090d8d4323e` → candidate `63a5a4f08bad6b98fe95942598291e0714bc09da` / tree `97425fb41939d9dfe7d5df74cd6889ae14c8e094`。独立读取以上Git对象的7文件增量及最终helper/client/主组件，不读取作者WIP，不切作者分支。以下行号绑定63a；主组件长行同时以函数名定位。

### WEB-01：CLOSED

`demo.tsx:26`的select和当前persona集合统一为`restricted_admin`，`:24` control直接使用选择值构造persona_id；未增加后端admin别名。新增浏览器fixture明确断言发送restricted_admin，但该fixture随后主动abort，证明范围仅是请求值及UNKNOWN处理，不能记成管理员完整切换成功。实际成功路径另由精确转换与current目标核验约束；shops为空仍显示reset/logout，店铺选项为空。源码缺口关闭，完整管理员成功浏览器证据本轮未执行。

### WEB-02：CLOSED

`v4-context.mjs:60`起matchesControlBoundary要求原与返回Context完整、session级shop为空、tenant/org相同、原operation/key和COMMITTED回执匹配、回执代际与返回一致且计数为安全整数。reset严格同principal、epoch+1/generation+1；persona严格epoch不变/generation+1及不同principal；logout保持同principal/原代际和LOGGED_OUT。

同目标persona在`demo.tsx:24`函数入口明确拒绝，`:26`按钮也禁用。故63a的不同principal要求适用于此UI允许的切换；不据此修改后端允许同目标控制的合同。新fixture的合法persona响应也改为不同principal，未以放宽helper来适配旧fixture。

实际control先保存非秘密原上下文proof及原key，再清屏并POST；只有boundary通过且随后GET current通过matchesControlReadback才清pending/显示成功。读回同时要求同返回身份/代际、原creation_request_key、reset原persona或persona精确目标；错误/零推进/跳跃保留UNKNOWN和原key，不自动重POST。

恢复路径也实际接入matchesRecoveredControl：原proof、原operation/key、精确变化、current及目标共同核验；缺proof的旧pending仍可读取但不能签reset/persona成功。logout恢复不以401或任意current签COMMITTED。session_create仍按原creation key及回执/current代际核验。这里的证明依赖服务端可信回执和current，客户端proof仅为比较快照，不是授权来源。

`v4-pending.mjs`新记录增加严格4字段proof（context、creation_request_key、persona_id、target_persona）；不存CSRF/bearer/权限数组。因此上文“pending仅operation/key、不存身份”只描述ac1，63a已保存非秘密身份标识及代际到sessionStorage。旧两字段兼容，坏proof失败关闭，session_create拒绝proof。

### WEB-03：CLOSED

`demo.tsx:22` chooseShop在当前请求非OK、上下文不能匹配、schema错误或网络异常时调用clear，立即清current/session/shop/summary并关闭dialog；401/403还失效activeKnown并广播。后续重新展示依赖current只读核验，不自动登录或控制POST。当前404同样保守清屏而未声称已登出，属可用性取舍，不形成旧身份复用。

迟到成功由seq拒绝；迟到非OK/异常仅在shouldClearSummaryFailure核得原tenant/org/principal/epoch/generation仍相同且仍选原店铺时清屏。故轮询推进seq但身份/店铺未变时不会吞掉失败，已切换新身份或其他店铺则不会被旧失败清除。helper刻意不以authorized_at变化判成新身份，与现有身份边界定义一致；这不是撤权即时送达或实际浏览器时序已验证的结论。

### 静态验证和未运行项

读取了新增/调整的纯测试与UI_FIXTURE定义：精确reset/persona转换、相同principal拒绝、安全整数、目标和creation key读回、proof恢复、迟到失败边界，以及summary 401/403/UNKNOWN/MALFORMED、restricted_admin请求值、零推进UNKNOWN、带/不带proof恢复。纯helper覆盖不冒充浏览器端到端：新增迟到失败的身份/店铺矩阵主要是helper测试，新增管理员用例是abort路径。测试定义本轮全部NOT_EXECUTED；未运行Node、Playwright、构建、API、PG或服务。

本次仅提交审查文档。ROOT独立不可变UI_FIXTURE结果应另绑其实际SHA、命令、退出码及失败记录；真实cookie/CSRF/鉴权/数据库Gate与owned PG窗口独立，不能用此静态接受代签。不push、不触Hosted/PR、不访问真实外部服务，不进入V4-1。
