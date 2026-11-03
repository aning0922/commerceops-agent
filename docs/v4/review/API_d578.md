# V4 d578会话/API/owner CLI主体独立审查

日期：2026-11-03（Asia/Taipei）。**结论：P1_REQUIRED_CHANGES，1 P1 / 0 P2；暂不签ACCEPT_PREPARED_API。** 四个主写端点的合法JSON请求在进入Store前被422拒绝。此为精确源码纯ASGI复现；没有连接PG，不据此判断实际SQL根因。

## 精确范围与复验载体

candidate `d57808f0627821ab202e054e7d464fa2d4b9798c` / tree `0bb6bf997c0b5c37abd3381246d361211974b8ff`，本提交7文件：原api.py最小装配、新v4_demo_http/sessions/store、显式seed CLI、启动合同§14及19项ASGI定义。完整读取提交对象，另读其固定DTO、原web_config/web_sessions/security、v4_demo_seed及baseline合同以核接线；未读作者新增PG测试WIP。

独立复验将该SHA的backend/src与已提交test_demo_api.py导出到Reviewer `.audit`独占临时目录，使用现有control虚拟环境的Python/已安装依赖，显式sys.path优先加载该精确快照并核模块__file__。依赖版本FastAPI 0.142.4/Pydantic 2.13.5。子进程环境仅PATH/PYTHONDONTWRITEBYTECODE，不继承owner DB配置；用作者显式StubStore和TestClient，未启动监听服务。临时目录已清理。此方式没有把其他工作树的源码证据移作当前候选证明。

## API-01 [P1] strict UUID DTO经FastAPI Python解析导致全部POST不可用

位置：`backend/src/commerceops/entrypoints/v4_demo_http.py:118–125` create；同类入口`:153–160` persona、`:164–171` reset、`:175–182` logout。相关固定DTO Contract(strict=True)与request_key:UUID位于application/v4_demo/contracts.py。

这四个函数把strict DTO作为FastAPI自动body参数。FastAPI先将JSON解为Python dict，再作Python模式模型校验；合法JSON里的UUID只能是string，但strict UUID的Python模式要求UUID实例。DemoRoute提前调用body仅验证原bytes的重复键/大小/content-type，没有把后续typed参数切到model_validate_json。因此客户端按冻结OpenAPI发送规范UUID仍得到INVALID_REQUEST/422，完全进不到create/control。

独立实际纯ASGI结果：给明确可信Origin、合成CSRF、规范UUID request_key，create带固定fixture，persona/reset/logout带整型0的epoch/generation及各自合法字段，**sessions/persona/reset/logout四条均422/INVALID_REQUEST，StubStore.calls始终[]**。未使用非法值来制造拒绝，也未读取真实cookie或secret。19项作者ASGI主要覆盖GET、拒绝和schema声明，没有任何合法POST应进入Store的用例，故它们通过不能关闭此缺陷。

最小修正：沿用旧replenishment_http已有的严格JSON解析方式，在四个端点对经body检查的原bytes调用各自DTO.model_validate_json（或等效且保留strict语义的专用dependency），同时明确维持独立OpenAPI的requestBody/schema。不要全局关闭strict或允许任意字符串转换来换取通过。补四个合法JSON POST确实到达stub业务层且值为UUID/精确DTO的用例；保留无Origin、无/错CSRF、重复键、extra字段、bool/浮点代际、非法UUID拒绝。后续PG测试即使直接构造UUID对象调用Store，也不能代替这个HTTP入口正例。

## 已核：独立bearer和完整身份闭包

公开cookie commerceops_v4_demo、Path=/api/v4、v4b_/v4d_+43字符；前缀总长47，而旧SessionStore._session只接受43字符。公开hash查V4专表，私有bound使用另一个随机token的hash且不返回其明文；复制cookie名不会通过旧形状检查。本轮为源码证据，实际浏览器改名401仍须PG/API Gate。

resolve_locked按公开token找到tenant后，tenant FOR UPDATE→session FOR UPDATE；核未撤销、绝对expires、相同deadline/epoch、key_version。persona映射绑定tenant/org/persona/principal/identity；credential查询复制旧完整principal→identity→web_credential连接，要求当前enabled、provider=web及精确org/主体/identity，随后比auth_version。target persona时先按principal UUID排序share锁，再锁原bound；重复获取当前principal是已持锁，不另建反向锁序。

bound检查kind/撤销/主体四元组、expiry上界与当前DB时钟、keyversion、不同于公开hash的私有token_hash、原P3 CSRF digest；公开Demo CSRF另绑定sid/nonce/epoch/generation。之后仍调用旧actor_guard，店铺用真实role_scope，而不是将persona名称直接视为授权。session_data只列有operator/approver实际scope的映射店，restricted_admin不隐式得到业务店铺；summary先限本tenant映射再查实际scope，错误目标404无payload。current/summary返回前再resolve，成功时钟来自DB。

上述是静态完整性核查，不签credential撤销/identity重映射竞争、旧actor失效、权限锁函数和SQL触发器的实际线性化。数据库约束与旧trigger运行行为须独立PG证据。

## 已核：控制、CAS和UNKNOWN恢复

create只接受bootstrap token及其当前CSRF，先独立事务固定该owner的create_request_key，之后rate/hash限流，再在全局capacity锁及bootstrap行锁下复核原key/未consumed。容量是未撤销未过期tenant/session的3上限，额外返回CAPACITY_LIMIT和按DB expiry算的正Retry-After；bootstrap最多128、peer窗和hash semaphore另限，失败不重试。原key预留是有意持久状态，不把429/失败写成创建已回滚或允许改原owner key。

bootstrap复用仅valid且未绑定key的owner；已绑定key显式新GET发fresh owner；有效active拒绝，过期/撤销active只有请求新的bootstrap时才进入新匿名流程。该HTTP函数不推断“真人点击”，明确用户动作由WEB负责，UNKNOWN客户端不能自动调用新bootstrap来掩盖原请求。

control先完整current/target认证与当前CSRF，再查稳定session owner+operation+key回执，digest同文才回原receipt、异文409；无回执才CAS。reset只删本tenant overlay、同persona、epoch+1；persona epoch不变，两者generation+1、旧bound撤销、新bound/CSRF/receipt/event同事务；原30分钟deadline不延长。logout撤销bound/session/tenant，不虚增代际，清V4 cookie；响应context是提交前身份而非新授权。connect上下文正常退出COMMIT后才交HTTP；commit异常走UNKNOWN/503，不自动重POST。

GET operations的active分支要求完整当前授权且只查原session owner；bootstrap仅未过期/匹配CSRF来源的原owner及精确session_create key，返回COMMITTED/OWNER_RECOVERY_REQUIRED或UNKNOWN/WAIT_READ_ONLY最小字段，不返回tenant/新bearer/CSRF。原key缺行保持UNKNOWN语义；logout或已失效active的401不冒充COMMITTED。实际ACK body丢、cookie/header整体丢、并发reset旧CSRF403、同key一effect仍NOT_RUN。

## 已核：Origin、装配与OpenAPI

V4独立boundary只作用于/api/v4/demo/；POST必须显式可信Origin，CSRF由Store当前持久身份校验。无Origin GET仅精确配置Host+scheme且Sec-Fetch-Site=same-origin，显式local_http测试例外才允许无fetch header；不读取X-Forwarded头授予例外。CORS显式origin/credentials、Cookie no-store、HttpOnly/Lax/HTTPS Secure均接线。原P3中间件的鉴权仍限定/api/v1，不用新V4边界替代它。

create_app默认None、enabled=false不装配；foreground仅新COMMERCEOPS_V4_DEMO_CONFIG_FILE开关。新配置检查v4_demo_库名、可信API origin/transport和私配文件；复用private_bytes逐级无symlink/0600/当前UID以及两份不同的至少32byte秘密读取。运行对象/host/owner环境隔离仍由ROOT §14新窗口绑定，库名前缀本身不是新资源授权证明。

装配在旧schema导出完成之后，独立app.state.v4_demo_openapi，未新增公开/docs或/openapi URL。纯生成核实8条路径与冻结baseline相同，cookie、POST Origin/CSRF、summary代际header均声明。**不宣称生成产物与baseline字节/组件/operationId相同**：FastAPI自动operationId、额外请求/泛型辅助schemas与基线命名有差异（18个baseline schemas对26个generated）；当前测试只证明八路径及安全声明。这些差异应在后续精确导出/QA接入时明确，不能用“八路径相同”冒充完整contract diff通过。修API-01时尤其需保留requestBody文档。

## 已核：显式新owned CLI及边界

scripts.v4_demo_seed固定四action，先要求v4_demo_库名；init/grant/gc调用原V4 helper，实际owner/revision/PG+vector版本由helper核验，原database grant-runtime不会自动给V4授权。verify是只读精确canonical fixture/hash对照，不证明其他权限已配置。

init导出目录必须全新绝对路径，逐父目录dir_fd/O_NOFOLLOW，新目录0700；content/manifest独占创建0600+fsync。DB先COMMIT后写文件并link发布MANIFEST，失败保留原DB和未完成目录，不重试覆盖；这不是DB/文件跨资源原子提交。gc仅显式tenant参数交原owner helper，本轮没有运行GC，也不签所有旧业务依赖/retention和删除顺序的实际验证。§14只列init/grant/verify启动流程，不是允许执行GC的资源窗口。

实际启动应使用新owner初始化与runtime API环境分离、同批新配置；原/api/v1对改名bearer的拒绝需要同时装配新库P3路由，404不能当401鉴权证据。没有新增Worker/Graph/provider/外发、自动迁移或服务拉起。

## 交接及未运行证据

请作者只修API-01及相应合法HTTP正例，普通提交精确SHA复审。19项stub ASGI不是PG鉴权，新增PG测试尚WIP未读取。原首窗migrate exit1/0tests、cleanup及SQL根因UNKNOWN保留；已独审安全诊断入口不改变本API候选状态。本轮没有实际PG、Docker、原配置/凭据读取、API监听服务、Hosted/push或V4-1操作。审查只提交文档。


## 534增量复审：API-01关闭

candidate `534844a848b7e4412a6b4b2ff178f7d0aa56c82e` / tree `ae03e8b997813c4db31a564ee76ee848d86bb162`，精确parent `12081e4f7dd326611b2be001aca4ed9a22acb9d1`。本次只审两个文件的JSON wire解析和对应ASGI增量，不把父链31d PG测试或1208 SQL修正当成本轮新审范围。**结论：API-01 CLOSED；解析增量0 P1 / 0 P2，原d578主体在此修正下可记ACCEPT_PREPARED_API，但不签PG/实际API Gate。** 原d578四POST合法UUID被422拒绝的P1与独立复现完整保留。

四个POST函数去除FastAPI自动typed body参数，改为各自调用read_command(request,精确DTO)，内部先await原body(request)，再model_validate_json原bytes。重复键、media type、字节上限、非有限JSON常量校验仍经过原body；DTO strict/extra=forbid及UUID/整型约束未放宽。DemoRoute不再预读body是去重，四个POST实际各自明确读取，不存在漏接端点。Origin中间件和Store当前CSRF/身份/CAS未改。

四个router decorator增加openapi_extra=request_body(精确DTO)，required=true且application/json schema与该DTO.model_json_schema逐一相同；因此手工解析没有丢失requestBody合同。前文生成OpenAPI与冻结baseline的命名/组件差异说明仍保持，不把此验证说成整份文档字节一致。

独立将本SHA backend/src和已提交test_demo_api.py导出至Reviewer临时目录，使用既有依赖Python（FastAPI 0.142.4/Pydantic 2.13.5），仅快照源码优先导入，环境不含owner DB变量；执行精确单模块全部 **38 passed / 2.02s / native0**（原19+合法POST4+严格counter负例15）。测试是StubStore ASGI，不监听服务、不连接数据库。还独立覆盖四端点的合法请求：到达Store时均为准确CreateSessionInput/PersonaInput/ResetInput/LogoutInput，request_key为UUID，控制expected_epoch/generation为非bool的int；四条随后由stub返回SESSION_INVALID/401，证明已越过解析而未假称鉴权成功。该追加typed探针native0。

原38项保留无Origin/恶意Origin、extra/无效UUID、重复键/content-type及缺失/错误代际等拒绝；新增15项覆盖三个控制端点epoch=True、字符串0、浮点0.0、负数、null仍422且不入Store。pytest和probe临时文件已清理；没有编辑作者实现、测试或读取WIP。

ROOT另转交candidate46164111/tree4175d5ba原native migrate0/no tests/cleanup all0及新owned SQL5+旧schema1窗口安排，此处只记转交事实，Reviewer未复跑、未据此签API/SQL整体验收。823b第五访客及后续PG测试不在本解析delta结论内；实际运行结果应由ROOT绑定各自源码/命令记录。
