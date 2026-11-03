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
