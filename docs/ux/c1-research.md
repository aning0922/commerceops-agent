# Phase C1 · 官方产品模式研究

核实日期：2026-10-09（Asia/Shanghai）。方法：读取下列官方帮助中心正文；没有登录付费产品、操作真实商店或验证其事务实现。页面描述属于“官方文档可核实”，不是本项目实际运行证据。更新日期按页面显示记录；仅显示相对日期的页面不推算精确发布时间。

## 1. Prediko Pia

**已核实：** 官方Q2更新介绍Pia在应用内回答库存、预测、补货建议和SKU风险原因，支持上下文会话、提示建议、全屏模式；同时列出Slack、WhatsApp、Email渠道。页面仅显示“Updated over 3 weeks ago”，不以Q2标题推断发布日期。[官方 Product Updates (Q2)](https://help.prediko.io/en/articles/16024095-product-updates-q2)

**值得借鉴（本项目设计判断）：** 从“哪些商品有风险”这样的具体业务问题起步；结果中的SKU可以继续解释原因；自然语言输入旁给出少量支持的示例；查看表格时保留当前任务上下文。落点：M02输入、S03报告、M04解释面板，J01/J02。

**不采纳：** Pia所在产品的预测、PO、供应商、多仓调拨、主动跨渠道自动化和可配置分析看板均超出M1。我们使用七天确定性库存规则，不把Pia“预测”的名称或采购能力迁入界面；只保留既定飞书渠道。

## 2. Shopify Sidekick

**已核实：** 官方入门文档说明Sidekick使用当前页面上下文，缺少细节时提问；回答可带资源导航或Apply动作。新版管理台逐步推出侧边面板、展开/收起和历史入口；官方声明更改商店前需要用户批准。该文档明确布局可能因灰度版本不同，不能声称所有账户界面一致。[官方 Getting started with Sidekick](https://help.shopify.com/en/manual/ai-powered-tools/sidekick/set-up)

**值得借鉴（本项目设计判断）：** 解释面板绑定具体报告而不是悬浮的全站自由聊天；回答中的“查看报告/审批”指向业务对象；参数有歧义先澄清；用户可关闭面板继续读表格。落点：M04标记task/report上下文、M02澄清、S09任务子导航。

**不能直接照搬：** “用户批准”不证明具备CommerceOps的角色、版本hash、完整假设集合或T3/T4事务保证。M1不开放自然语言执行批准，不做语音、屏幕共享、文件上传、跨应用动作、角色权限编辑或自由修改已冻结请求。

## 3. Triple Whale Moby

**已核实：** Moby介绍页说明自然语言指定指标、时间、分组形成报告，以及历史查询和继续修改分析的入口；页面标注2026-07-26。[官方 Moby Introduction](https://kb.triplewhale.com/en/articles/9211940-moby-introduction)

官方结果解释文档说明可点击所用Business Logic打开说明面板，并有结果校验提示；页面标注2026-07-26。[官方 Business Logic Annotations](https://kb.triplewhale.com/en/articles/11777854-understanding-annotations-and-business-logic-in-moby-ai)

官方审批文档说明动作受账户审批行为控制，**部分动作可能自动运行**；需要审批时呈现动作、原因、详情、Actions log和选择后Submit。日志可显示pending/approved/rejected/expired/failed；页面标注2026-07-15。[官方 Review and approve Moby Actions](https://kb.triplewhale.com/en/articles/15458816-review-and-approve-moby-actions)

**值得借鉴（本项目设计判断）：** 报告附近就能查看口径；历史结果可回到版本与来源；审批先呈现对象、范围、原因和结果日志。落点：S03/M03、S04、S06。M1保留确定性表格为事实，LLM仅解释，不展示缺乏依据的业务收益或置信度。

**不采纳：** 不加入“下次自动批准/Ask every time开关”、账户写操作、广告/营销动作、撤销业务决定、自由SQL或全局Business Logic编辑。未知在途必须使用PRD规定的一次联合确认按钮，不照搬“选Approve后Submit”的通用形式，也不允许对话修订直接覆盖冻结版本。

## 4. 模式到M1的选择表

| 交互问题 | 可借鉴依据 | M1选择 | 明确代价 |
|---|---|---|---|
| 第一次不知道怎么提问 | Pia提示建议 | M02提供库存分析/任务进度/解释报告示例，标支持范围 | 不提供大规模Prompt Library |
| 读表格时想了解风险 | Pia原因问答、Sidekick页面上下文 | M04任务内解释侧栏，明确引用report/sku | 不跨任务默默合并数据 |
| 不知道数字从哪来 | Moby口径面板 | M03窗口、库存观测、公式、规则版本、原始与估算在途 | 更多披露占用空间，采用渐进展开 |
| 不知道批准会做什么 | Moby动作详情 | S04完整SKU/数量、内部动作、版本、期限、假设 | 批准范围不能只展示top-N |
| 等待后找不到结果 | Moby历史查询 | S02持久任务列表+S09结果，不另做聊天历史产品 | 问答历史围绕任务组织 |
| 失败后如何继续 | 项目自身PRD/事务合同 | S06区分决定、内部回执与投影；安全恢复/重算不同入口 | 不以竞品营销描述推导恢复能力 |

外观、色彩与尺寸是本项目独立建议，未复制竞品截图或宣称视觉一致。行为选择全部受M1权限和不可变计划合同约束，详见 [C1主方案](c1-product-design.md)。
