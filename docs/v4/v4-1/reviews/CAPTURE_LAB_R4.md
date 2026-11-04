# Native capture R4 工程 lab 原件独立核收

2026-11-04（台北）。结论：`ACCEPTED_ENGINEERING_CAPTURE_LAB_ONLY`。核收已有 synthetic about:blank lab 的实际 capture helper、原生 zoom、PNG 与关闭证据；没有新 probe/资源运行，也没有重审产品 40 图。实际源码 `c8e817a587c6b65df520f8171e418c1637bf5822`，tree `890cfe12a06d36e42e8fd23206981c7082c88d6c`，模块 SHA-256 `0023672bfb9f648a5df2deac397fd7159dfbbc4c1cb385c5cab9d3c97396c538`。整合 candidate 261f399 的产品运行、组合检查与阶段验收不由本 lab 代签。

原件目录 `/Users/aipuli/.codex/worktrees/commerceops-v41-native-capture-fix/commerceops-agent/.audit/v4-1/native-capture-lab-r4/`。FINAL_INDEX.safe.json 独立 hash 为 `8e0aa71a9c4c379e95f06dcafee8d657d2e521a51389b1ba63cea7abf83bdbec`；其列出的 15 件原件全部逐 hash 匹配。delivery.safe.json 为 `080469a8c416bcab197234265b3108be49e814dbe181e11f76878e34cb0f0773`，parent.safe.json 为 `6a44a0712f2701ada42349a0661e24c6304b39a907cfd97e3f4668907257461a`，child case/receipt.safe.json 为 `83e2116c62f64956db1380b41c95c1e103a62dbc6ca98e3ff8267258bd5c7a07`；delivery 嵌入父子对象与各原文件完全相等。manifest/authorization、once、空 child stdout/stderr、geometry、独立关闭摘录、后置 pins 也在此次核对范围。

## 实际函数绑定

已读 pinned capture-lab.cjs、parent.py 与 c8 冻结模块。child 在启动前校验 Root manifest hash、source HEAD、clean status 及九个 pins；直接 require 本仓库 tests/e2e/v41/native_zoom.cjs，三次调用其导出的 captureNativePng。独立从 Git blob 计算模块 hash 与 manifest/index 相同；不是复制相似 helper 或运行另一份截图实现。lab 调用传入 page、固定文件名、实际 geometry、observations 和 limited 五个参数，没有覆盖第六个 save 参数，使用原模块的 writeNew 保存浏览器原始字节。

该 helper 经 page.context().newCDPSession(page) 调用 Page.getLayoutMetrics、Page.captureScreenshot（PNG/fromSurface=true/captureBeyondViewport=false），保存收到的原 bytes 后核 geometry，再取后置 metrics/DOM 并拒绝几何与 zoom 漂移，最后 detach。没有另行缩放、裁剪、填边或修改 PNG 的路径。lab 页面为唯一 about:blank，仅 setContent 合成 TOP/棋盘/BOTTOM，extension 无 permissions/host_permissions；没有产品登录、cookies、业务请求、API、PG 或 provider。products 命名只是复用固定 helper 允许的三个输出路径，不代表真实商品页。

## 运行、几何与三图

Root 授权窗口 UTC 10:38:00–10:46:00，原 parent 实际 10:38:16.844580–10:38:19.878390，child 实际 10:38:17.166–10:38:19.424，均在原窗口内。delivery 记录 outer_tool_native_exit=0，原 parent 记录 child_native_exit=0；Root 冻结公开回执同时记录 parent_native=0/child_native=0。child status 为 ENGINEERING_CAPTURED_PENDING_PNG_VISUAL_AND_PARENT_CLEANUP、contextClose=true，无 failure；parent status 为 ENGINEERING_CAPTURE_CLEANED_PENDING_VISUAL_REVIEW。原中间 PENDING 状态不改写，最终工程图片核收见后述 Root 回执与本轮查看。

实际同 tab baseline zoom=1、readback zoom=2，automatic/per-tab 与 1→2 event 均存在；外窗前后为 1440×1000。100% DOM 为 1440×913/DPR2，200% 为 720×456/DPR4；CDP cssVisualViewport.height=456.5，原 PNG 1826 像素与该小数高度相符，DOM 整数高度乘 DPR 的 2 像素差仍按原 helper 窄容差处理，没有补像素。before/after metric 与 DOM 均记录；底部 capture 维持 zoom=2，页面已滚动到底部 marker。

| 原 PNG | 原字节数 | 像素 | SHA-256 |
| --- | ---: | --- | --- |
| products-100.png | 35702 | 2880×1826 | `a0c228550b5d06aa17f37b41ccd2a6b5a351283fc0b3b2c17434869b2186ae14` |
| products-200.png | 54246 | 2880×1826 | `b576925cfd23c97e06db1ae0cb63227767521791c8499ac4bc1b5995c8a0d029` |
| products-200-bottom.png | 63006 | 2880×1826 | `4672cbe58437d73d6c9f4668eab721bcfd06bdaf7a7ac677a6b1d60322a23044` |

独立逐件核 hash、字节长度、PNG signature/IHDR 和尺寸，并直接查看上述三张原文件，没有重新生成图。100%/200% 图中的 TOP 0123456789、蓝白棋盘均清晰，200% 内容放大；bottom 图的 BOTTOM 9876543210 完整可见，未见空白或右侧内容截断。这与 261f399 冻结公开 `docs/v4/acceptance/v4-1/NATIVE_CAPTURE_LAB_R4.json` 中 Root 的三图查看结论一致；公开回执的 source/tree/module 与七项 artifact hash 也独立匹配。本轮只核这三张工程图，不覆盖产品页面视觉，不等同用户人工视觉验收。

## UID、pipe/TCP、清理与后置 pins

parent 原件登记 11 个进程 identity（child 与 Chromium 进程），均含 PID/PPID/PGID/birth/实际 UID501；原监控通过 child ancestry/独占 profile marker 校验同 UID，运行中观察到 remote-debugging-pipe。原 tcp_listener_observations 为空，读取源码可确认其为对 owned alive PID 的 lsof TCP LISTEN 检查结果；这不是全系统端口或所有 outbound 网络流量证明。child requestsRefused=0 表示没有命中页面 route 的请求，不扩大为全网抓包结论。

原 parent forced=false、remaining=[]、profile_roots=[]，无 sticky inventory failure；child 正常 context.close 后 native0，未走强制信号收口。delivery 的独立关闭采集时间为 UTC10:38:37.293844，registered_alive/profile_roots 为空；independent-closure.safe.json 明确是该原独立快照的摘录，并引用 delivery hash，不伪装第二次新 probe。profile 目录按计划保留，不能将保留目录当作活进程。本轮只核这些原记录，未运行 ps/lsof、探测端口或发送信号。

post-pins.safe.json 在 UTC10:39:05.595043 记录同 c8 source/tree、clean 与九个 pins 全同；本轮再次只读计算九个当前文件 hash，均与 manifest 匹配，覆盖 Chromium executable/framework、Node、Playwright core/package、c8 module、worker/lab/parent。Node 固定 e4b5a3af…；后置 pins 证明所列绑定未漂移，不扩称所有系统/依赖文件均被检查。Root 公开回执状态 ENGINEERING_CAPTURE_AND_ROOT_PNG_REVIEW_ACCEPTED 与 FINAL_INDEX 的工程核收状态一致，AI 工程查看已完成；用户人工视觉、真实产品 Native/身份/业务与完整组合仍各自另核。

本证据只支持新 capture helper 在本 synthetic 工程场景下真实调用、三张原 PNG、原生 1→2 与正常关闭。无额外执行或新窗口授权；不把 c8 lab 结果直接转成 261 最终组合 235、真实产品 Native、40 图、服务/PG或阶段完成。后续 261 检查待其真实回执另核。
