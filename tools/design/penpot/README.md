# 独立本地 Penpot 维护

此目录只管理设计工具。不要把服务、网络、卷或 .env 合并到 CommerceOps 的业务部署。当前运行目录位于仓库之外；秘密和备份不进入 Git。

## 当前服务

- UI：`http://localhost:19001`，只绑定 `127.0.0.1`。
- 项目：`commerceops-ux-penpot`。`compose.yaml` 与 `privacy.conf` 必须一起复制到独立运行目录。
- 官方 MCP：UI 账号 → 集成 → MCP；打开目标文件后连接原生 MCP。只作用于当前聚焦 Page。
- 私有配置：运行目录 `private/penpot.env`、`private/login.json`、`private/mcp-url.txt`、`.codex/config.toml`，分别保存设计服务配置、设计专用账号和官方 MCP URL；目录 0700、文件 0600。不能回显或提交这些内容。
- 官方鉴权数据库与数据库备份含 MCP 账号/token 信息；这不属于业务数据库，也不可作为脱敏交付材料。

在独立运行目录执行：

```sh
docker compose --env-file private/penpot.env config --quiet
docker compose --env-file private/penpot.env up -d
docker compose --env-file private/penpot.env ps
docker compose --env-file private/penpot.env down
```

`down` 保留命名卷；不要加 `-v`，不要执行全局 prune。不要运行会把插值后的密码打印出来的普通 `compose config`，不要启用记录完整 URL 的代理日志。最终配置关闭注册、PREPL、遥测与 Google Fonts Provider。若创建全新实例，需要按官方管理指南临时启用受隔离 PREPL 创建专用用户，随后立即撤销该 flag 并重建 backend，避免保留管理过程的鉴权日志；现有实例不必重复 bootstrap。

环境文件须独立生成随机数据库密码和 master key，字段名为 `PENPOT_DESIGN_DB_PASSWORD` 与 `PENPOT_DESIGN_SECRET_KEY`。没有可复用的默认密码；不要覆盖已存在 env。升级前先私有备份，核对官方镜像版本与 digest，在本实例重跑设计/MCP/原型回归，不修改全局 Node、Docker 分配或 Codex 默认模型。

## Codex CLI

本分支的 `codex_cli.py` 只为一次进程加载私有配置，保留当前默认模型，不写全局配置：

```sh
python3 tools/design/penpot/codex_cli.py --runtime /absolute/path/to/isolated-design-runtime -- mcp list --json > /absolute/path/to/isolated-design-runtime/private/mcp-discovery.json
python3 tools/design/penpot/codex_cli.py --runtime /absolute/path/to/isolated-design-runtime -- exec --ephemeral --json -s read-only '只使用 penpot MCP，先读 high_level_overview，再读取当前 file/page ID。'
```

第一条的原始 JSON 含 MCP URL，只能通过 shell 重定向到运行目录的私有文件，不能直接运行后回显、粘贴到聊天、日志或 PR。第二条测试应只输出 file/page IDs 和安全结果；CLI exit 0 不等于工具调用成功，必须检查 `mcp_tool_call.status`、result/error 和回读值。wrapper 的已授权四工具为 high_level_overview、penpot_api_info、execute_code、export_shape；不开放业务工具、任意 UI 会话或服务器权限。

`mcp_probe.py` 是标准 HTTP MCP **客户端**，不是自定义 MCP 服务。它只允许上述专用 localhost URL，用于保存可核查的 tools/call 请求和响应。`create-poc.js` 针对本次 POC file ID 有保护；不能对别的文件自动重跑，更不能删除原界面后重建来“修复”不确定状态。重建 POC 前须另选测试文件并明确审核新 ID。

## 保存、备份、恢复

先确认 UI 已保存，回读元素、交互与 revision，再通过 `File.saveVersion` 固定原生快照。`FileVersion.restore` 会重载工作区并关闭插件，应重新连接并再次回读；恢复请求返回成功不等于恢复内容核对成功。

停写期间将 `pg_dump -Fc` 和 `/opt/data/assets` 打包到运行目录 `private/backups/`，同时保留私有 master key/env 与镜像版本。备份目录 0700、文件 0600，禁止上传。本次实际执行了快照恢复、私有备份和保卷停机重建；异机备份还原演练尚未完成，不能称灾难恢复通过。

原生归档 File.export 当前失败，响应见 [证据](../../../docs/ux/evidence/native-export-response.json)。官方 UI 下载可作为人工操作路径，但本次未取得可验证的归档文件；不要以 PNG 代替可编辑文件的恢复证据。短期保留原生版本/持久卷及私有备份，待上游版本或正式 UI round-trip 验证后再改维护合同。
