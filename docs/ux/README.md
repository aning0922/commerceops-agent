# 本地设计工具链交付索引

日期：2026-10-09（Asia/Shanghai）。本轮先交付阶段 A/B 的选型与最小验证，完整 M1 产品设计仍待阶段 C。这里的原型不代表业务功能、权限服务或 M1 Gate 已完成。

- [选型与限制](tool-selection.md)
- [实际验证与验收边界](acceptance.md)
- [提交前实际检查](validation.md)
- [产品交互原则草案](product-ux.md)
- [页面导航草案](sitemap.md)
- [页面与状态](screens.yaml)、[事件与动作](interactions.yaml)、[POC 设计值](design-tokens.json)
- [真实画布 ID 映射](evidence/design-map.json)、[实际点击事件](evidence/prototype-ui-events.json)
- [独立部署与维护](../../tools/design/penpot/README.md)

`POC-*` 是已制作的工具测试界面；`M1-*` 是尚未映射画布的产品设计清单。两者不得相互冒充。YAML 文件采用 YAML 1.2 兼容的 JSON 语法，目前可用标准 JSON 解析器检查。`contract_version=0.1.0-draft` 与 `visual_revision=ux-poc/0.1.1` 分别描述合同草案和测试画布，不表示 M1 基线获批。

本分支基于 main `a0d521e`，不修改 Phase 1 主控的 STATUS、G3、CI、业务数据库或真实飞书配置。该 commit 的 STATUS 仍包含较早的“PR #9 待合并”记录，而实际 Git 已含 PR #9 merge；本轮以产品文档为范围依据，不代替主控修订阶段事实。

![两个原生界面与弹窗在画布中平铺](evidence/poc-canvas.jpg)
