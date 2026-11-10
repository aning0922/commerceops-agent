# Native 200% 最终模块源码独立审查

2026-11-04（台北）。结论：`HOLD / ONE_P2`。审查冻结提交 `315ee23948a4643ef2a007afc85f1c05a1a799c2`（parent `13b086ea007fca0cc7d0b1288799a0a1eb21b3b9`），tree `4b27eabbc3a9200ea403d2d364e80f4ef244779b`；唯一模块 `tests/e2e/v41/native_zoom.cjs` SHA-256 为 `3b79049984ee6454e497e499d93387cecaae4f64e80a305ad07162693a6662a2`。父清理接缝按冻结 `e20cf67f7bc7073e4e0c4a80cd3e2b3d853bc859` 核验；不读取作者未提交WIP，不签尚未交付的QA调用集成。

## P2：紧急终止事实被成功清理覆盖

定位：`native_zoom.cjs:424-437`。触发条件是页面采集完成、`context.close()`正常返回，但3秒等待后仍有已见证的同UID/PID/birth进程。模块随后发送SIGTERM，必要时SIGKILL；这条路径既未设置failure，也未保存强制终止前的残留及信号记录。如果残留消失、source/tool复核通过，最终仍为 `cleanup.confirmed=true`、`NATIVE_ZOOM_CAPTURED_PENDING_VISUAL_REVIEW`，并正常返回。

父 `browser_shell.py:453-468` 将清理前存在残留明确记为forced，并要求 `clean_exit = not initial and not remaining`；`owned_driver.py:525-530` 将不干净退出记作 `ForcedStopOrRemaining`。模块先行杀掉残留后，父层只能观察到空组，无法从最终资源为空还原这次异常。于是强制清理可被当作正常退出，丢失验收所需失败事实。此问题不等于已观察到真实Chromium残留。

最小修复建议：进入紧急信号路径前，持久记录已见证残留身份及实际信号尝试，并设置稳定失败码；继续完成清理、source/tool复核和回执写入，但最终状态保持 `FAILED_OR_UNKNOWN` 并向调用方抛错。清理完成与执行失败分别记录，不改父profile识别规则或组清理约束。修复应覆盖正常退出与强制清理成功两个分支，后者不能返回采集成功。

## 其余已核源码范围

- Root材料：核受保护case目录、owner JSON文件模式/UID/无符号链接读取，Root授权marker及source/tree/project/database/image/UID/端口/起止时间等逐项同绑，owner verification、Git源码和工具hash复核；墙钟与单调时钟取小并预留180秒清理。没有公开启动CLI，实际调用仍须Root和QA完成同源父链绑定。
- 权限与会话：扩展仅loopback host permission，worker再核完整origin和唯一精确tab URL；不声明广域权限、content scripts或外部消息入口。只向新profile复制当前Shell cookies，不复制storage、不创建新visitor；真实session GET复核相同context，UI选择currentShopId后核业务GET的shop与context。路由允许固定API/Web origin的GET/HEAD/OPTIONS，拒绝其他业务请求；回执不写cookie值、响应正文或错误原文。
- Native证据：Chrome tabs API设置automatic/per-tab，核1与2的实际getZoom读回、同tab及1→2事件；窗口1440×1000、viewport null，未用CSS zoom/transform或deviceScaleFactor替代。记录geometry和真实PNG摘要。成功命名仅表示采集完成待视觉复核，`visualAcceptance=PENDING_REVIEW`、真人视觉 `NOT_RUN`、browser native exit `NOT_EXPOSED` 均保留。
- 新profile与父接缝：最终路径为 `case/browser-tmp/playwright_chromiumdev_profile-native200`，新目录0700且EEXIST拒绝重放，符合e20的既定前缀；不接受旧chromium-tmp拼写。模块自身按已见证PID/birth及子树清理，不能独立代签完整PGID成员；完整组观察和孤儿进程核验仍由e20父层承担，运行时须绑定同一Root executable及owned Node。上述P2阻止当前组合取得无问题源码结论。

## 独立验证与边界

从精确Git blob导出私有审查副本，独立核对模块摘要；使用固定Node v24.21.0（SHA-256 `e4b5a3af0e05c75de2eae013904145f40fe7fc2a6e6f17510128bf45cca4e79b`）执行syntax check exit0和模块self-test：14项通过，browserLaunches=0、profilesCreated=0。

另将最终源码finally片段原样截取，以模拟时钟、进程清单和kill依赖执行纯控制流反例：close已正常结束、已见证进程在模拟SIGTERM后消失，结果仍为 `failure=null`、`cleanup.confirmed=true`、采集成功状态。该反例仅证实源码分支，实际发送信号0、浏览器启动0；私有复现位于本Reviewer `.audit/v4-1/native-315-review/cleanup-repro.cjs`，不作为实际运行回执。

实际Native、profile、截图、S01、真实浏览器/PG/API/Web运行及整链清理均 `NOT_RUN`。本报告不授权任何窗口，不签原生200%视觉通过、Full或阶段完成；待P2精确修复冻结后复审。
