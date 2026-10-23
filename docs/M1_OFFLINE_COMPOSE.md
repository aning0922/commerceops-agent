# M1 离线 Compose 装配与运行

## 新 clone 的 Mock 核心启动说明（2026-10-23，最终交接候选）

本节保留已核历史 `0661797b7b0c4bac78dcbb6f18abd6552875493a` / tree `da112ae63cb2de73206a143fd5d8ee3db4c4e4de` 为准备来源；[CI39417453535](https://github.com/aning0922/commerceops-agent/actions/runs/39417453535)五 job SUCCESS、565 PG（397+168，交集0），Web读/写/items及N01六项已由Root核收，最新owned准备范围见[Root安全回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6307662383)。本批只更新已知来源事实，没有执行clone、安装、build或服务启动。既有只读影响核对确认c460→066的Compose两文件、m1_offline_demo、前端/镜像及冻结18页映射无差异；四consumer在877→066无差异。当前数据库head仍为0017，运行时按最终冻结源码执行migrate/grant。W2 owned两回复/冷重放零新增、负向/低权及清理已核，不代表真实群、查询或新冷clone验收；main仍P3，最终组合来源及实际Gate待Root核收。

当前已核功能source为 `160d66acf5f21887abdfd5bada2232118755268e` / tree `90fc8ccce1421ea96a7fbbe0e450fe1b4ecca4cc`；[CI39909049939](https://github.com/aning0922/commerceops-agent/actions/runs/39909049939)五作业SUCCESS、567 PG及Web/N01通过。Next精确16.4.2有限安全升级已保留，原C双文件修复8b08573的本地audit0漏洞、contract67/B04 Mock8/Phase4 Mock22及build仅签其原范围，不代签后续源码。

原真实DM/F02、两轮群5+4动作、20 SKU/20 Base、原T6/v2/只读Web及最后两条新群查询所需真人平台Gate已收齐；新查询原独审PASS，各sent/attempt1、SDK6成功、17保护组不变、资源stop。raw wire/ACK及客户端已读均NOT_CAPTURED，不补写。旧两条群查询与旧原DM查询保持HOLD，原库/history恢复停止；新样本通过不回填旧消息成功。

本三文档为最终文档候选，docs/source Review、CI8、main、post1及Issues结案当前仍PENDING；main仍为原P3基线9d97，不预填未来SHA或完成。Root将后续实际结果统一登记在[固定权威结案回执](https://github.com/aning0922/commerceops-agent/issues/39#issuecomment-6360314990)，以该回执收口，不为合后结果循环改文档。

干净Compose四场景仍仅证明c460的offline Mock核心生命周期及恢复，不升级为真人渠道或本轮冷clone实跑；新真实群/查询证据单独核收。原视频和字幕只作私有自动化/静态演示，不是连续真人录屏，本批不重录、不重做Compose。

此前PR43 head36e的CI39644522303整体失败565/566及旧npm503保持；当时“下一候选待产生”的安排已由上述2f138技术核收接续。

### 三种入口不要混用

| 入口及仓库依据 | 新 clone 已有什么 | 不能据此认为有什么 |
| --- | --- | --- |
| `compose.yml` + `compose.m1-offline.yml`，`scripts/m1_offline_demo.py` 的 `prepare/seed/api/worker` | 实际 PG、原 API、单 Worker 与 Next 生产 Web 的 Mock 装配；可人工创建、审批及跟进内部项 | 不是单独运行一个 frontend memory Mock 页；不是飞书/模型入口，也不是完整四场景自动验收命令 |
| `frontend/app/[[...path]]/page.tsx` 的 Mock/B04 预览分支 | 静态或 memory DTO 的界面预览；不要求业务数据库 | 不能证明真实 session/PG、持久化、执行或外部投递 |
| `tests/e2e/web/m1_acceptance_driver.py`、`m1_acceptance_capture.py`、`m1_acceptance_ui.cjs` 及同一当前源码的 `scripts/p4_acceptance.py` | 已有消费、采集、浏览器及清理能力；共享入口按 manifest/request 与 hash 绑定来源 | Python consumer 库不是冷启动 CLI；CJS 也需要输入文件及 hash。不能不生成新 manifest/handoff 就消费旧窗口，不能把模块导入退出 0 当业务通过 |

容器化人工路径需要完整 Git 源码、Docker daemon/Compose、POSIX shell、Python 3.12.13 和 uv 0.11.25；从当前 checkout `uv sync --frozen` 建立自己的环境。源码依据是 `.python-version`、`pyproject.toml`、`uv.lock`、`infrastructure/Dockerfile`。前端镜像还需仓库两份公开 schema，不能只复制 frontend 目录；Node/npm 在 `infrastructure/Dockerfile.m1-frontend` 中固定，使用容器化 Web 不要求主机安装 Playwright。主机 Node/Chromium 是自动浏览器验收的额外依赖。当前采集器已准确注册0015/0016/0017；这只保持相应历史快照兼容，不授权对旧库执行迁移或沿用旧schema输入。冷缓存仍需获取锁定依赖和基础镜像；这里的“离线”指业务平台/模型关闭，不是断网安装包。此批未新增跨操作系统实跑，非 POSIX 的原生运行没有保证。

README 已链接到本文件；DEVELOPMENT 的环境安装段可复用，但其早期“没有 Next.js/正式业务 API”等阶段描述不能作为当前 P4 产品说明。外部导航随最终集成由原 owner 同步，本批只在原三文档内说明这一差别，不修改那些文件或据此新增工程任务。

### 人工路径：复用现有公开命令

所有参数从新 checkout 和新环境生成，不从旧 `runtime`、他人的 `.venv`、账号或窗口 DTO 复制。

| 要绑定的参数 | 取值来源 / 约束 |
| --- | --- |
| `COMPOSE_PROJECT_NAME` | 新的 `m1off-` 项目名；同时作为 `docker compose -p` 和本次请求的 project |
| `COMMERCEOPS_PG_RUNTIME_DIR`、`COMMERCEOPS_DEMO_PRIVATE_DIR` | 指向同一个新、canonical 绝对私有目录；最终目录 `0700`、生成文件 `0600`，不使用旧业务卷 |
| `COMMERCEOPS_DEMO_UID/GID` | 当前操作者实际 UID/GID，与私有目录 owner 一致；供 seed/API/Worker 读取本次文件 |
| `COMMERCEOPS_DEMO_API_PORT/WEB_PORT` | 本机两个不同空闲端口，范围 1024–65535；只绑定 loopback，选出端口不等于持续保留监听 |
| `m1_expiry` 与外层硬截止 | 新的含时区绝对 UTC；`prepare` 要求剩余大于 75 秒且不超过 1,800 秒。构建也消耗同一窗口，不因慢下载重置；停止全部服务的外层截止需另外管理 |

1. 在新源码根目录完成 `uv sync --frozen`，显式绑定上表参数。可在 Bash 中用下列公共标准库片段生成本次非秘密参数；本批只审文本，没有执行。两个 socket 关闭后端口仍可能被占用，后续冲突应停止并收尾，不复用旧项目。原 `scripts.prepare_pg`/`m1_offline_demo prepare` 创建凭据，不需要 Feishu AppSecret、模型 key 或旧数据库配置。

   ```bash
   m1_root="$(pwd -P)"
   read -r COMPOSE_PROJECT_NAME COMMERCEOPS_DEMO_API_PORT COMMERCEOPS_DEMO_WEB_PORT m1_expiry m1_hard_stop < <(
     "$m1_root/.venv/bin/python" - <<'PY'
   import socket
   from datetime import UTC, datetime, timedelta
   from uuid import uuid4
   with socket.socket() as api, socket.socket() as web:
       api.bind(("127.0.0.1", 0))
       web.bind(("127.0.0.1", 0))
       now = datetime.now(UTC)
       print("m1off-" + uuid4().hex, api.getsockname()[1], web.getsockname()[1],
             (now + timedelta(minutes=25)).isoformat(),
             (now + timedelta(minutes=30)).isoformat())
   PY
   )
   export COMPOSE_PROJECT_NAME COMMERCEOPS_DEMO_API_PORT COMMERCEOPS_DEMO_WEB_PORT
   export COMMERCEOPS_PG_RUNTIME_DIR="$m1_root/runtime/$COMPOSE_PROJECT_NAME"
   export COMMERCEOPS_DEMO_PRIVATE_DIR="$COMMERCEOPS_PG_RUNTIME_DIR"
   export COMMERCEOPS_DEMO_UID="$(id -u)" COMMERCEOPS_DEMO_GID="$(id -g)"
   ```

   `m1_hard_stop` 是操作者必须管理的绝对停止时间，不是自动计时器。以下是分步说明，不是带 trap 的一键脚本；出错后应主动进入第 7 步收尾，不能认为 shell 非零或 Worker expiry 已停止所有服务。
2. 运行现有准备入口（下面是参数化说明，本批没有执行）：

   ```bash
   uv run --frozen python -m scripts.m1_offline_demo prepare \
     --directory "$COMMERCEOPS_DEMO_PRIVATE_DIR" --project "$COMPOSE_PROJECT_NAME" \
     --api-port "$COMMERCEOPS_DEMO_API_PORT" --web-port "$COMMERCEOPS_DEMO_WEB_PORT" \
     --expires-at "$m1_expiry"
   ```

3. 组合 `docker compose --env-file /dev/null -p "$COMPOSE_PROJECT_NAME" -f compose.yml -f compose.m1-offline.yml --profile init --profile m1-offline-demo`，只操作本项目的明确服务名。先 `build db-init m1-seed m1-api m1-worker m1-web`，再 `up -d --wait --wait-timeout 90 postgres`。
4. 对同一 Compose 调用依次执行 `run --rm --no-deps db-init python -m commerceops.entrypoints.database` 的 `migrate`、`setup-checkpointer`、`grant-runtime`、`revision` 四个动作；066当前head为 `0017_p4_verified_history`，以本次实际revision输出核对最终冻结源码后，再 `run --rm --no-deps m1-seed` 一次。seed 会拒绝已有标记；重启不再 seed。它依赖仓库的 `tests` fixture 与 factory，使用的是 Docker `test` target，不能拿只含 `commerceops` 包的 wheel 代替整个源码装配。
5. 同一 Compose 调用 `up -d --wait --wait-timeout 90 m1-api m1-worker m1-web`。overlay 已令 Web 使用 `COMMERCEOPS_UI_MODE=live`、`local_http` 和本次 API loopback origin；数据仍为 Mock。单独的 `commerceops-api` 默认只提供基础入口，只有显式业务配置才装配业务路由，不是本 Mock 装配的替代命令。
6. 仅从本次受保护的 `demo-account.json` 本地取得合成登录信息，不复制进说明或控制台。用本次 Web 端口进入 `/login`，再从任务页明确新建请求。seed 的 `technical_fixture` 不是新业务任务；baseline 配合 L=3/R=7/S=2 的 20 项及完整假设确认、known_inbound 的 70 件都由现有 factory 提供。先读计划/版本，再显式提交本版本意见；内部项完成/关闭仍需原因和原请求回执。此处的合成授权不代表真人体验。
7. 任何命令失败或到截止即停止业务；先对同一 Compose 调用 `stop --timeout 30 m1-worker m1-api m1-web`，再 `stop --timeout 30 postgres`、`ps -a`，最后 `down --timeout 30`，不带 `-v`。Worker 父监督器负责同容器 child 的正常 stop/join/reap 和持久 audit；若停止非零，记录未知，不把它当成功，也不因此省略剩余清理。用本次 project label 单独查容器/网络、核两个监听关闭及本卷保留，正式验收再由原工具采低权停止证明。API/Web 不随 Worker expiry 自动退出，必须由操作者在 `m1_hard_stop` 前停止全部服务；不要用无作用域的清理命令处理其他项目。

### 私有自动采集器的限制，不新增一键验收 Gate

上述公开分步可作为可重现命令交付；不以“一条命令完整验收”作为新的必要 Gate。静态核对尚未发现人工 Mock 产品启动缺少不可替代的配置/装配，因此本批没有新增 A 工程任务。已通过的四场景整批调用者仍是私有验收资料，不能冒充 clone 自带能力；它的不便携也不使已有公开服务失效。

| 私有验收限制 | 对新使用者的准确说明 |
| --- | --- |
| 固定来源、工具链与 handoff | 自动验收输入需要当前 checkout 的环境、schema、工具版本/hash 和新窗口绑定；旧 `run-input` 不能复用。人工路径可直接使用本节分步，不必先构造旧验收 DTO |
| 具体四场景私有调用者 | 私有 `compose-commands.py`/`ui-commands.cjs` 及绝对路径不在公开 clone 中；现有 consumer/helper 不应伪装成自包含场景 CLI，也不要求为此新增通用 launcher |
| 停写后低权采集和自动清理报告 | 已审整批入口有 `CleanupPlan/cleanup_owned` 及诊断最多 20 秒/清理至少 180 秒的约束；人工启动与停止按前述公开命令执行，不把自动报告缺失当成公共产品启动缺配置 |
| 本次未做新机器运行 | 本批仅回填066已知来源并复用既有影响核对；c460既有541 PG/私有四场景、066的565 PG及旧录像均按原范围引用，不称本次冷clone通过。最终只补源码影响所必需的链，不新增通用launcher或整批重跑Gate |

本批不改权限、状态机、Next.js、迁移或平台功能，不为文档移植工作启动服务。投影、真实查询、群与负向恢复的 Gate 不因人工 Mock 启动说明而减少；29 outbox pending/attempts 0 的既有边界保持。

## 已核历史交付：c460 有限离线复现（原范围保持）

本节为既有 M1 交付的文档工作稿，待与 A 的稳定事实合批审核、集成。依据 Root 的 Issue39 核收评论 6233059628、6234076316，并纳入已独审 RO140200 与观察于 2026-10-17 14:16:09.975121Z 的后台只读日志；新增原件与 hash 见交付地图。没有因整理本文而启动服务或平台动作；下方旧装配说明和失败记录全部保留，旧 `not_run/partial` 不代表本节这次运行的结论。

- 业务源码固定为 `c460d6f63f95060a2b25ae9418ca6e3020f89169`，tree `fbdef75c80267596a5dd62fda1f28be6dd18a70c`。同源码 CI39015392794 五项成功、541 PG 的既有核收保持；这不是本次文档的新 CI。
- 本次从同一 Git archive 提取新自有目录，archive SHA256 `656e18693f67c5d154d6af3d533563ba06f5b661d1f657b99695ddde455f4c89`；1,075 个受版本管理文件的字节及 1,163 个归档成员的模式核验通过。目录和可执行文件为 `0755`，普通文件为 `0644`；外层私有目录仍为 `0700`。
- 实际运行 2026-10-17 10:47:00–10:48:22.689954Z（北京时间 18:47:00–18:48:22.689954），82.689954 秒是机器运行时间，不能当成录像时长。原 launcher 退出 0，结论仅为 `PASS_SCOPE_OFFLINE_DEMO_ONLY`。
- 原独审 `a6d70d4d8ad7ee82e5166518d33d997c5e6e0212d3330da952f0e07d1b0babeb` 无 P1/P2，签的是 `simulated_web / MockCommerce / offline_fake` 的核心生命周期和持久读取；真实飞书与整体 M1 另行验收。

| 本次原生 UI 场景 | 已保存的实际结果 |
| --- | --- |
| baseline 拒绝假设 | rejected，零 execution、零内部项 |
| baseline 完整假设确认并批准 | completed，1 execution、20 items、2,000 units |
| known inbound 单项 | completed，1 item、70 units；显式关闭后 closed/v2，原原因保留 |
| 同 SKU、同库存池新周期 | completed，1 新 item、70 units；新 task/execution/item 与旧对象不同 |

总计 4 formal、4 analysis 支持任务及 1 technical fixture，3 executions、22 items。11 POST 均非重复；84 GET 留存原件，重启后的 11 次原键 GET 的完整 `receipt.result` 与各自 POST 回执一致。正常恢复实际范围为 Worker `SIGUSR1` 后 API/Web restart；原 task/execution/item 绑定、closed/v2、原因和终态 B27 不可用保持。自动化执行不等于真人操作或真人已经观察这些页面。

**同步边界：29 条 outbox 仍 pending、attempts 0。** 本调用者未执行 SyncRead、drain 或投影验证。`offline_fake` 是来源模式，不是投影成功回执；不能用本次结果声明 Fake 投影、真实 Base 同步或群闭环完成。

### 私有原件与执行说明的边界

以下位置相对原 C 工作区，属于保留的私有证据，不随仓库 clone 分发；这里只列审计定位，不列账号、业务定位值、秘密或实际服务地址。

| 材料 | 私有位置 / 固定来源 |
| --- | --- |
| 完整实际索引，149 引用 | `runtime/m1-clean-c460-batch-88094ef275/C-complete-native-delivery.safe.json`；SHA256 `cbf5da8b111a6b76f2eb3d0edf2906e882aea9d9fc17158f57ba5f43d9768791` |
| 原始命令与生命周期入口 | 同目录 `compose-commands.py`；SHA256 `1aa302d2ba82ed3bd3bb4ce45a74f1caea5c69c0dbed4366f5ba144b02341481` |
| 原生业务调用者 | 同目录 `ui-commands.cjs`；SHA256 `f912d4c79e031af4322651b454af729d49516e82acf689c7dcddcaba58e2a1d2` |
| 来源、权限与业务证据 | 同目录 `evidence/source-archive-verification.safe.json`、`actual-service-image-binding.private.json`、`runtime-node-permissions.stdout.private`、`ui-success.private.json`、`before-restart.private.json`、`writer-stopped-snapshot.private.json` |
| 收尾与停止证据 | 同目录 `evidence/cleanup.safe.json`、`worker-stop.safe.json`、`browser-stop.safe.json` 及根目录 `independent-final-resource-check.safe.json` |

实际 argv 为从工程根目录调用 `.venv/bin/python` 和本次私有 `compose-commands.py`。这是历史命令说明，**不应直接重跑**：私有输入和固定 UTC 已过期，工具链引用带原机器的绝对位置，原片和私有件也未完成公开脱敏。当前材料不是已交付的可分发一键包。仓库内下方通用 recipe 仍可解释装配步骤，但不能代替本次精确调用者、环境绑定或授权。

最终运行说明还须在原 owner 的审核中说明：如何从新 checkout 取得审定装配、核 Node 24.21.0 / Playwright 1.64.0 / Chromium 1248 及其来源，如何重新生成全新私有输入，而不引用旧凭据、旧机器路径或过期窗口。本工作稿仅列该缺项，不发布执行许可、不新建脚本或另一包装入口。

### 已验证的保护与保留的失败

解包采用归档模式的规范权限，不能在 `umask 077` 下仅凭文件字节相等就认定目录可遍历。实际 Web 容器镜像与本次 build manifest 匹配；以 `USER node` 检查源码目录、配置及生成的 `.next` 路径，读取/遍历退出 0。调用者保留刚提交的决定，只等待同一审批的业务推进；只有明确的新 pending、更高版本且可决定的审批才进入下一次显式意见，不盲重发。GET 原件在 HTTP/schema 断言前保存。

原入口的固定机器窗不超过 1,800 秒，工作截止比硬截止提前至少 200 秒，失败诊断最多 20 秒，最后至少 180 秒留给原 `cleanup_owned`。失败时仅在项目、工作目录和服务归属核验后采集过滤的状态/镜像及有限 Web stdout/stderr，私有输出 `0600`，安全索引只含文件名、哈希和固定码；不采集 Config.Env 或秘密。诊断失败不能阻止清理。本次成功未触发失败诊断，不把未触发写成运行时故障路径全验。

writers 退出后的低权快照为 `commerceops_app`，三个高权 flags 均 false；Worker started/stopped/termination-confirmed 各 2。原清理全部命令 0，PG false/PID 0、down 不带 `-v`，本项目容器/网络为 0、两个监听关闭、卷保留；浏览器 PID absent。旧导入、网络容量、解包权限差异及已批准 v2 页 B02 禁用等失败保持原结论；旧逐次 GET 缺失的具体中间时序仍 unknown，不由本次成功倒填唯一根因。

最终逐 AC 边界见 [交付地图](PHASE4_M1_DELIVERY.md)，原片、截图和待 QA 的时间轴见 [Web 交接](ux/phase4-implementation.md)。本文不要求重复已核真实 F02、原 T6 或 Base v2。随后唯一原库 RO 已证明原两文本 exact hash、原 actor/chat 谓词下的本地 inbox/carrier 为 0，72 引用独审、三段 RO rollback/I/U/D=0、F02 保护行和清理均已核；不把该零行推广成用户未发送或全部入站为零。

Root 后台只读另见北京时间 21:02:10/21 两个消息事件：首推 app not online、retry 1/2/3 均 FAIL，旧 Gateway 21:01:45 已停；UI 无正文，事件与原两文本的精确关联仍 UNKNOWN。查询回复 Gate 未过，恢复由 A/Root 按实际证据制定，Gateway、SDK 回复及业务写窗口保持关闭。上述后台只读不授予执行许可，也不是本离线 Compose 的投影证据。

本地媒体有限核对已另记：七图中五图为加载或会话核实态；两张 closed/v2 长图和 45.80 秒原片仍带定位标识。现存文件/命令/回执可作私有技术证据，不把它们称为已脱敏求职成片，不因素材缺陷改写已核业务结果。

## 历史装配说明与失败记录（以下原文保留）

当前 Phase4/M1 持续开发，main 基线 9d97、候选沿 PR43，授权与分层证据见 [STATUS](STATUS.md)和 [Phase4 验收](PHASE4_ACCEPTANCE.md)。本轮（2026-10-13）只补 frontend 镜像的独立 N01 schema 输入并整理现成运行流程；这份源码候选未执行新 build/start、PG 或 Web closure。精确独审后由 Root 另注册全新 owned 30min 机器窗口，不能将历史 partial、memory Preview 或本文命令当作新 clean Compose 通过。

历史首包检查：7pure0.74s（项目/Mock/TTL/loopback/sourceFake约束），Docker Compose仅config解析0：postgres无hostport、API/Web host_ip均127.0.0.1、frontend无volume/secret、API/Worker仅app_password/user501:20；services_started0。完整1372offline87.59s/375integration deselected、252mypy/347format/Ruff/91MD0（含read恢复文档）实际核，scan及sourcefreeze另绑。初次新测试误引不存在helper名字导致ImportError/collection0，与初type3/import排序错误保留，换成已有projection_pair后7passed；无Dockerbuild失败假造或真实PG/SDK。上述原提交结果不能签本轮新 image、AC08 或原失败34PG；后面的实际 partial/失败记录保持历史。

## 装配与来源

原compose.yml不改，只叠compose.m1-offline.yml/m1-offline-demo profile：同一个自有无hostport PG，单API、单Worker子进程、既有Next生产CLI。API和Next在Docker私网监听0.0.0.0，主机只127.0.0.1发布两个明确临时端口。Web只公共COMMERCEOPS_UI_MODE=live/WEB_TRANSPORT=local_http/API_ORIGIN=http://127.0.0.1:实际APIhostport；无DB/任何秘密mount，不用container DNS作为浏览器origin。原C产品源码/npm锁原字节，Next正式CLI启动，不增加package脚本。

infrastructure/Dockerfile.m1-frontend用已实际核registry索引digest的node24.21.0-bookworm-slim，原npm ci --ignore-scripts/check-toolchain/check-read-schema/build；专属dockerignore只包含frontend及schema检查必需的两个公开输入 docs/contracts/p3-openapi.json、docs/contracts/p4-n01-openapi.json，排node_modules/.next/env/evidence等。两合同在 schema-check 前 COPY，工作目录 /app/frontend 保原 tooling 相对位置；P3 22 操作与独立 N01 操作不重写。后端复用原test Docker target COPY封存scripts/tests/fixtures，无源码bindmount、无全局环境改变。

scripts.m1_offline_demo只prepare/seed/api/worker一薄入口：新私有目录的owner/app PG密码由原prepare_pg安全生成，0600/目录0700；seed只commerceops_owner+新鲜organizations0的本次PG、已有migrate/checkpointer/grant后调用原initialize_p3，不读旧DB或任何平台身份/密钥。仅新synthetic operator+approver，同principal Web真实PGcredential/session，approval_mode simulated_web；demo-account.json只私有600，Git/控制台不输出密码。原WebConfig origins改为精确Webloopbackorigin，cookie/CSRF/nonce合同不变。

seed 还会建立原 initialize_p3 的 technical_fixture 分析基线及账户。该基线不是本次业务 T1、不是新周期验收，也不代表已批准或执行；ready 后须从 UI 明确创建一个新 cycle，再分别核当前 plan/approval/execution/item。此离线目录和卷不得复用已 prepared 的真实 A Feishu/Web 身份卷。

API原create_app/ReplenishmentStore；Worker原InventoryCompositeRunner/InventoryRunner/ApprovalRunner/Worker/Graph，P2/T2/T4共同注入已审M1DemoFactory（baseline原twenty20×100=2000/完整未知一项，known_inbound原金标70）。ProviderFactory默认关闭无key，model not_used/平台0/无Feishu消息入口或outbox外写。内部T1–T6仍原权限、原版本、nonce、同stockpool原限制，不创建第二业务状态机/fixture框架/dispatcher。

Fake投影仅local OfflineProjection合成完整15列/原版本/稳定synthetic锚，mode offline_fake且原outbox senderfalse，最多原5task白名单；明确不是任何远端readback/SDK或实际Base证据。重启后合成锚保持同ID，可显示Fake sync；原真实Base adapter/fullbinding未放宽。超过5task不扩大gate，仅暂停Fake projection，业务Graph与内部item规则照旧。

## 原Worker恢复证明

单父进程仅负责信号和同容器内child stop/join/reap；SIGUSR1显式要求一次旧child干净停止、OS回收之后才启动下一个唯一Worker，仍由原WorkerSession同host/同PID namespace/旧PID absent与stopped audit裁决。未clean/exit75不继续、未知不假stopped；无自动restart策略，不加第二Worker或并发Graph。不能用全worker容器重建导致新namespace后假证明原PID消失；这仍会按既有合同拒绝，本文不改变或自动确认。

原固定expires_at最多T0+30min，Worker在截止退出；Root实际窗口须含停止收尾，deadline不复位。API/Web服务的停止由原Root有界owned harness执行，不能只停Worker当所有监听已停。AC08实际证明须同自有卷/原business UUID经过API+Web重新启动与SIGUSR1子Worker恢复，原roles/session/plan/execution/item读回、gold/flags/stop证据完整后才签Gate；当前not_run。

## 现成命令（Root 独审后另开机器窗口）

从本工程根目录的 bash 执行，使用 DEVELOPMENT 已准备的本地 .venv。Root 先登记新 project、私有目录、source/tree/image、当次 host UID/GID、端口与绝对总 stop；例子为服务 T0+25min、总 stop T0+30min，留停止收尾时间。构建、初始化和操作均消费同一窗口，不在失败或超时后重置 expiry。API/Web 不会随 Worker expiry 自动退出，Root 的 owned 监督必须按总 stop 停止全部服务。

```bash
set -euo pipefail
m1_python="$PWD/.venv/bin/python"
m1_project="m1off-$("$m1_python" -c 'from uuid import uuid4; print(uuid4().hex)')"
export COMMERCEOPS_PG_RUNTIME_DIR="$PWD/runtime/$m1_project"
export COMMERCEOPS_DEMO_PRIVATE_DIR="$COMMERCEOPS_PG_RUNTIME_DIR"
export COMMERCEOPS_DEMO_UID="$(id -u)"
export COMMERCEOPS_DEMO_GID="$(id -g)"

# 两个同时保留的 loopback socket 选出不同空闲端口；启动时仍须核实际监听。
read -r COMMERCEOPS_DEMO_API_PORT COMMERCEOPS_DEMO_WEB_PORT < <(
  "$m1_python" - <<'PY'
import socket
with socket.socket() as api, socket.socket() as web:
    api.bind(("127.0.0.1", 0))
    web.bind(("127.0.0.1", 0))
    print(api.getsockname()[1], web.getsockname()[1])
PY
)
export COMMERCEOPS_DEMO_API_PORT COMMERCEOPS_DEMO_WEB_PORT
read -r m1_expiry m1_outer_stop < <(
  "$m1_python" - <<'PY'
from datetime import UTC, datetime, timedelta
start = datetime.now(UTC)
print((start + timedelta(minutes=25)).isoformat(),
      (start + timedelta(minutes=30)).isoformat())
PY
)
m1_compose=(docker compose --env-file /dev/null -p "$m1_project"
  -f compose.yml -f compose.m1-offline.yml
  --profile init --profile m1-offline-demo)

"$m1_python" -m scripts.m1_offline_demo prepare \
  --directory "$COMMERCEOPS_DEMO_PRIVATE_DIR" --project "$m1_project" \
  --web-port "$COMMERCEOPS_DEMO_WEB_PORT" --api-port "$COMMERCEOPS_DEMO_API_PORT" \
  --expires-at "$m1_expiry"
"${m1_compose[@]}" build db-init m1-seed m1-api m1-worker m1-web
"${m1_compose[@]}" up -d --wait --wait-timeout 90 postgres

"${m1_compose[@]}" run --rm --no-deps db-init \
  python -m commerceops.entrypoints.database migrate
"${m1_compose[@]}" run --rm --no-deps db-init \
  python -m commerceops.entrypoints.database setup-checkpointer
"${m1_compose[@]}" run --rm --no-deps db-init \
  python -m commerceops.entrypoints.database grant-runtime
"${m1_compose[@]}" run --rm --no-deps db-init \
  python -m commerceops.entrypoints.database revision
"${m1_compose[@]}" run --rm --no-deps m1-seed
"${m1_compose[@]}" up -d --wait --wait-timeout 90 m1-api m1-worker m1-web
"${m1_compose[@]}" ps
curl --fail --silent --show-error \
  "http://127.0.0.1:$COMMERCEOPS_DEMO_API_PORT/health/live"
curl --fail --silent --show-error --output /dev/null \
  "http://127.0.0.1:$COMMERCEOPS_DEMO_WEB_PORT/tasks"
```

每步非零、Worker 退出或到截止即停止，不继续业务流程；PG 没有 host port，API/Web 仅发布 loopback。`up --wait`、health/live 和 Web HTTP 200 只证明技术 ready。Root 还须核本次 app role 三个高权 flags 均 false、单 Worker、当前 source/build、无平台/provider 调用及 owned 标签；不把 shell 或 login200 签业务 Gate。

操作者只在本机从本次私有目录的 demo-account.json 读取账户，进入 loopback Web。新业务 T1 选择 baseline、L=3/R=7/S=2，原 M1DemoFactory 产生完整 20SKU 与原未知项；读取完整计划/来源与所有 unknown keys，使用绑定当前 plan/version/hash/nonce 的完整未知确认 T3，不能以普通 approve 代替。待 T4 原执行完成后核 20 内部工作项；T6 对同一 item 完成/关闭并核 v2、同一执行和投影锚。批准、创建与 T6 的原 request key 由操作者本地保留，通过原 GET /api/v1/requests/{request_key} 读取同一结果，不换键补写。known_inbound 的 Q70 是另一 fixture 切片，不能代签 20SKU 场景。

本流程始终标 Mock/simulated_web/offline_fake/provider disabled；没有 Feishu 入口、真实采购、库存修改或平台外写。收集当前服务和业务证据后，在已注册总 stop 前执行：

```bash
# 同一命名空间正常停 Worker；父监督器完成 child join/reap/termination 确认。
"${m1_compose[@]}" stop --timeout 30 m1-worker m1-api m1-web
# Worker 已回收且原 PG 中 termination 确认完成，随后才停 PG。
"${m1_compose[@]}" stop --timeout 30 postgres
"${m1_compose[@]}" ps -a
"${m1_compose[@]}" down --timeout 30
docker ps -a -q --filter "label=com.docker.compose.project=$m1_project"
docker network ls -q --filter "label=com.docker.compose.project=$m1_project"
```

Root 必须实际核唯一 child 的 stop/reap/audit、PG running false/PID0、上述 project 容器网络 0、两个本机监听 0 和原卷仍存在；保留镜像、卷、私有账户与 source/JUnit，不加 `-v`、不 prune、不删旧资产。可选恢复只在原未过期窗口内 `"${m1_compose[@]}" kill -s SIGUSR1 m1-worker`；API/Web 正常 restart，同 project/volume，绝不 seed 第二次或重置截止。本轮这些机器步骤仍 not_run，等待 Root 新窗口。

## 首实际装配与生命周期收口

Root已核精确b4独审noP1/P2/35pure/config-only，并释放m1off-d8684a08332d/P4-AC08-WTfd38/UID501:GID20新40min：UTC07:37:23.807641→08:17:23.807641，服务自身30min expiry08:07，SDK/平台/provider0。sealed COPY b4实际build49s/0012 init全0/低rolefalse3/tempDB0/schema1/seed0/API+Next+唯一Worker真实启动/真实PGsynthetic登录/known70不可变计划通过，仅partial。私有driver误从plan内容取plan_id/hash/version而该元数据在approval，KeyError前未发送T3；原公开OAS及已有payload helper确证，Root允许同原固定窗一次仅driver字段修正、不重seed或重建known task。

续验worker-start exit2/private固定TerminationRequired：已停整个父容器后新namespace无法证明原已stopped child；原core保护正确拒绝，不伪状态或SDK/第二T3。第二stop UTC07:47:18.7734250/allfalsePID0，UID/project/net/vol/loopback监听0核后UTC07:50:56.896959 only-owned down0/no-v/no-prune/no-rmi、volume/image/private retained。此scope明确AC08 partial failed，Root已读记录；旧source/known task/plan/CP/原秘密卷保留，不在原window热补丁/第三次或新的盲project。raw logs/metadata/252source-manifest、安全summary在WTfd38 ignored runtime/m1off-d8684a08332d中，源/真实失败不拿35pure掩盖。

Root正式授权最小父监督器修复，core/API/迁移/权限不改：child在原WorkerSession.start后单Pipe只传自己的owner/PID/org/host/ns（无凭据）；父process.join/reap且exit0后核这个明确child和原org/同host/namespace，实际require_process_absent，再读同owner唯一started+原clean stopped不可变audit对比完整pid/host/ns，原confirm_termination取得原全局锁再复核并持久结案。正常退出及SIGUSR1都先此结案，之后旧namespace销毁也已有原确认，不以新namespace假证明；non0/exit75/未reap/livePID/PID复用/错误owner/org/ns/缺stopped/PG失败拒绝，不能清lease/改guard/伪marker。新批source/纯/独审后Root另新actualAC08窗口，不改原b4 image或失败数据。

修复作者定向17pure实际1.03s：真实普通child wait/reap+原require_process_absent，正常只确认精确own owner；错误owner/org/ns/缺stopped/未reap/非0/livePID/持久PID错都0confirm。SIGUSR1测试用两个真正普通process，第一已OS absent与确认才第二唯一child启动，最后正常停也确认；Fake DB/SDK0/不签PG，生产保持spawn，测试仅fork继承Fake（两条fork multi-thread warning保留，信号恢复）。完整1388offline90.08s/375integration deselected/4warnings、257mypy/353format/Ruff/92MD0。初作者type annotation修订已修，不是平台Gate失败；修复source/三scope scan/独审另绑，实际新生命周期尚未PG/Compose运行。

Root精确9f23独审发现P1：started完整对比但stopped仅EXISTS，未比较stopped.after_state，错误同owner的stop记录可能过关；Core41pure5.13/type/Ruff/scan通过不解除P1。一次最小修复仅此查询改为join读取started_state/stopped_state，两者都必须完整等原receipt、联合行恰1；缺/多任一记录及stop错PID/host/ns拒绝。补四负例全部0confirm，原core/锁/角色/namespace/固定deadline不改，无实际热补丁或SDK。新的精确复审另记，旧P1与首AC08两partial仍保留。
