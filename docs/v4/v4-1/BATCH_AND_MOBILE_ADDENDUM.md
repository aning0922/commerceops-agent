# V4-1 当前页批量标签与真实移动端补充合同

2026-11-04，Root 根据完整阶段授权冻结。基线 `eb30d7b7ad26da95dcf1c03ea55c5b424fbd536d`。原规划 V4-F04-06 尚未实现，原 V41-05 的真实业务移动端证据不足；两项作为本阶段剩余工作补齐。不能声明原规划 19/19 或六卡已完成。旧四合同、V41-1f 原文和历史回执保留；本文件只增加必要 UI 行为与验收，不增加后端 API、schema、角色权限、外部调用或 V4-2 工作。

## 当前页多选与确认

只选择当前已核授权商品页实际返回的去重 product IDs，数量受当前页集合限制；不跨页保留，不提供全店或全查询选择。确认冻结完整身份、店铺、页查询、每项 ID/version、初始 data_revision 和规范标签。标签复用现有 0—8 项、每项 1—24 字及去重规范；语义是完整替换所选商品的标签，空集合表示清空，文案不得称仅追加。界面显示选中数、目标标签与逐项提交可能部分成功。

## 单串行与原键闭合

复用原 product_tags、reserve/dispatch/settle/finish pending 路径，不创造客户端授权或新批处理框架。现有 businessWrite 返回 void 且依赖 detail，不能直接循环调用。单一写锁覆盖整段串行；窄提取内部单项执行，显式目标并返回已核成功、明确拒绝、UNKNOWN 或取消，原单对象入口继续遵守原合同。

每项发送前读取当前授权详情，核对冻结的 ID/version；第一项 revision 必须等于确认页 revision，后续必须等于上一项严格回执的 after_revision。意外版本/revision 漂移立即停止，不自动接受新版本或在 409 后换键重发。为该项生成一次原 request_key，按现存格式在发送前持久化。只有原 COMMITTED 回执及同身份、同对象 fresh GET 的 version、after_revision、标签集合全部相符并完成原 pending 闭合后，才能计成功并开始下一项。

任何 UNKNOWN、存储故障、撤权、过期、401/403/409 或读回不闭合均停止后续项。原键与结果事实保留；pending 只能按原严格 COMMITTED/REJECTED 路径处理，不把未知当拒绝或成功。恢复只读原键，核成提交后也不自动继续批次，用户必须重新读取、选择并确认。每项独立事务，已成功项不因后项失败回滚，不宣称整批原子性。

## 生命周期与可见结果

关闭批量面板、刷新、路由/店铺/角色变化、搜索/筛选/排序/分页、reset/logout、hidden/offline 均撤销运行 token 并清选择；每次下一项发送前重核 token 和完整上下文。已发 POST 不因界面关闭或 Abort 被称为回滚，原 pending 继续受保护，迟到响应不能更新新范围或启动下一项。正常外部刷新取消，内部必要读回只可在同 run、同身份和店铺下闭合当前项；不得松动原安全 gate。

结果分别展示已核成功、明确拒绝、待核对、未发送数量。存在待核对不能显示整批完成；未开始不得算作已失败。进度只在原范围内显示，切换身份/店铺后清除旧范围内容。原切角色/reset 等 pending 阻断与退出行为保留。

## 单 owner 文件边界

- WEB：`frontend/components/v4/demo.tsx`、`business-pending.tsx`、`business-pending.module.css`，必要新增 `frontend/lib/v41-batch-tags.mjs` 与配套类型声明、`frontend/v41-tests/batch-tags.test.mjs`。若确需修改现 pending/context 库，先交 Root 精确差异，不能自行放宽。
- QA：`frontend/v41-e2e/business.live.spec.ts`，必要只在 `live-business.fixture.ts` 增加新行为的真实原键 journal 接线；原数据 fixture 不改。若父效果或截图收验需调整，先提交路径与 predicate，Root 再窄释放，不与 GATES Native 并行改同文件。
- GATES：仅原 `tests/e2e/v41/native_zoom.cjs` 的独立故障修复及必要资源无关检查，另按精确方案释放；不写上述 WEB/QA 路径。
- ROOT：本补充合同、阶段状态、普通集成/推送和资源窗口；REVIEW 独立核收精确冻结源码，不读作者 WIP。

## 必须验证

组件检查覆盖当前页/去重/标签规范、单串行、逐项 revision/version 接续、所有明确拒绝/UNKNOWN/持久化失败停止、取消与迟到响应、原键只读恢复后不自动续行；原单项行为回归不降低。

真实 API/PG/Web 同案验证至少两个当前页商品批量标签：每项不同原键、同身份同店、版本与 revision 单调、效果和读回一次，真实 journal 与最终 SQL 对账。遇中途故障的零后续发送与原键保存可由独立受控传输/组件负例分层证明，不能用假响应签真实提交。

真实业务浏览器覆盖 1440、1280、390，390 必须实际操作商品列表/详情/标签确认、订单列表/详情/演示履约及 CSV/XLSX 映射控件与导入读回；逐项保存实际截图、来源和结果。验证焦点/Esc、控件可达、局部表格滚动与页面无意外横向溢出、无权限空态；Shell 设置页或旧 Mock 不替代此 Gate。固定原两个原标题、workers=1、retries=0、240 秒与原 offline/hidden/原生 200%/迟到 ACK Gate 保留。数量取真实请求、journal 和 effects，不硬填旧 9 POST/31 journal。

先冻结源码与独审、再给新 owned build/runtime 窗口；旧失败案、once、卷、UNKNOWN 和来源分账完整保留。后端/PG 集合未变时以实际差异证明复用对应 e7 Gate；新产品 UI 必须完成相关类型、组件、Mock 与真实业务浏览器回归，不用旧 4fec 工程结果给新 UI 换标签。
