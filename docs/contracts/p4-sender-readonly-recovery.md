# P4 原来源与后续 sender 分离的 v1 只读对账合同

2026-10-14（Asia/Shanghai）。原 A/WTfd38/PR43 的合同修复候选，基线3f9b3aeb。单original Gateway同时约束旧receipt与后续005 SDK，是原Core确认的准入P1。真实RO、最新源码PG、精确独审和新CI尚待，不宣称M1或Phase4通过。

## 可信来源与 sender

`ApprovedOutboxRecovery` 保留原入站Gateway id/hash/终止、receipt/source/actor与原task/plan/approval/execution/hash，新增可选 `sender_gateway={gateway_id,gateway_hash,termination_id}`。省略该字段时保留旧sameGateway与v1/v2恢复；新路径只接受唯一原v1 projection，origin/sender/new Gateway互不相同。

三段claim均来自同org/shop的实际不可变audit，核hash、原Mock参数、完整started/process/reaped/int-exit终止。origin终止先于sender claim；sender Gateway started、旧Worker started、持久授权、SDK创建、C调用按实际时间相连；sender Gateway/Worker终止均先于新reconcile claim。旧child OS须不存在。Worker确认按owner/明确事件ID、同host/namespace和显式原因验证；其PID可属于执行确认的parent，不能错误按child PID遗漏。

`approved_workflow_claimed.id`须等于实际sender SDK window ID，其中完整窗口必须是enabled的approved_first_create，绑定sender Gateway、SDK caps/expiry、唯一原task/projection、origin claim/hash/终止、receipt/approval/decision/execution。当前task binding与不可变approval/decision hash重核。不能用任意Gateway、caller声明或仅C回执补链。

sender SDK须真实controlled/enabled、同org/shop、完整hash相等；创建/expiry在sender Gateway有效跨度，实际创建和C调用须早于sender Gateway停止。sender auth须唯一returned200/code0并在旧Worker生命周期内。C历史须全局唯一returned200/code0，同outbox/task/scope/window，处于SDK及Worker跨度。源SDK cap不得超原first-create ceiling，C上限仍1。

## RO 准入与落库

当前原operator/approver身份、App/Tenant/白名单、角色/auth版本/shop scope继续原可信检查。task completed、plan executed、approval approved且consumed、execution completed、item open/v1，完整原payload/15字段projection/request hash/client_token不变。首次RO需unknown/attempts2、原sender owner、无external ID、C1/anchor0。

当前caps仅auth1、bot1、table-list≤2、field-list≤2、record-list≤4，总≤10，C/U/IM方法缺席、provider0。只分派原outbox，Graph/job/IM不执行。完整分页、唯一原key、15字段及SyncVersion1相等后，原Base adapter仅reconcile，PG协调器写anchor/verified与ledger/audit；task/plan/approval/execution/item/CP不变。这是远端API只读，包含正常PG对账落库。不存在/多行/不同record/不完整/unknown/429/5xx/权限失败即停，不create/update、不换key。消耗attempt3，失败后不追加窗口。

private bridge保留C0原mode/profile/caps/C0/anchor0，增加显式readonly_reconcile的DTO/profile/只读cap/C1闭合分支。复用R13 pinned observer、canonical Worker/Factory/单child/Graph与late Secret；只刷新必要源pin metadata，原R13实现不改。RO terminal须完整唯一PG验证、parent/child reap、owner生命周期、Gateway停止、disabled恢复及owned down保卷；程序切片result/exit不代签M1。

## 实际证据与验证边界

原005六方法各一次HTTP200/code0、原key Create1/upper ACK-drop1；PG unknown attempts2/BASE_WRITE_UNKNOWN、C returned1/anchor0，是受控故障而非完整读回。真实parent确认已按owner核实；旧child PID收口查询遗漏、旧verification_failed、binding准备时间HOLD、提取字段错误、closed-window/once原字节保留。

首轮新owned合成PG前12节点通过、末个C-history夹具回退attempts被既有保护拒绝。既有diagnostic helper清理实际删除本轮合成首卷，先前保卷说法已更正。第二轮同project/同09:02:09Z截止重建合成资源，14必要节点通过，08:53:58Z停止PostgreSQL；18已退出one-off核完整ID/project/stopped后普通rm，08:57:45Z容器0/网络0，重建卷保留。不能称首卷保留或同卷续测。

最后auth/decision/历史cap/时间补强、SDK-span负例与13拒绝子例合并后的最终两个节点未跑最新PG。旧12/14仅签当时字节；当前源码与运行时hash证据缺口按最终freeze分列，原Core与新精确CI须补齐。当前真实准入HOLD，无PG第三段。本批SDK/AppSecret/provider0，原known70/P1/P2/P3资产0访问。

D1/D30、300h、P4 50h估计、18页冻结、人工H/L not_reported不重置。B/C/前端/CI/锁/迁移/Gateway/审批状态机/Worker Graph/生产/Woo/P5不扩写。Root源码窗口08:22:06Z→09:52:06Z，不续期；本批不push/main/关Issue。最终纯检查、候选SHA与未测项以冻结回执为准。

作者当前完整offline1806通过/480 integration排除/4 warnings/103.19s，Ruff/format417/type310/Markdown103通过；与最新PG待核分开。敏感扫描与最终private Fake/源pin/候选SHA以freeze记账，未执行平台RO。

## 2026-10-14 后续 wire 与显式单次 RO 候选：HOLD

本节为后续 Root 派单 UTC11:04:04→12:34:04 的当前事实；上方08:22批次与失败按当时历史保留。基线45778由Root报告精确Hosted38543318700五项SUCCESS、300+180=480完整PG；旧成功不签本候选。F02已批准“持久澄清请求编号，完整参数并明确确认后才创建正式Task”，本批只排队，未实施。

原007窗口已闭合：auth/bot/table/field/record-list各一次returned200/code0，C/U/IM/provider0；六行中五行空白、一行原key匹配，匹配行12字段=10text+两numeric字符串，三nullable列省略。完整分页、逐值相等与原record内容未捕获，PG仍unknown/automatic attempts3/reconcile/INCOMPLETE_READBACK、C1/anchor0。不能把SDK方法成功签成内容验证成功，不回退attempt/owner/旧时间。

### endpoint 特定读转换

依据Root实际保存的官方[列出记录](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/list.md)数字字符串示例、[新增记录](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/create.md)number写入合同及[记录字段数据结构](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/bitable-v1/app-table-record/bitable-record-data-structure-overview.md)type2/number，只在两列Quantity/SyncVersion的list读回处转换。通用共享DTO仍要求完整15字段和规范int；Create/Update仍写number。

当前候选允许：JSON int；有限、整值的JSON number；字符串文法`[1-9][0-9]{0,15}`。转换后须在1..2^53-1；拒bool、非有限、零/负数、分数、溢出、尾缀、空白、正负号、前导零、数字字符串小数/指数和未知类型。不截断、不round/clamp。浮点形式的边界目前按解码后值核验；原始JSON小数在默认decoder中提前丢失精度的边界未被本批独立验证，仍属HOLD评审项。

仅ResolutionReason/ResolvedBy/ResolvedAt且冻结PG expectation为None时允许omitted并转规范None；required列或expected非空列省略仍INCOMPLETE_READBACK。全分页/total/record-id去重、全局唯一原item key、数量/版本/全部文本的严格相等不放宽。三处旧负例改为缺SKU，保留“缺required绝不写”的原语义。

### automatic attempts3 与 explicit_ro_recheck1 分账

DB CHECK仍0..3，不迁移，不称DB attempt4。`explicit_ro_recheck`可选DTO绑定最近reader Gateway claim/hash/终止、SDK window/hash、原approved_outbox_claimed完整hash、reader owner/终止；原005 C sender lineage继续独立保留。reader必须是先前enabled的单v1只读窗口，与同一原receipt/task/approval/execution/projection/key绑定；SDK cap仅原RO五方法≤10，实际auth/list returned200/code0、scope及时间可信；真实started/stopped/termination/OS-absence均须闭合。当前原actor/roles/auth版本/App/Tenant/shop/expiry及C1/anchor0重核。

准入候选在既有audit内，用原outbox确定的唯一UUID持久消费`explicit_ro_recheck_authorized`（recheck_count1、完整当前window）；已消费即拒绝，SDK前消费失败不能续新窗口。dispatcher在delivery行锁下核此授权、当前窗口/caps/原owner/key/hash/unknown attempts3及INCOMPLETE_READBACK，再持久写唯一dispatched事件，保留automatic attempts3，仅reconcile。该授权不是仅绕过attempts predicate：重复/并发需0额外请求；失败保持spent，无自动继续。只有原完整唯一readback verified才由原协调器落anchor/verified；核心业务/CP、Graph/job/IM不动。当前该路径尚未通过PG正例，不可放行。

### 当前验证与停止

新自有project在11:25:58Z登记，固定20分钟截止11:45:58Z，预留75秒清理，不访问原known70/Secret/SDK/provider。首次启动参数被Compose拒绝（0pytest）；随后5pass/2fail（243.47s）、1pass/2fail（115.83s）、最后3pass/2fail（183.02s）。五个既有sender/first-create节点在前轮通过；最后三个pass为原sender两节点及撤权新节点。两个人工RO正例始终在并发准入前未成功消费，完整正例/失败spent/dispatcher并发尚未验证。

已拆除撤权后恢复角色的错误正例夹具：原冻结auth版本失效不能通过恢复enabled伪装有效。已修复prior DTO比较中ISO `+00:00`与Pydantic JSON `Z`的不一致，但最后两例仍失败；实际解除原因未确定，不把前述差异宣称唯一根因。两轮针对性修复已用完，不继续PG、不延长或复活窗口。各次down不-v均0；最终11:41:13Z容器0/网络0/卷保留；禁止diagnostic删卷/force/prune/清旧资源。

最后运行时六产品模块及新测试的实际import位置/hash已捕获于私有证据，与host字节另核；没有sealed新镜像或正式SDK证明。当前sameGateway实际PG未重跑。完整offline首1847pass/4fail/482deselected（旧nullable预期），修正required负例后1851pass/483deselected/104.87s；最终源码检查另由freeze记账。private 56pass/1 import-only probe排除/2.26s，只Fake/AST，不spawn主流程。safe observer最多四页，捕获has_more、完整页判定、原key数、数字合法/无损与逐字段相等布尔、schema type/ui_type；原值仅内存。旧96KiB self保护、006/007/旧freeze完整归档，实际007 reader DTO仍需Root另行授权的原PG准备，不能填造。

候选commit与private程序freeze供Root/Core审阅，状态HOLD；精确独审、新CI与实际RO均pending。无push/CI/main/Issue关闭，不改变0015/55表schema/权限/审批/库存规则/前端/B/锁/CI或18页。原D1/D30/300h/P450h/H-L not_reported保持。

最终当前源码完整offline1851pass/483deselected/4warnings/103.94s，Ruff通过/format419文件/type312/Markdown103均通过，实际六产品模块+一测试共七个import位置/hash与host完全相等。private adapter/r13 strict type两文件通过；private lint在既有E501/S101/S603/S607例外后仍有两处I001导入排序，按Root停止修复令保留，不记全绿。Root已确认预算spent，只交HOLD冻结给原Core只读审阅，无新PG/诊断/测试批；扫描与候选SHA在外置freeze核收。

## 2026-10-14 人工批准一次续段的最新候选

用户随后明确批准一次60min收口，Root释放原A同WT从F021137649冻结接续，T0 UTC13:05:49.310813→14:05:49.310813；一次定位+最多一次针对性修正验证，失败即停，作者PG≤15min/总≤20min/独审另预留5min、cleanup75s，不复活原窗口。上方budget spent/HOLD为当时历史；本候选仍待新精确独审/CI，不放行真实RO。

生产wire仅非bool int与原规范数字串，全部float拒绝。普通整值float、近整数/高位小数经默认JSON decoder舍入后的float负例通过；没有Decimal/rawnumeric新层，int范围/字符串文法/nullable/完整分页/唯一key/全部值绑定不改。

`trusted_reader`仅13个既有拒绝段加固定安全stage码，无DB值/ID/原异常文本，全部条件保留。新owned p4baserenew-c4a015eedb注册PG窗口13:10:19.080500→作者硬停13:25:19.080500：唯一定位真实PG捕获两个PermissionError/P4_RO_READER_SDK_CALL，当前新window SDK0；不是猜根因。核原Fake RecordedRecords返回ApiReply，但原ledger读取SDK `.raw.status_code`，所以Fake历史http_status=None。唯一针对性修正仅新reader夹具生成SDK-shaped Fake HTTP200/code0再交ApiReply给adapter，不追写旧行/失败资产，不改生产predicate或C1/anchor/hash/角色/终止/时间/caps。

唯一验证18/18实际PG通过（341.91s）：3manual（含撤权）、10sameGateway/v1-v2、2sender/13拒绝子例、3C0；两manual并发准入各1success+1重复Permission拒绝，dispatcher单次/重复idle/缺required失败spent、automatic attempts3/recheck1、核心及CP不变、无新execution/key均核验。首定位1fail原样保留，之后无第三轮/新PG。新库实际0016/56表，app三高权限false，原known70/0015/55表0访问；不是将新库说成原55表。

两轮均down不-v0/容器网络0/保卷，最后UTC13:22:11.697524退出，注册作者窗口累计712.617024s<900，独审资源另由Root指定，不保留在线项目。实际三产品模块+一测试+已冻结0016共五个hash匹配host，F02113所有13文件在Base事实导航追加前逐byte相同。完整1883offline/497deselected/4warnings/107.08s，相关107pure/3.39s，Ruff/format424/type316/Markdown104与敏感扫描分列；最终source/tree/private stage/计时/closure在外置freeze。

本段未改F02字段/迁移/私有bridge/锁/CI/审批/Graph，未AppSecret/SDK/provider/平台/旧DB/push/main/关Issue。旧a1864无效float规则和SDK_CALL失败不抹去；只新source独审+新精确CI后Root可另放实际RO，当前M1/P4/目标真实完整读回仍未验收。
