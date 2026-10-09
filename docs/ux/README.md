# 本地设计工具链与M1产品设计索引

日期：2026-10-09（Asia/Shanghai）。阶段A/B已提交工具验证；C1修订0.2.1已通过产品评审；B1a视觉评审已通过；本轮获授权制作 **C2-B1b审批、内部工作项与Agent轨迹原型**，交付后等待视觉与交互评审。B2/B3尚未授权。现有POC不代表业务功能、权限服务或M1 Gate已完成。

- **[B1b正式设计、原型验证与限制](c2-b1b-delivery.md)**
- [B1b当前UUID映射](evidence/c2-b1b/design-map.json)
- **[B1a视觉交付、截图、组件、实点证据与限制](c2-b1a-delivery.md)**
- [正式M1 UUID映射](evidence/c2-b1a/design-map.json)
- **[C1完整方案：旅程、权限、交互矩阵、风格、待决策](c1-product-design.md)**
- [18个逻辑界面逐页详设（含F02 proposal）](c1-screen-specs.md)
- [已接受设计决策、后端待确认合同与最低恢复保障](c1-decisions.md)
- [C2第一批及后续批次/验收计划](c2-batches.md)
- [Prediko Pia / Sidekick / Moby官方研究](c1-research.md)
- [C1评审清单与实际检查](c1-validation.md)

- [选型与限制](tool-selection.md)
- [实际验证与验收边界](acceptance.md)
- [提交前实际检查](validation.md)
- [产品交互原则草案](product-ux.md)
- [页面导航草案](sitemap.md)
- [页面与状态](screens.yaml)、[事件与动作](interactions.yaml)、[POC 设计值](design-tokens.json)
- [真实画布 ID 映射](evidence/design-map.json)、[实际点击事件](evidence/prototype-ui-events.json)
- [独立部署与维护](../../tools/design/penpot/README.md)

`POC-*` 是已制作的工具测试界面；`M1-*` 是正式产品ID；B1a样板已映射，B1b关联页面在同文件增量制作，B2/B3仍待授权。两者不得相互冒充。YAML 文件采用 YAML 1.2 兼容的 JSON 语法，目前可用标准 JSON 解析器检查。`contract_version=0.2.1-c1-revision` 与 `visual_revision=ux-poc/0.1.1` 分别描述C1评审稿和原样保留的测试画布，不表示全部M1视觉或业务Gate通过。47个事件ID中B09为不渲染的保留ID，其余46项为计划交互；18个逻辑界面含F02渠道proposal，全部未实现业务。其中5个B1a样板已映射正式文件（S09/M03仅最小覆盖）；14个控件实例实点，B1a视觉已通过。BC01–BC07仍待后端确认；B1b设计已获本次授权；当前B1b映射与验证详见新交付文档。

本分支基于 main `a0d521e`，不修改 Phase 1 主控的 STATUS、G3、CI、业务数据库或真实飞书配置。该 commit 的 STATUS 仍包含较早的“PR #9 待合并”记录，而实际 Git 已含 PR #9 merge；本轮以产品文档为范围依据，不代替主控修订阶段事实。

![两个原生界面与弹窗在画布中平铺](evidence/poc-canvas.jpg)

## C2-B2 当前交接

2026-10-09 用户转述 B1b 外审有条件通过，明确授权本轮 B2。当前候选版本为 `m1-ui/0.3.0-b2`，见 [B2 交付、实际验证与未完成项](c2-b2-delivery.md)。本文件早期授权/批次状态为历史记录；最新授权以本节及机器合同为准。设计候选待外部评审，BC01–07 与全部业务 implementation 仍 pending / not_implemented；未合 main，B3 未授权。


## C2-B3 当前记录（2026-10-10）

用户确认B2外部产品与交互评审通过并授权B3；本轮设计、合同检查及原型交接已完成。[B3交付](c2-b3-delivery.md)与[冻结候选/前端交接](ux-freeze-candidate.md)供最终评审。命名版本m1-ui/0.4.0-b3，数据库及命名快照revn57（MCP API回报56）；55次实际控件点击尝试，53通过、2个错误预期断言保留并复验。110原生页面/布局/局部实例、322控件，18逻辑页及全部事件映射，B09不渲染。早期中断记录保留，当前已继续完成；本文早期B3未授权为历史记录。BC01–BC07仍pending，真实前端/飞书未验，未合main或正式冻结，不改Phase1、不进入下一批次。
