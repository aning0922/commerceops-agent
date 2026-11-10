# V4-1 本地交付核收

当前状态：V41-01—06 六卡本地 Gate、AI 工程视觉及交付文档一致性均已核收，V4-1 本地阶段完成。
业务代码冻结为 `261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e` / tree
`34da95131e04d7360ea8aa5250ea40215bcb0713`。后续仅文档、回执和原图包装。

六卡范围是 [STAGE_SPEC](../../v4-1/STAGE_SPEC.md) 的 V41-01—06，
不是原规划 99 功能/66 业务页面全部完成。14 模块导航与当前 12 业务视图均按开放状态标注。

- [最终组合源码独审](../../v4-1/reviews/FINAL_SOURCE_261F399.md)：无集成新增 P1/P2，三 Native pin 一致，后端/锁/原权限与 SQL Gate 不变。
- [235 Python/74 Node/40 Native 纯组件影响检查](../../v4-1/reviews/COMBINATION_261F399_OFFLINE.md)：原退出与完整指纹核收，未改挂旧 Full 的来源。
- [33 项真实 React Mock 交互核收](../../v4-1/reviews/MOCK_BATCH_RUNTIME.md)：同源全通过，旧失败保留；不代签真实接口权限。
- [真实 r10](BROWSER_R10.json)：新 owned API/PG/Web、双 spec、原键、mobile consumer、SQL 及清理通过；[Main 原件独审](../../v4-1/reviews/FINAL_RUNTIME_R10.md) 已核收；原 API130、summary=NOT_WRITTEN 和未暴露的 Native browser exit 保留。
- [40 张实际原图视觉核收](../../v4-1/reviews/BROWSER_VISUAL_R10.md)：AI 工程范围无 P1/P2；人工视觉审批 NOT_RUN。

原工程 Full 4601 属于 4fec，Full PG 773 属于 e7，四 HTTP 案属于 54ab。
[QA_RESULTS](QA_RESULTS.json) 逐项列来源与限制；这些数量不相加，也不标为最终 SHA Full 重跑。

所有截图按原字节交付于 [BROWSER_SCREENSHOTS](BROWSER_SCREENSHOTS/INDEX.json)，
三尺寸为 1440/1280/390，原生 200% 仅原规定的驾驶舱与商品页。
手机表格部分右列需横向滚动，静态截图未验证真机触摸手势。
Native 浏览器单独 native exit 未暴露，未补造成 0；正式 Shell CFT 与 Node 退出另有原件。
原 r9 父失败、Mock r1—r3、CI/工程历史失败、未知、独立卷与 refs 都保留。

临时验收服务已关闭，无常驻或生产 Demo 链接；按 [复现流程](../../v4-1/proposals/LOCAL_DEMO_REPRODUCTION.md)
重新建立新 owned 资源，不重用旧 once 或过期窗口。真实模型/embedding、Woo 写、飞书外发、
Hosted、生产及 V4-2 均未启动。

最终交付包的[独立一致性审查](../../v4-1/reviews/DELIVERY_PACKAGE_746FB18.md)已核收。
审查目标为746fb18；之后仅追加本审查回执、关闭状态与哈希索引，不更改已验代码261f399。
