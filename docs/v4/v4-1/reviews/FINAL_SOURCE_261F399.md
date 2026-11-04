# V41 261f399最终组合来源核收

2026-11-04（台北）。结论：`ACCEPT_EXACT_261_SOURCE_COMPOSITION_RUNTIME_MOCK_VISUAL_PENDING`，未发现本组合新增P1/P2或遗漏已审修复。精确source `261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e` / tree `34da95131e04d7360ea8aa5250ea40215bcb0713`。本轮仅组合字节/档案及证据层级核对，不重做Native/effect已审全逻辑，不预签新运行。

## 六条差分与原冻结来源

相对已核fbb29a4，全部非文档差分恰好下列六路径，逐Git blob比较相等：

| 路径 | 原冻结来源 | 最终SHA256 |
| --- | --- | --- |
| frontend/v41-e2e/native-capture.ts | `c8e817a587c6b65df520f8171e418c1637bf5822` | `6d542007d24806bde5590f369eaeeddb97d6d5692b5ea48e8b62a548d00d8802` |
| tests/e2e/v41/native_zoom.cjs | 同c8 | `0023672bfb9f648a5df2deac397fd7159dfbbc4c1cb385c5cab9d3c97396c538` |
| frontend/v41-tests/batch-tags.spec.ts | `4da424a5b82b8e35ce7d601e0a04ab6b62c35df9` | `8e5fecb11a4e42fb33d726229661518cc9ba5cfcb7fd6fd29c32a1de5d9f9892` |
| frontend/v41-tests/lifecycle.spec.ts | `af033e00dba80353d21e545b3e58809b9869eadd` | `a11f5ead9348d9620c5cd8d127b0c2393259a29bfb37b443b66a22cd80db6e67` |
| tests/e2e/v41/browser_shell.py | `bb3775cce0d1c46212878d86cb2a54615dcdf2ed` | `630279188b0f2e8a0ae90eecd419954d2f3db2c45098cdc3fbe30fdeb8bcd275` |
| tests/e2e/v41/test_browser_shell.py | `7b43cba7d7ea80d4723711f6011e4c0f6f1fe6e9` | `4fa6cd40f5d401dbee7e03f96f140514a5023a11195e79896c0bfbb045b1e282` |

bb3775原提交确为261祖先。独立将7b父consumer中的唯一6fa966旧pin替换为002367新pin后，其完整文件与最终consumer相等，证明合入的是已审effect逻辑加精确pin同步，而非其他父校验改写。CJS实际hash、TS moduleHash与Python NATIVE_MODULE_SHA256三者现均为上表002367，关闭前轮“Python待同步”的组合事项。

## 权威边界及未变保护

已读组合内 `MOBILE_EFFECT_AUTHORITY_7B43CBA.md` 最终独审：公开ActionReceipt无effect_count，consumer只接受明确None，不把缺字段/伪造数字当合法；import以严格row_count及同原job/file uploads计数绑定。该已审修复不将UI None称作数据库效果UNKNOWN；原逐key SQL receipt/event/effects/digest/canonical request仍独立强制。没有重做其85分支或真实r9副本诊断，也未改写原r9失败。

独立字节核对final_facts.py、pg_observer.py、owned_driver.py、subjects.py，以及business.live.spec.ts、shell.live.spec.ts、playwright.config.ts、live-business.fixture.ts、browser-subjects.ts，均与fbb相等。故原SQL失败传播、当前身份/权限、原pending/key/journal、NativeTiming、两标题/240秒/retry0与业务步骤没有在组合中被改动。

backend、scripts、tests/v41/backend及.github与fbb/e7/4fec四源子树一致。完整tests差分对e7仍仅三项browser_shell/native_zoom/test_browser_shell，所有PG测试其余集合未变。按原LOCK_FILES提取14项，最终/fbb/e7/4fec字节相同，并逐项匹配Root engineering.binding的文件hash。frontend/components、frontend/app、frontend/lib三子树均与fbb完全相同，包含已审批量P2关闭、focus scope/view保护、原pending/context/client/schema；本轮没有将QA/Mock差分误列为产品变化。

## r10 archive与proof

授权目录 `/Users/aipuli/.codex/worktrees/commerceops-v41-control/commerceops-agent/.audit/v41-final-r10`。独立核source/tree、六路径差分与六个equal_subtrees，均与Git复算相符：

- incremental-source-proof.json SHA256 `1c388cb6c8137ee4c4f47f2d4491d218530de730651e9327b8f4b1cec22425ce`。
- engineering.binding.json SHA256 `f68b457e58d3e4926c12c27485ac818f8b9e299740f09fe23797fcebf0938591`；本轮核source/tree/14文件，未重测登记runtime/binary。
- source.tar SHA256 `f7526d9e27ffe65762d740fe180c70bb9bec67469ea6c3a3e33b45cbb1fd6a55`；只读逐项复算全部1858个非目录条目的Git blob与普通/可执行/symlink模式，完整等于261Git树，无重复、缺失、额外或字节/模式差异，未解包执行。

旧e7 PG、4fec工程、既有HTTP/browser及fbb/r9 build均保持实际原source；未变范围可按字节证明解释证据复用，但不改挂为261已执行。Root转交的独立about:blank Native lab及三markers检查仅属工程采集证据；本轮未读取/重验实际图片，不据其签产品页面、同会话业务或视觉验收。261受影响Native/parent/Mock仍需各自实际新source运行、原件/SQL/独立清理与视觉证据，当前不预签r10。

本轮静态字节/hash/集合核验native0，无WIP读取、测试体/Full重跑、服务、PG、Docker、浏览器或网络操作；仅本文件经指定changed-file/index预检普通冻结，不push，也不释放资源窗口。
