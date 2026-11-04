# V41 UI 验收清单独立文档审查

日期：2026-11-04（台北）。结论：`ACCEPT_DRAFT_CHECKLIST_NO_NEW_RUNTIME_OR_VISUAL_ACCEPTANCE`；限定本次文档差分，无实质 P1/P2，供 Root 单独普通集成。没有核收新运行或人工视觉结果。

审查对象为 `83e343c5ebd7bc4600f94c5e9ab40a9d6749afa8` / tree `d318ba0c84726bfb7cfa48e95fe7ca23e8123c9e`，父提交 `754e8796b88dca7c11c2d2956c8645486b2d55a2`。精确差分仅新增39行 `docs/v4/v4-1/proposals/UI_ACCEPTANCE_CHECKLIST.md`，文件 SHA256 `06b7c08ce792d6f97ca7a9aabb2fc831c659265916f2293b3c33e1c3d2f657b7`。清单所指产品审阅基线为 `4fec4a7416d7b9434d979f461d5da78508cfb850` / tree `20044a26fe39850cc31943bf4e328abba3936f3e`；文档作者分支不是该完整集成运行源码，不由本审查签其全部祖先。

## 核对依据与结果

- 在精确4fec读取 `STAGE_SPEC.md`、`CONTRACTS.md`、`UI_ROUTES.json`、`UI_SLICE_01.md`，以及路由解析、业务视图与已有spec源码。14个导航名称及12个业务视图名称/路径逐项一致；欢迎/演示空间/演示设置属于辅助入口，设置页未计入12页。前端路由manifest与合同字节相同，SHA256均为 `43ef769019a1bcad09b03c1e7db3daead7005b0bd8fc10504dfa26a8bdefb067`。产品组件、app、路由manifest/解析及路由合同在作者父提交与4fec之间无差异。category入口的可进入状态未提升为业务完成。
- 按冻结 `BROWSER_E466_R2_BUSINESS_PARTIAL.md` 与精确业务spec核对：e466/r2仅支持会话创建/切店、dashboard/期间/drilldown/非模型助手、SKU筛选和CSV下载、标签版本回读、单订单演示履约与未知支付按钮禁用、CSV/XLSX导入及来源、真实分页和隔离等所列业务partial。清单将详情关联保留final pending，履约限定单订单；这些层级是该行已有的相关证据，不代表整行每个预期或整条页面路由均经过真实浏览器验收。例如履约模拟行不能据单订单详情操作推断该独立路由已实际访问。
- 旧业务partial明确绑定 `e466f03436ba726b6050b10e879da68d80c7e372`，8997ms/retry0；整案Shell失败/Node1保持，390、offline/hidden、late ACK、Native均未由此核收。清单开头明确不代签4fec或完整浏览器；后续候选及Root转交的更新运行情况没有被加入这份历史partial。
- 按冻结 `HTTP54AB_FOUR_CASES.md` 核对HTTP层级：来源是 `54ab68f054a136f98dac0a50986caced11362fbd` 四个有限本地HTTP案；其分页、list/detail、支付与来源等API证据不证明订单列表/异常订单页面布局、点击或人工可读性。清单保留Mock/HTTP区别，最终实际版本及证据槽位仍待填写。
- `UI_MOCK_R4.json` 明确属于旧 `5cd587119e707d31c285424afaf9f74f2b421e6e`、11项Mock，业务API/权限/PG/provider未运行。清单的Mock行不能解释为4fec真实业务通过或逐页完整视觉验收；其未勾选、逐项证据及最终人工pending规则与此一致。本轮只读这份已冻结公开记录，没有重读其私有运行原件。
- 1440/1280/390、导航/焦点/Esc、reduced-motion、实际offline/hidden、受控迟到ACK、原生200%及人工可读性均保留final pending。截图不得代替操作/同源/人工判断，模型未启用、合成演示与Woo零写界限准确。加载/错误/恢复的Mock证据未提升为真实浏览器结果。

这是一份供后续逐项填写的验收清单，不是所有页面已通过的证明。表格“当前层级”应按其开头“最高相关层级”的限定阅读；填写最终结果时仍须逐项记录实际source、具体操作、证据及结论，不能将同一行已有partial扩展至尚未验证的预期。无需为本次文档接纳重跑既有业务案。

本轮仅精确Git对象、冻结公开回执和源码只读核对；未读作者WIP或未冻结NoDefaults fixture，未运行测试、collection、服务、浏览器、PG、Docker、SDK、Full或CI，未push。仅新增本审查文档，并在普通提交前执行指定changed-file/index预检。
