# V4-1 WEB 实施方案（待接口与 owner 冻结）

状态：PROPOSED；本文件不是代码开工或验收回执。基线为 `1730194028a01ddea0bbc573774d740ea4a29d55` / tree `5f2a92dffb49ef21682077e89459c85db55b668d`。用户已授权 V4-1，Root 将分别冻结接口、资源与路径后释放具体代码；本方案只提出 WEB 切片。资料来源：开发包 `03_delivery/TASK_CARDS.md` 的 V41-01—06、`01_product/SCOPE_AND_PAGES.md`、V4.5 Standalone 原型，以及仓库 `docs/v4/baseline/` 的 UI、API、domain、permission 四合同和 `reviews/PAGE_ROUTE_MATRIX.json`。基线文档中早期 NOT_STARTED 是历史状态；当前 V4-0 已有实现以实际源码和 Root 验收为准。

## 现状与原则

- `frontend/app/v4/[[...path]]/page.tsx` 当前只接受 `/v4`、`/v4/demo`、`/v4/settings/demo`，均由 `components/v4/demo.tsx` 承载；新增路径目前不存在。`v4-client.ts` 面向 `/api/v4/demo` 的现有会话信封和严格 schema；不能假定已支持 V41 业务 API。
- 旧 `/tasks`、`/approvals`、`/replenishment-items`、`/daily-reports`、`/inquiries`、`/copy` 等是各自受配置和权限约束的现有 M3 功能，不等于同名 V4 新页面已完成。Root/后端冻结桥接方式前，不直接把旧身份、DTO 或数据拼入新页面；不得让 V4 demo cookie 绕过旧 session/epoch 保护。
- 原型可参考深色侧栏、浅色工作区、信息层次、KPI 网格、趋势区、局部表格滚动、详情抽屉和移动重排；其浏览器模拟数据、角色、密码、规则、轨迹及回答不是服务端事实。不要嵌入原型 HTML、伪造指标或把规则结果叫作真实模型推理。
- 14 个导航分类是信息架构，不是 66 个业务页完成。根据服务端可见能力/权限展示可操作项；未开放模块呈现明确分类、范围及「尚未开放」，不伪造按钮或数据。导航隐藏不是授权；深链同样经服务端校验。

## 14 个分类及可达范围

下表 `/v4` 路径均为 route matrix 的**候选**，不是已实现或已核准 API；最终保留字、权限、路由与能力由 Root 和 API owner 冻结。可达分类应有可理解的内容和状态，不能把所有模块套成相同空白卡。

| 分类 | 候选入口 | 本阶段意图 / 限制 |
|---|---|---|
| 经营驾驶舱 | `/v4/dashboard` | 同源 KPI、趋势、规则洞察、异常/待办与授权钻取；依赖 V41-02。 |
| AI 智能工作台 | `/v4/ai` | 尚未开放的能力说明；侧栏提供真实上下文与只读快捷入口，模型未启用明确显示。多轮工作台留后续卡。 |
| 经营分析中心 | `/v4/analytics` | 分类及与现有日报的关系说明；完整报表留 V4-2，不以旧日报充当新分析。 |
| 商品中心 | `/v4/products` | V41-04/05 的列表、详情、标签、导入；受当前店授权及 API 合同约束。 |
| 订单中心 | `/v4/orders` | 列表、授权详情、过滤导出与演示履约；不向真实 Woo 写。 |
| 库存中心 | `/v4/inventory` | 分类/现有补货能力边界；风险计算和流水留 V4-2。 |
| 采购供应商 | `/v4/suppliers`、`/v4/procurement/requests` | 分类；报价、采购、审批和到货不冒充已开放。 |
| 客户与售后 | `/v4/customers` | 分类；客户画像/工单留 V4-3。 |
| 智能客服 | `/v4/support/inbox` | 分类；无真实客户收件和外发能力。 |
| 营销中心 | `/v4/marketing` | 分类；旧内部文案/审核为相关能力，不等于营销活动可发布。 |
| 自动化中心 | `/v4/automations` | 分类；旧日报调度和 Fake 投递不等于通用规则引擎。 |
| 知识中心 | `/v4/knowledge` | 分类；旧引用与合成检索不等于新上传或完整知识管理。 |
| 审批与任务 | `/v4/work/todos` | 分类；旧工作项/审批是独立真实入口，是否安全桥接由后端合同决定。 |
| 数据与系统管理 | `/v4/settings/demo`；候选 `/v4/settings/data-quality` | 保留现有演示设置；数据质量/映射依赖 V41-06，外部连接及模型配置不因导航开放。 |

驾驶舱钻取候选 `/v4/dashboard/drilldown`，商品详情候选 `/v4/products/:productId` 与导入 `/v4/products/import`，订单详情候选 `/v4/orders/:orderId`。`import`、`variants`、`categories`、`anomalies`、`fulfillment-demo` 等静态段优先于动态 ID，ID 语法、404 和对象归属由最终合同确定；未知路由保持明确 404。刷新、返回、深链需真实重取当前身份与授权，禁止从 URL 推导角色。

## 交互规格与后端依赖

**V41-01 Shell。** 宽屏侧栏分组、主区域面包屑、当前演示/店铺/身份及入口；1280 宽度收缩导航，390 切换到可关闭移动菜单。保留 V4-0 欢迎、persona、reset/logout 和原控制回执。不可用分类以文本说明当前阶段和下一步，当前授权范围未知时不显示敏感数量。Shell 状态与业务页共用已核对的当前 session，不能另造权限缓存。

**V41-02/03 Dashboard。** 后端冻结按 tenant/shop/时间范围查询的指标与趋势、钻取/异常/待办、服务端权限和 source/fixture version、snapshot、时区/币种及完整性状态；明确分页、时间边界、空集、缺失、刷新和失败语义。前端先选受权店与周期，再同时展示口径/来源/更新时间：KPI 数值和趋势图来自同一合同快照；指标缺失显示未知而非零，未提供成本不计算毛利，不合并不同币种。趋势提供表格/文本替代；规则洞察、异常和待办须来自受权数据及明确规则，标示「规则」而非 AI，引用不可访问目标显示受限。切店/期间先清旧图表与选择，结果必须匹配当前 context 与最新请求。

**全局 Copilot 容器。** 可展开/收起的侧栏仅展示服务端认可的当前店、页面、选中对象和可访问只读快捷入口；禁泄漏隐藏对象或原请求内容。模型未启用时清晰呈现不可用原因，不模拟聊天回复、token、工具调用、轨迹或进度；不启动 provider。小屏以模态抽屉承载并按 Esc 关闭/焦点回归。后续真正聊天、多轮与 Agent 另属 V4-4 合同。

**V41-04/05 商品与订单。** 等待 API owner 固定列表/详情/过滤/排序/分页、资源版本、source_ref、店铺/tenant 权限和错误协议；标签编辑与演示履约须提供允许操作、服务端写权限、对象版本、确认、幂等回执和只读恢复。商品表显示真实列、来源及筛选结果；打开详情抽屉可见 SKU/变体、授权字段和版本，编辑先预览再确认、成功重读列表及详情。订单表提供状态/时间筛选、来源和分页，详情关联同源商品及状态时间线；履约仅显式允许的演示状态转换。读取/导出/编辑/履约分别由后端授权，跨店统一安全拒绝；导出格式、字段范围、大小及防公式注入由 API 合同确定。无授权、无数据、过滤无结果、服务不可用与未知提交状态区分；UNKNOWN 保留原操作上下文，只查原回执，不自动再 POST 或推断回滚。

**V41-06 CSV/XLSX。** 联合 SCHEMA/API+QA 先冻结上传的文件类型、字节/行列上限、字符编码、解析隔离、公式/宏处理、预览版本、字段映射/必填、逐行错误和权限；UI 提供选择文件→受限上传→服务端预览→映射→质量错误/可修正提示→确认→原子导入回执→按当前店查询新 SKU。不可在浏览器伪造成功或用部分成功掩盖回滚；映射/文件改变使旧预览失效。容量、取消、失败、超时、原键查询、跨店/撤权均有明确状态。不得执行公式或宏，不假设 XLSX 支持已落地；以实际 API 安全合同为准。

**需要 Root/后端冻结的接口，而非本方案自定路径：** session/identity 复用边界；各 query/command 方法与版本化 OpenAPI/schema；响应上下文、CSRF、epoch/generation、错误/UNKNOWN 和只读回执；source/时间/币种/Decimal 序列化与数据完整性；权限矩阵及可见能力；商品/订单对象与写入 CAS；上传/预览/确认/导出协议和资源上限。新 API 命名、页面最终路径、状态码和 DTO 均待独立批准，不能让 UI 猜测后固定。

## 拟议文件与单 owner

以下文件是精确的**拟议路径**，目前除已标注的 V4-0 文件外不存在，必须经 Root 冻结路径和接口后再创建/修改：

| 路径 | 拟议职责 / 依赖 |
|---|---|
| 现有 `frontend/app/v4/[[...path]]/page.tsx` | 单入口路由分派、静态保留段优先、既有三入口回归；若 Root 选独立 App Router 文件则先调整所有权，不并行改同一入口。 |
| 现有 `frontend/components/v4/demo.tsx`、`demo.module.css` | 在不削弱 session 保护下接入 Shell，或仅提取现有内容到子组件；必须保留已有行为及测试。 |
| 新 `frontend/components/v4/shell.tsx`、`shell.module.css`、`navigation.tsx`、`copilot-panel.tsx` | 响应式框架、导航/能力状态、只读上下文侧栏。 |
| 新 `frontend/components/v4/dashboard.tsx`、`dashboard.module.css` | V41-03 真实指标、趋势、来源/状态与钻取。 |
| 新 `frontend/components/v4/products.tsx`、`orders.tsx`、`resource-drawer.tsx`、`catalog.module.css` | V41-05 列表、详情和受控操作；组件不掌握授权事实。 |
| 新 `frontend/components/v4/import-flow.tsx`、`import-flow.module.css` | V41-06 的真实预览、映射、确认与回执 UI，依赖 API/QA 的冻结协议。 |
| 新 `frontend/lib/v41-client.ts`、`v41-context.ts`、`v41-schema.json`、`v41-generate-schema.mjs` | 仅消费批准的业务 OpenAPI 和 context/请求边界；先决定生成资产与单 owner，禁止自行发明 schema。现有 `v4-client.ts`/`v4-schema.json` 只有 Root 明确释放必要接线才修改。 |
| 新 `frontend/v41-tests/shell.spec.ts`、`dashboard.spec.ts`、`catalog.spec.ts`、`import.spec.ts`、`lifecycle.live.ts` 和对应专属 Playwright 配置 | fixture、严格 DTO/状态/响应式与独立新 owned 真 API/PG/Web；QA 不并写 WEB 文件。 |

WEB 独占已释放的 `frontend/app/v4/**`、`frontend/components/v4/**`、`frontend/lib/v41-*` 和 `frontend/v41-tests/**`。既有 `frontend/v4-tests/**`、旧业务 UI、根 lock、全局 layout、backend、`api.py`、共享测试和 CI 默认不改；必要接线由 Root 精确释放。上述新增配置的准确位置也须 Root 冻结。

## 切片顺序、并行与首个可运行结果

1. **合同与路径冻结（Root/API，WEB只读参与）：** V41-01 的路由、服务端可见能力与 shell session 适配；V41-02 Dashboard 口径/响应；V41-04 商品/订单授权及写入；V41-06 导入协议。冻结前 WEB 不写业务代码。
2. **最小首片（V41-01，冻结后）：** 在真实 V4-0 session 上接入 responsive Shell、14 分类目录与现有三入口，保留 reset/logout 和失效处理。当前业务未授权/未开放项真实显示状态，不显示伪数；仅证明导航与既有 demo 生命周期，不签 KPI/商品/导入已完成。用户可在新 owned 窗口进入、切店/角色、浏览分类并退出；独立复核原 V4-0 生命周期。
3. **Dashboard/Copilot（V41-03）：** Shell 和 V41-02 合同与 API 冻结后接入；先真实单店/时间窗口 KPI、来源与状态，再趋势/异常/授权钻取及只读 Copilot。逐片提交、独审、同源实际验证；模型关闭是实际状态，不制作模拟回答。
4. **商品/订单（V41-05）：** V41-04 冻结后按列表→详情→授权标签/履约→筛选分页导出推进；与 Dashboard 的组件文件可并行，但唯一 WEB owner 串行落共享 Shell/client。跨店与写入竞争先有 API/PG 证明再浏览器签收。
5. **导入（V41-06）：** API/QA 冻结解析和事务语义后接入；真实上传→预览→映射→错误→确认→按店读回新 SKU，配异常/超限/原子回滚。不得以纯前端文件解析替代后端收口。

并行边界：API owner 可并行定义各域与测试，QA 可在独立测试路径准备验收；WEB 可在批准的独占组件内做互不依赖的切片。session、schema 生成、路由入口、公共样式与共享 DTO 只有单 owner 串行修改；依赖未冻结时只做文档/只读设计，不创建 mock 当最终实现。

## 验证和交付门槛

- 继承 V4-0：创建/切角色/切店/reset/logout、401/403/撤权/到期清屏、未知原操作只读核对；控制操作开始先清敏感数据并禁止新写；hidden/offline 即遮蔽，恢复 online/focus/visible 先 revalidate；跨标签仅广播无身份的失效信号，丢消息靠当前校验收敛。所有异步响应绑定 tenant/principal/shop/epoch/generation 和请求序号，迟到结果不能覆盖新上下文；服务端仍是授权权威。
- 交互与可访问：1440、1280、390；独立真实浏览器原生 200%（不是 CSS/viewport 冒充），移动菜单与抽屉焦点约束、Tab、Esc、关闭后焦点恢复、可见焦点、状态文字/aria-live 和 reduced-motion。表格仅局部横滚；图表有可读文本替代；测试真实已登录和空/错误/受限状态。
- fixture/纯测试验证路由、schema、加载/空/错误/UNKNOWN、竞争与伪响应拒绝；逐项标记合成来源，不能代签业务或权限。新 owned API/PG/Web 执行同源真实浏览器：两店/多 tenant、越权 404、切换/重置/撤权、KPI 口径、详情编辑读回、分页/导出、导入新 SKU 和失败原子性；后端 PG 并发/幂等/旧 Woo 零写另由 API/QA 负责并交回执。
- 每片提供实际 SHA/tree、操作步骤、测试命令及 exit/count、截图来源/人工判断、失败/UNKNOWN、资源停止与 cleanup；审查通过后 Root 集成。旧 M3、V4-0 回归和最终完整 Gate 按 Root 冻结源码实际执行，不能用 fixture 或历史成功代签。Hosted、真实 provider、外部发送和发布需各自授权/证据。
