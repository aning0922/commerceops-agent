# 助手按钮accessible name窄修独审

2026-11-04（台北）。结论：`SOURCE_FIX_ACCEPTED / NO_P1_P2_FOUND`。冻结提交 `754e8796b88dca7c11c2d2956c8645486b2d55a2`，parent `538665aebac7064c3d9b77bcbf65b4879b864123`，tree `5da4776cb2b6df6eeca8f993b75f81990da4f919`。相对parent只有 `frontend/components/v4/shell.tsx` 一行+1/-1，实际内容仅助手按钮新增 `aria-label="智能助手"`。独立逐字节断言其余内容完全一致、无测试文件变更。

Root `202807fb05d6ec3cb1ac2010ee681f3992dfe56e`（tree `8184dc241d8fef677a2b23dad90d351b6b193235`）中的shell.tsx与该修复parent字节完全相同，故此窄修与对应组件直接兼容。Root CSS在max-width:760px隐藏assistantTrigger内部span；显式aria-label使按钮名称不依赖被隐藏的文字，也排除装饰符号对精确名称的影响。原ref、type、dialog showModal、onAssistantOpen和关闭后focus回归均未改变。既有Shell按role/name查找、focus/Enter/Esc断言不修改、不放宽。

本次验证为冻结Git对象差分、Root组件字节比较及相关CSS/测试源码核对；没有新增测试、启动服务或运行浏览器。Root转交的e466浏览器r2业务PASS/8997ms、390 Shell查找超时、仅1440/1280截图及无390/Native，是原运行背景，本Reviewer未在本次重新核原件，也不以此源码修复改写原失败或补签浏览器通过。工程202807的scanner失败及原生trace仍由其原负责线程处理；本审查不判断其结果。

此结论只接受该一行源码修复供Root集成。新组合实际浏览器重跑、390截图、Native及完整验收仍须新证据；未push、未触CI或新资源窗口。
