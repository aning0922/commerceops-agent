# V4-1 原生截图采集修复边界

2026-11-04（台北），Root 在已授权本地 V4-1 内补充单 owner 路径。

r9 的两个浏览器 spec 通过，但父回执校验失败，整案保持 FAILED_OR_UNKNOWN。
只读副本诊断为 NATIVE_PNG_BYTES_OR_GEOMETRY_MISMATCH；原异常仅记录类型，
不回写其原件。真实 100% 图 2880×1826 对应 1440×913/DPR2；
200% 图实际 1440×912，与 720×456/DPR4 不符。Root 和 Terra 逐图看到
原生 200% 裁切及底图空白。五图原件保留，不经图像编辑补成通过。

本窄批 GATES 唯一负责以下三处：

- tests/e2e/v41/native_zoom.cjs：固定公开 CDP 原生视口拍图、即时 PNG 原始字节和几何拒绝。
- frontend/v41-e2e/native-capture.ts：仅同步已审模块 hash。
- tests/e2e/v41/browser_shell.py：仅 NATIVE_MODULE_SHA256 常量同步。

不改产品、API、DTO、父校验其它逻辑、身份、registry、subject、once 或原断言。
原 ±2 像素、8MB、五张图、真实 zoom1→2/event/tab/window、同会话只读及 cleanup 不放宽。
不缩放或编辑 PNG，不用 CSS/device emulation，不重试或自动 fallback。

固定候选方法为公开 CDPSession 的 Page.captureScreenshot，省略 clip，
fromSurface=true、captureBeyondViewport=false；这是待实现并实际验证的方案。
参见 [CDP 官方协议](https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-captureScreenshot)
和 [Playwright CDPSession](https://playwright.dev/docs/api/class-cdpsession)。
它们是接口参考，不是已核当前 Chromium 156 运行证明。

先冻结源码和纯检查，再在独立新 about:blank 工程资源内验证采集；
工程实验不带 cookie、访客、PG、API、产品或外部调用，不代签产品验收。
具体 helper、工具、资源、UTC 与清理由 Root 单独绑定，失败保留且停，不自行续窗。
工程实验和独审通过后才以新源码、新镜像、新 once 和资源运行完整业务 r10。
旧 r9/此前所有失败、卷、原始回执和未知保持原样。
