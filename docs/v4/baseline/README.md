# CommerceOps V4-0 A · 只读接单报告包

2026-11-03（台北）。**V4-0代码NOT_STARTED**。本目录是业务仓库外的规划/审查交付，不是新源码分支、真实Demo或正式实施授权。

推荐按顺序阅读：

1. [BASELINE_REPORT.md](BASELINE_REPORT.md)：三实时HEAD/tree/PR/CI、本地状态、M3证据、Harness差异、产品矩阵和集中决策。
2. [TASK_PLAN.md](TASK_PLAN.md)：35卡中的首五卡、唯一owner文件树、依赖与未来Gate。
3. [DOMAIN_SOURCE_CONTRACT.md](DOMAIN_SOURCE_CONTRACT.md)、[PERMISSION_DEMO_CONTRACT.md](PERMISSION_DEMO_CONTRACT.md)、[UI_ROUTES_CONTRACT.md](UI_ROUTES_CONTRACT.md)、[API_EVENTS_CONTRACT.md](API_EVENTS_CONTRACT.md)：四核心候选合同；均区分already_existing/proposed。
4. [v4-public-openapi.json](v4-public-openapi.json)、[v4-permission-matrix.csv](v4-permission-matrix.csv)、[v4-demo-seed-manifest.json](v4-demo-seed-manifest.json)：8端点、角色权限、未生成seed的候选附件。
5. reviews/：独立M3/Harness/产品审计，99功能与66页面矩阵，保留首审HOLD及修订后的最终候选回执。
6. evidence/：GitHub只读响应、初末工作树与参考包hash、文档结构验证、最终合同hash；FROZEN_MANIFEST.json为最终文件索引。

集中裁决在BASELINE_REPORT第7节：M3唯一起点/Harness暂不整合；30分钟不滑动TTL与cap3；V4-0最小双店seed及欢迎摘要；reset/UNKNOWN及创建丢cookie显式新空间；四合同审核后另发B授权。其余provider、embedding、飞书外发、Woo写、Hosted、生产/main/protection均不在当前许可内。

本次只读业务仓库与原包，新增内容仅在本外置目录。未执行受测代码/测试/collect/扫描器/PG/Web；没有创建git分支/worktree/commit/push或PR，也未触发CI。文档/JSON完整性检查不等于业务测试。候选接受不等于实现、权限安全实测、阶段Gate或用户批准。

最终独审：Astra与Terra均对八文件冻结hash接受ACCEPT_CANDIDATE，候选规范无未关闭P1/P2。用户审核及B授权仍待完成，身份SQL/ACL/锁序和实际PG/Web门禁不由文档接受代签。
