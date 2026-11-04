> 状态：PROPOSED / A阶段候选合同；V4-0代码NOT_STARTED。冻结的是文档内容，须用户审核并另发B授权后才允许实施。绑定远端M3 `952e6246deb01ec763f2541d9f316753987744f3`；不修改旧业务合同。

# domain + source · v4-v1 候选

## 已存在 already_existing

M3/P3：PG organizations/principals/identities、shop scope和role grants、WebActor/SessionStore、原库存/补货计划/审批/回执、日报、只读询单、knowledge/copy；迁移链head0023。实现路径、DTO/API及SQL权限逐项见 reviews/M3_BACKEND_AUDIT.md。source_mode并非全站新枚举：原Web deployment的mock、Woo来源woocommerce_test、日报source descriptor、询单内部UUID及外部shop key各保留原语义。不得全局替换为demo，不能将两个店铺合为一个来源。

## 新增 proposed；V4-0最小域

采用一个DemoTenant对应一个新合成organization，每tenant注册两个独立shop UUID；模板店铺键不充当内部UUID，也不跨tenant共享已授权业务行。每访客一租户，多个标签页同cookie属同一个访客。DemoSession绑定租户、当前persona principal、旧WebSession身份引用、绝对expires_at、auth_generation和reset_epoch。运营/审批/受限管理persona均为服务端预登记principal/identity及显式shop grant，真实账号不获得persona切换接口。

共享的是只读、版本化、无私人信息的baseline_snapshot；租户overlay和审计、receipt有tenant/epoch/owner，查询必须合并当前tenant覆盖层。V4-0可登记后续六链的合成对象和稳定关联ID，不提前创建采购/CRM/营销状态机或宣称六链能运行；V4-2/3/4再实现其行为。现有M3接口不可直接读取未适配的overlay。首次首页在V4-0只交同源seed摘要/欢迎视图，经营KPI接口和完整驾驶舱属于V4-1。

标识：tenant_id/organization_id/shop_id/principal_id为服务端opaque标识；resource_ref=(tenant,shop,kind,id,version,epoch)；source_ref包含不可变fixture_version/content_hash/基线来源。金额Decimal及币种、时区；未知字段null/UNKNOWN，不填0。跨币种不求和，缺成本不出毛利。

新V4 DTO分开保存 data_mode=demo_fixture、evidence_mode=synthetic_demo、model_mode=offline_stub、embedding_mode=synthetic_vector、delivery_mode=offline_fake。这些是新信封字段，不是修改旧source_mode。V4-0不调用模型/embedding/飞书/Woo；mode标签不是调用已经发生的证明，实际使用还要执行证据。

## seed / reset / 原子性

SeedManifest必须列出生成器版本、固定随机seed、每店数量、日期锚点、时区/币种、六异常对象、关系/内容digest。大规模建议是容量目标，不是V4-0默认一次写入所有领域表；先冻结最小连贯规模并以实际数量签收。旧M3日报/询单/copy脚本各有新库与来源限制，不直接串联旧CLI或读取旧配置。

初始化和重建：在新owned库内，基线只读、租户登记+双店映射+overlay初始化同一事务成功；失败全回滚，文件导出不是数据库事务的一部分。配置导出采用新临时目录、验证manifest后原子发布索引，失败保留原始证据，禁止覆盖/自动重试旧M3导出目录。

Reset持有tenant/session锁并CAS expected_epoch；单事务增加epoch，清当前tenant演示overlay、撤销旧generation的待处理能力，恢复同fixture版本。保留最小幂等/审计tombstone，直到会话到期及安全保留期，清业务内容不删除去重证据。禁止全库TRUNCATE/跨租户清理。旧generation异步返回/写入在提交前再校验而拒绝。reset与业务写竞争只能按锁顺序线性化；不允许旧写提交到新epoch。

## 验收例子（未来B；本轮NOT_RUN）

A/B访客同模板SKU但不同tenant对象，A读B返回404且不泄漏；A reset不改变B digest；同reset key同payload只有一个epoch增量，异文409；崩溃发生在COMMIT前全回滚，COMMIT后丢ACK按原键只读核对。两店订单/商品/引用一致，未知成本仍不可计算；任何demo写不产生Woo HTTP。旧0023升级前后原业务表/权限保护和M3回归必须保留。

## Worker现状与V4-0范围

现存Worker具有数据库固定advisory lock，队列消费不能由启动organization参数推定为per-tenant隔离。V4-0不为每访客启动Worker、不投递新Graph/自动化任务；新demo身份和seed/reset为有限PG同步路径，原单Worker/队列保持原样。后续V4接入M3异步用例前，必须冻结并验证任务绑定tenant/epoch、当前权限和late-result拒绝，不能直接宣称多organization已安全隔离消费。
