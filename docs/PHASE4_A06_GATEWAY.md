# A06原官方SDK正式业务consumer的有界生命周期候选

parent业务前层为已审e7/06cd及b0读取强约束与b4薄Compose源码；本批仅离线WIP，不启动PG/SDK/WS，不读取真实App Secret或旧私配。Root明确正式WS复用P1受控child/官方SDK/BusinessGateway，defaultoff、auto_reconnect false、≤5min wall-clock stop/wait/reap，独审与停止机制核实后才实际窗口。当前M1/Phase4/真实SDK发送与human未验收。

## 最小入口与原业务

原feishu_business入口追加gateway，需要--live与private GatewayWindow enabled（默认false）；schema p4-gateway-v1/id/org/shop/awareexpires/原Mock Parameters、max_callbacks≤100/max_workflows≤5。只同Root受控单部署/同PG单App：child使用本进程同步PG连接取得app namespace advisory session lease，与唯一Worker Graph的原锁独立、不启动另一个Worker；不跨event-loop/process借WorkerSession/AsyncConnection。原audit_events固定window UUID primary key记gateway_start_claimed，原不可变审计保一次claim；同ID二次/并发claim拒绝，不能重开预算或SDK重连。

原PG org/app/tenant/shop的Mock/test严格匹配后才claim+读单App Secret。child restrict_sdk_logs在读任何私配/秘密之前禁原Lark/websockets/httpx/httpcore/urllib3/psycopg与传播；原官方lark.ws.Client/BusinessGateway dispatcher、不全局SDK monkeypatch、auto_reconnect=False。SDK1.7.3 start永久阻塞且无public close，parent提前留10s停止reserve，固定expires绝对截止内terminate→wait→必要kill→wait/reap；不自动重启/续window。child还设置原绝对期限OS alarm，使直接误用也不能无限socket，但结果未知，仍需parent/Root核OS消失。

FeishuBusinessStore只增加可选服务端gateway_guard，默认None，原offline21/已有CLI不激活；当前guard在原transaction检查窗口/过期，T1新workflow前查本window claim后原P4inbox对应distinct workflows≤5，旧message/event replay仍原持久回执、不占新workflow；clarification不生成business task，T3仍原role/nonce/hash/version/chat/message/live binding。没有第二状态机/dispatcher/跨库网络、旧outbox升级、sender权限或新模型。callback admission仅当前SDK业务handler调用上限，不称raw收到帧；一次window拒绝复用，唯一App同步callback loop不并行新T1。

PG lease只保护这个已授权单受控部署，不能宣称跨不同PG/主机/生产全局唯一；Root实际放行须确认这个App没有其他consumer，并只用同一个已核资源包。既有P1资源保留、不调用或篡改其SDK模式，未经Root事实不能猜它已经停止。该窗口没有HTTP sender/worker自动外写；正式Base/IM原单Worker与持久SDK账本另按明确Gate/caps装配。

## SDK源码结论与实际证据

本地锁定1.7.3源码_connect为requests.post endpoint发现+websockets.connect，start/receive_loop异常在auto_reconnect=False不重连；SDK CARD transport branchreturn和正式card event实际路由均须后续真实Gate，不用offline证明。源码不等wire事实：现8HTTP方法账本不统计WS发现/握手/原始收帧/ACK，parent安全summary全部not_verified，不能报0/1或把admission当物理帧。重定向/自然断线/握手实际次数尚未验证；SDK原文日志抑制、child stdout/stderr不输出，root平台secret/定位/事件raw/URL不入Git或日志。

当前新6offline实际4.09s：窗口不能超100callbacks/5workflow/不接受bool计数，默认off不spawn/读App Secret；实际普通sleep child（非SDK）固定期限terminate/wait/reap、WS counters保持not_verified，admission cap不fake frames。初作者Ruff长行/排序/S603识别修订保留，当前固定executable/module+verified paths且no shell；该必要单行标注不是关闭全局检查。PG app lease/一次claim/guard quota仅源码，真实PG尚未运行；新SDK/真实auth/WS/旧私配均0，不能拿Author普通child测试签平台窗口。

整1378offline实际91.42s/375integration deselected、256mypy/352format/Ruff/92MD0；定向原Gateway/preflight/lifecycle合36pure4.59s，源码freeze与三scope扫描再精确绑定。PG lease/claim/quota仍未运行，任何真实SDK0。不混原p4read两轮失败镜像或旧CI。源06cd current34 read修复已由Root核精确CI38120338660全4SUCCESS/375完整union，但不等M1或A06；旧失败/metadata not_run/role未实际核仍保。日期、原300h/人工H-L未报告、原D1/D30、M1设计18页、旧资源/凭据/卷不变，生产/Woo/Phase5/paid/新scope未授权。

Root已核精确4654809原Core noP1/P2/80pure4.40s/type5/Ruff/scan0，PG lease/claim/quota仍not_run。已准备一个必要integration node，只synthetic MessageProbe/同原P3Fixture低角色、自有PG内一次claim+并发同App拒绝/原消息重投同task与全部business计数不增/新workflow超1示例quota拒绝零增量/过期拒绝/同window重claim UniqueViolation；无SDK/平台/secret文件读取。该node当前仅1collect，Root新AC08同一个PG窗口纳入，不另pool或借旧volume，不把collect写passed；fixture完整初始化/清理同原测试机制。设置对象直接构造，无Docker未COPY docs的依赖，也不新增test framework。

## 2026-10-11第二AC08窗口失败与最小修复

Root核6d薄Compose停止receipt修复独审P1解除后释放新project `m1off-aea95b833bff`，source `6d1405c746a71ab7a3a5cde8cd2e0994a35378e7` / tree `7e67cafb29a3de41f6a770fe968a3ebf16c99bd6`。T0 08:14:25.643109Z，固定外窗08:54:25.643109Z、服务截止08:44:25.643109Z；UID501/GID20，无PG hostport，Web62978/API62979。build16.724s、原0012迁移/checkpointer/grant/低权三flags false/tempDB0及schema成功后，必要A06单node实际collected1/call_failed1，command11.897s/JUnit9.035s（setup1.906257s passed、call0.015280s failed、teardown0.043254s passed）。失败点 `tests/test_p4_gateway_window_pg.py:65` 的claim，实际 `psycopg.errors.UndefinedColumn`：当前0001的 `business.audit_events` 无 `shop_id` 列，新claim INSERT与guard SELECT错误引用该列。这是本A06新源码缺陷，不能归因旧PG/read未知失败，也不能用此前pure/独审代替实际PG通过。

失败后未demo seed、未API/Worker/Web启动、未T1/T3/T6或C headless，SDK/provider均0；未热改image、未延长/重开窗口。08:15:18.325473Z正常stop0/本project PID0；仅同project PG短启只读核收尾tempDB0后正常stop/down no-v，遗留命名测试container核同project/PID0后普通rm，08:20:53.192768Z释放。containers0/networks0/两个listeners0，卷/images/700与600私包全部保留。完整258 Python源码hash、PG_DIAG、JUnit、ledger、safe-summary与only-owned-release在 ignored `runtime/m1off-aea95b833bff`；安全摘要回执Issue40#6107075760。结论为AC08第二窗口failed/not_accepted，不给C发送ready，不重置D1/D30/预算。

依Root明确授权，本修复复用既有org列、原唯一audit/window UUID与不可变after_state，不新增迁移/列/权限。claim在原trusted org/app/tenant/mock shop核对后，将完整原GatewayWindow（包括shop UUID、org/window UUID、expires、parameters、max_callbacks/max_workflows、enabled/schema）与原not_verified证据标记一并存JSON；guard保留org/id/action/entity/数据库时间条件，读取同JSON必须完全相等才进入原quota/T1事务。去掉不存在的列，未删除shop校验、未放松scope、未替换Worker锁/原幂等/审批。

原261 PG单node所有一次claim/同App rival拒绝/原消息replay/配额/过期/同window重claim断言原样保留；追加同org错shop、parameters变化、预算变化与enabled变化均应拒绝且五个business计数零增量。该PG修复当前只1collect2.20s，尚未在新PG窗口执行。offline审计读取增加原完整JSON正例及8类字段变更在quota查询前拒绝；不模拟PG schema/lease/业务成功。作者lifecycle15pure4.39s；Gateway/lifecycle/SDKwindow/ledgeredSDK/薄Compose合42pure4.22s，2条既有SDK import warning保留；定向mypy3/Ruff/format均0。新的精确source独审与Root新actualscope仍pending，不能自动循环窗或宣称A06/M1/Phase4通过。
