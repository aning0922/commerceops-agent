# V4.1 风险与证据边界（DRAFT）

正式 r8 browser、最终截图和人工视觉审阅仍 pending；本页不预填最终通过。证据必须按各自 source、窗口和验收范围引用，不把旧结果改挂到新候选。

- **产品范围**：14 个导航是范围入口，12 个是本期业务视图；规划类别可见不等于业务已开放。仅使用合成演示数据；模型关闭，规则洞察不冒充模型生成；Woo 和飞书零外部写入，模拟履约不表示真实履约。
- **运行环境**：自然 24 小时 GC/过期行为为 NOT_RUN；Hosted、amd64、production 和 V4-2 均为 NOT_RUN，不从本地演示推断。具体状态以最终回执为准。
- **工程证据**：完整工程通过属于 `4fec4a7416d7b9434d979f461d5da78508cfb850`；运行后的 216 个安装文件字节、after identity/wrapper 及停后 ps 不存在仅有当时 owner 封存声明，不提升为独立复核。见 [证据矩阵](../../v4-1/proposals/FINAL_GATE_MATRIX.md)。
- **FullPG 证据**：`e7aeeca90e98cc4af5b5f8f8ba0faddd33182bd6` 的 596 + 177 严格配对独审通过；容器内文件逐字节核验为 NOT_RUN。见 [配对独审](../../v4-1/reviews/PG_PAIR_e7ae_FINAL.md)。该结果不代签其他 source 或 browser。
- **历史失败与 UNKNOWN**：保留旧失败、原始回执和未知状态，不覆盖或自动重试。按 Root 转交，r7 业务单项通过，Shell 首次在 `read_at` 处失败、整案未通过；该次具体 Request lineage 为 UNKNOWN，不猜测根因。下一测试相关修复须以冻结源码及新案事实为准。
- **清理与保卷**：r7 按 Root 转交已关闭本案全部资源；关闭只证明该案对应范围，不能代签功能或全机无资源。按新案原回执分别记录进程、容器、网络、端口和卷 identity；HTTP owned 案依合同 scoped down 并保留原卷，FullPG 临时卷按其独立清理回执处理，不混同两种策略。失败或清理 UNKNOWN 保留原件，禁止借删除原卷或全局清理补绿。

复现须使用新授权的 owned 案、当前源码及新配置，历史服务和 URL 已关闭；参见 [复现草案](../../v4-1/proposals/LOCAL_DEMO_REPRODUCTION.md)。最终发布、真人审阅和阶段结案以 Root 后续真实回执为准。
