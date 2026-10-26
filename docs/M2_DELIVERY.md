# M2 交付与证据地图

本文件属于 [Issue49](https://github.com/aning0922/commerceops-agent/issues/49) 的 M2 持续交付。来源展示从已审 `5ac0c2f` 接续；创建与 N01 只消费已审 `3af5308f69dd54cada81b30c8e7e002c2ef5cc51` 的公开合同，保持既有 18 页风格，不增加视觉批次。阶段正式验收、main 与合后 CI 由 Root 按实际回执登记；此页不是结案证明。

## 当前可展示的事实

真实会话和传输方式与业务数据来源分别展示。报告来源只读取当前冻结报告的 `facts.source.provenance.source_kind`：`mock` 显示“Mock 样本”，`woocommerce_test` 显示“Woo 测试店（只读）”，没有当前报告或无法识别时显示“未报告”。登录、`local_http`、Worker 配置、P2 原始报告/P3 重观测均不能代替商业来源。

现有报告完整性与来源采集完整性继续分别展示；采集读齐不表示库存或在途已知，也不授执行权。SKU 保留原始未知库存、零/负库存、`inbound_units=null`、估算有效值、质量标志、硬阻断和当前版本假设集合。共享池需人工核对，不能按变体重复分配。页面不计算权威建议，不将原始在途改写为已知零。

离线 Mock 页面及注入合同响应仍明确标注没有真实身份/API/PG/Woo。展示层合成 DTO 中的 Woo 来源标签只验证页面消费合同，不算真实 Woo API 或业务接线证据。

## 范围与待完成项

| 项目 | 本批范围 / 状态 | 后续验收依据 |
| --- | --- | --- |
| 来源与质量展示 | 本批最小展示接线；测试结果见冻结提交交接，不把作者自检当独审 | 严格 DTO、页面回归及精确源码独审 |
| 创建与 N01 | Woo/Mock 按当前所选店铺 capability 分支；B 离线契约与组件已接，真实业务联测仍 pending | 精确源码独审、稳定后端及同源 API/PG/Woo 业务链 |
| Woo 对账 | 沿用独立 [实验环境](WOO_LOCAL_LAB.md) 与 [A/B 输入合同](contracts/p5-woo-readonly-v1.md)；实际 adapter probe 由 A/Root 单独核收 | 同源真实只读 API、独立 EXPECTED、完整性与质量结果 |
| 备份还原后待审批续跑 | pending，本批未执行，核心入口由 A 负责 | [恢复交付合同](M2_BACKUP_RESTORE.md)、新自有源库和新目标库的实际证据 |
| AC01–11 汇总 | pending Root 按影响复用已验 M1 并补 M2 缺项 | 不用页面 Mock 或旧 CI 抵扣新业务/恢复证据 |
| M2 独审、精确 CI、main、合后 CI | pending | Root 的实际结案回执；不自动进入 M3 |

## 文件所有权与运行边界

B 负责现有 Web 来源/质量披露、对应契约与页面测试、本文件及恢复说明。A 负责业务来源选择、collector/Worker/Graph 接线、公开 schema 源、权限与恢复核心、根 Compose/装配、锁和 CI；B 只消费已提交且已审的稳定合同。Woo 必须有当前所选 operator 店铺的合法、已启用 capability 和来源版本；缺失、禁用或不一致均关闭创建，不回退 Mock。只有所选店铺明确返回 Mock 时保留旧流。

验证页面可使用无服务端口的 headless 组件样例，结果只能标展示层合成测试。真正 API/Web/PG 联测等待 A 稳定入口后，由 Root 串行登记新自有资源、绝对截止和清理；不读取或复用旧 P4、QuizForge、Penpot 的私配或卷。

## 最小演示与证据包

演示只需串起：来源报告与完整质量披露、真实 Woo 对账回执、还原前待审批记录、还原后同一绑定、一次明确续跑及原键重放。记录 task/plan/version/hash/checkpoint 绑定、角色/期限/新鲜度复核、内部执行唯一性、原生退出和资源清理。原 M1 已核场景按影响复用，无需为本展示接线重录全部流程。

公开材料只含脱敏结果、准确证据类型、源码与工具版本、命令/退出码和摘要。凭据、cookie、dump、原响应与私有运行配置不入 Git；自动化截图不称真人连续操作，未执行处保持 pending。当前功能展示不代表生产、真实采购/入库或 Woo 写权限。

## Woo 创建与 N01 消费合同

客户端分别读取 `/api/v1/config?shop_id=...`；会话级 Mock 配置不代替所选店铺的来源。Woo 请求只包含 `source_mode=woocommerce_test`、`source_config_version`、L/R/S，不能加入 Mock fixture、时间、URL 或私有 binding。页面只是创建资格提示，服务端在每次写入重新核权限、当前版本及可信来源。

Woo N01 消费 `p5-n01-web-v1`；旧 Mock 仍消费 `p4-n01-web-v1`，外层均为 `p3-web-v1`。候选必须绑定所选店铺、来源版本及原始 Unicode code-point span。缺项保持空白，人工补参保留原始澄清记录，不能把示例改称服务端 ready。用户依次检查原句、明确确认完整参数，再准备和显式提交原请求；预检查不创建任务、不采集报告、不调用模型。来源重读或输入改变使尚未准备的确认失效，迟到结果不能复活旧确认。

一旦准备原请求，原 key 和字节保持不变。来源刷新、pending 和 UNKNOWN 都不重挂提交组件、不换键、不自动登录或重发。UNKNOWN 先读取原键回执；暂无回执不证明失败。`from_report` 继续使用原 task/report/snapshot/facts_hash 引用，不引入当前 Woo 参数。

生成器按 P3 → P4 N01 → P5 的顺序消费 `docs/contracts` 中公开冻结合同，同名定义由后者覆盖，得到 22 paths / 94 schemas / 23 operations / 零悬空引用。原 P3/P4 生成文件保持不变；P5 生成结果独立保存，生产解码仍拒绝 extra、coercion 和默认填充。复现命令：

```sh
node frontend/tooling/sync-p5-schema.mjs --openapi
npm exec --yes --package openapi-typescript@7.13.0 --package typescript@5.9.3 -- openapi-typescript .audit/p5-openapi.generated.json --immutable -o frontend/lib/p5-types.generated.ts
npm --prefix frontend run check:read-schema
npm --prefix frontend run typecheck
```

沿用既有临时类型生成器版本，未新增前端依赖或修改 lock；临时生成器没有单独 transitive lock，不将其称为生产锁保障。Node/npm 使用仓库要求的 24.21.0/11.19.0。生成类型可输出到 ignored `.audit` 后逐字节比较。

离线检查可运行：

```sh
frontend/node_modules/.bin/playwright test --config frontend/playwright.contract.config.ts --reporter=list
frontend/node_modules/.bin/playwright test --config tests/e2e/web/phase5/creation-playwright.config.ts
frontend/node_modules/.bin/playwright test --config tests/e2e/web/phase5/playwright.config.ts
npm --prefix frontend run build
```

新增创建组件用 `about:blank` 和内存 transport，测试夹具显式注入合成 UUID；它没有实际会话、API、PG、Woo 或模型。390px/键盘结果仅代表自动化组件证据，不能替代真人验收。开发失败、修正及最终原生退出分别保留在 ignored 私有运行目录，最终交接按精确冻结提交登记。当前后端截止类修复及独审仍由 A/Root 处理，B 本批没有启动正式业务联测。
