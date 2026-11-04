# V4-1 六卡独立 QA 计划（提案）

2026-11-04，Asia/Taipei。状态 `PLAN_PREPARED / IMPLEMENTATION_AND_RUNTIME_NOT_RUN`。
Root 本轮转交用户授权完整 V41-01—06；旧 V4-0 文档中的“不进入 V4-1”保留历史时点。
本片只写本提案，未启动 Docker、PG、API/Web、浏览器、网络查询、Hosted 或 push。

## 当前 H/S 文件卡与单案执行路径（2026-11-04）

以下是源码准备，真实 HTTP、浏览器、截图、原生 200% 和最终 PG 事实在本 QA 片均 `NOT_RUN`。
Root 的其他独立运行不得移填成本片结果；先前冻结与失败原件保持。

| 文件卡 | 精确实现文件 | 当前定义与待验 |
| --- | --- | --- |
| H01/H02 | `tests/e2e/v41/http_recipes.py`、`read_recipes.py`、`test_read_recipes.py` | ca69b83 已补四 GET 及独立 job GET；16 总路由为 12 GET + 4 POST，登记集合不作执行证明。TWD/CNY 14/7/1 日金标、分页、全筛选 CSV、三类 read-context；恢复 imported 对应 source 金标，实际监听未运行 |
| S01 父路径 | `tests/e2e/v41/browser_shell.py`、`owned_driver.py`、`test_browser_shell.py` | shell_navigation 固定 Shell 与 business 两标题、恰好 2 passed/0 skipped/0 retry；仅 native0 不通过。固定 argv，无 all 或任意 spec 参数；缺已提交业务 spec 或 Root 浏览器绑定时在 Docker 前拒绝 |
| S01 前端接缝 | `frontend/v41-e2e/playwright.config.ts`、`shell.live.spec.ts`、`browser-subjects.ts` | testMatch 固定两 spec；Shell 真实严格 session/control 响应、14 导航/刷新、三宽截图/键盘/persona/logout。WEB 独占 business.live.spec.ts 与 live-business.fixture.ts，QA 不编辑这两文件 |
| S01 原始请求与末态 | `tests/e2e/v41/request_witness.py`、`subjects.py`、`final_facts.py` | 真实 POST 透传前 fsync scope/原 key/path/body/hash；writers 停止后导入两份私有 journal，有效前缀保留，失败/UNKNOWN 不重放；按实际 DB canonical 请求核对原意图 |
| Shell 迟到清屏专项 | `frontend/v41-e2e/shell.live.spec.ts` | 原 operator 的真实 read-context GET 经 route.fetch 成功后暂缓交付；既有 persona/logout 成功且清空敏感状态后原样交付，核完整 body hash 相同、真实 response finished 和 UI paint 后事实仍清空。无 sleep、无新访客/业务写；tier=`NETWORK_ACK_DELAY_INJECTION_REAL_UPSTREAM`，仅源码准备，实际 `NOT_RUN` |
| 浏览器权限矩阵 | 完整权限/失效交错 | 本片只含现有 persona/logout 与延迟响应专项，不签完整 browser 权限 Gate；PG 专项不能代签，FR-05 尚未完成 |
| 原生 200% | GATES 独立新 owned headful/profile 路线 | 本片不包含该路线，两个 safe receipt 均保留 native200=NOT_RUN_IN_THIS_SPEC；viewport/CSS 不代签 |

执行接口仍为五个既有 scenario，不增加第六个或通用组合执行器。单案精确入口：
`python -m tests.e2e.v41.owned_driver execute --case <Root新私有case.json> --root-opened-window`。
先按原 prepare 仅生成新私配，再由 Root 提供新 authorization/build/expected-runtime/daemon 回执。
Shell 额外需要 0600 `browser-runtime.safe.json`：精确字段 schema_version=v41-browser-runtime-v1、
source_sha/source_tree/authorization_id/directory/uid/project/test_image/executable/sha256；executable 为
实际 canonical Chromium 路径及 bytes hash，无隐式下载、缓存或用户 profile。资源/UTC 由 Root 新核。

父流程保持：精确 source/image/Root 绑定 → 原 bootstrap → 已审三 owner 动作 → 本案 API/Web →
固定 HTTP 配方，或 shell_navigation 的固定双标题 Node/Playwright → writers 停止 → 独立浏览器
残留核验与 journal 导入 → PG 存活时逐 scope/key/job/version/receipt/event/effect 末态采集 →
scoped down 与独立容器/网络/端口核验、原卷保留。浏览器使用本案新 0700 HOME/TMPDIR；
残留强停或归属 UNKNOWN 会拒绝成功，不把清理动作补签成测试通过。任意实际失败不自动重试。

7358880 的 owner_setup.py、owner_recipe.json、owner_bridge.py、verify_inside.txt 字节继续冻结；
S01 只在原 owned_driver 中增加固定场景选择、报告/清理/事实接线，不改 bootstrap/owner准入。

## 来源、职责与前置冻结

- 唯一作者树：`/Users/aipuli/.codex/worktrees/commerceops-v41-qa/commerceops-agent`，
  分支 `codex/v41-qa-20261104`，base `1730194028a01ddea0bbc573774d740ea4a29d55`，
  base tree `5f2a92dffb49ef21682077e89459c85db55b668d`。每条命令显式绝对 workdir。
- 原包：`/Users/aipuli/Downloads/CommerceOps_V4_Codex_Development_Package`，已读
  `03_delivery/TASK_CARDS.json` 六卡完整交付/Gate、`PHASE_ROADMAP.md` 和
  `05_quality/TEST_AND_ACCEPTANCE.md`；14 模块参考 `01_product/SCOPE_AND_PAGES.md`。
- 当前已读 [V4-0 FINAL_GATES](../../acceptance/v4-0/FINAL_GATES.json)、
  [交付与限制](../../acceptance/v4-0/DELIVERY.md)、[原路由映射](../../baseline/reviews/PAGE_ROUTE_MATRIX.json)
  及现有 `tests/e2e/v4/{owned_driver,supervisor,http_probe,owned_adapter,browser_lifecycle}.py`。
  只做本阶段必要差异核对，不重做原基线审计。
- 后续 QA 独占 `tests/e2e/v41/**`、`frontend/v41-e2e/**`；本提案路径由 Root 释放。
  `tests/v41/backend/**` 由 API owner 写；QA 不改共享 schema/迁移、backend、WEB 生产文件、
  scanner、原测试框架或现有 V4-0 证据。需要接口/夹具/collector 变化时先给相应 owner 缺口。
- 常规机械执行 Sol medium；并发/事务隔离/撤权竞争专项按 Root 分派升 high，并交独立审查。
  本计划不自行创建会话、调整模型或放开资源。

开写测试/运行前必须具备 Root 冻结的六卡 TaskSpec、route/page/feature ID、API/OpenAPI、
角色与店铺矩阵、source_ref/version、KPI/导入口径、错误码和具体资源 UTC。凡尚未定义的
金额字段、退款归期、CSV 编码/大小、XLSX 解压/行列上限、映射规则、版本冲突语义，登记
`CONTRACT_PENDING`，不由测试作者猜默认值。原候选 66 路由不直接当本期都已实现。

## 六卡验收矩阵

| 卡 | 原 Gate 与 QA 可核行为 | 必须关联的证据 |
| --- | --- | --- |
| V41-01 Shell | 14 模块导航、角色可见/点击/刷新、直接 URL、过期/撤权/退出清屏；真实后端权限不由 UI 替代 | 路由状态矩阵、真实 HTTP 鉴权、每种状态浏览器行为 |
| V41-02 KPI API | 来源、时区、币种、期间、快照一致；不完整显式状态；程序金标可追溯 | 已审数据金标、真实 API/PG 同快照比对、空/缺/退款反例 |
| V41-03 首页/Copilot | KPI/图表/洞察/异常/待办由真实 API 驱动；切店/期间/权限后无旧响应污染 | 金标与 UI 对照、交互及多尺寸截图；AI 模式如实标注 |
| V41-04 商品订单 API | 多店 source_ref、服务端角色、数据/履约版本；overlay 受控编辑、旧 Woo 零写 | PG 原前后事实、版本/原键/并发/隔离/撤权、外写能力边界 |
| V41-05 管理页 | 商品/订单列表详情、编辑、筛选导出联动；原键状态持久、移动端、越权空态 | 点击/刷新/新页面、真实请求与 PG、UNKNOWN 只读核对 |
| V41-06 导入 | CSV/XLSX 上传→预览→映射→校验→显式确认；恶意/超限拒绝、会话隔离、原子回滚 | 实际文件、解析/安全纯测、真实 API/PG 导入与拒绝零写、SKU 可查 |

V41-06 的无 AI 导入→列表/详情→同源看板为本阶段跨模块演示候选，至少给三步用户操作。
包内 FLOW-F 的“AI”及六条完整 L3 流程仍分阶段；侧栏入口不等于真实模型或六链完成。

## 01：14 模块导航、角色与失效

清单覆盖 01经营驾驶舱、02 AI智能工作台、03经营分析、04商品、05订单、06库存、07采购供应商、
08客户售后、09智能客服、10营销、11自动化、12知识、13审批任务、14数据系统管理。
对每个冻结入口登记 module/page ID、path、stage、实现状态、所需 scope、persona/shop 和证据。

每条入口区分实际可用、明确后续规划、权限拒绝及未知 URL。规划模块可以展示真实状态，
不能让空壳成功页计为业务完成；原型 83/83、14 模块或 66 页总量均不作本期通过数。

1. 新会话点击、直接访问、刷新、前进后退和携带筛选深链结果一致；旧 M3 catch-all 路由优先级保留。
2. operator/approver/restricted_admin 与无 grant/跨店/跨 tenant：导航可见性与真实请求权限相符；
   隐藏按钮不是服务端拒绝证据，URL/参数/伪 role 不得提权。冻结状态码精确验证，不随意接受任意 4xx。
3. session 到期、撤权、退出、切 persona/reset 后，当前身份、指标、商品/订单详情与敏感缓存清除；
   旧 CSRF/epoch/generation 写拒绝。401/403 不自动重登或恢复旧写操作。
4. 延迟响应在切店、改期间、切角色、退出后到达，不覆盖新上下文；浏览器刷新不复活旧 pending key。
5. 移动导航键盘可达、焦点可见，抽屉 Escape/焦点返回、错误提示关联、无键盘陷阱和遮挡。

## 02/03：KPI、金标和图表同源

同一请求/截图记录 tenant、当前 shop、fixture/source_ref、schema/snapshot version、期间及 timezone、
currency；响应上下文与当前身份、钻取及 PG 金标一致，不能拼不同快照生成看似相等的数值。

- 金标由明确公式与固定种子独立核算（Decimal/最小货币单位及舍入按合同），不直接复用被测聚合输出。
  首页→钻取→商品/订单详情对账；切店/期间后数字、图例、异常列表/待办保持同源。
- 时区覆盖 local midnight 与 UTC 跨日、期间边界、订单 paid 与 refund 发生日不同，夏令时仅在
  冻结支持时区适用时测试。日期选取采用明确区间边界，不能以浏览器本地时区隐式改变归期。
- 单币种与混币种：无已批准汇率/转换依据不得相加；币种标签与数据相符。成本缺失不产出毛利。
- 全额/部分退款、延迟退款、重复退款来源、净额与数量口径；无销售且有退款的期间。
  零是实测空数据的数值，UNKNOWN/部分分页/不完整退款证据不能填 0；比率分母为 0 有明确状态。
- 空店、空期间、部分来源、旧快照、服务错误/超时、无权限分别有合同状态；未声明的指标保持未实现。
- chart/KPI/洞察若不一致即失败；侧栏合成或未接模型状态明确，任何 AI 文案不能改写程序金标。

## 04/05：商品标签、订单关联与履约

- 两个 tenant 各有双店，使用同名 SKU/相似 display ID 反例；详情以服务端 source_ref/版本绑定，
  商品→关联订单→订单行商品回链必须指向正确店铺、版本和授权对象。
- 标签/受控字段编辑后，同页详情、关闭重开、列表筛选/分页、新请求和刷新均与 PG 当前版本一致；
  未确认/取消/验证错误无写入。异店/异租户标签不能出现；导出也执行同一筛选和权限。
- 履约按冻结允许状态转换；提交旧版本、同 key 异 payload 冲突，不偷偷 last-write-wins。
  同 key 同 payload 重放 10 次只产生原一次效果/receipt，审计数量与版本增量实际核验。
- 同对象两请求版本竞争、标签编辑对列表读、履约对 reset/撤权竞争：用新 owned PG 同步屏障，
  比对事务前/后与合法序列；不能靠 sleep 猜竞争顺序或用串行用例代签并发。
- ACK 丢失使用真实 POST 到服务端后的测试端丢弃；保留原 operation/key/context，刷新仍可 GET 原键。
  UNKNOWN 不自动第二次 POST、换 key 或将当前页显示成功当 commit；原键冲突/过期按冻结合同处理。
- 原 source_kind 显示演示 overlay，保留可追溯 seed/version。PG 写仅本会话合成数据；禁真实 Woo
  库存/订单/退款写入及外发。拒绝路径记录业务零增量，不以“没看到 UI 变化”代替 PG 事实。

## 06：CSV/XLSX 文件与导入原子性

采用小型合成公开样本，精确 bytes/hash；恶意样本不得含真实客户数据，不调用外部解析服务。
导入限制由 API owner 合同冻结后用 limit-1/limit/limit+1 验证，测试不自行扩大上限。

| 类别 | 必须验证 |
| --- | --- |
| 成功流程 | 两格式上传/预览/映射/显式确认，确认前无业务增量，确认后 SKU 在正确店铺列表/详情可查，来源与导入批次/快照一致 |
| 映射与质量 | 必填/重复/未知列、列重排、编码/BOM、引号/换行/分隔符、空文件/空值/非法数值、重复 SKU、首中末错误行；规则依冻结合同 |
| 超限 | 上传 bytes、CSV 行列/单元格、XLSX 压缩/解压总量、压缩比、entry/worksheet/行列数量；拒绝在受控资源和截止内完成 |
| XLSX 攻击 | ZIP 路径穿越/绝对路径/重复 entry、损坏/伪扩展或 MIME、宏/vba、外链/外部关系、DTD/实体/XXE、异常 XML 深度；不访问外网/宿主任意路径 |
| 公式 | CSV 和 XLSX 公式及 =/+/-/@、空白/控制前缀等绕过样本；文件公式不执行，按合同拒绝；导出另验证中和策略，不混同导入规则 |
| 原子回滚 | 前段合法后段错误、解析/验证/持久化故障与提交前中断；新 owned PG 确认整个批次业务表/关联/receipt/版本无部分提交；安全审计可按合同保留 |
| 并发与原键 | 同批同 key 同 payload 十重放、异 payload 冲突、双确认竞争；导入与商品编辑/reset/撤权交错；一个逻辑效果，不用全局清表重建样本 |
| TOCTOU/隔离 | 预览后文件/映射/数据版本变化、预览过期、权限撤销、切 persona/shop、另一 tenant 使用 preview/token/key；确认重新鉴权并绑定原文件摘要/版本，拒绝零业务写 |
| 恢复 | commit 后 ACK 丢失 GET 原键核对，UNKNOWN 保持；拒绝/过期不静默变新 key，用户显式新操作才另案 |

测试文件集合和故障点由 API/QA 协议列明，API owner 的 `tests/v41/backend/**` 验证解析/事务内部；
QA 用公开接口/受限 PG observer 和真实浏览器独立验收，不增共享 schema 或替代 backend 测试。

## 分层检查与 Full_required

| 层级 | 触发/范围 | 只能证明 |
| --- | --- | --- |
| Fast | 每个短提交：受影响纯测、strict DTO/类型/lint、规则及金标/文件安全负例 | 当前代码静态/纯函数；UI fixture 合成响应单列 |
| 专项 | API/PG 权限事务、并发/回滚/UNKNOWN、import 安全、撤权/租户隔离；真实 HTTP 与受限 observer | 精确已执行场景，不能由 MockTransport 拼成 API_PG_VERIFIED |
| 浏览器 | 新 owned API/PG/Web，冻结 specs/title/blob、真实网络与 Cookie；桌面/手机/原生缩放 | 页面用户路径及对应后端效果，不代替完整工程或 PG |
| 最终 Full | 以下 Full_required 全部实际执行并独审精确冻结源 | 本地阶段 Gate；Hosted/生产与真实模型继续独立 |

Full_required 清单（计划，全部实际状态 NOT_RUN）：

- FR-01 完整工程 `python -m scripts.check` 及当时依赖/工具链/锁：扫描、文档、lint/format/type、
  全 offline、strict schema/M3 无 server 契约、前端 typecheck、依赖审计；网络步骤须 Root 窗口，
  当前不运行，不用删审计或 `-k` 筛选伪作完整通过。
- FR-02 冻结源动态 PG collect：完整 integration 节点清单及 hash，逐项登记新增 V41 backend
  目录是否被真实 collector 收入（marker/path 任何漏收阻断，交 API owner/Root）。不能固定写 745+N。
- FR-03 原 canonical 两线 existing/phase3，实际 selected/collected/setup/call/teardown 与
  pass/failed/skip、模块 exit、超时全部采集；相同 SHA/tree/工具/锁/collection，union=完整动态
  集合、intersection=0，原 `scripts.pg_ci_evidence` 严格配对 native0，不调整 G1/G2 或放宽分区。
  G1 三项、G2 原六场景都需真实证据；phase3 不冒签 existing 的 G1/G2。
- FR-04 新 V41 API/PG 专项及跨模块导入→SKU→同源看板；所有合同要求的并发/撤权/回滚负例实际验证。
- FR-05 V41 真实浏览器：1440、390、1280、原生 200%，键盘/移动/空错态与权限失效矩阵；关键截图
  来自实际页和干净 profile，原生 zoom 不用 CSS/viewport 仿造；禁止跳过/重试/裁剪遮住错误来签收。
- FR-06 受影响 V4-0 regression：session/capacity/ACK 两支、CSRF/Origin/跨 tenant/shop、persona、
  同 key reset/撤权、bootstrap restart、固定非滑动 TTL、seed 回滚/来源、路由优先级。涉及权限/身份
  高风险修改按完整矩阵执行；无变更复用只能由 Root 精确字节/输入证明单列，不能变成新源实跑。
- FR-07 旧 M3 全工程/PG、legacy Web read7/write10/items7 与 N01six 对应回归。M3 daily/inquiry/copy
  三独立 flow live 在 V4-0 为 NOT_RUN，本期若受影响或被 Root 列入 Full_required 必须补实跑；未释放
  资源/合同则保持 NOT_RUN、最终受影响 Gate HOLD，不拿旧 Web/离线/PG 代签三 flow。
- FR-08 精确 SHA 独立 review、最终文档/目录/index/完整可达历史扫描、文件地图及安全证据清单；
  scanner 变更与运行由原 owner/Root，不在 QA 片内补豁免。

当前 V4-0 已核 Gates 是历史参考：[FINAL_GATES](../../acceptance/v4-0/FINAL_GATES.json) 为
REQUIRED_LOCAL_RUNTIME_GATES_ACCEPTED；PG R2 existing568+phase3177=745、零交集、G1三/G2六；
工程 cbd 4316 offline/748 deselected、native0；HTTP11 分 F1/R2/R3；fixture35、R3 browser1、自然
TTL、legacy24/N01six 分来源。数字、已知 deprecation warnings、旧失败/UNKNOWN 均保留，
不能从这些基线直接声明 V41 完成；原型 83/83 不进真实回归计数。

## 资源窗口与测量容量（尚未释放）

每个 runtime run 由 Root 绑定唯一 owner、新 clean source/tree、锁/合同/seed/hash、exact image ID、
新 project/DB/目录/端口/CIDR、UID、实际 start/deadline 与清理 reserve，绝不沿旧 privateconfig、
once、卷或窗口。现有 V4-0 `Case` 还硬绑定 0024 migration 和旧 browser pins，不能改个场景名就
运行 V41；后续仅在授权 QA 路径准备窄入口、由 API/WEB 提供已审接缝和精确迁移/contract 摘要。

沿用已审机制的原则：UTC+monotonic 双截止，启动前 exact image/namespace/IPAM/model 校验，
PG 不发布 host port、API loopback、owner/runtime 权限分离，禁代理/redirect/自动 POST 重试；
所有 Cookie 快照复用逐 Cookie 的 `snapshot_cookies` 语义，禁止 deepcopy CookieJar 锁。
独立 child probe 原生退出与预先登记的 process group/容器归属必须可追溯。先停所有 writers、
再在 PG 存活时最终只读采集、最后 scoped cleanup；核容器/网络/登记进程/端口及保卷事实。
不 prune、接管未知 PID、全局修改 Docker 或因镜像消失自动 build/retag。

容量仅用于 Root 排窗参考，不构成新授权或可用性保证：V40 完整工程约 1389.861s，PG existing
1947.5s、phase3 1684.853s。新 V41 数据/导入负例与机器争用尚未测量；普通 case 原 20/30min
上限或父窗口不能硬套 FullPG。保留 canonical 命令/模块时限，Root 应按新实测总量+启动+最终
采集+至少180s清理余量分配明确窗口；容量不足则 HOLD，不能缩集合/丢 G1G2/续旧窗。

Fast 无服务；专项按新案隔离；并发专项与 Full 两线是否并行由 Root 看 CPU/内存/磁盘余量统一
安排。无测量时先串行有限 pilot、冻结后再整体测量，不盲目重复失败；修复后新的 case/source/
窗口单列。需要自然到期的时间按真实合同另排，禁止调 DB 时钟/缩 TTL 冒充自然验收。

## 回执与监督：退出码、状态和 refs 分账

Root 报告的“最后包装器在回执写后 KeyError”按原事件保留；本计划未重新读取/执行该未提供
路径的原件，不臆造 traceback 或归为测试失败。后续索引须登记原 source、日志/ref/hash 和
wrapper nonzero；已有子命令结果也不被 wrapper 失败抹掉。待 Root 提供精确原件位置后补证据。

V41 ops 监督设计必须先独立核：

1. 每个真实子命令立即保存 argv 安全摘要、start/end UTC/elapsed、source/tree、原生 exit（含 signal、
   timeout/UNKNOWN）、selected/actual/pass/fail/skip 与日志 path/hash；即使后续汇总失败也能核原件。
2. 分离 `command_results`、`evidence_refs`、`cleanup_result`、`observer_result`、`outer_native_exit`。
   refs 是信息索引，不带 pass 字段，不将所有对象在最后当测试字典统一读取；最终聚合只读取明确
   schema 的命令记录。missing key/坏 JSON/观察失败有独立非绿状态，不能默认 pass。
3. 记录真实命令、probe、writer 停止码、观察器、final collection、parent/outer 各自退出；预期
   服务 SIGTERM/-15/143 与异常停止区分。未捕获则 NOT_CAPTURED，父0不覆盖子非0/未知。
4. 业务提交事实、客户端 ACK、只读核验、wrapper 成功分开。observer 记录异常类型/errno/阶段，
   原始 exception 文本仅新 private0600、无 locals/env/敏感请求泄露；日志失败不替换业务异常。
5. 无资源、未执行、不适用、UNKNOWN、NOT_CAPTURED、原失败逐项保留；旧原件只读不覆盖。
   相同未知故障不盲重跑，停受影响路径，先按现有证据定位并由 Root 冻结后续精确切片。

最终提案证据包在 Root 释放后写 `docs/v4/acceptance/v4-1/`：MANIFEST、QA_RESULTS、review、
截图安全索引、三步 DEMOS 和 RISKS；逐 case 包含 task/feature/page ID、受测层级、精确来源、
实际 PG/API/Web、原生 exit/计数/cleanup、原件/hash 与未跑项。当前仅本计划，所有 V41 运行
结论为 NOT_RUN，actual token/cost UNKNOWN；无 Hosted、远端、真实 provider 或生产结论。

## 本片读取的原包指纹

下列指纹只绑定本次读取，不声明整个包重新审计或合同已冻结。

| 原包相对路径 | SHA-256 |
| --- | --- |
| `03_delivery/TASK_CARDS.json` | `7aa2da8c979fcd35d3746e01b3c64db569767745e7b9377dc2c5fb087e137440` |
| `03_delivery/PHASE_ROADMAP.md` | `54c65e513a418ba2e2bde62df6048550b086d46c7b7da0d4257189f769ec74e4` |
| `05_quality/TEST_AND_ACCEPTANCE.md` | `c4ed70d461d0101e2db00b58231f151fad523511d415bd52158ea6ca59ae6e28` |
| `01_product/SCOPE_AND_PAGES.md` | `5f68594ffb2759504d7472bcccec2e732fc623a6c4f96b6292f059a7b3d35a68` |


## 合入增量 V41-1 的精确目标（2026-11-04）

Root 合同 `84db1ba34120cac3b4fccb6bbe316d3efbca1659` 已普通合入本 QA 树；权威为
[CONTRACTS.md](../CONTRACTS.md) 和 [STAGE_SPEC.md](../STAGE_SPEC.md)。下列取代本计划相应
数值/语义的 CONTRACT_PENDING，实际 DTO/schema、SQL 和资源窗仍待精确冻结。没有改变旧原包。

- same-source：当前 fixture+tenant/shop/epoch+有效确认导入的统一视图，data_revision 与
  auth_generation 分开；cursor 绑定 filter/sort/revision/snapshot/稳定键，新数据返回明确冲突。
- 商品上传闭集 sku/title/price/currency/tags；ASCII casefold SKU 唯一，不 upsert；价格非负
  十进制最多 6 小数；导入不创造销量/库存。标签最多 8 项、每项 1—24 字。
- JSON body≤3MiB，严格 base64 后文件≤2MiB；500 行、24 列、cell≤512 字、title≤120 字；
  每 tenant/shop/epoch 最多 500 导入 SKU。CSV 固定 UTF-8/可 BOM 和严格逗号引号。
- XLSX 单 sheet、≤32 entries，实际解压总计≤8MiB、单 entry≤2MiB、ratio≤100；XML 增量
  深度/节点/字符串/属性边界仍待精确实现独审，不猜未给出的数值。宏/外链/公式缓存/DTD 等拒绝。
- 解析硬预算 2 秒；独立子进程真实终止并 wait/reap 后才释放槽位，不能用 async/线程取消代替。
  同 tenant 最多 1 个、全局最多 2 个解析；PG advisory slot 跨进程、准入前鉴权，解析不持业务锁；
  后置 job 写重新核当前权力和 TTL。SQL statement5s/lock1s 不放宽。QA 模拟的 TERM→KILL/reap
  只证明短进程机制，不证明 2 秒解析器或 PG slot 生命周期，后者须 API/PG 专项真实验证。
- preview 原 key 同文唯一、异文409；GET `/api/v4/imports/preview-requests/{request_key}` 在当前
  tenant/shop/owner/epoch/gen/权限下只返回最小 job_ref/UNKNOWN。缺行不判回滚，不自动新 key POST。
- parent_job_id 链必须同 file/owner/context，不可变子版与 supersede 同事务；每链≤5版本、
  每 tenant≤12 jobs、≤3未过期 active heads；preview10分钟且不晚于 session。sample≤20、错误≤100。
- confirm 仅接受 job/version/digest 和预期 context/revision；重核权限、expiry、supersede、SKU/
  币种/额度；effect/receipt/event 同事务。自身已提交原 key 同文回执在业务 CAS 前读回，不能把
  第一次效果推进的版本当重放失败；旧身份/TTL/撤权仍先拒。已确认 job 换 key 不得再次导入。

后续精确 schema 到位后补独立 golden/真实 E2E；当前只已有固定本机监督模拟，没有业务 API
断言、PG、browser 或 importer 实跑结果。原 V40 wrapper1/031/446 和所有历史失败保留。
