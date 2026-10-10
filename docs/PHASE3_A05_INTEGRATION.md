# Phase3 A05 最终集成与四作业 CI 交接

当前A05两修复集成导航（2026-10-11）：Root已核A精确087恢复测试/Core无P1P2+独立19PG94.91s/19pure0.89与B精确849 Linux only-owned/Web无P1P2+27contract/Linux ARM8/22.1s；原CI972双job失败、partial28actual27pass/73not_run、旧236/G1G2cleanup0成功及unknown assertion trace全部保留。原Core外层zsh reserved status wrapper1不冒称整wrapper0；B两次SWC准备环境0test失败及随后公开registry锁定npm准备/断网ARM8成功分记，Root停止回执核对另行记账。A已普通merge两精确fix无冲突，backend/锁/sharedCI原195行不改；新x64四CI/修复后real24/main/postmainCI/Issue33仍pending，阶段in_progress。详见[两修复集成](PHASE3_A05_TWO_FIXES.md)及[STATUS42](STATUS.md#42-a05-两项修复独审核收与正常集成候选)。下方原候选/失败/当时待核按历史保留。

历史最新A05失败/修复导航（2026-10-11）：972最终增量独审5480825374无阻断，但CI38086696815实际frontend与phase3均失败，pg-pair正确拒绝失败分区；旧236/G1三/G2六/cleanup0成功，首P3模块28中27passed/1failed、后73not_run，完整Gate不通过。A在新固定30min/两轮owned窗口已证实T2提交与wait CP持久化的合法间隙，原CI具体assertion未捕获/根因unknown保留；仅测试同步修复与19定向PG/19pure通过，backend/共享CI/B不改，资源已停/保卷。新精确fix待原Core独审及Root合已审B修复后一次四CI，不push/body/main/关Issue。详见[恢复修复](PHASE3_A05_RECOVERY_FIX.md)及[STATUS41](STATUS.md#41-a05-实际ci失败与恢复测试同步修复)。下方972候选/既有Gate回执保留，不覆盖本次失败。

2026-10-11，Root 在 A03 与 B 最终源码、独立审查及各自精确三作业 CI 核收后，正式释放本批。A 沿用 WT62c8、`codex/phase3-approval` 和 [Draft PR37](https://github.com/aning0922/commerceops-agent/pull/37)，只负责正常集成、共享 frontend CI 与阶段文档。完整四作业 CI、最终增量独审、main 合并、同 main 合后 CI 和 Issue33 关闭均仍待正式回执；不预写最终提交 SHA 或阶段完成。

## 已核前置证据

| 来源 | 精确源码与独审 | Root 已核实际 CI |
|---|---|---|
| A03 | `052d4ecb9e24a8c8164938c1d7bb20a92ba89c3e` / tree `e383962013633768e9c7b4216693c6db48992a00`；[Core review 5480529395](https://github.com/aning0922/commerceops-agent/pull/37#pullrequestreview-5480529395) 无阻断，继承748 business bytes及独立101真实P3、32 HTTP/22 operations | [38079599247](https://github.com/aning0922/commerceops-agent/actions/runs/38079599247) quality/phase3/pg-pair 全 SUCCESS；actual checkout `319eee3e9f37ad1e8ed78a76c1ada4c752fece46`，parents main59+052、同tree；1025offline/126.34s、236旧PG/257.24s及全部101P3；full337、3G1/6G2、两侧cleanup0和安全artifact配对 |
| B最终 | `a65eb22884c0e6c5b612833766b555ea0ae715b7` / tree `43d9a43341949905b346e7cdb3aa8520ccdc62f0`；[Web review 5480795768](https://github.com/aning0922/commerceops-agent/pull/36#pullrequestreview-5480795768) 无新增P1/P2；原Reviewer自有 fresh PG/API/Next/singleWorker完整read7/write10/items7、native200和20SKU/T6不变量通过，Root逐核四metadata及39辅助源码哈希 | [38085161901](https://github.com/aning0922/commerceops-agent/actions/runs/38085161901) 三后端job全 SUCCESS；actual checkout `8bca9e3f4feb110f0c5263dcff646eacded42425`，parents052+a65、同tree；1057offline、337PG=236+101无重漏，3G1/6G2/cleanup0及source/tree/tool/lock/fullcollection配对；没有frontend job |

上表为 Root 已核回执，不是 A 新跑 PG/Web。B 作者完整24和1057offline证据见[原B交接](ux/phase3-implementation.md#b04-真实接线与可复现入口收口)，不替代独审。d889裸文件CLI在任何资源前 `ModuleNotFoundError:scripts` 的P1保留；a65仅UX文档9+/1-，13helper及全部业务blob不变，正式入口为从精确checkout根运行 `python -m tests.e2e.web.run_live_batches`。无PYTHONPATH的 `--help` 由B和Reviewer实际核exit0，不把零资源help记作24Web。

## 正常集成与字节继承

A先本地普通提交唯一owned frontend CI为 `d476292d4c1f2bfcfabe319646a7db51d4922058`，未单独push；再正常merge精确a65为 `53cdffa44d2c1d6b77f8f7cb67e07bf9d33ccee3` / tree `25fce471dd6c3ee72e5b7eb38d5ec5935426a847`，parents d476+a65，无冲突、无历史改写。相对052，backend/迁移/DTO/业务tests/scripts/Python锁/Compose不变；相对a65，frontend/npm锁/全部Web tests/原UX交接不变。共享workflow仅追加独立frontend job，原quality/phase3/pg-pair全部字节保持。文档随后单独正常保存；最终source/tree及实际CI checkout由PR37/Root验收receipt绑定，避免提交内部自指未来SHA。

Root另核原独立p3_contract_review对精确d476 / tree `02c6b58f870a6466fd7025532d54677f754c83dc` 的195行共享CI增量：无P1/P2，YAML/精确a65七helper语法、旧共享文件继承、23min/default三stage/13hash/7+10+7标题/四安全JSON/清理与后台隔离通过。最终文档与冻结继承仍待同Reviewer增量核收，实际完整四CI容量未证明。合并时530个A既有tracked文件逐字节保持，199个B继承文件仅来自已审分支，B产品/harness blob diff0；本批随后改动只在A负责的八份阶段文档。

## 新 frontend job 的完整合同

独立ubuntu-24.04 job25min，第一步骤在checkout前登记UTC+23min，后续沿用同一截止不重置。checkout精确 `${github.sha}`、read-only仓库权限和既有官方Actions pins保持；固定Python3.12.13/uv0.11.25，既有bootstrap校验Node24.21.0，显式核npm11.19.0。scan、uv frozen、npm ci/工具链/typecheck/schema/26contract/audit/build、锁定Playwright Chromium Linux依赖、原Mock13页面与B04联动8页面串行执行。准备命令按剩余截止扣75秒清理和10秒kill grace，旧PG分区每条300s及完整337不调整。

正式live CLI不传stage过滤，`--owner ci`、本checkout和RUNNER_TEMP全新空0700目录、同首步截止。每段独立project/卷/账号/org/facts，先reap种子OS进程再起单Worker/全局单Graph；真实API使用session/CSRF/Origin，电商来源为Mock fixture，ACK丢失与superseded分别标受控transport/PG fixture，不冒称自然故障。native200使用headless私有profile/background tab，任何用户Chrome、可见窗口、OS键鼠/焦点均不操作。

开始live前只删除本checkout三个已提交reporter样本，防止旧passed JSON继承。本次CLI exit0后，项目专用内嵌检查要求result三个stage完整顺序、passed/invariants真、test_exit0/provider0/PGfalse/PID0；window闭合metadata字段、实际owner/UID/currentcheckout/当前HEAD/同build、原截止、停止时间不晚于截止、seed/test0、全部child已reaped/正常或TERM退出、13确切辅助源码hash匹配；items native_zoom passed。reporter固定字段/模式及trace/video/自动screenshot off，完整实际标题集合精确匹配本checkout read7/write10/items7，24全passed、无漏项/skip/重复。

只有上述验证成功才上传四个点名安全JSON：新private目录下 `read/window.json`、`write/window.json`、`items/window.json`、`result.json`，固定官方upload pin、1天保留。不上传整个目录、accounts/config/settings/私有事实/密码/DSN/nonce/receipt body/pw-private/raw stderr/trace/HAR，原PG双artifact/pair不变。A已从a65 Git blobs核三份batch-final-window sample的安全字段、audit输出及13hash逐项一致；sample.source_commit为bc15运行基线加当时WIP，不能改称a65实际checkout运行。

作者完整薄入口约12m14s（不含依赖/build准备），read28.414s/write327.172s/items327.039s，后两段含自然300s登录滑窗。A未追加本地101PG/24Web或资源；新四作业job实际23min容量、完整frontend Gate均pending最终精确CI，不能由历史耗时或静态检查推断通过。

## 本批检查与剩余裁决

本批集成后实际 `uv run --frozen python -m scripts.check` exit0：1057offline passed/337integration deselected/84.90s，两个既有lark-oapi弃用warnings；69Markdown0error、Ruff全仓lint/266format、mypy193、frozen锁检查、Node24.21.0工具链/npm ci/frontend typecheck、Node与95Python锁包漏洞0，current/index/fullgit扫描0。另实际22-operation `check:read-schema` exit0；无PYTHONPATH模块 `--help` exit0且没有运行资源。YAML解析、4段Bash语法、4段Python编译、diff check及原workflow字节比较通过；文档最后收口另核docs/static/提交前三scope。初次新增三mode元组比较被generic-api-key规则误报1，等价拆三assert后三scope均0，规则/222条及原四精确例外未改变。未本地重跑101PG/24Web/build/Mock browser，原精确a65产品与harness已独审，新完整四job实际运行由最终CI证明。

下一步为本批最终冻结独立增量Review及精确四job CI；PR37保持Draft，标题/正文在最终push前一次更新，后续用评论补证据。main实时仍 `59b350cb719a9d2fed3f68b1ee598fa0a9b97875`，A不合main、不关闭阶段Issue。Root核必要Gate后才正常main merge，并以同main CI与[Issue33](https://github.com/aning0922/commerceops-agent/issues/33)结案回执确认正式阶段完成。

原333/988作者证据、2e0独审23/1失锁失败、B03/A03旧CI失败与取消run、B04首失败/tail、A02旧12/8和旧Review fullcheck not_verified均保留，不能借新Gate改写历史。Phase1有限G1/G2/G3与Issue23 not_identified/risk_accepted保持，M1设计m1-ui/0.4.1-freeze-rc/18页冻结不追加视觉批次。human_feishu/正式Card/Base/Woo业务写、平台扩权、生产/Phase4、多Worker R02–04、p95/40×3/95%/自然故障/长期TTL/原G3收到后过滤仍未授权或not_run。零新增paid provider，Phase2既有actual1不续跑。D1=2026-10-10/D30=2026-11-08、总300h与Phase3 A32+B18+Review10=60h不重置，人工H/L not_reported。
