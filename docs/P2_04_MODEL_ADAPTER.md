# P2-04 离线模型说明组件

2026-10-10（Asia/Shanghai），B 独立 Worktree `0c5a`，分支 `codex/phase2-model-explanation`，基线 `eb537e552456313100065551bc7f0b045fd08257`，开工 HEAD 精确一致且 clean。授权以 [Issue29 并行冻结合同](https://github.com/aning0922/commerceops-agent/issues/29#issuecomment-6093683362) 为准；A 独占 P203/迁移/业务集成，Root 唯一总控。本组件不表示 P204 或 Phase2 完成。

Root 通过运行元数据核实本顶层为 `gpt-6-astra/high`，不是推荐但未运行的 Sol。初始 6–9 有效小时估计已被 Root 收缩为首批 3–4 有效小时，计入原 P204 与 Stage 30–40h/总 300h；人工 H/L 仍未报告。开工工具时间 04:18:53 UTC（12:18:53 Asia/Shanghai），Agent 墙钟与机器等待另记，不能折算人工工时；D1/10-10 至 11-08 不重置。

## 交付范围

仅新增本包 application/adapters/model_explanation 子目录、`tests/test_model_explanation.py`、独立手写正文金标、本说明与非秘密 env example。未改任何父 package、共享 DTO、业务规则、旧 fixtures/goldens/manifest、migration、Worker/Graph/API、权限、依赖锁、CI/scanner、AGENTS/STATUS/ROADMAP。原共享 DTO 只读；数字展示只读复用已审 `domain.inventory_rules.display_fraction`，未改其实现。

模型仅选择已有 SKU 对应原因的说明顺序。最终中文、数字、状态提示由确定性模板生成；没有自由文本进入业务事实，没有计算风险/Q、修改 assumptions/quality/资格或生成执行字段。主动限制能力是本组件的安全边界，不代表完成意图路由/参数澄清/五意图或泛化评测。

## 冻结接口

```python
from commerceops.application.model_explanation import (
    ModelExplanationService,
    ExplanationResult,
    ReferenceIds,
)


async def explain(
    report: InventoryReport,
    *,
    reference_ids: ReferenceIds | None = None,
) -> ExplanationResult: ...


service = ModelExplanationService(provider=None)
result = await service.explain(report)
```

输入必须为已审 `inventory-analysis-v1 / canonical-facts-v1` 的 `InventoryReport`。入口保留原类型递归重验模型（包括 model_copy 可能绕过校验的值），再验证原 facts_hash；有效报告的原哈希原样保留，报告对象及全部字段不修改。不能用模型反馈回写 metrics/金额/规则事实。重复 SKU 拒绝。

`ReferenceIds(snapshot_id, report_id)` 仅承载调用方已核验的引用，字符限制为 ASCII 字母/数字与 `_.:/-`、1–128 长度。组件没有数据库查询，不证明引用属于该 report 或该用户。缺省 `binding_mode=standalone`；传入合法标识仅为 `caller_references`，不是已完成 P203 持久绑定，A 必须验证身份/归属/hash 后传入。

`ExplanationResult` 包含 `facts_hash/narrative_mode/binding_mode/summary/lines/reference_ids/metadata`。每行包含 `sku_key/reason/text/facts_hash/reference_ids`。`narrative_mode=template` 或 `model_selected`；后者只代表已通过输出结构校验的选择，是否真实 provider 必须同时检查 `metadata.evidence_mode`。

`metadata` 是本包 `ModelReply`，包括 `error_code/evidence_mode/provider/requested_model/returned_model/prompt_version/request_id/usage/latency_ms/pricing_version/cost_estimate/stop_required`；外层 service 总会清空 `content`，不保留模型原始文本。未请求时 `evidence_mode=not_used`；MockTransport 请求为 `offline_stub`；仅真实 transport 进入 send 后才为 `actual_provider`，该标签不表示请求成功。未知 usage/cost 保留 null，不当作零。

错误分类固定：缺 provider/admission、输入报告/引用失败、必须模板、预算/计数未验证、预留失败、timeout、429、5xx、认证/余额/其他 HTTP 错误、transport、JSON/schema、截断、不安全说明、输出超限、usage/cost 未知、模型不符、响应过大。接口不返回原 exception/body/header；没有自身 logging/print。生产调用方应关闭第三方 httpcore 的 wire DEBUG 日志，不能开启 HTTP header/body 调试日志来收集真实证据。

## Prompt、引用与确定性模板

固定 `prompt_version=inventory-explanation-v1`，只有 system/user 两条消息。user 只含 SKU 标识和确定性允许的原因，不发送商品名称/标签、任意来源文本、参考业务 ID、权限或客户指令。响应固定：

```json
{"highlights":[{"sku_key":"sku/demo/a/p","reason":"risk","source":"facts"}]}
```

每个输入 SKU 必须恰好一次，原因必须与该 SKU 既有风险/阻断匹配、source 必须为 facts；拒绝重复/缺漏/外来 SKU、额外字段、自由文本、数值、tenant/role/approved/工具/虚构执行。拒 JSON duplicate keys、NaN、错误根类型。模型可重排，不能改事实。最终来源链接由原 facts_hash 与调用方引用构建，不接受模型生成 URL。

模板使用既有精确 D 经六位 HALF_EVEN formatter 渲染，整数直接来自既有 A/inbound/suggested_units；不信任排除在 hash 外的 display 文本，防止展示字段注入。模板不展示或改写其他指标，也不暗示未显示指标消失。仅说明已有分析、没有采购/库存修改/审批动作。

空报告、不完整/需复核/超范围、未知在途/假设草案直接模板且不发送；在途 null 显示未知，硬阻断不能由说明解除。模板保留完整事实对象在调用方，不创建替代业务报告/伪 API。模型异常仍有确定性模板；不是空结果冒充成功。

## DeepSeek 协议与预算交接

构造入口为 `DeepSeekAdapter(api_key: SecretStr, token_counter=None, admission=None, pricing=None, offline_transport=None, base_url=..., model=...)`。不自动读 env/config/file，不提供真实 key 加载 CLI。URL 严格等于 `https://api.deepseek.com`，model 严格等于 `deepseek-flash`；其他协议、host、userinfo、路径/查询、模型拒绝。路径固定 `/chat/completions`。

发送固定 `thinking={"type":"disabled"}`、`response_format={"type":"json_object"}`、`stream=false`、`max_tokens=800`，不传 tools，没有重试/redirect/代理环境继承/自动换模型。HTTP transport retries=0，从 `complete()` 入口冻结 `monotonic()+20` 截止；token计数、请求构造、admission、连接、响应头与完整 body 读取共用预算。计数后、预留前、发送前及body处理均检查剩余时间；keepalive 空行不续期。响应含压缩编码拒绝；读取总上限 65536 bytes；HTTP 非200不读取错误 body。取消正常传播，不冒称请求未发生。

`TokenCounter.count(messages: tuple[Message, ...], *, model: str) -> TokenCount` 必须由 A 注入实际核验的 tokenizer（含完整 chat template、角色/特殊 token/生成前缀），返回 `input_tokens/model/tokenizer_version/evidence`。只接受整数 1–8000；真实 transport 必须 `evidence=verified_tokenizer`。离线计数器明确 `offline_stub`，不能用于真实发送。**本批未锁定当前 alias 对应的 tokenizer，不提供任何字符÷4或无依据字节上界；缺正确计数时真实发送保持拒绝。A 的实际计数实现与核验是待集成 Gate，不能只改 evidence 标签。** 响应 usage 若超预留/8000 input/800 output，同样 stop，不重试。

`Admission.reserve(request: BudgetRequest) -> Reservation | None` 必须在 send 前由 A 的持久账本执行一次原子预留：身份/审批与报告归属检查、阶段最多10次、每次 input8000/output800、总 USD0.10，以及对应峰值成本上界。BudgetRequest 带本次 UUID、准确请求 body SHA256、facts_hash、model/prompt、tokenizer、input count/output cap、pricing version/cost upper bound、offline/actual evidence。返回 `Reservation(request_id, request_hash)` 必须绑定同一请求；缺 admission、返回拒绝、绑定不符或异常都不发送。

预留不是本组件授权。B 不提供 PG/内存累计实现，不称跨重启预算通过；测试 LedgerStub 仅离线。A 在预留时就必须占用次数与上界，按结果 request_id 单次结算；取消/崩溃/超时/未知usage/未知cost/预留结果未知不得自动释放或记零，先停止后由 Root 查账。`stop_required=true` 必须停止本阶段后续发送；B 没有后续请求循环。HTTP失败/网络错误无法证明未计费，保守 stop。失败返回的数据足够关联预留，不替代持久事务。

`Pricing(version, input_per_million: Decimal, output_per_million: Decimal)` 由调用方用当前官方价格核验后注入，字段只接受有限正数；未知拒真实发送。估算按未缓存 input 上界，不利用 cache hit 降低预留；已知 usage 的 estimate 为 USD Decimal，不是账单实收。测试价格 0.30/1.20 每百万 token、8000/800 峰值每次0.00336，十次0.0336低于授权0.10；真实调用前仍必须再核价。响应 model 仅接受请求 alias，否则固定 MODEL_MISMATCH、returned_model=null、stop，任意返回字符串不回显；alias 不等于不可变权重 snapshot。

## 官方文档核对与证据层级

2026-10-10 只读核对官方文档；初次页面直接打开超时，搜索索引/后续官方页读取成功。未调用模型 API、未网络探测 provider，未读取或复制 A 的 key/config。只读文档事实：

- [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：支持上述 model、thinking disabled、max_tokens、JSON object 与 usage 字段。JSON 语法保证不是本组件 schema/语义保证，仍本地校验。
- [JSON Output](https://api-docs.deepseek.com/guides/json_mode/)：prompt 需含 json 与格式示例；可能返回空内容，输出上限可能导致截断。本包空内容/截断直接模板，不自动重试。
- [Thinking](https://api-docs.deepseek.com/guides/thinking_mode/)：默认思考模式需显式关闭；本包不接收非空 reasoning/tool calls。
- [Rate Limit/Keep-Alive](https://api-docs.deepseek.com/quick_start/rate_limit/)：非流式可能持续空行，故本包绝对 deadline 独立于每次 socket read timeout。
- [错误码](https://api-docs.deepseek.com/quick_start/error_codes/)：400/401/402/422/429/500/503分类；文档建议重试/切服务不覆盖本阶段禁止重试/切模型合同。
- [价格/型号](https://api-docs.deepseek.com/quick_start/pricing/)：deepseek-flash 是可变化 alias，当前对应 V4.1 Flash；生产安装、实际returned model/usage/latency/cost必须在最终集成另验。

文档核对、源码实现、离线实际运行和真实 provider 四层证据分别记录，不能互相替代。

## 实际验证

机器基线 Darwin arm64、Python3.12.13、uv0.11.25；项目内 `uv sync --frozen` 与 `python -m scripts.bootstrap_tools`（Node24.21.0/Gitleaks8.30.1含下载hash）实际通过，未改全局环境。httpx0.28.1 当前只是已锁 dev 依赖；运行依赖 promotion 由 A 拥有，`--no-dev` 生产安装未验证且 pending，不能声称可部署。

专项命令：

```sh
uv run --frozen ruff check backend/src/commerceops/application/model_explanation backend/src/commerceops/adapters/model_explanation tests/test_model_explanation.py
uv run --frozen ruff format --check backend/src/commerceops/application/model_explanation backend/src/commerceops/adapters/model_explanation tests/test_model_explanation.py
uv run --frozen mypy backend/src/commerceops/application/model_explanation backend/src/commerceops/adapters/model_explanation tests/test_model_explanation.py
uv run --frozen pytest tests/test_model_explanation.py -q --tb=short
uv run --frozen python -m scripts.check
uv run --frozen python -m scripts.scan_secrets
```

专项覆盖有效引用/纸面正文、全部冻结场景事实与hash不变、未知在途/不完整/空数据、注入/执行/数字/auth/外来SKU拒绝、timeout/429/5xx/JSON/schema/截断/budget/admission/未知cost、实际20秒keepalive deadline、取消预留保留、无重试/redirect、不安全URL/日志回显。

开发失败保留：初次lint/typecheck有导出/类型收窄及格式错误，已修正；第一轮专项34 failed/33 passed（20.52s），定位 MockTransport 的预载响应再次 aiter_raw 导致 StreamConsumed，改为限制编码和总长度的 aiter_bytes；第二轮1 failed/66 passed（20.21s），仅手写金标省略了既有formatter六位小数，按已审展示合同补齐为10.000000，未改原fixture/golden。最终专项/全套/敏感扫描结果及SHA/CI在本说明后续记录与PR交付回执。

本批实际 provider 请求0、source_mode=mock/model_mode=offline_stub（无发送路径另为not_used）、PG/Feishu/Woo/业务集成 not_run；没有借用 A 的未提交工作目录。自动 CI 若包含 A 移动 base 的代码，必须单列实际 checkout parents/tree 及组合范围，不能外推 A Gate 或本包独立实测。

## 待集成与冻结交付

待 A/Root：P203稳定Gate、共享接口核对、正确 tokenizer 计数与版本绑定、PG持久预留/结算与身份授权、httpx运行依赖、reference绑定、跨模块真实PG、最终代码独审、有限真实DeepSeek说明及受控失败回退。真实模型总预算不重置。独立Reviewer审冻结SHA由Root协调，自检与CI不替代独审。

组件PR base为 `codex/phase2-inventory`，不merge/关闭Issue29；A稳定后按Root协调普通merge同步，不rebase/reset/force。最终Phase2主PR仍PR30，main合并授权由Root另核。本交付不承诺原Phase的T3/库存/自然网络故障/wire/p95/长期幂等等未经实跑事项。

最终本地实跑：专项 **71 passed（20.39s）**；原样完整 `scripts.check` **passed**，723 offline passed / 79 deselected（79.33s），两条既有 lark SDK deprecation warnings 保留；104源文件 strict mypy、159文件format、52份Markdown、锁/工具链/前后端漏洞门禁通过，Python audit90包零已知漏洞。首次完整门禁因本新文档 Python fenced 示例格式失败，修正后上述完整重跑成功，未修改check/豁免。没有本地PG/模型/平台实测，79 deselected不能写成通过。

本地最后暂存后的当前/index/完整可达history扫描与diff边界、冻结SHA/tree及实际CI见组件PR交付回执；文档/机器结果不替代Root独审。Agent开工至首批PR交付墙钟单列在PR，包含机器等待；有效人工小时仍not_reported。

## 首轮独审绝对截止修复

Root转达独立Reviewer在冻结8f5fb9a9发现P2阻断：同步counter先消耗20.2秒，旧timeout在其后启动，仍会reserve/send。原71专项/成功CI未覆盖计数前置耗时，不能据此忽略缺陷。

最小修复仅adapter、专属tests和本说明：入口固定monotonic截止；纯计数以`asyncio.to_thread`运行并仅等待剩余时间，超时/取消不进入admission或HTTP。线程只有messages/model，不传credential/admission/transport；迟到结果丢弃，永不继续send。线程池工作数由Python默认executor限定，没有新增executor/平台/调度器。Python不能强制中断已运行线程，故注入counter必须自身有界、无网络/副作用且不长期阻塞GIL；调用方收到stop_required必须停止后续请求，不能无限提交计数。`asyncio.run`进程级收尾可能等待后台线程，不能将服务await的截止外推为进程强制退出时限。

请求JSON/hash构造的同步耗时也扣在入口截止内，耗尽后TIMEOUT/零reserve/零send；admission/HTTP使用剩余timeout，并在发送前再次检查，阻塞式caller在恢复控制后也不得过期send。读取/解析同步结束检查同一截止，不新增重试；未知usage/cost、预留未知、取消不释放预算的原合同保持。取消HTTP测试改为等待确实进入Mock send后取消，避免线程启动调度使其意外变成取消计数测试。

四项新增定向回归先实际4 failed（1.36s），修复后4 passed（0.95s）：计数消耗0.25s/截止0.05s时服务await按时返回且后台结束后仍零预留/发送；计数0.2s/总截止0.35s下keepalive仅剩余时间；请求hash构造超时；admission同步耗尽预算不得send。这些缩短时间的定向用例与原真实20秒keepalive测试并存，不伪称新慢计数用例实等20.2秒。初次strict mypy发现测试访问adapter未显式导出的hashlib，已改为测试自身导入标准库。最终专项、全离线、三层扫描与新SHA/CI在同PR修复回执记录；本轮不merge A、不读key、不真实调用。

首轮修复最终本地结果：专项 **75 passed（21.21s）**；原样完整 `scripts.check` **passed**，**727 offline passed / 79 deselected（69.07s）**，两条既有SDK warnings；104文件strict mypy、159文件format、52份Markdown、锁/工具链/前后端漏洞检查均通过，Python audit90包零已知漏洞。原8f5fb9a9及其CI仅历史证据；新冻结修复须新CI与原Reviewer复审，尚不宣称P2阻断已由独审解除。只改本包三个文件，parent保持8f5fb9a9，未同步A；本地PG/真实模型仍not_run。
