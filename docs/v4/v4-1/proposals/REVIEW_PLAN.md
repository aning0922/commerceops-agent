# V4-1 独立审查计划与架构预审

2026-11-04（台北）。状态：REVIEW_PLAN，实施与运行结果尚未核收。

## 1. 范围与来源

Root 会话 `01a19f1b-f4c0-75c1-a9f0-8f8b88db72d5` 转交用户对完整 V41-01—06 的本地实施授权。本审查工作树从 `1730194028a01ddea0bbc573774d740ea4a29d55` / tree `5f2a92dffb49ef21682077e89459c85db55b668d` 开始。基线 AGENTS 的“不进入 V4-1”保留原批次时点，本次范围以新明确授权为准。当前仅只读预审和本计划普通提交；不改作者业务代码或读取作者未提交 WIP。

读取原任务包 `/Users/aipuli/Downloads/CommerceOps_V4_Codex_Development_Package/03_delivery/`，不是用 V40 TASK_PLAN 代替 V41 六卡：

- `TASK_CARDS.md` SHA256 `b39f1c893f98f9f195e97b1207c93752967aa87031f987b2bf4cdad91bf51a03`。
- `PHASE_ROADMAP.md` SHA256 `54c65e513a418ba2e2bde62df6048550b086d46c7b7da0d4257189f769ec74e4`。

基线四合同：`docs/v4/baseline/{DOMAIN_SOURCE,PERMISSION_DEMO,UI_ROUTES,API_EVENTS}_CONTRACT.md`，连同权限 CSV、OpenAPI 和 seed 定义保留。四合同中的历史候选/未授权表述不回写；V41 增量通过新合同列出兼容与变更点。

| 卡 | 完整交付范围 | 独立审查重点 |
|---|---|---|
| V41-01 | AppShell、14 模块路由/分类、主题、统一错误 | 可见、点击、刷新、权限与失效清屏；不是 14 个假成功页面 |
| V41-02 | KPI、统一经营查询、指标钻取 API | 金额/币种/时间/来源/快照一致和缺失状态 |
| V41-03 | 首页 KPI/图表/洞察/异常/待办及全局 Copilot 容器 | 真实本地 API、筛选联动、响应式与无模型能力的明确边界 |
| V41-04 | 商品订单授权详情、受控演示编辑与履约 API | 版本 CAS、当前授权、幂等事务、overlay、旧 Woo 零写 |
| V41-05 | 商品订单列表/抽屉/编辑/筛选/导出 | 持久回读、订单关联商品、分页一致、迟到结果与导出隔离 |
| V41-06 | CSV/XLSX 预览、映射、质量回执、确认导入 | 资源限额、文件解析、整批原子性、导入 SKU 可查询 |

阶段产品 Gate 必须包含：14 模块有可达的基础业务界面或明确分类；同源看板有数据；标签修改后详情可回读；切店清旧状态；订单关联商品；CSV 导入后可查询新 SKU。阶段后端 Gate 包含超限/恶意输入拒绝、异常行整体回滚、跨租户 404、来源保持、可复验分页筛选。六卡全覆盖，不缩减为前三卡；14 模块分类不代表 66 视图或 99 功能完成。

## 2. 已观察的实现接点（不是新运行证据）

- `v4_demo_sessions.py::resolve_locked` 先定位 tenant，再锁 tenant/session，核 credential/principal、bound WebSession 与 actor；persona 路径按 principal 排序。新路径应复用这条身份链，不能只拿裸 WebActor 绕过 epoch/generation。credential 查询与撤权写的竞争需专项核验；现有身份测试不能自动证明新长事务安全。
- `v4_demo_store.py::summary` 校验 fixture canonical hash 后返回模板计数；它没有读取商品/订单 overlay。经营查询必须实现有效数据视图，不能把欢迎摘要换标题当 KPI。
- `seed_contract.py` 已有两种店铺币种、订单金额/支付时间、订单行和退款；SKU 成本为未知、部分支付时间未知、退款数量/回库及网关状态未知。不能从 supplier quote、订单创建时间或退款金额猜成本、支付或履约事实。
- `0024_v4_demo_foundation.py` 的 overlay kind 只有两种窄用途，runtime 仅获 overlay SELECT/DELETE；控制 receipt operation 限四种，事件/FK/请求校验也有窄约束。业务编辑、履约和导入需要明确新持久模型/约束/ACL，不能只扩大 DTO 枚举。
- `v4_demo_seed.py::require_owner` 精确要求迁移 0024；新 head 上初始化、grant、reset、GC 兼容均须显式处理。旧 revision 不回改，不能通过撤掉 head 校验掩盖升级断链。
- `frontend/lib/v4-context.mjs` 以身份、店铺、epoch/generation 和请求序列拒绝迟到结果；当前单 gate 的全局 sequence 适合串行摘要，多个 KPI/列表并发复用时可能互相淘汰。建议共用身份失效代次、每个独立查询槽位保留自己的 sequence，并绑定筛选/快照，不能简单删除序列检查。
- `frontend/lib/v4-client.ts` 用 schema 校验信封、cookie/no-store 与有界 fetch；新的分页、导入、导出格式必须有自己的严格校验，不能因通用 Envelope 类型宽泛而接受未验证内容。

## 3. 实施前冻结的增量合同

Root 分配唯一 owner 后提交一组可审增量：领域/来源、能力矩阵、KPI 口径、操作事务与回执、导入格式及限额、API/OpenAPI/错误、UI 路由状态与文件 ownership。Reviewer 针对精确 SHA 审查；冻结值写入合同，不靠聊天口头常量。以下是可由 owner 采用的最小实现建议，不是要求用户逐项审批，也不是已实现事实。

### 来源与经营快照

保持旧 M3 source_mode 语义；V41 使用明确的 demo fixture / 租户覆盖 / 本次导入来源链，沿用各独立 mode 字段，不把 offline_stub 显示成真实模型运行。每个对象带 tenant/shop/kind/id/version/epoch，源引用含 fixture version/digest；导入对象另含 batch digest 与原始行定位，不冒充原 fixture 中已有对象。

建议先按单店查询，跨店展示按币种分组，不默认换汇求和。有效数据视图定义基线加当前 tenant/epoch overlay，明确新增、更新、删除/不可见和关联优先级。所有读路径（KPI、列表、详情、钻取、导出）走同一语义，避免改完只在 UI 内存可见。

一次响应中的指标、分母、图表应来自一致 PG 快照或同一已物化版本。分页和钻取绑定 dataset revision、tenant/shop/epoch、筛选摘要及排序；数据变更后游标明确过期或继续读已有快照，不默默混页。稳定排序含唯一 tie-breaker；offset/keyset 的选择可由 owner 决定，但必须证明无重复/遗漏。授权在每次读时重核，快照不能恢复被撤销权限。

### KPI 金额、时间、完整性

冻结每个指标的名称、公式、计入状态、时间字段、退款归属、币种、舍入、未知值处理和钻取集合。建议金额以十进制字符串在 API 传递，服务端 Decimal 定量计算；禁止 JS 浮点累计或 bool/非有限数混入金额。币种精度及最终舍入规则明确，零分母显示不可用。

以 shop IANA 时区解释日期选择，转 UTC 半开区间 [start,end)，单独记录 fixture snapshot_at、数据版本和 DB as_of；不能将固定 fixture 日期伪装成今天实时交易。建议默认日期锚定已知 fixture 范围并显式显示。支付时间未知的订单不拿 created_at 补齐；展示已知部分及 excluded/unknown 数量。退款分别按批准的事件时间/订单口径计算，避免净额重复扣减；毛利在成本未知时不可计算。没有异常/没有数据/权限不足/数据不完整/服务错误必须不同状态。

验算使用手工可核小样本：跨日边界、时区转换、相同排序时间、缺支付/成本、退款跨期、空集合、币种分组、大金额/精度、筛选后总数及钻取之和。UI 的值须能追到 API 中具体来源和公式版本，不能仅比较两份同算法输出。

### 权限、业务写与竞争

新增能力按读取、标签/允许字段编辑、履约、导入预览/确认、导出明确映射到当前角色与 shop grants。建议 operator 获受控 demo 操作，approver 不因角色名称自动获得运营写，restricted_admin 不隐含业务权限；最终矩阵由合同具体冻结。客户端 role/tenant/principal/source 字段不授予权限；静态路由 import 等不能被动态资源 ID 吞掉。

建议第一版限定标签等非金额字段及明确有限履约转换，不实现真实发货/退款/扣款。履约允许状态、库存是否变化、重复转换语义需完整列明；不改历史订单价格来制造 KPI 变化，不凭金额推退款数量。读/写均核资源所属店铺、当前身份及 expected resource version/epoch/generation。

同一事务提交业务效果、不可变最小审计和业务 receipt；幂等键命名空间绑定 tenant/session owner、principal、shop、operation 与规范 payload digest。不要把新业务回执塞入只允许四种控制操作的既有恢复接口。相同键同内容只有一次效果，异文 409；重启后原键可查，当前授权失效不泄漏旧业务。提交前失败全回滚，提交后 ACK 丢失保持 UNKNOWN 并只读原键核对，缺行不等于失败；禁止自动换键重发。

沿用 tenant→session→身份/权限→资源的兼容锁序，并列出所有写、reset、persona、logout、credential/grant 撤销、导入的实际 SQL 锁次序。多资源按稳定 ID 排序；保持锁等待/statement deadline。必须证明撤权与提交线性化、reset 不容旧写进入新 epoch、同对象双写 CAS 一胜一冲突、相同请求竞争一次效果、跨租户写不串行污染。不要靠 UI 禁用按钮替代 PG 约束。

## 4. CSV/XLSX 导入与导出

建议初版导入商品/SKU，不暗增订单支付或库存调整权限。冻结 UTF-8/BOM CSV、严格引号与列映射；XLSX 只接受无宏工作簿白名单结构和显式文本/数值单元格，不执行公式或信任缓存公式结果。映射字段白名单；拒绝重复表头/重复主键、未知列策略明确，保留 SKU 前导零。数值、日期、空值、长度及 Unicode 规范化需明确；公式样文本不可在导出后变为可执行内容。

建议起始限额（待 owner 固化）：上传 5 MiB、解压累计 20 MiB、ZIP entry 128、单 entry 5 MiB、展开比 100、单数据 sheet、2000 行、32 列、单元格 4096 字符、解析 5 秒；以最先触及者拒绝，含输出错误列表数量上限。限额是建议而非测得容量。多 sheet 文件应明确拒绝或显式选一张，不悄悄忽略数据。

同时校验流式接收字节和真实文件内容，不能仅信扩展名/MIME/ZIP central directory 声明。解压前和读取过程中执行累计限额，拒绝路径穿越/绝对路径/符号链接/重名 entry/加密归档/嵌套归档、宏/OLE/外部关系、DTD/实体与外部 XML 引用；不访问 URL、本地路径或网络。临时文件仅随机私有 owned 目录并有失败/超时清理，异常回执不包含原文件内容或路径秘密。

解析与质量预览无业务写效果；可保存有界临时 preview 元数据。确认需绑定 tenant/shop/principal/epoch/generation、文件 digest、映射 digest、parser/schema version、dataset revision 和到期时间。客户端不能修改预览行后直接冒充确认。预览后撤权/reset/编辑/换店或超时则拒绝并重新预览；稳定 request key 控制原子确认。全文件验证成功后一次事务写入 SKU/关联/来源/审计/receipt，任何一行失败整体回滚，不先逐行 commit。只读查询必须实际读到新增 SKU，订单关联不能跨 tenant/shop。

导出复用当前权限及完全相同筛选/快照，不只导出屏幕当前页。确认大小/行上限、编码、引用转义、公式注入防护（含 =、+、-、@ 与控制字符前缀）以及金额列类型；所有导出值按数据写出，不作为公式/HTML。下载前重核 context，切换/reset/登出清待下载 blob URL/预览与缓存；已下载文件不能承诺远端撤回。导出文件的原子发布与 PG COMMIT 分开记账。

## 5. 最小迁移与接口审查

优先新 revision 串行承接 0024，具体编号在作者冻结时核当前 head。不回改旧迁移或改旧授权语义。新增业务 receipt/overlay/import schema 选择由 owner 提出，审查最少表/列/索引、tenant/shop 复合 FK、版本/金额/状态约束、不可变来源、删除与 reset 保留策略；不引入新通用框架、第二 Worker 或后台任务来回避短事务。

低权 commerceops_app 仅授必要 SELECT/INSERT/指定列 UPDATE；审计/receipt 不给任意 UPDATE/DELETE，fixture 不给写，导入不获得旧商务表全权。若使用 SECURITY DEFINER，锁定 search_path、限定调用角色与参数、禁止动态对象名；实际以低权连接验证允许与拒绝。新 head 表集合、空表/旧数据 byte preservation、0024→新 head、初始化与重复 grant/reset、故障回滚须同源码验证；只更新当前 head 期望，历史固定迁移断言不改。

新增 DTO/OpenAPI 统一 strict extra forbid，所有敏感响应带权威 context；请求携带的版本只是 CAS。授权失败不带旧 data，422 不回显文件敏感内容，未知提交状态与业务拒绝不同。分页游标/preview id 不成为 bearer 权限，资源不存在与越权遵守冻结 404 策略。旧八端点及 /api/v1 行为保持回归，不能全局重写旧 schema/source_mode。

## 6. UI、Copilot 与完整阶段证据

Shell 有十四个明确类别与路由登记，每个类别说明可运行基础页及后续能力；禁止假按钮、空成功态充数。首页、商品订单管理与导入完整实现后才能签本阶段，后续模块的分类界面不签 66 视图全量。

每次敏感请求/抽屉/分页/图表/导出捕获 context、筛选、快照及 query sequence；切店/persona/reset/logout 开始即清旧数据。401/403、轮询失败、后台/offline、BroadcastChannel 丢失和恢复都不得重新显示旧上下文。错误的迟到响应也不能清掉更新后身份。业务 key/proof 保留限于安全恢复，不存 token、权限或文件内容到 localStorage；刷新后的 UNKNOWN 不能靠新 key 掩盖。

Copilot 在此阶段是侧边容器。规则生成的洞察标记规则和 synthetic source，建议操作只链接已授权页面；不得伪造 token streaming、模型推理、工具调用成功或已执行任务。没有真实模型能力时显式说明，禁用真实发送/执行；不接 provider key、外部工具、M3 Worker。若要使用本地 stub，仅冻结输入输出与实际模式，不将它计为真实 AI 验收。

审查与运行按顺序：合同/SQL专项→作者精确 SHA→独审→新 owned PG/API/Web 实跑→Root 普通集成与同源最终 Gate。关键 KPI、权限/事务、导入专项使用高强度审查；纯 metadata 最后只读确认，不为扫描制造循环提交。资源窗口和唯一 owner 由 Root 另登记，计划本身不开放资源。

阶段 Full 要求：动态 collect 的完整 PG 精确并集/交集与旧 G1三/G2六保护；完整工程检查；新增权限/事务/导入 PG 真实失败与并发矩阵；完整 V41 六卡浏览器主链及旧相关 Web/N01/M3 回归。UI 1440/1280/390、原生 200%、键盘/焦点/Esc/reduced-motion、刷新/切店/迟到/失效、下载与恶意文件拒绝分别留证。浏览器至少证明标签持久回读、订单→商品关联、CSV 与 XLSX 导入确认及新 SKU 查询、异常行回滚和跨租户拒绝；fixture 测试不代签真实 API 链。

可复用 V40 冻结合同、seed 内容及已核历史事实，代码不变可做精确 source/blob 对照；V41 新写入模型和迁移会改变验证边界，旧 745 PG、4316 offline（以及更早 719/3684）都不是 V41 数量或通过证据。实际节点数靠最终源码 collect；旧工程/浏览器结果仍绑定原 SHA，不迁移签名。新锁/依赖变化需重新登记工具链与扫描/漏洞检查范围，CSV/XLSX 引入依赖需评估有界读取能力。

每卡交付 >=3 个可操作演示步骤、source/tree、实际命令/native exit/count/elapsed、原始失败、未跑项、资源生命周期和 cleanup。最终全量 source map、目录/索引/全历史扫描及文档检查绑定最后冻结源码；原 V40 031 扫描失败、446 失败提交及最终编排 wrapper exit 1 的备注均保持，不回填。Hosted/amd64、main/远端写、真实外部调用及生产不在本次授权；人工可用性/财务语义评价与自动断言分列。

## 7. 首轮结论

完整六卡可以按上述依赖准备；暂无必须转用户逐项选择的常规技术决策。实施前最高风险是有效数据视图与快照、业务写/导入的当前授权及锁序、既有控制 schema 与新业务能力的边界、文件解析有界性。作者先冻结对应增量合同和精确源码，Reviewer 再逐项核收，当前不能以本计划签实现安全或 Full 通过。

本计划只做源文件阅读和文档差异检查；未执行业务测试、collect、扫描、PG/API/Web、网络或旧资源操作。
