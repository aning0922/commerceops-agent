# V41 fbb29a4 最终组合源码核收

日期：2026-11-04（台北）。结论：`ACCEPT_EXACT_SOURCE_COMPOSITION_RUNTIME_AND_VISUAL_PENDING`。精确 source `fbb29a429b7f680328ab4451a717adb3ad2d99c1` / tree `ef6d8230ac4b58401af2771d722064aadacc5eed`。本轮未发现集成新增P1/P2或丢失已审修复；只核组合字节、来源和证据层级，不重做既有全逻辑，不签新运行、视觉或阶段完成。

## 已审切片与最终字节

相对e7完整非文档差分恰好17路径，下表逐文件与对应原冻结Git blob比较均相等，没有未归属代码差分：

| 最终路径 | 精确冻结来源 |
| --- | --- |
| business-pending.module.css、v41-batch-tags.mjs/.d.mts、batch-tags.test.mjs | `a7e5f9ff4b53a956390c0807c3efcad135c9047a` |
| frontend/components/v4/demo.tsx | `cc5c9a6b3a361c2c451c5652023b9e73b5488f9d` |
| frontend/components/v4/business-pending.tsx | `ee547b4a6b0823ac9a652081d507b157b22b86d5` |
| frontend/v41-tests/batch-tags.spec.ts | `99a48b54eff83733aa805465acc68c2619ffd91c` |
| frontend/v41-e2e/business.live.spec.ts | `ec7b6717f5a4421f494b91c9eed803178e7039cd` |
| shell.live.spec.ts、current-facts-correlation.test.mjs | `859dbad0764ce280f244f539880fd97024274b4b` |
| owned-cdp.fixture.ts、owned-cdp.argv.json、owned-cdp.fixture.test.mjs | `c154777f8689da589a25a253a6c234bfb7891444` |
| tests/e2e/v41/browser_shell.py、test_browser_shell.py | `d36a514e307107e61834e1722739252f94902cd8` |
| tests/e2e/v41/native_zoom.cjs、frontend/v41-e2e/native-capture.ts | `217baea74687490fb4a45f108f62841f57d2f931` |

前述路径按各自components/lib/v41-e2e/v41-tests原位置核对，并非同名文件模糊匹配。已审cc5“POST之后读回失败只能UNKNOWN”、ee547的editScope+view双回焦绑定、ec7自动header焦点断言、99a Mock完成边界、859 Request/UI关联及c154归属/原生退出边界均保留原字节。既有review与历史HOLD/失败未被覆盖。

读取组合内 `NATIVE_217baea.md` 与 `QA_MOBILE_PARENT_9726885.md` 的最终增量结论：Native217只在已审范围内改locator/安全阶段；父d36完成原文件摘要/status、scope/snapshot及job.version绑定。父审查中曾提出的全局journal顺序/sidecar已正式撤回，不作为本组合新Gate。本轮复用其精确独审结论，未把旧误判重新引入，也未重新运行其pure矩阵。d36原提交确为fbb祖先；最终两父文件字节分别为 `181301fde7be5984ef9929a5022bd537527b0bd7de07b772adffed30ef273499`、`8e2a4ce7d9c5a44b4fafb44e13186e3fb9ad0914f0049384cd18f2d40cadf507`。

Native实际模块SHA256、TS caller moduleHash、Python NATIVE_MODULE_SHA256三者独立相等：`295bf2c61e7cd30e7a47d7368d93fbadb40764fb41072a9119b5d78ed925689e`。无旧3d71 pin残留于这三处，无删除guard的集成绕过。

## 未变范围与archive证明

与e7及4fec逐树比较：backend、scripts、tests/v41/backend、frontend/app、.github均相同。e7到fbb全部tests差分只有上述browser_shell.py/test_browser_shell.py/native_zoom.cjs，PG测试其余全集未变；不仅仅检查单个V41 PG目录。

按冻结pg_ci_evidence的LOCK_FILES精确提取14项，最终/e7/4fec逐文件字节相同，并与Root engineering.binding.json的14项hash一致。另显式核旧v4/v41 pending/context、v41-client/schema、final_facts、subjects、browser-subjects、live-business.fixture及Playwright config共11个保护路径与e7相同。故原审批/身份、UNKNOWN、持久key、只读恢复、journal/final SQL及固定两标题/timeout/retry保护没有在组合中被额外编辑。

Root允许读取的 `.audit/v41-final-r9` 原件位于control工作树。独立核：

- incremental-source-proof.json SHA256 `ee771843daed29cdc47bcd50ebc813552796bd9f0a5a140df157be399a262143`；source/tree、四个equal_subtrees、相对eb30的12项代码路径及Native三pin与Git复算相符。
- engineering.binding.json SHA256 `20c2283e2c292942f6d2643e60f84e07b3ea9311a267b95e4effa2987a2e94dc`；source/tree/14文件hash已独立核对。runtime/binary字段仍是Root登记，本轮没有执行工具或重测live binary来追加运行结论。
- source.tar SHA256 `aa3b0733062b6731d0b7703fe13dd92d7fc889bf8b30fbd5600c64e82ecfa36a`；只读遍历全部1844个非目录条目，逐项复算Git blob hash并检查普通/可执行/symlink模式，与fbb递归Git树完全相等，无额外、缺失、重复或内容/模式差异；没有展开或运行archive。

随后Root `c9fd4b9` 相对fbb仅PUSHES.json文档增量，已核diff路径集合；它不改变本fbb运行源码绑定，本报告仍固定fbb SHA/tree，不将后续文档SHA当实际运行来源。

## 证据层级与剩余Gate

e7双线FullPG及严格配对保持原source/tree，已冻结回执为596+177=773、交集0；本轮仅确认相关源码与锁未变及读取已审结论，没有重读原PG运行资产或重跑checker。4fec完整工程保持原SHA。字节等价是复用对应未变范围证据的依据，**不是fbb已运行FullPG/完整工程**，也不将旧e7/4fec结果改挂新SHA。

新产品批量/焦点、Mock、业务mobile、Shell NoDefaults/currentFacts、QA父收验和Native模块各有源码/纯组件核收；仍需依Root新精确source完成受影响检查及实际Mock/browser/Native、原始回执/SQL/独立清理与视觉验收。旧r1及各browser失败/UNKNOWN保留，collect数量不变成PASS，合成PNG fixture不变成视觉证据。原NativeTiming只按已核本地请求/回执层解释，不扩为独立wire抓包。

本轮只读Git、三份授权archive/proof原件及冻结review，运行静态字节/hash/集合比对native0；无测试体、Full重跑、浏览器、服务、PG、Docker、网络或远端操作，无WIP读取。仅新增本文件，指定changed-file/index预检后普通冻结、不push。此源码核收不释放资源窗口或未来r9运行结果。
