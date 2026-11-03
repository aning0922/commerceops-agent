# V4作者身份PG测试31d/823组件独立审查

日期：2026-11-03（Asia/Taipei）。**结论：ACCEPT_PREPARED_PG_COMPONENT，当前14节点可进入ROOT登记的新owned组件窗口；静态范围0 P1 / 0 P2。** 本结论不是14节点实际PASS，不签并发、完整rollback、HTTP/browser、旧M3 Full或整个身份矩阵完成。当前切片无需先改测试才能运行，缺项须保持独立待验。

## 精确对象

首包 `31d11cc76c13a7a56afc5fec541b1657dc747cab` / tree `a39381825d0d4c04ad3ae93fdcef1794296a3d38`，parent d578，只新增`tests/v4/test_demo_sessions_pg.py`。增量 `823b132766184b3f35b93d0e306f4182da23ce38` / tree `c169274050f09e95381ca4f42a1bc89498491322`，parent534844a，只将容量测试第四访客扩为第四及第五。读取精确提交及所调用initialize_schema/原grant-runtime/新V4 helper/既有表约束；未读取作者新增rollback测试WIP。

独立从823精确源码快照导出依赖，在Reviewer临时目录只执行本模块collect-only，psycopg.connect额外设为禁止调用，环境不含DB配置。**14 tests collected / 0.83s / native0**，无任何fixture执行、DB连接或服务启动。临时目录已清理。此为可收集证据，不是运行通过；实际测试必须在ROOT完整集成source（含已接受534解析和1208 SQL修正）及新owned环境下执行，不能直接用31d旧SQL父链冒充修后源码。

## fixture与资源边界

每个case从显式DatabaseSettings读取本窗口base新PG环境，要求runtime_password_file存在；随机生成`v4_demo_<uuidhex>`独立数据库，用sql.Identifier构造CREATE DATABASE。setup在新数据库上执行initialize_schema(owner,head)，该helper真实Alembic迁移、setup_checkpointer、原grant_runtime；再owner initialize_fixture及独立grant_v4_runtime。没有Fake SQL/连接或自动skip来替代这一路径。

业务app配置明确user=commerceops_app、password_file=runtime_password_file、runtime_password_file=None；DemoConfig、DemoStore及HTTP安装均引用这一app配置，不传owner作为runtime。旧grant_runtime固定ALTER/CREATE commerceops_app为NOSUPERUSER/NOCREATEDB/NOCREATEROLE；但本测试模块本身没有再查询current_user/pg_roles/table owner作实际角色证明，ROOT运行回执应绑定这些真实低权事实，不能只凭变量名app签权限Gate。base owner环境仍须由ROOT保证是新owned实例及独立owner，库名随机前缀不是允许连接旧PG的授权。

owner用途明确：新库schema/fixture/ACL初始化、7个撤权或损坏场景的造态、两tenant overlay准备。随后所有current/control/summary、旧actor_guard以及业务计数读取均走app。owner插入overlay是测试前置条件，不证明runtime具有INSERT overlay权限（本切片本来只要求runtime reset DELETE）。7个owner UPDATE造态也不能记作runtime写这些表已获授权。

finally仅DROP本case随机新库WITH(FORCE)，未删除base库/卷或采纳别人的进程。CREATE失败在try之前不会执行DROP；CREATE成功后的setup/test失败仍尝试DROP。DROP失败将真实暴露teardown失败，不被吞掉。外部PG/卷/进程与绝对UTC/reserve由ROOT负责，本模块无自带服务启动、截止或cleanup证明。由于setup会迁移完整head，每节点耗时尚待本次实际测量，不预签现有300秒或整包预算可容纳。

## 14节点的实际测试意图与证据上限

| 节点组 | 数量 | 当前覆盖与限制 |
| --- | ---: | --- |
| current/scope/summary/旧cookie改名 | 1 | 实际Store双店summary；TestClient实际PG GET current及旧/api/v1已注册路由401；tasks/jobs=0。无监听API/真实浏览器 |
| persona→restricted_admin→reset | 1 | 原actor_guard拒绝、admin无shop、deadline不变、epoch/generation、旧CSRF拒绝和用新CSRF原key重投不再推进；串行 |
| bootstrap复用/绑定429/新owner/UNKNOWN | 1 | rate方法一次合成429注入，但bootstrap原key预留真实PG提交；验证原key UNKNOWN、错key404及active bootstrap拒绝。非真实rate限额测试 |
| 创建cookie丢失后的最小恢复 | 1 | 显式保留原bootstrap token调Store，验证最小字段/原owner禁止再create/active禁止create；不是实际网络丢Set-Cookie/响应中断 |
| credential/bound失效 | 7 | owner造credential disabled、identity provider变化、principal disabled、bound CSRF/key/revoke/expiry后，app current拒绝；每例独立新库 |
| 三个活跃+第四第五拒绝 | 1 | 先串行建3，再串行拒绝2；前三仍可current，tenant不同，跨shop和跨owner key404；非五个并发请求 |
| logout及无恢复特权 | 1 | Store logout回执/随后current和operation401、新匿名bootstrap；未测试HTTP delete-cookie属性或丢ACK |
| reset租户隔离 | 1 | owner为两tenant各写overlay，runtime只清第一tenant，第二数据/代际不变；无并发写入 |

模块没有skip/importorskip/xfail或捕获全部异常当通过，缺配置/权限/连接/SQL错误都会失败。7个失效场景只要求最终SESSION_INVALID，不证明每个独立谓词单独负责拒绝：例如credential/identity变化可能通过旧trigger推进auth_version或撤销session，因此不能用一个401代签完整身份JOIN各字段的独立反例矩阵。这个限制不妨碍先运行组件。

## 明确保留的覆盖缺项

- **并发未覆盖**：无线程/屏障/多进程请求；五个并发create恰3成功、capacity锁竞争、并发reset同key一次effect/旧CSRF403、reset与read/owner撤权/overlay写的竞争均不能从本14节点推断。
- **事务中途rollback未覆盖**：现429在独立key预留后、业务provision之前注入，只证明预留后UNKNOWN路径；没有在持久化中途真实PG trigger故障并核完整回滚。ROOT告知作者正在补此项，但WIP未读、未预签。
- **异文与完整幂等审计未覆盖**：现同key同文串行重投仅核receipt epoch和current epoch，没有独立计数全部receipt/events/一次effect；原key异文冲突及before/after业务快照需后续精确测试。
- **身份/权限矩阵未齐**：缺identity/principal/org重映射各字段、公开session CSRF/key、target persona撤权、去scope、同persona切换、bootstrap过期/单key跨operation、完整TTL容量释放等分支。新grant前后逐表/列/function与runtime拒写反例也不在本模块。
- **真实HTTP/UI未覆盖**：绝大多数通过Store直接传UUID DTO；其中TestClient只验证GET与旧cookie改名。534的38纯ASGI入口修复证据独立保留，二者不拼成真实POST cookie/CSRF/CORS/browser验收。
- **旧M3 Full未跑**：这14节点不减去或替代旧动态PG集合/其他质量Gate；schema首6节点成功也不代签本14节点。

## 交接

ROOT可以按其已登记新owned资源、owner/runtime分离、精确集成source和绝对截止运行这14节点并收setup/call/teardown/native/cleanup事实。测试退出、清理失败或超时按实际保留，不以collect14补签call14；不自动续窗或重试。Reviewer本轮仅普通提交本报告，无PG/Docker/API服务/外部provider/Hosted/push操作。后续已提交rollback/异文切片由ROOT另交精确SHA审查。


## dc439增量：真实事务中段故障与reset原key不变量

candidate `dc439e92ea561ea7d0c95e7ef255d0fc7237f26a` / tree `501a653ca1e23bc66187505cbe35b41b34d27dd0`，parent823b。**结论：ACCEPT_PREPARED_PG_COMPONENT_DELTA，新增2节点可进入ROOT新owned组件窗口，0 P1 / 0 P2。** 实际diff是两个原文件各新增一项：seed_pg的provision故障、sessions_pg的reset原key，不是seed_pg单文件两个case。旧14节点的运行结果和缺项不被改写。

### provision中段故障：准备代码范围接受

`test_demo_seed_pg.py::test_seed_native_mid_persona_failure_rolls_back_but_preserves_reserved_key`复用已审demo新库fixture。owner只在该新库安装有固定search_path的测试trigger/function，并撤去PUBLIC/runtime直接EXECUTE；实际调用仍是runtime DemoStore.create→原SECURITY DEFINER provision。trigger由该provision的有效owner执行，不是给runtime旁路授权。

注入点是v4_demo_personas的approver BEFORE INSERT。已核原0024执行顺序：此前已插入新org/tenant、两店及映射、完整operator的principal/identity/scope/grant/credential/persona，并已插入approver的principal/identity等。trigger先核两店、operator persona存在及当前org恰两个principals，不符抛独立P0001；正确中段才抛固定23514。测试同时要求CheckViolation、SQLSTATE23514及精确固定message_primary，因此一般约束失败/错误阶段不能冒充目标故障命中。此处是待执行的真实PG触发器，不是Python monkeypatch或HTTP替身。

失败后新连接核15个物化表行数与此前相同，覆盖org/shop/principal/identity/scopes/grants/credential/bound/V4 tenant与映射/session/receipt/event/overlay；再由runtime读bootstrap，要求原create_request_key仍在、consumed_at为空，并GET原key得到精确UNKNOWN/WAIT_READ_ONLY最小字段。bootstrap/rate刻意不在物化计数中，符合独立admission已提交而业务事务回滚的合同。固定fixture本身未重写。计数相等只支持此全新库case的无部分物化，不代签任意既有行字节保持。

finally显式DROP测试trigger/function，随后再次只读核原key UNKNOWN；换新key的同owner create必须RESOURCE_NOT_FOUND且15表计数仍等于before。没有移除故障后自动重投原POST，不以清理trigger授予重试权限。测试对象全在新库，外层demo fixture仍负责最终DROP该随机库；任何安装、断言或清理失败仍真实失败，运行回执须记录。

### reset原key：准备代码范围接受

`test_demo_sessions_pg.py::test_reset_same_key_payload_once_changed_payload_conflicts_and_other_tenant_stays`串行建两个tenant；第一tenant reset后，用当前新CSRF重投相同原key/原body，要求完整receipt相同。再保持key而将expected epoch/generation改为当前1/1，要求IDEMPOTENCY_CONFLICT，故不是仅因旧CSRF或CAS不匹配拒绝。随后核current epoch/generation仍1/1、runtime计本tenant reset receipt=1及reset_committed event=1；第二tenant data及tenant/org/principal/epoch/generation均不变。该case补齐串行同文一次回执/异文拒绝及对另一tenant无影响的断言。

### 独立收集与边界

Reviewer从dc439精确对象导出，在禁用psycopg.connect的collect-only子进程中收集全部sessions模块15项+仅新增seed fault节点1项：**16 tests collected / 0.86s / native0**。未执行任何fixture/PG/trigger/服务，临时文件已清理。旧seed模块已有5项SQL反例未在此次16节点重复计数；若ROOT另选整个seed模块，节点集合须按实际命令另记，不能混称16。

新增两项尚未实际PASS。它们只为一个provision中段回滚点和串行reset幂等补证，不补齐所有持久阶段故障、commit后ACK丢、实际HTTP recovery、并发create/reset、撤权竞争或旧M3 Full。owner/runtime实际角色核验、精确集成source、UTC/reserve与cleanup仍按前节ROOT运行合同；本次无新资源授权或自动重试。当前新增2节点无需先改源码即可运行，后续以实际setup/call/teardown/native/cleanup记录判定。
