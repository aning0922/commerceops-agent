# V4-0 B 本地托管实施授权

2026-11-03，台北。用户在主控会话01a19f1b-f4c0-75c1-a9f0-8f8b88db72d5明确：“审核通过，接受上述推荐方案和四份合同，授权按B模式启动V4-0本地托管实施。继续用可见会话分工、动态调整模型和推理强度，及时提交，完成V40-01—V40-05并通过本地Gate后交付；不自动进入V4-1，不触发Hosted CI、真实外部调用或生产发布。”

A原件位于baseline/，其NOT_STARTED/PENDING/B未授权是A结束时历史事实，不覆盖本授权。冻结八文件哈希清单与Astra/Terra最终独审均保留；本批用户已接受其方案和四合同，未以此代签代码、身份桥接SQL/ACL/锁顺序、真实PG/Web或阶段Gate。

本批唯一业务基线已重新git ls-remote核实为M3 952e6246deb01ec763f2541d9f316753987744f3 / tree43e4e732824e23b991660a4f7882ba8f5a265df1；main6d3a8f7b、远端Harness684e645f均未变。原M3/Harness与README工作树保留，不合Harness、不改main、不push/远端写。

范围：V40-01只读审计沿用并重核HEAD；V40-02合同沿用本批核收；V40-03新服务器DemoSession/身份隔离/角色店铺；V40-04同源双店seed、reset/回滚；V40-05欢迎入口、真实API/PG/Web及旧M3对应完整本地回归。阶段Gate后交付，不进V4-1。

ROOT协调/冻结/集成；SCHEMA/API唯一作者控制迁移/shared DTO/API与seed/reset；WEB独占V4专属前端；QA独立E2E/验证，REVIEW对精确提交独审。模型Sol日常medium/复杂后端high，UI Terra high，关键权限与并发Astra high；按任务切换，actual token/cost若不可见UNKNOWN，不使用付费API fallback。

实现前专项Gate：新identity绑定/完整credential检查、旧bound session失效、token跨API拒绝、SQL锁序/ACL、seed固定规模/日期/hash与tombstone保留。迁移head仍0023_p6_copy_drafts，新0024单owner线性推进；旧auth如需窄helper先ROOT精确释放/专项审查，不泛化旧权限。

每次新owned真实资源须先记录project/database/ports/PID/volume/source、绝对UTC与cleanup reserve；只用本批新凭据/资源。单Worker保持，不开每tenant Worker或新Graph任务。未知资源不操作；同因重复故障先定位，不盲重试/自动续预算。历史139根因UNKNOWN、旧失败/证据/账本/预算不重置。标准PG临时卷删除和独立Web保卷按各资源实际合同分列。

每个可审切片检查后及时普通commit，冻结移交独审后ROOT普通merge，不reset/amend/force。Hosted/真实模型embedding/飞书外发/Woo外写/生产/main/protection及新权限扩张均未授权。最终报告实际Full/Hosted/未跑、源SHA/tree、命令exit/count/耗时、失败与cleanup，不预填通过。
