# V41 Native公开CDP截图窄修独审

2026-11-04（台北）。结论：`HOLD_ONE_P2_CAPTURE_GEOMETRY_DRIFT`。source `25de479e134cc4e6ca98399fe2bd54e4fe320fcb` / tree `979d6e442526851754e0d49431557d1d6155b52e`，父 `f0c6551e420801d790720a502967fe0ae0160008`。仅原三路径，父Python/TS均只改pin；按Root冻结 `ce0ff9213cac041d7cd84ce670b0011fe2d1c8ee` 的NATIVE_CAPTURE_ADDENDUM审查，没有读取作者WIP或启动about:blank lab。

## P2：像素乘积相同的拍图期间几何/zoom漂移被接受

位置：native_zoom.cjs的captureNativePng末段，保存PNG后对expected及observation.dom分别调用pngGeometry。两次只核pixelWidth/Height等于innerWidth/Height乘devicePixelRatio，未比较拍图后DOM几何与该张已绑定expected几何本身。

独立执行精确导出函数：expected为720×456/DPR4，模拟Page.captureScreenshot返回2880×1824原始字节；拍图后实际DOM为1440×912/DPR2，before/after cssVisualViewport记录zoom2→1。两次乘积均为2880×1824，因此函数成功返回；记录已经含相互矛盾的DOM/zoom却未拒绝。该反例说明采集期间退回100%可被继续关联到此前200%的expected/原report.after，父既有PNG几何检查仍按该旧expected乘积判断，不能替采集层拒绝此新观测到的漂移。

反例仅使用与原self-test相同的33字节合成PNG头及Fake CDP/DOM，不声称真实浏览器发生该漂移或合成头是有效图像。原函数确实保存且返回同bytes、detach成功，复现native0表示缺口成立，不是截图通过。

最小修改：返回成功前将实际post-capture DOM的innerWidth/innerHeight/devicePixelRatio与该张expected逐字段绑定，并维持已绑定outer window约束；变化或非有限数据应拒绝。不要仅比较乘积，诊断metrics可以保留为诊断而非授权。保留失败PNG原字节、原±2像素/8MB/五图和父检查，不编辑/缩放图、不重试或fallback。补当前等乘积但DPR/CSS几何漂移的拒绝负例及原正常正例；无需新增框架或改API/父predicate。

## 其余已核项

公开CDPSession仅调用固定Page.getLayoutMetrics和Page.captureScreenshot，截图参数精确为format png/fromSurface true/captureBeyondViewport false，省略clip。五个basename闭集不变。base64字符串有界后解码，writeNew以wx/0600保存浏览器返回原bytes；没有裁切、重编码、拼接或图像补偿。PNG签名/IHDR/尺寸/有限正几何与±2、8MB检查存在，坏尺寸在下一协议读取之前拒绝。

每张共用10秒单次工作预算，仍通过原limited受Root绝对窗口/180秒reserve约束；detach独立1秒cleanup预算。已有session时异常也尝试detach，detach失败单列safeFailure，原主失败不被覆盖；成功采集但detach失败会抛出。底层迟到promise不引发第二次保存/重试；若session创建本身迟到，函数无法取得的session仍需原run外层context/profile cleanup闭合，不把promise timeout称作资源已停止。

captureObservations仅保存固定basename、尺寸、字节数及白名单有限数值；错误仍走原safeFailure，不添加header/cookie/body/URL。原safeStage主阶段与cleanup分账、同Shell会话/只读请求/真实zoom1→2/event/tab/window、五图顺序、context关闭与精确PID/birth强停失败分类均未放宽。父PNG predicate没有改动。

模块SHA256独立核为 `6fa9663dfc3695c2e3caa4cc482776f7ad87d62f47cc811bbc7d91da77e83079`，与TS moduleHash及Python NATIVE_MODULE_SHA256一致。此pin一致不抵消上述几何P2。

## 独立纯验证

新review-owned目录 `/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/v41-native25-review-onirknnm` 提取精确模块，使用既有Node v24.21.0执行原--self-test：34 checks/native0，browserLaunches0/profilesCreated0，Native/截图/S01均NOT_RUN。

额外两个异常场景native0：提取原limited函数，在受控短预算下让截图底层promise迟到拒绝，确认无late save、detach1、无unhandledRejection；另令主capture失败且detach失败，确认主错误保留、detach错误安全收敛、不输出原异常正文。上述几何反例另native0确认接受缺口。

反例 `geometry-drift.cjs` SHA256 `de1ef3e78a2c0e15bf8f40ed4f3cbd140e47c6e055de68fbd87ef3c82159ae6a`；异常脚本 `capture-failures.cjs` SHA256 `b1ee4ae4e8be05ad2e0c9a5879fb5969dc5dc9f62e26f4e8e267cbb00e6362c9`，均保留。作者TS/72parentpure/preflight是转交结果，本轮未重跑。合同不在候选base，最初Git读取路径未找到后从Root ce0冻结读取，未转读WIP。

原r9图像不符、父拒绝与FAILED_OR_UNKNOWN完整保留，本轮不判断唯一历史根因，不预签lab或r10。仅新增本review文档，经指定changed-file/index预检后普通冻结，不push；无浏览器、profile、服务、PG、build或网络启动。

## c8e817a完整增量复审：几何漂移P2关闭

2026-11-04。结论：`CAPTURE_GEOMETRY_P2_CLOSED_SOURCE_AND_PURE_ONLY`。完整审查25de→`5ce5965f7357595a7d4aabb3b067da4233d769d3`→`c8e817a587c6b65df520f8171e418c1637bf5822`，最终tree `890cfe12a06d36e42e8fd23206981c7082c88d6c`，非仅末次可选字段修片。唯一CJS与TS两路径增量；原25de缺口/34pass/反例/HOLD记录保持。

拍后DOM的innerWidth、innerHeight、devicePixelRatio现必须逐字段等于本张expected，且两者outerWidth/Height均必须为1440×1000；然后仍执行原PNG乘积±2检查。expected的inner/DPR在此前pngGeometry已要求有限正数，拍后字段由numericFields过滤，缺失/非有限值不能通过相等/外窗检查。原等乘积但DPR/CSS变化及outer漂移被明确拒绝，失败PNG仍原bytes保留，不产生重拍或fallback。

CDP cssVisualViewport.zoom按可选协议字段处理：保留原始hasOwn presence事实，前后均缺失时不凭空要求字段；任一存在则须双边存在、有限正数且值相等。非法值不能因numericFields过滤而被当作双缺失。真实zoom/event/tab仍由原extension观测与父契约承担，缺省diagnostic字段不代替这些Gate，也未被提高为必须存在的新门槛。

独立提取最终模块执行原self-test，40 checks/native0，browserLaunches0/profilesCreated0，Native/截图/S01均NOT_RUN。另复用原几何反例并补齐合法expected外窗字段：720×456/DPR4→1440×912/DPR2的等乘积变化现在精确触发NATIVE_CAPTURE_GEOMETRY_DRIFT，原bytes仅保存一次、detach执行；独立反例复核native0。临时原件保留于 `/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/v41-c8-review-dj5doc58`，没有改旧反例或运行浏览器。

最终模块SHA256 `0023672bfb9f648a5df2deac397fd7159dfbbc4c1cb385c5cab9d3c97396c538` 与TS moduleHash独立相符。Python在此freeze仍为旧 `6fa9663dfc3695c2e3caa4cc482776f7ad87d62f47cc811bbc7d91da77e83079`，按Root单owner安排待QA同步；本次只接受Native组件源码，不宣称产品三pin或整组合准入完成。原捕获params/10秒工作/1秒detach、异常分账、8MB/五图/±2、原生zoom/session/只读/cleanup保护在该完整diff中均未削弱。

可供Root继续审查其独立工程lab helper及具体窗口；本回执没有启动lab或给其结果背书，更不代签业务截图、r10或视觉。仅本文件指定预检后普通追加冻结，不push。
