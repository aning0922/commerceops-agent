# Native 店铺定位与安全阶段诊断独立审查

2026-11-04（台北）。结论：`SOURCE_INCREMENT_ACCEPTED / NO_NEW_P1_P2`。仅接受冻结源码与纯组件证据，供 Root 后续集成。审查提交 `217baea74687490fb4a45f108f62841f57d2f931`，tree `b17fc1af55faf081dbb05ac56247d88683e14cdb`，直接 parent `ef0ae74906f424073ace07bec0bd93c5d69fd9e1`。完整差分只有 `tests/e2e/v41/native_zoom.cjs` 与 `frontend/v41-e2e/native-capture.ts`；后者仅更新 moduleHash 常量。独立提取 Git blob 核得模块 SHA-256 为 `295bf2c61e7cd30e7a47d7368d93fbadb40764fb41072a9119b5d78ed925689e`，与 caller 一致。未读取作者或 QA 未提交文件。

店铺 locator 改为 `getByRole('combobox', {name: '店铺', exact: true})`，与同冻结 Shell 的店铺选择及 Native 前 inputValue 读取一致。原 visible wait、count 严格等于 1、显式 currentShopId 选择仍在；没有增加 fallback、重试、timeout 或第二种店铺选择规则。session 身份与当前授权店铺验证在选择之前，业务响应的同身份、同店铺、HTTP 200、OK/data 以及真实表格行门槛在选择之后，均保留。

新增 safeStage 只接受十个固定阶段；evidence 只接受三个具名 boolean 与三个非负安全整数计数，拒绝未知字段、未知阶段及不合类型数据，复制后冻结。各 enter 调用传入固定字段，不传 Error、URL、cookie 或业务正文。safeFailure 将异常类型收敛为 Error/TimeoutError，不保存 stack；普通异常正文映射为固定通用码，沿用既有 `NATIVE_[A-Z0-9_]+` 形式的诊断码保留规则。该既有规则是格式限制，不宣称新增了完整错误码枚举白名单。

主流程 catch 在进入 cleanup 之前捕获独立的 `failure.safeStage`。finally 更新的是报告当前 `safeStage`；closeFailure、cleanup.failure 分别保留，`failure ||=` 与 markForcedStop 的已有 failure 优先规则不会覆盖主流程失败阶段。只有 cleanup 出错时也会设置 failure；最终将状态置为 FAILED_OR_UNKNOWN、回填 report.failure 并抛出，不能因资源后来清零而返回成功。读取回执时应以 failure.safeStage 解释失败发生阶段，顶层 safeStage 可以为 cleanup；阶段标签只定位操作段，不证明具体 await 或历史根因。

差分逐项核对：同 Root source/tree/inputs、固定工具字节、授权窗口及 180 秒保留、同 Shell session/cookies/currentShopId、只读路由、新建独占 profile、两真实页面、原生 factor 1→2 与同 tab/event/settings 校验、1440×1000 外窗及前后 geometry、五张 PNG 与签名/hash、最后商品行截图、source/tool 前后复核均保留。原 forced-stop 的 PID/birth/UID 校验、intent fsync 在信号之前、异常清理不能抹除失败等约束继续适用，见[此前修复审查](NATIVE_651cac3.md)。没有改动 timeout、重试或放宽失败准入。

独立使用固定 Node v24.21.0（SHA-256 `e4b5a3af0e05c75de2eae013904145f40fe7fc2a6e6f17510128bf45cca4e79b`）对精确提取模块执行 `--check`，exit 0；执行原 `--self-test`，23 checks PASS、exit 0，输出 browserLaunches=0、profilesCreated=0，Native/截图/S01 均 NOT_RUN。提取副本位于 Reviewer 私有 `.audit/v4-1/native-217baea-review/`；没有调用 run、启动浏览器/profile、读取进程清单、发信号、联网或启动服务。作者全 tsc 与扫描结果未作为本次独立执行证据。

QA Python 父 pin 尚未同步是 Root 已声明的后续集成事项；本审查未读 QA WIP，也未删除或绕过旧 hash guard。同步必须保持同精确模块 hash 后另核组合。r8 原具体 await 仍 UNKNOWN；Root 转交的剩余 1521 秒预算事实只排除截止缩短解释，不足以认定唯一根因，本次未重取 r8 材料。Native 实测、真实截图与视觉验收、整链清理和阶段验收仍未由本次证明；不授权新资源窗口，不代签 Full 或阶段 complete。
