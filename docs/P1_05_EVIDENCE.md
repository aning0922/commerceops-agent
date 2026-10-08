# P1-05 飞书技术探针离线交付证据

更新：2026-10-08（Asia/Shanghai）。完整离线实现与本地检查已完成，待精确提交 CI、独立审核与主控核对；真实 G3 **blocked_external**，Issue #6 保持 OPEN，不记 Phase 1 全 Gate 或 main 完成。[配置与复现](P1_05_SETUP.md) · [Issue #6](https://github.com/aning0922/commerceops-agent/issues/6)

## 1. 基线与修改范围

执行会话 `01a11b89-ef8f-7160-93ae-2faef97647be`，Worktree `/Users/aipuli/.codex/worktrees/4094/commerceops-agent`，分支 `codex/phase1-05-feishu`，PR 目标 `phase/1-integration`。

初始 P1-01 基线 a0d521e，纯合同中间提交09dcd122（94offline，其中52新增），随后按主控交接普通 merge 精确集成基线 `662fb575c377b174135bcf4755ba6d866dfe6cbb`。该基线 [push run37782046504](https://github.com/aning0922/commerceops-agent/actions/runs/37782046504) SUCCESS、G1verified_on_integration；不用这条 CI 代替本 PR head 检查。

本次只增加 Feishu adapters/技术入口/专用 probe schema与tests/两份P105文档，并按主控唯一锁责任加入SDK依赖。没有改正式 migration、共享DatabaseSettings/授权入口、Worker/runner、PGsmoke、workflow、STATUS/AGENTS/ROADMAP或DEVELOPMENT。不创建正式审批/补货/库存/Graph job，不调用模型，不发布应用、不扩scope或启公网隧道。

## 2. 已执行的证据层次

| 层次 | 实际执行与界限 |
|---|---|
| 官方文档/发布包源码 | 读取官方消息/新版callback/JSON2.0/Base与bot info正文；发布wheel静态核查与版本hash，见配置页 |
| 官方 SDK 离线 | lark-oapi1.7.3真实类型、dispatcher、WS protobuf响应编码和HTTP请求构造执行；网络由替身截获，没有连接飞书 |
| 真实 PG 技术 | 真实PG17.11，现有commerceops_app/app_password连接，技术schema、身份FK/角色/锁/事务/持久幂等实际执行 |
| 飞书真实平台 | 未运行，专用组织应用/身份/群/Base/凭据与资源授权未准备，G3blocked_external |

模式分别标识：合成字段/SDK使用 source_mode=offline_synthetic、model_mode=not_used、approval_mode=simulated_probe；PG技术样例为 source_mode=postgres_technical（外部transport仍offline_stub）、model_mode=not_used、approval_mode=simulated_probe。原P1-02持久恢复为approval_mode=not_applicable。技术结果不表示正式T3/A01–A08/AC10验收。

## 3. 本地最终检查

环境：macOS arm64；uv0.11.25、CPython3.12.13；项目固定Node24.21.0/Gitleaks8.30.1已SHA256校验。Docker daemon29.6.2、Compose5.3.1；实际PG为17.11 Debian/aarch64，镜像digest沿用已验证基线 `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826`。

`uv run --frozen --no-sync python -m scripts.check` 退出0，2026-10-08 21:57前完成：

- dir/index/完整可达history扫描0；提交前暂存新增内容后仍须复验扫描。
- 依赖锁一致；21 Markdown，0错误；ruff lint通过，66 Python文件格式一致；mypy45文件通过。
- **112 offline passed / 43.55秒**，39integration按marker deselected，无skipped；70项为本任务（52纯合同、10SDK、8配置入口），其余42底座。
- 固定Node工具链与TypeScript通过；npm已知漏洞0；Python87锁包已知漏洞0，无skip。

`uv run --frozen --no-sync python -m scripts.pg_smoke` 退出0，2026-10-08 **21:51:46–21:52:48**（Asia/Shanghai）：

- **39真实PG integration passed / 6.30秒**，112offline按marker deselected，无skipped；其中26项为P105，13项为原P102。
- 技术接收提交后另一连接可回读；消息event/message去重及新event alias持久化，内容冲突拒绝；同一卡片不同callback保留各次技术结果，不误填message唯一列。
- 身份enabled/roles/app/tenant/组织/店铺、目标卡片、计划ID/version/hash、nonce hash、完整确认键及期限校验；首次决定、相同决定重复、A/B相反动作与并发冲突通过。
- 真正延迟FK导致COMMIT失败时，决定和接收整次回滚；SDK不会取得成功receipt。WS编码离线验证DB异常返回500、无成功Toast。
- 预建PG池实际checkout和transaction_timeout配置验证；受控正常callback和真实锁超时失败样本均满足<3秒断言。没有真实客户端响应延迟样本，也不声称p95<1秒性能验收通过。
- SDK卡片发送前通过另一PG连接可见inflight与持久UUID；实际SDK请求含该UUID，成功绑定message_id后新版callback可记录；超时unknown不重发。
- Base UUIDv4 token/ProbeID/hash持久化，1254291明确拒绝后显式原token重试，同表跨连接串行；HTTP/code双重成功要求、1255006不换key、unknown停止、分页唯一/重复/异常、更新未知需匹配pending_fields/hash通过。
- 既有空库/重复migration/setup/grant、原G1权限/约束/失败恢复、PG重启/保留卷重建/停库非零失败/恢复回读全部通过。稳定原G1 task/thread `61e6bb7d-d6ea-4627-9a86-1e9dd4f86817`，回读inbox/jobs/audit=1和官方checkpoint一致。
- 自建随机项目p102-c9f8e40366ef，cleanup_exit=0，项目/自有卷/镜像/临时秘密文件清理成功，不使用prune。

第一轮33 integration和第二轮36 integration也通过；最终新增锁预算/分页异常/目标变化覆盖后以上39项通过。SDK离线早期测试曾暴露帧required字段、queries列表/字符串差异，已按实际锁定SDK构造修正；没有改SDK源码。上述本地PG命令运行时尚未最终提交；最后仅完善拒绝分类Toast/固定日志及文档，绑定精确提交的完整CI结果以PR/Issue记录为准。

## 4. 依赖、日志与敏感检查

固定lark-oapi1.7.3，wheel SHA256 `c91f00087b7977dc9059ab492e8fe435e1a873863dca1d4e660d2be5b801e4cd`。其websockets>=11,<16合同使既有锁由17.2降为15.0.1；新增pycryptodome3.24.0/SDK等固定锁项，HTTPX0.28.1保持；PG/基础回归已实跑，后续模型websocket行为未验证。

官方SDK缺py.typed，仅在SDK导入边界使用import-untyped注释，项目代码保持strict mypy；实际类型/字段/编码由执行测试补充。Python3.12执行时有两条SDK自身DeprecationWarning（utcfromtimestamp与导入时get_event_loop），未屏蔽或修改SDK，不将其说成运行失败或真机成功。

SDK会输出payload/INFO连接URL/异常原文，本项目禁用相应SDK/传输/PG池原始logger及传播；canary证明无这些输出。应用仅输出固定拒绝分类，不输出payload/身份IDs/nonce/token/连接URL。技术状态可从PG安全回读；失去SDK原文日志是明确诊断限制。未知身份/合同拒绝不写接受记录，固定分类日志与error Toast可解释；合法重复/冲突在技术接收表留痕。

曾出现generic-api-key对错误码字符串、合成文件路径、pytest类型注释和导入符号组合的误报，已核对为代码/虚构值后改短分类/别名；未改扫描器、豁免或忽略策略，未上传真实秘密。未将只删除当前文件当历史清理；最终提交前检查待提交内容及全部可达历史。

## 5. 未验证与门禁

真实私聊/群@/机器人过滤、飞书应用配置生效、JSON2.0真机confirm/reject往返、真实operator/Toast/延迟、断线投递、实际Base最小权限/创建读回更新/原token重投、幂等长期期限仍未执行。所有真实项blocked_external，不以离线/PG/CI或代码合入推导G3。

本实现只有隔离technical schema；部署owner是高权限角色，runtime无新增DDL/DELETE权限，但不声称生产RLS/DBA隔离完成。没有生产outbox/审批服务/完整备份恢复/正式Graph恢复合同。SDK静态与离线EVENT帧行为不能替代真实wire方式确认；若长连接失败先核对配置/发布，不能自行开HTTP或隧道。

不关闭Issue、不自行合并/APPROVE；最终离线PR须精确SHA CI、独立审核与主控核对。main与Phase1完整验收仍依赖真实G3和其他Gate。
