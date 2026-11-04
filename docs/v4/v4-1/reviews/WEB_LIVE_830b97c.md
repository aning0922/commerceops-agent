# 真实业务 browser 首候选独立审查

2026-11-04（台北）。结论：`HOLD_QUERY_EVIDENCE_P2 / SHARED_INTEGRATION_PENDING`。精确WEB source `830b97c5b52558a2f6f49f4bd0afb1406da3481d`，tree `c46ab20d41f64bd8be6b32e6b25af0f33dccd02d`，增量仅 `business.live.spec.ts`与`live-business.fixture.ts`（189新增/2删除）。共享writer按 `95deb3943d53f444bb63e48b5245deb3d19ea3fe` / Root `f12fcffd7d5fd6eaa05eed3ea5a9d946cba82bf9` 精确对象合审，参考已核接口报告53478d4。未读QA/WEB WIP，未运行浏览器、API或其他资源。

## P2-LIVE01：过滤与分页观察没有绑定查询，存在假阳性

`business.live.spec.ts:51-52,129` 使用只匹配origin/path/method的 `waitApi`，没有匹配本次q/cursor。生产页每五秒轮询，旧查询响应可满足等待；过滤后仅要求包含原列表选中的商品，而原未筛选列表本来就包含它。即使API忽略q、始终返回原页，过滤断言仍通过。导入后的SKU搜索也只查“结果中存在该SKU”，未证明筛选生效。分页分支只比snapshot，未核请求cursor/下一页内容，上一页也没有等对应回读，可能把未验证的翻页标为OBSERVED。

最小修复由WEB owner处理：等待具体请求参数（shop、q、cursor、相关filter/sort），用已知唯一SKU或明确金标结果集合检验过滤，不能只用contains；翻页核发送的原cursor、稳定snapshot/revision和页集合，上一页绑定回读后再继续筛选。没有分页样本时保留NOT_AVAILABLE，不造数据/不称分页通过。补能证明忽略q、旧query响应或重复第一页会失败的局部验证；真实运行前再交精确SHA。

## 共享集成依赖：现配置不收集business，末态消费尚未闭合

f12精确 `frontend/v41-e2e/playwright.config.ts`仍为 `testMatch:'shell.live.spec.ts'`。本片虽只有一个固定title `LIVE V41: business reads writes and import roundtrip`，使用现配置指定business文件仍收集0。独立隔离实测 `--list` native1、No tests found、0 tests；没有启动测试或浏览器。需Root由QA owner提供新的精确配置/driver切片，不要求WEB擅改共享文件。

95接口报告已明确只签writer，不签终态消费者。当前f12实际owner export读取 `subjects.private.json`，新writer产物为 `browser-business.subjects.private.jsonl`；本次精确树未见该browser journal到既有subjects/终态collector的消费接线。因此原意图写入与浏览器读回标签可审，不等于最终SQL事实核对已接通。后续共享聚合必须保留原method/path/body/key及ACK/UNKNOWN历史，不把调用方的COMMITTED_READBACK当数据库权威。本项是待Root/QA冻结的集成依赖，不凭读取其WIP补签。

## 已核可保留的行为

- 固定单title；页面动作读取真实配置的loopback API。route仅continue/abort，没有fulfill/fake成功，也没有替换响应body。生产components/app/schema与已核3342968逐对象diff为空，当前使用的页面、按钮、对话框与映射字段语义相符。
- `installBusinessJournal`对四种真实UI POST先核原body和身份计数，再在浏览器读取真实当前session核同scope/operator。等待95 writer的ATTEMPT_STARTED（包含原method/path/body/key）同步返回后才route.continue；writer异常使请求abort，不继续发送。新key由产品产生，本spec没有换key重发或自动重试。
- ACK按原Request对象关联，按schema/context/key分类；响应解析或网络失败保留ACK_UNKNOWN。flush检查异步writer失败和未完成请求；成功写不自动升级READBACK。95的本地body SHA不是server payload_digest，本片没有混称。
- tag两次及履约核原request_key、对象、版本与after_revision资源回读；preview两阶段核原lookup key、job/digest/parent与同文件；confirm核不可变job.version、before/after revision、COMMITTED job、上传来源和新SKU存在后才记COMMITTED_READBACK。回读事件是浏览器观察，仍待共享SQL终态收口。
- session创建响应在UI消费前，通过fetch wrapper将server返回的scope/shops同步登记；随后真实safeSession、creation_key与登记项对应检查。safeSession返回白名单且CSRF脱敏；不过它校验的是投影后DTO，不独立证明原始session信封没有额外字段，原产品strict client保护仍承担原响应检查。
- 新browser context创建第二tenant并核不同tenant/current scope与无原标签；切到CNY店也核scope。这里只验页面/返回列表隔离，不代跨tenant对象越权请求或完整权限负例。未知支付订单的按钮disabled不等于实际server拒绝POST。

## 证据与验证边界

本spec仅1440视口，写 `business.safe.json`计数、来源mode、CSV摘要和分页观察状态；没有screenshot调用。原生200明确NOT_RUN，真实业务截图、390/1280业务布局、完整视觉/键盘/权限验收不能据此核收。原页少于20项时pagination保持NOT_AVAILABLE_IN_CURRENT_PAGE，不能因test title含pagination就标完成。

独立验证采用830精确archive，显式叠加f12的共享writer/config/shell spec（无WIP），固定Node24.21与字节相同lock/只读现有依赖。`tsc --noEmit --incremental false` native0。以专用0700/0600合成manifest仅执行原配置 `--list`：business收集0/native1，验证上述接线缺口；该manifest仅本地收集参数，不是Root资源窗口或运行授权。没有执行spec、网络请求或浏览器。私有日志 `.audit/v4-1/browser-review-830b97c/`保留。

本轮未发现新增P1；P2-LIVE01修复与共享配置/subject消费精确闭合前，不准据此签完整真实business browser Gate。Root独立9e1 HTTP case及其他既有Mock/PG证据与本片分别计账，不转签尚未运行的浏览器。
