# M1 离线 Compose 装配与运行

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
