# M3 K2 知识存储与固定 pgvector 构建准备 v1

状态：**PREPARATION / REVIEW_REQUIRED，BUILD_AND_PG_NOT_RUN**；2026-11-03（台北）。
本片父提交 `59c40c2adbed00a3a5e6983bc1162488da33b501`，本线 branch `codex/m3-knowledge-20261103`。
只新增本合同、[Dockerfile](../../infrastructure/knowledge_pgvector.Dockerfile) 与
[pin 清单](../../infrastructure/knowledge_pgvector.pins.json)。K1 冻结模块不改；
[原合同](p6-knowledge-copy-v1.md) 的许可、权限、逐 claim/审核/UNKNOWN/零发布保护全部保留。
共享 DDL/ACL/迁移、根 Compose/锁/CI 不写；0019 已由 Backend 日报线占用，0020 的 owner/父 SHA
待 Root 明确登记，不能形成并行 migration heads。资料/实际模型预算均稍后，provider 继续关闭。

## 1. 官方源码与构建依赖核验

| 项目 | 实际核验结果 |
|---|---|
| 官方 v0.8.7 tag | `git ls-remote` 返回 `f37c13f68b57d2c3472b2214fbcff699d6d34876 refs/tags/v0.8.7`，无额外 peeled ref；提交归档 vector.control 与 Makefile 均声明 0.8.7 |
| 提交固定归档 | `https://codeload.github.com/pgvector/pgvector/tar.gz/f37c13f68b57d2c3472b2214fbcff699d6d34876`，实际下载 133206 bytes，SHA256 `83d673c3b287cddbf3879f86215f043f2c2b56c69d37b2a77504910db1ed6e56` |
| PG 基础 | 复用根 Compose 同一 `postgres:17.11-bookworm@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826`；本片未拉取/检查镜像内容，构建时强制核 PG_MAJOR17、包版本及 pg_config，不能将官方 master Dockerfile 视作该 digest 的实际检查 |
| Debian 工具链 | 只用官方 `snapshot.debian.org/archive/debian/20261101T000000Z` bookworm/main，冻结 gcc `4:12.2.0-3`、make `4.3-4.1`、libc6-dev `2.36-9+deb12u14`、curl `7.88.1-10+deb12u15`、ca-certificates `20230311+deb12u1`；arm64/amd64 官方 Packages 元数据及其摘要已核入 pin 清单 |
| PG 开发文件 | 从官方 PGDG archive 元数据核到 arm64/amd64 的 postgresql-server-dev-17 与 libpq-dev `17.11-1.pgdg12+2` 的路径、SHA256；只下载元数据，**未下载或执行 .deb** |

GitHub API 首次返回 HTTP403 rate-limit，未重试 API；改用公开 Git refs 和固定提交归档核验。
首次 PGDG Packages.gz 为 HTTP404，官方目录仅列 Packages/Packages.bz2，读取后者完成核验。
临时源码归档在本树临时目录内读取后删除，没有导入仓库或读取任何凭据。

依据：官方 [v0.8.7 源码](https://github.com/pgvector/pgvector/tree/f37c13f68b57d2c3472b2214fbcff699d6d34876)、
[同版 Dockerfile](https://github.com/pgvector/pgvector/blob/f37c13f68b57d2c3472b2214fbcff699d6d34876/Dockerfile)、
[Debian snapshot 使用说明](https://snapshot.debian.org/)、
[PGDG archive 说明](https://apt-archive.postgresql.org/)。PGDG 索引每日更新，**不是冻结仓库**；
因此构建不接入其浮动 APT 源，而使用固定版本下载路径并逐个核 pin 中的包 SHA256。
Debian 的直接包版本、transitive 解析来源由固定 snapshot + 固定基础镜像限定；APT 仍核签名，
仅关闭历史 Release 的 Valid-Until，不使用 trusted=yes/允许未认证包。不可用或摘要变化即失败，不切 latest。

## 2. Dockerfile 的实际行为与后续构建 Gate

多阶段均从同 PG digest 派生，支持 arm64/amd64，其他架构拒绝。builder 先核基础实际包版
`17.11-1.pgdg12+2`；若不符保留失败并由 Root 核实际镜像，不能忽略断言自动升级。
清除 builder 的默认 APT 源；以签名验证的 HTTP snapshot 引导安装 ca-certificates，随后下载全用验证 TLS 的 HTTPS。
固定 PG 开发包校验后只解压到 disposable builder，**不执行其维护脚本、不安装其 LLVM/clang 依赖图**；
通过 PGXS 的 `with_llvm=no` 明确禁用 bitcode，使用固定 PG17 headers/pg_config 编译 C 扩展，
`OPTFLAGS=""` 去掉机器专属 -march=native，`-j1` 与 SOURCE_DATE_EPOCH=0/TZ=UTC/LC_ALL=C 固定构建环境。
此开发文件提取路径/PGXS 无 LLVM 的可用性是待实际 build 验证项，不预称已构建成功。

`make install DESTDIR` 后 runtime 仅复制 vector.so、vector 扩展 SQL/control、LICENSE/README 与 builder 包版本账；
不复制 gcc/开发包/PG 二进制或修改根 Compose，不启动集群，不包含 initdb 自动安装脚本。
原 runtime entrypoint、数据路径与 PG 版本沿用。构建只添加可安装文件；扩展激活由迁移 owner 单独做。
固定输入不等于已证明二进制逐字节可复现：后续记录架构、Dockerfile/源码 SHA、基础及结果镜像 digest、
实际工具链/包清单、日志/native exit；必要时同架构复建比较 vector.so。不同架构不合并签名。

后续仅在 Root 审查本片并放行新 owned build/PG 窗口后执行准备好的 Dockerfile；推荐命令形状
`docker build --platform linux/arm64 -f infrastructure/knowledge_pgvector.Dockerfile -t <本窗唯一tag> .`，
本片**没有执行**。实际 build 必须核 ldd 无缺依赖，PG/extension 的平台和版本一致；失败不绕过校验。
同一个 postgres 服务切换派生镜像由 Backend 后续单点修改，不能加第二向量服务或复用未知旧卷。

## 3. 扩展 schema、版本和运行权限

迁移 owner 在全新 owned DB 建 `knowledge_ext`（owner 控制；PUBLIC/runtime 无 CREATE），
显式 `CREATE EXTENSION vector WITH SCHEMA knowledge_ext VERSION '0.8.7'`。
预先已有扩展时核 pg_extension.extversion、namespace/owner 和实际安装文件；不以 IF NOT EXISTS 掩盖错版本，
不自动 ALTER EXTENSION UPDATE 或 DROP 重建，不假设 app 能安装扩展。
runtime 不得 superuser、CREATEDB、CREATEROLE、CREATE ON DATABASE 或 CREATE ON schema；
仅授予知识 schema 的 USAGE、实际类型/函数/操作符所需权限和 scoped 表的窄读写。
函数精确 grant 清单由 migration owner 依据实际低权 SQL probe 冻结，不新增全库写/SECURITY DEFINER 绕过。
迁移/正常查询使用固定 search_path 并限定 schema，不能让用户 shadow vector operator/function。
验收实际 app 角色拒绝 CREATE SCHEMA/TABLE/EXTENSION、ALTER EXTENSION UPDATE、改证据/授权/历史草稿。

## 4. SQL 检索接口提案（表/列名待唯一迁移 owner 核定）

接口 `retrieve_pg(scope, registry_id/version/digest, query_profile/digest, query_vector, query_hash)`：
scope/current principal/registry/clock 均来自服务器与 DB，不接受模型指定租户、now、许可或 SQL。
在同事务读取当前 principal/source 授权并持适当共享锁，阻止撤权 check/use 竞态；具体锁顺序仍为
principal → candidate（如有）→ source authorization，由 Backend 与现有锁序核定。
单次 SELECT 用 statement_timestamp() 冻结同一时点；多 SQL 采集若需一致快照须明确事务隔离与来源版本，
不能把不同请求的“最新”结果拼成同一证据。

固定参数 SQL 的核心形状如下；**设计示例，不是现有可执行 migration/API**：

```sql
WITH eligible AS MATERIALIZED (
  SELECT e.*, c.document_id, c.document_version, c.chunk_id AS chunk_key
  FROM business.knowledge_embeddings e
  JOIN business.knowledge_chunks c ON c.id = e.chunk_id
    AND c.organization_id = e.organization_id AND c.shop_id = e.shop_id
  JOIN business.knowledge_documents d ON d.id = c.document_version_id
    AND d.organization_id = c.organization_id AND d.shop_id = c.shop_id
  JOIN business.knowledge_manifest_entries me ON me.chunk_id = c.id
    AND me.embedding_id = e.id AND me.document_version_id = d.id
    AND me.organization_id = e.organization_id AND me.shop_id = e.shop_id
  JOIN business.knowledge_authorizations a ON a.document_version_id = d.id
    AND a.organization_id = d.organization_id AND a.shop_id = d.shop_id
  WHERE e.organization_id = %(organization_id)s AND e.shop_id = %(shop_id)s
    AND me.registry_id = %(registry_id)s AND me.registry_digest = %(registry_digest)s
    AND e.profile_digest = %(profile_digest)s
    AND a.approved IS TRUE AND a.revoked IS FALSE
    AND d.valid_from <= statement_timestamp() AND statement_timestamp() < d.expires_at
), counts AS (
  SELECT count(*) AS n FROM eligible
), scored AS MATERIALIZED (
  SELECT eligible.*, embedding OPERATOR(knowledge_ext.<=>)
    %(query_vector)s::knowledge_ext.vector AS distance
  FROM eligible WHERE (SELECT n FROM counts) <= 20
), quality AS (
  SELECT count(*) FILTER (WHERE (distance >= 0 AND distance <= 2) IS NOT TRUE) AS invalid
  FROM scored
), ranked AS (
  SELECT * FROM scored WHERE distance <= %(max_distance)s
    AND (SELECT invalid FROM quality) = 0
  ORDER BY distance, document_id COLLATE "C", document_version COLLATE "C",
    chunk_key COLLATE "C" LIMIT 5
)
SELECT (SELECT n FROM counts) AS eligible_count,
       (SELECT invalid FROM quality) AS invalid_distance_count,
       coalesce(jsonb_agg(jsonb_build_object('embedding_id', id, 'distance', distance)
         ORDER BY distance, document_id COLLATE "C", document_version COLLATE "C",
           chunk_key COLLATE "C"), '[]'::jsonb) AS hits
FROM ranked;
```

归属与源摘要由 scoped composite FK/唯一约束及不可变证据约束落实；示例 JOIN 不替代 DDL 约束。
文本稳定键显式 COLLATE "C"，避免库默认 locale 与 K1 codepoint 排序不同；UUID 键按其原类型固定比较。
current registry 的启用、版本/授权摘要及 profile 也须在同事务先核并锁定，不从任意客户端 digest 推定可用。
参数使用 psycopg `execute(sql, mapping)`；query_vector 为程序先严格校验后的规范有限数字数组文本，
仅作为 `%s` 绑定值 cast 到固定 `knowledge_ext.vector`，不拼接维度、标识符、URL、排序或 SQL。
max_distance 取服务器版本化 registry（当前0.35），非模型值；不开放任意 top_k/阈值。
WHERE scope、授权、许可期、精确 registry/doc/chunk/profile 必须先于候选上限/距离/top-k。
eligible_count>20 返回容量失败，invalid_distance_count>0 返回数值质量失败；两者不能变成“无命中”或完整候选。
候选计数/score/引用在同句基于相同 eligible；无命中仅 `INSUFFICIENT_EVIDENCE`，不回退关键词。
输出补取 evidence_id 对应的已授权原文并复核 codepoint/字段/hash，原 registry 只给 digest，
不把全 registry/外店铺 ID/未授权全文返回给客户端；读取不能修改资料或生成审批。

## 5. PG float32 摘要与 K1 排名一致性

官方 [v0.8.7 vector.c](https://github.com/pgvector/pgvector/blob/f37c13f68b57d2c3472b2214fbcff699d6d34876/src/vector.c)
实际 vector_send 为 int16 dimension + int16 unused + 每分量 float4 网络编码；cosine 的点积/范数累加是 float，
最后转 double 求 sqrt/比值。K1 是 float64 范数/乘积和，不得直接用 K1 距离严格相等校验 SQL 距离，
也不能把原 f64 hex 摘要写成 PG 实际存储摘要。

拟 `knowledge-vector-pg-f32-v1`：输入先拒 bool、非有限、错维/错 profile/全零；按 IEEE754 binary32 round-to-nearest
固定每分量（含 -0→+0），再检查 round-trip 后仍非零。以 C-locale、每分量最多9位有效数字（如 Python format(value,".9g")）作可回读参数，
该规则不宣称最短字符串；最终必须经实际 PG 字节比对验证。
PG 插入后同事务取 `knowledge_ext.vector_send(embedding)`，逐字节比 Python
`struct.pack('!hh', dimension, 0)` + 连续 `struct.pack('!f', component)`；拒差异，禁止默默覆盖输入 hash。
PG 摘要覆盖固定编码版本、profile_digest、chunk evidence_id/query_hash 与上述真实网络字节，
与 f64 原输入摘要分列保存。此二进制摘要不依赖 PG native 内存布局或 CPU endian。

PG 距离采用新版本 `cosine-pgvector-0.8.7-f32-v1` 并绑定构建 flags/profile；K1 `cosine-f64-v1` 保留。
K1 DTO 目前只接 synthetic/f64；K2 adapter/结果 DTO 的必要版本扩展须新片放行，不改冻结 K1 冒充兼容。
超大/极小非零向量虽能存 float4，其 float4 点积/范数仍可能溢出/下溢；score 不是有限 [0,2] 即整次质量拒绝。
首批 synthetic profile 使用普通量级手工向量，极值作为必拒负例；不暗中归一化或改变预处理版本。

一致性验收：先以 0/正交/反向、3-4-5、相同二进制向量的独立纸面金标验证；
用实际 float32 round-trip 分量另算 f64 参考，普通量级差异绝对容差初值2e-6（待实测记录，不是放宽引用校验）。
大于1e-5间隔的排序/阈值两侧必须同 K1；相同向量同距严格按稳定键。
边界带内单列 PG 实际 distance/是否<=0.35 与 K1 差异，不能强制把 PG 的略高值夹成0.35或改阈值。
若首批固定边界金标不一致，保存失败并提交版本化数值口径复核，不能宣称“两种实现完全一致”或拼签通过。
首版 SQL 实际 PG 值是 PG profile 的权威距离；其数值/阈值版本必须在结果中可见。

## 6. 后续 owned PG 与审核保存矩阵

| 组 | 新 owned 实际验证与必保负例 |
|---|---|
| 构建与扩展 | 本窗精确 Dockerfile/base/source/arch/结果 digest，原生 build exit；PG17.11/vector0.8.7/schema/owner 实值；错误版/缺文件拒绝；runtime不能CREATE/升级，证据不可改写 |
| SQL 与隔离 | 手工向量真 INSERT/SELECT，不用 Mock SQL；授权低分与>5个无权高分、跨 org/shop、撤销/期边界/过时 registry/profile/chunk/source digest，先过滤再容量/top-k；未授权 ID/正文不出结果 |
| 数值与引用 | 实际 vector_send字节/hash、错维/NaN/Inf/零/float4归零/极值cosine异常；独立距离/稳定键/反序/0.35两侧与边界差异；UTF-8中文/emoji/组合字符切片与派生正文真实复核 |
| 容量/完整性 | 有效20与21个、无命中/不完整、query profile错版，零 model/embedding HTTP；失败不生成可审批候选，不以空结果掩盖质量失败 |
| 审核持久性（K3） | 当前 approver明确决定、拒绝零草稿；双连接同键/异键并发至多一决定/草稿；异文409、相反动作冲突、过期/撤权竞争与固定锁序；提交/ACK丢失、回滚、重启先只读原键，DB不可读UNKNOWN保留 |
| 外部零副作用 | 无发布outbox/电商写、无平台发送；synthetic_vector/offline_stub只记本地证据，不称实际embedding语义、人审或生产数据通过 |

Root 审查后登记新的 owned project/network/新卷、本机绝对 UTC 和固定总截止（建议<=1200s、末清理>=180s）；
不复用旧资源或窗口。build 若需独立更长机器窗须预先明确，不从 PG 清理预留偷时，失败不自动重试/续期。
与 Backend 共享唯一迁移链后再验证 init/升级/低权，0019/0020 来源各自精确提交分记。
运行日志需记录全部命令/原生exit/失败与未跑、DB时钟/低权角色/关键行数/版本/资源探针；
父child实际退出，down不删卷，独立核容器/网络/进程归零；零旧 Secret/DB/模型访问。
本片 **build、PG、DDL、低权SQL、vector round-trip、保存并发、人工审批、CI 均 NOT_RUN**。

准备片本地检查：Dockerfile RUN 块仅送 `/bin/sh -n`，exit0（未执行）；静态核两 stage 的基础 digest、
两个架构的 PG 开发包 hash、全部直接工具链版本与 pin 清单相同；文档检查122files/errors0/exit0，
Git 差异空白检查通过。未跑 Docker parser/build/PG/业务测试，不把 shell 语法通过写成镜像可用。

## K2 代码候选交付记录（2026-11-03）

Root 明确独占分配本线 `0020_p6_knowledge_copy`（Backend 后续从0021）；0019 日报父提交仍待精确转交。
当前 `down_revision="0019"` 是 Root 指定的待父提交绑定值；**未运行 Alembic graph/upgrade/PG**，
须在收到实际0019后普通合入并核真实 revision 标识，再交 Root 的冻结/独审与新 owned UTC GO。
K1 源码、0019/旧迁移、根 Compose/锁/CI、API/Worker 入口均未改。

本片新增五张检索专属表：documents、authorizations、chunks、embeddings、registries，前缀均为
`business.p6_knowledge_`；manifest 为有界不可变 canonical JSON，不新增通用授权/CMS/第二服务。
0020 安装固定 knowledge_ext/vector0.8.7；证据 body/hash、codepoint切片、citation、原向量→实际float4、
profile及manifest成员在列约束/插入触发器绑定同 org/shop；证据 update/delete/truncate拒绝，
仅owner可更新当前 approved/revoked/enabled 并留下审计，不删除旧证据/撤权历史。
此处 owner 注册只接受 self-authored synthetic，不能记为真实资料或人工审核完成；K3 copy表尚未创建。

`knowledge_copy_repository.py` 提供调用方事务内的 owner合成注册、显式bootstrap及 scoped只读检索。
注册用嵌套savepoint，任一后续验证失败回滚本次全部新增；重复注册校验原数据，不重新启用撤权或disabled状态。
bootstrap必须在现有 `grant_runtime` 之后由owner显式调用 `grant_knowledge_runtime(db)`，本片没有修改共享入口；
此步骤授予runtime仅SELECT/限定函数/USAGE，不给来源登记、证据写或CREATE权限，也不读取密码/创建角色。
`p6_lock_knowledge` 是窄 SECURITY DEFINER锁函数：复用当前p3 operator权限锁，再锁本registry与相关授权行，
避免为FOR SHARE授予runtime UPDATE资料权限；固定search_path、参数化对象ID，无任意SQL或注册写操作。

实际检索固定SQL先核scope/registry/profile/证据成员/许可有效期/当前授权，再count容量、算距离及top5。
超过20有效候选拒绝，不截断冒充穷尽；结果带eligible_count/complete/exhaustive与registry/profile版本，
有效证据池及选中引用均来自同一SQL语句；原完整manifest只留摘要，不泄漏被拒文档ID/正文。
SQL距离为版本化PG事实；DTO另重算实际float4字节/hash、f64 reference_distance、范围/容差、
排序/count/命中和reason，不能靠重算外层hash豁免结构或显示事实校验。API不接收这些结果DTO作为授权事实。

数值策略正式收紧为 `bounded-components-1e-6-1e6-normsq-1e-12-1e12-v1`：每个非零float4分量绝对值
须在[1e-6,1e6]，平方范数在[1e-12,1e12]，维度<=2000；规范化-0，拒原非零分量round成0。
这使每个非零乘积和范数累加远离float4下溢/溢出，应用和数据库CHECK双层约束，
不只依赖PG最终可能夹紧到[0,2]的结果。K1 f64证据不改；实际PG profile另编号，不暗中归一化。
边界按实际float4值判断，不承诺十进制1e-6 round后恰等于下界；小于下界就拒绝。

本地已跑：K1+K2纯测试 **84passed/0.22s/exit0**；新增五文件strict mypy与Ruff通过。
K2新增纯测试18项（K1原66项保留），含独立网络字节、0.1 round-trip、极值/下溢/零/错profile、
合法距离0不能掩盖极值、结果count/hits/mode/过期篡改。开发Ruff格式/导入与mypy Literal/异型空tuple
比较错误已修复；未删负例或降检查。真实PG测试 **28节点仅collect**，当前全部 **NOT_RUN**。
矩阵含真vector_send/距离、20/21容量、>20撤权高分先过滤、当前身份/版本/角色/scope、低权CRUD/CREATE/升级拒绝、
数值CHECK指定约束反例、owner错片段重hash仍拒、过期/外组织隔离、撤权锁竞争、savepoint失败回滚及阈值边界。

Root另提供的已构建事实（非本线执行）：8ee Dockerfile、arm64，74.12s/native0；tag
`commerceops-m3-vector:8ee1df0-arm64`，image `sha256:4ebf3de8870438618836dd1765632b7e90cb950632c929162441367087439d5a`；
Root无网络检查PG17.11/control0.8.7/ldd无缺失、容器退出。该回执仅构建，不签本0020或SQL/PG Gate；本线未重复build。

后续PG命令形状：在Root新owned服务/新凭据/新环境内，从本片冻结源码执行
`uv run --frozen python -m pytest tests/test_p6_knowledge_copy_pg.py -m integration -q --junitxml=<owned-log>/knowledge.xml`。
该fixture每例仅在本窗PG中新建唯一数据库、按真实head迁移/初始化/低权授权并清理该自有DB；
因此必须先绑定精确0019/0020和含扩展镜像，不能在原PG/旧环境运行。资源/绝对截止/清理仍由Root统一准入。

### K2 P2：registry逻辑分块唯一性修复候选

Root独审8a6发现：同document_version/chunk_id的多个chunk_version可同时进入registry，
SQL与K2 DTO排序键不区分这些版本。Root原独立反例为六条同距：正序取v0..v4、反序取v5..v1，
两结果均自称完整；该P2与原84offline/28collect未跑事实保留，不把旧源码追记为通过。

本次采用与K1相同的逻辑身份 `(document_id,document_version,chunk_id)`，每registry只能出现一次，
不通过扩排序键支持同registry多版本。全库保留历史chunk_version，不同registry可各自绑定准确的一版。
注册入口在任何证据写入前拒重复；0020 registry绑定触发器将JSON evidence成员展开后按关系中的
(document_id,chunk_key)分组拒重复（同scope内document行已唯一绑定文档版本），也拒JSON重复成员。
检索Source在当前授权过滤/容量/score/top-k之前另查完整绑定registry，异常整体拒绝、不静默丢一版；
结果DTO按同逻辑身份拒重复pool，即使外层hash重算也不能接纳歧义。K1已拒该组身份，本片未改其冻结源码。

新纯回归覆盖正反序六同距版本、不同metadata/向量的同逻辑身份、不同registry准确引用版本、
重算结果hash仍拒，以及离线Source故障注入证明未进入排名SQL；故障替身不签实际数据库Gate。
新增PG两节点覆盖合法不同registry精确版本与应用/直接SQL重hash混版拒绝，仍须新owned窗口实际执行。
开发新Source回归首次因漏导入canonical为1failed/87passed，修复后88passed；新SQL测试漏导入仅静态发现并修复，
无PG执行。本修复独立提交，只含K2原文件与本事实记录；K3未提交文件保留且不混入该commit。

### K3 源码候选 / HOLD（实际PG与父链尚未就绪）

Root预留0023（父0022）给本线内部草稿；本片完成新commands、候选重建、CopyStore、独立router及0023，
不改共享API/Worker/旧迁移。K3四表为p6_copy_products/candidates/decisions/drafts：
产品仅owner登记synthetic事实；候选由当前授权registry检索和服务器固定合成query映射生成，
商品标题与SOP片段逐claim重建，无自由价格/收益/功效。标`template / model_evidence_mode=not_used`，
向量仍标synthetic_vector；没有真实生成式provider、embedding、平台或人审完成证据。

候选固定owner/当前指派reviewer、id/v1/hash、来源与到期（15分钟和来源最早到期取小）；
审核命令必须显式version/hash/key/action/reason，不能从模型approved/文本推定批准。
CopyStore在审核时用owner登记商品、registry真实profile/阈值、不可变向量/引用，以及服务器原query
逐项重放，重新查询完整排名；拒调用方仅自洽重hash的来源/阈值/候选。query_ref配置须保持原版本，
改变配置使旧候选HOLD，不能悄换query或来源；原决定回执仍可按原键只读核对。

审批先锁当前principal/角色scope，再锁候选与registry/product/相关授权行；owner与指派approver
当前资格、session、版本、TTL/撤权均核验。SQL commit约束再查到期与来源，并强制
approve有且仅有一份draft、reject无draft；决定/草稿/审计同事务，历史不可改/删/截断。
同actor/key同语义返回原决定，异文409；不同key/actor首决定由候选唯一约束和行锁串行化。
保存仅返回COMMIT后的确认，运输结果不明为UNKNOWN；查询缺行不声称已回滚，不自动POST/新建键/外发。
无发布outbox、商品价格修改或其他外部写工具。嵌套savepoint保证调用方捕获普通验证异常也不残留本次半写。

Backend单点集成exports（本片不注册主入口）：

- `knowledge_copy_http.knowledge_copy_router(config, store)`，由现有FastAPI明确include_router；复用真实SessionStore、Origin/CSRF、固定安全错误；POST JSON schemas已随router导出。
- `CopyStore(config.database, {(org_uuid,shop_uuid,query_ref): synthetic_Query})`；映射不可变、缺条目拒绝，不加载env/模型，不接受客户端向量或actor。空映射即不提供候选生成。
- owner在现有grant_runtime、grant_knowledge_runtime后显式调用`grant_copy_runtime(db)`，runtime只读products，窄插入candidate/decision/draft；不可注册来源、改历史或CREATE。
- owner合成fixture登记使用`register_copy_product(db,id,ProductCitation)`；业务路由不提供登记接口。
- HTTP：POST `/api/v1/copy/candidates`；GET `/copy/candidates/{id}`（同api/v1前缀）；POST `.../{id}/review`；GET `.../{id}/review-receipts/{key}?candidate_hash=...`；GET `/api/v1/copy/candidate-requests/{key}`。UNKNOWN仅查询原键。

本地组合K1/K2/K3纯与HTTP替身测试实跑121passed/0.80s，新增八文件strict mypy、Ruff/format通过；
K3当前28个真实PG节点仅collect，全部NOT_RUN。覆盖真实矩阵代码：显式指派/仅approver、原键同文/异文、
双连接同/异key及不同actor、撤权/TTL/提交时到期、grant/product锁竞争、NULL重hash、拒绝零草稿、
无draft批准提交失败、事务回滚/实际COMMIT后模拟客户端ACK丢失/原键只读恢复、历史不可改和outbox计数不增。
HTTP替身不签真实session/数据库Gate；ACK模拟不是raw-wire捕获，新Store实例也不称进程重启验收。
开发Ruff导入/行长、mypy动态Literal、漏Manifest导入均修复；未执行新PG或删改既有Gate。

0019精确父提交已由Root交付37e7e99e89fdfc7b87145317fabf373306d60dfd，实际revision为
`0019_p6_daily_reports`。遵Root指令先普通冻结本K3候选，再普通merge该精确提交并另提交0020父标识修复。
0023仍只保留待0022转交的父依赖，不预填其SHA；整体Alembic graph/升级/K3 SQL、完整CI、人审均NOT_RUN。

### K3 P2：不同候选复用审批请求键的竞争修复候选

原cf86独审发现：请求键唯一范围是`(organization_id,actor_id,request_key)`，
原先只锁单一candidate；同一approver并发审核两个不同candidate、复用同一key时，
双方都可能先读不到receipt，败方触发UniqueViolation并走503，未返回约定的异文409。
该P2与原121纯测试通过事实分记，不能由旧测试签收此竞争行为。

本修复给原请求键约束固定名`p6_copy_decision_request_key`，只将decision与draft两次INSERT
放入一个局部savepoint；捕获时必须同时匹配business schema、p6_copy_decisions表和此约束名。
局部回滚完成后按原org/actor/key读取已提交receipt，异文409、同文返回原decision/draft；
未读到则503，不假定已回滚、不重试写入、不换key。其他唯一约束异常原样抛出，
原候选行锁、同候选first-decision、权限/来源/TTL与commit原子约束均保留。

新增六项离线故障注入验证局部回滚先于receipt查询、INSERT仅一次、异文/同文/缺回执，
以及错误schema/table/constraint不被吞掉；使用真实psycopg UniqueViolation诊断字段，
SQL和事务仍为替身，不签实际数据库竞争。新增PG节点在真实source replay之后以Barrier(2)
让两个不同candidate的审批会话均到达INSERT前，要求一份saved、一份确切409，
并核count为2candidate/1decision/1draft/1review audit；原同candidate并发节点保留。

本次组合纯与HTTP替身测试实际127passed/0.84s/exit0；四个变更Python文件strict mypy、
Ruff及format通过。K2 30与K3 29共59个PG节点仅collect/0.70s/exit0；
本线未运行PG、Docker、SDK或模型。K3实际SQL和独审仍pending，0023父0022仍待精确交付。

### K3 Web响应、独立合同与合成Query配置交付候选

Root已回执e40请求键修复独审ACCEPT_K3_KEY_FIX/127独立纯测试，另交付S3精确对象32dd7c2，
只读核对其0022→0021与本K3父标识一致；本线仍未合入S3或运行完整链/PG。
Root随后明确放行本片补完必要Web DTO、独立OpenAPI和默认关闭的显式Query loader；
本交付不改e40的CopyStore、0023、锁或PG测试，也不修改共享API/Worker/database/旧合同/CI。

新`application.knowledge_copy.http_models`严格表达真实Store.read的四种状态、source_current和draft_id，
以及创建原键UNKNOWN、已确认approve/reject决定、原键UNKNOWN决定与各自envelope。
saved可在来源之后失效时保留原draft；UNKNOWN不带已保存ID、不解释为rollback、不自动写入。
Router在序列化前按DTO重建，决策还核原candidate id/hash/key；坏Store输出固定503。
GET始终重新认证；新增离线负例在模拟ACK丢失后撤销session，读取返回401且不调用Port读取或再写。
这只是替身边界，不签真实session、网络ACK或真人操作。

原COPY_*错误不在P3冻结枚举内，本片显式映射到PLAN_CHANGED/DECISION_CONFLICT/NOT_READY/
ACCESS_DENIED/SERVICE_UNAVAILABLE，保留原IDEMPOTENCY_CONFLICT；未知内部码不回显。
错误仍是合法p3-web-v1 Error形状/原枚举，receipt=null/retryable=false；旧P3/P4/P5资产不改。
新独立`copy_openapi()`包含五操作、path/query/Origin/CSRF/cookie、POST请求、成功/UNKNOWN及错误依赖闭包；
`separate_copy_legacy`只移除五条已声明路径和未被其他操作引用的新model，未知路径仍由export_web拒绝。
Root仍须在主API正确位置调用两helper，默认关闭与daily/copy四组合接线尚未在本线实施。

新`load_copy_deployment(path,enabled=False,expected_sha256=None)`默认返回None且零文件读取。
显式启用要求原始文件sha256、绝对路径无..、逐级NoFollow、regular/0600/当前owner及32KiB限长；
duplicate JSON、非有限数、未知字段、重复org/shop/ref、错误query/profile/vector/binding/config摘要均拒绝。
query_ref必须为版本化引用（以@query_version结尾），最多100项；额外按实际PG float4范围验证向量。
模型/provider/publication三标志只能为真实bool false；只有self-authored synthetic Query，
只返回不可变映射，不读取env/Secret/数据库、登记来源、构造provider或接受HTTP权限/向量。
source许可、owner登记和当前授权仍由原Store/SQL独立核验，不由配置摘要授予。

同源资产：docs/contracts/p6-copy-web-v1.schema.json、同名.openapi.json及包内.openapi.json；
`python -m scripts.export_copy_schema`重生成；UI消费边界见[p6接线清单](p6-knowledge-wiring-v1.md)。
JSON Schema验证结构；精确引用/显示公式/hash/source/current auth仍须真实DTO/Store。
共享wire案例明确保留“结构合法但hash公式被改”的DTO拒绝/Schema允许差别，不把schema通过当授权。

本地最终组合185passed/1.02s/exit0；九个变更Python文件strict mypy/Ruff/format通过。
独立Ajv2020 8.20.0/formats3.0.1严格校验24案例和五操作请求/响应schema通过，实际Node20.20.1；
依赖仅从既有npm缓存离线安装到新/tmp目录，无生命周期脚本、网络或项目依赖/锁改动。
该证据不是锁定前端Node24.21.0的build或UI验收。K3原29PG只collect，实际SQL仍待Root。
开发保留：首HTTP1failed/11passed由父校验器影响嵌套strict tuple的JSON处理引起，
已仅在JSON表示层转不可变tuple且保留Python输入strict；首资产比对1failed/42passed为错误闭包set顺序不稳定，
已排序再冻结字节。静态发现query_parameter漏profile参数等已修，不修改旧测试门槛。
本批没有PG/Docker build/浏览器/实际服务、SDK、模型或外发；全链、主API/owner bootstrap、真实资料与人审仍未签收。

### Root回交K3真实本地PG与dev-only seed候选

Root回执Core8933f85ba2c121dd25892947d1dd19a02305ade6（含769 fixture与e371分段DB等待修正），
新owned m3core-4154f023a3bf实际29passed/61.99s/native0/outer0；05:33:00.005130Z cleanup0，
独立库存0容器/0网络、唯一新卷保留。原setup29错误、后28passed/1 QueryCanceled57014及旧窗零资源未运行事实保留；
本次成功只绑定旧image4eb与该Core，不代签新标准image946、真实资料/provider或主API/UI。

Root新放行本地可验证窄片：普通合eff02e3精确冻结后，提供仅新m3_daily_demo库的copy seed/export CLI，
沿原Web账号/scope、原owner注册helper和纯合成fixture，不改业务/API/Worker/迁移/权限/锁实现。
Root待审接线1e30c999不由本线合入；使用和边界见[接线清单第5节](p6-knowledge-wiring-v1.md#5-新owned本地演示来源登记与导出)。
本线仅代码、纯构造/临时文件/CLI帮助与collect验证，seed SQL/服务/Web/浏览器均未运行；真实执行仍由Root登记。
新dev-only CLI与原knowledge/copy纯测试组合193passed/1.42s/exit0；新增两Python文件strict mypy、
Ruff/format通过，CLI --help native0，Markdown133文件/0错误。
新8项离线案例只验证命名与低权拒绝先于连接、合成scope/有效期/配置pin往返、
0600/0700独占文件、禁止覆盖/祖先symlink及help不读取配置，不签SQL筛选或登记通过。
