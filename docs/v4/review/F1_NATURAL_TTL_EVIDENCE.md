# F1 自然30分钟TTL实际证据独立核收

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_LOCAL_NATURAL_30_MINUTE_TTL_EVIDENCE。** F1本次自然到期观察及固定拒绝断言可核收；不签完整Q04所有撤权/重放分支、Full、Hosted或后续SHA实际运行。

受测source `047a43dafef90edea2eb532c2a03b6f850da0b9a` / tree `5c0699edb2d30889ce770ca9b05b56dab957ce10`，项目 `v4qa_naturalttl_20261104b`。只读ROOT `.audit/v4-0/ttl-F1`、原运行目录的case/阶段副本/probe成功日志，以及提交 `ee1dab651b1b42b99f602a02205a3d8710bb6fd9` 内 `docs/v4/acceptance/v4-0/TTL_F1.json`。未读私钥、未启动PG/HTTP/Web、未重等30分钟或重跑测试。

## 原始阶段与自然时间

原case的source/tree/project/scenario/deadline与ROOT_OUTER及tracked摘要一致；窗口2700秒，子网10.242.20/21。initial/before/after/success四文件与原运行目录逐字节相同。initial/before/after及最终natural_ttl.safe.json均仍为UNKNOWN，没有事后覆盖；另立success为NATURAL_TTL_OBSERVED_PENDING_REVIEW。success完整对象与tracked success_witness相同，各阶段累积观察一致。

以下为原DB UTC（台北日期均为11月4日，时间加8小时）：

| 事实 | 2026-11-03 UTC | 与expiry差值 |
|---|---|---|
| tenant/session created | 17:35:06.829447 | -1800秒 |
| tenant/session expires | 18:05:06.829447 | 0 |
| initial DB UTC | 17:35:07.941356 | -1798.888091秒 |
| before DB UTC | 18:04:38.095653 | -28.733794秒 |
| after DB UTC | 18:05:09.901774 | +3.072327秒 |

独立计算expiry-created精确1800秒；tenant与session创建/到期完全相同。before/after除db_utc外全部字段与initial逐值相同，tenant_revoked/session_revoked始终false。支持固定自然30分钟到期、没有滑动延长或显式撤销替代；不称在expiry精确同一微秒采样。tenant为 `c3474340-fc04-430c-9974-c9acb68cdf30`，原creation key在各阶段一致。

## 实际HTTP断言与成功标记含义

已读F1精确ttl_probe及其真实Visitor路径：初始创建并核原creation key、API expiry与DB一致；monotonic分段等待、不持续业务/PG轮询；到期前GET current且authorized_at<expiry；实际after DB UTC越过原expiry后，GET current、原shops集合每项summary、原creation-key receipt GET均要求HTTP401，并要求error code为SESSION_INVALID或EXPIRED。Visitor同时核no-store/Vary Cookie+Origin及strict response schema。固定seed/operator路径和ROOT摘要记为两店summary；本证据包没有逐响应wire或独立请求计数原件，不能声称另行亲见四条HTTP原文。

success只在上述所有断言、visitor.close及UNKNOWN汇总持久化成功之后才写入；它证明探针内部完成，不单独代表容器清理。原probe stdout为PROBE_COMPLETED_PENDING_REVIEW，driver scenario native0、状态SCENARIO_COMPLETED_PENDING_REVIEW，外层driver native0。结合精确源码和success可核收这些实际断言已执行；raw_per_response_wire仍NOT_CAPTURED，不补造状态行、响应body或具体错误码二选一。

## 外层清理与最终PG

driver records与tracked stages逐项一致：writers_stopped(probe0/API130)→API container stopped0→owner oneoffs inventory0→final PG readonly(1tenant)→down keep volume0→containers/networks gone0。API130保留为停止阶段退出值，不改成0或归作业务失败。自然TTL模式没有启动Web/browser，Web端口关闭不当作Web已运行。

final PG在UTC18:05:13.290021读取同tenant，epoch0/generation0/receipt1/tombstone1，digest `93ecab032a5d71d24677193359b933429434570ca33946eaf95ef3642da1e6f5`。ROOT_OUTER于18:05:14.749899（台北02:05:14）闭合，forced=false、initial namespace empty、cleanup_confirmed=true，登记进程组无live members、leftover IDs为空、final containers/networks为空、两端口关闭，保留卷 `v4qa_naturalttl_20261104b_pg_data`。这是原运行时证据核收，没有查询当前daemon来反推当时状态。

## 指纹与保留项

阶段SHA256：initial `332325d59e28a32d987d7c760497e312f3950b1a443fdacd8250f19412c98ac2`；before `3725a531f7f59e503c3366efbb80176537a95ad57bd6f73cffc061b739f0dc56`；after `1cac71f8170be50c71a74cfc380d8202d62593beee48352843136d31fc3d62a0`；success `e5917137c32593a95b4b25704a944df5a477323de194af5790a17e13b360d8b8`。

driver/finalPG/outer SHA256分别为 `c4825d1248943892fd5e4f8272098189387ff6ee7f6cd0784d1cc75b820c6036` / `403738e7b396e06a2f49e1798d264e098fb768716a3a9a2e09b46acb93b06ede` / `e8026e36df8aa32ee00c68001bce0ea85e10b4578d66079fb0938efdad2d6435`。

TTL-A服务前NoSuchImage失败与causeUNKNOWN保留，不因TTL-B成功而抹除。ROOT另报告的Full existing F1失败、未运行节点/G1及未捕获具体assertline属于独立Gate；本次TTL成功不补签它们，也不审尚未交付的表集合修复。未来合批若复用F1业务证据须证明有关字节不变，并继续标注实际受测F1，而非未来HEAD。
