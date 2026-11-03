# Phase6 / M3 SOP 检索与审核草稿短合同 v1

状态：**DRAFT / ROOT_REVIEW_REQUIRED**。日期：2026-11-03（台北）。
本线基线 `32b36edd4646f8d54df6d8c8e3e3baec6e93ea4b`，唯一工作树
`commerceops-m3-knowledge/commerceops-agent`，分支 `codex/m3-knowledge-20261103`。
依据：[托管计划](../plans/M3_MANAGED_DEVELOPMENT.md)、[PRD §5](../PRD.md)、
[架构 §3](../ARCHITECTURE.md)、[数据模型 §6](../DATA_MODEL.md)、
[Agent 设计 §6–7](../AGENT_DESIGN.md)、[测试计划 §5.1](../TEST_PLAN.md)。
本合同需 Root 对精确提交审查后分片放行；不代表生产实现、RAG 质量或 M3 验收完成。

## 1. 授权与范围

用户尚未准备许可 SOP/商品资料，仅允许本线自创、明确标为 `synthetic` 的 fixture；
不导入历史资产，不读旧 Secret，不调用 embedding/model API。真实资料、真实 embedding、
真实模型与人工业务审核为 **NOT_RUN**，provider 与 embedding 默认 disabled，实际预算待用户。
实现 SOP 向量检索、可定位证据、商品事实分源、候选文案、明确人工审批和幂等保存内部草稿。
零外部发布；不引入 CMS、第二服务/Worker/调度器，不给模型任意 SQL/URL/shell 或写工具。
本线仅写专属知识/文案模块及测试；共享迁移、ACL、根 Compose、锁与 workflow 由 Backend 单一 owner
经 Root 协调，不能由本线私改。旧预算、SPENT、UNKNOWN 和失败证据不重置。

## 2. 资料、向量与引用的不可变绑定

| 实体 | 最小字段与校验 |
|---|---|
| SOP document version | organization/shop、document_id、document_version、source_kind、title、内部 source_ref、授权记录 license_ref/digest、批准者/批准时刻、valid_from/expires_at、content_sha256；正文 UTF-8、LF，拒 CR，不 trim/Unicode 归一化；版本正文只追加 |
| chunk | document_id/version/content_sha256、chunk_id、chunk_version、chunker_version、section、start/end（正文 Unicode codepoint 半开区间）、text_sha256；切片逐字等于正文区间，无越界/空片/重号 |
| embedding | chunk identity/text_sha256、embedding_profile_id/version、provider/model/model_version/dimension、vector_sha256、evidence_mode；profile digest 覆盖全部模型、维度、预处理与距离版本；维度 1–2000、分量有限、非零向量 |
| retrieval | query_hash、query embedding/profile/vector hash、scope、manifest_digest、retrieval/ranking_version、DB as_of、命中 chunk 引用/距离、complete/reason；不保存任意模型生成的链接 |
| product facts | 独立 product_snapshot_id/source_binding/version/digest、SKU、captured_at/expires_at、facts_hash、字段路径和值；仅已授权来源的明确字段，不从 SOP 推商品属性 |

向量摘要采用版本化 canonical 编码并以 PG 单精度存储值复核，拒无法有限表示的分量；不得把
应用 double 精度摘要冒称实际 PG vector 字节摘要。S1 只验证规范值/identity，PG round-trip 在 K2 验证。
有效 manifest 为服务器批准的 document/version/chunk/profile 摘要集合，并绑定授权记录；
模型、客户端和检索文本无权批准资料、设置 scope 或替换 manifest。撤销状态在服务器当前授权记录中
更新且留审计，不回写旧证据。检索、候选生成、审核与保存均核当前有效/未撤销/未过期，
`valid_from <= now < expires_at`；now 来自可信服务端/DB。新增版本须新 manifest，不原地覆盖向量。
模型或维度变更须独立 profile 与完整重嵌入；query 和 chunk profile 必须精确一致，禁止混用。

引用 DTO 使用服务器生成的 evidence_id、source_kind 与上述全套 identity/hash、section/offset；
返回原文短片及 title，UI 解析内部引用。缺文档/区间/字段、摘要或版本不符、过期/撤权、跨店铺均拒绝，
不能以“找到了 ID”代替来源核验。历史草稿保留原引用，并显示当前失效原因；读取不重新检索覆盖旧证据。

## 3. 标准 SQL + pgvector，禁止降格为关键词 RAG

首版精确 cosine nearest-neighbor：参数化 SQL JOIN 授权 document/chunk/embedding/manifest，
WHERE 限定组织、店铺、批准且有效的精确版本/profile，使用 `embedding <=> query_vector`；
按 distance 升序，再按 document_id/version/chunk_id 稳定排序。禁止模型生成 SQL。
`knowledge-ranking-v1` 初值 top_k=5、最多 20 个候选、cosine distance <=0.35，阈值同 manifest 配置摘要
绑定；只是待评测配置，不是实测质量承诺。先在 SQL 限定有效范围再排名，不能全库 top-k 后泄露/过滤。
返回少于 top_k 可有效，但无过阈值命中、来源不完整、query 向量缺失/错版均 `INSUFFICIENT_EVIDENCE`，
不继续产生可审核候选；无 embedding/profile 不暗中回退关键词或 Mock。
S1 的纯排序只作为 K2 SQL 排名金标/边界组件，不称已经完成向量检索。

现 [compose.yml](../../compose.yml) 是固定 `postgres:17.11-bookworm` digest，未装 pgvector。
提案由 Backend 在**同一 postgres 服务**派生镜像：保持该基础 digest，编译安装官方 pgvector **v0.8.7**，
构建前冻结 tag 对应 commit、下载归档 SHA256 和构建依赖版本，记录镜像 digest；这些 digest 当前 **未解析**，
未固定前不构建/运行，不用浮动 latest 或悄换 PG 版本。安装文件后由 migration owner 在受限扩展 schema
执行 `CREATE EXTENSION vector VERSION '0.8.7'`，核 `pg_extension.extversion`，不以 IF NOT EXISTS 跳过版本核验。
runtime 不拥有扩展安装/升级/schema CREATE 权限。首版不加 ANN 索引、不加向量服务或 Python 向量依赖；
可用 psycopg 参数文本绑定再固定 SQL cast，不能拼接用户向量/维度为 SQL。

依据：官方 [pgvector README](https://github.com/pgvector/pgvector) 描述 cosine `<=>`、精确检索与安装；
[PG17 CREATE EXTENSION](https://www.postgresql.org/docs/17/sql-createextension.html) 要求先安装扩展文件并控制权限。
本次仅只读核对文档，构建/扩展/SQL 实测 **NOT_RUN**。最终构建须核固定 tag 的同版文档和可用性。

## 4. 候选文案、注入与模型边界

候选固定 `candidate_id/version/hash`，包含 SKU/product facts hash、manifest/profile/retrieval 摘要、
prompt/template/schema 版本、到期时刻和逐条 claims。每条 claim 必须列 source_kind 和精确证据引用；
商品属性只引 product facts；SOP 说明只引 SOP chunk，不能从运营规范推导这款商品的材质/功效/价格。
现有 Product DTO 无价格/功效字段；首版无此证据就不能写价格、收益、销量保证或医疗功效。

K1 先提供确定性 claim 模板：`product_title` 从事实原值渲染，`sop_excerpt` 逐字引用并明确标为 SOP 操作说明；
候选是可供运营审核的结构化内部草稿。不得靠任意自由文本附一个 citation 就判为事实成立。
后续允许模型重排/选择现有 claim，不允许改字、增数字/属性或生成执行参数；自由改写若另扩范围须新合同、
逐 claim 支持性评测和人工核对，不能把引用存在率当语义正确率。unsupported/incomplete 不进入可审批状态。

`knowledge-copy-prompt-v1` 将商品文本/SOP/用户输入放入显式不可信数据段；固定系统约束优先，
无 tools/write credentials，输出 strict schema/extra=forbid、去重 claim IDs、限定原证据集合，程序重建最终正文。
出现要求忽略规则/泄露凭据/越权工具的候选输出或非法 schema 直接拒绝，不从文本推定审核同意。
固定恶意 fixture 验证零写/零外发；关键词筛查不能证明检测了所有注入，权限与保存 gate 必须独立有效。

复用现有 [模型合同](../../backend/src/commerceops/application/model_explanation/contracts.py) 及
[持久预算模式](../../backend/src/commerceops/infrastructure/model_budget_repository.py)：
embedding 与文案各显式 stage/profile，网络前原子预留次数/Token/费用上界，绑定 request/corpus/facts/prompt hash；
记录 usage/latency/pricing/evidence_mode，未知 usage/cost 为 null，超时/取消/崩溃/结果不明不释放预留且停止。
不借用旧 stage 余额；预算或兼容协议未落实保持 disabled，embedding 非 chat 协议不能硬塞旧适配器假装可用。
合成手工向量标 `synthetic_vector`，固定模型响应标 `offline_stub`，真实 transport 才标 `actual_provider`。

## 5. 人工审核与内部草稿保存事务提案

创建/本人结果读取只允许同组织店铺的 owner operator；审核保存需同店铺当前 approver，角色不互相隐含授予。
审核者仅可读取服务器分配到本人且同 scope 的待审候选与证据，不获得其他任务/草稿的普遍读取权。
使用现有 session、Origin/CSRF、auth_version 与撤权模式；admin 不自动获得业务权限。
人工明确动作 approve/reject 绑定 candidate_id/version/hash、全部来源摘要、expires_at、actor 和 UUID request_key；
模型“approved”、GET、检索结果或聊天确认不能形成决定。approve 才保存内部草稿；reject 只记决定/审计。

**拟议同一 PG 事务**：按 principal → candidate → source authorization 的固定顺序锁定，重新校验当前身份、
候选完整性/hash/版本/有效期、资料许可和商品新鲜度；插入唯一审核决定；approve 时插入唯一 copy_draft
并关联原 candidate/decision/hash/引用，同时写审计。撤权/资料失效变更遵守同锁顺序，不能 check 后另事务写。
与既有权限实现的精确锁顺序须 Backend 核定并测试，未核定前不能接线；审核不能豁免缺证。

唯一约束提案：`(organization_id,shop_id,actor_id,request_key)` 绑定规范 action/payload_hash；
同 actor/key/hash 重试返回原决定/草稿，异文 409；`UNIQUE(candidate_id,version)` 固定首个决定，
`UNIQUE(candidate_id,version)` 固定至多一份草稿，不同 key/actor 并发亦不能双写；首决定后相反动作冲突。
保存草稿并消费批准在同事务，禁止先消费后补写。修改正文/来源产生新版本并重审，不回填旧批准。
提交后 ACK 丢失返回 `UNKNOWN`，客户端只读查原 request_key；读得同 key/hash 既有结果才返回已保存，
DB 不可读保持 UNKNOWN，不换 key/自动重发；确认回滚后沿原 key 重试，唯一约束仍是保护。
已保存草稿为不可变内部结果，不创建发布 outbox、不请求电商写端点。

Backend 所需 DDL 提案：knowledge_documents（版本）、knowledge_chunks、knowledge_embeddings、
copy_candidates、copy_review_decisions、copy_drafts；manifest 可作 document 集的有界不可变 JSON 绑定，
当前授权/撤销采用既有受控来源模式。复合 FK 绑定 org/shop/source/candidate；向量 `vector` +
`vector_dims(embedding)=dimension` CHECK；runtime 只读批准资料、窄插入候选/决定/草稿、无改写历史权限。
DDL/ACL/迁移号、API 路由/Worker 注册和模型 ledger 扩展均交唯一 Backend owner，不在本线抢号。

## 6. 分片与验收，按实际证据晋级

| 分片 | 实施与独立交付 | 通过条件与不能代签的 Gate |
|---|---|---|
| K1，先 Root 审合同 | 专属 application/knowledge_copy 下 contracts/citations/ranking/prompt 纯模块；独立 test_p6_knowledge_copy_*；合成 fixture | DTO/hash/精确切片与字段引用、错版本/过期/跨店铺/非有限向量/稳定排序、claim 重建与注入拒绝；零 DB/网络，不称 RAG/并发保存完成 |
| K2，Backend 统一集成 | 固定镜像/扩展、DDL/ACL、参数 SQL repository；本线提供纯接口与 PG 测试 | 新 owned PG 真 SQL/extension/version/低权/跨 scope/错 profile/维度/hash/到期/撤销、同向量 tie 和独立排名金标；合成向量不证明 embedding 语义质量 |
| K3，合同复核后接线 | 同 Worker/API 的候选、当前权限、审核事务、只读回执 | 真 PG 拒绝零草稿、双连接并发 approve/reject/同键异文、撤权竞争、commit 后 ACK 丢失/进程重启只读恢复、零发布；fake store 不替代 PG |
| K4，资源就绪再申请 | 许可资料、实际 embedding/model 配置与预算、独立 holdout、真实人工审核 | 定位引用/缺证拒绝/语义检索与注入固定集；真实模型按 TEST_PLAN 重复至少三轮并保留波动/holdout；Root 独审、完整 CI 及 M3 总验收另核 |

K2 新 owned 本地真实 PG **仅提案，当前不启动**：Root 先批准同源候选和绝对 UTC，独立 project/network/新卷，
无宿主端口、低权 runtime、新本地合成密码；单窗建议 <=1200s、末 cleanup >=180s，超时即停不自动续。
记录镜像/源码/tree、PG/extension 版本、fixture/SQL 金标、每命令原生 exit 与失败、低权/事务结果；
停止父/children、down 不删卷并独立核容器/网络/进程为零，旧资源零访问；失败/未跑/UNKNOWN 均保留。
根 Compose/Hosted CI 修改仍须 Backend+Root 具体放行；本线只普通 commit，不 push/PR/main/触 CI。

## 7. K1 本地实现交付记录（2026-11-03）

Reviewer 对合同 `3097d605b214555b182b76e78e9089e45fff961a` 给出 ACCEPT_K1，Root 随后明确放行本片。
本次实现仅 `application/knowledge_copy/{contracts,citations,ranking,prompt}.py`、包入口及专属测试；
不改变 K2–K4 闸门，不代表主体 RAG 或草稿保存完成。

- 资料/profile/manifest/query/product、精确 codepoint chunk、逐来源 citation 均 strict/frozen，
  函数边界重新校验嵌套实例，拒 model_copy/model_construct 绕过。manifest 同时绑定完整 citation ID，
  不能通过修改 chunk_version/展示文字再重算局部 hash 放行。商品标题与 SOP 引文分别确定性重建。
- `retrieve` 是纯 f64 排名金标：先 scope/当前有效期/批准撤销/精确 manifest/profile/citation，再容量与排序。
  合成向量只接受有限、维度正确且可非零表示为 float32 的值；K1 摘要为明确命名的 f64 hex 编码，
  不等于 PG 实际单精度摘要。JSON round-trip 保持这些校验，PG round-trip 仍 NOT_RUN。
- 结果携带有效证据池与 `ManifestView`，其中只保留有效文档/证据绑定；原完整 manifest 仅留下摘要引用，
  避免泄漏被排除的文档 ID/正文。结果 DTO 重算距离、顺序、命中集合、view/池对应关系及 reason，
  候选 DTO 重建每条 claim/正文及最早到期时刻；构造 prompt/离线选择还要求显式当前 clock。
- 摘要是完整性绑定，不是授权签名；`verify_retrieval` 通过可信原 manifest/query/完整 corpus/clock
  重算结果，拒绝来源摘要或证据池被一起重哈希的伪结果。K2 必须从受控 DB 取得当前授权/撤销及完整语料，
  不能把调用方自称的 manifest/complete/clock 当准入事实；纯 DTO 本身不提供真实身份认证或数据库完整性证明。
- 仅生成模板候选或解析离线 claim-ID 选择；模型无 tools，所有输入文本保留为 JSON 数据，
  schema 不接受批准/发布/任意文案/真实 provider 标签。approved/publication_allowed/provider_enabled 固定 false。
  保存、事务、当前 session 鉴权、API、Worker、SQL 与真实模型均未接线。

最终本地专项：`uv run --frozen python -m pytest tests/test_p6_knowledge_copy_contracts.py -q --tb=short`
实际 **66 passed / 0.21s / exit0**；专属六文件 strict mypy、Ruff lint、format check 均 exit0。
金标包括独立 3-4-5 向量、距离 0/0.04/0.4/1/2、0.35 等值与两侧、倒序输入/同距稳定键、
中文/emoji/组合字符精确区间、错正文/错版本/错 hash/跨 scope/过期撤销/非有限或零向量、
无命中/不完整、逐 claim 跨源/数字篡改、重复/未知 claim、JSON 注入/重复 key、过期 prompt/选择。

开发失败原样保留为阶段事实：首轮 32failed/29passed（手算区间结束多一 codepoint）；修正后 9failed/52passed
（JSON 向量数组入口及完整 manifest 结果泄漏 ID），修复后 61passed；加当前时钟校验后 2failed/59passed
（无命中 min 空分支），修复后 65passed；新增权威回放测试首次漏 import 为 1failed/65passed，修复后上述 66passed。
首轮 mypy 字典展开类型不匹配与开发 Ruff 格式问题均已修复；不删除负例或放松检查。
全库 scripts.check、PG/扩展/SQL、外部资料/embedding/model、人审保存/并发及 Hosted CI 本片均 **NOT_RUN**，
实现的精确提交独审由 Root 后续核定；不预写 ACCEPT_K1_IMPLEMENTATION。
