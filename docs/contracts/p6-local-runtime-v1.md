# M3 本地 PG 镜像与运行接线提案 v1

2026-11-03（台北），状态 **PROPOSAL / ROOT_REVIEW_REQUIRED**。唯一基线 `671a4b3548403c6e1c1acfd61e56bf8b31968bbc`；本批只新增本文，不执行命令示意、不改配置或业务实现。

## 问题与已核来源

当前 [compose.yml](../../compose.yml) 的 `postgres` 是固定 stock PG17.11 digest，只有PG、db-init、pg-test；不会因Dockerfile已存在而获得vector。基线迁移文件止于0019，不能称其已含完整M3 head。

已审构建提交 `8ee1df005823502d587344dcf23f7b3f59038ffa` 的 [Dockerfile](../../infrastructure/knowledge_pgvector.Dockerfile) 和 [pins](../../infrastructure/knowledge_pgvector.pins.json) 基于同一PG17.11 digest，仅在runtime增加vector0.8.7文件，支持arm64/amd64，扩展仍由owner迁移创建。固定K2早期源码 `8a6c6ebb59abf451c810bb6aebcdf1b8f6510e9d` 的0020明确在`knowledge_ext`执行`CREATE EXTENSION ... VERSION '0.8.7'`；该早期提交的parent还是占位，不作为可运行head。

Root阶段记录已证明arm64镜像构建，tag为`commerceops-m3-vector:8ee1df0-arm64`、image ID为`sha256:4ebf3de8870438618836dd1765632b7e90cb950632c929162441367087439d5a`。本次派单另确认K2实际migrate20成功；该新事实未附精确迁移提交，本提案不推算SHA或将之签给基线。旧pins及准备合同中的NOT_RUN属于原时点，不改写。amd64构建及本提案接线均未验证。

| 实际入口 | 已核约束及影响 |
| --- | --- |
| [pg_diagnostic](../../scripts/pg_diagnostic.py) | 固定`-f compose.yml`，不会读环境中的默认override；build只构建db-init/pg-test，120s；healthy75s，单初始化30s，测试命令300s。原绝对截止减75s停止业务，清理最多60s且不越总截止。 |
| [双PG集合/配对](../../scripts/pg_ci_evidence.py) | 全量实际collection决定existing/phase3分区；P6当前自然落existing。actual=selected=passed、双分区交集0且并集等于全量；同SHA/tree/tools/文件fingerprints，G1三验证与既有G2保护完整保留。 |
| [N01入口](../../tests/e2e/web/run_c09_n01.py) | base compose加新私有port overlay；新PG/API/Web段，75s清理预留。CI外层还精确核Docker `config_files` 标签。 |
| [三批Web入口](../../tests/e2e/web/run_live_batches.py) | read/write/items各自base compose加私有port overlay，共同绝对截止和75s预留；API迁移同样需要vector镜像。 |
| [M2 owned](../../scripts/m2_owned.py) | `PG_IMAGE`精确固定旧stock digest；overlay相等校验、实际`Config.Image`与project/port/volume身份校验；显式`-f compose.yml -f 私有overlay`；cleanup reserve180s且down保卷。 |
| [M2备份](../../scripts/m2_backup.py) | revision精确0018、PG170011、精确60表、低权/ACL/checkpoint和全表快照校验，不允许借M3扩大。owned source-init调用migrate(head)，因此不能把该旧场景直接当M3 head备份工具。 |
| [M2 PG回归](../../tests/test_p5_m2_backup_pg.py) | 用隔离schema显式初始化0018继续核旧60表；该真实PG回归继续包含在完整collection，不因M3排除。 |

## 方案比较与推荐

| 方案 | 好处 | 额外影响 |
| --- | --- | --- |
| 默认compose改为vector image+build | 各硬编码base入口自然取得vector。 | 改变旧入口含义；M2 overlay会覆盖image却仍可能继承新增build，必须证明不会把扩展镜像构建并标记成原stock tag。还会给旧场景引入新冷构建与检查义务，不能仅改一行后宣称兼容。 |
| **显式`compose.m3.yml` override（推荐）** | 基础PG/M2镜像与保护保持原含义；同一个`postgres`服务/数据库/卷接口，M3明确选择vector。 | 必须逐一接入所有当前head消费者和清理验证，单放文件不足；需要显式构建、镜像身份及同源文件核验。 |

推荐override只覆盖`services.postgres.image/build`，不新增PG服务、数据库、端口、secret、volume或业务服务。新镜像建议固定专属tag `commerceops-m3-pgvector:8ee1df0-v1`，构建上下文仓库根、Dockerfile固定为上文已审文件；不覆盖stock tag，也不重标Root旧arm64实测tag。本机native arm64/CI native amd64分别构建、记录实际arch/image ID/PG与vector版本；跨架构不可直接借用已有image ID。

## 放行后的最小改动清单

1. **新增`compose.m3.yml`**：仅上述postgres image/build，沿用base healthcheck、owner文件secret、禁SQL错误日志配置和pg_data。原`compose.yml`、M2 PG_IMAGE/overlay及backup规则不改。
2. **现有helper加封闭选择**：建议仅`--m3-pgvector`，不开放任意compose文件/镜像输入。诊断器、N01和三批Web固定追加`-f <root>/compose.m3.yml`，最后仍是其原私有port overlay；所有up/run/restart/recreate/stop/down共用同一有序文件列表。目录/配置不符、缺vector镜像/错误架构或版本即拒绝，不回退stock。不建新的通用runner或第二Worker。
3. **显式构建及来源绑定**：M3模式先用同一文件组显式构建postgres，受既有父绝对截止约束；PG up必须禁止隐式build/pull，以免绕过该阶段预算。既有db-init/pg-test build120s不被暗中延长。CI可在调用诊断/Web入口前完成有界镜像build，诊断内部只校验已构建镜像；本地同形使用Root另核的新构建窗或原父窗内明确阶段。新增compose/Dockerfile/pins进入PG fingerprint、Web source manifest和私有资源登记；记录实际image ID及预期版本，不能只信tag。compose文件顺序和hash在退出时再次核对。
4. **CI最小同步**：[quality workflow](../../.github/workflows/quality.yml)仍五job：quality、phase3、n01-web、frontend、pg-pair；前四个当前head PG消费者选择M3，pg-pair仍精确配对。N01 CI外层cleanup的`config_files`从原base+port同步为base+M3+port的精确列表，不能删除/放宽该身份断言。三批Web的父子登记与停止校验同样同步；不得只改启动命令遗漏异常清理。
5. **必要契约验证**：核M3合成compose只有一个postgres、原秘密/日志/卷约束；默认M2 overlay/image与旧backup fail-closed不变；错误选择/文件篡改/错镜像拒绝；清理使用同一文件组。保留原PG全节点、G1/G2、Web各批/N01六项及全部工程检查。只在实际collection/容量证据表明有必要时，复用现有分组机制把完整P6自然模块拆成独立300s命令，分区/节点/总截止不变，另交Root审查。
6. **README当前M3启动段**：明确所需文件顺序、全新私有目录/project/卷、PG17.11+vector0.8.7、迁移/checkpointer/grant顺序、实际head及显式停止。说明旧M1/M2运行说明的历史范围；不把M3新head的失败归到旧已验场景，也不将旧M2备份门禁扩成M3备份承诺。S3交付前只公布PG基础/诊断路径，不提供虚假的完整M3应用启动命令。

实施时如需触及本文之外的共享入口，由Root协调owner；本轮不提前改上述文件。

## 本地与完整Gate的命令形状（未执行）

固定Compose文件顺序为`compose.yml`、`compose.m3.yml`、该owned入口自己的私有overlay（如有），所有子命令共用。新owned凭据仍由 [prepare_pg](../../scripts/prepare_pg.py) 生成，0700目录/0600文件，不读旧Secret、不复用旧卷或已消费窗口。

有界build并核镜像后，沿同一postgres执行`migrate → setup-checkpointer → grant-runtime → revision`，读取实际extension版本与线性head；不能只以health/live或pg_isready证明M3业务就绪。M3本地完整PG使用现有`pg_diagnostic --combined --full-smoke --m3-pgvector`（拟新增flag），`--session/round/deadline`由Root给新对象与实际UTC；该诊断器按原历史行为down删其新自有测试卷。开发演示段及M2/Web原保卷行为分别保持，不把CI删卷改记为保卷。

Hosted仍按原同SHA五job运行：quality为existing+full-smoke，phase3为phase3+无重复smoke，pg-pair验证精确集合。保留当前job timeout45/50min及从原登记点开始43/48min绝对截止；N01为25min/23min，frontend为35min/33min；PG命令/清理和Web预留均不增加。冷构建或新增P6令容量不足时如实FAIL/HOLD，Root依据证据另审容量，不能续旧窗、删节点或直接复用74.12s arm64耗时声称amd64必过。完整工程`uv run --frozen python -m scripts.check`仍不代替这些实际PG/Web Gate。

## S3依赖与证据边界

基线API只在显式daily配置存在时装配日报读路由；Worker读取`COMMERCEOPS_M3_DAILY_CONFIG_FILE`，但CLI仍是既有test-run/inventory-test-run等入口；[M1演示装配](../../compose.m1-offline.yml)调用专用m1 helper，并未证明消费完整M3来源/调度/知识/询单配置。S3 Backend仍在实施默认来源、单Worker/API配置与注册，本runtime任务不改其实现、不虚构配置字段或假注册。

完整本地应用启动依赖Root转交S3及K2后续精确已审提交、真实线性head和默认关闭外发/模型的配置合同；在新owned段使用自创合成资料/替身。真实资料、模型/embedding预算和实际发送不从本提案获得授权。原M2 backup在M3 head继续拒绝不匹配版本/表集合；若后续需要M3备份须独立合同，不在本片放宽。

本轮Markdown检查127files/errors0、Git差异空白检查通过。证据仅Git/源码只读核查、本文及文档检查；未运行Compose parser/build/PG/API/浏览器/模型/飞书或Hosted。本提案是否实施及具体资源窗口均待Root精确审查后放行。
