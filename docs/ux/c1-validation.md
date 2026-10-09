# Phase C1 · 评审与检查记录

日期：2026-10-09。状态：设计提交评审；C2未授权，M1业务未实现。基线为UX `77b69d3` / main产品合同 `a0d521e`；本轮仅改docs/ux，使用原独立UX工作树/分支及PR #24。

## 1. C1文档交付覆盖

| 用户要求 | 可评审交付 | 证据层级 |
|---|---|---|
| 阅读PRD/ROADMAP/DATA_MODEL/AGENT/FEISHU及已有UX | 主方案的业务合同、状态、T2/T3/T4/T6映射 | 仓库文档核对，不代表实现 |
| 三款产品研究 | [官方来源与采纳边界](c1-research.md) | 官方帮助文档正文，不是实机测评 |
| 完整M1信息架构 | [导航](sitemap.md)，11个Web页面、1张飞书卡片、5个辅助层 | 产品提案 |
| 每页目标/布局/指标/操作/跳转/角色/异常 | [逐页详设](c1-screen-specs.md)，17条screens记录 | 规格覆盖，未生成画布 |
| 自然语言到内部项全旅程 | [主方案J01–J05](c1-product-design.md) | 主旅程及澄清/拒绝/同步/渠道分支 |
| 关键交互矩阵 | 主方案§5与45条interactions记录 | 稳定ID、守卫、结果、异常、合同缺口 |
| 风格与易用性 | 主方案§6 | B2B表格/密度/响应式/键盘与文案建议 |
| 待明确产品决策 | 主方案D01–D09 | 推荐项、责任与C2阻塞范围 |
| 保留工具链、导出/恢复缺口 | 原[A/B验收](acceptance.md)、主方案§8 | POC及部署未改变，未重跑基础设施测试 |

## 2. 本轮实际检查

| 实际检查 | 结果与边界 |
|---|---|
| `uv run --frozen python tools/design/penpot/check_contract.py` | 通过：已有3个POC屏幕/4控件/14次点击的记录引用一致；读取历史证据，未重新点击原型 |
| `uv run --frozen python -m scripts.check_docs` | 28份Markdown，errors=0；本地链接/围栏检查通过 |
| C1结构化引用核对（一次性只读Python检查） | 17个页面/辅助层、45个控件；source/target/also_on/alternate_targets、角色、逐页必需字段均有效；M1状态仍planned_unmapped、UUID为null |
| 与`77b69d3`比较 | POC数组完全相同；tools/design/penpot、docs/ux/evidence、design-tokens.json无差异；变更均在docs/ux |
| `git diff --check` | 通过，未发现差异空白错误 |
| `uv run --frozen python -m scripts.scan_secrets` | 当前内容、index和全部可达Git历史均findings=0；暂存后提交前再次执行 |

没有运行新的Penpot操作、Compose重启、备份恢复、业务pytest、真实飞书或Next.js/Playwright。GitHub基础CI按PR新head单独核对，不把旧head的成功转记到新提交。

## 3. 用户评审与C2进入条件

- [ ] 确认三个主导航、任务上下文子页和17个页面/辅助层范围（D09）。
- [ ] 确认T2自动送审推荐，不新增人工送审步骤（D06）；如改变先修业务合同。
- [ ] 确认对象读范围，admin不默认业务读/审批，角色可显式兼任（D01）。
- [ ] 明确澄清、重算与人工恢复的产品选择及领域合同责任（D02–D04）。
- [ ] 确认只读管理说明、期限/新鲜度展示、业务导出取舍（D05/D07/D08）。
- [ ] 用户明确批准进入C2。没有这条确认不生成正式批量页面。

## 4. 后续验收，不作为本轮通过项

C2须把J01–J05和四类角色映射到真实Penpot状态/控件实例，实点导航与弹窗，验证完整SKU披露、窄屏/焦点、保存版本与UUID回读；把截图、点击证据与合同commit绑定。原POC的14次点击不能给M1这些动作勾选。

Phase 3–4须读取已批准规范并在Next.js实现，Playwright覆盖正常旅程、无权限/权限撤销、重复/并发冲突、过期/计划变化、加载/空/失败/未知、工作项完成关闭和版本历史。真正的幂等、T3/T4/T6原子性、真实飞书与Base结果分别由集成/真实环境测试证明。这里列的是未来验收输入，没有运行这些业务测试。

设计变更需同步产品方案、screens/interactions、已批准Penpot、代码和测试。发布记录绑定contract_version、Git commit、M1 visual_revision和测试run；不能沿用POC revision冒充正式M1映射。未决合同保持显式blocked/proposal标识，避免代码生成误把提案当成已授权业务接口。
