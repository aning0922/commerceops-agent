# Phase4 A09：单原 workflow 跨 Gateway 接续与 N01 Web preflight

2026-10-12（Asia/Shanghai）。原 A 唯一后端 owner、原 WTfd38/codex/phase4-feishu/PR43；本批候选已实施，作者必要 PG 通过，完整检查已通过，冻结源码独审/精确 CI 待最终回执。不提前写未来 SHA/CI、main 或 Issue 关闭。原 C 独占 N01 M02 接线和 U02/U03/U06/U08，B 三适配器及全部产品/锁字节不写。

## 依赖、范围与接口

Root 已核 A08 source efcd4cd3dee2cb5a0b4bb3c886a573beca654391/treee0e15b78baeccf561b65e5db55335b907b313ac7，原 Core 增量此前 P1 解除/无新 P1P2；精确 [CI38164348959](https://github.com/aning0922/commerceops-agent/actions/runs/38164348959) 四 SUCCESS，本 A 在 GitHub API 再核 head/attempt1/各 job。Root 在精确 source review checkout 用原 verify_pair 核236+186=422完整 PG、25模块无漏重、A08 39与 G1三/G2六/cleanup0/三Web13hash。Root 首次旧 main 分组上下文拒绝已换精确 source 核定，不是 CI 缺陷；这些回执不验收 A09 新功能。main 仍9d97，Phase4/M1/Issues39–42未结案，真实 SDK/真人未放行。

用户原批准 N01+UX4，Root 在 A08 依赖 Gate 后释放本功能批；接单 [Issue40#6112580546](https://github.com/aning0922/commerceops-agent/issues/40#issuecomment-6112580546)。真实起始19:03:09Z/客户端03:03:09，硬截止2026-10-12 01:03:09Z/客户端09:03:09，wall≤6h；不借新任务续原 A08 20:37:16Z诊断或 SDK。自有 PG 固定每批≤30min/同源≤3；D1=10-10/D30=11-08/300h/P4 D13–17/50h保持，A4–6+C9–13/13–19 Agenth规划与跨 Gateway 2–4h竞争原预算，不折算 human H/L（not_reported）。无新会话/branch/WT/模型、平台调用/扩权/新成员/生产/Woo/Phase5。

先交接 [N01合同](contracts/p4-n01-web-v1.md)及真实 DTO，再串行补 [workflow恢复合同](contracts/p4-a09-workflow-recovery.md)与 preflight；文字/端点更新回执为 Issue40#6112610035/#6112816542/#6112908726。`POST /api/v1/tasks/preflight` 为 Web session/current operator/shop/CSRF/Origin 的业务只读入口，严格响应 ready/clarify/unsupported、参数出处与缺项、Mock fixture 冻结窗口/全店范围，ready仍需本地明确确认；原 CreateNewCycle 鲜键显式提交才产生 T1。无通用 draft/token、自动提交/审批、Graph/Worker/provider。原 P3 22 操作/OpenAPI字节保留，独立 [N01 OpenAPI](contracts/p4-n01-openapi.json)加入运行时第23操作。

支持 PRD§3/J01/M02 两条完整原句及六条明确库存句式；未给 L/R/S 必须 clarify，不能默认确认demo3/7/2。复用原 P2 的完整 LRS 参数块，拒绝重复、分数/范围/负数/非法尾词/未全消费；头部也只消费支持语句/有限 window/scope。其他 SKU 或日期/能力 unsupported，原 BC02/产品能力依赖 pending，不冒 BC02/M1全部完成或擅移 M2。C 本地确认失效、异步旧响应、unknown 原键、真实 Web/390px/键盘及其四 UX Gate 仍由 C/Root 核，不以 A 的 ASGI/Mock 代签。

## 作者实际 PG 与失败保留

全部新自有项目仅当前 backend/tests/scripts/docs只读挂载、旧依赖镜像；UID501:GID20、私有目录700/文件600，无主机端口/loggingnone、新 PG 凭据仅本项目。窗口开始即固定，不重置；每批 stop/down exit0/containers+networks0/低权三false/tempDB0/未用-v保卷。actual SDK/Factory/Secret/provider全部0。Mock ledger、同进程ASGI、Worker进程、官方平台证明分别记账。

| 批次 | 实际结果与时间（testcase Σ / suite 秒） | source/import | 资源实际停止 UTC |
|---|---|---|---|
| workflow a5b7 首批 | 5/5 fail；ready/state/jobs有界等待；148.335 /153.263 | 502 source0差/10 Worker四模块匹配 | 19:18:33.659260Z |
| workflow b79b 修后定向 | before-T2 1/1 pass；14.094 /18.883 | 502 source0差/2 Worker四模块匹配 | 19:21:15.339510Z |
| workflow b160 完整 | 21/21 pass；196.692 /201.415 | 504 source0差/21 Worker四模块匹配 | 19:29:13.390229Z |
| N01 2709 首批 | 13中11pass/2fail/exit1；27.318 /29.168 | 509 source0差；Worker回执0，four_imports=false，不作通过 | 19:37:08.129172Z |
| N01 275f 修后完整 | 13/13 pass；23.134 /24.758 | 509 source0差；实际ASGI同进程四N01模块1回执匹配，无Worker child | 19:40:23.024472Z |

workflow 首批具体子进程异常未捕获，仅保存有界失败；源码核初版对 immutable p4_inbox_receipts 多用了 FOR SHARE，运行角色只有 SELECT/INSERT。移除多余 r 锁，不扩权；增加 scope_validated 观测点，之后定向及完整通过。不得追溯声称已捕获首批实际 SQL trace，亦不解释旧 P3 972 assertion unknown。

完整 workflow21=新6（五实际 SIGKILL/原 OS 终止证明/新 Gateway、一个含14子负例的拒绝测试）+原outbox10+IM2+Gateway1+controlledWorker2。五边界 before/after T2、ready、before/after T4，原 plan/approval/hash/nonce/expiry/决定、同 task/source/job/CP 原接续、唯一 execution/20×100/原20投影key均核；new Gateway max_workflows0 拒新 T1，窗口外不吞队列。负例包括原 Gateway/Worker/SDK/task/receipt/approval/version证明、当前app/tenant/allowlist、原never-started queued、撤权，业务/队列/全部四 CP不变。

N01 首2fail为测试夹具：另店external_shop_key=demo撞当前唯一约束；显式创建后全表数误当增量、漏库初始技术任务。改用独立另店key及冻结before增量，不改业务逻辑；13/13随后完整通过。actual允许/PRD-J01缺项/非法/附加采购/范围窗口不支持/跨店未知店/来源不匹配/无身份/无operator/CSRF-Origin/strict JSON输入/撤权与 stale actor均核，全部业务表（认证会话/登录凭据限流表排除）和四CP canonical字节不变。ready后仍零写；显式原创建才新增任务2/jobs2/receipt1、原key回放10及回读唯一，approval/exec/outbox/SDK/model0。

## 完整检查与待门禁

targeted workflow原回归88pass/6.41s；N01 pure48+原runtime OpenAPI2=50pass/0.75s；后补独立 OpenAPI 引用闭合 pure1，当前51pass/0.71s。PG后仅补JSON Schema的独立错误/安全scheme闭合及pure引用检查、公开authority文档名等价换行和文档；业务Python实现未变，最终精确CI仍须跑本源完整441 PG。全量 scripts.check 首次在目录scan因公开 x-authority-contract 文档名 generic-api-key 两误报 exit1（index/git0）；只将等价JSON字段值另起行，scanner规则/allowlist未改，完整重验实际 exit0：1531 offline pass/441 integration deselected/93.00s，Ruff384/mypy282/Markdown98，Node24.21/tsc/npm42 audit0/Python95 audit0/lock99/三scope scan0。补最终文档后Markdown99/errors0；pre/post index与commit扫描随后单独核。原 Deprecation/fork警告保留。

新增原 workflow profile 只允许原单任务、当前身份、原 SDK 窗口/各方法上限/两进程终止、原CP与 attempted job、已有不可变审批/决定/执行；maintenance复核。未知 IM不重发，Base未知走原B严格读回；真实跨窗 SDK/断线/真人及M1仍pending。C真实接线/UX、独立Core/Web审核、最终冻结SHA/CI/artifact pair、Root集成、正式Gate及结案待外部回执。旧cdbc P1/CI取消、旧Gatewayreap not_verified、SWC0test、wrapper1/pytest0/Issue23风险及全部旧私有资源原样保留。
