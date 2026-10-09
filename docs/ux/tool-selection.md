# Penpot 本地工具选型与最小验证

日期：2026-10-09（Asia/Shanghai）。工作树分支 `codex/ux-penpot-toolchain`，基线 main `a0d521e`。结论：推荐 **Penpot 2.18.3 + 同发布系列官方 MCP 镜像 + Codex CLI**，保留原生文件导出 API 缺陷及浏览器连接限制，作为本机产品设计工具使用。没有部署 OpenPencil，没有开发自定义 MCP 或修改 Penpot 源码。完整 M1 设计与业务验收均未完成。

## 1. 文档、源码和运行证据分开

已读仓库 PRD、ROADMAP、ARCHITECTURE、DATA_MODEL、AGENT_DESIGN、FEISHU_INTEGRATION、STATUS。M1 为 MockCommerce 库存分析、真实飞书审批、内部工作项生命周期、Base 投影及最小 Web 轨迹；Woo 实测属于 M2，日报/RAG/受限动态只读工具属于 M3。该工具 MCP 仅服务开发设计，不进入业务 Agent 的工具白名单。

官方最新 release 为 [2.18.3](https://github.com/penpot/penpot/releases/tag/2.18.3)，发布于 2026-10-06。实测四个 Penpot 镜像均能在 arm64 拉取并运行，部署记录保存 RepoDigest，Compose 同时固定 tag 与 digest。npm 查询的 stable/latest 为 2.15.4、next 为 2.17.0；**不能把 npm stable 与 2.18.3 自动视为兼容**。采用 [2.18.3 官方 Compose](https://github.com/penpot/penpot/blob/2.18.3/docker/images/docker-compose.yaml) 对应的 frontend/backend/exporter/mcp 镜像，经实际文件读写验证。其 tag 中 MCP package.json 内部版本仍写 2.17.0，因此本报告分别记录镜像 bundle 版本与包版本，不声称每个内部包都为 2.18.3。

| 能力 | 官方依据 | 本轮实际结论 |
|---|---|---|
| 自部署与持久化 | [Docker 指南](https://help.penpot.app/technical-guide/getting-started/docker/) | 独立 6 服务、2 命名卷、独立网络；只映射 loopback |
| MCP 读写 | [MCP 指南](https://help.penpot.app/mcp/)、[固定版服务源码](https://github.com/penpot/penpot/tree/2.18.3/mcp) | CLI 的 high_level_overview/execute_code 读、写、回读通过；本会话另用官方 HTTP MCP 作设计探针 |
| Board、组件、Flex | [固定版 Plugin types](https://github.com/penpot/penpot/blob/2.18.3/plugins/libs/plugin-types/index.d.ts) | 2 界面+1 弹窗、2 Pages、1 组件主实例和实例；Flex dir/padding 回读通过 |
| 导航、弹窗 | [原型说明](https://help.penpot.app/user-guide/prototyping-testing/prototyping/)、[固定版 API 用例](https://github.com/penpot/penpot/blob/2.18.3/plugins/apps/plugin-api-test-suite/src/tests/interactions.test.ts) | 鼠标 A→B、返回、打开/关闭弹窗、背景关闭通过；连续 3 轮点击验证 |
| PNG 导出 | 官方 export_shape 工具 | 3 张 PNG 实测，中文视觉检查通过；Viewer 截图另保存 |
| 原生版本保存/恢复 | Plugin File.saveVersion/FileVersion.restore | 已执行快照恢复，持久化与重建证据见 acceptance |
| 原生归档导出 | File.export('penpot','all') | 实际失败 `No matching clause`；官方 UI 显示完成但未取得归档文件路径，不计便携归档导出通过 |

来源在调研时读取；网页的最新说明与固定 tag 内部分“multi-user 尚未集成”的旧 README 不完全一致。推荐来自固定版镜像的实际组合验证，不仅依赖网页描述。详细成功/失败结果见 [acceptance](acceptance.md) 和 evidence 中原始脱敏响应。

## 2. 本机部署与开销

运行目录在业务仓库和工作树之外，当前为 `/Users/aipuli/Documents/DesignTools/commerceops-penpot`。Compose 项目 `commerceops-ux-penpot`；PostgreSQL 数据库/用户 `penpot_design`；网络 `commerceops-ux-penpot_design`；卷 `commerceops-ux-penpot_design_postgres_v15`、`commerceops-ux-penpot_design_assets`。PostgreSQL 15.18、Valkey 8.1.6 随本分支固定，不复用业务 PG。没有公开注册、SMTP/邮件接收器或 admin-console；不用公网、隧道或生产 Compose。

只向主机暴露 `127.0.0.1:19001`。MCP 容器的内部监听地址 0.0.0.0 仅在独立 Docker 网络内；主机通过前端 `/mcp/stream` 访问。最终关闭 PREPL，临时管理员 bootstrap 过程不作为常驻接口。关闭遥测和 Google Fonts Provider 不等于完全断网；镜像拉取、Codex 模型调用仍需网络。Penpot/MCP 没有新增许可证费用，现有 Codex 账号的模型额度/费用不因此变成免费或离线。

环境检查：host 32 GiB、Docker VM 约 7.75 GiB/12 CPU，磁盘可用约 237 GiB；当时已有一个隔离飞书探针 PG 运行，未停止或改配置。6 服务显式内存上限总计 5.69 GiB，实际采样见 runtime-summary。官方[容量建议](https://help.penpot.app/technical-guide/getting-started/recommended-settings/)的 4 CPU/16 GB 面向大型实例，数据库 50–100 GB 为容量规划建议；它们不是单用户最低配置或本次消耗。本次短时验证不能推出长期容量、睡眠唤醒或长期稳定性。

## 3. OpenPencil 差距

只读检查最新 release [v0.15.1](https://github.com/open-pencil/open-pencil/releases/tag/v0.15.1)、[MCP 文档](https://openpencil.dev/programmable/mcp-server)、[兼容性矩阵](https://openpencil.dev/reference/figma-compatibility)与[路线图](https://openpencil.dev/development/roadmap)，没有本机运行证据。

| 项目 | Penpot 实测/文档 | OpenPencil 文档/源码结论 |
|---|---|---|
| 本地 MCP | 官方容器+原生浏览器插件；当前聚焦 Page | stdio/HTTP、本机 Unix socket/loopback，100+ 设计工具，显式 document/page ID |
| 保存与恢复 | PG/assets 持久化、原生版本快照；原生归档 API 有本次缺陷 | open_file/save_file 可读写 .fig，本地文件路径范围限制；未实际验证 round-trip |
| 组件/布局 | 已实测 | 文档列有组件、实例、Flex/Grid；未部署 |
| 画布/页面 | 两个界面 Board 平铺；组件另一个 Page | 多文档/多页面可查询、创建、切换，不等于可播放的跨界面原型 |
| 原型导航/弹窗/播放 | 同一 Page 的 Board 连接已点击验证 | 当前矩阵/路线图将 flows、hotspots、overlays、播放列为未实现/待办；保留 Figma 元数据不等于能播放 |
| 资源与许可 | 多容器，MPL-2.0 | README 声明 Tauri 客户端约 15 MB、MIT；安装包尺寸不能当运行内存 |

本需求最关键的跨界面导航及弹窗不能由 OpenPencil 的多 Page 保存能力替代，因此保留备选，不同步部署。Penpot 的业务“页面”以同一 Page 中的 Board 表示；不同原生 Page 自动互跳未实测，不作承诺。

## 4. 风险与最小替代

- MCP 在浏览器运行，聚焦 Page/标签页生命周期影响上下文；写前核对 file/page ID，只允许目标 POC 文件，不凭屏幕名称推断。休眠、关闭标签页、密钥过期需要重新连接。
- 默认 Nginx `$request` 会记录含 userToken 的 URL，本次检测到本地测试密钥落日志。已使用配置级 privacy.conf 禁止该设计前端访问/错误日志，重建容器，通过官方 API 撤销并替换密钥，重启 MCP 断开旧会话；只发布脱敏布尔核查结果。没有修改上游代码。Penpot 自身鉴权库和私有备份含账号/token 数据，不能上传。
- Codex CLI 项目配置的 `mcp list` 未显示新增服务器；用会话配置 wrapper 显式加载私有文件验证，未修改全局 config。早期 override 给键名额外加引号，生成无 transport 的条目并报 invalid transport；最终 wrapper 修复键语法，并只对用户已有带 transport 的配置作会话禁用。默认工具审批策略也曾阻止 smoke。仅给专用 Penpot 的四个设计工具配置已授权的执行范围，其他工具不因此获准。
- 文字/背景分为 sibling 时，背景交互不会覆盖文字命中区。本次已改为原生 Group 容器，并重测文字点击。后续按钮必须验证文字和留白区域，不能只查看连接线。
- File.export 原生归档 API 的失败不隐藏；PNG/截图和原生版本快照可用，私有 PG+assets 备份作为当前最小维护方式。便携文件 round-trip、异机灾难恢复未通过，不用自动生成 HTML 或另写 MCP 冒充。

阶段 C 再制作全部 M1 角色/异常屏幕；阶段 D 完整映射及代码测试合同随后冻结。本轮附结构化草案和 POC 双向映射，不宣称完整 M1 视觉基线就绪。
