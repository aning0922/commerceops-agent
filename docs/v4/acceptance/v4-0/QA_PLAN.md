# V4-0 独立 QA 执行方案

2026-11-03，台北。状态 `PREPARATION_ONLY / RUNTIME_NOT_RUN`。Root 精确释放本文件；
QA 仅写此文件及 `tests/e2e/v4/**`。实现授权见 `docs/v4/IMPLEMENTATION_AUTHORIZATION.md`；
四合同与 strict OpenAPI 使用 baseline 冻结原件，其 A 阶段状态保留。沿用 A 审计，不重复审计。

QA 起始源码 `fa96764cf2b8e3ab9adbb579b764f600a7d17e60`，分支 `codex/v4-qa-20261103`。
仅在 `/Users/aipuli/.codex/worktrees/commerceops-v4-qa/commerceops-agent` 写入。
本切片不含 API/WEB 作者未提交成果；Root 提供精确已审提交后普通合入、重新绑定最终 SHA/tree。

## 可执行准备与依赖

从当前 worktree 执行 `python3 tests/e2e/v4/preflight.py`，输出当前 SHA/tree、dirty、
五合同文件 SHA256 和八端点结构检查。此命令无 network/Docker/Secret/启动/清理能力，
成功只证明准备结构检查通过，不证明运行 Gate。`--window /absolute/new/window.json`
额外检查 Root 拟定的对象、源码、显式 UTC、端口与清理余量；仍不会开窗或启动服务。
窗口 JSON 不存凭据，精确字段为：

```json
{
  "owner": "QA",
  "project": "v4qa_REPLACE_NEW_LOWERCASE_ID",
  "database": "v4qa_REPLACE_NEW_LOWERCASE_ID",
  "volume": "v4qa_REPLACE_NEW_LOWERCASE_ID",
  "api_port": 18080,
  "web_port": 13000,
  "source_sha": "REPLACE_EXACT_REVIEWED_40_HEX",
  "source_tree": "REPLACE_EXACT_REVIEWED_40_HEX",
  "starts_at": "REPLACE_ROOT_UTC",
  "deadline": "REPLACE_ROOT_UTC",
  "cleanup_reserve_seconds": 180
}
```

上面故意不能直接运行，端口也尚未分配。每 slice 提议最多 1800 秒、reserve 至少180秒，
不是继承旧预算或已获运行窗口；不足则停并交 Root 调整，不续期。真实 TTL30分钟案例
须 Root 单独登记覆盖自然到期及清理的窗口，或由 API 作者提供已审 owned PG 时间夹具；
短 TTL 夹具不能签收真实30分钟自然到期。所有昂贵完整运行由 Root 串行统一安排。

接线前必须取得：身份桥接 SQL/ACL/锁序专项审查回执；API/迁移/seed/reset 已审 SHA；
WEB 已审 SHA 与真实 Playwright 命令/环境；新 owned PG17.11/pgvector0.8.7 指纹；
Root 的 project/database/volume/loopback ports/绝对 UTC/cleanup 合同。
尚未交付的 API/seed 启动参数与 SQL 对象名保持 `PENDING_OWNER_HANDOFF`，禁止猜测运行。

## 有界全链编排（等待 Root 开窗）

1. 在最终干净集成 SHA 上执行 preflight 并保存 stdout/native exit。Root 单独分配全新证据
   目录（0600 原始证据，不提交 cookie/CSRF/明文凭据），记录工具/锁/合同指纹。
   资源 owner 在启动前生成本批新凭据；环境不得继承旧 `.env`、私有 runtime 或 `.audit`。
2. 只创建登记的新项目/卷/网络；PG 无宿主端口，API/Web 仅 loopback。记录本次确切
   container IDs、volume/network IDs、镜像指纹与创建时间；禁止停未知资源或清扫全机。
   没有原 M3 镜像 receipt 的继承权，新 receipt 必须绑定本次源码与构建输入。
3. SCHEMA/API 提供并执行已审迁移和最小 seed 入口，验证低权 runtime 与无额外 Worker/
   Graph/外部调用；API 实际连新 PG，WEB 实际连 API。直接 readiness GET 不授予测试通过；
   记录每个自启 PID/进程组和精确命令。启动任一失败转收证与 owned cleanup，不盲重试。
4. 两个独立 cookie jar/browser context 创建 A/B 访客，完成欢迎→创建→GET current→
   双店 seed-summary→persona→reset→logout。每一步核 strict DTO、真实 PG receipt/DB UTC/
   context/seed digest，不以 UI 文本或 HTTP200 单独签收。QA 使用真实 HTTP 与独立 PG 核验，
   WEB 的专属 UI tests 由其 owner 执行；QA 不写 `frontend/v4-tests/**` 或其配置。
5. 依下表独立负例执行，显式记录预期拒绝与实际 status/code/DB差异。作者 PG 测试可复现，
   不能代签独立 HTTP/浏览器全链。ACK 故障仅在新 owned 传输边界丢弃真实响应，后端实际提交；
   不用 Playwright route mock 返回伪造成功或拒绝作为 Gate。
6. 工作截止前停本次 writers/API/Web并回收子进程，PG 仍在线时最后采集 DB UTC、receipt、
   immutable audit/tombstone、B digest；随后只停已登记 owned PG。独立核 PID/端口/容器/
   网络状态，按 Root 本窗口合同保卷或删除临时卷，绝不擅自 `down -v`。cleanup 失败单列 FAIL。

首提交59a7仅实现步骤1的只读准备。后续本目录已新增项目专用 supervisor 与真实 HTTP/PG
probe代码，具体能力与尚待接线见下节；仍未启动服务，不能宣称已通过全链。
必要共享入口修改先交 Root，不改旧 harness、不新通用 runner/framework/业务worker。

## 独立负例与判据

| ID | 操作与独立观察 | 必须满足的判据 |
|---|---|---|
| Q01 | A/B 同模板不同 tenant；A 查询 B shop/receipt，反向再测 | 404且无标识/业务泄漏；PG tenant/org/shop对象不同 |
| Q02 | 默认 operator 两店都读；移除一店 grant 后逐店读；受限 admin无grant | 有权店仍成功、撤grant店404；admin无隐含权限；不能因seed两店默认全授权 |
| Q03 | persona前保留actor/CSRF/generation，切换后重用并撤credential/identity/principal | 当前完整身份再次核验；旧actor/bound session撤销、旧CSRF403/旧generation409，无旧data |
| Q04 | TTL临界前后、主动撤权、logout，之后读业务/回执及重放旧token | 401/403按合同拒绝；绝对TTL不滑动，bound到期不晚于demo；logout不虚构COMMITTED恢复 |
| Q05 | 写缺Origin/错Origin/错CSRF；GET缺Origin并改变Host/FetchMetadata | 写403；GET只可信同源例外，same-site/cross-site不放行；不能信任任意转发Host |
| Q06 | V4 bearer改名commerceops_session请求旧/api/v1；篡改role/tenant/principal | 旧API401；strict额外字段422，无授权效果；私有bound bearer未发布 |
| Q07 | 控制操作同key同payload串行/并发及异payload | 同回执/一次效果，异文409；PG receipt/效果/审计同事务。浏览器不自动重发POST |
| Q08 | 真实create提交后仅丢body（cookie已应用） | GET current匹配creation_request_key、原key安全回执；不二次POST/新tenant |
| Q09 | create提交后丢header/cookie整体，保留原bootstrap | 300秒内仅原key最小COMMITTED/UNKNOWN；OWNER_RECOVERY_REQUIRED；无token/CSRF/tenant泄漏 |
| Q10 | bootstrap跨key/跨operation/过期、create重放写、丢失bootstrap | 拒绝探测/写；保留UNKNOWN，404/401不能推导回滚；不自动新空间 |
| Q11 | seed中途真实PG异常/rollback；核manifest固定日期/计数/六异常关系/hash | 初始化全回滚；两店引用一致；source各mode真实为合成，不声称六链可运行 |
| Q12 | 同reset key并发；reset与已发请求竞争；reset后再查原key/tombstone | 一次epoch推进；旧写不能进新epoch；A清业务但留receipt审计，B digest/count/epoch不变 |
| Q13 | DB不可读/COMMIT后ACK未知 | 503/server_time=null或传输UNKNOWN，不伪造DB时间/回滚/成功，不自动POST |
| Q14 | 5独立访客（不是5个tab），前3active，第4/5尝试 | 后两429+Retry-After，无挤掉前3；旧unknown创建仍占cap，限流不自动新建 |
| Q15 | A双tab延迟读后切persona/reset/logout；丢BC；hidden/offline→恢复 | 开始即清屏；旧context/request_seq不渲染；恢复先GET current，可见5秒核验失败清屏 |
| Q16 | 真实Web 1440/1280/390、200%缩放、Tab/Esc/focus/reduced-motion | 页面不横溢，modal focus约束/Esc回归/文字aria反馈；缩放不能只用viewport替代 |
| Q17 | cookie/响应/敏感context与缓存安全 | HttpOnly/SameSite/Path=/api/v4、TLS Secure及显式本地HTTP分记；no-store/Vary；token不入storage/log |
| Q18 | 确定性REJECTED429后，用户显式再次进入→GET bootstrap→新key POST；对照UNKNOWN不重启 | 已绑定旧bootstrap行/原key不可清空或改写；明确重新进入才签发新匿名owner，新key不因复用旧绑定而404；无额外成功tenant；RATE与CAP分记；active仍拒绝bootstrap |

Q03/Q11/Q12/Q13 的底层故障/旧actor需要 API owner 提供已审窄测试入口或真实 PG 操作。
不新增公开调试路由；PG管理员只改本批 owned fixture，HTTP始终用低权 runtime。
V4-0没有业务写路由，reset与旧业务写线性化用作者已审PG事务测试及负例复现，不擅自开放旧API。
Q07并发是服务端防重验证；正常浏览器在UNKNOWN时仍只安全GET。同key异文应隔离为独立
恶意请求 case，不能因为切persona后CSRF先拒绝就把幂等409判据标绿。

## 完整回归与证据口径

Root 在最终精确集成源码串行安排 `python -m scripts.check`、实际动态完整 integration
collection、两条 PG 分区及 `scripts.pg_ci_evidence` strict pairing。沿用原G1三项/G2六场景、
每命令300秒/清理/来源/工具/锁/完整集合要求，不在本切片调整共享 helper。
`719 = existing542 + phase3 177` 只是 M3历史基数；新增 `tests/v4/**` 后必须按实际collect
确定完整集合，核每节点归属与两个分区并集完整/交集0，不能手写719+N或漏掉新目录。
新QA目录的独立 HTTP场景不等同旧integration集合，不拿二者拼接为同一count。

旧Web/N01与对应M3日报/询单/copy回归、strict DTO/schema与路由优先级均保留；由Root分配
既有已审命令与新owned资源，QA不自行启动旧live harness（可能引用旧资产）。WEB新UI的
mock/合同测试只记该层，新V4全链须实际PG/API/Web。Full/Hosted分开填，失败/skip/unknown不抹除。

每次报告：source SHA/tree、合同hash、argv/命令、开始/结束UTC/elapsed、native exit、
selected/collected/call-pass/failed/skip、每case证据位置、PG事实、cleanup与保卷/删卷事实。
原始cookie/CSRF/凭据不入普通JSON/截图/仓库；公开证据仅保留安全ID和hash。
当前 actual token/cost `UNKNOWN`；真实PG/API/Web、Full、Hosted全为 `NOT_RUN`。
本次没有创建资源，cleanup `NOT_APPLICABLE_NO_RESOURCES_CREATED`；不进入V4-1。

## QA 第二切片：运行代码已准备，尚无服务运行证据

该节覆盖上一段“没有创建资源”的准备时点：本切片只创建并终止了进程单元测试的短命 Python
子进程，没有 PG/API/Web/浏览器/容器/卷。PG/API/Web、Full、Hosted 继续 `NOT_RUN`。

| 文件 | 已实现能力 | 运行前仍须核定 |
|---|---|---|
| `tests/e2e/v4/supervisor.py` | 固定api/web/pg/probe角色、独立进程组、显式env、新建0600日志、UTC+monotonic截止、watchdog、TERM→KILL/reap、writer先停/PG后停、无自动重启 | Root精确argv/env/对象；只管理自启进程，不替代容器/卷清理 |
| `tests/e2e/v4/http_probe.py` | 真httpx/CookieJar、loopback限制、禁代理/redirect/自动POST重试、7个明确场景入口、安全响应头/上下文核验、旧API改cookie401、persona旧CSRF/generation、同key并发reset | 已审adapter、初始空新库、真实HTTP/PG运行、未覆盖的Q矩阵专项夹具 |
| `tests/e2e/v4/pg_probe.py` | 真实psycopg只读事务、statement/lock timeout、prepared单参数查询、精确tenant快照/DB UTC/计数/hash | 精确schema的已审单SELECT与新owned connection；不自找DSN/读env/连旧库 |
| `tests/e2e/v4/validate_response.mjs`、`strict_response.py` | 现有锁定Ajv2020+formats校验冻结OpenAPI的operation/status response，未知status/extra/格式拒绝，不输出payload | adapter直接调用validate_response并绑定同一Budget；Node/依赖固定安装 |
| `tests/e2e/v4/adapter.py` | 唯一V4Adapter类型接缝：launch_spec、persona_ids、snapshot、validate_response | 目前只有Protocol，缺实现必须阻断，不能skip/fallback或猜业务配置 |

`run_scenario(scenario, api, origin, budget, adapter)` 支持 `lifecycle`、`capacity`、
`ack_body`、`ack_headers`、`security`、`same_key_reset`、`persona_stale`；每个场景要求
**独立初始空新owned库**，不能把多个场景串在cap3库里再删除tenant凑数。访客client在finally
关闭；transport/DB异常保持UNKNOWN并向外抛出，不执行后续业务写或自动重试。丢ACK方法是
对真实HTTP响应作测试端丢弃/还原原bootstrap jar，不制造成功JSON，不恢复明文bearer。

Root后续已审driver必须按以下顺序接线：preflight精确clean/source/window → Budget.bind →
新建Supervisor独占证据目录 → 已审foreground PG/API/Web argv/readiness → 将
`run_scenario`放在Supervisor管理的**独立probe子进程组**内执行 → 保存native exit →
`stop_writers()` → PG最终只读snapshot(final_collection=True) → `close_pg()` →
新owned对象独立cleanup核验。HTTP每次I/O timeout不是HTTP总时长保证，probe必须在该
supervisor子进程内，由watchdog为整个场景封顶，禁止直接在无父进程约束的Root中运行。

Supervisor不采纳PID、不搜索Docker、不停止未知容器；若PG通过Docker提供，精确资源owner
另交已审的创建/停止/保卷合同，不能把终止docker CLI当容器已停。PG进程角色只适合真正
foreground受管进程；缺容器cleanup实现则该资源路径仍阻断。readiness重试只允许已审的
有限只读启动检查，不能重试创建/persona/reset/logout或自动延长窗口。

后端一次性待接字段清单：API启用/可信Origin/local_http配置名与argv；最小显式env及
新凭据来源；迁移/seed初始化命令；两个预登记persona ID；新owned PG连接入口；返回
Snapshot七字段的只读SQL（digest排除采集时间，保留B业务/epoch/receipt/tombstone）；
低权ACL/旧bound session撤销的专项SQL；reset/seed rollback故障夹具。WEB待交：实际
启动argv/Origin、已审Playwright入口与新资源环境。以上不从作者WIP或旧私有配置读取。

纯验证命令是 `.venv/bin/python -m pytest -q tests/e2e/v4`，另运行该目录Ruff lint/format、
Mypy及 `python -m scripts.check_docs`。它仅签纯/进程/DTO契约，不计作HTTP/PG/E2E Gate。
首轮出现过pytest相对导入collection失败（exit2），补v4包入口后通过；首轮lint两项已修正。
Node缓存安装曾因复制的npm launcher找不到`../lib/cli.js`而exit1，改为固定Node执行同包
`lib/node_modules/npm/bin/npm-cli.js --prefix frontend ci --ignore-scripts --offline`
后exit0、41 packages安装，未改锁。这不是在线完整漏洞查询或scripts.check通过。

第二切片首次冻结为 `34e895eb1e873027b2201d7bd159d464200e39ae`；冻结复核实际
26pass/1fail、3.32s、native1（此前WIP同27项曾全通过）。失败为已退出leader的后代组清理，
补安全errno诊断后单项再次native1/0.11s，实际捕获 `PermissionError errno=1`。
具体平台根因仍UNKNOWN，不将先前27pass改写为冻结通过，也不忽略所有EPERM。

修正加入对**该自建process group**的独立 `/bin/ps -g <owned-pgid> -o stat=` 观察，
在清理截止内核无live writer；仅空组或全zombie可作为无活跃写入者事实，未知状态/观察失败/
活跃成员仍FAIL。信号错误保存在OwnedProcess.signal_errors，不因最终清理成功而丢弃。
SIGKILL后同样核组状态；日志finally关闭；某角色失败仍尝试清理其他自有角色，绝不扩到
其他进程组。此次并未证明平台EPERM根因已修复。定向修正验证1pass/0.80s/native0，随后
完整本目录29pass/4.11s/native0；含两条显式EPERM有/无独立清理证明的单元契约。

## Astra 05a 三项 P2 增量整改

只读报告来源：`a4ed08ff45b1116931784b6a344dd5d38fb448d6:docs/v4/review/QA_05a.md`，
结论0P1/3P2，尚未签ACCEPT_PREPARED_HARNESS。保留该审查与05a旧29项结果，不能用
旧测试抵本次源码发现。本次只改QA独占路径；后端设计只读精确 `c4c4840`，未读作者WIP。

- QA-01：串行capacity场景只接受429/CAPACITY_LIMIT和正整数秒Retry-After，RATE_LIMITED
  及缺失/零/负数/非法等待值均失败。新PG接口先核空库，再核三活跃tenant/三session/三份
  creation receipt；原三key逐一对应唯一receipt+两个create事件。后两容量拒绝无receipt，
  原三session仍同tenant/key、PG cohort仍3/3/3。它只签未来**串行cap3**，五并发竞争仍是
  独立NOT_RUN Gate，不将peer限流签为容量成功。
- QA-02：两个旧CSRF并发reset接受两个200且回执相同，或200与精确403/CSRF_INVALID；
  其他403/非成功组合不能通过，无成功观察保留UNKNOWN。GET current后原key GET回执，
  再用新CSRF显式对抗同key同body取原receipt、异body409/IDEMPOTENCY_CONFLICT；
  PG必须原key恰一receipt/一reset事件、tenant一致、当前epoch恰+1，重读current不再推进。
  这是显式安全实验，不是UNKNOWN后的客户端自动POST重试。
- QA-03：普通与bootstrap最小回执均核请求operation/key，最小分支只允许session_create。
  ACK-body恢复还要求COMMITTED并与PG唯一原key receipt ID/tenant一致；header整体丢失
  保持最小恢复分支，PG只在独立owned观察端核原key一receipt/两个create事件，不向API
  bootstrap返回tenant/token。schema-valid错误key/operation同样拒绝。

新增 `test_http_criteria.py` 20项离线判据验证，不发HTTP、不用mock transport、不连PG。
定向结果20pass/0.36s/native0；未重跑无改动的supervisor/strict旧29项。类型检查覆盖11个
源码文件。当前变更没有运行PG/API/Web、浏览器、Full或Hosted。

新增 `design_pg_adapter.py` 仅为已审c4表名/字段准备参数化只读SQL：tenant快照、DB活动
容量、operation/key回执与事件。它不连接、不加载DSN、不提供API配置/启动实现，不读取
token/CSRF/password/credential列；事务固定UTC并有statement/lock timeout。snapshot的
业务hash包含fixture/当前身份代际/shops/overlay digest/receipt/event，排除采集时间；
保留control receipt在该设计中承担去重tombstone，因此两count同源，无新造tombstone表。
该hash只覆盖明确选列，不宣称全组织ACL/credential所有表字节指纹；撤grant/旧actor专项
仍须真实已审实现和独立观察。SQL尚未在实际0024执行，必须核后端精确提交一致后才用。

单一V4Adapter现增加capacity_facts/operation_facts依赖，缺实现必须阻断，不能返回占位0。
API实际配置字段、启动argv/env、新owned连接方式和容器cleanup仍PENDING_OWNER_HANDOFF。
本次无新运行资源；先前工具copy/symlink原因已由Root确认并修复，原npm失败继续保留。

Q18为Root新登记的8API内细化，原c4设计对该GET复用分支尚未证明实现。后端交精确已审
细化commit后再接独立PG/API负例；WEB owner负责显式再次进入与UNKNOWN不自动调用的
浏览器验证。需要分别观察：第一次429是确定性REJECTED且原owner已绑定但未consumed；
用户显式GET得到新owner；旧行/旧key仍不可变且旧token仅保留原key最小回读；第二个新key
按当前真实限流/容量结果处理，无隐性新tenant；UNKNOWN不自动GET bootstrap/POST。
这里不将未来分支或未交SQL写为已实现，不用RATE_LIMITED代签CAPACITY_LIMIT。

## QA-04：原回执事件种类精确核验

只读增量报告 `8e9794ac7a57e9055153af39d4eca064da04472f:docs/v4/review/QA_05a.md`：
原QA-01/02/03在源码审查层关闭，新增QA-04 P2，暂未ACCEPT_PREPARED_HARNESS。
此次只修事件语义：OPERATION_SQL保留operation/key→receipt/tenant的参数化绑定，另返回
该receipt全部event_kind有序数组，不过滤期望kind、不DISTINCT、不丢重复或额外事件。
适配要求数组完整且与count相等；ACK创建及capacity原三key必须精确含一次
demo.session_created和一次demo.seed_materialized，reset必须仅一次demo.reset_committed。
顺序不影响判据，遗漏/重复/额外/相同数量但错误种类均失败。

新增 `test_event_criteria.py`：15项定向离线测试，15pass/0.03s/native0；Ruff通过，Mypy
12源码文件通过。没有重跑未改的旧29项和上一批20项。SQL/PG/API/Web/浏览器/Full/Hosted
仍NOT_RUN，实际适配继续等后端精确提交与Root资源窗口；本修正待Astra复审。
