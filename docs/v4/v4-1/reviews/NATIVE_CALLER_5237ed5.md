# Native caller 5237ed5 增量独立审查

2026-11-04（台北）。结论：`CALLER_SOURCE_INCREMENT_ACCEPTED / NO_NEW_P1_P2_FOUND`。精确提交 `5237ed50b3c5a55c2060a068b0b94864d355505e`，tree `d3156dff150e710c1f47eb74ba8c4946e76cd537`，parent `e20cf67f7bc7073e4e0c4a80cd3e2b3d853bc859`；范围仅8文件+421/-32。按已审Native `651cac313a242ebf1ad29cacc40f29d2d660d959`接口核对调用，不复制或修改该模块，不读取QA未提交WIP。

## 授权、字段和同源接线

Python runtime严格要求8项Root身份/授权字段加6项工具字段，拒绝额外或缺失字段；source/tree、authorization_id、directory/UID/project/test_image逐项绑定。canonical executable/framework及实际Node文件核摘要、必要可执行权限，Playwright固定1.64.0；新增工具及package摘要进入原source/tool seal。父Case仍经完整OwnedManifest/Root runtime_handoff准入，启动前固定source文件与HEAD一致，Native文件摘要精确锁定已审651版本。

`native-capture.ts`从同一私有case重读完整对象、核与原Shell对象一致，17字段集合与OwnedManifest一致，不构造缩减Case；runtime六字段逐一映射为CJS接口的executablePath/executableSha256/frameworkPath/frameworkSha256/nodeSha256/playwrightVersion。模块路径固定且核canonical与SHA，使用createRequire加载唯一模块，不接收任意模块名或启动参数。TS局部检查不是独立授权入口，依赖前述父层严格准入及模块自身Root窗口/source/tool复核。

调用位于原三宽/键盘之后、persona/logout之前。真实session GET按原schema解析，与原context五个身份字段相等；从当前店铺combobox读取shop并核仍在session shops内，再传同一context、当前context.cookies(api)及shop。新调用不创建visitor或业务写，不复制storage；模块内继续核授权shop、真实session与只读业务响应。Shell其后的切换身份、退出、迟到响应及清屏检查未被本增量替代。

## 回执、捕获与清理

TS和Python均要求CAPTURED_PENDING_VISUAL_REVIEW，保留nativeBrowserExit=NOT_EXPOSED及humanVisualAcceptance=NOT_RUN；Python摘要严格限定五字段并核私有receipt原始字节摘要。TS核当前shop/context摘要，Python核完整source/inputs/module/tool及清理后相同绑定。两层拒绝forced、emergencyEvents、closeFailure/failure及未清零残留；不把强制清理成功转成采集成功。

两页固定dashboard/products，核同tab的1→2真实factor、per-tab automatic及对应事件；Python进一步核有限正几何、1440×1000窗口、inner尺寸/DPR倍数、root/body无CSS模拟，五个固定路径PNG原始字节摘要与尺寸、几何相容。上述是采集证据检查，不是视觉质量判定；PNG头和尺寸检查本身也不等于完整解码或人工审图。

Native profile沿用browser-tmp/playwright_chromiumdev_profile-native200，符合既定父组观察前缀；e20的Node祖先、executable、UID/birth及完整PGID成员清理保持。owned_driver仍先要求probe退出及固定两标题报告/回执，再进入writers停止、完整组残留检查与末态流程；模块自身PID清理不替代父组清理。

## 独立检查与未覆盖范围

在Reviewer私有目录导出精确5237 Git archive，独立执行受影响 `test_browser_shell.py`：22项通过；三Python文件mypy通过。固定Node24配合只读现有依赖，对native-capture及Shell和其导入执行定向strict TS检查，最终exit0。首次仓库根目录定向TS命令缺Node types失败，第二次在frontend被TS6要求显式ignoreConfig拒绝；随后显式`--ignoreConfig --types node`完成检查，未改源码或安装依赖。首次工具调用因目标scratch目录尚未创建未执行，之后才导出并验证。作者报告26组件不冒称本Reviewer独立运行26项。

本次不运行Playwright joint --list，不审或签后续StageSpec offline/hidden两步与ESM followup，不扩全矩阵。Root a96/WEB538作为本次指定的已审依赖边界，不从5237单独重签整合树；Native651按既有[修复复审](NATIVE_651cac3.md)及本次接口对照承接。实际profile/browser/PG/API/Web/真实信号均0，截图与Native运行NOT_RUN。当前只接受此caller源码增量供Root集成；组合精确SHA、后续调用链检查、实际资源准入及视觉验收仍分别核定，不签Full或阶段完成。
