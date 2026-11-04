# 批量 React Mock 实际运行原件核收

2026-11-04（台北）。当前结论：`R1_R2_FAILED_CLOSED_RECORDS_ACCEPTED / MOCK_SUITE_NOT_ACCEPTED`。本报告只读核收两次已有运行的失败与关闭记录，不重跑测试/资源，不修改产品或测试代码，不将后续静态修复当作动态通过。后续新的实际运行另行追加，旧失败与未知项保留。

## r1/r2 来源与实际结果

| 项目 | r1 | r2 |
| --- | --- | --- |
| Source | `5acf03ae30807c160aa110035127a4e308e95da9` | `fbb29a429b7f680328ab4451a717adb3ad2d99c1` |
| Tree | `9c967e247d24a2acc36f1e4f6d827763e3d13a47` | `ef6d8230ac4b58401af2771d722064aadacc5eed` |
| 原件目录 | commerceops-v41-ui-fixture-batch-r1 WT 的 `.audit/v4-1/ui-fixture-batch-r1` | commerceops-v41-ui-fixture-batch-r2 WT 的 `.audit/v4-1/ui-fixture-batch-r2` |
| 检查开始 UTC | 09:45:21.900524 | 10:05:17.242282 |
| worker 结束 UTC | 09:45:36.673089 | 10:05:36.734355 |
| 独立关闭采集结束 UTC | 09:46:37.237778 | 10:06:24.906047 |
| 实际测试 | 1 PASS / 1 FAIL / 31 NOT_RUN | 1 PASS / 1 FAIL / 31 NOT_RUN |
| 原测试耗时 | 2496.901 ms | 6453.005 ms |
| 端口 | 13487 / 18487 | 13488 / 18488 |

两个 WT 均位于 `/Users/aipuli/.codex/worktrees/`，仓库目录为 commerceops-agent。独立核 closedfinal.json：r1 SHA-256 `666ffe6a875c08d7dcb27113c348956d1b65f8a39342333ee3c91c22fbbcea42`；r2 `9725809f5100d17a3ad10e16e847ae02e8ae4a3e60feacca217e887ba70991c8`，后者与 Root 指定值一致。r1 引用的 24 件原始 artifacts、r2 的 29 件均逐一核 hash 匹配，包括 Playwright JSON/error context、build/raw logs、registrations、checks、source snapshots 和 outer receipt。

原 probe argv 显式使用原 frontend/playwright.v41.config.ts 与四个 spec，workers=1、retries=0、forbid-only、max-failures=1；原 Playwright config 对应 repeatEach=1、fullyParallel=false。独立解析各自 JSON：共 33 项，只有两项实际 result，其余 31 项 results 为空。stats.skipped=31 在这里对应首错停止后的 NOT_RUN，不能写作 31 项已运行的 skip 或成功；flaky=0，实际两项 retry 均 0。两次通过的都是“两选中项不同 durable keys 与顺序读回”用例，失败的都是 first unknown 保留原 pending key 用例；不能将这两个不同 source 的局部结果拼成一次完整 33 项通过。

失败位置分开保留：r1 的 batch-tags.spec.ts:82 实际断言 f.requests 长度应为 1、收到 0；此前 UI 待核计数断言已经过，不据此猜测 dispatch 的完整运行顺序。r2 的同文件:86 在点击原操作核对后，等待“原操作仍需核对；未重复提交。”可见，5 秒超时未找到元素；原请求数/旧 pending key 的前置断言已经过。两次 Playwright stderr 均空不代表测试无错，具体错误保存在 JSON 与 error-context。Root 已转交仅 Mock lookup 顶层响应的后续静态候选 `4da424`；本次未审该后续切片，也不把静态解释写作这两次失败的唯一动态根因，后续修复有效性需新实际证据。

## 原 native、清理与 r1 更正边界

两次 build native 均 0，Next 原 build 日志显示编译完成；probe-command 原 native_exit=1、signal=null/error=null，worker 的 outer-receipt 均记 native_exit=1、parent_timeout=false、notes=[]。Root 回报 outer native=1；本目录 outer-receipt 字段记录的是 worker native，原 runner 最终以 `timed or notes or native!=0` 返回失败，支持该失败传播，但不把 worker 字段改称一个独立 outer wait 原件。cleanup 原 native 记录均为 probe=1、web=143、dummy api=0；web 停止码不能抹掉 probe 失败。两次均首错停、未在同案自动重试。

逐一核原 api/build/probe/web registration 的 PID/PPID/PGID/birth 与 closedfinal 嵌入值一致；原关闭采集对四个登记 PGID 的 `/bin/ps -g …` 均 native=1、stdout/stderr 空，worker/outer 的原 absent 结果也为 native=1、空输出。各案两端口原关闭检查同为 native=1、空输出、closed=true，与 checks.cleanup 对应。这里接受的是当次原采集记录，本轮没有重新运行 ps、探测端口或发信号。browser native exit 保持 `NOT_EXPOSED_SEPARATELY`，不能用组已消失替造独立浏览器 exit 0。

r1 原 closedfinal 的 independent_resources_closed=false 完整保留：它将 task-private 的 playwright-transform-cache-501 列为 profile 剩余。补充 `closedfinal-profile-classification.json` SHA-256 为 `2998fe171a7307f598901c147f102b1b3dc91956536204a2d8d41c67aba19256`，精确引用原 closedfinal hash，分类为 Playwright TypeScript transform cache，记录 known browser profile paths 为空、原 groups/worker/outer 已消失及 ports closed，补记 independent_resources_closed=true。这是分类更正，不是重新运行或把失败转为通过。原 false、补充 true 与保留缓存的事实分列；r1 运行时 UID 仍 `NOT_CAPTURED_IN_ORIGINAL_REGISTRATION`，collector_euid=501 不能补造运行 UID。

r2 有独立 worker-uid-evidence 与四组 uid-evidence 原件。逐一核采样 identity 等于该案 registration，实际 ps_native=0、stdout=501、actual_uid=collector_euid=501；不能将这些证据移用到 r1。r2 closedfinal 记录 private transform cache 保留、known profile paths 为空、independent_resources_closed=true。两案旧 artifacts、失败原文、r1 UID 缺口及分类补记均未改动。

## 源码、工具、依赖与生成文件

每案 source-before/after 与 build-source-before/after 四份记录完全相等。独立按原 state 算法只读重算当前 tracked 文件和 Git HEAD/tree/status，也与各案四份记录一致；r1 tracked digest 为 `3f344ec3eb131404c4dfc5710dac1a4282bddf7e228e191c4502043f31c2f9bf`，r2 为 `9920fae2a4c51e0758a5e121095d3ba4039978b704ee8c436dfe197ed6f7f362`。该算法不同于组合离线包的 JSON 行摘要，不能仅比较摘要字符串就推断同 SHA 漂移。

读取对应冻结 prep plan/pins/runner（不读 sourcepending 或后续 WIP）：r1 使用 ui-fixture-batch-prep 的 plan.r3/pins.r3/ui_fixture.batch.r3.py，r2 使用 ui-fixture-batch-r2-prep 的 plan/pins/ui_fixture.batch-r2.py。prep 名中的 r3 是 r1 准备迭代名，不是未来第三次实际运行。两份 plan 对 pins 的 hash 均匹配；各案原 runner 启动与 finally 都调用 verify_pins，原 checks 记 pins_unchanged=true、closedfinal pins_mismatch=[]。本轮独立重算每案 4815 个工具/helper pin 和 12178 个 node_modules 文件摘要及完整清单，全部相符；已知空 npmrc 仅核零字节，不读取配置内容。pins 声明 Node 24.21.0、Playwright 1.64.0 等版本属于工具绑定，不改称实际浏览器 version 回读。

ignored `frontend/next-env.d.ts` 生成变化单列：build 前 296 字节，摘要 `0f70629890b72a0a82e91972cc032c04b658b26c265373cb711cf576bfbf8fcc`，引用 .next/dev/types；生产 build 后 288 字节，摘要 `1862ac4bbbc5192d4bf562161df66ea547ed3e67173100656ab606ae9797db2b`，引用 .next/types。原记录证明未 tracked、被既有 frontend/.gitignore 排除；不得把 tracked unchanged 写成工作树所有字节不变，也没有为通过校验删改 tracked 内容。

两次都是本地 React Mock UI。原 dummy-counts 均 total=0、status=503、DUMMY_ONLY_NO_BUSINESS_API；不因此升级为真实业务 API/权限/PG/provider 证据。原 real business/PG/provider/Native200 均 NOT_RUN。此次核收接受失败关闭记录及明确更正边界，Mock suite 仍未验收；不签真实移动端、完整 Full/FullPG、阶段完成或新窗口授权。等待后续新运行的精确原件后，在本文件独立追加。

## r3 失败补记与 r4 完整 Mock 运行核收

2026-11-04 同日追加。当前结论：`R4_MOCK_UI_33_PASS_CLOSED_ACCEPTED / R1_R2_R3_FAILURES_PRESERVED`。仅接纳 r4 本地 React Mock 层实际运行及其关闭记录；上文 r1/r2 的所有失败、NOT_RUN、UID 缺口及分类更正保持原文，不用 r4 覆盖。独立读原件，没有重跑测试、启动服务/浏览器/DB、探测端口或重消费 registry。

| 项目 | r3（保留失败） | r4（本轮接纳的 Mock 运行） |
| --- | --- | --- |
| Source | `f0c6551e420801d790720a502967fe0ae0160008` | `261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e` |
| Tree | `0666dbc18f3a4d5bdf55b22f08527c4d94bfd6b3` | `34da95131e04d7360ea8aa5250ea40215bcb0713` |
| closedfinal SHA-256 | `e0cdb733b8297b5777b7b67e6a2de829251875a8dce63f56fea209ad08a5dd72` | `1e0681b8a170b25511927111b924fa7dae886b9b074de504230ff681338245d1` |
| 检查开始 UTC | 10:16:18.081881 | 10:45:16.100754 |
| worker 结束 UTC | 10:17:07.892619 | 10:46:05.071165 |
| 独立关闭采集结束 UTC | 10:17:40.018565 | 10:46:35.692180 |
| 实际测试 | 29 PASS / 1 FAIL / 3 NOT_RUN | 33 PASS / 0 FAIL / 0 NOT_RUN |
| Playwright 实际耗时 | 36753.791 ms | 33321.905 ms |
| build / probe / worker | 0 / 1 / 1 | 0 / 0 / 0 |
| 原案端口 | 13489 / 18489 | 13490 / 18490 |

原件分别位于 commerceops-v41-ui-fixture-batch-r3/r4 的 commerceops-agent/.audit/v4-1/ui-fixture-batch-r3/r4（共同 worktree 根与上文相同）。逐 hash 核 r3 closedfinal 引用的全部 29 件、r4 全部 28 件原 artifacts，全部匹配。r4 playwright.json hash `7b9b657408d337bd1f93bc77afa82eef3db3e0c73aa9275798fd224e461e98a8`，checks.json hash `3c176478d209c1e4bf9332194775b450a5864bc9c033d7b42416995d32a52a09`；r3 对应为 `40f39af67787b0c92da29d7153159c599d0e393aa29372f5f3337cfb520a6cd4` 与 `5d5c5136cb9564fbd63d4b1157dd76c0e7122729ac5e3f5a5dd275f32c98e63f`。

独立逐条核 r4 的 33 个唯一 file/title，与本案 collect.final.json 全集精确相同；每项恰好一个实际 result，status=passed、retry=0、expectedStatus=passed。分布为 batch-tags 9、import-flow 2、lifecycle 19、shell 3；stats expected=33/unexpected=0/skipped=0/flaky=0，原 errors 空。四 spec 原命令保留 workers1/retries0/repeatEach1/max-failures1/forbid-only/fullyParallel=false。本次是实际执行，区别于此前 261 离线包的 33 collect；九个 batch 包括两项顺序成功、UNKNOWN/409 停止与原键恢复、shop/close/query 中止、390 焦点/Escape 及 COMMITTED 后 409/403 readback 两分支，均有各自真实 passed result。不是把 r3 的九项通过拼到 r4。

r3 同样独立核到 33 项集合，其中九个 batch、两 import-flow、18 lifecycle 通过，lifecycle 的 changed identity generation clears the prior edit draft 失败，三个 shell results 为空，按 NOT_RUN 保留。实际失败定位 lifecycle.spec.ts:170：身份 generation 更新并重选店铺后，等待“编辑标签”按钮可见 5 秒超时。Root 转交修复 `af033e00dba80353d21e545b3e58809b9869eadd` 的冻结差分只改该 Mock：seed-summary 返回刷新后的 generation，严格核 GET/path/shop/header，并等待对应 summary，原草稿清除断言保留。r4 source 中该 spec 字节与 af033 相同，仓库落地记录为 `d6dff815bdd222269b66925b469380c77d6fe172`；不要求二者具有直接祖先关系。此说明源码修复及新 r4 运行通过，原 r3 仍 failed，不改原回执，也不把静态解释升级成捕获了唯一网络动态根因。

r4 probe-command 原 native_exit=0、signal/error 均 null，worker outer-receipt 原 native_exit=0、parent_timeout=false、notes=[]；build 原 native0 与编译完成日志对应。Root 回报 outer 原 native0，冻结 runner 的失败传播返回表达式与这些原记录一致；outer-receipt 的字段仍只称 worker native，不伪装另一份独立 outer wait 原件。r3 同层 probe/worker 为 1，保留失败传播。两案 web cleanup=143、dummy api=0，r4 probe cleanup=0、r3 probe cleanup=1；web143 不改写为正常业务 exit0，也不覆盖 probe 结果。

两案四个 api/build/probe/web registration 与 uid-evidence 逐一匹配 identity：运行时 worker 与各组 actual_uid=collector_euid=501、原 ps_native=0/输出501。关闭原件对四组、worker/outer 均记录 absent、native1、空 stdout/stderr，原端口检查也为 native1/空输出/closed=true。r4 的 13490/18490 与 r3 的 13489/18489 全关闭，independent_resources_closed=true；known profile paths 为空，task-private transform cache 保留。browser_exit_native 仍 `NOT_EXPOSED_SEPARATELY`，不因 probe0 或组消失造 browser native0。本轮没有新 ps/lsof 或端口 probe。

两案 source-before/after 与 build-source-before/after 四份原快照一致；按各自原 state 算法独立只读重算当前源码和 Git 状态，也与四份一致。r4 tracked digest `fa0fad1ab3c3cedf5dfc7f880bbda18c596457039d3912a9aee36108bde8ad12`；r3 为 `a166672a197dbd5b2cf3e4ecd94893ced1c1049df35079582a7d5f6adb98b872`。读取各自冻结 prep plan/pins/runner，未读 sourcepending/WIP；每案 4815 个工具/helper pin、12178 个完整依赖文件清单/hash 均独立重算匹配。原启动与 finally 的 verify_pins、checks.pins_unchanged=true 与 closedfinal 空 mismatch 相互吻合。ignored next-env.d.ts 仍按原件单列 296 字节 dev 引用→288 字节 production 引用，前后 hash 与上文相同，不混进 tracked unchanged 声明。

r4 dummy-counts 记录 6 次 GET /api/v4/demo/session，固定 dummy status503、DUMMY_ONLY_NO_BUSINESS_API；不误报该案 dummy 请求为 0，也不把它写成真实 API。r3 dummy total0 单列保留。r4 的 33 PASS 仅证明这组本地 Mock UI 路径，真实业务权限/API/PG/provider/Native200 仍 NOT_RUN，真实产品 Native、运行/PNG审查和阶段验收另由其原件证明。旧 r1/r2/r3 失败不被删除或重命名为通过；未借本回执复活旧窗口或授权下一次运行。
