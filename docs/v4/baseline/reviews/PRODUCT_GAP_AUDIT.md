# V4 产品差距与实施合同审查（只读）

状态：PLANNING / STATIC REVIEW ONLY，非实施授权或验收。M3 源码证据固定 `952e6246deb01ec763f2541d9f316753987744f3`；以下仓库路径和行号均指该提交，不指当前工作区内容。main `6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265`、远端 Harness `684e645feb1dbe0a27864ca2308fe1afd9fa948d` 为 ROOT 本轮提供的实时观测，本任务未再访问远端；本地 Harness `b9ceaf3…` 不是远端基线。资料包路径为 `/Users/aipuli/Downloads/CommerceOps_V4_Codex_Development_Package/`。包内 README、架构、任务卡仅为规划，不构成 B 开发许可。旧 719 PG / 3684 offline 为历史证据，不是本轮执行或通过。

## 范围核对与结论

`01_product/PRODUCT_SCOPE.json` 实际含 14 模块、66 唯一页面 ID、99 唯一功能 ID、6 条流程；`01_product/PROPOSED_ROUTE_MAP.json` 的 66 个 page ID 与 scope 完全一致。逐项见同目录 `FEATURE_REUSE_MATRIX.json`、`PAGE_ROUTE_MATRIX.json`：52 extension、47 new 是基于本次静态抽查的工程分拣，不是功能完成率。每项有缺口和固定提交的相关源码锚点；`new` 表示未在已检查入口证明可直接复用的同域能力，并非证明全仓不存在；`extension` 只表示相关基础。进一步进入具体实现前应对每项相关域、DTO、权限和测试逐条复核。

页面是逻辑视图，66 条 `/v4/...` 和 permission scope 均 **PROPOSED**，不是已存在路由、有效授权或 66 个独立 Next 页面。包中商品 `:productId` 与 `/variants`、`/categories`、`/import`，客户 `:customerId` 与 `/segments` 等存在静态/动态匹配设计需明确优先级、保留字和参数验证；最终深链/资源所有权需合同冻结。读 scope 不足以授权写、审批、导出或重置。

## 现状：入口与能力边界

- `frontend/app/[[...path]]/page.tsx:21–59` 是 catch-all，live 模式分派给 `LiveConsole`；`:94–109` 是 mock 模式显式路径和 fixture ID 验证，不能由此推断 live 支持任意新 URL。`frontend/components/live-console.tsx:79–107, 239–281, 657–682` 中已有 `/tasks`、`/approvals`、`/replenishment-items`、`/admin/operations`、`/daily-reports`、`/inquiries`、`/copy` 及相关详情；后两者受开关/身份条件限制。V4 路由不应覆盖原路由；新增 catch-all 分支与 shell 必须单 owner 统筹。
- `backend/src/commerceops/entrypoints/daily_http.py:27,45,91–115` 有日报创建、读取、问题和证据接口；`backend/src/commerceops/application/daily/aggregation.py:126 aggregate_daily` 是确定性日报聚合。它们不等于可配置的全经营看板、跨周期分析或六链。
- `backend/src/commerceops/entrypoints/inquiry_http.py:26,62,80,122,126` 是受限只读询单及按原 key/任务读取；`frontend/components/inquiry.tsx:1` 是相关 UI。不能据此声称通用持久多轮助手、跨域写入或模型真实推理均已完成。
- `backend/src/commerceops/adapters/commerce/woocommerce.py:223,292,380,388` 有商品、订单行、退款、库存读取适配原语，并非 V4 商品/订单管理 API、采购或真实写入。`backend/src/commerceops/entrypoints/knowledge_copy_http.py:113,142,197` 与 `application/knowledge_copy/citations.py:44,56` 提供特定内部文案/审核与引用基础，不等于通用知识上传、客服或营销全链。
- `backend/src/commerceops/application/daily/scheduling.py:53 due_at` 和 `infrastructure/daily_delivery.py:44 payload_for` 是日报调度与 Fake 投递基础；通用事件编排、规则运行、外部通知并非由此证明。`infrastructure/web_sessions.py:59 actor_guard, :113 role_scope, :159 SessionStore` 是身份/作用域基础，不是现成 V4 demo tenant、persona 或重置系统。

## 原型与真实实现差距

资料包 `prototype/CommerceOps_AI_V4_5_Standalone.html:524–526` 从 localStorage 装载/保存本地业务数据；`:609` 的采购对象在浏览器数组中变动；`:1128–1131` 本地保存 AI 对话；`:1149,1161` 用合成样本和 `deterministic_demo` 生成答案；`:1167` 用定时器推进轨迹，`:1198` 导出的证据明确标模拟。它们可参考视觉与交互，不可当作 PG 原子事务、模型调用、真实工具执行或 trace 证据。

`:1242,1262–1269,1282–1284` 的登录、密码和角色切换全部为前端模拟，`demo/demo1234` 是公开原型文本；sessionStorage/localStorage 不能作为身份权威。`:1278` 只清本地记录，无法撤销服务端会话或回收已产生的异步写入。建议由服务端创建短期隔离 tenant/session、独立 persona principal、HttpOnly Secure SameSite cookie、CSRF/Origin 校验及租户 epoch；切换、撤权、到期或重置时清敏感 UI 并阻止迟到响应，所有授权在后端按当前对象/店铺再判断。上述为建议合同，尚未实现。

ZIP 仅核过列表（38 文件，包含独立 HTML、JS/CSS、说明及 QA 材料）；其中声明的 83 项浏览器原型检查未由本轮重跑，也不证明服务端鉴权或业务验收。尤其不要复制其固定 trace、密码、客户端角色判定或本地数据作为正式安全机制。实现时需显式显示实际 `model_mode/tool_mode`、来源及 usage 的已知/UNKNOWN，防止用演示动画冒充执行。

## 六链逐项差距（均未被本轮验收）

| 流 | 已核相关原语 | 还需产品/合同与验证 |
|---|---|---|
| A 经营诊断 | 日报聚合及证据/提问入口（daily aggregation:126；daily_http:98–115） | 同店铺同时间口径首页指标→证据→追问→可持久读取报告；限制模型声明与来源版本 |
| B 缺货采购 | 补货工作项/审批 UI（live-console:99–107） | 新供应商报价/MOQ、采购草稿专用审批、同事务分批收货与库存事件；同键回执、拒绝零执行及上限。现有补货项不等于采购订单 |
| C 滞销营销 | 特定内部文案候选、审核、引用（knowledge_copy_http:142,197；citations:44,56） | 商品分析、客群、活动草稿、SOP/商品来源绑定及复盘；不真实发布，审核版本及跨租户隔离 |
| D 客服售后 | 知识引用模型、Woo 订单行读取原语（citations:44；woocommerce:292） | 独立模拟消息/客服会话、授权订单关联、人工确认、幂等转工单；不得真实外发 |
| E 自然语言自动化 | 日报定时与 Fake 投递（scheduling:53；daily_delivery:44） | 自然语言转规则预览与确认、独立规则版本/触发/运行回执；到期去重，UNKNOWN 原键查询不盲重发 |
| F 导入到看板 | 日报聚合与 Woo 来源原语（aggregation:126；woocommerce:223） | CSV/XLSX 安全解析、限制/映射/质量、原子导入与隔离种子、看板与询问绑定；公式/宏不执行 |

## V4-0 首五卡：具体建议边界与门禁

下述路径仅为未来实施时拟定的唯一 owner 提案；前两卡为文档/只读，03–05 依赖正式授权、合同与独立审查。不能并行改共享入口。

| 卡 | 唯一 owner / 精确拟用边界 | UI、API、事件与验证合同 |
|---|---|---|
| V40-01 | ROOT：只读 `AGENTS.md`、`docs/M3_LOCAL_ACCEPTANCE.md`、`docs/M3_LOCAL_DELIVERY.md`、相关 Git 对象与资料包；外置基线报告 | 固定三 HEAD/tree、工作树/PR/CI 由 ROOT 独立核；历史结果与当前 SHA 分列。无业务变更、服务或资源；本报告不替代完整基线审计 |
| V40-02 | ROOT：拟新增 `docs/v4/v4-domain-contract-v1.md`、`docs/v4/v4-public-openapi.json`、`docs/v4/v4-permission-matrix.csv`、`docs/v4/v4-demo-seed-manifest.json` 与 owner/测试计划 | 冻结 UI 状态、资源所有权、读写 scope、错误、event/receipt 和 epoch；核现有 `daily_http.py`、`inquiry_http.py`、`knowledge_copy_http.py` 防重复。上述路径是提议，非本轮创建 |
| V40-03 | SCHEMA/API 唯一 owner：拟新 `backend/src/commerceops/entrypoints/v4_demo_http.py`、`backend/src/commerceops/infrastructure/v4_demo_sessions.py`、新线性迁移及对应 `tests/`；若接入现有 `backend/src/commerceops/entrypoints/api.py` 则仅此 owner 修改 | 提议 `POST /api/v4/demo/sessions`、当前 session、persona 切换、退出/重置接口；session 创建/变更/失效审计事件含 tenant、epoch、actor、时间和结果，不记录 cookie；服务端 principal/CSRF/TTL、并发隔离、撤权与旧 epoch 负例需 PG/API 验证。新接口名称均未冻结 |
| V40-04 | SCHEMA/API 同一 owner：拟新 `backend/src/commerceops/application/v4_demo/`、`backend/src/commerceops/infrastructure/v4_demo_seed.py`、线性新迁移与 `tests/`；不可改旧迁移或真实来源 | 固定版本种子、六场景及 tenant overlay，seed/reset 记录版本、epoch、actor 与结果；同租户重复操作幂等，其他租户不变，失败回滚，旧任务拒绝；需要 owned PG 验证，旧卷/真实 Woo 零写 |
| V40-05 | WEB 为 UI 唯一 owner，QA 独立审查：拟新 `frontend/components/v4-demo-welcome.tsx`、`frontend/lib/v4-demo-client.ts`、`frontend/m3-tests/v4-demo-welcome.spec.ts`；若接入 `frontend/app/[[...path]]/page.tsx` 或 `frontend/components/live-console.tsx`，由 WEB 单人串行修改 | 仅首次欢迎/进入、角色体验、退出/重置 UI 和 auth E2E；调用 03/04 冻结 API，显示真实错误/到期与 tenant 重置结果；1440/390、跨角色/tenant、并发、撤权、失效清屏/迟到响应及原 M3 smoke。**不是重做全站 Shell 或 14 模块导航**；完整 Shell 属 V41-01。任何 trace/UI 事件不冒充服务端审计 |

所有新增文件路径为建议而非存在事实，实际应先冻结目录、唯一 owner、接口及既有测试归属。03/04 共用迁移链、API 根入口或 `tests/` 公共夹具必须串行；05 不得修改后端安全规则或用 mock 冒充 PG/auth E2E。会话切换及 reset 的原子性、撤销语义和异步写屏障应先设计并单独审查；不因 UI 先行引入客户端权威。

## 本轮边界和保留项

只读资料包、ZIP 列表和指定 Git commit 的 tracked 源码；未读取私有 runtime/历史密钥，未启服务、PG、浏览器、模型或平台，未改仓库、提交、push、触发 CI。未做本轮业务测试或独立真人验收。未对每个可能的全仓实现做穷尽证明；矩阵分拣需在实施前二次核查。固定提交的本地验收状态与实际外部 provider、真实数据/飞书、人工质量、Hosted/amd64、main/发布分别记录，不能由本报告升级。
