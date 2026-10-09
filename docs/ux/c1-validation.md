# Phase C1 · 外部评审修订与检查记录

版本 `0.2.1-c1-revision`。原稿 `fabf1a6` 外部评审有条件通过；本次修订已通过用户产品评审，本文件记录C1修订当时仅授权B1a，M1业务未实现；后续B1a视觉通过、本次B1b获授权与实际验证见[B1b](c2-b1b-delivery.md)。本轮沿用独立UX工作树/分支及PR #24，只改docs/ux。

## 1. 评审意见落实

| 意见 | 本次修改 | 合同边界 |
|---|---|---|
| D01最小权限与兼任 | 按角色自身scope授权合并，禁止跨角色拼接；共同拒绝优先；明确三种兼任例子 | 产品方向接受，服务端过滤/撤权BC01 pending |
| D02两种澄清 | Web M02/B35提交前草稿；飞书F02/B47任务关联异步proposal | 不增状态/API，BC02 pending |
| D03三类重算 | 待执行计划、rejected/expired、completed新周期分别规定；B46只开新草稿 | 状态迁移/原子失效/API为BC03 pending；旧批准不可复用 |
| D04不启用通用恢复 | E09/B09保留ID但不渲染/绑定 | 不新增恢复权，自动恢复/安全对账按既有合同 |
| D05–D08保持精简 | 只读管理、自动送审、实际期限、无额外报告导出 | 相应未定传输/config仍pending |
| D09按批设计 | B1主闭环、B2身份异常、B3辅助/待合同；共用组件与状态变体 | C2整体仍需用户正式授权 |
| 飞书/窄屏完整披露 | 全部SKU/风险在最终动作前；不全或截断不能批准；首批验1/20条 | 真实客户端限制/回退BC06 pending |
| 不冒充实现 | 18个逻辑界面、47个事件ID（1个保留无UI）；全无M1 UUID、implementation未实现 | 所有未定合同有proposal/pending及BC引用 |
| 工具缺口独立记录 | 原生版本/持久卷/配套私有备份最低方案及局限 | 本轮未导出/备份/恢复，无新增基础设施 |

完整依据见 [决策记录](c1-decisions.md)、[分批计划](c2-batches.md)、[页面详设](c1-screen-specs.md)、[结构化屏幕](screens.yaml)及[交互](interactions.yaml)。F02是已有M1澄清能力的渠道消息规格，不增主导航。

## 2. 实际检查

原C1的检查及CI成功属于fabf1a6历史记录，不转记为本次通过。本次实际检查如下：

| 检查 | 结果与边界 |
|---|---|
| `uv run --frozen python -m scripts.check_docs` | 30份Markdown，errors=0；本地链接/围栏通过 |
| `uv run --frozen python tools/design/penpot/check_contract.py` | 通过；核对历史3个POC屏幕/4控件/14点击记录引用，没有新点击 |
| 一次性只读结构化核对 | 18界面/47事件ID（1保留无UI、46计划）；source/target/also_on/alternate_targets、角色、字段和BC引用有效；首批12个页面/辅助层的主要事件目标均在首批 |
| 修订语义核对 | B35留M02草稿、B47独立飞书proposal；B09无UI，B36/B47未启用；D01–D09产品决定与BC01–BC07 pending一致；逐页Markdown字段与screens一致 |
| 与fabf1a6比较 | 业务状态枚举、POC数组、工具/evidence/token文件完全不变；变更仅docs/ux，C2授权false |
| `git diff --check` | 通过 |
| `uv run --frozen python -m scripts.scan_secrets` | 当前内容、index、全部可达Git历史findings=0；暂存后提交前再次执行 |

本轮未操作Penpot、MCP设计实例、Compose、业务数据库或飞书配置；未运行导出/备份/恢复、业务测试或Playwright。新head的GitHub基础CI在PR按实际结果记录，不作为新增业务验收。

## 3. 决策与进入条件

- [x] 已接受三个主导航和任务上下文结构；C2使用组件复用，优先主闭环。
- [x] 已接受D01最小权限原则及D02/D03分类方向，本稿补兼任规则和合同边界供复审。
- [x] 已接受D04不启用通用手动恢复。
- [x] 已接受D05–D08推荐：只读管理、T2自动送审、按实际期限展示、无额外业务导出。
- [x] 用户已确认0.2.1修订通过本轮产品评审；明确仅授权B1a。
- [ ] BC01–BC07由对应后端/领域负责人确认；未确认部分保留pending，按批次限制功能范围。
- [x] 用户明确授权C2-B1a；其余批次未授权。

## 4. 后续验收，不作为本轮通过项

C2须把J01–J05和四类角色映射到真实Penpot状态/控件实例，实点导航与弹窗，验证完整SKU披露、窄屏/焦点、保存版本与UUID回读；把截图、点击证据与合同commit绑定。原POC的14次点击不能给M1这些动作勾选。

Phase 3–4须读取已批准规范并在Next.js实现，Playwright覆盖正常旅程、无权限/权限撤销、重复/并发冲突、过期/计划变化、加载/空/失败/未知、工作项完成关闭和版本历史。真正的幂等、T3/T4/T6原子性、真实飞书与Base结果分别由集成/真实环境测试证明。这里列的是未来验收输入，没有运行这些业务测试。

设计变更需同步产品方案、screens/interactions、已批准Penpot、代码和测试。发布记录绑定contract_version、Git commit、M1 visual_revision和测试run；不能沿用POC revision冒充正式M1映射。未决合同保持显式blocked/proposal标识，避免代码生成误把提案当成已授权业务接口。

本页是C1检查历史，不把旧检查转记为B1a。实际B1a设计证据及本次检查见 [B1a交付](c2-b1a-delivery.md)。
