# V4-1 完整 UI 冻结独立审查

日期：2026-11-04（台北）。结论：`HOLD_UI_P2`。本次发现三项 P2，未发现可据当前 UI 源码确认的新增 P1；不签完整 V41-01—06、真实业务权限或端到端验收。

## 精确范围

- 审查 source：`622ee6e021b4fa33efc6a5fe4ffff436f429ad9a`，tree：`452c7d3bab8410ce4ccb780affc7bdfdd346ca06`。
- 独立工作树 `commerceops-v41-ui-review/commerceops-agent`，branch `codex/v41-ui-review-20261104`；开始时干净，origin 为 `https://github.com/aning0922/commerceops-agent.git`。未操作默认 checkout。
- 已接受 Shell：`c343516e78d4d227a7f705aef4dc3b73469b0e99`；前次业务 source：`301da4f61beac25646ec2fc3ad3c7df3a14488dd`；前次独审：`5a3211128d8d240b0663194c28e6f4cddbf1af5f:docs/v4/v4-1/reviews/WEB_BUSINESS_301da4f.md`。
- 合同：control `4acba0ccc97477b94d624c3a5a68ff930957f4e0` 的 CONTRACTS、STAGE_SPEC、UI_ROUTES；同时读取冻结 UI_SLICE_01 与 WEB_PLAN。审查使用精确 Git 对象，不读取 WEB 作者未提交源码。
- 本 Reviewer 只新增此报告；未改业务、测试、锁、扫描规则，未启动服务或浏览器，未访问旧环境配置或真实外部业务。

## P2-UI04：正常会话轮询卸载详情编辑器，丢失未提交输入

定位：`frontend/components/v4/demo.tsx:58,60`；`frontend/components/v4/business-pending.tsx:57`；`frontend/components/v4/write-controls.tsx:7`。

进入商品详情，点击“编辑标签”，输入新标签后停留超过一次五秒轮询。`refresh()` 在等待 `/session` 前无条件 `setDetail(null)`；详情通过 `catalog.detail ? <DetailBody ...> : ...` 条件渲染，因此 `TagControls` 被卸载，其本地 `editing/text` 状态丢失。随后即使同一 session/shop/revision 验证成功，也会重新挂载默认非编辑状态。订单履约确认组件有相同卸载路径。网络稍慢时用户可直观看到输入消失；这不是撤权、切店或版本冲突。

最小修复方向：保持现有后台权限再验证及拒绝清屏，单独保全绑定 tenant/principal/shop/epoch/generation/resource/revision 的未提交编辑状态，或使编辑器在同上下文再验证过程中不因数据暂空而丢失草稿；身份、资源或版本真正变化时明确失效，未核身份时禁止提交。不能通过停用轮询、忽略拒绝或展示旧授权数据解决。增加组件级用例：编辑后跨过至少两次轮询，输入/确认意图仍在；切店、撤权和版本变化则清除或明确冲突。本次为源码可确定的控制流问题，浏览器复现 `NOT_RUN`。

## P2-UI05：四个已声明业务子视图无数据读取分支

定位：`frontend/components/v4/demo.tsx:63,81`；`frontend/components/v4/business-pending.tsx:86`。

路由解析器接受全部十二个本阶段业务视图，但 dashboard effect 仅接受 `/v4/dashboard`，订单列表 effect 仅接受 `/v4/orders`。`BusinessPending` 对其他 01 模块路由又强制传 `dashboard=null/state=idle`。因此已授权选店后，`/v4/insights`、`/v4/dashboard/drilldown`、`/v4/orders/anomalies`、`/v4/orders/fulfillment-demo` 永远不能加载相应数据，仍显示“请选择授权店铺”或空内容。根驾驶舱内嵌钻取、根订单详情内履约不等于这些深链可用。

应由 WEB 接入受权共享查询/明确筛选与对应视图，或由 Root 明确调整路由表达，使其引导到已实现的同一能力且不伪装选店即可加载。不得据空占位签十二视图完成。以下逐项为源码接线盘点，均不等于真实 API/浏览器验收：

| 本阶段视图 | 冻结源码实际状态 |
| --- | --- |
| V4-P01-01 经营首页 | 根 dashboard 已接 KPI、期间、趋势、规则与内嵌钻取 |
| V4-P01-02 AI经营洞察 | 独立 `/v4/insights` 无读取，属于本项缺口 |
| V4-P01-03 指标明细钻取 | 根页按钮有接线；独立深链无读取，属于本项缺口 |
| V4-P04-01 商品列表 | 已接查询、筛选、分页、导出 |
| V4-P04-02 商品详情 | 已接当前对象、SKU、关联订单和标签；受 UI04 影响 |
| V4-P04-03 SKU规格 | 展示本次商品页的 SKU，界面明确页内范围 |
| V4-P04-04 分类标签 | 展示本次商品页标签，明确分类树来源未提供，不算已实现分类树 |
| V4-P04-05 商品导入 | 预览、映射、原键恢复、确认接线已有；受 UI06 影响 |
| V4-P05-01 订单列表 | 已接查询、筛选、分页、导出 |
| V4-P05-02 订单详情 | 已接关联商品、已知时间线及演示履约；受 UI04 影响 |
| V4-P05-03 异常订单 | 独立深链无读取，属于本项缺口 |
| V4-P05-04 履约模拟 | 独立深链无读取，属于本项缺口 |

其余十四分类中的未来模块已明确规划/未开放，不纳入本阶段缺功能问题；不要求实现 V4-2 或后续阶段。

## P2-UI06：修改文件或映射后仍可确认旧 READY 预览

定位：`frontend/components/v4/import-flow.tsx:18,24,29`；`frontend/components/v4/demo.tsx:285-298`。

在 READY 预览后更换文件，或把映射下拉框改为另一列，组件只执行 `setFile`/`setMapping`。父级 `preview`、`canConfirm` 和确认按钮条件均未与当前本地选择绑定；即使映射改为空或已进入第二步确认，仍可点击确认并按旧 job/version/digest 导入。服务端旧 preview 没被替换，但最终效果对应旧文件/旧映射，和界面当前选项不符。WEB_PLAN 的“映射/文件改变使旧预览失效”尚未落实为确认栅栏。

最小修复方向：保留不可变服务器 job 和 UNKNOWN 引用；对当前本地文件摘要/映射与已验 preview 建立确认一致性检查。变化或检查未完成时关闭确认步骤并禁 confirm，要求明确恢复旧选择或重新预览；异文件不能沿原父链提交。恢复已保存引用且没有重新选择文件时，可明确确认已验证旧预览，不要求持久化文件字节。补 READY→改映射/换文件→直接 confirm 的零派发用例，以及同文件合法重预览/恢复后确认。R3 仅验证换文件后点“重新预览”被拒，未覆盖直接确认。本次浏览器复现 `NOT_RUN`。

## 可接受的源码切片与前次问题状态

- 前次 P2-W02 已有对应源码修复：业务 POST、原 key lookup、资源 readback 使用 `guardedRequest` 和各自 gate ticket；当前 401/403 清屏、广播无身份 invalidate，旧 ticket 拒绝不清新上下文。三类恢复分支逐项读取，未见绕过该 guard 的新增业务 lookup/readback。纯 helper 通过不替代组件交错验证。
- 前次 P2-W03 已有对应源码修复：logout 不再受业务 pending 一律阻止，详情抽屉内也提供退出；退出不删除业务 pending/preview。persona/reset 继续禁止并解释原因。实际 reload/退出生命周期例在 R3 未执行，仍待动态结果。
- `scopedV41Storage` 只从已验证 session context 选择 tenant namespace；legacy 记录原位保留，不迁移或重写。全量识别到损坏、错误 owner、legacy/namespace 重复冲突均 fail closed。新 tenant 不读取旧 tenant 原 key；恢复再次验证 identity/shop，原 UNKNOWN 不因缺回执或拒绝变为已解决。相关纯测试已通过，不能代签真实身份隔离。
- preview 映射重传核同 file digest/parent/revision；原 key 查询与 job 回读匹配后先持久化引用再清 pending，存储失败保留。import_confirm 用不可变 job.version 而非商品/订单的 +1；确认结算要求回执、COMMITTED job 与 after_revision 数据来源相符。
- 已提交 import 的结算调用 `validPreview(..., true)`，仅 COMMITTED 回读允许原 preview 过期；READY 过期仍拒绝。此项纯函数分支通过，实际后端是否允许该当前身份读取仍待 API 验证。
- frontend schema 与 `00851a8c87191de52ab127d6ff46a6c56e892981` 和 control `4acba0c` 的 API_CONTRACT.json.json_schema 分别精确相等，前次三字段缺失已消除。strict Ajv 全定义编译通过。request gate、对象 ID、来源 dataset、export revision/snapshot 均保留检查；没有从 source label 推导权限。
- Copilot 明确模型未启用，只消费当前受权 read-context；未来模块、未知成本/库存、退款到账未知及上传来源均未伪称真实功能或外部事实。此次差异审查未发现新增私有邮箱。敏感扫描由固定 native 预检单独执行。
- 详情与菜单/助手使用原生 dialog，源码有焦点进入、Esc 及菜单/助手关闭后回焦点；详情 Esc 导航返回列表。此项不能据源码签 1440/1280/390、Tab、原生 200%、reduced-motion 或最终视觉通过。

## 独立验证与实际 R3

独立执行固定 Node `24.21.0`，二进制 SHA-256 `e4b5a3af0e05c75de2eae013904145f40fe7fc2a6e6f17510128bf45cca4e79b`。执行前核 frozen lock Git blob `ce9c5bf957a5602a6615a5701497d7ebd5a9bf5e`，复用依赖的 lock 与本树逐字节 SHA-256 均为 `0958459e1d54335162c55996d1ea63e66179054974907f9b6e125cdd9029706f`；实际 Ajv 8.20.0、ajv-formats 3.0.1、React/react-dom 19.3.0、Playwright 1.64.0、TypeScript 7.0.2。仅只读使用已安装依赖，未安装软件或写共享 node_modules。

命令：固定 Node 运行 `--test frontend/v41-tests/*.test.mjs`。实际 **45 PASS / 0 FAIL / 0 SKIP / 0 cancelled，native exit 0，429.604125 ms**。包含 client/schema、request gate、pending tenant 隔离、preview/import、来源、查询、路由等纯测；fetch 为测试替身。日志保存独立树私有 `.audit/v4-1/ui-review-622ee6e/pure-tests.log`，不入提交。工具路径检查曾发现默认 Node 为 20.20.1、依赖尚未链接，未用默认 Node 执行测试；一次只读 Git 路径未引用导致 shell glob 拒绝，引用修正后读取成功，两者不记成测试失败或产品结论。

Root 转交并允许只读的 R3：独立 `commerceops-v41-ui-fixture-r3` 工作树内 `.audit/v4-1/ui-fixture-622ee6e-r3`，冻结同一 622ee6e/tree452c7d3。已读 result.json、playwright.json、checks.json、outer-receipt.json、dummy-counts.json 及错误 context，并核四项关键 artifact SHA-256 与 result 索引一致。

- 动态收集 11，全选、worker1、retry0、maxfail1；实际执行3：CSV/XLSX两例 PASS、首 lifecycle 例 FAIL、其余8 `NOT_RUN`。Playwright stats 为 expected2/unexpected1/skipped8/flaky0，耗时4538.01 ms。
- 失败是 `openDetail` 的 `getByLabel('店铺')` 同时匹配全局及详情 select，strict mode 拒绝；未到 late tags dispatch，不能称权限断言失败，也不能称该交错已验证。后续 locator 修复不在本报告 source 内。
- 两个合成导入例覆盖 discovery、reload引用、同文件映射、异文件重新预览拒绝、confirm503后原 key lookup/readback；只签 Mock UI fixture 结果。
- outer/worker实际 native1，parent_timeout=false。checks 记录 groups_stopped=true、13443/18443 均关闭、dummy请求0、前后源码相同。保留原始各层 native 字段，不改写为整轮成功或所有子进程退出0。
- 未由本 Reviewer 启动/重跑浏览器、服务或该 case；R3 与独立45纯测分别计账。

## 剩余门槛

三项 P2 由 WEB owner 修复后按新精确 SHA 复审。R3 未运行的异步/拒绝/退出/抽屉/跨租户例，以及新增编辑持久性、导入变更确认栅栏和业务深链例，须 Root 按新窗口实际验证，不能使用本报告或旧 Shell 成功代签。

API 后端 S02/S04 runtime 继续 HOLD；本次真实 PG、真实 API 权限、真实导入事务、真实外部调用、完整工程/Full PG、Hosted、发布均 `NOT_RUN`。本报告只对上述冻结源码和已列 Mock/纯测证据负责。
