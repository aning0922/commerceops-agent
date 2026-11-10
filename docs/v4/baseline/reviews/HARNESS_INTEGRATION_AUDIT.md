# Harness / M3 集成只读审查（A）

日期：2026-11-03，Asia/Taipei。结论：**可继续 A 的合同冻结；禁止把当前结果当成 B 开发、Harness 合并或新 PG/CI 的准入。建议 V4 以已核 M3 为产品基线，暂不引入 Harness，另立独立兼容候选。** 直接整体合并两支的语义兼容性尚未成立。

本报告只读取精确 commit 的 tracked 内容与资料包，使用 Git 对象查询、diff、Python 标准库文本/AST/JSON解析；没有导入执行仓库模块，没有 pytest collect、测试、工具安装、扫描器运行、Docker/PG/Web、分支/worktree创建、commit/push/远端写、私有runtime/密钥读取或付费调用。引用的历史结果只是 tracked 文档里的记录；未读取其私有原日志。本轮写入仅本报告和同目录 SHARED_FILES.json。未读取本地 Harness b9ceaf3 或其 WIP。

## 1. 精确基线与引用规则

| 别名 | commit | tree |
|---|---|---|
| B/main | 6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265 | ac92562c26d24eb183143e52de64e5a51282948c |
| M/M3 | 952e6246deb01ec763f2541d9f316753987744f3 | 43e4e732824e23b991660a4f7882ba8f5a265df1 |
| H/Harness | 684e645feb1dbe0a27864ca2308fe1afd9fa948d | 7d063bad82294de006f38a520ef84a435f1fd215 |

远端 SHA 为 ROOT 此任务开始时提供的 ls-remote 观察；本审查核实本机对象及 tree，没有再次联网取证当前 PR/CI。`git merge-base M H` 实际返回 B。相对该共同祖先，M 修改/新增 224 条路径，H 69 条，两支共享修改 **8** 条；未执行试合并，不将共享文件数称作 Git 文本冲突数。完整路径、各 blob/hash/行数与 diff hunk 在 SHARED_FILES.json。

下文 `M:path:Lx–Ly` / `H:path:Lx–Ly` / `B:path:Lx–Ly` 均绑定上表完整 commit；不是当前工作树行号。`P:path:Lx–Ly` 指资料包 `/Users/aipuli/Downloads/CommerceOps_V4_Codex_Development_Package/` 下对应文件。新增路径、owner、Gate 明标为 **PROPOSED**，并非已有功能或实施授权。

当前事实入口：M:AGENTS.md:3–7 明示 M3 LOCAL_IMPLEMENTATION_ACCEPTED / EXTERNAL_ACCEPTANCE_DEFERRED_BY_USER；H:AGENTS.md:3–17 与 H:CURRENT_STATE.md:1–30 仍是 Harness 自己的历史快照（含 M3 unapproved 与 H3未验），不能覆盖 M3的新事实。B:AGENTS.md:3–5 是较早M2收口导航；本报告不据此重新裁定M2结案。

## 2. 优先阻断与最小取舍

| 编号 | 结论与影响 | 精确已有依据 | 最小取舍（PROPOSED） |
|---|---|---|---|
| HIA-01 / BLOCK | H 六分片入口没有 M3 image preparation/override；若直接以H workflow覆盖M，会丢失PG17.11/pgvector0.8.7及Web/N01来源绑定。只增加节点数不能修复。 | M:.github/workflows/quality.yml:47–56,113,167,209–223,328–344,481–489,573,641,733–749；M:scripts/m3_pgvector.py:18–26,66–87,99–134；H:.github/workflows/quality.yml:97–125（路径同上） | 暂不引入Harness；如以后适配，所有实际PG片段与Web/N01均绑定M3 image receipt/inputs/source/tree，不能只适配主PG job。 |
| HIA-02 / BLOCK | 动态发现完整节点不等于执行分组已兼容。H只抽出P5，其ordinary包含M3新增族；M已将daily/p6/m3拆成自然模块。照搬H会把这些重新塞进共同ordinary/Checkpoint group，增加300秒命令风险并失去M3既有分组。 | H:scripts/pg_diagnostic.py:69–88；M:scripts/pg_diagnostic.py:m3_pg_module/combined_groups:75–102；H:scripts/pg_ci_evidence.py:_assignment/plan_shards:544–598 | 保留M的自然模块、旧approval14/history7+7/read-parent6+5/terminal4边界；以当前动态完整集合构造新计划，缺权重不是漏测理由。 |
| HIA-03 / BLOCK | H环境只读取compose.yml中postgres digest，schema强制postgres格式；这不绑定M3构建镜像。H同时要求六个job实际image ID完全相同。不同runner各自build相同Dockerfile是否产生相同ID未证明；不能静默删除等值检查。 | H:scripts/pg_ci_evidence.py:441–482,485–515,777–796；M:scripts/m3_pgvector.py:99–134；M:scripts/pg_ci_evidence.py:81–96 | 先裁定单一不可变amd64镜像分发/复用方案，或另审新的严格等价合同；记录base digest、inputs、源码、平台、pgvector版本及actual image ID，不把基础postgres descriptor当运行镜像。 |
| HIA-04 / BLOCK | H旧扫描器只接受17例外/10历史，M为45例外/20历史；覆盖任一侧会导致缺规则或Fast API不兼容。 | M:scripts/scan_secrets.py:56–331,334–483,486–526,528–571；H:scripts/scan_secrets.py:193–218,322–362,391,540–550；两支scripts/gitleaks_rules.json整文件 | 以M生成器/TOML/provenance/精确line+span为底，若以后引入H Fast，只移植current-only选择能力并保留Full完整历史；不得以按目录豁免化解冲突。 |
| HIA-05 / HOLD | M3两次native139根因未知；H有独立本地C watchdog机制探针和Python Timer候选，但不是M3故障诊断证据。只复制timeout=0会失去45秒观察，只复制plugin会叠加两个watchdog。 | M:docs/M3_LOCAL_ACCEPTANCE.md:36–40,62–73；M:scripts/pg_diagnostic.py:843；H:scripts/pg_diagnostic.py:765；H:tests/diagnostic_plugin.py:24–60；H:docs/harness/h2/native139-local-repair.json:2–24 | 默认保留M；若另批采用诊断修正，将timeout0+Timer整套作为单独小候选，与M安全异常/帧白名单合并；保留外部300秒/总截止，复现先取native栈，不无限重跑。 |
| HIA-06 / HOLD | 已有文档与精确源码的超时口径不同；性能和容量尚无本轮证据。 | M:docs/M3_LOCAL_ACCEPTANCE.md:23,64 写Hosted35/33未验；但M:.github/workflows/quality.yml:15,31,450,465为45/43与50/48（B亦如此）；H:.github/workflows/quality.yml:15,69,81,151,162,544,592,640,651 | 合同引用当前可执行值并另列旧历史文案；不能拿旧40/42本机例外或H43分钟六片证明新组合容量；是否变更任何预算另决策。 |

以上阻断作用于“Harness引入/联合CI签收”，不阻止只读A和后续独立M3产品合同设计。现有719节点并非永久验收常数。

## 3. 动态PG、G1/G2与完整门禁

**已有M3历史，不是本轮执行：** M:docs/M3_LOCAL_ACCEPTANCE.md:21–28,62–73 记录受测532eefd的3684 offline、existing542+phase3177=719、无交集与G1/G2/严格配对；两次139、一次期限耗尽137及未跑项均保留；最终本机串行40分钟诊断/42分钟外层不代表Hosted容量。本报告没有用M HEAD代签该历史受测SHA，也没有重跑719或3684。

**已有H机制：** H:.github/workflows/quality.yml:32–59 用当前integration collect生成full.json及6片计划；H:scripts/pg_ci_evidence.py:574–598只把weights作为提示。H:docs/harness/h2/weights.json包含590个键，没有daily/p6/m3族键；新节点缺weight走1.0（:556–558），不会因此被筛掉，但负载估算不能称实测时长。590→719历史差129不是本轮精确node delta：当前参数化节点须经另获授权的实际collect证明。

**已有验证强度：** H:scripts/pg_ci_evidence.py:668–796要求完整计划/actual/passed严格相等、模块native0、父native0、cleanup0/stopping、同run/attempt/source/tree/tools、唯一项目、全片native success、并集等于完整集合。取消/skipped不得充成功。H:.github/workflows/quality.yml:121–138在父进程返回后finalize实际native_exit。M:scripts/pg_ci_evidence.py:370–379则验证原两分区来源/指纹/并集，不能混用两套旧回执。

**G1/G2细节必须显式保留：** M:scripts/pg_ci_evidence.py:97–104的G2_REQUIRED是五个基础场景，:355–366为subset校验；M:scripts/pg_diagnostic.py:953–961同样五项subset。历史完整运行文档记录“六场景”，但这与validator最小谓词不是同一句话。H:scripts/pg_ci_evidence.py:378将retired_probe_version_refused加入G2_V2_REQUIRED，:735–742要求shard0精确G1=3/G2=6，其余片0/空；_assignment:547–553确保Checkpoint完整组唯一。未来合同必须列出六个名字，既保留真实六场景，也不把M的历史六场景反说为源码已强制exact-six。此处未建议本轮改M测试或validator。

**完整工程入口：** M:scripts/check.py:15–30含全历史扫描、锁/lint/type、Copy Ajv strict、M3无server合同、offline、frontend检查/漏洞；M:scripts/check_m3_contracts.py:26–86拒绝skip/retry及collect/执行集合不一致。M:frontend/package.json:22保留全部M3 schema工具。H:scripts/verify.py:175–229只有H1映射，unmapped impacted=Full required/NOT_RUN，不能冒充V4覆盖；且其:185依赖M现有CLI没有的--current-only。建议A合同直接登记M原检查与各专项，Fast/Impacted在独立适配验收前不成为任务卡的可执行默认命令。

## 4. 工具链、时限、清理与Web/N01

| 项目 | 精确已有行为 | 集成合同要求（PROPOSED） |
|---|---|---|
| 工具链 | H:scripts/pg_ci_evidence.py:485–506固定Python3.12.13 / uv0.11.25 / Node24.21.0 / gitleaks8.30.1及binaries/LOCK_FILES；M:scripts/pg_ci_evidence.py:81–96额外纳入M3镜像输入 | 取完整M锁/镜像输入并集，新增变更须重核；H环境仅接受Linux x64（:479），本地ARM历史不能冒签。 |
| 容器优化 | H:infrastructure/Dockerfile:10–15仅test stage加--compile-bytecode；M未改此文件 | 可选优化，需独立源与环境验证，不列为B前置必要功能。 |
| 原M PG | quality outer45/deadline43；phase3 outer50/deadline48；N01 25/23；frontend35/33；pair5 | 本轮只登记；不得因文案35/33自动修改可执行值。 |
| H topology | quality15为collect/plan；6个pg-shards各45/43；phase3变聚合15；pair5；N01 25/23；frontend35/33；额外merge-gate5 | 同名job语义变化要列清；保留existing required contexts，并验证aggregate实际依赖，不能由旧job名推定旧测试已执行。H:.github/workflows/quality.yml:542–637,982–996；H:scripts/merge_gate.py:11–32。 |
| 单命令/停止 | M:scripts/pg_diagnostic.py:269,514,596–601；H同文件:264,475,540–545：300秒命令，expires-75运行截止，cleanup最迟min(expires,now+60) | 总截止、单命令、等待/终止与资源预算分别记账。M3镜像build/准备要包含在已登记deadline内。 |
| PG临时资源 | 两支diagnostic finally的down --volumes（M:1083–1099；H:997–1024）；H分片要求最终containers/networks/volumes=0（evidence:743–773） | 属于本次新owned测试项目，不自动套用旧私有卷；不能统一写成“都保卷”。 |
| Web/N01资源 | M:quality.yml:209–223,328–344,393–396,733–749,810–829绑定override/来源；H:.github/workflows/quality.yml:475–476,945–947验证Web/N01停止并保卷 | Web/N01保卷与PG临时项目删卷分账；仅当前明确owner资源可清理。read7/write10/items7与N01six不被M3新页面合同替代。 |

H的H3性能是否已正式接受不能靠资料包“后续单次Full成功”一句决定；H:CURRENT_STATE.md:12–25写新topology Hosted/performance NOT_RUN，H3 IN_PROGRESS_NOT_ACCEPTED。P:05_quality/TEST_AND_ACCEPTANCE.md:7和H:docs/harness/h3/README.md的历史成功应逐个绑定实际source/topology；A本轮未联网核PR/CI，保持REMOTE_GATE_NOT_REVERIFIED。

## 5. 八个共享文件的唯一owner与依赖

以下是 **PROPOSED职责角色**，不是已经创建的会话或工作树。ROOT须绑定具体一位作者与冻结TaskSpec；审查人不得兼任该切片作者。所有owner在本轮A均无仓库写权限。

| 文件 | 唯一写owner | 依赖/禁止覆盖 |
|---|---|---|
| .github/workflows/quality.yml | CI_INTEGRATION | 消费M3镜像/PG/Web与H v2证据接口；WEB提供已审runner提交，不与CI并写。 |
| scripts/pg_diagnostic.py | CI_INTEGRATION | grouping、image、subnet、timer、native出口/cleanup必须同源。 |
| scripts/pg_ci_evidence.py | CI_INTEGRATION | 先冻结image/schema/plan/aggregate合同，再落脚本。 |
| tests/diagnostic_plugin.py | CI_INTEGRATION | 保留M3白名单与H完整timer方案；与diagnostic一起审。 |
| scripts/scan_secrets.py | SECURITY_SCAN | 先合精确provenance，后CLI兼容；不得删M3固定span。 |
| scripts/gitleaks_rules.json | SECURITY_SCAN | 与.gitleaks.toml/vendor生成器同批、逐项精确。 |
| tests/test_quality_gates.py | SECURITY_SCAN | 同步真实合同，保留新key/异内容/错源拒绝。 |
| AGENTS.md | ROOT | 保留原历史与新M3状态；不整段继承H过时授权。 |

静态AST比较结果：M APPROVED_TEST_HISTORY 20条，H 10条；**H的10条逐字段均为M的子集**。两支gitleaks_rules.json分别45/17 exact exceptions及20/10 historical_findings，规则总数同222。此结论仅适用远端H684与M952，不适用本地b9的17指纹或任何未来历史扫描结果。只比较表内容，没有运行扫描，也未读这些引用指向的私有资源。机器清单记录8共享文件全量hunk，另附非共享但必须一起审的脚本/Compose/测试/Web依赖。

## 6. 首五任务卡的精确文件地图（PROPOSED）

来源：P:03_delivery/TASK_CARDS.md:9–15；P:03_delivery/OWNER_AND_PARALLELISM.md:5–20仅给示意owner，尚未冻结到路径。本表提供最小首批归属；新名称须ROOT合同裁定，**不声明这些新路径已存在**。

| Task | 单owner与拟文件 | 依赖及Gate |
|---|---|---|
| V40-01 | ROOT；外置BASELINE_REPORT与本报告/SHARED_FILES，仓库0写 | 三精确SHA/tree/merge-base、8共享文件、历史719 vs新NOT_RUN、PR/CI若未重核明确unknown。 |
| V40-02 | ROOT为四合同最终唯一作者；建议外置contracts/v4-ui-contract-v1.md、v4-domain-contract-v1.md、v4-permission-matrix.csv、v4-public-openapi.json，附v4-demo-seed-manifest.json和PG_TEST_PLAN.md | V40-01；API字段/错误、principal/tenant/shop/source/epoch、期限、回执、reset/persona行为与现有M3入口逐项映射，独审后再请求B。当前仅本报告允许写，其余由ROOT另派。 |
| V40-03 | SCHEMA_API；拟新backend/src/commerceops/application/demo_v4/contracts.py、infrastructure/demo_v4_sessions.py、entrypoints/demo_v4_http.py；拟新tests/test_v4_demo_sessions.py、tests/test_v4_demo_sessions_pg.py；共享api.py/database.py仍只该owner；迁移由同owner从0023线性新增，具体revision在TaskSpec分配 | V40-02+B明确批准；先鉴权/CSRF/epoch/TTL合同，后新ownedPG及浏览器准入。M:backend/src/commerceops/entrypoints/api.py:create_app:30–147；infrastructure/web_sessions.py:SessionStore:159–420、actor_guard:59、role_scope:113为已有只读对照，不未经专项批准改旧session。 |
| V40-04 | 同一SCHEMA_API；拟新application/demo_v4/seed_contracts.py、infrastructure/demo_v4_seed.py、scripts/v4_demo_seed.py、tests/test_v4_demo_seed_pg.py；新增迁移严格串行；共享demo_v4_http.py由原owner增量修改 | V40-02/03；seed版本/hash/对象引用、同key异文冲突、reset并发/晚到/他租户零影响、旧M3/Woo零改。先只初始化首阶段已定义实体，六场景其余数据作为版本化fixture，不提前写完整采购/客服状态机。 |
| V40-05 | 拆成05W=WEB和05Q=独立REVIEW_QA，避免WEB/QA共同owner。WEB拟新frontend/components/v4-demo-entry.tsx、frontend/lib/v4-demo-client.ts并唯一持有page.tsx/live-console.tsx；QA拟独占frontend/v4-tests/demo-auth.spec.ts和frontend/playwright.v4.demo.config.ts；frontend/package.json唯一WEB消费已审QA入口，不让两人改同文件 | V40-03/04与冻结OpenAPI；真实API/PG与浏览器1440/390、跨session/shop/角色、过期清空、重置/晚到拒绝、原M3 smoke，列各模式。运行仍须新的owner/资源/UTC许可。 |

已有入口锚：M:backend/src/commerceops/entrypoints/api.py:30–147(create_app)，database.py:19(migrate)/38(grant_runtime)/250(grant_knowledge_copy_runtime)；M:frontend/app/[[...path]]/page.tsx:9(Page)，frontend/components/live-console.tsx:112(LiveConsole)、138–218(session/失效)、430–468(当前身份刷新)、771–775(M3组合)；M:frontend/package.json:17–22(工具链/合同)。M3旧0019–0023迁移不可改号/覆写，主Worker在首五卡不需要新增调度，作为只读依赖。所有新增路径是设计建议，不能以此提前创建文件。

## 7. 资料包矛盾、缺决策与四合同独审检查点

1. **四合同清单不一致。** P:TASK_CARDS:12称UI/领域/权限/OpenAPI四份；P:DATA_AND_API_CONTRACTS:89–91列domain/OpenAPI/permission/seed四文件却少UI；P:PHASE_ROADMAP:26同样UI为四合同之一。建议“四核心合同+seed manifest+PG计划”统一清单，seed是附件，不能用seed替代UI。
2. **reset的会话返回行为缺失。** P:DATA_AND_API_CONTRACTS:35与SECURITY_AND_DEMO:12要求旧session/epoch立即失效，UI又要一键重置继续体验；必须选“成功原子轮换token/principal/CSRF/epoch”或“注销后重新进入”，定义reset成功但ACK丢失的原key只读路由。不能一边撤销token一边要求旧token查询任意新数据。
3. **TTL与并发目标未冻结。** SECURITY_AND_DEMO:7无活动续期待定、:10建议2–5；PHASE_ROADMAP:27 Gate两并发；RISK_AND_DECISION_REGISTER:R12写三人初测；TEST_AND_ACCEPTANCE:49写五浏览器。建议首版30分钟绝对TTL不滑动，产品准入cap与负例并发区分：cap2时五浏览器应验证2准入/其余受限，不承诺五活跃会话容量；实际数由ROOT/用户冻结，不能从建议推导已批准容量。
4. **V40-04六场景 vs后续业务迁移存在依赖倒置。** TASK_CARDS:14要求六场景稳定，而采购/客服/营销真正状态机到V4-2/3。PHASE_ROADMAP:28又禁止V4-0大规模采购迁移。建议首阶段fixture可引用六场景但只建身份/覆盖层/首场景必要实体；后续场景“不运行/未实现”，不得以种子存在签六条全链。
5. **V40-05与首页Gate有缺口。** PHASE_ROADMAP:27要求进入→有数据首页；TASK_CARDS把dashboard API放V41-02，完整shell放V41-01。建议V40仅用最小数据摘要/现有M3授权页面证明身份与隔离，或明确提前一个只读dashboard子切片；不要暗中把V41内容计入05。
6. **CI owner和双owner未闭合。** OWNER_AND_PARALLELISM:5–11没有CI/扫描专项角色，TASK_CARDS:15又写WEB/QA。采用本报告角色分工与05W/05Q，ROOT为每个角色绑定唯一实际会话；迁移/主API/frontend shell/公共验收各唯一作者。
7. **Harness何时必需。** BASELINE_AND_INTEGRATION:25–29说独立适配，RISK登记R02要求V4-0核查，TASK_CARDS:66又把完整兼容裁决放V45-02。建议V4-0完成只读风险结论即可，Harness不进入V4依赖；若后来要采用，必须先过独立兼容Gate，不能推迟到最终发布再发现运行合同错误。
8. **历史状态不可折叠。** P:TEST_AND_ACCEPTANCE:6–8的719/3684与H成功都只能回到各自精确源。M验收中35/33文字与当前workflow45/43、50/48需在合同解释为历史文案差异，不能默认现值已测。H的CURRENT_STATE还称M3 unapproved，必须标历史，不覆盖M AGENTS。
9. **Tool预算负例措辞含歧义。** P:AGENT_AND_AUTOMATION:38记M3最多3次模型/4工具；P:TEST_AND_ACCEPTANCE:46说“第三轮继续工具”应拒绝。四合同以后如涉及该项，必须按原M3阶段状态/调用次数精确映射，不能把自然语言第三轮直接变成新2轮限制或放宽既有终轮规则。

上述为独审包的决策清单，不代替SCHEMA/API对领域/鉴权的专项审查。四合同收到后应逐项核对以上编号、single owner、已实现/proposed、资源授权和退出证据。

## 8. 后续Gate顺序与交付结论

A0（本轮）：只读源码/资料包、冲突地图、合同待决项完成；执行/性能/测试均NOT_RUN。A1：ROOT统一四合同+附件与owner并交独审；只通过文档不自动批准开发。

未来B若另批准：先M3产品底座→V40-03→04→05W/05Q→同源独审及各获准本地Gate。若选择Harness，独立路径为“冻结兼容合同→单CI作者+单扫描作者各独立文件→源码独审→实际current collect与no-.git收集→单owned targeted诊断/失败清理→完整新集合与G1/G2/Web/N01→同源Hosted（仅获准后）→Root裁决”。失败/未跑保留，授权耗尽不自动续窗。

最小决策建议：**A采用M952为产品事实基线；暂不移植Harness；保留M现有完整门禁；native139保持UNKNOWN；冻结四核心合同+seed附件/PG计划；首五卡按单owner地图切片。** 这允许合同推进，同时把六分片性能、镜像跨job一致性、扫描Fast兼容与native139诊断作为有明确边界的后续候选。未创建候选、未修改参考包、未宣布V4-0完成。
