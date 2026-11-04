# V41 lifecycle generation Mock窄修独审

2026-11-04（台北）。结论：`ACCEPT_EXACT_FIXTURE_DELTA_SOURCE_ONLY`，无新增实质P1/P2。source `af033e00dba80353d21e545b3e58809b9869eadd` / tree `2209cb0e1aac573de52a5ce32c744aad38415f64`，父 `4da424a5b82b8e35ce7d601e0a04ab6b62c35df9`。唯一变更lifecycle.spec.ts最后一个changed identity generation case，10+/2-；产品、gate、client、schema及配置均未改。

静态诊断已独立确认：原fixture默认seed-summary使用auth_generation0，而该case切换后session与业务详情均为generation1。真实chooseShop按同身份五字段严格核summary，包含auth_generation；旧summary不符应当清屏，不应放松产品边界。本修片仅为该case覆盖summary，使正常重新选店与当前已刷新session一致。

新增精确summary route置于generation切换后、focus触发之前，沿用原cors包装；OPTIONS按原预检处理，不计入summaryGenerations。实际handler严格要求GET、完整pathname及唯一shop_id=id query，并核X-Demo-Generation等于当前generation；响应使用同generation、同shop和既有合成source/counts。恢复后核实际summary响应context代次，并要求调用记录精确[1]。没有用宽松兜底或多次请求来满足断言。

原focus事件、新session等待、旧详情dialog清除、用户重新选店、编辑按钮恢复及旧草稿消失全部保留。独立Git字节比较确认最后case之前全文件相同；click/selectOption/fill/focus事件数量不变，没有新增sleep/retry/timeout或改断言文案。新增summaryRead在重新选店之前登记，仅观察原动作产生的GET。

本轮只执行静态字节/结构断言native0，未运行测试体、浏览器、服务、PG、网络、build、Full或CI，也未执行作者/tmp脚本。作者纯校验/TS/33collect/preflight为转交证据，collect不记PASS。Root转交r3为9个batch PASS、合计29pass/1fail/3NOT_RUN，原实际失败及具体动态根因UNKNOWN保持，不据本修片倒签旧案或未来r4。

仅此review文档经指定changed-file/index预检后普通冻结，不push。修片可供Root集成并按实际新source安排验证，尚未证明Mock整批或产品实际generation交互通过。
