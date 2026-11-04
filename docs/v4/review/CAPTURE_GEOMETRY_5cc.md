# Native 200% 分数视口高度 5cc 窄审

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_PREPARED_FRACTIONAL_NATIVE_CAPTURE，0 P1 / 0 P2。** 关闭本次整数/分数视口高度混用的实现缺口；真实新browser/Q16视觉补证尚待ROOT，不签研究页或纯模拟为产品验收。

candidate `5cc19ae8ba533a6fe667676b12ac8b01eaae1e76` / tree `2fe9d33c8373ebc659d80bfcd3d06e47ab18330a`，parent `c6abe0528f05b458331f270d758317c1d7b38843`。唯一 `frontend/v4-tests/lifecycle.live.ts` 5行新增/4行删除。parent原capture替换由ROOT独审，本次只核其几何小delta及必要上下文。

## 高度含义与修正

CSSOM View将innerHeight定义为long，VisualViewport.height定义为double，后者是视觉视口的CSS高度；scrollY也可为double。故不能用整数innerHeight无损代替真实视觉视口的分数高度。[CSSOM View定义](https://drafts.csswg.org/cssom-view/#the-visualviewport-interface)、[Window视口定义](https://drafts.csswg.org/cssom-view/#dom-window-innerheight)。本处引用编辑草案说明类型/含义，不据此保证任意平台截图行为。

CDP的cssVisualViewport采用CSS pixels；captureScreenshot的fromSurface=false选择view而不是surface，默认不捕获viewport之外。协议没有承诺任意环境PNG必满足某个DPR等式，因此新代码的严格像素检查仍是本目标环境的实际准入验证。[官方Page协议源](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Page.pdl)。

ROOT研究报告visual height456.5、layout innerHeight456、DPR4及PNG高1826。新measure将height改为visualViewport.height，并独立保存layoutHeight=innerHeight供审；实际PNG高要求严格等于round(height*dpr)，即该组数据下1826。原>=整数高度改为严格相等，无magic tolerance、没有允许短图或超长图掩盖缺口。

相同分数高度用于每段几何和最后覆盖比较，避免实际滚动到文档底部时，由整数高度少算半个CSS像素而误认未覆盖，再请求同一已钳制位置。ROOT旧R2没有最终coverage或完整actual y清单，本审不回填旧y，也不以纯模拟宣称捕获了旧运行的全部内部状态；说明的是该修复与已报告测量之间一致的因果机制。

## 未放宽的边界

独立比对helper之前、之后原文件内容逐字节相同。真实zoom选择/尺寸断言、业务POST/GET及strict响应判据、120s配置、profile清理均不改。helper仍只用原CDP原图，不裁剪/拼接/缩放后处理；每段先核实际位置，再拍图，再核位置/视觉尺寸/documentHeight/DPR未改变。宽度仍要求原严格像素相等；layoutHeight仅追加诊断字段，不用作容差或覆盖替代。

仍要求首段实际y=0、后段严格前进且无空档、最多32段、末段实际y+height到达documentHeight；仍恢复原滚动位置并detach CDP。分段每张PNG成功写入后追加覆盖写私有progress，status始终INCOMPLETE，保存截至该刻实际测量；不预写目标y或未来段。单独coverage文件只在覆盖完整后写入，原finally恢复若失败仍令整个test失败，所以coverage文件存在本身不等于完整测试成功。progress写失败也传播失败。证据目录与文件私有性沿用原browser launcher的0700目录/umask077，不另引入公开输出。

## 独立纯验证

只从两个精确Git对象抽取captureNative200，使用本机Node stripTypeScriptTypes执行同函数；页面度量、滚动钳制、CDP返回和文件写入均为内存替身，没有真实浏览器、网络、PNG图像生成/改写或资源启动。用明确合成documentHeight2000、visual456.5/layout456/DPR4演算，不冒作R2原actual y：旧函数因底部重复位置拒绝，无coverage；新函数6段覆盖完整、height/layoutHeight/PNG高一致，恢复原滚动位置，逐段progress保持INCOMPLETE。

另验证短PNG、长PNG、错宽度、重复位置、段间缺口、截图间度量漂移、中途CDP失败、32段仍未覆盖等8个负例均拒绝且无coverage；中途失败保留已完成段progress，32段限制未放宽。非分段viewport路径仅1张且不宣称全页coverage。**共11个纯场景符合预期 / native0**。不是11次浏览器运行；ROOT已报tsc0未在本次重复执行。

R2原capture repeated position or gap/native失败、5段PNG和缺失最终coverage均保留；F1功能PASS与原200%裁切限制也保持。Prepared接受后需ROOT绑定新live blob/pin和最终源码，再以新owned实际browser报告、实际分段位置/原图/coverage及清理结果核收Q16；不得将当前几何研究或模拟直接标为真实UI视觉通过。
