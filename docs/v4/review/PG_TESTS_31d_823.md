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
