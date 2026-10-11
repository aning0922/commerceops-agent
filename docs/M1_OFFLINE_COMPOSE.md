# M1薄Compose离线装配候选

本功能批只准备原AC08所需可运行产品装配，不以memory Preview替cleanCompose证据。当前尚未build/start/真实PG或Web测试；必须精确源码独审后Root另注册自有有限窗口执行。原A04/Core池已释放，A05/e7精确CI与P1修复另记。M1/Phase4/human均未由本文验收。

作者当前实际7pure0.74s（项目/Mock/TTL/loopback/sourceFake约束），Docker Compose仅config解析0：postgres无hostport、API/Web host_ip均127.0.0.1、frontend无volume/secret、API/Worker仅app_password/user501:20；services_started0。完整1372offline87.59s/375integration deselected、252mypy/347format/Ruff/91MD0（含read恢复文档）实际核，scan及sourcefreeze另绑。初次新测试误引不存在helper名字导致ImportError/collection0，与初type3/import排序错误保留，换成已有projection_pair后7passed；无Dockerbuild失败假造或真实PG/SDK。上述离线/配置结果不能签AC08或原失败34PG。

## 装配与来源

原compose.yml不改，只叠compose.m1-offline.yml/m1-offline-demo profile：同一个自有无hostport PG，单API、单Worker子进程、既有Next生产CLI。API和Next在Docker私网监听0.0.0.0，主机只127.0.0.1发布两个明确临时端口。Web只公共COMMERCEOPS_UI_MODE=live/WEB_TRANSPORT=local_http/API_ORIGIN=http://127.0.0.1:实际APIhostport；无DB/任何秘密mount，不用container DNS作为浏览器origin。原C产品源码/npm锁原字节，Next正式CLI启动，不增加package脚本。

infrastructure/Dockerfile.m1-frontend用已实际核registry索引digest的node24.21.0-bookworm-slim，原npm ci --ignore-scripts/check-toolchain/check-read-schema/build；专属dockerignore只包含frontend及其schema检查必需的单个公开docs/contracts/p3-openapi.json，排node_modules/.next/env/evidence等。工作目录/app/frontend保原tooling相对位置，后端复用原test Docker target COPY封存scripts/tests/fixtures，无源码bindmount、无全局环境改变。

scripts.m1_offline_demo只prepare/seed/api/worker一薄入口：新私有目录的owner/app PG密码由原prepare_pg安全生成，0600/目录0700；seed只commerceops_owner+新鲜organizations0的本次PG、已有migrate/checkpointer/grant后调用原initialize_p3，不读旧DB或任何平台身份/密钥。仅新synthetic operator+approver，同principal Web真实PGcredential/session，approval_mode simulated_web；demo-account.json只私有600，Git/控制台不输出密码。原WebConfig origins改为精确Webloopbackorigin，cookie/CSRF/nonce合同不变。

API原create_app/ReplenishmentStore；Worker原InventoryCompositeRunner/InventoryRunner/ApprovalRunner/Worker/Graph，P2/T2/T4共同注入已审M1DemoFactory（baseline原twenty20×100=2000/完整未知一项，known_inbound原金标70）。ProviderFactory默认关闭无key，model not_used/平台0/无Feishu消息入口或outbox外写。内部T1–T6仍原权限、原版本、nonce、同stockpool原限制，不创建第二业务状态机/fixture框架/dispatcher。

Fake投影仅local OfflineProjection合成完整15列/原版本/稳定synthetic锚，mode offline_fake且原outbox senderfalse，最多原5task白名单；明确不是任何远端readback/SDK或实际Base证据。重启后合成锚保持同ID，可显示Fake sync；原真实Base adapter/fullbinding未放宽。超过5task不扩大gate，仅暂停Fake projection，业务Graph与内部item规则照旧。

## 原Worker恢复证明

单父进程仅负责信号和同容器内child stop/join/reap；SIGUSR1显式要求一次旧child干净停止、OS回收之后才启动下一个唯一Worker，仍由原WorkerSession同host/同PID namespace/旧PID absent与stopped audit裁决。未clean/exit75不继续、未知不假stopped；无自动restart策略，不加第二Worker或并发Graph。不能用全worker容器重建导致新namespace后假证明原PID消失；这仍会按既有合同拒绝，本文不改变或自动确认。

原固定expires_at最多T0+30min，Worker在截止退出；Root实际窗口须含停止收尾，deadline不复位。API/Web服务的停止由原Root有界owned harness执行，不能只停Worker当所有监听已停。AC08实际证明须同自有卷/原business UUID经过API+Web重新启动与SIGUSR1子Worker恢复，原roles/session/plan/execution/item读回、gold/flags/stop证据完整后才签Gate；当前not_run。

## 命令合同（待Root注册窗口）

Root先选两个空闲回环hostport、新m1off-UUID项目及ignored私有路径，记录source/tree/image、UID/GID、绝对截止与清理75s。COMMERCEOPS_PG_RUNTIME_DIR和COMMERCEOPS_DEMO_PRIVATE_DIR都指同本次目录；COMMERCEOPS_DEMO_UID/GID为本机501及实际gid，四端口/目录变量只传公开值。--env-file /dev/null防默认旧.env。

```sh
python -m scripts.m1_offline_demo prepare --directory /absolute/new/private-directory \
  --project m1off-UUID --web-port HOST_WEB_PORT --api-port HOST_API_PORT \
  --expires-at ABSOLUTE_UTC_DEADLINE
docker compose --env-file /dev/null -p m1off-UUID -f compose.yml \
  -f compose.m1-offline.yml --profile m1-offline-demo build \
  db-init m1-seed m1-api m1-worker m1-web
```

原db-init migrate/setup-checkpointer/grant-runtime/revision依次完成，role flags/tempDB/schema实际核后，仅一次m1-seed run --rm seed；启动m1-api/m1-worker/m1-web后安全壳/login200不代表业务ready。实际浏览器由C原live读/写合同完成账户登录→新cycle→20全披露→显式全ack T3→T4→T6与同ID恢复，断言不以Mock memory替代。保每步实际收集/JUnit或Playwright/私有manifest，而非本文预填结果。

同容器一次显式Worker恢复由`docker compose … kill -s SIGUSR1 m1-worker`触发；API/Web用正常restart，同project和同volume不seed第二次。终了必须only-owned标签/UID及falsePID0核实、监听0、普通down无-v，保卷/镜像/私有账户与source/JUnit，不prune/删旧资源或读取其他工程私配。当前所有这些实际步骤not_run。

## 首实际装配与生命周期收口

Root已核精确b4独审noP1/P2/35pure/config-only，并释放m1off-d8684a08332d/P4-AC08-WTfd38/UID501:GID20新40min：UTC07:37:23.807641→08:17:23.807641，服务自身30min expiry08:07，SDK/平台/provider0。sealed COPY b4实际build49s/0012 init全0/低rolefalse3/tempDB0/schema1/seed0/API+Next+唯一Worker真实启动/真实PGsynthetic登录/known70不可变计划通过，仅partial。私有driver误从plan内容取plan_id/hash/version而该元数据在approval，KeyError前未发送T3；原公开OAS及已有payload helper确证，Root允许同原固定窗一次仅driver字段修正、不重seed或重建known task。

续验worker-start exit2/private固定TerminationRequired：已停整个父容器后新namespace无法证明原已stopped child；原core保护正确拒绝，不伪状态或SDK/第二T3。第二stop UTC07:47:18.7734250/allfalsePID0，UID/project/net/vol/loopback监听0核后UTC07:50:56.896959 only-owned down0/no-v/no-prune/no-rmi、volume/image/private retained。此scope明确AC08 partial failed，Root已读记录；旧source/known task/plan/CP/原秘密卷保留，不在原window热补丁/第三次或新的盲project。raw logs/metadata/252source-manifest、安全summary在WTfd38 ignored runtime/m1off-d8684a08332d中，源/真实失败不拿35pure掩盖。

Root正式授权最小父监督器修复，core/API/迁移/权限不改：child在原WorkerSession.start后单Pipe只传自己的owner/PID/org/host/ns（无凭据）；父process.join/reap且exit0后核这个明确child和原org/同host/namespace，实际require_process_absent，再读同owner唯一started+原clean stopped不可变audit对比完整pid/host/ns，原confirm_termination取得原全局锁再复核并持久结案。正常退出及SIGUSR1都先此结案，之后旧namespace销毁也已有原确认，不以新namespace假证明；non0/exit75/未reap/livePID/PID复用/错误owner/org/ns/缺stopped/PG失败拒绝，不能清lease/改guard/伪marker。新批source/纯/独审后Root另新actualAC08窗口，不改原b4 image或失败数据。

修复作者定向17pure实际1.03s：真实普通child wait/reap+原require_process_absent，正常只确认精确own owner；错误owner/org/ns/缺stopped/未reap/非0/livePID/持久PID错都0confirm。SIGUSR1测试用两个真正普通process，第一已OS absent与确认才第二唯一child启动，最后正常停也确认；Fake DB/SDK0/不签PG，生产保持spawn，测试仅fork继承Fake（两条fork multi-thread warning保留，信号恢复）。完整1388offline90.08s/375integration deselected/4warnings、257mypy/353format/Ruff/92MD0。初作者type annotation修订已修，不是平台Gate失败；修复source/三scope scan/独审另绑，实际新生命周期尚未PG/Compose运行。
