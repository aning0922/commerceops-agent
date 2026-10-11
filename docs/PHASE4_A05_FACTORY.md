# P4-A05窄Factory与只读preflight功能候选

本候选在42c81e0测试修复后离线准备，A04实际PG仍以原0011精确COPY及独立回执为准。新增0012仅原SDK方法CHECK扩认证internal与原bot info，不新增权限、DDL授权、业务表或复位预算；新schema断言精确0012，全部旧表集合保留。B三模块、shared DTO/OAS、C前端与根CI原字节，不把此候选混入A04实际镜像。

## 一轮Factory边界

BusinessSDKFactory构造无IO，显式controlled_sdk enabled窗口同organization/shop且auth cap精确1时才核WorkerSession并读取Root明确0600/owner/regular/O_NOFOLLOW有界私有App Secret文件。没有旧.env/旧DB/旧Probe回填、配置复制或secret日志。官方SDK1.7.3 InternalTenantAccessTokenRequest一次ainternal：持久preflight scope预占原cap后单次调用，真实HTTP/code与token/expire形状核实；token有效期必须覆盖原窗口并留60s，不够则停、不再认证。

认证用显式request body，后续Client只app_id/enable_set_token/timeout，不设置app_secret/assertion/cache；所有业务方法传同token RequestOption。已读锁定SDK token/auth.py：丢失显式token时因client无secret直接NoAuthorizationException，不能落入TokenManager自动刷新。官方Transport.aexecute源码为单次httpx.AsyncClient.request，无自动retry或follow_redirects配置；本实例账本仍仅说明SDK方法started/returned/raised/not_called及安全HTTP/code，取消或未知不称wire完成。没有全局SDK monkeypatch、代理发现或自建HTTP旁路。

bot仅沿用P1已授/open-apis/bot/v3/info窄GET（SDK BaseRequest），cap1、同账本scope、原bot open_id严格匹配。随后只同Base明确tableID的fields list；没有tableID时仅Root明确table name在该唯一Base内table list完整唯一匹配，不查Drive/Base目录/群列表/通讯录/猜tenant接口。两类metadata各最多2页×100且整次分页共用10s截止、总数一致/完整/无重复cursor；SDK逐method持久cap不重置。schema必须原15列唯一完整、Quantity/SyncVersion number2、其他text1，错误不改表不换目标。

## 显式入口与安全结果

原verify-config仍不读秘密/SDK/PG。preflight action额外需要--live和Root私有window-file enabled，默认false；window严格p4-preflight-v1/id/org/shop/awareexpires/caps，工作截止当前最多90s+最多20s收尾，整体建议Root120s（留余10s），只允许auth1/bot1/fields1–2/可选tables1–2，任何record/send method拒绝。原WorkerSession全局锁隔离短preflight，commerceops_app低角色，已有0012迁移和Root自有DB由原机制准备；入口不自行建库或升权。相同原窗口/cap账本不能换预算，失败不retry或续期。

summary只分类authentication_observed/bot_identity_observed/target_unique/15count+type bool、各安全method/status count、failure类别及锁关闭；raw schema/定位/用户/群/URL/token不输出。计数读取失败为not_verified，不把未记录当0。tenant/group/member API不足均not_run；后续真实业务消息/callback逐actor+PG权限另作current_observed，不能由本轮bot或本地配置推出。本轮records/send为0由只读cap和调用路径约束，不解除external_sender_enabled false。

## 实际证据及后续

Root独立4a62审发现P1：仅叶O_NOFOLLOW无法拒绝父目录symlink，Reviewer已用synthetic文件实际复现，真实preflight尚未放行/未读私配。普通最小修复复用原infrastructure.web_config.private_bytes助手：绝对无..路径，从anchor逐级O_DIRECTORY|O_NOFOLLOW+dir_fd打开祖先，保原owner/0600/regular，读32769并拒超32KiB；不resolve/创建/chmod未知目录。Business Factory统一委托该助手，原Web配置/nonce/CSRF亦直接继承祖先拒绝，不新建通用框架或加平台权限。六参数父目录symlink反例覆盖config/window/App Secret/Base token/table ID/Web config；必须在leaf fdopen前拒绝且输出固定类别，canonical synthetic仍可读。新修复实际检查/独审另记，旧P1与82pure/type/Ruff/scan通过保持，不能拿旧pure消掉P1。

作者修复后18新增/原定向合36pure实际2.75s；合已审C2后完整1365offline88.73s/375integration deselected、250mypy/343format/Ruff/89MD0、三scope扫描各0。两次作者误写不存在Web config测试文件路径exit4/0tests/0PG保留，随后以真实存在的P4preflight/Gateway/window与完整offline执行，不把错误命令计通过。新P1精确独审待Root，不自行宣解除；真实SDK/读取旧私配/新PG0。

新12pure实际2.88s；加入原Gateway/window合计30pure2.61s，Ruff/type初次import顺序与Any→str局部作者修订已修，不是平台失败。使用锁定官方request/Fake response，secret仅测试tmp synthetic文件，无真实认证、SDK网络、旧私配或平台/provider调用。完整1331offline通过93.25s/375integration deselected、249mypy/342format/Ruff/89MD0已实际核；扫描及精确冻结另补，不提前填未完成检查。0012真实PG和实际新15列表schema、资源包、认证/长连接/业务sender、human验收仍待Root独审与有限窗口。长连接默认关闭，本批未实现WS endpoint/handshake cap，不把认证窄读取等同完整live Factory。

原A04首轮39=37pass/2fail/停止保卷及42c earlycallback拒绝修复保留；原截止和最多第二轮不受本源码WIP影响。清洁Compose原AC08后续采用一层m1-offline-demo装配，复用既有P3 API/单Worker/Graph/20+known70 fixtures/Next，Mock/model not_used/simulated_web/Fake/senderfalse，实际freshCompose与同ID恢复另核，不以memory Preview或本文签M1完成。日期/人工工时未报告/原300h及既有资源与风险历史保持。
