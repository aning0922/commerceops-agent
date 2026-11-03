# M3 knowledge/copy 精确接线清单 v1

2026-11-03（台北）；**INTEGRATION_CHECKLIST / DEFAULT_DISABLED / REVIEW_AND_PG_PENDING**。
代码锚：K2唯一性fix e1a52d6、K3候选cf86b303、已合0019父37e7e99、精确0020父标识fix51065b19。
本文件仅准备单点接线，不表示已安装主API/Worker/生产bootstrap或实际SQL通过；
Root validation-k2 的新owned 30K2+16日报正在另行核验，本线不重复PG，也不预写其结果。
[实现与证据账](p6-knowledge-storage-v1.md)保留原失败、collect与NOT_RUN。

## 1. 当前已经存在与尚缺的出口

| 出口 | 已有精确实现 | 当前边界 |
|---|---|---|
| knowledge检索 | [repository](../../backend/src/commerceops/infrastructure/knowledge_copy_repository.py) 的 `retrieve_in_transaction(db,actor,shop_id,registry_id,expected_registry_digest,query)` | 调用方事务、当前scope、固定SQL和PG float32；没有独立HTTP任意向量入口 |
| 内部草稿 | [CopyStore](../../backend/src/commerceops/infrastructure/knowledge_copy_draft_store.py) 的 `create/read/candidate_request/review/receipt` | 当前只接受服务器显式synthetic Query，不构造provider，不含发布方法 |
| 独立HTTP | [router](../../backend/src/commerceops/entrypoints/knowledge_copy_http.py) 的 `knowledge_copy_router(config,store)` | 当前未被主create_app注册；自身校验Session/Origin/CSRF，POST schema显式导出 |
| owner bootstrap | `grant_knowledge_runtime(db)`、`grant_copy_runtime(db)` | 测试显式调用；现有 [grant_runtime](../../backend/src/commerceops/entrypoints/database.py) 尚未自动接入两者 |
| 主Worker | [serve](../../backend/src/commerceops/entrypoints/worker.py) / InventoryCompositeRunner | 没有knowledge/copy Runner、workflow_version、job生产者或outbox，不能登记不存在的runner |
| 主API配置 | [create_app/main](../../backend/src/commerceops/entrypoints/api.py)、[WebConfig](../../backend/src/commerceops/infrastructure/web_config.py) | 没有copy_enabled、query配置文件loader或copy_store参数；下文这些接线项均待Backend实施 |

## 2. 主API的Backend单点顺序

1. 默认关闭：建议给create_app新增显式可选 `copy_store: CopyEndpoints | None = None`；None不挂路由，
   未配置不得猜Mock、读旧密钥或因某个文件存在就自动打开。此参数**尚不存在**，不是现有调用示例。
2. 仅在明确启用且真实web_config/replenishment_store已安装时注入CopyStore；用同一个runtime DB配置，
   不把owner连接注入服务、不另开第二API服务。启用却缺配置/父链/授权时固定报错或保持disabled，不回退。
3. `CopyStore(config.database, queries)` 的queries为不可变 `(org_uuid,shop_uuid,query_ref) -> Query` 映射；
   每个Query必须服务器提供、冻结query/text/vector/profile摘要、标synthetic_vector，HTTP只传query_ref。
   当前没有自动文件loader；Backend若增加，须strict解析受控非秘密配置并先核版本/digest，不从消息/请求body取向量或许可。
4. source由owner先登记：registry id+digest、product_source id均是已登记实体的引用；请求中ID/hash只是前置条件。
   Store必须按当前session/角色scope重读并重放owner数据，不能用客户端自洽hash注册/替换来源。
   query_ref配置变更使用新版本并保留原pin；旧候选不能自动重绑定，原回执仍按原key查询。
5. 使用 `app.include_router(knowledge_copy_router(config,copy_store))`，在生成最终OpenAPI前完成。
   Router与现有 `/api/v1` session、Origin/CSRF/CORS边界共同存在；不能装测试身份resolver绕过真实SessionStore。
6. **OpenAPI必须同时接线**：现 [export_web](../../backend/src/commerceops/entrypoints/web_openapi.py) 拒绝没有已审合同的/api/v1路径，
   直接include后调用export_web会失败。copy需独立冻结的OpenAPI/错误依赖闭包和与旧合同分离的导出，
   可沿用 [daily的separate_legacy模式](../../backend/src/commerceops/entrypoints/daily_http.py)。
   不放宽“未知路径/operation拒绝”或偷偷修改旧P3/P4/P5 schema；当前仅router的POST request schemas已有，完整copy asset尚缺。
7. 五个实际路由：POST `/api/v1/copy/candidates`；GET `/api/v1/copy/candidates/{identifier}`；
   POST `.../{identifier}/review`；GET `.../{identifier}/review-receipts/{key}?candidate_hash=...`；
   GET `/api/v1/copy/candidate-requests/{key}`。成功envelope为p6-copy-web-v1，固定错误沿用p3-web-v1 error_response。
   ReviewCopy要求显式v1/hash/key/action/reason；UNKNOWN只GET原键，缺行仍UNKNOWN，不自动POST或换key。

## 3. owner初始化与最小runtime权限

按实际已合父链先迁移，再由已授权owner执行既有grant_runtime（建立低权角色），最后在显式owner事务内执行
本功能grant helper；不依赖“表存在即功能开启”。服务默认disabled时不因测试曾授权就推定部署已授权。

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
0020已精确绑定0019_p6_daily_reports；0023仍等待Root的实际0022及祖先提交，不能将缺父链视作已迁移。
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
