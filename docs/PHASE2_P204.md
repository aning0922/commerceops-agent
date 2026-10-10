# Phase 2 P2-04 集成合同与证据

当前 in_progress_p2_04：P203已获冻结3986dd独审/精确CI内部门禁；B组件经独审普通合入A07d3。A在同一Draft PR30完成固定五意图路由、解释子任务、权限和持久预算集成，作者代码/完整检查候选已交付，最终冻结SHA独审/精确CI与受控真实窗口尚未完成。真实provider请求0，真实routing not_run；不以Mock/模板或组件独审抵最终Gate。

## 1. 固定工作流与事务

P203 `inventory_analysis_only` / `p203-inventory-analysis-v1`、报告completed语义、冻结InventoryReport/goldens及checkpoint保持。说明使用一级显式 `report_explanation_only` / `p204-report-explanation-v1` 新UUID/thread；只有自己的已完成P203 Mock报告能作为父引用。父task、snapshot、report、facts_hash、body_hash、logical_key与当前操作者/identity/auth_version/org/shop/grant分别核验。完成结果、收据和child completed同一PG业务事务；checkpoint不是副作用事务。

模型路由是固定 `inventory_intent_only` / `p204-inventory-routing-v1` 新UUID/thread。原句限2000字符、catalog固定inventory-intents-v1、prompt固定inventory-routing-v1；原句不能提供scope/role/approved/evidence-mode。DeepSeekRoutingPort只接受五意图及有限L/R/S候选，确定性guard验证Unicode原句span、整数0..365、参数名及明确来源，拒绝重复/缺失确认/越权字段。不是字符串匹配冒充LLM。routing结果及单独routing审计不自动创建库存分析、审批或补货业务任务。

三张固定图由同一Worker/global Graph slot串行执行，各自pin版本/thread/key。没有通用子Agent/动态工具/通用调度。新表为显式intent请求/结果、说明引用/结果/收据、模型调用/观察及阶段预算；证据禁止UPDATE/DELETE/TRUNCATE。所有own PG测试是Mock/simulated范围，旧P1真实有限Gate另行记账。

## 2. 五意图与有限参数

| intent | 确定性边界 |
| --- | --- |
| inventory_replenishment | 仅受限分析意图；缺省L/R/S=3/7/2标demo_assumption。未确认参数不能自动创建库存业务任务 |
| task_status | context必须是当前org/shop/requester的P203任务；读取任务状态 |
| explain_report | context必须是自己的已完成可信报告；显式说明child，没有业务审批/执行 |
| clarify | 歧义、未知scope或不安全候选；不创建库存/补货/审批任务 |
| unsupported | 采购/支付/退款/执行等超范围请求；不执行 |

受控 `/test/route` 默认只入队template模式意图任务，HTTP输入不能开启paid/provider；`/test/routes/{task_id}`只读取已存结果。显式注入的Mock port用于契约验证；若参数未全部具有代码确认的explicit_text来源，受控业务分派返回澄清。正式session/飞书多轮权限未授权且未实现。

## 3. 同一阶段持久预算与恢复

routing和explanation真实调用共用 `phase2-deepseek-20261010:actual`；自有替身仅使用独立offline账本，不能当作实际provider证据。固定DeepSeek/deepseek-flash/https://api.deepseek.com Chat Completions，thinking disabled，无tool/自动重试/model切换/redirect/proxy继承。端到端绝对截止20秒。

输入上限8000，输出800；每次先原子持久预留一次调用和8000/800峰值cache-miss费用US$0.00336，再进入HTTP。阶段总调用≤10、USD cap≤0.10。随机HTTP request_id用于追踪；幂等依据scope、原句或报告hash、完整body、prompt/model/catalog/mode/pricing组成logical_key。预算count/金额只能单调增加，halt不能清除；预算行不能删除或TRUNCATE，重启不清零。

usage/价格估算/预留金额分别保存；无实际账单时actual_cost_usd=NULL，不编造实际费用，不经库存Money(20,6)serializer舍入。未知timeout/usage/cost、截断或usage越界保留完整预留并halt。已预留而无业务结果时，无论重试或OS确认后的恢复都不重发HTTP；返回安全模板/澄清，记录uncertain。已提交结果则优先收据，重复读取/恢复不再扣款。继续保留P1显式OS终止证明，lease/锁可用不等于原进程已停止。

## 4. Token与key边界

固定官方纯文本资产、完整chat framing、上界与API差异余量见[tokenizer资产说明](../backend/src/commerceops/infrastructure/token_assets/README.md)。本地GIL释放的有界BPE计数不冒充API实际usage；正式窗口须核对usage和上界差异。runtime使用锁定tokenizers0.23.2及httpx0.28.1，不下载模型或执行远端代码，no-dev wheel应包含资产。

默认Worker和API不读模型key、不连接provider。仅Root明确真实窗口后使用inventory-test-run的显式actual开关和key-file；key必须当前OS用户所有、普通600文件，拒symlink，open/fstat核同inode后限512字节读取为SecretStr。`model_probe verify-config`只stat/验证非secret固定profile，不读key/请求API。本轮没有读取现存`.env.model.probe.local`或`runtime/model/api_key`内容，没有balance/models探测。

## 5. 验证记账与保留边界

已实际执行的开发专项：解释7 PG第三轮全部通过/13.00s；两种SIGKILL→阻止启动→显式OS确认→新进程恢复均无第二次HTTP。预算并发两项PG通过/3.56s：12个不同请求最多10个预留、相同logical并发仅1个且unknown halt。路由/token/config+原P203离线契约59项通过/1.09s（含35新增P204）；当前/index/完整可达history敏感扫描0，scanner配置/豁免未改变。首轮tuple与JSON list缓存比较错误、第二轮严格DTO list错误真实失败记录保留，第三轮7项通过，不把失败或未运行写成通过。

准确profile组合后P204完整专项18 PG passed/26.47s：路由与解释同账本、五意图、same-key缓存、并发最多10/重复一次、四处真实SIGKILL恢复、授权撤销、读接口无调用、owner/runtime不可变保护，以及越界usage降级后只读可用。完整scripts.check实际826 offline/68.98s，182 integration deselected；mypy135源文件、ruff/format/文档/锁/Node工具链通过，Python95锁依赖及Node漏洞0。no-dev实际runtime中httpx0.28.1/tokenizers0.23.2/固定token资产可用、pytest未安装。

完整隔离PG supervisor使用自有p123-92f833c0a6ac/无宿主端口，0003迁移/初始化/授权/版本查询重跑成功；182 PG passed、826 deselected/90.79s（含85 P203、18 P204），G1三次count_one核验及六种G2必要证据完整，passed_no_hang_reproduced，cleanup_exit0。实际复核containers/volumes/networks均0、所属runtime目录已删除。早前自有p203-006432bf0e也已cleanup0且只移除所属PG密码；模型资源未读/改。最终冻结SHA独审与新精确CI尚待，作者自检不替代独审或实际模型Gate。

完整组合验证前另保留两个真实失败：旧B profile尚未同步时误提前运行1条routing PG，预留按prompt_version不匹配拒绝，1 failed/2.43s；准确B routing-v1同步后已通过。初次18项扩展前12项综合为11 passed/1 failed/20.93s，owner TRUNCATE被外键提前拒绝，测试调整CASCADE以明确触发不可变保护后通过；没有放宽数据库保护。安全扫描初轮两个非secret label/多赋值误报，改清晰分字段代码后三层0，scanner规则/豁免未改。真实routing/解释仍not_run，正式T3/真实库存/自然网络故障/wire/p95/长期幂等不外推；#23 risk_accepted/not_identified、P1冻结和M1冻结保持。

基线机器Darwin25.6.0/arm64，Python3.12.13；隔离容器PG17.11-bookworm。数据inventory-v1固定25场景，baseline为1 product/1 order/1 inventory、0 refund/open_item；P201/202共享DTO、fixtures/goldens的hash不变。真实模型基准、M1前端联调/交互回归、p95、40×3重复稳定性、生产认证、正式审批/执行仍not_run，不将这些开发运行时长外推为产品性能或人工有效工时。

双线及额外Review扣原P204/Phase2 30–40h与总300h，不增预算，不改D1=2026-10-10、D30=2026-11-08；人工H/L not_reported。A只交付实现与证据；Root在全Phase2必要Gate后按用户委托正常合main，A不自行合并，不扩后续Phase/飞书/生产。
