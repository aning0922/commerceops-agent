# V4 文档与阶段归档入口

2026-11-04（台北）：V41-01—06 六卡在合同受控合成本地范围内已完成并独审核收。
业务代码冻结为 `261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e`，归档/PR 正待主控推进并合入 main，
实际合并结果另记。
主控本次核 main 仍为 `6d3a8f7`；归档使用独立新分支。合并须用户后续确认与必要CI授权，并满足原保护检查，不绕过pending checks。 归档记录见[主控集成说明](archive/V41_MAIN_INTEGRATION.md)（由主控在集成时提供）。当前暂停后续开发；用户尚未交新研究，V4-2未启动，原V4-2及以后路线仅供历史参考。

| 需要了解的内容 | 入口 |
| --- | --- |
| 原规划、来源与冻结基线 | [基线报告包](baseline/README.md)、[冻结索引](baseline/FROZEN_MANIFEST.json)（均按原日期阅读） |
| 四份原始核心合同 | [领域来源](baseline/DOMAIN_SOURCE_CONTRACT.md)、[权限演示](baseline/PERMISSION_DEMO_CONTRACT.md)、[UI路由](baseline/UI_ROUTES_CONTRACT.md)、[API事件](baseline/API_EVENTS_CONTRACT.md) |
| V4-0 实施与交付 | [实施授权](IMPLEMENTATION_AUTHORIZATION.md)、[本地交付](acceptance/v4-0/DELIVERY.md)、[最终Gate](acceptance/v4-0/FINAL_GATES.json) |
| V4-1 六卡合同 | [阶段范围](v4-1/STAGE_SPEC.md)、[合同](v4-1/CONTRACTS.md)、[批量与移动补充合同](v4-1/BATCH_AND_MOBILE_ADDENDUM.md) |
| V4-1 最终验收与来源 | [交付核收](acceptance/v4-1/REVIEW.md)、[QA结果](acceptance/v4-1/QA_RESULTS.json)、[交付索引](acceptance/v4-1/MANIFEST.json)、[功能状态](acceptance/v4-1/FEATURE_STATUS.json) |
| 本地演示与复现 | [演示流程](acceptance/v4-1/DEMOS.md)、[新owned案复现说明](v4-1/proposals/LOCAL_DEMO_REPRODUCTION.md) |
| 实际截图与视觉边界 | [40张原图索引](acceptance/v4-1/BROWSER_SCREENSHOTS/INDEX.json)、[AI工程视觉审查](v4-1/reviews/BROWSER_VISUAL_R10.md) |
| 风险、未验与历史失败 | [风险说明](acceptance/v4-1/RISKS.md)、[分层Gate矩阵](v4-1/proposals/FINAL_GATE_MATRIX.md) |

当前14导航/12业务视图不等于原99功能/66页全部完成。历史Full工程4fec、FullPG e7、HTTP54ab与最终261
按各自来源核收，旧失败和UNKNOWN保留。40原图的AI工程视觉已通过；用户人工视觉、真机触摸、真实
模型/embedding、外部Woo/飞书业务、Hosted与生产仍按各自未验状态记录。

所有临时验收服务已关闭，没有常驻演示URL；需要复现时按说明另建获准的新案，不复用旧once或过期窗口。
后续研究与阶段范围须由用户新的输入决定。本入口只导航已有材料，不启动资源或授权新阶段。
