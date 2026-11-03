# V4 新 owned 单场景 driver 准备

本切片普通合入精确backend `d57808f0627821ab202e054e7d464fa2d4b9798c`
（其tree `0bb6bf997c0b5c37abd3381246d361211974b8ff`），按IDENTITY_SQL_PLAN§14实际
字段接线。提交时后端独审/后续Root集成以Root回执为准；合入不签运行准入。Root后续通知
534844a/38ASGI及461 PG事实不转记为QA执行，也未自行读作者WIP或启动资源。

## 命令及冻结输入

Root先将本提交、最新已审backend与WEB普通集成，在干净精确source/tree上构建本批test
镜像并绑定image ID；PG镜像必须是Root本批核定PG17.11/pgvector0.8.7新owned镜像，
不读取旧M3 `.audit` receipt。本driver不build/pull、不变更共享Dockerfile/compose。
宿主已有本批锁定Node24.21/npm11.19、frontend锁定依赖与Ajv；backend test镜像不需要Node。

Root填写新私有manifest（没有秘密值；以下占位不能直接执行）：

```json
{
  "project": "v4qa_REPLACE_NEW_CASE_ID",
  "database": "v4_demo_REPLACE_NEW_CASE_ID",
  "directory": "/REPLACE_ROOT_NEW_CANONICAL_PRIVATE_DIRECTORY",
  "source_sha": "REPLACE_40_HEX_INTEGRATED_HEAD",
  "source_tree": "REPLACE_40_HEX_INTEGRATED_TREE",
  "pg_image": "sha256:REPLACE_64_HEX_LOCAL_IMAGE_ID",
  "test_image": "sha256:REPLACE_64_HEX_LOCAL_IMAGE_ID",
  "api_port": 18440,
  "web_port": 13440,
  "starts_at": "REPLACE_ROOT_UTC",
  "deadline": "REPLACE_ROOT_UTC",
  "scenario": "lifecycle",
  "migration_sha256": "REPLACE_ACTUAL_REVIEWED_0024_BYTES_SHA256",
  "uid": 501
}
```

project/database后缀必须小写；UID填执行prepare的本机owner UID，不沿用示例501。
directory的parent须已存在、路径canonical且无空格/compose env特殊字符；目标必须不存在。
建议Root新建本树忽略的`.audit`下唯一子目录（不读旧目录）；input manifest也应在忽略的
本批新目录内，不能因untracked文件破坏clean-source核验。代码只检查指定路径，不扫描历史。

```sh
.venv/bin/python -m tests.e2e.v4.owned_driver prepare --case /ROOT_NEW_PRIVATE/input.json
# 只有独审核收与Root具体project/port/UTC开窗后才运行下一条：
.venv/bin/python -m tests.e2e.v4.owned_driver execute \
  --case /ROOT_NEW_PRIVATE_CASE/case.json --root-opened-window
```

prepare只在独占新700目录生成本批owner/app/CSRF/nonce新随机值及600配置；不访问服务。
再次prepare拒绝覆盖。执行前核HEAD/tree/0024指纹、clean、明确UTC与180s cleanup reserve，
单case≤1800s；execution.once独占创建，失败仍消耗该case，不复活旧窗。
Root必须另有绝对截止的外层project清理安排：内层watchdog封顶宿主子进程组，不能把杀
compose CLI等同容器已停。driver中途被外部SIGKILL时由Root按登记project清理，不能假造
finally已执行。标志仅表达Root开窗意图，不是独立的权限认证或预算授权。

## 实际拓扑与命令顺序

固定使用根compose.yml + compose.m3.yml + QA独占owned.compose.yml（JSON兼容YAML）。
Root只提供显式本地image ID及本case env-file；不改根文件、不加载旧.env。Docker客户端
只取本机正常context所需HOME与固定PATH，不向子进程继承owner DB/provider环境。

- PG不发布宿主端口；默认网络internal。起PG等待healthy，失败不自动再起。
- 使用pg-test/test镜像owner one-off依次执行受限migration诊断、原setup-checkpointer、
  原grant-runtime、V4 init-fixture/grant-runtime/verify-fixture；所有库名均v4_demo_。
  migration即使非0也先保留migration.safe.json及native exit，不丢SQLSTATE再报错。
- API在同project namespace的test镜像内前台运行，容器可绑定0.0.0.0，宿主映射仅
  127.0.0.1。COMMERCEOPS_PORT采用Root登记API端口；新P3+V4配置均装配。API只挂runtime
  子目录，不挂owner目录/secrets，不设置或继承COMMERCEOPS_DB_* owner环境。
  配置600文件与运行UID相同；Root须在实际Linux/挂载机制核可读性，不放宽为世界可读。
- WEB用宿主锁定Node前台运行next dev，127.0.0.1，服务端COMMERCEOPS_API_ORIGIN直连
  实际API；关闭Next telemetry。API/Web端口先做占用拒绝，readiness还要求自启进程存活，
  不以已存在的其他监听者200冒充本case服务。
- probe在supervisor管理的宿主子进程运行，真实httpx/CookieJar；strict响应仍由宿主
  锁定Ajv校验baseline。PG事实经本project内具名临时pg-test observer运行真实psycopg，
  不发布PG端口，不让API获得owner连接。observer不是业务Worker/Graph任务。
- case结束先停宿主writers，再显式停止API容器及可能遗留owner one-off；之后PG仍在线时
  采完整新tenant inventory及只读最终snapshot，再down该project并核容器/网络已空。
  不加--volumes，记录实际保留卷名。Root须登记每个case卷并按后续授权处理，不能为
  下一case清空/复用。原生退出、超时UNKNOWN、watchdog/采集/cleanup失败都不能签成功。

pg-test observer只读事实与显式负例夹具写入分支分开：credential-revoke/grant-revoke
只在Root新库、指定tenant映射的principal/shop内撤销一个既存对象，带SQL/锁超时，
不接任意SQL/表名、不新增权限、不恢复grant、不读取秘密列；final阶段禁止这些写分支。

## 分窗：每行一个独立新project/DB/API配置与UTC

| scenario | 当前代码入口与判据 | 运行状态 |
|---|---|---|
| lifecycle | A/B互读404、双店、reset B不变、persona、logout | NOT_RUN |
| capacity | 空库3提交/2精确CAPACITY_LIMIT拒绝、PG/原session核对；只签串行 | NOT_RUN |
| ack_body | 创建真实响应body丢弃后原cookie/current/key/PG恢复 | NOT_RUN |
| ack_headers | 还原原bootstrap jar，最小原key恢复；旧空间仍占cap | NOT_RUN |
| security | Origin/CSRF/strict字段/改cookie旧API401 | NOT_RUN |
| same_key_reset | 200+CSRF_INVALID或相同200；当前CSRF重放、PG恰一次effect/event | NOT_RUN |
| persona_stale | generation推进、旧CSRF403、当前CSRF+旧generation409 | NOT_RUN |
| bootstrap_restart | Q18：3active占满，确定性429→用户显式GET新owner/newkey，旧owner/key不可变、原key UNKNOWN、无新增tenant | NOT_RUN |
| identity_scopes | approver恰一店、另一店404；restricted_admin无店，reset保留无grant角色 | NOT_RUN |
| credential_revoke | 新owned撤当前credential，current及旧CSRF reset均401 | NOT_RUN |
| grant_revoke | 两店operator撤一店grant，PG另一grant仍enabled；旧P3触发器推进auth_version，旧bound对两店均401 | NOT_RUN |

grant撤销后的旧session失效是实际既有P3规则；不为“另一店还能读”的UI描述放宽auth_version。
初始approver单店范围由identity_scopes单独验证。Q18 HTTP只模拟明确用户意图；UI UNKNOWN
不自动bootstrap、跨标签late context、1440/1280/390/200%、focus/Esc/reduced-motion仍由
WEB owner在同源已审浏览器用例验证，driver仅启动Web，不自动签browser Gate。
旧bound WebActor的进程内复用、完整identity映射篡改与目标persona credential专项仍须
Root独立PG矩阵；本HTTP fixture不冒充这些未运行证明。原旧M3动态完整PG/G1G2/Web/N01/
scripts.check仍由Root统一安排，不用11个场景替代。

## 自然TTL专项计划（未开放）

当前driver拒绝超过30分钟case，故不能签真实30分钟TTL。若Root决定自然到期核验，建议
单独登记45分钟窗口：启动/创建≤5分钟，记录DB expires_at；创建后完整等待30分钟并取
边界前/后真实GET/receipt拒绝；最后≥180秒cleanup。只有原deadline事实才可签到期，
不改expires_at、不用短TTL夹具冒签；需要单独已审专项入口与Root窗口，不能偷偷放宽本driver。

## 本切片纯验证

`pytest -q tests/e2e/v4/test_owned_driver.py`：13pass/0.08s/native0，验证新目录/0600、
配置隔离、不可重用、非owned输入拒绝、overlay没有PG端口/API owner环境、非0诊断保留、
execute缺Root flag拒绝。没有启动Docker/PG/API/Web或创建实际case runtime。
首轮类型检查缺yaml stubs/ROOT再导出已修：overlay改用JSON兼容YAML，仅标准库解析，未改锁。
Ruff通过；Mypy覆盖本切片5个Python文件。不重复其它未变QA测试，当前所有运行Gate均NOT_RUN。
本次运行前必须再对Root最终已审统一源码检查adapter SQL/配置一致性；actual token/cost UNKNOWN。

## ce51 五项P2整改（与后续TTL/browser新增模式分开）

已读正式报告 `0bd86545da67ebc0d664d9b9ac8cae5a143953f4`：
`docs/v4/review/OWNED_DRIVER_ce51.md`，0P1/5P2，未签execute准入。
DRV01：API attached up限定--no-deps，仅选v4-api，并用--exit-code-from v4-api传播退出；
PG先独立healthy，不纳入API writer停止集合；仍须实际窗口证明PG存活至final facts。
DRV02：Q18原bootstrap/key读回接受200，精确核data.UNKNOWN/WAIT_READ_ONLY及原key；
不把外层OK或正确原键当404，错key路径仍另记。DRV03：Web显式传local_http transport。
DRV04：每个observer启动前定名，finally以600文件记录action/container/native_exit或null、
TIMEOUT_UNKNOWN/INVALID_FACT_JSON/NONZERO_UNKNOWN及有限safe_status；先落盘再抛，
不留stderr或任意payload。父receipt引用本case observers目录，已见137不被统一unknown覆盖。
DRV05：所有服务之前只读inspect两个精确本地image ID；缺失即停，不build/pull补齐。
本机`docker compose run --help`实际没有--no-build；故展开原三文件后生成本case独占
no-build.compose.json，移除所有build映射/未用db-init服务，保留三个精确image并固定
pull_policy=never，附内容hash核对。后续所有owner/observer都用冻结模型且显式--pull never，
而非传不受支持的参数；启动up仍带--no-build。没有修改原compose/Dockerfile。
定向纯回归15pass/0.09s/native0，含missing-image、原生137/timeout/坏JSON记录不丢、
Q18 minimal owner绑定、Web环境、API依赖范围、冻结模型无build。没有启动服务或跑任何case。

## natural_ttl 独立新增模式（窗口未开放）

仅此scenario允许≤2700s，其他仍≤1800s，reserve180不变。沿用同driver/manifest，
独立project/DB/API；不启动或绑定Web，web_port仅保留manifest兼容字段。
ttl_probe.py不改变业务期限。初始以PG tenant/session created/expires和API expiry核恰30分钟，
并拒绝已撤销/不同期限；工作截止须≥expiry+60秒，另留180秒cleanup，否则UNKNOWN/非0。
静置只在probe内monotonic分段等待，无业务轮询；Root可用独立资源做Full串行PG。
到期前30秒取PG+有效current；之后核DB确已跨expiry、原期限/撤销事实未变，再核current、
旧两店及原控制回执401。边界丢失/中断/传输错误留UNKNOWN，不续窗；600独占证据文件
natural_ttl.safe.json保留部分事实。13项定向纯测试0.08s/native0，无真实等待；实际SQL/
HTTP/30分钟自然行为NOT_RUN，需Root专项新对象/端口/UTC，不以此签Full。

## browser_lifecycle 独立新增模式（窗口未开放）

仅执行WEB交付a2a7873ca7453fc2c86ffdc1b8cd57063b66f5b3的固定
frontend/playwright.v4-live.config.ts与frontend/v4-tests/lifecycle.live.spec.ts，标题固定
`LIVE: isolated demo lifecycle and browser layout`。两个Git blob及工作文件bytes必须一致，
且在当前HEAD内；缺文件/未集成/改动直接阻断，WEB后续修订必须Root交精确SHA再机械刷新。
这是候选源码钉住，不代替WEB独审或Root运行准入。

沿用prepare/execute命令，仅manifest scenario=browser_lifecycle，仍≤1800s/reserve180。
API/Web ready后probe子进程固定exec本地Node/Playwright CLI，不接受任意argv；workers1、
retries0、forbid-only、JSON reporter。Playwright实际grep含project/file前缀，故用固定
title后缀匹配，再对JSON的唯一spec.title做严格全等核验，不使用会零匹配的整串标题锚。
Root独立新case的browser目录700、子进程umask077；仅传V4_WEB_ORIGIN、V4_API_ORIGIN、
V4_EVIDENCE_DIR与本地工具环境，不传owner DB env。候选config trace/video/screenshot自动
捕获均off；spec主动截图仍私有，HAR默认无记录。没有浏览器安装/route stub/fallback。

只有native0且实际JSON唯一expected/passed、无skip/flaky/retry/errors，才记浏览器执行待审；
之后仍按停writers/容器→final PG→down流程。HTML200不再冒充WebGate。此spec不签独立
真实GUI 200% profile，该项仍另开窗口；其余跨标签/视觉矩阵以WEB原交付实际结果分列。
新增11项离线source/report/固定命令测试0.06s/native0，不启动Node/browser/HTTP/PG；
源码测试只从已交Git blob取公开样本，不读取作者WIP。Root尚未在本QA树集成WEB两文件，
因此当前browser模式会按设计拒绝；所有真实浏览器/自然TTL/Full/Hosted仍NOT_RUN。
