# Phase4 / M1 Web 接线交接

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
