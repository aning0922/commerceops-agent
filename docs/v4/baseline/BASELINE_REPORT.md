# CommerceOps AI V4 · BASELINE_REPORT（A只读接单）

2026-11-03，Asia/Taipei。授权仅A：只读源码/远端查询及外置文档。ANING LAB请求已被用户明确更正撤回；本次仅CommerceOps。参考包中的B/C是未来模板，不构成本轮代码或远端许可。

**V4-0代码NOT_STARTED。当前完成的是V40-01只读审计及V40-02候选合同文档，不是V4-0实施或可运行Gate。**

## 1. 实时远端、本地及证据来源

远端独立查询时间：2026-11-03T13:37:35.985082+00:00。实际运行git ls-remote与gh REST/PR/Issue查询，不用资料包历史SHA代替；原生命令exit和返回保存在evidence。最后收口另做只读复核，见GITHUB_FINAL_VERIFY.json。

| 目标 | 实时commit | tree | PR / checks / Actions |
|---|---|---|---|
| main | `6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265` | `ac92562c26d24eb183143e52de64e5a51282948c` | PR #50已合；quality/frontend/phase3/n01-web/pg-pair精确SHA五绿；run40432280677 success |
| codex/m3-control-20261103 | `952e6246deb01ec763f2541d9f316753987744f3` | `43e4e732824e23b991660a4f7882ba8f5a265df1` | 该HEAD关联PR=0，Checks=0，Actions runs=0；分支已存在远端，未合main |
| codex/harness-v3 | `684e645feb1dbe0a27864ca2308fe1afd9fa948d` | `7d063bad82294de006f38a520ef84a435f1fd215` | Draft PR #52 OPEN；精确SHA20个check success，run41063567853与41063567878 success；不代表M3兼容 |

这三者共同祖先为main当前HEAD。GitHub原legacy combined commit status在零contexts时返回pending；本报告以check-runs和Actions实际记录判断，不把该空pending升级为运行中或失败。PR52的旧CURRENT_STATE文字与实时checks事实分开，当前20绿也不能代签M3 719节点、性能或amd64适配。

[main精确CI](https://github.com/aning0922/commerceops-agent/actions/runs/40432280677)、[Harness PR52](https://github.com/aning0922/commerceops-agent/pull/52)、[M3远端提交](https://github.com/aning0922/commerceops-agent/commit/952e6246deb01ec763f2541d9f316753987744f3)。最新Issue实时查询：#51 Harness、#46本地CI仍OPEN，#49 M2、#39–42 M1已CLOSED；不写评论、不改状态。详见evidence/GITHUB_ISSUES.json与GITHUB_PRS.json。

本地原目录位于codex/readme-project-overview@e06b66580d49866888c3ef11ccc8afb2df9a236b，不是业务开发基线。M3工作树@952e6246；Harness本地@b9ceaf3b7cf510a4eaae47f64eb982b5a172ea4b，**领先/不同于远端H684，未作为本报告源码基线**。开头三个工作树均clean；不读取Harness未发布源码、不改checkout、不创建branch/worktree。初末状态对照存evidence。

## 2. M3已有能力与可复用边界

独立源码盘点46个method+path，其中39个/api/v1、7个legacy/health；不是默认部署全部开启。已有完整路径、装配条件、DTO/参数/权限入口见reviews/M3_API_INVENTORY.json，易读清单和源码行号见reviews/M3_BACKEND_AUDIT.md。

- 入口api.py:create_app有默认关闭/显式装配；原Web middleware只匹配/api/v1，新/api/v4不自动受保护。无默认公开/docs、/openapi.json。legacy resolver默认拒绝，不是无鉴权旁路。
- 已有WebActor/SessionStore、当前principal/identity/credential/auth_version、shop grant/permission lock、Origin/CSRF和PG token_hash；默认absolute8h/idle30m不等于V4绝对30m。admin不默认有业务权限。
- 日报确定性金额/退款日期口径、冻结报告/证据、持久调度去重与Fake delivery；受限只读询单(3 model/4 tools/60s等)；synthetic知识pgvector引用及指定审核内部copy草稿。询单固定一个内部shop UUID与Mock baseline，不是两店任意动态Agent。
- 0019–0023合计新增19张业务表，head revision准确为0023_p6_copy_drafts。复合FK、当前权限锁、不可变/禁止TRUNCATE与窄ACL已在源码；没有通用DemoTenant/epoch或RLS。原runtime也并非全库read-only角色，不能仅凭“低权”宣称租户安全。
- 旧Graph prepare→wait→revalidate→execute→finish、nonce/hash/PG审批和checkpoint保留。Worker固定数据库advisory lock，默认队列不因启动organization参数而隔离消费。V4-0不为每tenant起Worker，不新增Graph任务，不改锁。
- M3没有公开一键联合双店seedCLI；日报/询单脚本各要求不同新库，copy exporter是受限追加且先DB COMMIT后逐文件fsync，不能把旧脚本直接串联当新底座。

M3执行文件自受测532eefd至当前952e6246无新增业务变更（差异7文档）；这可证明源码关系，不能将历史执行source改为952或V4。

## 3. 历史验收与当前NOT_RUN

| 证据 | 精确受测source | 受测/未验边界 |
|---|---|---|
| scripts.check 3684offline、719integration排除 | 532eefd83e4b1d0e6ddc6e44e89c0d806021eb1e | tracked M3_LOCAL_ACCEPTANCE回执转述，本轮未跑 |
| PG existing542+phase3177=719实际通过、交集0、G1三/G2六/配对清理 | 同532eefd | 本地ARM串行来源；旧失败与两个139 UNKNOWN保留，不代表新source/Hosted |
| M3实际本地API/单Worker/Web3、原Web145/原live24/N01六 | 3a184e9a74c1db524d58228ed90b7ea20388a722 | 合成资料/offline_stub/Fake/合成向量，非真实模型/飞书 |
| 本轮A | 无受测业务source | TEST/COLLECT/PG/Web/Hosted/模型/embedding/平台/部署全部NOT_RUN |

历史原始私有.audit日志未打开；证据来自tracked验收回执及其安全索引，不宣称重算原件。保留先前K2 owner SQLSTATE0A000、部分节点NOT_RUN、deadline137、两次native139、Next/browser个体exit NOT_CAPTURED等，不补造原trace。当前CI可执行PG时限quality45/43、phase350/48，与旧验收文案Hosted35/33分列；未改变/重测容量。真实资料/模型/embedding、飞书实际外发、人工质量、Hosted/amd64、main和发布未由M3本批核收。M2备份工具仅0018，M3备份扩展未实现。

## 4. Harness兼容性及8个共享修改文件

两分支相对共同祖先修改224(M3)/69(Harness)条路径，共享修改8条；这不是试合并后的文本冲突数量。完整blob/hash/diff hunk/工具链依赖见reviews/SHARED_FILES.json。

| 共享路径 | 主要兼容风险 |
|---|---|---|
| .github/workflows/quality.yml | M3 pgvector preparation/binding in PG, Web and N01 vs Harness six shards/aggregators/cache/final merge-gate; semantic integration required. |
| AGENTS.md | M3 current local acceptance vs Harness historical snapshot/archive; preserve dated authority, do not adopt stale M3-unapproved state. |
| scripts/gitleaks_rules.json | M3 45 exact exceptions/20 historical findings vs Harness 17/10; keep generator/TOML/validator/provenance coherent. |
| scripts/pg_ci_evidence.py | M3 LOCK_FILES image inputs plus Harness v2 plan/native/aggregate schema; base PG descriptor is not M3 image binding. |
| scripts/pg_diagnostic.py | M3 module family/owned subnet/image lifecycle plus Harness shard selection/native image/native exit evidence and timer switch. |
| scripts/scan_secrets.py | M3 exact line/span guards and historical records vs Harness include_history/current-only API used by Fast. |
| tests/diagnostic_plugin.py | M3 sanitized diagnostic allowlists plus Harness 45s Python Timer with cancel/join; must remain paired with timeout0. |
| tests/test_quality_gates.py | Both branches alter exact history assertions; no blanket skip/allowlist or deletion. |

最小取舍：**V4从实时重核的M3派生，Harness独立，不整体merge、不先偷改CI。** Harness590旧权重不包含M3新增族，动态发现不证明719已按自然模块/300s/总deadline运行。六job基础postgres描述不能替代M3 PG17.11/pgvector0.8.7镜像receipt/源/输入/actual imageID绑定，跨runner镜像一致性未验。M3扫描45精确例外/20历史，H17/10，必须成套整合且不得删规则。H native诊断候选不修复本项目历史139事实。以后采纳Harness先另冻兼容合同并完整实际验证，远端CI仍须专项授权。

G2未来计划明确六场景：cross_process_resume、receipt_commit_checkpoint_gap、graph_lock_loss_cancel、graph_noncooperative_exit、checkpoint_db_failure_recovered、retired_probe_version_refused。M3当前validator是五项subset，不误说它已强制exact-six；不削弱历史实际六场景及G1三节点。

## 5. 原型、14模块/66页/99功能复用矩阵

资料包27项清单hash全部匹配(另manifest自身计28文件)；PRODUCT_SCOPE唯一ID核14/66/99与六flow，TASK_CARDS共35卡。原型ZIP38entry。HTML的demo1234、roleSelect、localStorage业务数组、确定性Trace+计时器均只供视觉交互参考，83/83是原包声明的浏览器原型记录，本轮未重跑，更不是PG/真实模型/权限证据。

99项逐条分拣：52项可扩展相关基础，47项需新建同域能力；没有将任一整项标已完整完成。分类是静态相关原语/缺口，不是完成率或全仓不存在的证明。逐项ID/源码/差距见reviews/FEATURE_REUSE_MATRIX.json；66页均PROPOSED，见reviews/PAGE_ROUTE_MATRIX.json。

| 模块 | 页/功能 | 相关可复用原语（并非整模块完成） |
|---|---|---|
| 01 经营驾驶舱 | 3/6 | M3日报、任务读取 |
| 02 AI智能工作台 | 6/9 | M3只读询单、Graph、模型预算、事实绑定 |
| 03 经营分析中心 | 6/8 | M3日报指标及订单事实 |
| 04 商品中心 | 5/7 | M2 Woo只读商品、SKU、库存来源 |
| 05 订单中心 | 4/6 | M2 Woo只读订单/退款 |
| 06 库存中心 | 6/8 | M1库存风险和补货审批 |
| 07 采购供应商 | 5/7 | M1内部补货项、审批/回执 |
| 08 客户与售后 | 4/6 | M2订单与退款数据 |
| 09 智能客服 | 4/6 | M3知识检索、原会话权限 |
| 10 营销中心 | 5/8 | M3知识文案草稿及审核 |
| 11 自动化中心 | 4/7 | M3持久调度、去重与Fake投递 |
| 12 知识中心 | 4/6 | M3 PG+pgvector知识、引用和审批 |
| 13 审批与任务 | 4/7 | M1真实审批、PG幂等及审计 |
| 14 数据与系统管理 | 6/8 | M3会话权限、M2来源绑定 |

商品订单管理、采购报价/分批收货、CRM/客服、活动、通用自动化、上传/导入、多轮会话/记忆/Skills等仍需按阶段新增；现有read facade、internal copy或调度不是完整新产品能力。六flow各缺口详见reviews/PRODUCT_GAP_AUDIT.md。

## 6. 四合同、首五卡与候选冻结

四核心候选：DOMAIN_SOURCE_CONTRACT.md、PERMISSION_DEMO_CONTRACT.md、UI_ROUTES_CONTRACT.md、API_EVENTS_CONTRACT.md；附件v4-public-openapi.json（8个proposed端点）、v4-permission-matrix.csv、v4-demo-seed-manifest.json；唯一owner和首五卡准确目录/依赖/Gate以TASK_PLAN.md为准。独立报告的路径均为建议，以ROOT最终地图覆盖，不让两owner同时写共享schema/入口。

V40-01本次只读；V40-02本次候选文档。V40-03/04由同一个SCHEMA/API作者串行掌握迁移/会话/seed/reset/API装配；V40-05 WEB和QA拆分不重叠文件。原业务、Worker、锁、workflow、旧迁移默认受保护。A不创建任何未来代码路径。实施前独审桥接、迁移ACL及current context必须过Gate。

本轮产物可冻结为可复核候选，**不是用户签收合同或V4-0开工许可**。独审首轮发现和修订原件保留，最终review及精确hash见候选冻结索引；用户审核后仍须明确B。V4-0预估沿资料包2–4有效工作日，仅计划，不是本轮测得吞吐或承诺；全量31–52工作日仅包内串行等价估算，不承诺日期。所有实际token/付费成本若API不暴露写UNKNOWN，不由模型名估算费用。

## 7. 集中需用户裁决（不反复打断）

1. 是否接受以M3为唯一业务起点、暂不引入Harness，现有完整门禁不降级？建议接受。
2. 是否接受每访客一DemoTenant→新organization/两店、30min绝对TTL不滑动、服务端独立persona；默认并发cap3，第4/5访客用于限流负例而非承诺5活跃容量？建议接受，真实容量后再定。
3. 是否接受V4-0只建最小联合seed/身份/覆盖层、六异常保留fixture关联，首屏为seed欢迎摘要；完整导航/KPI/六业务链按后续阶段交付？建议接受。
4. 是否接受reset推进epoch继续当前空间、旧身份/CSRF失效、保留去重tombstone；创建cookie整体丢失无法恢复bearer时保留原操作状态，用户明确重新开始才能建新空间？建议接受。
5. 是否审核候选四合同并另行发送B授权？仅同意阅读或合同不会自动开工。Hosted/真实模型embedding/飞书/Woo写/生产/main/protection均仍未授权。

上述方案是候选默认取舍。两店时区/币种暂拟Taipei/TWD与Shanghai/CNY，用于跨币种不混算反例，seed数量/digest均未生成；实施前manifest必须固定实际规模、日期锚点和hash，不能把建议大样本量或已填null当已验。

## 8. 本轮动作核账

只读Git对象/工作树状态、gh查询、资料包文本/ZIP目录/JSON、标准库生成外置报告；未运行受测业务代码、测试/pytest collect/扫描器、服务或Docker。仓库零改动；没有新branch/worktree/commit/push/PR/CI/merge/protection、真实飞书/Woo/模型/新权限。所有本轮结果为文档和源码审查，不是可运行Demo交付。最终仓库/参考包状态对照见evidence/FINAL_INTEGRITY.json。

**V4-0代码NOT_STARTED。**

## 最终独审实际回执

Astra最终独审 reviews/CONTRACT_REVIEW_FINAL.md 与Terra reviews/UI_CONTRACT_FREEZE_ACK.md 均对 evidence/CONTRACT_REVIEW_CANDIDATE_HASHES.json 的八个实际hash给出ACCEPT_CANDIDATE。最终候选无未关闭P1/P2，首审HOLD/REVISE及修订记录保留。关闭的是候选规范缺口，不是实际安全代码验收；用户签收/B、桥接SQL/ACL/锁顺序、seed最小规模/retention细化与owned真实验证仍独立。

当前状态：V40-01只读报告已交；V40-02候选合同文档冻结、待用户审核；V40-03/04/05代码均NOT_STARTED。12项文档结构/唯一ID/hash/引用检查通过，性质仅文档检查，不升级为应用测试。源仓库三工作树与参考包初末全同，远端三HEAD复核未变。完整交付文件hash见FROZEN_MANIFEST.json。
