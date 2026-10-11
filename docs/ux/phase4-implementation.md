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
