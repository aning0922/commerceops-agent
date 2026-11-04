# M3 knowledge/copy 精确接线清单 v1

2026-11-03（台北）；**COPY_CONTRACT_READY / MAIN_WIRING_PENDING / DEFAULT_DISABLED / K3_SQL_PENDING**。
代码锚：K2唯一性fix e1a52d6、角色夹具fix98cc39d、K3候选cf86b303与请求键fix e40ee5a、
已合0019父37e7e99、精确0020父标识fix51065b19；S3只读精确对象32dd7c240b9d2d979bf684eeb1dc8bcba7e35d31。
本文件仅准备单点接线，不表示已安装主API/Worker/生产bootstrap或组合SQL通过；
Root已回执K2 fixturefix批b828c6f实际30passed/47.75s/module与outer0、清理0/容器网络0/保留新卷1；
前批日报16实际通过，K2只核收本地synthetic SQL组件。Root另回执e40独审ACCEPT_K3_KEY_FIX/127独立纯测试；
K3实际29PG仍待，S3询单SQL仍HOLD（Root整批25/36pass），以上均非本线执行，不互相代签。
[实现与证据账](p6-knowledge-storage-v1.md)保留原失败、collect与NOT_RUN。

## 1. 当前已经存在与尚缺的出口

| 出口 | 已有精确实现 | 当前边界 |
|---|---|---|
| knowledge检索 | [repository](../../backend/src/commerceops/infrastructure/knowledge_copy_repository.py) 的 `retrieve_in_transaction(db,actor,shop_id,registry_id,expected_registry_digest,query)` | 调用方事务、当前scope、固定SQL和PG float32；没有独立HTTP任意向量入口 |
| 内部草稿 | [CopyStore](../../backend/src/commerceops/infrastructure/knowledge_copy_draft_store.py) 的 `create/read/candidate_request/review/receipt` | 当前只接受服务器显式synthetic Query，不构造provider，不含发布方法 |
| 独立HTTP | [router](../../backend/src/commerceops/entrypoints/knowledge_copy_http.py) 的 `knowledge_copy_router(config,store)` | 当前未被主create_app注册；自身校验Session/Origin/CSRF，成功及UNKNOWN响应显式DTO校验 |
| 独立合同 | [copy_openapi / separate_copy_legacy](../../backend/src/commerceops/entrypoints/knowledge_copy_openapi.py) | 五操作、严格请求/响应、原P3错误闭包，独立asset；主入口尚未调用 |
| 合成Query配置 | [load_copy_deployment](../../backend/src/commerceops/infrastructure/knowledge_copy_config.py) | 默认关闭不读文件；显式raw pin、逐级NoFollow/0600/owner/32KiB及语义digest，返回不可变映射 |
| owner bootstrap | `grant_knowledge_runtime(db)`、`grant_copy_runtime(db)` | 测试显式调用；现有 [grant_runtime](../../backend/src/commerceops/entrypoints/database.py) 尚未自动接入两者 |
| 主Worker | [serve](../../backend/src/commerceops/entrypoints/worker.py) / InventoryCompositeRunner | 没有knowledge/copy Runner、workflow_version、job生产者或outbox，不能登记不存在的runner |
| 主API配置 | [create_app/main](../../backend/src/commerceops/entrypoints/api.py)、[WebConfig](../../backend/src/commerceops/infrastructure/web_config.py) | 没有copy_enabled或copy_store参数；独立loader已提供，主入口接线仍由Root实施 |

## 2. 主API的Backend单点顺序

1. 默认关闭：建议给create_app新增显式可选 `copy_store: CopyEndpoints | None = None`；None不挂路由，
   未配置不得猜Mock、读旧密钥或因某个文件存在就自动打开。此参数**尚不存在**，不是现有调用示例。
2. 仅在明确启用且真实web_config/replenishment_store已安装时注入CopyStore；用同一个runtime DB配置，
   不把owner连接注入服务、不另开第二API服务。启用却缺配置/父链/授权时固定报错或保持disabled，不回退。
3. `CopyStore(config.database, queries)` 的queries为不可变 `(org_uuid,shop_uuid,query_ref) -> Query` 映射；
   每个Query必须服务器提供、冻结query/text/vector/profile摘要、标synthetic_vector，HTTP只传query_ref。
   现可使用`load_copy_deployment(path, enabled=explicit_bool, expected_sha256=raw_sha256)`；
   默认enabled=False返回None且不读文件。启用必须给原始文件pin，loader不读env/Secret/数据库/模型。
   返回的CopyDeployment经`.queries()`提供上述映射，不从消息/请求body取向量、角色或许可。
   文件含schema_version、enabled、bindings及config_digest；每binding含org/shop/query_ref/query_version/Query/binding_digest，
   query_ref须以`@query_version`结尾（如synthetic-name@v1），新版本另立ref，旧ref保留原pin。
   provider_enabled/model_requests_enabled/publication_allowed均必须显式false；未知字段、重复JSON键、重复映射、
   非有限数、错误query/profile/vector摘要、PG数值越界及坏文件pin均拒绝；单文件最多100条且总长<=32768bytes。
4. source由owner先登记：registry id+digest、product_source id均是已登记实体的引用；请求中ID/hash只是前置条件。
   Store必须按当前session/角色scope重读并重放owner数据，不能用客户端自洽hash注册/替换来源。
   query_ref配置变更使用新版本并保留原pin；旧候选不能自动重绑定，原回执仍按原key查询。
5. 使用 `app.include_router(knowledge_copy_router(config,copy_store))`，在生成最终OpenAPI前完成。
   Router与现有 `/api/v1` session、Origin/CSRF/CORS边界共同存在；不能装测试身份resolver绕过真实SessionStore。
   精确S3的`create_app`先`install_web`，可选安装daily，然后调用`app.openapi()`；copy挂载须加入该调用之前。
   `install_web`现对全部`/api/v1`使用真实session、operator/approver能力及POST CSRF边界，
   copy router仍保留自身同配置核验，Store继续核当前owner/assigned reviewer；不因中间件检查而删Store校验。
6. **OpenAPI必须同时接线**：现 [export_web](../../backend/src/commerceops/entrypoints/web_openapi.py) 拒绝没有已审合同的/api/v1路径，
   直接include后调用export_web会失败。copy需独立冻结的OpenAPI/错误依赖闭包和与旧合同分离的导出，
   现使用`copy_openapi()`和`separate_copy_legacy(schema)`完成该独立出口；
   不放宽“未知路径/operation拒绝”或修改旧P3/P4/P5 schema。copy分离仅移除声明的五路径和不被其他操作引用的新model，
   未知copy路径仍交原export_web拒绝，旧model保留。
   精确S3只在`daily_enabled`时运行daily的`separate_legacy`；copy的独立导出与分离须按copy启用状态单独运行，
   在最终`export_web`前剥离copy已审路径和专属model，不得依赖日报开关或使用宽泛`/api/v1`过滤。
   Root可将`copy_openapi()`保存至`app.state.copy_openapi`；该state绑定仍未安装，helper和冻结asset已交付。
   [完整OpenAPI](p6-copy-web-v1.openapi.json)及[响应JSON Schema](p6-copy-web-v1.schema.json)可交UI严格消费，
   同源模块为[http_models](../../backend/src/commerceops/application/knowledge_copy/http_models.py)，
   `python -m scripts.export_copy_schema`重生成文档及包内asset，旧合同文件不变。
7. 五个实际路由：POST `/api/v1/copy/candidates`；GET `/api/v1/copy/candidates/{identifier}`；
   POST `.../{identifier}/review`；GET `.../{identifier}/review-receipts/{key}?candidate_hash=...`；
   GET `/api/v1/copy/candidate-requests/{key}`。成功envelope为p6-copy-web-v1，固定错误沿用p3-web-v1 error_response。
   ReviewCopy要求显式v1/hash/key/action/reason；UNKNOWN只GET原键，缺行仍UNKNOWN，不自动POST或换key。
   候选GET/创建后的读取为CandidateResponse：data含candidate、state、source_current、draft_id、publication_allowed。
   state四分支为awaiting_review/current=true/draft=null、source_unavailable/current=false/draft=null、
   saved/draft=UUID（来源之后可失效）、rejected/draft=null；没有批准状态可从文本或模型推定。
   创建原键未知为UnknownCandidateResponse（仅state/key/publication_allowed）；决策成功与未知分别为
   DecisionResponse/UnknownDecisionResponse，保留原candidate id/hash、request_key，UNKNOWN的decision/draft id均null。
   HTTP先重建严格DTO，再序列化；Store错shape/错ID/错receipt key返回固定503，不能把未验证dict当成功体。
   COPY_VERSION_CHANGED映射冻结PLAN_CHANGED、COPY_ALREADY_REVIEWED映射DECISION_CONFLICT、
   来源/query/reviewer不可用映射NOT_READY，原IDEMPOTENCY_CONFLICT不改；未知内部错误映射SERVICE_UNAVAILABLE。
   所有实际错误枚举均属于原P3冻结Error，不向UI裸露COPY_*或异常原文，receipt=null/retryable=false。

## 3. owner初始化与最小runtime权限

按实际已合父链先迁移，再由已授权owner执行既有`grant_runtime(owner_settings)`（建立低权角色），最后在显式owner事务内执行
本功能grant helper；不依赖“表存在即功能开启”。服务默认disabled时不因测试曾授权就推定部署已授权。
`grant_runtime`接收DatabaseSettings并自行连接，两个新helper接收已连接的owner DB事务，不能混用签名；
运行时CopyStore使用同一WebConfig里的低权DB配置，owner配置只留在显式初始化侧。
精确S3的bootstrap自动处理daily表；其中没有knowledge/copy授权，不能由迁移存在推定两个helper已执行。

| 阶段 | owner明确执行 | 新增runtime权限 |
|---|---|---|
| K2 | `grant_knowledge_runtime(db)` | knowledge_ext仅USAGE；五张p6_knowledge表仅SELECT；p6_lock_knowledge、p6_vector_safe及七个精确vector I/O/distance/cast函数EXECUTE |
| K3启用 | 在K2之上 `grant_copy_runtime(db)` | products仅SELECT；candidates/decisions/drafts仅SELECT+INSERT；p6_copy_session/source_current/lock_copy/reviewer/lock_copy_product五个固定函数EXECUTE |

runtime无UPDATE/DELETE/TRUNCATE新历史、无owner登记、无CREATE/extension安装升级权限；当前身份、角色和来源锁
使用窄definer函数，不为FOR SHARE扩大资料UPDATE授权。与既有基础角色权限的差额必须实测，不能只看新GRANT文本。
owner登记仅 `register_synthetic_corpus(db,registry_id,manifest,corpus)` 和
`register_copy_product(db,id,ProductCitation)`；原文/分块/embedding/profile/query/商品须明确自创合成，
旧资料、旧卷、旧secret和真实资料不从历史授权继承。公开服务没有登记路由。

基础镜像沿用Root已build的固定imageID；扩展只能owner以knowledge_ext/0.8.7安装，runtime不能CREATE或UPDATE扩展。
0020已精确绑定0019_p6_daily_reports；只读核对S3精确对象中的`0022_p6_daily_operations.py`后确认
其`revision='0022'/down_revision='0021'`，本K3的`down_revision='0022'`无需修改。
该S3树只有0019及0022新增迁移，没有0020/0021；Root仍须组合各owner精确提交并验证完整0019→0020→0021→0022→0023链。
本线没有合入S3，完整Alembic graph/upgrade/K3 SQL均未在本线执行，不把父标识正确记为迁移通过。
停用时先关闭路由生产入口，再由owner按受控事务撤本功能写入资格/来源enabled；在途已进入事务的结果按真实COMMIT回执记，
不承诺撤销已保存草稿，不删历史、不把UNKNOWN改成未保存。

## 4. Worker及放行前的组合核验

当前K3是同步、有限的PG读取/模板重建/人工审核保存，不需要向serve()/InventoryCompositeRunner添加空runner，
也不建第二Worker/调度器。现Worker只消费同一实际迁移链与runtime权限；knowledge/copy不注册job、模型factory或发布outbox。
未来真实embedding/生成式调用另须版本化provider/预算admission/usage/UNKNOWN与持久任务合同，不能仅靠挂本router打开。

主控组合放行前须补：默认关闭时路径不安装且零新副作用；显式启用时OpenAPI闭合、真实session/CSRF、
current operator/assigned approver、撤权/TTL/Source replay、同key/异文/并发、原键UNKNOWN只读、低权CRUD/CREATE负例；
重跑迁移前后ACL/旧Gate并核父链、actual source SHA和资源清理。审查/PG/完整CI/主入口部署回执以Root实际记录为准。
本清单未改共享文件、未启服务或PG、未调用模型；真实SOP/商品许可、embedding/model质量和真人审核仍NOT_RUN。

主API最小组合矩阵（待Root实现与实际验证）：

| daily启用 | copy启用 | 必须核对 |
|---|---|---|
| 否 | 否 | 旧路由与旧schema保持原合同；无copy配置加载、授权或模型构造 |
| 是 | 否 | daily独立schema与原功能可用；copy路径不安装 |
| 否 | 是 | copy五路由、独立schema与旧export_web均闭合，不因daily关闭漏分离 |
| 是 | 是 | daily/copy各自独立导出，旧schema无新增路径/model；同真实session与低权DB |

copy显式启用却缺WebConfig、ReplenishmentStore或服务器Query/source配置时须安全失败；
生产owner bootstrap与主API修改仍由Root单点实施；e40的Store、0023、锁和PG测试未由本交付修改。

## 5. 新owned本地演示来源登记与导出

本片普通快进合入Root冻结eff02e3b4c2ba023d09ddde9b4b131720a98fcf6；
没有读取或合入Root待审1e30c999主API/config/owner grant接线。
现有`m3_daily_demo`仅初始化日报及原Web账号，无copy来源登记命令，因此新增dev-only
`scripts.m3_copy_demo`；复用其已生成的唯一operator+approver及shop scope，不再初始化账号、session或平行认证。

Root须先在已登记的新owned窗口完成完整迁移、基础权限和日报demo seed；沿同一个新owner连接，
显式按已审入口授予knowledge/copy runtime资格。本CLI不迁移、不grant、不创建库、不运行API/Worker/浏览器。
目标库必须精确匹配显式`--database`与COMMERCEOPS_DB_NAME，且名为`m3_daily_demo_`加1–40位小写字符。
查询再核真实current_database/table owner、唯一技术org、mock/test demo shop、org创建不足1小时，
原Web credential/identity和当前双角色scope必须唯一，已有knowledge documents或copy products则拒绝。
只读必要身份元数据，不SELECT密码hash/token，不读原login/config/Secret或实际商业资料；owner连接使用Root本窗凭据。
登记前只在新知识表取本地事务锁防止重复seed并发，不改生产锁实现；失败保留新目录/资源，不自动重试或清库。

```sh
uv run --frozen --offline python -m scripts.m3_copy_demo \
  --database "$COMMERCEOPS_DB_NAME" \
  --organization "$TASK_M3_ORG" --shop "$TASK_M3_SHOP" \
  --directory "$TASK_M3_COPY_DIR"
```

三个TASK变量由Root从本次新demo非秘密metadata填写。COPY_DIR须不存在、绝对、无..且祖先无symlink，
父目录已存在；CLI逐级NoFollow后独占创建0700目录，再以O_EXCL/NoFollow写入0600并fsync。
登记仅复用既有纯合成fixture的codepoint SOP/vector/product及owner注册helper；来源按DB UTC当前时刻有效1小时。
owner事务确认COMMIT后才导出以下文件并打印安全metadata；导出失败不推定DB已回滚，不自动重跑。

| 产物 | 用途 |
|---|---|
| copy-config.json | strict CopyDeployment；只有本org/shop与synthetic-name-check@v1固定Query，三项provider/model/publication为false |
| copy-create.json | 原store CreateCopy请求：新registry/product引用、准确digest、原reviewer及新request_key；由真实登录后POST，CLI不代发 |
| copy-demo.json | 非秘密UUID、摘要、有效期与两个产物路径；含copy_config_sha256供Root显式pin，不含DB密码/凭据/session |

Root待审主入口接线约定为COMMERCEOPS_M3_COPY_ENABLED=true、CONFIG_FILE与SHA256三项显式参数；
实际变量全名/调用方式以该接线独审后的源码为准，本CLI不写env或自动打开路由。
真实Web随后复用原local-login.json的新demo账号，按旧Session/CSRF获取当前身份，创建候选、明确approve/reject、
GET原key回执和owner内部草稿；无模型、embedding、发布或外发。seed SQL/实际导出/API/UI执行仍待Root新owned回执。
