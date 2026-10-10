# Phase3 A01：会话、T1 与不可变 T2 等待候选

状态：作者实现与实际验证收口中，冻结 SHA、精确 CI、独立 Review 及 Root A01 Gate 以同 [PR37](https://github.com/aning0922/commerceops-agent/pull/37) 的后续回执为准。不是完整 Phase3 验收。授权来自 [Issue33](https://github.com/aning0922/commerceops-agent/issues/33)、[A34](https://github.com/aning0922/commerceops-agent/issues/34) 和 Root 直接派单；A 不合 main。

本批基于合同修复 `3e05c714289135ab6901159d7e9210d657967fc2`，合同 CodeGate 已由 Root 放行，实际 [CI38047261517](https://github.com/aning0922/commerceops-agent/actions/runs/38047261517) 成功，checkout `ff1ad1169a7561eae65dbfd935a83dd2ceb2b4fd` 同源。此前 edited 事件取消的 CI38047239504 和 bootstrap 失败 CI38046950437 保留在 [首批记录](contracts/p3-contract-delivery.md)，不当本批业务证据。分支仍 `codex/phase3-approval`，同隔离 WT62c8、同 Draft PR37；B14dc 组件未合入本批，frontend/npm lock/E2E 未修改。

## 实现与限制

- `0005_p3_approval` 以既有0004为父：固定逐角色 shop grant、Web credential/session/登录窗口、持久请求回执、P3源绑定、不可变 plan、approval 和永久禁用 sender 的 outbox。runtime 对 credentials/grants 仅 SELECT；无注册或角色配置 API。配置管理员改 scope/credential 必须先锁 principal，触发器递增 auth_version；不把基础 shop scope 自动扩成每个角色权限。
- Cookie 是随机32-byte opaque token，PG只存摘要；scrypt 固定 N131072/r8/p1/dk32、128MiB工作区，单API进程有界校验，未知用户同成本 dummy。CSRF 与 approval nonce 使用不同私有密钥和用途前缀。登录轮换、注销、绝对/空闲期限、当前 identity/credential/principal/auth_version/role-bound scope 由PG核实。精确Origin、JSON/严格整数、无客户端actor，可信socket peer限流；uvicorn 不信任代理头。
- T1 `from_report` 只建独立 P3 task/job/请求回执/audit，核绑定并保留原 P2。`new_cycle` 一事务建新 P2+P3 两 task、两首 job、源绑定和请求回执；单 Worker 串行采集/分析后再冻结 T2。同principal/operation/key锁及语义hash拒绝异payload，不以checkpoint充当事务。
- T2重验冻结P2报告及原参数：无建议为no_action；硬质量问题无plan；21候选整批SCOPE_REQUIRED，绝不截断；raw inbound null 与 effective0同时保留并生成完整假设对象。canonical plan/hash+approval+blocked card意图同事务。DB不可修改计划内容/期限/源证据；P3 completed在A01仅接受已绑定完整且无候选、无需复核的P2事实，带plan不能提前completed。A03须普通后续迁移加入永久execution回执证明。
- 首个P3 checkpoint即固定 `prepare_approval→wait_approval→revalidate→execute→finish`，唯一 interrupt、官方PG saver、durability=sync。只实现T2和持久等待，ready_at保持NULL、outbox blocked、sender false；任何决定/执行resume都fail-closed。恢复协调器/ready/T3/A02、重观测/T4/items/T6/A03均尚未实现。
- 当前读投影按owner/当前role-bound scope/冻结eligible限制，分页items/counts/total使用同一SQL CTE快照，cursor签名绑定actor/auth_version/endpoint/filter/order。admin-only无业务编号/计数/SKU，运维不虚报Worker状态。计划/历史审批只读，nonce null、can_decide false、can_resolve_items false；sync与业务状态独立。events仅安全已发生审计字段，无原始checkpoint/输入/秘密。

## 运行接口子集

以下为实际17 operations/16 paths；[冻结OpenAPI](contracts/p3-openapi.json)仍是完整21 paths/22 operations合同，不能据文档存在认定全部实现。

| 方法 | `/api/v1` 后路径 | 本批行为 |
|---|---|---|
| GET/POST | `/auth/csrf` GET、`/auth/login` POST、`/auth/session` GET、`/auth/logout` POST | PG真实会话/轮换/CSRF/注销 |
| POST | `/tasks` | 两模式T1，202持久回执 |
| GET | `/tasks`、`/tasks/{task_id}` | 有权P2/P3列表/详情，严格区分kind/workflow |
| GET | `/tasks/{task_id}/report` | 冻结P2事实原样，p3 session envelope |
| GET | `/tasks/{task_id}/explanation` | 只回已有校验缓存，不发新模型；正向缓存HTTP样例本批not_run |
| GET | `/tasks/{task_id}/plans`、`/tasks/{task_id}/plans/{plan_version}` | 不可变版本历史/完整假设披露 |
| GET | `/tasks/{task_id}/events` | 脱敏实际审计/轨迹 |
| GET | `/approvals`、`/approvals/{approval_id}` | 列表/完整只读详情，无nonce/决定能力 |
| GET | `/requests/{request_key}` | 当前principal+operation且当前有权原任务的持久回执 |
| GET | `/config`、`/admin/operations` | 当前有权店配置或admin安全运维摘要 |

未实现的5 operations：decision、execution、items列表、item详情、resolve。未开放写端点返回统一404安全envelope、零副作用；A01不接受模拟决定冒充T3。FastAPI手写请求解析/JSONResponse所导出的schema不完整，未将其当完整合同比对通过；实际wire JSON Schema检查单列，完整运行接口导出收口仍随A02/A03。

## 实际检查与失败保留

时区 Asia/Shanghai，2026-10-10；全部业务来源mock，身份是真实PG session，自动化approval_mode=simulated_web；无人类审批、模型调用或平台写入。

| 命令/探针 | 实际结果 | 证明边界 |
|---|---|---|
| `uv run --frozen python -m scripts.check` | exit0；933offline/87.16s、269 integration deselected，Ruff216/format216、mypy153；Node24.21.0工具链/原tooling typecheck，Node与95 Python包漏洞0，dir/index/git敏感扫描0 | 旧离线与29新增纯计划/严格输入/配置/crypto测试；不是真实PG或B业务Web |
| `uv run --frozen --with openapi-spec-validator==0.7.2 python docs/contracts/p3-validate.py` | exit0，385检查，21/22/67 | 冻结文法/refs/P2导出保持；不替代运行时安全 |
| `uv run --frozen --with jsonschema==4.26.0 python -m tests.p3_wire`，配显式自有PG配置 | 实际17响应checks passed | bootstrap匿名/session、401、T1、读plan/report/approval/list/config/receipt、404、logout；不记录响应正文/密码/Cookie/CSRF |
| A01定向 `pytest tests/test_p3_pg.py -k 'ten_replays or precommit_failure or twenty_one'` | 3passed/11.64s | T2十次重复同一套/事务提交前回滚/21候选整批拒绝；提交前RuntimeError仅事务负例，不冒称R01进程kill |
| A01稳定批 `pytest tests/test_p3_pg.py` | 26passed/58.76s | 含两个模式10路T1并发、一套T2、真实R01三模式、DB禁止提前completed；随后增加的在线撤权/限流/Cookie案例不属于该26项 |
| `pytest tests/test_p3_migration_pg.py` | 1passed/0.97s | fresh0004先实际完成P2+3checkpoint，再升最新0005；九表逐行JSON字节排序/row count/SHA256完全相同；仅基线生成用owner，P3运行权限另用app证明 |
| 最终串行 `pytest -m integration -q --tb=short` | exit0，271passed/223.90s、933 deselected、2既有lark SDK弃用warnings | 236既有PG+34 A01 PG+1 fresh迁移；真实app权限、R01三模式SIGKILL、T2、合法在线撤权、限流、两传输模式Cookie、单Worker及原回归；不将前两轮当通过 |

失败/修正事实：初始定向13passed/24.64s后新增读测试发现approval CTE少一个闭合括号，第二次18passed后失败；仅安全SQLSTATE42601/category诊断，补括号后2定向passed/3.92s。完整PG第一轮258passed/199.83s、1旧revision断言失败；更新revision后第二轮261passed/214.65s、1旧schema表全集断言失败和1初始化ERROR。与此同时补测28passed/68.04s、1新增principal撤权测试没按既有合同递增auth_version失败、3初始化ERROR。该撤权失败在db.execute时被既有require_auth_version约束明确拒绝（CheckViolation/SQLSTATE23514），上下文回滚，尚未提交且API请求没到达；不是已提交撤权后API放行。两批初始化重叠改集群role导致tuple concurrently updated，是作者验证编排错误；已停止重叠、保留失败，最终严格串行。旧schema exact set已加入全部9张P3新表，合法撤权测试按principal先锁/auth_version+1修正，base/role/credential撤权由0005触发器升版后回核session拒绝。静态长行/类型迭代也保留工具事实，不伪填通过或同一产品阻断三轮。

R01分别对 `new_cycle/from_report/inbox` 使用实际子进程在T1提交后/ACK前阻塞，parent SIGKILL、wait/reaped=-9后原请求十次回放；new_cycle增量2task/2job，from_report及兼容inbox增量1task/1job，Web请求增量1。没有以异常代替kill；没有新Worker热接管或伪旧进程终止证明。原from_report源task逐行JSON不变。

## 自有资源与时间账

唯一项目 `p3a-aa0deb15851d`，owner `phase3-A-WT62c8`，PG17.11-bookworm固定镜像摘要，loopback54435；私有目录700、配置/两密钥/PG密码/ledger/证据600且gitignored，不读.env。只启动该项目postgres；随机临时DB每测finally DROP，源基线与卷保留，不用down-v。

第一窗口19:18:54生成0004真实P2 completed/mock及三checkpoint后停止PG，running=false/PID0。第二窗口ledger20:20:24.931178登记，Docker实际StartedAt20:19:50.42877676；90min按较早真实启动计，最迟21:49:50停止。最终实际17响应wire复验再次passed，停止前临时库0/其他base连接0，app role superuser/createdb/createrole全false；随后只stop该项目postgres，实际inspect running=false/PID0、保卷。时间/owner/UID/停止事实见[安全停机摘要](contracts/p3-a01-stop-evidence.json)，最初九表摘要见[安全迁移摘要](contracts/p3-a01-migration-preservation.json)，最终fresh迁移probe另证最新源码；不上传原行/秘密，未标cleanup0或删除保留卷。

九表为business_tasks、commerce_snapshots、snapshot_products、snapshot_order_lines、snapshot_refunds、analysis_reports及官方checkpoints/checkpoint_blobs/checkpoint_writes；初始基线行数分别2/1/1/1/0/1/3/1/5。所有P2 evidence/task/report/hash/thread/checkpoint保持，不复活completed。

Agent墙钟按GitHub/ledger实际时间记账，机器等待按测试报告分列；未捕获的开发有效时间不估算。人工H/L not_reported、D1/D30/300h与A32/B18/Review10原容量保持。真实Browser/B集成、A02 R05–R09/R17及恢复ready、A03 R10–R12/C01–C05、T3/T4/T6、human_feishu/外部Base/生产/Phase4均not_run。原P1 G1/G2/G3回归不升级为P3业务Gate，#23 risk_accepted和M1冻结不变。

## 私有配置接线

API/Worker仅通过显式 `COMMERCEOPS_P3_CONFIG_FILE` 读取本阶段600配置文件：database为本阶段app连接字段/密码文件引用，csrf_secret_file与nonce_secret_file为两个不同至少32-byte私有文件，origins为精确scheme/host/port数组，transport_mode明确local_http或https；其余配置实值和bounds见`WebConfig`与冻结合同。API仍仅loopback，HTTP测试的local_http不能视为HTTPS部署证据；https Cookie属性由TestClient传输模式验证，TLS代理/生产部署不属本批。

预置用户由owner先写web identity、scrypt hash credential、基础scope和每角色grant；不暴露注册/授权端点。A01测试生成随机账号密码/私有密钥，源码只有生成器，没有真实password/hash fixture。Worker在相同显式DB、test mode、inventory-test-run及自有fixture下运行，配置不一致或actual-model/key选项同时出现即拒绝。A02尚未提供扫描/恢复协调器；不可把API写成功或job done当全部阶段完成。

## CI38053812405失败与一次有界预算修复

冻结39d7a3ad/tree9ab84f的[精确CI38053812405](https://github.com/aning0922/commerceops-agent/actions/runs/38053812405)实际FAILURE。933offline通过，但PG combined未出最终summary，不能以作者271pass替代该CI。Root于2026-10-10要求30min只读定位；A在21:13:30开始解码，随后Root按原Phase3持续授权放行一批最多30min scripts/test/docs最小修复，21:20:31开始实施。没有rerun旧39 head、重开旧#23未知根因、增加PG窗口或付费/平台操作。

只读安全事实（Asia/Shanghai）：combined于21:01:05.707718开始，原单命令limit_seconds=300；21:06:05.709116 command_timeout，elapsed300.001398s，随后自有container_stop/container_wait137/CLI wait137/reader_end，command_end elapsed303.735524s、timed_out=true/stopping_confirmed=true，cleanup_exit0。25min job/23min absolute未到截止；PG等待采样仅base闲置ClientRead、blocking_pids=[]。这只说明采样时无阻塞，不替未执行测试下结论。

1649 progress中235个call及各自setup/teardown均passed，failed phase0；最后停在`test_login_rate_limit_is_persistent_and_generic`的setup。九个CheckViolation文字来自唯一既有`test_runtime_money_precision_before_seal[1.0000001-CheckViolation]`的两collection+node_start+三phase_start/end重复，此负例三phase都passed，源码在未封存合法写入中明确pytest.raises金额payload与numeric(20,6)一致CHECK；日志没有九个真实SQLSTATE/异常，不能将testID当作故障。剩余36节点未完成：P3四个、postgres十三个、worker十九个。完整collection两次记录均271节点，原236/P3新增35；这些数字是该次观测，不是永久契约。

本批仅修改`scripts/pg_diagnostic.py` combined编排：先读取并严格核一个完整collection/count/唯一node与相对tests文件路径；按当前P3测试文件前缀从实际集合派生existing/P3两组，核并集精确等于完整集合、无重叠/遗漏/空组。串行两条命令每条仍300s，使用原main同一expires-75预算；每组成功退出后，实际collection必须与该组expected精确一致，缺失/改名/额外/无collection即失败，任一失败不跑后续组并沿原finally停止/cleanup。历史无P3时仍一条combined、paths=[]。不硬编码35/271、不跳测试、不扩全局截止，不更改G1流程/跨全部records的G2核收/Scrypt/角色/业务/恢复/锁/框架。

实际本批离线：新增19项分组反例与原21项停止控制回归共40passed/0.06s；覆盖遗漏、重叠、额外节点、伪count/无或多collection、实际集合同数量但改节点、历史单组、组失败停止、fake clock跨组绝对截止不重置。最初lint负例绝对路径文字与mypy引用非export time属性失败，修改测试表达后通过；没有新增扫描例外或改变deadline。最终Ruff/218format/mypy154 passed，完整offline952passed/77.12s、271 integration deselected、2既有SDK弃用warnings。私有实际CI collection离线重放派生236/35、并集271/重叠0/遗漏0；这是集合复算，不是两条新PG命令通过。自有PG只读inspect仍running=false/PID0，本轮未启动资源。

本轮不新增作者PG，分组实际PG/完整G1生命周期/新冻结独审/新精确CI仍not_run，A01正式Gate未过，A02/B未放行。Reviewer此前pytest planning并未执行wire.main，后来缺jsonschema前置失败也not_run；A自己的17实际wire证据单列，不代替独立补证。完整22 operations的FastAPI export/runtime一致仍A02/A03 finalGate，未降门槛。
