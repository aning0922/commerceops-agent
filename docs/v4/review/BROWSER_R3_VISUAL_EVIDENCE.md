# R3 浏览器与原生200%分段视觉证据核收

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_R3_BROWSER_AND_BOUNDED_Q16_VISUAL_EVIDENCE；Q16-VISUAL-01由本次新证据闭合。** 仅针对固定本地浏览器用例及原裁切缺口，不是生产视觉、完整无障碍/屏幕阅读器或全浏览器兼容验收。

受测R3 `0636d3c9c70500f12b5f73de45217513ff38e93a` / tree `dd0c81bb5928219d87c713c8956b05aadb1fec9c`。原证据 `/Users/aipuli/.codex/worktrees/commerceops-v4-live/commerceops-agent/.audit/v4qa_browser_20261104c`；只读case、Playwright原probe JSON、安全driver/outer/finalPG及原PNG/coverage，没有启动浏览器、后处理图片或读取私钥。

## 实际原生执行与来源

独立用R3原validate_report核原JSON：固定唯一LIVE lifecycle标题，expected1/unexpected0/skipped0/flaky0、单次passed/retry0；总duration8181.118ms。五个源码pin均与实际R3 Git blob相符，live blob `2ad9fcad7b6736d6c55de8d5e482d0369ea129c3` 与已审5cc完全相同。case与ROOT_OUTER均绑定R3，driver/scenario native0、browser EXECUTED_PENDING_REVIEW。

原测试实际包含desktop、390px及独立headful native200三个不同tenant的真实API交互；固定schema/身份/视角/reset/logout、导航键盘、dialog内Tab和Esc回焦点均由单次通过支持，非旧失败与本次部分结果拼接。finalPG为3tenant：两个epoch0/generation0/receipt2/tombstone2，桌面epoch1/generation4/receipt6/tombstone6。外层于UTC18:51:06.886617（台北11月4日02:51:06）完成，driver0、forced=false、cleanuptrue、containers/networks/leftover及登记组live成员为空，端口关闭并保留原卷。

## 原生200%实际覆盖

原metrics仍为GUI选择2、outer1440不变、inner1440→720、DPR2→4、visualScale1、CSS zoom1及scrollWidth720。五个实际segment的visual height456.5、layoutHeight456、width720、documentHeight1577；每张原PNG实际IHDR均2880×1826，与记录和精确像素等式相符。

| 段 | 实际y | 覆盖结束y | 原PNG SHA256 |
|---|---:|---:|---|
| 01 | 0 | 456.5 | 35f2ab4976aa5e1172777dd38c03295e47d58e652d38dc1f23210764e4380d61 |
| 02 | 365 | 821.5 | c45f975985c51521ecda3a406448569f4d22cfe007a7f773ace3aacf9e8299c6 |
| 03 | 730 | 1186.5 | 6b047ce9aa1eee052570cd1b59ec6efa098b9431e85ee2a989d928cf2b53176c |
| 04 | 1095 | 1551.5 | e354a6f33f013401b6131a6d13ebe7c37119c5f025a9738bad51a164aab66962 |
| 05 | 1120.5 | 1577 | 7bcd8da7f55e8fd0f5708839d246a93f088575021586797eeb565bb75dbaddd3 |

独立逐段核首y0、严格前进、相邻无空档，末端精确覆盖文档底部；不是根据target补写actual。progress仍为INCOMPLETE，内容与独立coverage的已完成段相同，不把它重写为成功。coverage存在加上整个test通过，支持截图后滚动复原及profile清理也完成。

已实际view全部五段、native dialog、native settings和本次390已登录图。五段合看可见完整横向页面边界、欢迎/会话文字、商店与视角及重置/退出控制、summary、六张场景卡和页尾，之前被导出截断的右侧信息现在可见。原dialog PNG2880×1826中标题、完整说明、取消/确认按钮及焦点轮廓都在图内。窗口分段自然在上下边界截取局部内容，但通过相邻重叠覆盖，不能误称单张为全页图。

Next dev浮动标记仍可遮住局部左下内容，未宣称生产图无叠层；此处关闭的是原native200横向裁切及完整dialog的证据缺口。设置图仅viewport且未拍到下方200%选项，选择值仍由真实GUI断言和metrics证明，不伪称选项文字入镜。三张welcome与mobile dialog的hash和先前已view原图一致；本次390会话新图另行view，文字换行与主要控件可读。

F1功能PASS及原裁切图保留；R2 browser_b原FAIL、5张未闭合片段和无最终coverage事实保持FAIL，不拼签。当前Q16只核固定宽度/缩放/所测keyboard与反馈、reduced-motion断言和本次视觉范围；完整键盘循环/ARIA朗读仍未采集。

## 关键证据指纹

原probe JSON SHA256 `a240f3a23c1d58fdf86a107eaf1b2092ebbbf8e55895fece9dd8058c9e59241e`；ROOT_OUTER `34750ca422dafc7cba5e56818e0b25fa18c167b8250b205d621396a47af9bd11`；coverage `fff871aa91939735f7ef8a79d1fc2b5462d6a54eafda9085fa6a3d3edaf69a3f`；native dialog `36b671f26d9c306542ccfe8cb975421b3ee1f831798d7acc9fd695f2f5330060`。

审查时运行tree仍R3；ROOT cbd1与R3仅两份LOCAL_RUN文档不同，产品子树与F1/R2相同的独立字节核对见HTTP11回执。保留实际R3来源，不把当前/未来HEAD工程检查写成浏览器重新运行。
