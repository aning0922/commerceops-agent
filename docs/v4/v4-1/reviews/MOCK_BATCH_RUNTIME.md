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
