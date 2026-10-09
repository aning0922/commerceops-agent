# 工具与原型验收记录

日期：2026-10-09（Asia/Shanghai）。视觉测试版本 `ux-poc/0.1.1`，原生快照标签 `ux-poc/0.1.1 / verified prototype`。本轮结论为**本机核心能力验证通过，便携原生归档导出存在未解决缺口**；完整 M1 设计和业务验收未执行。

## 1. 实际运行结果

| 项目 | 结果 | 可核对证据 |
|---|---|---|
| 独立运行与 loopback | 通过 | [runtime-summary](evidence/runtime-summary.json)：6 服务，独立卷/网络，PG/Valkey healthy，无 OOM；前端只映射 127.0.0.1 |
| Codex CLI 读/写/回读 | 通过 | [初次成功 CLI](evidence/cli-smoke3.jsonl)；最终 wrapper/新密钥 CLI 的独立复验见 [cli-final2](evidence/cli-final2.jsonl)，检查 completed MCP 调用及实际回读，不仅看 exit code |
| 查询 Pages / 创建 Board | 通过 | [初次读](evidence/initial-read.json)、[创建请求](evidence/create-poc-request.json)、[创建响应](evidence/create-poc-response.json)；2 Pages、2 界面和 1 弹窗 |
| 创建组件 / Flex 布局 | 通过 | [design-map](evidence/design-map.json)：1 组件主实例，实例、row Flex 和 16/10 padding 可回读 |
| 原型添加 / 实际点击 | 通过 | [10 个实际动作](evidence/prototype-ui-events.json)：3 轮文字点击开/关弹窗，背景关闭、返回与再次导航；来源为真实 Viewer AX 状态 |
| 截图与 PNG 导出 | 通过 | [平铺画布](evidence/poc-canvas.jpg)、[A](evidence/prototype-a.jpg)、[B](evidence/prototype-b.jpg)、[弹窗](evidence/prototype-overlay.jpg)，另有 [MCP PNG](evidence/poc-s02.png)；实际中文视觉核对 |
| 原生版本保存与恢复 | 通过 | [保存版本](evidence/save-version-response.json)、[临时修改](evidence/restore-probe-modification.json)、[恢复请求](evidence/restore-version-response.json)、[恢复回读](evidence/restored-read.json)：purpose 从临时标记恢复为 tool-verification-only，revision 保持 0.1.1 |
| 停机重建后保存恢复 | 通过 | 对专用 Compose 执行 down（不带 -v）/up；[MCP 重建后回读](evidence/after-restart-read.json)中原 file/page/control IDs 和动作保留；[4 次原型点击复验](evidence/prototype-after-restart.json)通过 |
| 私有备份 | 已制作 | PG dump 225296 bytes、assets tar 699459 bytes；文件未提交，大小记录在 runtime-summary。**未执行异机/新卷备份还原** |
| 原生 .penpot API 归档 | 失败 | [原始响应](evidence/native-export-response.json)：`Tool execution failed: Error: Error handling task: No matching clause:`；保留原始失败，不自改上游 |
| 官方 UI 原生下载 | 受限证据 | [UI 状态](evidence/native-download-ui.jpg)显示完成标记，但未取得可核查归档路径，download event 等待超时；不计便携归档/导入 round-trip 通过 |
| 日志密钥修复 | 通过当前采样 | [事故](evidence/log-secret-incident.json)、[修复](evidence/log-secret-repair.json)；前端隐私配置、密钥替换、MCP 会话重启；runtime-summary 对旧/新 key、服务 master key、DB 密码及登录密码作值匹配，当前容器日志均未命中 |

原生版本恢复和命名卷重启恢复已实测；它们不替代灾难恢复演练。短时原型成功不代表长期稳定性、浏览器休眠恢复、跨原生 Page 自动跳转、多人协作或全部 Plugin API 已通过。当前四个业务外设计工具可用，MCP 为官方 Beta 集成，保留上述限制后采用。

## 2. 已修复或保留的失败

1. 初次 CLI 配置 override 使用带额外引号的 dotted key，产生 invalid transport；修复为实际 CLI 接受的键名，并使用私有配置 wrapper。项目自动配置发现没有作为最终成功路径。
2. 一次 CLI 进程 exit 0，但工具因审批策略 never 被拒绝；[原始 CLI](evidence/cli-smoke2.jsonl)保留。专用 Penpot 设计工具获本任务授权，按服务器限定为四工具后 [重测](evidence/cli-smoke3.jsonl)成功；不会因此授予业务工具权限。
3. 初版按钮背景是 rectangle、文字是 sibling；点击文字无响应，点击留白能开弹窗。[失败截图](evidence/failure-label-hit-area.jpg)、[修复请求](evidence/repair-hit-area-request.json)、[修复响应](evidence/repair-hit-area-response.json)保留。改为共同 Group 容器后文字和背景行为一致，重复测试通过。
4. 官方前端访问日志包含 query userToken。只在隔离本地设计实例发生，未上传。部署配置先禁止访问/错误 URL 日志，重建前端、替换本地测试 key、重启 MCP 断旧会话，再执行值匹配检查；原始含密钥日志不交付。
5. 原生 File.export 失败仍保留；官方 UI download event 没有提供可核查文件。当前最小替代为原生版本快照、持久卷、私有 PG+assets 备份及 MCP PNG，不声称静态图可以恢复可编辑文件。

## 3. 阶段 C/D 后续必须补齐

下列原型/业务项保持pending，不能用POC勾选。C1文档覆盖见 [C1检查](c1-validation.md)，不替代原型验收：

- [x] C1已完成 [Prediko Pia、Sidekick、Moby官方研究](c1-research.md)，只借鉴M1相关模式；没有竞品账户实操证据。
- [ ] 任务、报告、审批/内部补货、轨迹、飞书卡片及登录/权限/加载/空结果/失败/过期完整画布。
- [ ] operator、approver、admin、无权限身份的全部旅程；admin 不自动获得审批权。
- [ ] 未知在途逐项披露、绑定 version/hash/完整确认键的专用确认和拒绝；硬质量错误不可确认豁免。
- [ ] 重复、并发冲突、已记录决定、过期、计划变化、权限撤销、执行复核、同步失败及 unknown 对账的交互。
- [ ] 完成/关闭一个 open 内部工作项，原因必填、expected_version/request_key、终态不重开，无库存/采购写入。
- [ ] 键盘、焦点、读屏、文字/留白命中区、窄屏飞书卡片；本轮只验鼠标交互。
- [ ] 全部 M1 screen/control/event ↔ Penpot UUID 映射；native tokens/bindings 与设计版本冻结。
- [ ] 后续 Next.js 的路由/组件/测试映射及 Playwright 状态/角色/异常验证；真实业务 T3/T4/T6 与飞书测试另附证据。
- [ ] 便携原生归档导出/导入 round-trip，以及异机/新卷 PG+assets 备份恢复。

`screens.yaml / interactions.yaml`现为C1待评审规格，`design-tokens.json`仍是原POC设计值。原生导出/异机恢复缺口本轮只记录，不扩大基础设施工作。审阅、PR 创建或 main 合并都不自动升级为 M1 产品基线或业务 Gate。

## 4. C1外部评审修订说明

原C1有条件通过；本次仅修订设计规范。已接受决定和pending后端合同见 [决策记录](c1-decisions.md)，C2按 [批次](c2-batches.md) 复用组件并优先闭环；第一批就验Web窄屏/飞书全部SKU和风险披露，不能延后批准安全边界。原生导出/异机恢复缺口继续保留，最低维护方案见决策记录§4，本轮未执行新的备份或恢复。
