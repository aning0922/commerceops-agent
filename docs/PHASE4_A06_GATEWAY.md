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
