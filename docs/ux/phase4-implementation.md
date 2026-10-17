# Phase4 / M1 Web 接线交接

## 展示材料与新 clone 的启动边界（2026-10-18，静态增量）

新使用者的人工 Mock 启动路径见 [Compose 说明](../M1_OFFLINE_COMPOSE.md)：使用仓库现有服务、生成本次私有配置和合成账号，再通过实际 Web/API/PG 操作。容器化 Web 不要求为了观看或人工使用而安装 Playwright；memory Mock/B04 预览也不等于这个业务装配。只有需要自动浏览器验收时，才须绑定当前 checkout 的 Node、Playwright、Chromium、schema 与新输入，不能从原机器拷贝旧路径、账号或窗口 DTO。

原 45.80 秒视频及后续 57 秒选帧候选是交付材料，不是启动入口。原 Reviewer 对候选的结论仅为 `PRIVATE_UNPUBLISHED_CANDIDATE_ONLY`，无 P1/P2 不等于获准公开或真人完整连续录屏。本批不重制、不发布、不复制原片或私有 launcher 到公共运行包；原素材、遮罩、失败日志与本地备份保持原样。

公开分步启动说明及证据引用可以完成这层交付，不新增一键完整验收 Gate。私有四场景自动采集器的来源/工具链/handoff 绑定不直接移植给新用户，也不因此要求 A 新建框架；实际人工启动若发现不可替代配置缺陷，再集中报 Root/A。下面字幕、时间轴和截图的通过范围不替代新 clone 验证，也不降低完整 20 行、真实飞书、29 outbox pending/attempts 0 或其他未完 Gate。

## 当前交付材料与演示时间轴工作稿（2026-10-17）

本节整理既有材料及有限机器可见内容核对，待与 A 稳定事实合批审核。真实 F02、原 T6/Base v2 及 c460 四场景有限离线核心复现均已核收。随后已独审 RO140200 证明原两查询在 exact hash、原 actor/chat 谓词下的本地 inbox/carrier 为 0；Root 观察于 2026-10-17 14:16:09.975121Z 的后台日志另见两条近时失败事件，但无正文，原文本关联仍 UNKNOWN，真实查询 Gate 未过。群、必要负向恢复和最终 M1 验收未完成。本节不启动 Web/PG/Compose/浏览器、不重录或修改原媒体、不追加 UX；下方实施批、旧录屏候选和失败原文保留，旧“尚未授权/待验/UNKNOWN”只描述当时证据。

核心运行与私有文件定位见 [Compose 说明](../M1_OFFLINE_COMPOSE.md)，逐 AC 剩余项见 [交付地图](../PHASE4_M1_DELIVERY.md)。统一原始索引为 `runtime/m1-clean-c460-batch-88094ef275/C-complete-native-delivery.safe.json`，SHA256 `cbf5da8b111a6b76f2eb3d0edf2906e882aea9d9fc17158f57ba5f43d9768791`，独审 `a6d70d4d8ad7ee82e5166518d33d997c5e6e0212d3330da952f0e07d1b0babeb`。这些 ignored 私有件不是公开仓库附件，正文不复制其中的身份、业务定位值或服务地址。

### 已有材料及本次核对范围

下列位置相对该私有运行目录。2026-10-17 的只读材料核对确认文件存在且哈希与原索引一致；后续有限 OCR 核对修正了按文件名推断画面内容的风险，没有追加完整逐帧、公开脱敏或真人观察通过结论。

| 材料 | 现有文件 / 尺寸 | 可复用的事实与限制 |
| --- | --- | --- |
| post-login 原片 | `video/page@5f4771dc3df38eef4be2a29cb066b47b.webm`，9,939,594 bytes；SHA256 `ae14edf181346c39800c1940fb8e1b1ca888a829741640276b94d3ea2e39e9ec` | 本次完整 caller 场景的原片，认证输入未录；45.80 秒、1440×1000、25fps、无音轨；仍为自动化 `simulated_web`，未经公开脱敏 QA |
| 名为计划的两张截图 | `evidence/plan20-1.png`、`plan20-2.png`，各 1440×1000 | 有限 OCR 均识别“正在读取当前授权记录”，不作已渲染计划或完整 20 行的画面证据；文件名和程序断言不能替代实际可见内容 |
| 名为完成态的三张截图 | `evidence/completed-2.png`、`completed-3.png`、`completed-4.png`，各 1440×1000 | 前两张识别“正在核实会话/登录运营工作台”，后一张识别“正在读取当前授权记录”；不作可见完成态插页，也不由此推断登录或业务失败 |
| 关闭与恢复后画面 | `evidence/known-closed-v2.png`、`after-restart.png`，各 1440×2944 | 两图均识别“已关闭/当前版本 v2/70 件”；前图可见“等待同步”。均检出 UUID 样式及长十六进制定位文本，未经遮罩不适合公开；长图仍须逐区域人工 QA |
| 运行回执 | 11 POST、84 GET、before/after、writer 后低权快照、cleanup 与 browser stop | 可制作证据引用卡；不把不可见的后台快照伪装成片内真人观察，不公开原始 JSON |
| 390px、缓存与轨迹说明插页 | 仓库已有 `frontend/evidence/p4-c1/cached-final-390.png`、`frontend/evidence/p4-c2/c2-sync-390.png`、`c2-trace-390.png` 及相应 verification | 独立 memory Fake/历史预览，只能明确标注来源作说明，不混成同一次实际 API/PG 或真实 Base 画面 |

### 有限可见内容核对及求职交付判断

仅使用本地文件元数据、ffmpeg 解码和 Vision OCR 白名单核对，不启动页面或浏览器。视频 1,145 帧解码到空设备，退出 0，无解码损坏错误；这只检查媒体可解码，不签内容完整。七张截图分别核固定状态文案；视频在 0.5、4、8、12、16、20、24、28、32、36、40、44 秒取 12 个内存采样，均可解码。只返回标签是否出现及定位文本数量，不回传识别出的账号、UUID、hash 或原始 OCR 文本；原媒体不变。OCR 是有限机器筛查，不是真人评测，也不保证未检出的内容不存在。

- 4 秒、12 秒采样能识别审批事实、20 项及 2,000 数字；44 秒采样能识别 closed/v2/70。部分采样出现完成标签，但还未逐帧配对各 task 和版本，不能据此签发所有步骤的可读时间码。
- 0.5 秒、24 秒采样均识别“正在核实会话/登录运营工作台”；七张截图已有五张明确加载/会话核实文案。应在后续成片中剔除这些图作为业务结果插页的用法，不改动或删除原件。
- 两张长图及多个视频采样检出 UUID 样式/长 hash 定位文本。没有检出完整地址不等于已完成地址、身份或其他秘密的遮罩检查；本批不会公开原图、原帧或 OCR 值。
- 原片无音轨，现有后期说明仅为本文字幕文字稿；没有可直接交付的完整旁白/字幕成片。快速自动操作、加载画面、技术标识及未证明全 20 行可读，会削弱求职展示的自解释性。

本节新增字幕/演示脚本文字已检查，未加入真实账号、Token、实际平台/服务地址、原消息正文或业务 UUID。当前交付仍是文字工作稿，不是 SRT/VTT、已烧录字幕或完成遮罩的成片；原私有测试调用者及过期输入也不随公开包分发。文字检查不能替代原片逐帧脱敏。

**交付判断：可保留为私有技术实证和后续选段来源，当前不适合直接公开为求职主片或“真人完整飞书闭环”演示。** 最小后续是从现有原片定位有效画面、逐帧脱敏、加入持续模式/范围说明及简短叙事，并列明缺镜头；这些工作当前只列待办，不制作新媒体。若现有原片不足以覆盖全量可读性或真实渠道，只保留缺项，另由 Root 裁定，不自动重录、补业务或追加 UX。

查询恢复的字幕须按最新事实表述：“原两条精确绑定请求本地零行；平台两条近时事件投递失败，原文本关联未知；真实回复未验收。”后台首推 app not online 与 retry 1/2/3 FAIL 只适用于已见事件；旧 Gateway 停止与事件时间接近不证明文本相同，不把此前用户发送记录改成未发送。原件及校验值集中于交付地图，不能拿 UI 无正文的日志补出原消息内容。

### 按事件锚点排列的时间轴草稿

下面是待剪辑/配字幕的顺序，**不是已核时间码或新录制脚本**。每段入点、出点、停留时长及可读性均待在原片逐帧确认；不借旧 8–10 分钟候选安排推断本片长度，也不把 82.689954 秒机器运行时间当成媒体时长。`POST n` 指保留的 `post-n.private.json`，只用于私有对照，成片不显示原键或业务标识。

| 顺序 / 事件锚点 | 现有素材 | 拟用字幕文字（工作稿） | 待 QA 或不能声称的内容 |
| --- | --- | --- | --- |
| 1 / 开场来源 | 原片登录后首段；来源/权限原件另证 | “c460；自动 Web；实际 API/PG；MockCommerce；模型未使用。” | 核首帧无认证输入/身份定位值；字幕是材料说明，不伪装产品字段或真人操作 |
| 2 / 拒绝案例，POST 0–1 | 原片候选段及最终快照；`plan20-1.png` 为加载态附件 | “本版本拒绝假设；最终零执行、零内部项。” | 仍须定位完整意见确认和受理的可读原片；加载图不作计划插页，零项以最终快照佐证 |
| 3 / baseline20，POST 2–3 | 原片候选段、POST/GET/快照；两张相关截图均为过渡态 | “完整未知集合显式确认；20 项，共 2,000 件。” | 从首行到末行、null 与有效 0、默认未勾选及全量集合须逐帧核；程序通过不补齐缺镜头 |
| 4 / known70，POST 4–6 | 原片候选段与 v1/v2 决定原件；`completed-3.png` 为会话核实态 | “新 pending 更高版本重新显式决定；本任务完成，70 件。” | 核版本切换及各次确认的实际画面，不将旧 approved/disabled 失败片段剪成本次成功，不把两版本说成重复批准同版本 |
| 5 / 关闭，POST 7 | `known-closed-v2.png`、原 resolve receipt | “关闭内部工作项，保留原因，版本推进至 v2。” | 核 close、原因及版本实际可读；不称采购、入库、库存修改或真实 Base v2 投递 |
| 6 / 同池新周期，POST 8–10 | 原片候选段、两周期计划/执行原件；`completed-4.png` 为加载态 | “同 SKU、同库存池重新分析和审批；新任务、新执行、新内部项。” | 核 B46 草稿、重新确认与实际画面；精确同池/不同对象关联由私有原件证明，不以加载图或公开标识代替 |
| 7 / 正常恢复与原键回读 | `after-restart.png`、11 次原键 GET | “Worker 正常换代、API/Web 重启后，绑定、关闭原因和原回执保持。” | 核重启前后片段边界；后台 GET 完整相等以证据卡说明，不伪装为画面已经展示每个 JSON 字段 |
| 8 / 收尾及未完成项 | 退出前原片；cleanup/低权快照另证 | “核心离线生命周期通过；投影未验证；群与真实查询仍待。” | 清理在浏览器退出后另取证，不声称片内已拍到全部停止过程或真人已核页面 |

### 字幕、脱敏与缺镜头的 QA 清单

- 模式标签贯穿实际来源：`simulated_web / MockCommerce / offline_fake`。本次 29 outbox 仍 pending、attempts 0，未执行 SyncRead/drain；任何字幕都不能将其改称投影核实、平台已发送或真实 Base 完成。
- 公开前逐帧核身份定位值、组织/店铺、任务/计划/审批/执行/内部项、原键、nonce、trace、外部记录定位及服务地址的遮罩；当前只列待办，不产生新脱敏图片或视频，不宣布已安全公开。
- 遮罩不能改变全量 20 行、未知集合、null/0、数量、版本、勾选、禁用原因或业务/同步状态。全量数据在 DTO/程序中通过，与所有行在视频里逐行可读分记；不足则明确 `not_captured/not_verified`。
- 当前原片、旧失败原片、历史只读补证和 memory Fake 插页分别标来源，不剪接成一次真人连续闭环。旧 QA 路径缺证保持原记载，不为本工作稿寻找替身或删除旧资产。
- 真实 F02/T6/Base v2 只引用 Root 已核材料，不要求重做。原查询先由 A 核持久接收；群、负向恢复及当前真实 Web/同步观察的镜头须待对应事实与单独准入，不靠本片填充。
- 入点/出点、字幕与画面一致、完整行可读、长图区域、遮罩覆盖和公开版本的 hash/来源绑定仍待逐帧 QA。若成片确有缺镜头，先报告缺项，不自开服务、补业务写入或追加设计。

本工作稿没有新增产品、回归、浏览器或平台通过结论。原 18 页、owner、D1/D30 和项目 300h 保持；人工 H/L unknown，旧失败和工时不重置。最终字幕和公开成片尚待 QA、Root 核收；当前只交可审文本差异。

## 历史 Web 接线与材料记录（以下原文保留）

## C1：已有缓存与安全新周期

Root依据Issue39/42派发，原M1 Web owner使用新managed WT `/Users/aipuli/.codex/worktrees/phase4-web/commerceops-agent`、分支`codex/phase4-web`，从精确已验main `9d97c19009d932036809ac3e2638bb68f4b7f765`/treea03a6ae起步。原a266/phase3-console/Penpot/私有证据及历史保持，不handoff/reset/复制旧项目或并写。冻结18页、组件/Token/字体和产品route复用，无视觉批次、第二管理体系、新依赖或平台框架。

产品增量仅live-readviews/live-console/p3-present与原CreateTaskDialog最小澄清文案。M04读取既有GET explanation后核outer task/report、inner source_task、snapshot/report/facts_hash及每SKU风险/refs一致性；展示原metadata/provenance/provider/requested/returned_model/prompt/request_id/usage/latency/cost_estimate与全部缓存依据。确定性模板、记录的降级原因、offline_stub、历史actual_provider分记；内层P2 simulated/analysis_only保持。null是“未报告”，真实原值0仍0；估算不等实际账单/实扣，合同未给币种不补猜或换算。没有新GET模型、动态工具链、重算或RAG，NOT_READY不伪造缓存。关闭/卸载或改变绑定后epoch丢弃迟到结果，401照旧清全部身份/缓存。

M05/B36仅在当前task completed、服务端can_start_new_cycle、当前operator创建能力及该店grant齐备时可用；其余具体禁用。M05先显示原记录冻结与新周期影响，B46仅打开无source授权的原CreateTaskDialog；默认参数来自既有新草稿常量，仍须重新明确确认，不复制旧批准/hash/nonce/假设/请求键。店铺限制到当前报告关联授权店。B01仅准备fresh request_key，随后用户明确提交才走既有new_cycle，创建全新P2/P3；不原地修改待审批task/plan，不重执行旧execution。缺L/R/S/非0–365整数/无授权店铺明确澄清reason，无自动补参、续答或业务创建。F02/B47/原地recompute/手工平台重发仍禁用，P4同步schema的sender constfalse未放宽。

## 首包实际离线验证与边界

原27契约+新3（缓存完整引用绑定反例、新周期服务器资格/角色边界、缺参/整数reason）实际30/30（2.9s）。生产typecheck、test-owned预览局部typecheck和Next锁定SWC/webpack单用途bundle编译通过，生产build `OSmd1s56ZnMLLzum2TmS1`通过；bundle只在tests/e2e/web/phase4，输出ignored .audit，不添加产品入口/依赖。该test-owned tsconfig只解析已锁frontend依赖，不改根/产品配置。

6预定义UI场景：缓存metadata/usage/refs与390；模板/离线stub及null；NOT_READY/异refs/撤权；关闭/卸载迟到缓存；M05→参数澄清/新空授权草稿/新key显式提交；待审批/无operator/服务端禁用。首collect的mjs转换与一次错误cwd命令均0test/0resource；前序readonly测试变体/缺默认压缩器/局部模块类型准备错误保留。首次实际6失败于bundle挂载、服务全停；第1mount修复注入测试构建环境常量后1passed/5failed；第2且最后mount修复是在headless私有iframe挂载监听前准备焦点，实际5passed/1failed（16.1s）。剩余仅全页两个B01控件的strict locator，限定当前Dialog后定向1/1（6.0s）；6个unique用例已覆盖，但不称单次6/6。后续生成兼容合后还须最终回归，真实24/PG/native200本首包not_run，不能拿旧成功冒充新调用路径。

所有page实际为headless private context，自有Next3496仅Mock安全壳提供冻结CSS/font，test iframe注入memory P3Client且醒目标记，fake actual_provider仅历史字段样例，不是实际provider。network只有本机GET，memory POST是明确Fake回执，无业务API/PG/Worker/平台/provider；末轮原source仍completed，新request body不含旧source/hash/approval/nonce/假设集合。已有owned-mock helper创建新PID，不复用服务，UID/currentcheckout/亲缘/build核实，fixture结束只停止自己的wrapper/Next。各首失败与tail资源/结果在frontend/evidence/p4-c1；主机3496无listener以工具回执记，不操作用户Chrome、OS键鼠/焦点、旧数据库或secret/env。

从本worktree执行（临时PATH仅项目工具链）：

```sh
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run typecheck
frontend/node_modules/.bin/tsc --noEmit --project tests/e2e/web/phase4/tsconfig.json
COMMERCEOPS_WEB_BATCH=p4-c1 PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run test:contract
PATH="$PWD/.tools/node/bin:$PATH" NEXT_TELEMETRY_DISABLED=1 npm --prefix frontend run build
# 必须从frontend cwd运行；reporter明确写本WT公开evidence/p4-c1
cd frontend
PATH="$PWD/../.tools/node/bin:$PATH" npm exec -- playwright test --config ../tests/e2e/web/phase4/playwright.config.ts
```

现有根frontend CI自动收集新增3契约（通配contracts），但不收集phase4/ui.spec.ts六用例。给A唯一CI owner的最小后build/headless安装增量就是上述最后命令；A保留原24/current-source hash/native200/截止/only-owned全部门槛，增量用例另计，不减少Expect。Web三态真实sync/安全平台trace仅等A审后read DTO/spec，shared内部投影Protocol不能当浏览器API。

原交付8h/P4 50h/D1Oct10/D30Nov8/D13–17及300h保持；人工H/Lnot_reported，Agent墙钟/机器等待另账。原平台/生产/Phase5/新增paid不授权。本包普通提交保存后，Root已明确允许正常merge精确A01+已审Base `545137d014e38ea8ac387139334e92095837dc85`，只做DecisionReceipt可信来源web|feishu的既有生成器同步及严格消费检查；source/扫描/实际最终测试/新PR/独审/精确CI以之后回执为准，不提前标M1通过。

## A01 合后最小兼容与最终回归（2026-10-11）

首包普通提交 `22edbbd8bd15562cb8b7c00a215030e8e14c73bd`/tree `57d15dbc9ac3e0d9ea0faa283c6220121408e2c8` 后，普通无冲突合入上述A545，合并节点 `12fb7f52bdff38e8a25014a64fa9b8d12f2341eb`/tree `e2f58f0de9e36c76fb8ca66cd6e66c1e8b2e850e`，parents为22ed+545；未stash/reset/强推。A精确CI38110473072前端失败的已复现原因是旧生成schema仍将DecisionReceipt.decision_source限定为web。文档与wheel OAS逐字节cmp相同，使用原sync-p3-read-schema与锁定openapi-typescript7.13.0生成，只改变DecisionReceipt来源web→web|feishu（JSON5行/TS4行）。未修改A spec、后端/迁移/共享CI/锁/Compose或阶段文档，不生成猜测的P4浏览器DTO；22操作、session、constfalse及请求白名单保持。

两条新增契约通过真实P3Client/readTransport/verifyReadResponse消费固定内存回执：web与feishu均严格通过；未知/bool来源、缺字段、额外actor、假身份、bool版本、坏hash形状仍WRITE_RESULT_UNKNOWN，不自动重投；客户端附带decision_source/actor/role不进入请求。字段枚举放宽不替代原UI的request_key/task/plan/version/hash/action/假设集合精确匹配，也不赋予Feishu认证或平台执行权限。

合后生产typecheck、局部预览typecheck、22操作schema --check通过；完整契约32/32（3.0s），包含原27+首包3+兼容2，公开结果[contract-results](../../frontend/evidence/p4-c1/contract-results.json)，初批30条结果单独保留。生产build `TO6Hj7zslszJvKlp_AsA4`通过。因合入新source和生成schema，最终只跑一次全六场景：6/6（13.0s），[ui-final](../../frontend/evidence/p4-c1/ui-final.json)及[cached-final-390](../../frontend/evidence/p4-c1/cached-final-390.png)。首轮失败/1+5/5+1与定向1/1原记录继续保留，最终通过不覆盖历史失败。

最终Mock仅headless自有Next PID27554/current UID501/本checkout/3496/build匹配，[resource](../../frontend/evidence/p4-c1/mock-final-resource.json)与[stop](../../frontend/evidence/p4-c1/mock-final-stop.json)记录启动04:23:45Z、停止04:23:54Z；3496实际nolisten。没有真实API/PG/Worker/平台/provider。390px无横向溢出、20SKU缓存依据及null/0语义保留；这里只是C1增量验收，原24Web/native200/真实PG和正式P4/M1总Gate不能外推。

共享frontend CI会自动收集新增共5条契约，但尚未收集六条UI；A唯一owner仍需按上方固定命令接入并保持原24/hash/native200/owned门槛。独立审核、精确CI及Root阶段裁决仍pending；本交付owner不合main。

合后完整`uv run --frozen python -m scripts.check`实际exit0：目录/index/完整可达历史扫描各0、锁一致、80份Markdown错误0、Ruff/format/mypy通过，offline 1270 passed/358 deselected/2既有SDK deprecation warnings（99.83s），Node锁安装/24.21.0工具链/typecheck通过，npm audit0、Python audit95包0漏洞/0跳过。[verification-final](../../frontend/evidence/p4-c1/verification-final.json)保存实际计数、私有原log hash及测试时产品/生成/契约/预览源码byte hash；358未选集成用例不称本地通过。最终提交后的精确SHA由PR与Root交接回执定位，CI/独审不得用此作者自检替代。

## 610 独审 P1：任务详情新周期入口统一修复

独立Web Review已实际复验610的32契约/原6UI，并发现一个P1：任务详情旧B46只看can_start_new_cycle，打开通用create草稿，未检查completed与当前源店operator授权；若账号在其他店有operator，可把新草稿默认到该店。这违反本批同源UI合同。后端仍重验所选店铺权限，不能将该缺陷描述成实际越权写入。原6遗漏任务详情，旧作者通过与P1事实分别保留。

两入口现在只计算同一个newCycleEligibility：当前可信task completed、serverflag和当前源店operator创建能力齐备；报告入口额外核同task与报告的source_task/report/snapshot/facts_hash一致。任务详情B46改走create-new-cycle，负向显示具体原因；两入口草稿渲染都再核资格，只提供源task.shop_id。草稿按页面/task/shop/当前principal/auth_version绑定，参数仍须重新确认、新key准备后明确提交；不复制旧授权。PageData绑定读取时client/session，切换身份或client首帧不显示旧page，刷新/撤销/卸载和epoch继续丢弃迟到许可。不改后端、共享spec/CI/锁/权限函数；frontend/package.json保持610原字节，没有第二套caller接线。

实际修正回归：产品typecheck、test-owned预览typecheck、schema22 --check通过，生产build `6LHxKG0dBLKGyORdN3i_Y`成功；完整契约33/33（2.8s），原32+任务/报告同资格及来源反例1。完整P4 UI8/8（15.1s），原6未减少，新增2：task详情pending且serverflag=true/跨店operator但源店仅approver/serverfalse无草稿、完成且多operator授权时只源店草稿→freshkey→明确提交；准备后撤权清草稿/零POST、卸载后迟到completed不能复活待审批资格。原B04 headless回归8/8（20.4s）证明当前原键恢复、终态和会话变更保护未退化。UI均memory Fake/自有Next/严格本地GET，业务API/PG/Worker/平台/provider0。

新证据在[reviewfix verification](../../frontend/evidence/p4-c1-reviewfix/verification.json)、[33contract](../../frontend/evidence/p4-c1-reviewfix/contract-results.json)、[8UI](../../frontend/evidence/p4-c1-reviewfix/ui-results.json)与[B04回归](../../frontend/evidence/p4-c1-reviewfix/b04-regression/ui-results.json)；原610、P3和历史失败文件字节保留。自有3496与3490已停止且nolisten，资源/stop附证据。C-only无A/Python改动，因此不重复1270 Python全量；旧成功不冒充本修正执行，最终CI仍须重新验证新冻结源。

Root采用唯一A根CI owner接线：在原run_before_cleanup窗口加入同现phase4 config命令。该config now实际收8（原6+新增2），beforeAll自行用锁定SWC/webpack构建，不能删旧6或用本地8替代CI8。增量独审、新精确整批CI和Issue42结案仍pending；源冻结后先Root复审，不改PR body触发重复CI。

## 原 read7 失败安全诊断与 NOT_READY 单断言对齐

Root派发沿原WT/branch/PR45的最小测试增量。旧610真实read段test_exit1、invariants_passedtrue、PG已停/PID0，却failure_category=null：测试进程非零返回只置passed=false，不进入except。旧实际failed节点仍not_captured/unknown，不能根据随后发现的源码问题倒填旧执行轨迹；write/items未跑事实保持。

现有LiveReporter只额外把同一结构化结果独占wx/600写到当前自有private窗口`read-live-results.json`，不保存TestError/stdout/body/steps等。run_live_batches只在失败read且完成原清理后读取该私有文件；先拒绝已有reporter，必须是本次test进程已launch才消费。成功read、write/items既有closed摘要/window字段和公共reporter格式不改，runtime SourceFiles仍原13路径闭集，无第二caller或新framework。

解析仅接受原read7完整固定标题集的唯一子集、原9顶层字段、原4行字段、已知状态/finite安全duration/固定相对location；额外error/body/URL、未知或重复title/JSON键、缺字段、非法数、过大文件、非600/软链/缺reporter均拒绝。安全输出重建固定标题+状态、expected7、reported actual/pass/fail/skip/not_run计数；actual是reporter记录数，skipped单列，不冒称执行通过。缺/非法/非当前reporter的counts/tests是null，不伪造0。只加已登记Git SHA/原13源hash闭集/UTC stop/资源已停bool，不回显private输入/业务ID/URL/token/DOM/console/network或原stdout。受控类别仅read_test_failed/read_test_timed_out/read_test_interrupted/read_tests_incomplete/unknown，表示结果类别，不能推断assertion/fixture具体根因；无法确定保持unknown。

Root另授权同批仅对齐read.spec.ts原一句文案。自核live_seed仅创建P2/P3/来源/计划，未建explanation task/link/result；explanation读取SQL无缓存row时NOT_READY，GET不创建或调用模型。当前UI精确标题“已有解释尚未就绪 · NOT_READY”，旧断言“已有解释不可用或尚未就绪”已不存在于frontend。只将该断言更新为精确新标题，固定task/report、未调用模型、noPOST/仅login writes及原7分母和其余断言保持。这是源码核定的不一致，未证明旧CI实际失败节点。

本批实际纯回归60/60（0.21s），含新诊断闭集/非法title/缺reporter/旧报告拒绝/解析限制与原owner/origins；此前59/59准备批保留。Ruff全项目通过、296文件format、mypy212、锁检查、frontend typecheck/schema22、diff通过；[verification](../../frontend/evidence/p4-read-diagnostic/verification.json)记录实际scope与源码hash。真实read7、本批PG/API/browser/platform/provider均not_run/not_started，没有占A03唯一PG池。原default13+B04Mock8/真实read7-write10-items7/native200、300秒/23min/75cleanup及A产品/共享CI/合同/锁/权限均未改；没有重复1270全Python。小批freeze先独审、暂不push；Root释放后才在新owned窗口完整原7read一次，仍unknown即停止，不自动第二轮。

## C2：A03 已审四读组接线

Root释放后正常无冲突合入精确A `a1cd66936c3cd268d32c68bfafc8f34555e44aa7`，合并节点 `038868b71d246c88511a25770c2eb02b5b88c9dc`/tree26d056c/parentsb88+a1cd。此前Root已核b88一次真实read7实际7/7、31.65s、invariants/model0/低权flags/停止与自有down无-v保卷，私有完整证据保留；该成功不外推新C2真实数据。旧C1/B/Penpot及原失败字节保留，不重置日期预算或人工H/L。

只用原锁定sync generator与openapi-typescript7.13.0/TS5.9.3同步A OAS（docs/wheel逐字节一致），仍21paths/22operations/旧版本，无新routes/依赖/锁/视觉批次。新增mandatory sender_gates、投影目标/观察/完整唯一/当前历史/attempts/mode、principal linked_channels、事件record_trace/ref/relation/channel/tool/safe_code。旧Mock必需字段最小补齐且明确Fake，终态v2不会留“当前v1”的Mock资格。原严格shape/no-coerce/no-default/no-extra保留；消费额外核冻结模型的enabled/reason/mode、外部资格与controlled_sdk、当前版本旗标、完整唯一观察版本、tool类别/sdk_method/非model选择不变量。旧v1 verified属于合法历史，不拒绝或改写成当前v2成功。

Task/Execution/Item/列表/回执复用现Sync/Notice：业务状态和同步分别呈现，sender资格不等送达或手动重发权限；显示逐条alias/目标/观察/历史当前/完整唯一/attempts/as_of/safe error/mode。旧v1不能证明当前v2；legacy sent未报告完整唯一不能当当前核实；offline_fake核实明确非平台回执。unknown保留原记录待核，stale显示safe码/观察版本，业务终态不重开。新信息使用Notice info语义，不能被当作实际业务list-row计数。ops/config动态读取Gate原因和Worker bool/null，不使用旧固定sender禁用；身份仅当前principal的关联渠道及读取时间，不出外部身份定位。events再核当前task/精确source/ref关系；记录trace不是动态工具链，确定性工具/电商查询/SDK adapter操作/具体SDK方法/model事实分类型。当前A未报告sdk_method则明确未报告，不推方法调用次数或模型选择；不输出平台record/target/token/openID/PID或外链，不为新P4说明复用历史P2 actualprovider。F02/B47/B32手动路径保持原限制。

最终实际契约37/37（4.2s，原33+四读组4）；产品/test-owned tsc、schema22与生产build `SHqDQAyTPzSzDVQ8M0Mnl`通过。P4 headless完整12/12（26.1s，原8+新4），覆盖v1历史/当前Fake、unknown-stale-terminal/20内部项390、trace精确source/不伪SDK方法/模型选择、当前identity键盘/admin角色深链隔离/撤销。原B04Mock最终8/8（27.1s），原断言/分母不改；前序5pass3fail（新信息误用list-row与重复同步文案）、7pass1fail（原失败summary字面量）均保留，修本展示而非减测试。UI首次12/12（22.9s）长截图下部因iframe只绘viewport留白，测试改390宽4096高私有viewport+关键Card采集后12/12（23.2s），再修本展示回归后最终12；最终sync/trace截图经Agent目视核完整，无新视觉页/框架。所有UI是memory Fake、仅自有静态GET，未启动实际PG/业务API/Worker/平台/provider；3496和原B04 3490均自有停止且nolisten。证据独立于旧文件，见[p4-c2 verification](../../frontend/evidence/p4-c2/verification.json)、[37contract](../../frontend/evidence/p4-c2/contract-results.json)、[12UI](../../frontend/evidence/p4-c2/ui-results.json)、[B04最终](../../frontend/evidence/p4-c2/b04-final/ui-results.json)、[sync390](../../frontend/evidence/p4-c2/c2-sync-390.png)、[trace390](../../frontend/evidence/p4-c2/c2-trace-390.png)。

完整scripts.check真实exit1：目录/index/history扫描0、锁、83MD0、Pythonlint通过，继承A的feishu_delivery_read.py:55缩进导致format阻断（321formatted/1needsformat）。同命令后续mypy/offline/npmci/audit为not_run；另行mypy233与上述C检查通过，不宣称完整check成功。Root已派A单owner随A04一行格式修正，C不并写、不忽略；待精确A更新普通合入/CI核。根CI继承A唯一一行现phase4 config，会收当前12（原8不减），必须实际12通过，原default13/B04Mock8/real read7-write10-items7/native200与截止/清理不减；完整包CI/独审/Issue42/M1验收仍pending。C本批一功能freeze先独审，不因A格式停自主交付，也不push或改PR body触发新CI。

## M1 录屏与演示路线候选（2026-10-12，离线材料准备）

本节由 Root 释放给原 C owner，仅补交付文档。当前 A08 的 group20 / 可信原 outbox 恢复由 A 继续实施，SDK 保持关闭；本节不代表 A08 已验收。本次 docs-only 不启动业务录制；最后稳定源码的有限复现由 Root 在既有 Phase4 授权内调度，冻结对象、动作数量、额度和期限，无须逐动作再向用户请求开发许可。U01–U08 / N01 实施仍未授权，本轮不修改 Next.js、Penpot 或测试驱动。沿用冻结 18 页的导航和控件语义；原设计候选、失败测试和待确认合同的历史记录不改写。阶段验收仍由 Root 核实全部必要 Gate、独审、精确 CI 和实际回执后裁决。

本工作树当前已提交基线是 `43c40bb955a1ce4ef07704173759983eb8c8f4f5` / tree `25dde89c392b82b71060b05812f38807fb9bbcf2`，既有实际 Web BUILD_ID 为 `so6sfDmeVw7HKWdbGnVJf`。这是下方旧证据的来源，不是当前 A9a / A08 的最终稳定录制版本。Root 本轮实际核定祖先链为 PR45 head `52a4f76344fe15af25fdab4acdb53c2f0493080c` → 本地 source43 → 当前 A9a；PR45 至本地增加的是 A 原后端/Compose/SDK 文档等已集成历史，Web 产品零差异，不算本轮 C 的新修改，无须重合 52、reset 或改写历史。本地 HEAD 不用于推断远端 PR 状态或最终源码，旧 source53/43 也不升级成 A9a 录屏。精确最后稳定 source/tree/CI/build 由 Root 再配对。本轮不联网刷新 GitHub 状态，阶段事实引用 Root 已核 [Issue39 回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6108800023)；UX/N01 仍按 [Issue42 登记](https://github.com/aning0922/commerceops-agent/issues/42#issuecomment-6107597478) 待明确实施授权。六个旧未跟踪 ac08 驱动保留，不删除、不顺手 stage 到文档包；本轮只有本文件的 tracked 文档改动，不能称整个工作树 clean。

### 既有证据怎样使用

| 材料 | 实际事实 | 可复用范围与限制 |
|---|---|---|
| source43 原 AC08，23.32 秒 | 原 known 只读、20 项拒绝零新增、另一组 20×100 联合批准、单项 complete 至 v2 的驱动断言通过；`new_cycle` 段失败 | 保留 `failed/partial` 标签。DOM 21 行断言不是录像中全 20 行可读证据；complete 不能改字幕称 close。 |
| source43 v2 续测，2.68 秒 | current v2 / Q70 / 旧 v1 禁用的准入及一次 Web 决定回执通过；`wait_same_workflow` 为 `failed_unknown` | 保留原失败。后续 PG 完成事实不倒填当时画面；瞬时失败状态未捕获，不能断言一定是 `needs_reapproval`。 |
| source43 完成态只读补证，6.96 秒 | `readonly_completed_verified`；登录 POST 一次，其余业务 GET；零创建、决定和业务写。完成态 v2 / Q70 项 / 独立 execution hash / 旧 known 绑定保持通过 | 可作为新的只读结果补证；PG 唯一性、旧 21 items / 2 executions 的完整 digest 由 Root/A 独立实证，不以 API 单条返回冒充数据库计数。 |
| 完成态录像的本地离线 QA | 完整播放 174 帧，无媒体错误；细采样找到约 2.6 秒的新周期完成态、4.7 秒的 Q70 / v1 / 独立同步分区标题、6 秒的旧 known 完成态 | 三张脱敏静态帧只保留安全固定标签或数量像素，其他原帧像素去除。`simulated_web / Mock / offline_fake` 是明确的核验元数据标注，不能冒充已拍全投影核实卡。 |

只读源录像 SHA256 为 `2c645f6b512c0b7e60940a6508e72e0a250ddb42b3d731145d31a9836e6a152b`。原录像、抽帧、OCR 和失败摘要继续私有留存；不删除、覆盖或重剪成一次成功流程。C 私有材料位置为 `.audit/ac08-private-video-qa/qa-safe.json` 与 `.audit/ac08-readonly-video-qa/qa-safe.json`，均在本工作树，不在 Root 或 A checkout；这些 ignored 文件不是仓库公开附件。后者记录 QA 在 2026-10-11 20:48:43（Asia/Shanghai）前完成、报告 20:50:24 补记，保留 `report_written_after_deadline=true`，不把补记时间伪装成媒体窗口内动作。

可复用脱敏静态素材在 C 私有 `.audit/ac08-readonly-video-qa/` 下：`cycle-completed-redacted.png`、`q70-open-sync-heading-redacted.png`、`known-completed-redacted.png`。旧 C2 的 [同步 390px](../../frontend/evidence/p4-c2/c2-sync-390.png) 和 [轨迹 390px](../../frontend/evidence/p4-c2/c2-trace-390.png) 是独立 memory Fake 预览，只能作标注清楚的界面说明插页，不能拼入真实 API 录像并宣称来自同一任务。

### 最后稳定源码一次录制的前提

1. Root 先给最后稳定 source/tree、独审结论、精确 CI、真实 API/PG 结果和 BUILD_ID 配对。A 独占准备 PG/API、必要时的单 Worker / 全局单 Graph 与清理；C 不起第二套资源，不替 A 改 fixture、权限、outbox 或平台配置。
2. Root 注册唯一有界窗口，明确剩余 workflow / 决定 / 内部项动作额度、账号 scope、已存在对象与可读缓存引用、工作截止和清理 owner。只读路线用既有完成态，零 Worker、T1、T3、T6；过程路线只执行 Root 一次冻结批中列明的对象、数量和步骤，不逐动作另问用户，也不从本文件、旧额度或旧计划自行扩大范围。仅在复用原 AC08 既有四-workflow 库及其已登记额度的录屏窗口内，不能为凑镜头新建第五备用任务或再成功执行一组 baseline20，不能复活旧 completed task 或重批旧决定/原键。此限制不排除最终干净 Compose 复现由 Root 事前独立登记的一次新自有隔离 baseline20；该新窗口不继承旧额度，仍须完整必要 Gate，不能据此无限增加资源或平台权限。
3. 所有对象引用和低权限合成账号只从 Root 指定的当次私有材料取得；正文、公开日志和视频字幕不放账号、业务 UUID、URL、nonce 或 Cookie。认证输入不录像，登录成功后才在新隔离 context 中录业务页；登录页只能录不含输入值的安全空白界面。不得使用日常浏览器、HAR、trace、console 或原始 DOM 导出。
4. 录制只消费现有页面与后端事实。待内容与实际绑定加载后再停留取景，单张核心画面应有可读停留；若瞬时切页只拍到 loading，就记缺镜头，不用旧截图或补造状态替换。录制 caller 的选择与审核由 Root 决定，本材料批不修改已冻结测试入口。
5. 内容目标约 8–10 分钟，不是 Gate 或延窗理由。Root 的总窗口必须另容纳启动、登录与至少 75 秒退出余量；若仅有短只读窗口，优先完成约 6–7 分钟的必要结果镜头，明确标为只读补证。时间不足、身份/版本/来源不匹配、未知写回执或 API 不允许时停止；不重试换键、不自动批准新版本、不启动 SDK/provider、不延长原窗口。

### 候选镜头顺序与必要画面

时间段只用于编辑规划，实际时长取决于 Root 放行的范围、服务端响应与记录内容；未录到的段保留 `not_captured/not_run`。18 页不等于本次每页已实现或验收，下面只走现有 Web 主闭环，F01/F02 的未验真实渠道能力单独列缺口。

| 顺序 / 候选时间 | 页面、动作与必要画面 | 必须讲清的事实 |
|---|---|---|
| 1 / 0:00–0:35 | S01 安全空白登录页；认证后展示 S02 与当前授权身份/店铺范围，遮罩身份定位值 | 低权限合成会话；兼任 operator/approver 仍按各角色自身 scope 与 eligible 校验，不代表两个真人或额外扩权。 |
| 2 / 0:35–1:15 | S02→S09 读取 Root 指定任务及其报告/审批/执行/内部项链接；若已授权创建，M02 显式核对 Mock case、L/R/S 后准备原请求并明确提交 | 现入口是结构化创建。草稿和 B35 不受理任务；B01 的明确提交才走 T1。N01 自然语言原句解析/歧义接口仍有合同缺口，不用按钮名或自然语言字幕冒充已实现。 |
| 3 / 1:15–2:35 | S03→M03 冻结报告：来源/时区/最近七个完整自然日、参数、质量与总量；从第 1 行连续读到第 20 行，包含长名称、末项与 100 件值 | 全 20 SKU 不折叠、截断或只拍前几项。未知原始在途继续显示 null/未知；按 0 的有效估算仅属于指定版本的明确假设，不能声称库存原值为 0。实际总量以本次 DTO 为准。 |
| 4 / 2:35–3:55 | S04 固定 plan/version/hash：总项数/总件数、期限及完整假设集合；先拍默认未勾选，再展示全部未知项及末端动作区 | 普通批准不能替代联合假设确认。既有拒绝案例只读展示“拒绝假设、零新增项”；若 Root 放行新决定，逐项明确勾选完整集合后只提交一次本版本意见，不自动全选或另造拒绝任务。 |
| 5 / 3:55–4:45 | 原意见回执与 S09：approved/rejected、resume 状态、下一步读取；若 Worker 尚未完成，保留真实待处理状态 | 意见已受理不等于 T4 已执行；队列/Checkpoint 不能当成内部项事务。`needs_reapproval` 必须读 current plan/approval，旧意见不授权新版本；只有 Root 另行批准且资格满足才决定新版本。未知或冲突先读原回执，不能盲重投。 |
| 6 / 4:45–5:35 | S09 执行事实→S05/S11 内部项：已提交 execution、可见项与数量；同段拍同步卡的当前/历史投影、target/observed version、complete-unique、模式、时间和错误码 | 分别读任务执行结果、内部项跟进状态、同步结果。内部项 open/complete/close 都不等于采购、入库或库存修改；历史 v1 同步不能冒充目标 v2，Fake 核实不能称真实 Base 同步。 |
| 7 / 5:35–6:30 | S11/M01：优先只读既有 closed 项的原原因、原动作、版本 v1→v2、来源与独立同步；仅在 Root 明确批准 T6 时演示一次 close 原请求和原回执 | close 和 complete 的原因/终态分别呈现，不把原 complete 片段改称 close。关闭内部项不会复活 completed task 或重跑旧 execution；不手动重发平台记录。 |
| 8 / 6:30–7:30 | S09/M05/B46→M02：先展示旧 completed 与影响；打开新空草稿可取消；另读已完成新周期的报告/快照/plan/approval/item 及旧对象结果 | B46 只开草稿。新周期不继承旧批准、nonce、hash、假设集合或请求键；重新提交必须是被 Root 放行的新 T1。既有 open 项约束保留，不能绕约束重复建项。新旧对象的私有精确绑定由证据核对，不用字幕伪造新标识。 |
| 9 / 7:30–8:40 | S06 技术详情与 S03/M04 已有解释：事件来源、可靠 Tool 分类/SDK method、模型是否选择、引用、fact/model/usage 和模板/缓存来源 | 确定性金额/库存规则不交给 LLM。tool/usage/null 以 DTO 为准；当前 `model_mode=not_used` / 未报告不补成调用次数或 token 0。历史 actual_provider 缓存注明历史调用、原绑定和成本估算，不冒称本次新增调用；无缓存就显示 NOT_READY，不能临时付费生成解释或合成工具链。 |
| 10 / 8:40–结束 | 必要时只读展示 390px/键盘焦点/技术信息展开，再汇总本次通过、缺镜头及停止；保留足够资源收回时间 | 自动 Web 录像与真人观察分记；未做的 200% 缩放或身份 Gate 不由旧 Mock 图片替代。退出只关自有浏览器，资源由登记 owner 按原截止停止保卷。 |

若已放行窗口只有完成态对象，段 4–8 全部采用“已发生事实的读取/历史回顾”，不得拍本地假按钮动画或把旧 failed 片段剪成当次连续成功。原 AC08 四个 workflow 角色可作为受控案例说明，但不是新 scope 的默认额度；新周期若因真实 material 变化换版，必须按实际版本记录，不能强迫其停留在 v1 为了简化叙事。

### 画面中的证据标签与脱敏

| 实际来源 | 可用标签 | 不得外推 |
|---|---|---|
| 真实 session/API/PG + 自有 Mock + 自动 Web | `simulated_web`；业务 API/PG 为实际，业务数据为 Mock，模型按实际来源标识 | 不称 human_web / human_feishu；低权限合成账号不等于真人可用性实测。 |
| 离线 Base/IM 替身与 `offline_fake` 核实 | “离线 Fake 投影核实”；分别展示业务、发送资格、当前/历史投影 | 不称 SDK 写入、平台已发送或真实 Base 已完整唯一。配置 enabled/资格本身也不证明已发送。 |
| memory Fake / 原型 / 历史缓存插页 | 明示独立预览或历史；caption 标原 source/mode/绑定边界 | 不伪装为当前 session、当前任务、当前平台或当次 provider 调用。 |
| 真人飞书 / 真实 Base | 仅引用 Root 对精确实际平台回执及真人观察的最终结论 | 本轮 SDK 关闭；不为片长添加平台记录、成员、群/表权限或补造截图。 |

私有原片保留原字节、hash、source/tree/build/driver、窗口和结果摘要；素材索引不得包含账号、Cookie、业务 URL 或可重放决定材料。发布前逐帧遮罩 display_name/login 定位信息、组织/店铺与 task/report/snapshot/plan/approval/execution/item 标识、request_key、nonce、hash/trace/外部记录定位值；未知假设与 SKU 如需匿名，整段使用稳定行序号/映射并声明脱敏，不能改变全量成员数、勾选状态、数量、版本或原值 null。保留 Mock/Fake/simulated_web、风险、动作语义和业务/同步边界；不裁掉末项或禁用原因来制造顺畅流程。

新加的解说、字幕或脱敏注释应明确是材料层的说明，不能覆盖当前产品字段，尤其不能把 `pending/unknown/failed` 改写成成功。原标识截图、录屏与 OCR 不发 Issue/聊天；公开素材先做脱敏 QA，再由 Root 决定发布，当前三张静态素材仅供本地复用核对。

### 最终一次录屏仍缺什么

| 缺口 | 已有实证与仍缺内容 | 最小补证方式，须 Root 另行放行 |
|---|---|---|
| 全量 20 SKU / 未知假设 / 意见受理 | 原 API/驱动有完整行与明确集合断言，但旧视频只有统计/披露片段，缺全 20 行可读覆盖及从意见到执行的连续画面 | 优先读取既有 report/plan/decision：稳定停留、逐行滚动到末项，再读 execution。复用原 AC08 既有四-workflow 库及其已登记额度的录屏窗口时，限原额度，不增加成功 baseline20，也不为未知/冲突换新键重投；最终干净 Compose 复现的一次新自有隔离 baseline20 可由 Root 事前独立登记，不继承旧额度，仍保留完整必要 Gate。 |
| 单项 close / 新旧周期结果 | 旧 known 的 close 与新周期完成已由 Root/A/只读 API 独立核；原 Web T6 片段实际是 complete。新脱敏帧可说明新周期 completed 与 Q70/v1，尚无完整 close 原因/版本画面 | 只读既有 closed 项的 resolution、来源和独立同步，再读新旧 task/execution。完整 close 过程只有新的明确 T6 放行才录，不为了素材关闭额外项。 |
| 三态与可信轨迹/模型说明 | Q70 素材拍到独立同步标题，没拍全 Fake current/history/target-observed/unique 卡；新 scope 不保证存在解释缓存 | 拍现有三态字段与完整投影卡，S06 只展示 DTO 已给的事实；缓存缺失拍 NOT_READY。真人飞书/真实 Base、N01 和尚未授权 UX 整理仍分别列缺口，不以此材料批替代实现或验收。 |

本节仅候选文档及文本检查，不产生新的业务录制、平台/模型调用或测试通过结论。当前资源、SDK、模型门禁与 owner 不变；D1=2026-10-10、D30=2026-11-08、总 300h、原 P4 预算保持，人工 H/L `not_reported`。本轮材料窗口不超过 Root 释放的 90 分钟，不推送、不改 PR body，不进入生产或 Phase5。

## C09：N01 与 U02/U03/U06/U08 实施中的实际记录

2026-10-12 本轮已获用户正式实施授权，并由 Root 在核定 A08 后释放给原 C owner。此授权覆盖 N01 和 U02/U03/U06/U08；上节“未授权”是原材料批的历史状态，不覆盖本次直接授权。U01/U04/U05/U07、F02/B47 仍待收口，冻结 18 页设计不增加视觉批次。本节是实施记录，尚未表示整个 M1 或 Phase4 完成；独立审核、精确 CI 和最终集成由 Root 裁决。

实施 checkout 为隔离 `phase4-web`，普通快进继承 Root 已核 A08 的 `efcd4cd3dee2cb5a0b4bb3c886a573beca654391` / tree `e0e15b78baeccf561b65e5db55335b907b313ac7`，保留文档 `967d06c` 祖先。原 `a266` 工作树和六份旧未跟踪 AC08 驱动未改。C 独占 frontend/npm/Web 测试与本 UX 文档；后端、共享 DTO、迁移、Worker/Graph 和根 CI 仍由 A 单一负责。

### UX4 当前实现

| 项目 | 当前行为与安全边界 |
|---|---|
| U02 结果与下一步 | 创建回执主入口为“查看本次任务”；决定回执主入口为任务与执行结果。原标识/hash/处理人放在可展开技术详情。成功回执不默认要求重投，显式同键恢复入口保留。 |
| U03 失败、未知与冲突 | 无记录的 GET 失败与 loading 互斥；只读刷新不发业务 POST。提交 unknown 先查询原键，再允许用户明确同键/原字节恢复。已知冲突/拒绝锁住重投；即使原键查到已有回执，也不解除本次冲突、不当成本次成功。原有会话失效与撤权清缓存路径保留。 |
| U06 分离状态 | 执行回执不推断内部项已跟进完成；内部项终态不推断采购/入库/库存变化；同步卡独立显示当前/历史、target/observed、完整唯一及 Fake 模式。同步异常不重开业务项或追加平台写。 |
| U08 中文与语义 | 状态按显式枚举/中文别名映射语义颜色，不用正则猜颜色；未知枚举中性显示并保留原值。安全错误给出中文下一步，390px 页面与原键入口保留键盘可操作性。 |

Root 后续正式转交 A09 `3c393e33d7a9c479a87b0f0db1475b61681ff535` / tree `f67b44f18ba68a9e38f8ee2d839160863a8f95da`，C 核非重叠后普通 FF 集成，自有 WIP/旧驱动保留，无 reset/stash/强推。合同 Markdown SHA256 `17408b764a49c9a7e95f93097065558da24291a0df002b989c26e3af2484b495`，双 OpenAPI SHA256 `b9dd7f6175489899b6a69a2109dd2116e637c326d098e041e63e71cab2ca06ef`；独立 N01 schema --check 匹配，不重写 P3 原 22 操作资产。

N01 现已实现精确 `POST /api/v1/tasks/preflight` 客户端白名单/闭合解码与 M02 本地草稿接线：Unicode code point 计数和来源位置，明确进入文本草稿后检查来源/冻结窗口/全 fixture 范围，B35 本地完整确认，再经原 B01 准备与鲜键明确提交。ready 不自动提交；MISSING 只允许手工补缺项，示例值留空、不把服务端 clarify 改成 ready。INVALID/unsupported 锁住，须改原句重新解析或明确取消再开空结构化草稿。文本/shop/fixture/参数编辑撤销旧确认，原句和来源变更清候选；revision 与身份/auth_version key 丢弃迟到或撤权后的响应。未使用 P2 `/test/route` 或模型解析，不增加通用持久 draft。

### 本轮已执行离线测试与保留失败

以下是实施中实际运行，最终冻结源码验证仍待 N01 接线完成后记录。

| 检查 | 实际结果与范围 |
|---|---|
| TypeScript / Next.js build | 产品与 P4 测试 typecheck 已通过；Next.js 生产 build 已通过，发生于最新冲突回执 guard 之前，因此不外推为最终冻结版本 build。 |
| 合同 | 39/39 passed，3.5s：旧 37 加 2 项中文语义/安全错误契约；纯离线，无 API/PG/Worker/provider。 |
| P4 页面首次 | 13/15 passed，45.1s：2 个失败分别为 intentional GET failure 的测试等待条件不匹配、memory RequestRead fixture 缺 `status=succeeded`。保留首轮 JSON 和错误上下文，不抹去失败。 |
| P4 页面修正 | 15/15 passed，26.7s；仅修正上述测试接线。旧 12 项全部保留。 |
| P4 页面最新冲突 guard | 15/15 passed，27.3s；新增 3 项覆盖 GET failed/loading、unknown 原键读取与字节不变恢复、409 查到已有回执仍失败锁住。 |
| B04 页面 | 8/8 passed，24.9s；旧断言保留，原 ACK unknown 同键恢复测试增加明确展开技术详情。发生于最新冲突回执 guard 之前，最终回归待接线后核对。 |
| N01 候选 decoder | 4/4 passed，1.8s；只验证离线严格结构/假 ready/缺项示例/Unicode 来源位置，不是 API 接通或真实 PG 验收。初轮 typecheck 引用旧 DTO 名 `Parameters` 失败，已修正为现有 `CreateNewCycle.parameters` 后通过；最终完整验证待固定合同接线。 |

接线后完整离线矩阵已实际通过：合同 **45/45，3.6s**（旧 37 + UX2 + N01 6）；P4 页面 **19/19，33.4s**（旧 12 + UX3 + N01 4）；B04 **8/8，25.1s**；原 B01 **13/13，14.4s**。合计 85/85，保留全部旧分母。N01 页面 memory DTO 由冻结 A 的确定性 pure parser 导出，来源 SHA 随 `n01.fixture.json` 记录；它只证明离线组件行为，不是业务 API/PG 实测。生产 build `5fDxN-Axb18MAcYy903OP` 已通过，产品/P4 tsc、C 新测试辅助程序 Ruff/format/mypy 已通过；完整工程检查另行记录，不用作者自检替代独审。

### 新自有 PG/API/Web 的三轮未执行与停止

| 段 | 实际结果与保留层次 |
|---|---|
| `p4c09-n01-2ad3770888`，20:13:16Z→20:13:19Z，原截止20:42:15Z | PG 启动后，seed 前登记读取拒绝：C window 内联源码清单33866 bytes，超过既有 private_bytes 32768上限。尚未 migrate/seed/API/四imports，6 PW not_run，Create0。C-only 将完整清单移至独立 manifest，window保留SHA；不放宽A校验。 |
| `p4c09-n01-991fd784b0`，20:15:41Z开始，原截止20:44:41Z | Compose准备失败，原输出未保存，具体原因unknown；cleanup inspect空container又失败，两层分别保留。随后只读核该project容器0、三端口native退出1/无监听；6 PW not_run/Create0。修正C-only空container停止分支与私有Docker启动诊断，不追填第二层原因。 |
| `p4c09-n01-ceaf737353`，20:18:53Z开始/结束，原截止20:47:52Z | 私有313byte Docker日志确认 `all predefined address pools have been fully subnetted`：新网络创建失败，未到seed/API。6 PW not_run、Create0；PG container未创建/无监听，停止，不自动第四轮。 |

三project清理回执位于 `frontend/evidence/p4-c09/n01/cleanup.safe.json`：各容器/网络剩余0，仅本批第一project的container/network执行down（未-v），卷1保留；第二第三无卷创建、从未删卷。仅释放本批网络1，清理后当时Docker网络总数31；不列他人项目、不全局prune/改地址池。第二原失败及第三日志hash、各私有窗口保留于 `.audit/c09-n01/source1-run*`。真实 N01 Web/PG **6 expected / 0 actual / 6 not_run**、API四import与实际创建pair核证均未执行；A自己的13 PG不得替代C的新联调。解除条件为可用Docker subnet及Root在冻结独审后另行裁定一次新的有界验收，不能暗续旧三轮；预计准备+6PW约5–10分钟，尚非实际运行结果。

证据位于 `frontend/evidence/p4-c09/`；首轮失败保留于私有 `.audit/c09-offline/source1-first/`，不会改写为通过。离线矩阵使用新自有 headless 上下文、localhost Next 与 memory Fake，不启动业务 API/PG/Worker/SDK/provider；上表第一联调段曾启动新自有PG，尚未到业务seed/API，分别记账。本轮 3496/3490 服务已停止，native listener 检查无存活监听；新增页面测试限制 30 分钟，自有资源启动/停止另记，不继承旧 AC08 放行窗口。既有 npm schema 检查现串行核对原P3 22操作与独立N01资产，实际--check均通过；根CI文件/锁不改。

离线最新停止回执 `offline-stop.safe.json` 核3410–3415/3490/3496八端口全无监听。P4/B04继承自有UID/cwd/build检查；B01通过当前checkout的Playwright新webServer/no-reuse跑完并自动收回，其额外UID/cwd观察发生于teardown之后，未核到启动时逐PID绑定，明确记not_verified，不为补此观察重复完整矩阵。所有截图/字体报告改写本批独立路径，原B01/B04/P4历史证据不覆盖。

本段执行窗口为 UTC `2026-10-11T19:03:28Z` 至 `2026-10-12T01:03:28Z`，不自动延长；同源运行上限 3 次，测试资源单次不超过 30 分钟。新增 paid/provider 调用 0、平台业务写 0、真实 SDK 关闭；D1/D30/300h 与原 P4 50h 不重置，人工 H/L `not_reported`。

完整 `uv run --frozen python -m scripts.check` 实际 exit0：当前/index/完整历史敏感扫描各0，锁一致，99份Markdown错误0、Ruff/format/mypy（284 source files）通过，offline1531 passed / integration441 deselected（92.47s），4条warning为既有SDK deprecation及终止测试fork警告，不报成新增SDK调用；Node24.21.0锁安装/typecheck通过，npm漏洞0、Python95包漏洞0/跳过0。441未选集成不称本地通过。集中结果与测试/代码哈希见 `frontend/evidence/p4-c09/verification.safe.json`，私有完整日志hash保留；文档最终与待提交新文件敏感扫描在commit前另核。候选冻结后停push，交Root安排原Web独审，真实Gate/精确CI/main仍待裁决。

### C09 原 Web P1 的 scalar span 修正候选

原 Web 对精确 `0fd4a10820e9d42614ee315d11733a56cb2891c4` 正式独审发现唯一 P1：`n01MatchesInput` 只限制 shop/fixture/end，未证明明确参数的 span 对应原句中的 name/value；契约测试的 ready 样例误用 full-token span。没有其他独立 P1/P2，但原 source 不能集成，原85项离线/Fake成功和实际6项not_run不解除P1，全部保留。

Root已核真实服务端 `_explicit_lrs_spans`，派回C-only最小修正：使用code-point array核safe integer索引、start>=2及完整bounds，`slice(start,end)===String(value)`，start前紧邻两字符须为对应`NAME=`或`NAME:`；end后不得仍为ASCII数字，防止把`L=33`截成首位3。只验证服务端返回的有限标量绑定，不增加前端全句NLP、猜参或修改A文法。契约ready的真实scalar偏移为L7..8/R11..12/S15..16；UI `n01.fixture.json` 原本正确，逐case对照冻结Python pure输出，原字节不改。

新增负例包括范围内错误span/value/nameprefix、full-token、UTF16偏移及截短多位数字；新增Unicode空白/0085/天/冒号正例逐项由真实Python输出核准，多位L33的7..9/R12..13/S16..17亦核准。emoji只证明code-point scalar单元边界，不宣称服务端支持含emoji的自然语言原句。shape合法但name绑定错误的响应经实际P3Client离线transport拒绝；页面禁止进入B35/B01，不发创建。

本修正实际执行完整contract **49/49 passed，3.4s** 和P4页面 **20/20 passed，33.9s**；所有旧contract/P4分母保留。证据独立写入 `frontend/evidence/p4-c09-reviewfix/`，不覆盖原0fd/85证据。产品与P4 typecheck、新生产build、schema原22+独立N01 check均通过；3496自有Mock按固定30min期限启动/结束，native退出1无监听。A/backend/共享DTO/锁/根CI、六旧untracked、原a266与原文法不改，未重启PG/Docker网络/SDK/provider。B04/B01产品路径未改，本批不重复其原8/13；Python1531/441是原0fd完整检查，不冒本修正重跑。实际6PW/API import/Create pair仍not_run，旧三轮暂停不变；新精确冻结停push，P1解除以原Web复审和Root核定为准。

### C09 runner 派生输出与输入哈希的小批修正

Root已核e375原Web复审P1解除、无新增P1/P2；该产品结论保持。A集成检查与Root随后定位受控runner把本段会覆写的结果文件也作为来源输入：CI清除旧样本后可能因tracked文件缺失而捕获失败，结束后的输出hash也会变化。此问题是runner输入/输出边界，不改变N01协议或产品。

C只在既有 `run_c09_n01.py` 排除三条固定派生sink：`frontend/evidence/p4-c09/n01/live-results.json`（live-reporter C09分支）、`pg-invariants.safe.json`（live/n01.spec.ts afterAll）和 `resource-stop.safe.json`（runner finally摘要），实际writer路径均核准。其他tracked源、历史evidence/fixture与原6条显式关键files全部保留，缺真实源仍fail closed；不泛排evidence目录，不新增路径接口或通用manifest框架，A共享CI不写。

仅自有tmp纯验证：最终代码 **14/14 passed，0.41s**，覆盖三个输出缺失/新建/改变/删除均不影响input manifest，6关键代码/fixture/其他历史证据的变化仍改变对应hash，缺真实关键源拒绝。真实checkout只读清单也与原全集精确set对照（提交前322条，固定sink3条，其中当时tracked输出1条），代码和fixture均纳入；此数量是提交前实测，不预写提交后数字。初轮mypy测试引用未显式导出的subprocess报错，已改为stdlib patch；最终Ruff/format/mypy通过。产品、49/20与原85证据、原UI scalarfixture不改，不重复18页/底座/build；无PG/API/浏览器/新服务/Docker网络/SDK/provider，实际6PW继续not_run、三轮停止不变。小批精确冻结停push，交原Web runner-only增量审查，不能提前签实际CI Gate。

## C10：现有失败 CI 的只读定位与闭合安全诊断

Root核综合 `e9b9c1bf67c14fc8b9ff12e091c516433aa899e4` 的 [CI38175892938](https://github.com/aning0922/commerceops-agent/actions/runs/38175892938) 终态FAILURE后，派回新的普通C-only收口段：UTC `2026-10-12T04:40:50Z` 至 `06:40:50Z`（Asia/Shanghai 12:40:50–14:40:50），最多2h Agent墙钟。旧6h段已过期，旧本机三轮不续、不第四次联调；本段不启动PG/API/SDK/provider/浏览器服务、Docker网络，不push/触发CI或改A共享CI/后端/迁移/DTO/锁。

原C `phase4-web` 与a266 checkout缺失、worktree registry无C，原因unknown；本会话仅有陈旧active附件、无archive。Root核原branch仍精确22aa且对象存在后，授权普通 `git worktree add` 恢复同原branch/path，恢复HEAD22aa/trackedclean，无force/reset/stash或新branch。attach_worktree固定返回“existing managed worktree”错误，未强制；六旧untracked及旧runtime历史本次未恢复，不能沿用“六资产完好”作为当前事实。此前原字节/hash与22aa历史证据保留。验证临时只读复用同repo已装锁一致依赖的ignored aliases，不改A产品或全局环境。

### 可核实 CI 事实与 unknown 边界

| 现有job | 日志可核实内容 | 仍缺 |
|---|---|---|
| frontend `114578090663` | read test_exit0/invariants true/provider0/PG已停；write test_exit1/invariants true/provider0/PG已停；items没有启动记录。实际JSON failure_category均null。 | 逐case状态/实际分母/具体断言无输出，不能据exit1指定某case或业务根因。 |
| n01-web `114578090517` | test_exit1，owned段244.932s，PG stopped/Pid0/无listener、Worker/SDK未启；实际JSON failure_category=null。 | 没有逐case或expect诊断，不能声称6项都执行/通过；具体断言和实际case数unknown。 |

两个完整job日志只在工具私有store读取，未输出或上传原始内容；早先从全log命中RuntimeError包含workflow回显代码，已更正，不能当实际异常。只读artifact inventory仅pg-existing/pg-phase3，无frontend/N01失败产物；两runner将PW stdout/stderr送DEVNULL，现有reporter只输出有限状态且隐藏raw error，而失败job跳过“require成功证据/上传已核safe报告”，所以现有日志不足。441PG由Root单独核，C不借其成功替Web失败。历史本机0actual/6not_run与本次CI“PW进程失败、实际case数unknown”分别记录。

### 本包最小修正与 A 接线边界

现有live-reporter只在 `b04-read/b04-write/b04/p4-c09-n01` 四目标启用闭合失败sidecar；正常live-results字段及b02/b03历史success行为保持。新 `frontend/tooling/live-failure.schema.json` 结构闭合，30个源码固定title、四stage、固定错误category/matcher enum；专用导出 `liveFailurePolicy()` / `validLiveFailureDiagnostic(value, policy)` 另核title/声明file-line、known tracked test/frontend源码有效line、唯一reported数量/每状态计数/未报告数量/实际body观察不足null、global错误最多16与固定spec源码SHA。无message/value/cause/stack/snippet/expected/actual/响应/DOM/URL/任意路径落盘；message仅512字符首行在内存派生固定枚举，位置只接受已知源码有效行。reported数量不冒body执行；FullResult passed且无异常时不能成为失败产物，异常passed只供诊断，job_outcome=failure/gate_passed=false由A单独绑定，不能签Gate。

固定失败sink为 `frontend/evidence/b04-live/read/failure-diagnostic.safe.json`、`frontend/evidence/b04-live/write/failure-diagnostic.safe.json`、`frontend/evidence/b04-live/failure-diagnostic.safe.json`、`frontend/evidence/p4-c09/n01/failure-diagnostic.safe.json`。C逐阶段启动前只清对应sink，N01只清单sink，其他历史报告/源码/未知目录不删；N01 manifest精确增加此第四mutable排除，原3排除及其他inputs保持。来源绑定额外纳入immutable schema文件，不减少原源分母。A独占workflow失败时验证/上传接线，独审后才下一精确CI；若reporter未启动/被kill且无sidecar，继续unknown，不能用旧sample补结果。

只读还确认write.spec两处交互与已审C09不符：普通批准十次回放、unknown先GET后的重投直接点击折叠details内按钮。Root批准各新增一次显式展开“原请求技术详情与受控恢复”，产品不改；去掉恰两新增行后新spec与22aa逐字节相同，10用例、全部assertions、10次/单digest/key及unknown先GET保留。此静态错位不是CI38175892938具体失败断言的定位，实际效果待精确CI，不声称PG/Web已过。

### 本段实际离线验证与保留失败

最终完整 **62/62 contract passed，5.444s**（含13项C10敏感注入/四stage落盘/旧success/非法metadata回归）；Python **58/58 pure passed，0.38s**（第四sink来源边界/四sink清理/旧read安全诊断/owner）；产品typecheck、Ruff/format/mypy通过。没有page/browser/PG/network服务，本段不重跑18页/底座/build。类型检查覆盖新write；辅助native TypeScript7没有旧AST JS API，AST未核，不冒通过，改用精确字节差异核证。

首C10 contract导入import.meta在CJS失败、0test，改Git root兼容定位后9/9 pure通过；清理纯回归首19pass/1fail为Darwin unlink目录EPERM和Linux EISDIR分类差异，明确两OS异常tuple后仍证明目录保留，非业务assert放松。首完整contract60pass/1fail为恢复checkout缺Python runtime path（T6 strip对照），补同repo只读runtime路径后61/61通过；再加非法FullResult安全负例后的最终62/62。首完整原JSON被后续报告替换，未保存原JSON，明确保留安全失败摘要与私有原log，不伪称完整artifact已恢复。结果在 `frontend/evidence/p4-c10-diagnostic/`，raw日志/敏感素材不提交；新candidate精确独审前nopush/noCI，剩余24真实Web/6N01实际Gate与具体失败根因保持pending/unknown。
