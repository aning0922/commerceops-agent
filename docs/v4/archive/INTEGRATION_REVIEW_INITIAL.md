# main → accepted 全跨度 PR 集成审查

2026-11-04，台北。结论：`PR_CREATION_ALLOWED_WITH_DISCLOSED_FINDINGS / TWO_P2_DEPLOYMENT_FINDINGS / MERGE_NOT_AUTHORIZED`。未发现新的P1；发现两项可静态确定的旧部署路径集成问题，不能给“无阻断可合main”的结论。它们不改写M3/V40/V41已核本地阶段结果。用户仅授权独立归档与PR，不授权merge或继续功能开发。

## 固定对象与审查范围

- main输入：`6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265`。
- accepted输入：`6bf38bf5bc04f48903b695e4d843210ae1c7dbc1`；tree `acb18ea3bb7c0440b8d19c90df647a0e43356eba`。
- 原review WT HEAD仍为 `a52210240cc47a3087c79cacdc5b7d729480f98f`，未checkout、未编辑受测文件、未commit/push。仅在私有.audit提取冻结源码与本报告。
- 完整差异为779文件、912 commits、190655新增/86删除行。按顶层分类：backend84、frontend150、tests159、scripts17、docs362、infrastructure2、workflow1、gitleaks1、AGENTS1、README1、compose.m3.yml1。本轮覆盖完整差异清单与跨阶段接口/权限/部署/CI风险，重点读取相应入口及迁移；不是宣称逐行重审全部19万新增行，也不是重新运行全部验收。
- `main → 952e6246(M3) → 1730194(V40) → 261f399 → 6bf38bf` 各段is-ancestor均0。261后仅docs、AGENTS及交付PNG变化。`git merge-tree --write-tree main accepted`成功，结果精确等于accepted tree；不存在另一个未审合并结果树。
- 本地对象684e645不是accepted祖先，未合入Harness新head。本轮不查询远端；“实时main”和“Harness远端已变”是Root提供的冻结输入，不冒现场远端验证。

## P2-1：M3 schema检查使现有前端Docker构建确定缺文件

新增触发点：`frontend/package.json:22` 将 `tooling/sync-m3-read-schema.mjs --check` 加入既有check:read-schema。该新脚本第3–5行无条件读取 `/app/docs/contracts/p6-daily-read-v1.schema.json`。

现有 `infrastructure/Dockerfile.m1-frontend:7-10` 仍只COPY p3/p4/p5三份旧JSON，随后执行check:read-schema；其专属dockerignore第10–14行也只放行这三份JSON。因此按现有受推荐M1 Compose构建m1-web时，即使依赖安装成功，新增schema检查也会ENOENT，尚不能到npm build。这不是运行时开关能规避的问题，且本地仓库中的完整文件检查无法证明Docker build context齐全。

建议最小处理：若要保留当前head的此构建入口，需同时窄增该schema的专属dockerignore放行和Dockerfile COPY，保持检查；若当前只允许归档、不修部署，则明确将此入口限定到已验证历史SHA并披露当前head未适配，不能写成当前可用。未运行Docker或构建复现；结论来自确定的文件依赖与COPY集合。

## P2-2：README当前离线路径仍引导stock PG执行新head迁移

入口：`README.md:141-151` 继续推荐M1 Compose完整闭环。其目标 `docs/M1_OFFLINE_COMPOSE.md:31,81-82` 要求当前checkout、仅compose.yml+compose.m1-offline.yml，并调用database migrate，且仍称当前revision预期0018。`compose.yml:4`是stock postgres17.11；`entrypoints/database.py` 的migrate执行upgrade("head")；本PR新增 `backend/migrations/versions/0020_p6_knowledge_copy.py:11-14` 无条件CREATE EXTENSION vector VERSION0.8.7。stock镜像不含本仓另外构建的vector扩展，该明确路径不能迁到0025。此前README的M3路径有正确override说明，但“方式二”仍明确指向未使用override的另一组命令，不能自动视为已修复。

建议最小处理：将M1指引明确冻结到其真实0018历史SHA，并从当前README标出历史适用范围；或另行适配并验证当前head的完整装配（后者超出本次只归档/PR范围）。不要直接修改历史验收结果或声称旧0018回执覆盖0025，不建议为本PR启动完整部署复验。

## API、迁移、权限及Worker集成结论

静态解析全部25个迁移revision/down_revision形成唯一无环链；新增段0019→0020→0021→0022→0023→0024→0025连续，无分叉、缺失或重复revision。未执行迁移。0020是强扩展依赖；0024/0025不提供可自动回退的破坏性downgrade。旧0018备份/回滚不等于新schema兼容证明，生产升级与备份恢复仍需单独方案。

API新增日报/询单/copy均依赖显式配置及原Web session；copy enabled默认false且需原配置与完整hash；InquiryDeployment限制mock/baseline/offline_stub，model/external sender为Literal false。V4 DemoConfig默认关闭，限定v4_demo_*库，local_http只允许loopback。V41挂在显式demo启用分支，不因主API启动而自行seed、迁移或授权。

M3保留原WorkerSession先start持锁、原InventoryCompositeRunner串行消费和原Worker.run；scheduler/Fake delivery挂同一maintenance，没有新增独立cron/第二Worker/并行Graph。mark_attention仅对已持久化有效日报/追问/询单终态加保护条件，仍保留原termination路径。实际调度/竞争保证沿用既有PG证据，本轮未再跑。

owner迁移与runtime授权仍分开：原grant-runtime仅列出日报/询单窄权限；knowledge/copy通过显式owner CLI。V41迁移对新表及函数撤销PUBLIC和app权限；runtime helper仅SELECT与七个固定函数入口，policy私有verifier不授予app读取，policy激活先核owner/revision/库与PG/vector版本；tenant/session→policy锁序明确。SECURITY DEFINER函数所查声明固定search_path，V41 trigger限定demo绑定，不按organization广泛撤销M3 session。未发现新的默认外发、默认模型启用或全schema写授权。

保留风险：上述是代码集成审查，非新数据库升级实跑、生产权限渗透或全部并发状态穷举；默认关闭功能不消除新增schema升级前提。V41有效业务仅合成本地demo，不可把19合同项说成99原规划全完成。

## CI、证据复用与不触发Hosted的PR方式

accepted只有一个workflow `.github/workflows/quality.yml`。第2–6行实际监听pull_request opened/synchronize/reopened/edited，以及push到main/phase/1-integration；不是“只有pull_request”。没有pull_request_target、workflow_dispatch或其他仓库内workflow。PR HEAD提交原文为 `Complete reviewed V4.1 local delivery without entering the next stage [skip ci]`。

官方规则本轮只读核验：https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs 。push/pull_request可用提交信息跳过，PR取HEAD commit；[skip ci]适用，PR标题/body不能代替HEAD。被跳过的必需检查保持Pending并阻止合并；不等于成功或获得merge授权。规则不覆盖pull_request_target等其他事件，本冻结树无此事件。按本HEAD普通创建PR即可满足本仓workflow层面的不触Hosted条件；若归档分支有后续head提交，必须再次确认那个最终commit含[skip ci]。不改workflow，不手动dispatch，不合main；PR后由Root只读核实际Actions结果，不能预填“未触发”回执。外部GitHub App/规则状态未在本轮读取。

workflow、pg_diagnostic、pg_ci_evidence和scripts.check从M3冻结952e到accepted无变化。partition按完整collection动态计算existing与phase3，M3 family按模块拆分，V4/V41非P3/P4节点归existing；run_combined核完整集合/唯一性，verify_pair核精确来源、两集合交集0和全并集。没有把567/719硬编码成当前全部节点；历史7+7/6+5保护仍单独保留。新集合可静态兼容不意味着Hosted deadline容量或amd64镜像构建已通过；本地PG773不能冒Hosted773。

独立比对4fec4a7（Full4601）和e7aeeca（PG596+177=773）到accepted：backend、迁移、scripts、workflow、依赖锁和PG测试无差异。完整非文档差异为15个前端文件及3个浏览器验收文件（browser_shell.py/native_zoom.cjs/test_browser_shell.py）。因此可继续引用原来源的Full/PG及已审影响分析，但不能写最终6bf精确Full/PG新跑。前端变化与browser consumer由后续受影响235Python/74Node/Native40、Mock33及261/r10原件覆盖；261→accepted docs-only，因此保留此前本地阶段核收。当前report不重复审签全部原件、不把这些不同来源计数相加。历史失败、UNKNOWN、Native exit未暴露、API130、human NOT_RUN均不改。

## 本轮检查、异常与后续最小步骤

已执行：冻结对象清单/祖先、merge-tree、完整diff --check均0；25迁移AST链解析0；代码来源差分及部署COPY/配置静态核对。首次试读不存在的ci.yml及archive错误的LOCAL_DEMO_REPRODUCTION路径分别失败，随后改读实际quality.yml和docs/v4/v4-1/proposals路径；没有以失败提取物支撑结论。未运行pytest/collect/Full/PG/服务/浏览器/CI，也未访问private auth。

建议Root先在PR描述披露两项P2和历史M1装配适用范围；PR可创建供审，但不标ready-to-merge或部署可用。若后续获准最小修正，先做Docker COPY/ignore/schema文件闭包静态检查和文档链接/范围检查即可；新功能、PG、冷构建及Hosted不因本报告自动获得授权。最终PR head若变化，再核docs-only差异、祖先和skip marker。只读确认远端main未漂移、实际PR base/head及Actions未启动属于Root的PR回执步骤；无需为单纯docs归档重跑已核Full/runtime。

## Root归档候选补充

随后只读核b6d2b37的AGENTS授权、V41_BASELINE.json及V41_MAIN_INTEGRATION.md；相对6bf恰好这三份文档，无功能变化。其main/M3/V40/261/accepted来源、累计779/912、受测分账、Hosted/merge授权与保护Pending口径符合本轮静态结论。Root报告该候选已push/无Actions及main四项保护属于Root远端回执，本轮未重复联网核验。c35924a仅四份导航文档，未合入本review WT。

本轮从源码另核 `scripts/m2_backup.py:13` 的REVISION仍固定0018_p5_commerce_sources；新增七迁移0019—0025不在该历史备份工具支持范围。b6归档说明已正确披露此限制。其文档尚未具体记录上述前端镜像缺schema和M1 stock-PG命令两项P2；这两项继续保留，不能因一般“生产未验”说明自动关闭。

## 41c34e2 README部署表述增量

只读核 `41c34e2b54f5410172fa609cc3519fe05df3bbaa`。frontend、infrastructure、backend、两份M1 Compose及M1指引相对6bf无变化，因此两项技术事实未变。新README第154–171行正确将当前V41定义为受控复现、显式0025/policy/窗口；第196行正确说明stock PG与M3 override。然而第191行仍把M1 Compose列为完整业务运行指引，目标文档第31、81–82行仍要求当前checkout和stock PG迁head，未明确限定历史SHA，故P2-2尚未关闭。

P2-2可纯文档修正：README第191行及末尾导航将M1 Compose标为“历史0018冻结基线”；目标文档顶部增加当前适用性说明及已经验证的完整历史SHA，说明后文命令仅适用于该冻结源码，当前head含0020扩展依赖且不能照搬。保留后文历史证据，不仅修改revision数字、不暗示加一个override即可获得新部署验收。

P2-1的构建缺文件不能用文档修成技术通过；实际修复需要Dockerfile COPY及专属ignore的两处构建配置修改，属于部署配置修复而非业务功能，但未在本轮擅自实施。若本次坚持纯文档归档，可明确记录当前M1镜像构建KNOWN_BROKEN、保留问题及历史替代基线，提交Draft PR供审；不能将其标为FIXED，也不据此建议合并。待Root提供冻结文档增量后，仅复审上述声明是否准确，不启动构建或扩大验收。
