# M3 托管开发与交付记录

## 当前事实

- 授权日期：2026-11-03（台北）。主控会话：01a19f1b-f4c0-75c1-a9f0-8f8b88db72d5。
- 远端 main 只读核对：6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265；Issue49 closed/completed。
- 状态：IN_PROGRESS / LOCAL_IMPLEMENTATION；S1实现待显示校验修复复审，其余功能、完整CI和部署未验收。
- 当前目录 README 分支 e06b665 保持原样；本阶段使用独立 control/backend/web 工作树。

## 交付顺序

1. 日报确定性指标与异常规则，冻结数据口径、快照来源及验收金标。
2. 复用单 Worker / PG jobs / outbox 的持久调度、去重、补最近一期及受控推送。
3. 报告绑定的证据追问与最小可用 UI。
4. 白名单动态只读工具及实际工具序列/权限/预算评测。
5. 版本化 SOP 检索、可定位引用、人工审核及幂等保存内部草稿。
6. 必要本地/PG/Web/真实模型或平台证据、独立审查、精确 CI 与主控核收。

原范围依据：PRD、AGENT_DESIGN、ROADMAP、30_DAY_EXECUTION；日期与工时均须按新实际记录，不能把历史计划余额当可用额度。缺少许可资料、模型预算、接收对象和真人操作时，相关真实 Gate 保持 NOT_RUN，离线候选不代替正式完成。

## 分工

- Root：本文件、阶段授权导航、集成工作树、任务依赖、模型调整、必要发布与最终核收。
- Backend：合同草案、确定性指标、持久化/API/Worker/共享 DTO 及相应测试；不改 frontend。
- Web：仅 frontend 与最小 UI 实施说明；消费冻结且已提交的共享合同，不虚构接口。
- Reviewer：先只读评审合同与范围，再评审精确实现提交；不接管作者源码。

各开发者不得修改 Root 的阶段导航、另一开发者文件或 Harness 资产。共享 schema/迁移、根配置和 CI 只由 Backend 提案并经 Root 协调；锁文件或 workflow 必须有实际必要性。Root 普通合入精确已审提交，不 reset/amend/force，不读他人未提交 WIP 作为交付。

## 模型调度

初始：Backend Sol/high，Web Terra/high，Reviewer Sol/xhigh。常规文档/机械接线可降为 medium；跨层恢复、权限或并发阻断可提高强度，必要时以独立专项使用 Astra。工具实际接受的设置与回执为准，额度不可用不自动转付费 API。

## 外部边界与验收

新开发授权不复活旧真人/SDK/Native/CI一次性窗口，不修改旧 once 或 UNKNOWN。真实外发须绑定已授权对象；当前没有新增 paid API 或业务凭据访问。开发者无 push/PR/Hosted/main 权限，统一由 Root 在具体可审交付就绪后处理。保留现有所有安全、业务、恢复、权限和全量 CI 要求。

## 证据账

本次启动仅核对 GitHub main 与 Issue 状态、创建工作树及本文件；未运行业务测试、模型评测或服务。后续按实际 source SHA、命令、退出码、资源与限制增记，不预写通过或完成。

## 可见会话与动态命名

用户追加要求：会话名必须随当前开发内容动态调整，让侧边栏直接展示正在做什么。统一格式为 CommerceOps M3｜具体任务 · 当前阶段或阻塞原因；职责切换/进入实现/待审/修复/验收/被外部依赖阻塞时更新，避免只写A/B/Worker等内部代号。模型与推理在主控消息中记录，以实际工具接收结果为准。

| 会话 | ID | 初始分配 | 当前阶段 |
| --- | --- | --- | --- |
| 日报与调度 · 合同设计 | 01a19f34-8596-7732-8ac4-09ad74df324d | GPT-6.1 Sol / high | 已派发，合同草案 |
| 日报界面 · 交互梳理 | 01a19f34-ce14-7f83-a9c3-11b3a224389d | GPT-6.1 Sol / high（Terra 容量不足后切换） | 最小交互文档 |
| 独立审查 · 等待合同提交 | 01a19f35-0999-72f1-89ad-cf1de5421b75 | GPT-6.1 Sol / xhigh | 范围核查已交付，合同未验收 |

三会话实际状态均由 wait_threads 首次快照确认 active；创建返回不代替开始证据。旧Harness主控已获边界通知，本阶段不重开旧真实窗口。

### 启动核查结果

- 主控文档检查：当前118份Markdown，errors=0，命令退出0；仅文档检查，不代替业务测试。
- Web 的 Terra 调用返回模型容量已满；原会话切 Sol/high 继续，未改用付费API、未新建替代任务。
- 独审首轮范围意见：首批范围合理，但库存创建日cohort不能替代支付日/退款发生日完整采集；现OrderLine缺订单级运费。新日报合同应明确独立订单事实与完整性，不放宽旧inventory/P4约束。调度须绑定版本/时区/接收对象，最多补最近一期；报告唯一与外发唯一分开验证，UNKNOWN不自动重发。
- 合同与主体实现尚待精确提交独审；本记录不签M3或任何功能完成。

### S1 实施放行

独立Reviewer只读核对 Backend cfd3ef2d38c3c84c8d2c3a0dcd79616f8680c5c7 与 Web 27a11f211f39f767ae2916b8a447d7b6f914f37c，结论 ACCEPT_S1；只放行严格日报DTO、纯聚合/异常/证据hash和独立金标，不代表完整M3合同或实现通过。Root普通合入两份文档，组合Markdown检查120files/errors0/exit0。

Backend 已获S1实施指令，模型调整为Sol/xhigh；当前可见名为“CommerceOps M3｜日报聚合 · S1实现与金标”。Reviewer为“CommerceOps M3｜独立审查 · 等待S1与扫描候选”。Web方案依赖S4冻结接口，当前暂停UI接线，同一可见会话暂转“CommerceOps M3｜历史扫描 · 精确核收同步”，唯一写入新scan工作树，允许范围仅已有扫描器精确历史审批元数据/必要最小机制与针对性契约测试。

旧Harness owner只读回执确认固定b9ceaf3的审批索引含20项，后增17项已分别独审；尚须逐项集合/摘要对齐，不凭数量判定相同。扫描候选不得改变222条规则、dir/index门禁、扫描范围、历史refs或广泛allowlist，后续精确独审及实际全扫描仍待。历史M2规则扫描20命中/3已审/17blocking保留，不回填。

此时S1代码、scanner兼容、PG/Web/模型/实际推送、完整本地/Hosted/main核收均未验收。

### 连续托管与用户补充边界

用户于同日明确纠正主控“需要按照设定目标一直开发到完成”。Root建立持续目标，接回提交/审查/修复/集成/后续派发，不再把启动分工当开发终点。

用户已明确答复：SOP/商品资料暂未准备；真实模型及embedding预算稍后确定；暂不实际发送，先完成可验证实现。本阶段继续全部本地代码与替身/合成资料/新owned资源的验证，真实资料、真实模型/embedding评测与实际推送保持NOT_RUN，不能自动访问旧秘密、套用旧真实窗口或宣称正式全M3验收。

独审接收扫描兼容f1ad601：仅已审20项精确历史元数据，算法/222规则/全历史边界不变；Root已普通合入，完整实际扫描进行中。日报e073独审1项P2阻断：display未验证派生值/完整集合，作者已接回最小修复；旧135pass及失败反例分记。

增加可见知识检索/草稿会话01a19f5b-4424-7413-8933-58980c0c4155（Sol/high），在独立knowledge树先做最小合同；无许可资料时仅自创合成fixture。动态只读会话01a19f34-ce14-7f83-a9c3-11b3a224389d已由扫描任务转为inquiry树，按原D01–D05准备执行器合同。所有共享DDL/ACL仍由Backend统一协调，避免迁移号冲突。

### 首轮扫描与执行器进展

Root在扫描集成提交7db2b69be0bcab8d9a2b85f600858e0b63d702d3实际执行完整scan：dir0/index0/git20全部精确已审/阻断0，aggregate exit0；原生history scanner exit1保留。独立针对性quality gate 30pass/93deselected/8.78s/native0，包括原缺工具的合成扫描反例；不代替完整工程/PG。工具node24.21.0与gitleaks8.30.1均按固定官方归档SHA256 bootstrap到新control树。

动态查询合同cd2caad已独审ACCEPT_IMPLEMENTATION，Root已释放application/commerce/readonly_inquiry_*纯模块与专用测试；查询级累计窗口/实际扫描行/SKU、每次鉴权、第三模型轮停止、迟到/partial与错引拒绝为明确约束。API/Worker/真实provider后续，当前真实预算关闭。知识合同3097d60已转独审，尚未放行K1。

### S1 核收与后续实施

S1修复e47a2e3已独审ACCEPT_S1_FIX，独立149pass及十币种/四HALF_EVEN边界40组低precision+traps验证通过；Root普通合入承载S1并复跑149pass0.18s/exit0。合同显示语义P2已关闭，来源status冲突映射由S2负责。

Root测试修正063bb75已独审ACCEPT：完整可达历史的实际findings必须等于对应精确审批集合；production scanner不改。本机17provenance通过；新非浅单分支隔离clone仅3条审批源可达/17条源不在该历史，18针对性tests通过4.69s/exit0。首次17fail由Root误用返回None的git helper导致，pytest失败但外层末命令曾掩盖为0；已改check_output并使用set-e，该失败保留。

S2设计836bf87获得storage/source/runner实施准入，Web schema6处ge非标准关键字为P2，修正/实际Pydantic生成验证前不开放Web消费。Backend已获新0019迁移、三表持久化/来源/runner/Read DTO/API及必要测试代码实施授权，新ownedPG需冻结候选后Root具体UTC登记；旧0018保护不改。动态执行器f0ceb20已提交/30purepass，正式独审中；K1纯知识模块实施中。

### 接线与迁移独占分配

Root完整本地check绑定aaaa132263a219f49539347e4e6818f11283b258，322.614s/native0；2944offline通过、590integration排除、4既有warning，工程锁/文档/lint/type/Node/Python审计通过（Python95包/已知0，npm0）。之后新实现须另验证，不用此结果代签。K1 59c40c2独审ACCEPT，Root已合并66pass0.22s；ReadDTO1434909独审ACCEPT_WEB_SCHEMA，Root已合并182pass0.25s，Ajv复核进行中。

新增专职Web会话01a19f70-5c01-7bd3-9d92-4f0ba28babe9（Sol6/high），已转1434909实际DTO/schema并放行首片日报详情/strict client/契约测试，接口无列表或创建能力时不伪造。动态会话继续独占inquiry模块，f0旧结果HOLD，消费片负责逐claim可读答复、双窗口事实/代码歧义澄清及真正MockCommerce分页。

为减少串行等待，Root明确更新共享DDL协调：唯一线性链0018→0019日报（Backend独占）→0020知识/copy（知识owner独占）→后续0021起（Root另分）。各owner只写自己的新迁移/专属模块，0020必须固定down_revision0019并普通合入已冻结父提交后才能真实升级验证；不并行创造head。根Compose/共享database入口/权限helper仍由Backend+Root单点协调。此为Root授权的独占范围更新，旧一人写全部DDL规则在本次分配范围内被替代。

固定知识构建8ee1df0已独审放行；Root实际镜像build74.12s/native0，唯一tag commerceops-m3-vector:8ee1df0-arm64，image sha256:4ebf3de8870438618836dd1765632b7e90cb950632c929162441367087439d5a。只读无网络utility容器核PG17.11/control0.8.7/ldd无缺失后已退出，无PG服务启动；扩展CREATE/SQL/低权/向量float32与保存事务仍NOT_RUN。构建GO03:27:10Z→03:47:10Z，结果早于截止；未使用旧卷或秘密。知识owner已获K2专属0020/repository代码实施授权，PG仍待冻结后统一具体窗口。

### 功能修复与界面验证继续

动态3cab独审三组P2已接回：跨SKU/未知SKU范围、订单有效状态口径、未分配共享池SKU可用量；作者独立fix22b60150add80f59613445260e1e2851b5d0b86f/79targetpass已交复审，未提前签工具完成。服务设计832c7d1独审ACCEPT_SERVICE_IMPLEMENTATION，Root已分配0021（父0020）及专属store/runner/router实施，主API/Worker注册仍Backend单点。后续0022给日报调度/投递/追问，0023给知识审核草稿。

K2 8a6c6eb（84offline、28PG仅collect）独审1P2：同registry同逻辑chunk多版本造成top5同距不稳定，Root要求与K1一致的逻辑identity单版本约束/应用+DB校验；作者保留K3WIP另独立fix，不用重排序掩盖引用身份。0019父仍待冻结，全部PG尚未启动。

UI原a9bef16已独审ACCEPT_UI_FIX，旧401403清新会话问题已关闭；10UI_FIXTURE通过/服务停止/18649关闭，受测界面a64188f到a9仅文档不同。迟到403DOM例等待响应处理有非阻断加强项。随后按Root实际390截图复核改为首屏核心摘要、完整细节折叠，界面ddeb42d/最终7dfe8bd重新build+10UI_FIXTURE通过；新布局尚待静态审，不转签旧布局。真实API/PG、实际browser page zoom与Hosted未由这些结果证明。Root另登记独立小批验证真实浏览器page zoom200%（允许仅新profile内极小runtime extension/tabsAPI，禁止用户Chrome/系统键盘），不续旧已结束服务。

### 模型偏好与真实 SQL 首轮事实（2026-11-03）

用户要求优先使用 GPT-6.1 Sol、GPT-6 Astra、GPT-6.1 Terra。当前主要实现使用 Sol/high 或 xhigh，UI 使用 Terra/high，关键事务与权限独审使用 Astra/high；会话名继续跟随实际阶段调整。工具可切换时由 Root 设置，不把作者无法自行换模型当作已切换证据。

动态工具修复22b6015已独审接受并普通合入，Root79targetpass；UI布局7dfe8bd与真实浏览器缩放证据71d18ff已独审接受并合入。缩放以独立 Chromium profile 的 tabs.setZoom(2) 实现，三宽度读回zoom2与DPR变化，属于明确UI_FIXTURE，不冒充真实API。旧90契约检查通过，但其默认输出曾改写旧tracked evidence；Root已保存本轮报告到独立.audit并恢复旧artifact原字节，不覆盖历史证据。

S2精确候选37e7e99经过独审217purepass/no新增P1P2，结论仅ACCEPT_S2_PG_DIAGNOSTIC。Root独立validation树359933f0012adf9202c52f184c6ba46d08ab853f普通合入该候选与此前已审代码，启动全新owned PG；不访问原库、旧卷、旧Secret或实际模型/飞书。原有诊断器派生副本只修改资源namespace、绝对清理reserve180、单模块command300与down不删卷，全部精确差异/hash登记在.audit。总绝对截止04:38:03Z，不自动延长。

首轮m3s2-dc4f56944928 build/healthy退出0，04:23:34Z migrate退出1，16测试未开始；原诊断器不保留原始stderr，具体根因当时UNKNOWN。04:23:35Z cleanup0、CLI/reader结束，独立查询容器网络0，新卷保留。为取得安全诊断，另开全新owned round2，不读取首轮卷；04:25:01Z同源码返回ProgrammingError/SQLSTATE42601/primary“syntax error at end of input”，16测试仍未开始，04:25:02Z cleanup0、容器网络独立查询0、新卷保留。只采集异常类别/SQLSTATE/primary，不输出DSN、参数或完整SQL。Root怀疑p6_binding_guard的IF中未括起CASE，但须后续实际SQL证实，不把假设写为已证实根因。已交Backend独立最小修复，S2尚未核收。

K2修复e1a52d6已静态接受，但尚未SQL核收；其真实revision为0020_p6_knowledge_copy，parent占位0019须改为0019_p6_daily_reports。询单服务1a78d5a候选实际revision为0021，parent占位0020亦须绑定上述真实K2标识；独审与PG测试代码继续。后续0022/0023父链只按实际冻结值接线，不凭分配号宣称Alembic已通过。询单终态JSON NULL与原session/fixture先于完成回执重放的风险正在独审，未核收。

### 日报 S2 组件核收与 K2 首轮实际验证

日报最小修复66ee8d7（IF内CASE括号）和89d1d86（严格响应模型JSON校验后返回模型）分别独审接受。Root纯CPU真实ASGI先复现response_model对wire dict的UUID/datetime/tuple拒绝，未放松DTO；作者与独审39Read/TestClient通过。后续旧截止内整模块复测运行余量估计不足，82ff候选到04:35:03Z停止时只有10callpass，exit137/cleanup0，失败事实保留，不能拼为16通过。

Root另建K2专用validation树849ba3bdf3329736be965c93374545cb02f136bb：S2两fix、K2e1a52d6及独立cherry-pick51065b1一行真实parent（不带缺0022的K3祖先），46collect通过。新窗口04:36:02Z→04:51:02Z/180清理余量，显式Compose override仍仅原postgres服务，按已构建镜像完整ImageID固定，无模型/embedding/飞书或旧资产。首轮0019→0020迁移/初始化均0，K2实际29pass/1fail50.05s，唯一role反例；因该模块非0，后续日报16未跑。04:37:46Z cleanup0/stopping确认，owned m3k2-195fff8f757c保卷。

为定位新增P6错误，Root f195701仅将四个指定P6模块与固定safe文件名帧加入原opt-in结构诊断，原异常消息/SQL/locals不输出、分类/SQLSTATE/16帧上限不变；独审ACCEPT_P6_DIAGNOSTICS。随机marker排除探针首因模拟metadata缺funcargs失败，补齐后通过；不改业务断言。第二轮源fe6e7b89091e9b8a9f1e4e94158af68fb4e8372f在fresh owned m3k2-406293707a73先跑日报：实际16passed/30.18s/native0；再跑K2单role反例，CheckViolation23514定位test_p6_knowledge_copy_pg.py:184的角色UPDATE，尚未执行到检索断言。整个batch仍exit1，04:39:49Z cleanup0/stopping确认，独立容器网络0/新卷保留。知识owner确认缺原auth_version增量约束，将独立修夹具并新身份验证，不放宽原约束。S2可按组件已审源码+实际16核收，K2与整体M3仍未核收。Root已普通合89和095前端失败码同步；095祖先247联调入口亦伴随合入，该入口仍HOLD且从未运行，需402精确修复独审后才可真实联调，不把当前全树称为已审。

Root359广离线实际3126pass/5fail/606deselected/261.58s/native1。四项失败确认缺frontend锁定依赖，补齐固定Node/npm（初次PATH错误、复制后npm脚本入口相对路径错误均保留，后使用canonical npm-cli路径offline ci0）后相同四项4pass/2.81s；剩余全历史原20对native42的22个新增命中，由新可见扫描会话提出bcf9604候选：9组源commit/path/整行/hash公开字段，190定向及122旧质量门禁通过，完整主库扫描待独审后Root统一执行。该会话随后转新local-runtime独立树，只拟同PG的固定扩展镜像和本地/CI验证入口提案。

询单18a修复前两P2后复审新增CASE括号与失败usage归零两P2，已交作者；K3 cf86有跨candidate同审核人同key并发冲突返回503的P2，已交修复；询单UI d9因未接受新无facts失败结果亦已接回。以上离线通过不代签真实SQL或完整功能。

### 本地组件核收、应用接线与完整门禁准备（2026-11-03）

后续模型按用户偏好使用Sol实现、Terra界面、Astra关键审查；所有开发仍在侧边可见会话，各标题随当前任务改名。外部资料未准备、真实模型/embedding预算后定、实际飞书发送关闭是用户确认的边界，继续完成本地实现，不把这些外部NOT_RUN写成通过。

K2角色夹具98cc修正保留原auth_version规则与真实新session；精确源b828c6f0993550e899760c9a836f6ee848538ae6、新owned m3k2-5a1f7eb25909实际30passed/47.75s、native/outer0、cleanup0，独立容器网络0/保留新卷1。询单SQL的局部变量r与SQL别名r冲突由eed9165改名并补真实正向库存/销量反例，da2补撤权夹具auth_version；未用Fake签实际SQL。Root主应用询单接线1d5d1bb已独审接受，Core8748e326f73a293674f26ed9445e362ca7ac2a81实际38询单callpass、16日报callpass，但该整批95节点结果仍55pass/11fail/29setup错误，outer1，不能记为整批通过。

K3原29setup错误源于缺原fixture导入；769e307独立修正。其后999ce7d实际28pass/1fail，唯一expiry用例在10.1秒pg_sleep触发原5秒statement_timeout，尚未抵达COMMIT。e371a2d保持真实10秒TTL与5秒语句上限，分五个2.1秒等待并断言数据库已过期与抵达COMMIT。精确源8933f85ba2c121dd25892947d1dd19a02305ade6、新owned m3core-4154f023a3bf实际29passed/61.99s、native/outer0，05:33:00.005130Z cleanup0，独立容器网络0/新卷1保留。本批仍使用旧固定镜像4eb，后续标准镜像SQL不从该结果继承。

S3两权限/不可变P2由7848ca8修正并独审：目的地通过原窄definer锁定，runtime不扩大UPDATE或直接helper执行权限；daily_question旧/新kind均入约束。首次实际12节点仍1pass/11fail，涉及真实OS WorkerSession未退出、Web conversation夹具和严格日期wire。fafb0fa改为实际子进程退出与原事务创建conversation，并只在日报投影将date转ISO，不放宽canonical/DTO。9023742补日报创建及追问POST的原键GET回执，独审接受。

固定扩展入口0e94d3f独审接受并普通合入；compose.m3只覆盖原postgres镜像，stock Compose与M2 backup保持原字节。首次标准镜像prepare在3a4f90c成功，image94630f25cd59b9b2bfc1fbfe5d630b71f38122e9d52701c27b29c6ecca639a03，arm64；仅native构建，AMD64/Hosted尚未运行。后续新source重新生成独占receipt，不重用旧source绑定。

Root精确标准validation源eff02e3b4c2ba023d09ddde9b4b131720a98fcf6，原scripts.pg_diagnostic显式--m3-pgvector、新owned p123-15c61adc3b9e：升级唯一0023/初始化均0、原legacy79collect；S3 operations12passed/26.25s、receipts2passed/7.13s、native/outer0。05:43:40.895263Z cleanup0/stoppingtrue，独立容器网络卷均0。原标准helper按fresh ephemeral合同删除本轮新卷；此前private diagnostic保卷结果仍单列，所有旧卷均不碰。

主API文案接线1e30c9994c2d9f034ce516d0d5453f4dac165150独审ACCEPT_COPY_APP_WIRING，独立30offline/四种开关边界通过。默认关闭不读文件；显式enabled与配置raw pin/逐项语义pin接入原Web/session与五路由，独立OpenAPI与旧合同隔离；新增显式owner CLI，不由通用grant-runtime隐式开启文案写权限。Root首次文档检查误用不存在的scripts.docs_check且shell末commit掩盖退出，保留失败；正确scripts.check_docs后132files/errors0。

Root单项组合测试4c6d601独审发现创建202被误期望200，HOLD；f20dadf改202、合法Origin缺CSRF精确拒绝，并改只预授K2的fixture。精确validation源42af9ab3f4a13aa018a89ff8f120c767b9ed2183、新owned p123-08ae09175e1f、该次实际绑定image504a1480df943d2cf87f80947db069186bf5bd4e411360513f22683f60340231实际1passed/4.04s：K3 INSERT=false→真实owner CLI→true，主API真实session/CSRF/创建→GET原key→approve→receipt，1candidate/1decision/1draft/outbox0。05:50:08.014475Z cleanup0、native/outer0，独立资源0；只签该组合用例。

UI询单128e43d、S3只读dbdc16c、日报写cfd620c和文案审核cc7e646均独审接受并普通合入。询单区分内部shop UUID与commerce external key；已失败任务允许保留已知本次attempt usage但无facts/claims/refs/options。写UI先保存原请求、UNKNOWN只GET原键；真实身份/来源/assigned reviewer在服务端重核。sessionStorage仅当前tab恢复，copy前端不能独立重算浮点候选hash/向量排名，说明保留。新界面实际浏览器/真实API组合仍待，旧UI_FIXTURE/zoom不代签。

当前head测试85ba0b4已独审接受：精确75business+4CP=79，0020–0023新增16张表逐项列举，历史0012→13/0016→17原行与checkpoint字节相等、M2固定0018/60表保护保留；68PG仅collect，完整旧回归仍待。门禁覆盖审计发现M3节点自动进入existing但共用300秒大批，copy strict Ajv与无server M3契约未接统一入口；Root已释放最小拆批/显式检查，不削减旧节点、五jobs、清理与绝对截止。

Root在已合UI的ac6edf树实际完整敏感扫描native1：dir/index各15blocking、history156总/原20精确已审/136blocking。后续owner逐行归并公开请求键/DDL/类型/指标和生成摘要；新增豁免必须固定source/path/完整行hash与严格whole-line，不新增宽泛路径或忽略历史。本轮失败保留，候选独审及实际重扫尚待，不预写pass。

合成copy exporter a9e3dc1已独审准备通过；逐文件独占/fsync输出，不是三文件整体原子发布，COMMIT后导出失败可留下登记和部分文件，须保留核实且不自动重试。实际登记/导出、同源完整工程/PG/Web门禁、最终集成核收仍未完成。托管目标继续，未push/main/Hosted、未调用真实服务；本记录不是M3完成或发布声明。

### 标准镜像 ID 校正与完整工程结果

Root此前把首个control构建的946镜像ID沿用到后续标准构建，这是由固定tag推测固定imageID的错误。直接读回原round报告的m3_pgvector字段后校正：eff02/p123-15c61adc3b9e实际为sha256:8ba6c6f1c56536139b17f955ba6e123e8d8eff76749da33fbf1aaab4db5da3b3；42af/p123-08ae09175e1f实际为sha256:504a1480df943d2cf87f80947db069186bf5bd4e411360513f22683f60340231。946只签3a4首次prepare。SQL/source/native/cleanup结果未改变，错误口述不作为镜像证据。不同build重新绑定tag得到不同imageID，不据此推断编译可重现性。

52525ba356f78ec2447d7bbe036f96ea90140088完整scripts.check实际native0：3643offline通过/718integration排除/4既有warning，542.63秒；495文件type、Ruff/format、139文档、锁、固定Node24、copy Ajv24样例5操作、6文件33无server零skip/retry、Python95包已知漏洞0/npm0通过。扫描dir/index0，history原20精确已审/阻断0，原生history exit1保留；新18公开整行豁免32576e9已独审34target通过，旧222规则语义、26例外与20历史审批不变。以上仅签该次精确工程结果，不签正在增加的联调发现阶段测试、完整PG/Web或任何真实业务。

完整PG按718节点划为existing541/phase3177，同源分区与完整并集仍待实际结束和配对；最初existing因并行重打共用tag在命令前拒绝0tests，之后因默认网络地址池用尽启动拒绝0tests，均cleanup0且不改业务断言。Root保留其他既有网络，后续按可用资源串行，不清理历史环境。相同52525/source_tree/六项INPUTS/本机架构与当前实际image19ac的真实构建回执，可在独立校验后供其他同源树使用；只复用构建产物，不转移任何测试通过，原件与SHA/sidecar另存。

真实browser准备批保留全部失败：Root私有parent漏传timeout导致资源登记前失败；大样本来源与旧config_ref唯一约束冲突，后改为新owner配置引用/新版本并保留原绑定；就绪探测误用/health而实际路由为/health/live；共用tag变化和默认地址池耗尽均先拒绝且业务POST0。新独立显式172.16.240.0/24子网经重叠检查，仅用于本轮自有网络，未改daemon/旧环境。52525/m3web-1ccaa5d5712d实际seed、来源登记导出、API/唯一Worker/Next已ready，Playwright发现期与worker顶层重复loadOwned，独占账本EEXIST，业务POST0、cleanup0。UI仅修测试生命周期，不放松O_EXCL；真实七POST闭环仍待新窗口。
