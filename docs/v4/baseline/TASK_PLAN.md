# V4-0精确接单、单owner地图与Gate（候选）

状态：A文档审查，不授权下列代码改动。全部未来仓库路径均相对commerceops-agent；不在旧工作树写入，不创建V4 branch/worktree。B明确授权后只从当时重新核准的M3 HEAD新建V4集成worktree，记录commit/tree并保留M3/Harness原树。当前M3=952e6246deb01ec763f2541d9f316753987744f3。

## 单owner精确路径（ROOT权威地图，覆盖各独立审计中的示例路径）

| 路径 | 未来唯一owner | 变更限制 |
|---|---|---|
| docs/v4/** | ROOT | 本轮外置报告，B才普通导入经审合同与任务证据，不导入整个原型包 |
| backend/migrations/versions/0024_v4_demo_foundation.py | SCHEMA/API | proposed，重核head仍0023后新增；demo tenant/session/receipt/epoch/最小overlay约束与窄ACL，不能改0019-0023；若期间迁移head变化必须重签，不占用冲突revision |
| backend/src/commerceops/application/v4_demo/{__init__,contracts,policy,seed_contract}.py | SCHEMA/API | 新域DTO/规则；旧WebActor/guard只复用，不修改旧批准/nonce/hash |
| backend/src/commerceops/infrastructure/{v4_demo_store,v4_demo_sessions,v4_demo_seed}.py | SCHEMA/API | 认证映射、tenant事务、当前身份再校验、版本种子与重置；session/reset同owner，不另开seed owner |
| backend/src/commerceops/entrypoints/v4_demo_http.py | SCHEMA/API | 8个候选端点、专属boundary/Origin/CSRF/限流、OpenAPI；未实现 |
| backend/src/commerceops/entrypoints/api.py | SCHEMA/API | 仅默认关闭V4装配和独立OpenAPI错误映射；旧middleware/API schema字节回归，不广泛重构 |
| backend/src/commerceops/entrypoints/database.py | SCHEMA/API | 如确需新增demo窄grant action，先Root释放明确diff，不变更原grant-runtime语义 |
| scripts/v4_demo_seed.py | SCHEMA/API | 新owned初始化CLI、fixture版本/hash、失败保留；不可调用旧私有服务/配置 |
| tests/v4/{test_demo_sessions_pg,test_demo_seed_pg,test_demo_api}.py | SCHEMA/API | 新功能作者测试，独立QA只读重现，不能多人写公共conftest |
| frontend/app/v4/[[...path]]/page.tsx | WEB | 新专属路由，旧catch-all默认只读；实际Next路由优先级须验证 |
| frontend/components/v4/{demo-welcome,demo-session,demo-reset}.tsx | WEB | V4-0首次进入/双店摘要/角色体验/重置/退出，非14模块完整Shell |
| frontend/lib/v4-{demo-client,demo-state,types.generated}.ts | WEB | DTO来自SCHEMA/API独立OpenAPI，生成输出WEB独占；安全字段不能推导权限 |
| frontend/v4-tests/**、frontend/playwright.v4.config.ts | WEB | 新UI用例/配置；共享live harness与旧m3-tests只读，必要改动另释 |
| tests/e2e/v4/** | QA | B中新owned全链编排/独立核验；只消费冻结源码/API，不代写业务 |
| 旧业务域/worker/checkpoint/审批、旧迁移、compose/锁/workflow、Harness全部文件 | 无V4-0改动owner | 默认受保护；若实际阻断，暂停受影响路径交ROOT，不扩大卡范围 |

## 5张卡的依赖、交付与Gate

1. **V40-01 / ROOT**：完全只读远端分支/PR/Issue/Checks、M3证据/源码、Harness8共享文件、原型模拟差距、99功能66页面矩阵。当前交付为本目录BASELINE_REPORT和evidence/reviews；不称真实PG验证。
2. **V40-02 / ROOT**：依赖01；四候选合同、OpenAPI草案、权限CSV、seed manifest、文件owner和回归计划。独审后按hash冻结为候选文档，仍须用户审核与B独立授权。当前可完成文档，不等于阶段V4-0 Gate通过。
3. **V40-03 / SCHEMA/API**：依赖02获准+B；独占新0024迁移、application/contracts+policy、store+sessions、v4_demo_http、api装配、test_demo_sessions_pg/test_demo_api。先固定接口/迁移线，再PG验证身份、Origin/CSRF、跨tenant/shop、persona、到期/撤权/logout、原key。每个独立可审切片普通commit，不amend/force。
4. **V40-04 / 同一SCHEMA/API**：依赖02+03；seed_contract、v4_demo_seed、CLI、test_demo_seed_pg；同一store内reset事务由此owner串行接线，不能与03并改。共享迁移只由该owner在创建前规划，一旦03冻结不改旧revision；确需第二新revision须Root增量审。最小联合双店、六异常对象关联、固定日期/计数、失败原子回滚、重复seed/reset与跨tenant不变、清理/tombstone证据。
5. **V40-05 / WEB（UI）+QA（独立E2E）**：依赖03+04冻结API/种子；WEB与QA分别拥有上表不重叠路径。欢迎/真实服务端身份/双店摘要/切persona/reset/logout、1440/1280/390与键盘状态，至少一个新owned API/PG/Web全链；既有M3接口和界面对应回归。首次首屏是seed欢迎摘要，不抢V41-02/03经营KPI工作。

可并行：02批准后WEB做专属组件与合同状态测试，API串行03→04，QA只写独占新owned编排；API未冻结之前不宣称联调通过。迁移/共享schema/API根装配/reset提交一律单owner串行。ROOT不承担全部业务作者或唯一审查者。

## 未来B真实验证和资源合同（本轮均NOT_RUN）

新owned对象必须登记project/database/namespace/volume/host-port/PID/owner/sourceSHA/绝对UTC截止及cleanup reserve，禁止探测/启动旧M1/M2/M3私有库和读取历史秘密。PG17.11+pgvector0.8.7沿用M3显式构建/指纹绑定，不复用旧receipt、不开额外Worker；仅新生成非历史凭据由资源owner登记。实际建测资源及本地预算依B授权后精确TaskSpec，不以本计划当窗口已开放。

最小矩阵：two visitors互读404；tenant内两个shop的显式scope反例；operator伪造role拒绝/admin无grant；persona当前主体与旧CSRF/actor拒绝；TTL/撤权/logout；同key同payload原回执/异文409；seed事务失败无部分记录；reset同key并发一次epoch推进，跨tenant digest不变；reset与旧写线性化；DB失败保留UNKNOWN；cookie/响应整体丢失不重POST；第4/5访客限流不踢既有3；移动菜单/focus/Esc/200%/reduced-motion。

高风险认证/迁移阶段必须当前动态完整PG集合、G1三/G2六、旧M3对应日报/询单/copy及旧Web/N01、原来源/锁/工具/清理strict pairing。719仅历史基数，新增后数目靠未来实际collect固定精确源，不预填719+N。完整scripts.check、所有PG/浏览器Full在B执行后才填actual；Hosted/amd64独立未授权，NOT_RUN。Harness不可直接merge，先独立适配合同，不在V4-0内偷换workflow。

## 交付和停止

按TaskSpec→作者commit→独审精确SHA→必要owned真实验证→ROOT普通集成；每卡报告demo步骤(>=3)、源SHA/tree、实跑exit/count/elapsed、失败、资源stop/cleanup、未跑Full/Hosted。出现未知资源、相同未知重复故障、预算或合同阻断只停受影响路径，其他独立文档可继续。到V4-0 Gate停止，不进入V4-1。模型分派Sol medium/复杂后端high、UI Terra high、并发权限Astra专项；实际token若不可见写UNKNOWN，不付费fallback。
