# V4-0 本地交付记录（验收进行中）

阶段：V4-0 / B 本地托管实施。当前不是阶段交付完成回执。
唯一业务起点为已核 M3；主控分支为 `codex/v4-control-20261103`。
四份合同及 V40-01/02 沿用已批准版本，原 A 文档中的 NOT_STARTED 为历史时点。

## 本阶段实现

- V40-03：新服务器 DemoSession、服务端真实 persona/角色/双店范围、30 分钟绝对到期、撤权/登出、Origin/CSRF、独立 cookie、原 request key 回执与 UNKNOWN 只读核对。
- V40-04：固定版本的双店联合种子、六类关联异常、严格 schema/窄 grant、租户内 reset 与 epoch/generation 旋转、事务中途失败回滚、跨租户不变。
- V40-05：`/v4`、`/v4/demo`、`/v4/settings/demo` 首次欢迎、双店摘要、切视角、二次确认重置与退出，移动导航、键盘/焦点/Esc、reduced-motion。

上述为本地实现范围。14 模块/66 页面/99 功能及六个后续场景入口仍是规划，不作为本阶段已开发功能。Harness 未合入；外部模型、embedding、Woo 写、飞书实际发送和生产发布未授权且未运行。

## 已有实际证据

| 验证 | 实际结果 | 精确回执 |
|---|---|---|
| 原生 SQL/schema | 6 通过，native/cleanup 0 | SCHEMA_SIX_461.json |
| 原生身份/权限组件 | 14 通过，native/cleanup 0 | IDENTITY_FOURTEEN_3606.json |
| 原生 seed 中途回滚/reset 原键 | 2 通过，native/cleanup 0 | ROLLBACK_TWO_1C35.json |
| 五连接真实数据库容量竞争 | 1 通过，三提交/两精确拒绝，native/cleanup 0 | DB_CAP_761.json |
| 前端 UI fixture | 35 通过，无 skip/flaky | UI_FIXTURE_363_FULL.json |
| 原生浏览器 200% 方法研究 | 已证实真实浏览器缩放，尚不代表真实站点整链通过 | NATIVE_ZOOM_METHOD.json |

组件证据各自绑定记录中的 source SHA/tree。以上 23 个原生组件检查与 UI fixture 不代签完整 PG、真实 HTTP/Web 或真实模型验收。所有已有失败、UNKNOWN、后续修复和清理回执保留，不拼接为单一通过结果。

## 尚缺的阶段 Gate

1. 独立真实 HTTP 的十一类场景与自然固定 30 分钟 TTL。
2. 同一新 owned API/PG/Web 的真实浏览器完整生命周期、1440/1280/390、原生 200%、键盘/焦点/Esc 和移动导航。
3. 冻结源码的完整工程检查、动态完整 PG 两线、G1 三/G2 六、实际完整并集/零交集及严格配对。
4. 旧 M3 对应 Web read/write/items 与 N01 回归。
5. 最终精确候选独审、文件清单、演示复现步骤、资源清理与阶段核收。

Hosted CI、amd64、真实模型/embedding、飞书/Woo 外写、生产：NOT_RUN。未经新授权不进入 V4-1。

## 运行与清理边界

所有真实验收只使用新 worktree、新 PG namespace、新生成配置与凭据，启动前固定 source、镜像 ID、端口、UTC 截止和清理预留。API 仅宿主 loopback，PG 无宿主端口。测试专用入口装配真实 create_app/P3/V4 栈；它不代表原生产入口或部署已经验收。

HTTP 启动试验中，导出文件名碰撞、旧入口 host 校验及 internal-only 网络发布失败分别有独立记录与修复。旧 case 不复用、不重放；新窗口使用新资源。已结束试验的容器/网络及宿主进程均核验关闭，相关新测试卷按回执保留。不得将尚未启动或已经关闭的端口列作可用演示链接。
