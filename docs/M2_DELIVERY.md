# M2 交付与证据地图

本文件属于 [Issue49](https://github.com/aning0922/commerceops-agent/issues/49) 的 M2 持续交付。来源展示从已审 `5ac0c2f` 接续；创建与 N01 只消费已审 `3af5308f69dd54cada81b30c8e7e002c2ef5cc51` 的公开合同，保持既有 18 页风格，不增加视觉批次。本次技术/业务实证按下文范围核收；最终文档、精确 CI、main、合后 CI 及正式结案以 [固定权威回执](https://github.com/aning0922/commerceops-agent/issues/49#issuecomment-6430237354)的后续实际更新为准，不预填未来 SHA 或 CI 成功。

## 当前来源与结案边界（2026-10-27）

本次文档接续只消费已提交候选 `8ad436595794ef83f3a99bc80bd9ad4948b7117e` / tree `ea86b637190ec0ec42da771638a6c72b2853e82b` 的公开父入口、helper 与合同。Root 已回执该候选原独审通过，以及完整本地检查 native0 / 226.945秒、2778 offline 通过 / 590 integration 排除、398文件typecheck与依赖审计0漏洞；这些不是 590 PG 实跑或新 Hosted CI。B consumer `27af9c3` 已正常集成，允许同一决定的异步 resume 推进，严格保留稳定字段和 UNKNOWN 边界。

Root 已核收较早 `26c` / c6 样本的实际正向链：真实本地合成 Woo、source consumer、官方待审批 checkpoint、native dump、空白新库 restore、原审批与十次同字节重放，以及停写后 PG 唯一 1 execution / 4 items / 219 units。该 run 随后在撤权负例期望 404、实际 HTTP403 处失败；响应 error code 为 NOT_CAPTURED，expired 未运行。正向范围已独审核收，整体 run 仍 failed，不能拼签完整 M2。

当前 `8ad43659` / e890 的完整真实 owned Gate 已获 Root 与原 Reviewer 核收，具体正向、两负例及清理范围见下节。当前0018本机新数据 clean Compose 也已核收，见 [Mock装配与边界](M1_OFFLINE_COMPOSE.md#当前-0018-mock-装配与公开复现2026-10-27)。最终文档、精确 CI/main/合后 CI 与正式 M2 结案仍以固定权威回执的后续实际结果为准；两次实际 Gate 不预签这些独立项。

A 是本次实际运行的唯一资源 owner，父入口直接调用 B consumer；B 不另开 consumer、浏览器或服务，也不接触运行凭据。此文档不登记运行中的微步骤或猜测成功。完整阶段仍 pending，不预填 main 或合后 SHA。

## 已核实际窗口：8ad / e890

精确 source `8ad436595794ef83f3a99bc80bd9ad4948b7117e` / tree `ea86b637190ec0ec42da771638a6c72b2853e82b`；运行 `e89054e7-079a-43b3-a218-3300ebd1cef7`，UTC 2026-10-26 23:12:14.944768 → 23:28:13.904003（台北 2026-10-27）。父 native0、958.959235 秒、logical passed、cleanup confirmed；75 条命令 native0、均已回收、无 timeout。机器运行时长不计作 Agent 有效分钟或真人操作时长。

| 证据范围 | 已核实际结论 | 范围限制 |
| --- | --- | --- |
| 来源与正向消费 | 新自有本地合成 Woo 实际 HTTP probe MATCHED / complete、4 SKU；source 浏览器建立原待审批及官方 checkpoint | 是真实本地 Woo/PG/浏览器/运行时链，不是生产店、真人或真实飞书平台验收 |
| 新库恢复 | 停 writers 后 native dump、目标原先空白、原生 restore；完整快照与官方 checkpoint 一致 | 同版新自有库/卷恢复，不替代旧 checkpoint→新依赖兼容、异机灾备或 RPO/RTO |
| 原审批与幂等 | 同一原审批明确批准一次、原 decision 字节重放十次；PG 唯一 1 execution、4 items、219 units、1 decision receipt、1 consumed resume | consumed 不单独签执行成功；执行/items 另有读回及停写后 PG 事实 |
| 撤权负例 | 403 / ACCESS_DENIED；该 clone 零决定/resume/execution/items | 只撤销独立负例库的 grant，正向原对象不受破坏 |
| 原期限负例 | 真实原 expiry 之后 410 / APPROVAL_EXPIRED；该 clone 零决定/resume/execution/items，原 nonce/expiry 未改 | 没有改时钟或延长 TTL，也没有换键补写 |
| 最终清理 | 四个 PG project 与 Woo project 容器/网络均 0，7 端口关闭，10 个登记 PID absent，6 卷保留 | 本次 scoped 资源实际结果，不是全机器无资源；旧失败原件与卷继续保留 |

安全总索引 `M2-8AD-E890-FULL-RUN-INDEX.safe.json` 的 SHA256 为 `c128a20e86d45f4eacf826bf95e8e42fb686d52c2e1fa8bab0ee66dfec1a9c8a`，包含 129 个原件引用；Root 独立 proof SHA256 为 `5ec89f65b372495f1051142cc81bb4815a8eefab6e5a02c6b4e189dfdaf59470`。B 校验并消费总索引，不展开 private 原件；各原件核收以 Root/Reviewer 为准。安全材料只记绑定和摘要，凭据、请求正文、nonce、cookie 与 dump 不进入公开文档。

## 当前可展示的事实

真实会话和传输方式与业务数据来源分别展示。报告来源只读取当前冻结报告的 `facts.source.provenance.source_kind`：`mock` 显示“Mock 样本”，`woocommerce_test` 显示“Woo 测试店（只读）”，没有当前报告或无法识别时显示“未报告”。登录、`local_http`、Worker 配置、P2 原始报告/P3 重观测均不能代替商业来源。

现有报告完整性与来源采集完整性继续分别展示；采集读齐不表示库存或在途已知，也不授执行权。SKU 保留原始未知库存、零/负库存、`inbound_units=null`、估算有效值、质量标志、硬阻断和当前版本假设集合。共享池需人工核对，不能按变体重复分配。页面不计算权威建议，不将原始在途改写为已知零。

离线 Mock 页面及注入合同响应仍明确标注没有真实身份/API/PG/Woo。展示层合成 DTO 中的 Woo 来源标签只验证页面消费合同，不算真实 Woo API 或业务接线证据。

## 范围与待完成项

| 项目 | 本批范围 / 状态 | 后续验收依据 |
| --- | --- | --- |
| 来源与质量展示 | 本批最小展示接线；测试结果见冻结提交交接，不把作者自检当独审 | 严格 DTO、页面回归及精确源码独审 |
| 创建与 N01 | B `85f477c`：75 契约、9 创建组件、3 来源展示、22 共享页面回归通过；Root 已回执原 Reviewer 无 P1/P2。两处公开 scanner 命中已纳入 A 冻结的精确绑定；e890 正向浏览器链已核收；局部历史测试数不替代该实际链 | 稳定后端、精确集成源码及同源 API/PG/Woo 业务链 |
| Woo 对账 | 沿用独立 [实验环境](WOO_LOCAL_LAB.md) 与 [A/B 输入合同](contracts/p5-woo-readonly-v1.md)；实际 adapter probe 由 A/Root 单独核收 | 同源真实只读 API、独立 EXPECTED、完整性与质量结果 |
| 备份还原后待审批续跑 | e890 正向新库恢复、原待审批续跑及两负例已核收，核心入口由 A 负责 | [恢复交付合同](M2_BACKUP_RESTORE.md)、新自有源库和新目标库的实际证据 |
| AC01–11 汇总 | 本次Woo/恢复/两负例与当前Compose已核；正式AC汇总由固定权威回执收口 | 不用页面 Mock 或旧 CI 抵扣新业务/恢复证据 |
| M2 独审、精确 CI、main、合后 CI | 源码与两实际证据包已独审；最终文档/精确CI/main/合后仍待固定权威回执 | Root 的实际结案回执；不自动进入 M3 |

## 文件所有权与运行边界

B 负责现有 Web 来源/质量披露、对应契约与页面测试、本文件及恢复说明。A 负责业务来源选择、collector/Worker/Graph 接线、公开 schema 源、权限与恢复核心、根 Compose/装配、锁和 CI；B 只消费已提交且已审的稳定合同。Woo 必须有当前所选 operator 店铺的合法、已启用 capability 和来源版本；缺失、禁用或不一致均关闭创建，不回退 Mock。只有所选店铺明确返回 Mock 时保留旧流。

验证页面可使用无服务端口的 headless 组件样例，结果只能标展示层合成测试。真正 API/Web/PG 联测由 Root 串行登记新自有资源、绝对截止和清理，A 独占父生命周期；不读取或复用旧 P4、QuizForge、Penpot 的私配或卷。

## 最小演示与证据包

演示只需串起：来源报告与完整质量披露、真实 Woo 对账回执、还原前待审批记录、还原后同一绑定、一次明确续跑及原键重放。记录 task/plan/version/hash/checkpoint 绑定、角色/期限/新鲜度复核、内部执行唯一性、原生退出和资源清理。原 M1 已核场景按影响复用，无需为本展示接线重录全部流程。

公开材料只含脱敏结果、准确证据类型、源码与工具版本、命令/退出码和摘要。凭据、cookie、dump、原响应与私有运行配置不入 Git；自动化截图不称真人连续操作，未执行处保持 pending。当前功能展示不代表生产、真实采购/入库或 Woo 写权限。

## Woo 创建与 N01 消费合同

客户端分别读取 `/api/v1/config?shop_id=...`；会话级 Mock 配置不代替所选店铺的来源。Woo 请求只包含 `source_mode=woocommerce_test`、`source_config_version`、L/R/S，不能加入 Mock fixture、时间、URL 或私有 binding。页面只是创建资格提示，服务端在每次写入重新核权限、当前版本及可信来源。

Woo N01 消费 `p5-n01-web-v1`；旧 Mock 仍消费 `p4-n01-web-v1`，外层均为 `p3-web-v1`。候选必须绑定所选店铺、来源版本及原始 Unicode code-point span。缺项保持空白，人工补参保留原始澄清记录，不能把示例改称服务端 ready。用户依次检查原句、明确确认完整参数，再准备和显式提交原请求；预检查不创建任务、不采集报告、不调用模型。来源重读或输入改变使尚未准备的确认失效，迟到结果不能复活旧确认。

一旦准备原请求，原 key 和字节保持不变。来源刷新、pending 和 UNKNOWN 都不重挂提交组件、不换键、不自动登录或重发。UNKNOWN 先读取原键回执；暂无回执不证明失败。`from_report` 继续使用原 task/report/snapshot/facts_hash 引用，不引入当前 Woo 参数。

生成器按 P3 → P4 N01 → P5 的顺序消费 `docs/contracts` 中公开冻结合同，同名定义由后者覆盖，得到 22 paths / 94 schemas / 23 operations / 零悬空引用。原 P3/P4 生成文件保持不变；P5 生成结果独立保存，生产解码仍拒绝 extra、coercion 和默认填充。复现命令：

```sh
node frontend/tooling/sync-p5-schema.mjs --openapi
npm exec --yes --package openapi-typescript@7.13.0 --package typescript@5.9.3 -- openapi-typescript .audit/p5-openapi.generated.json --immutable -o frontend/lib/p5-types.generated.ts
npm --prefix frontend run check:read-schema
npm --prefix frontend run typecheck
```

沿用既有临时类型生成器版本，未新增前端依赖或修改 lock；临时生成器没有单独 transitive lock，不将其称为生产锁保障。Node/npm 使用仓库要求的 24.21.0/11.19.0。生成类型可输出到 ignored `.audit` 后逐字节比较。

离线检查可运行：

```sh
frontend/node_modules/.bin/playwright test --config frontend/playwright.contract.config.ts --reporter=list
frontend/node_modules/.bin/playwright test --config tests/e2e/web/phase5/creation-playwright.config.ts
frontend/node_modules/.bin/playwright test --config tests/e2e/web/phase5/playwright.config.ts
npm --prefix frontend run build
```

新增创建组件用 `about:blank` 和内存 transport，测试夹具显式注入合成 UUID；它没有实际会话、API、PG、Woo 或模型。390px/键盘结果仅代表自动化组件证据，不能替代真人验收。开发失败、修正及最终原生退出分别保留在 ignored 私有运行目录，最终交接按精确冻结提交登记。该段只记录85f历史组件范围；后续正式业务链由 A 父入口实际执行，结果见上文8ad/e890，不把组件测试算为实际链。

## 当前证据分层与缺项

下表记录证据能支持的结论；测试数不跨层累加为“完整 M2 通过”。历史创建组件基线为 B `85f477c46d5348a9e3667f606d273eff3cbaaa32` / tree `97189ab748e316fb48e82fe5f8e1e2e11a70873f`；正式8ad/e890与当前Mock Compose分别按上文和各自索引的精确SHA/tree记账。最终集成源码及结案以固定权威回执后续实际记录为准。

| 层次 | 当前事实 | 不能代替的证据 |
| --- | --- | --- |
| 公开合同与消费 | 已审 A `3af5308` 的 22 paths / 94 schemas / 23 operations；B 严格生成和消费，原 P3/P4 文件保留 | 已修后端的真实来源绑定、截止与权限行为 |
| B 离线契约/组件 | 75/9/3/22 全部通过，类型/生产构建/再生成逐字节比较/115 份文档检查通过；Root 回执 B 原独审无 P1/P2 | 真实身份、API、PG、Woo、Worker 执行或真人验收 |
| 独立 Woo lab | positive 新店原生对象与两轮 verify 已记录；EXPECTED 为 4/4/0/4，独立规则金标 Q219 | adapter 完整对账、真实业务报告、四项确认或内部项落库 |
| 后端实际 PG、Fake HTTP | A/Root 单独核收来源、审批、幂等及兼容证据；Fake HTTP 必须显式标明 | 实际 Woo HTTP 与 positive 业务金标 |
| 正式 Woo/API/PG/Web | 8ad/e890 完整本地合成 Woo + 真实 PG/Web 链已核收 | 不从前三层推定通过 |
| 新卷还原/待审批续跑 | e890 正向及撤权/真实到期负例已核收；见 [还原合同](M2_BACKUP_RESTORE.md) | 保卷重启、旧 G2、当前版本新写新读 |
| 当前0018 Mock Compose | 8ad/1a7c本机新项目新数据，Mock20/2000、T6v2、原键/同父Worker与APIWeb恢复、真实隐藏Web只读及清理已核；见 [Compose](M1_OFFLINE_COMPOSE.md) | 新机器全冷缓存、真实Woo/Base或真人操作 |
| 精确集成 CI/main/合后 CI | pending Root 正式回执 | 旧提交五绿、作者自检或已 push |

历史 B `85f477c` 冻结时 scanner exit 1 的两条公开命中及 `d42d094` consumer 八条公开命中原始记录保留。A 的冻结入口已包含固定 source/path/整行 SHA/位置同时匹配的精确绑定，并对 `27af9c3` 保持原八行 literal 摘要、重绑 source 与位置；这不删除原发现、不扩大规则，也不自行证明最终集成源码扫描或 Hosted CI 成功，最终退出仍随同源索引核收。7 份早期 lab 日志非敏感字节不可恢复的历史限制按 [lab 原记录](WOO_LOCAL_LAB.md) 保留。

## 命令使用顺序

从目标 checkout 根目录执行，并先按 [开发说明](DEVELOPMENT.md) 使用仓库固定 Python/uv/Node/npm。依赖准备命令会安装工具或依赖；以下前端检查不启动业务服务：

```sh
export PATH="$PWD/.tools/node/bin:$PATH"
npm --prefix frontend run check:toolchain
npm --prefix frontend run check:read-schema
npm --prefix frontend run typecheck
frontend/node_modules/.bin/playwright test --config frontend/playwright.contract.config.ts --reporter=list
frontend/node_modules/.bin/playwright test --config tests/e2e/web/phase5/creation-playwright.config.ts
frontend/node_modules/.bin/playwright test --config tests/e2e/web/phase5/playwright.config.ts
npm --prefix frontend run build
uv run --frozen python -m scripts.check_docs
uv run --frozen python -m scripts.scan_secrets
```

不要用 `npm audit fix`、改 lock 或扩大 scanner 例外来替代失败处理。组件输出位于 ignored `runtime/m2-web-creation` 与 `runtime/m2-web-source`；重复开发尝试先保留原结果，再写新一次结果。检查命令的成功不表示真实验收窗口已获准。

[Woo lab 命令](WOO_LOCAL_LAB.md) 已存在，`prepare/build/verify/serve/stop` 均只作用于明确登记的新自有目录。正式业务前必须由 A 交接 canonical organization/shop、不可变 binding/版本与私有 pin；旧 `synthetic-woo-positive` 实例不能改绑成业务 UUID。Root 登记资源和截止之后，adapter 对账可使用既有入口；下列三个绝对路径变量由该次私有交接提供，内容不写入命令参数：

```sh
uv run --frozen python -m scripts.woo_readonly_probe \
  --config "$M2_WOO_CONFIG_PATH" \
  --expected "$M2_WOO_EXPECTED_PATH" \
  --output "$M2_WOO_OUTPUT_PATH"
```

这条命令实际读取 Woo；e890 的实际对账 MATCHED 已核收，不能据此认定任意新配置或新窗口也已通过；输出必须是新路径，不能覆盖已有对账原件。只在同一新 owned 窗口内执行，不因为路径变量存在就启动服务或访问旧资产。

`run_live_batches.py`、`run_c09_n01.py` 及 live config 的旧 Mock 分支仍保持原种子、owner 与输出范围，不能直接改绑为 M2 Woo。正式 M2 已有独立 `p5-m2-live` config 分支与下文固定 source/restored argv，由公开父入口 `scripts.m2_owned` 生成不可变私有输入、直接调用并 wait/reap。其 `prepare/run` 命令、四个新库与备份顺序见 [恢复入口](M2_BACKUP_RESTORE.md#稳定入口与当前可执行边界)；控制流已入 Git，无需旧私有 launcher，不另建父编排。入口存在与获准运行均不代替实际结果。

## 真实 Web 最小验证顺序与结果范围

开始前，Root 交接精确 checkout/SHA/tree/build、owner/新资源、UTC 起止及清理预留、API/Web origins 与监听 PID、canonical org/shop/来源版本、私有账号路径、正向 EXPECTED/金标摘要、允许的业务写入数、现有 PG 只读采集入口和最终清理责任。B consumer 仅由 A 父入口直接调用，操作已绑定的 headless 页面与公开 API；A 采集 PG/Worker 证据和子进程退出，运行中不靠聊天接力。密码、cookie、CSRF、nonce、原请求正文和原始 DB/平台标识只留受保护原件，公开索引只留脱敏绑定与摘要。不要以截图或浏览器 POST 计数替代 PG 提交事实。

| 顺序 | 最小操作与复用依据 | 必须取得的结果 | 当前状态 |
| --- | --- | --- | --- |
| 0 准入与只读基线 | 复用 `owned-listeners.ts` 和 live read 的 build/PID/origin、当前角色/店铺校验；A 提供业务计数/摘要基线 | 来源为服务端 Woo 配置，operator/approver 分工明确；无自动业务 POST | e890 已核收 |
| 1 来源、N01 与原创建 | Woo p5 schema 的来源/窗口/范围、缺参到明确确认；只在 A 矩阵分配 B 创建额度时，固定 L3/R7/S2 后准备并显式发送一次 | N01 不传 fixture、不访问 Woo、不产生 task/job/plan/approval/outbox/model；创建才产生原键唯一受理结果及对应分析/补货任务，不预设“一个 task 行” | e890 已核收 |
| 2 报告与四 SKU | 读取 A 交接原样本或上一步明确创建的报告/计划，复用 read/report 和来源展示断言 | 4 SKU/4 order lines/0 refunds/4 inventories；gross147/CNY994/tax0、Q100/40/60/19 总219；来源完整与库存/在途质量独立披露 | e890 已核收 |
| 3 还原后原待审批 | A 按 [还原合同](M2_BACKUP_RESTORE.md) 停 writers、dump/restore；B 恢复后重新登录读取原 tuple/全部披露，按 A 矩阵执行唯一批准或只读已有回执 | 原来源/报告/待审批 tuple 与 PG/checkpoint 对齐；四项在途仍 raw null，四个当前版本确认键完整且无默认勾选。只有分配 B 的当前有效批准操作才由 B 明确提交一次；同一 execution/每 SKU 唯一内部项及原键零新增由 A 采集 | e890 已核收 |
| 4 收尾与封包 | 复用既有 finally 清理与原生退出采集；A/Root 核各自进程与资源 | 浏览器上下文关闭、API/Web/Worker 停止/reap/OS absent、容器/网络/监听核实，源/目标卷保留；失败/UNKNOWN 单列 | e890 已核收 |

A 的样本矩阵必须在开始前列明每个原任务当前状态、创建/批准是否已发生，以及 B 可以执行的唯一动作。若 A 已创建或已批准，B 只读该对象和原回执，不再创建替代任务或重复批准；“已有批准回执可读”不能写成“本次浏览器实际批准”。正常报告与待审批恢复可使用同一正向样本，先保留 awaiting_approval 再备份；B 不先批准该样本再把它称为待审批还原。

UNKNOWN、受控 ACK 丢失、同字节重放、不同内容冲突、权限和窄屏优先复用原有定向契约/组件及同冻结 A 的实际验证，明确其各自证据层级。本次最小 UI 顺序不自动新增这些写入或故障注入；如集成出现新风险，Root 再在原矩阵和预算内安排必要增量。受控 ACK 丢失必须标明故障注入，实际 PG 提交与只读恢复不能仅从浏览器行为推定。

B consumer 已按显式资源输入和 M2 来源断言冻结，不 seed、不管理 PG、不另建测试框架或父编排。正式 argv 与专属输出见下节，由 A 父入口直接调用；本次文档准备没有执行真实操作。

每一项分别记录源码/样本、实际开始结束、选中节点/预期分母、原生退出、必要业务计数/摘要及清理事实。只运行某个尾段时保留前段失败并标明分段结果；没有执行的操作保持 pending。真实 Web 结果只代表自动浏览器验收，真人体验另记。

## 已冻结接口下的 M2 consumer

B consumer 使用 [机器接口](contracts/p5-m2-live-resource-v1.md) 的五个不可变私有输入，两个阶段各自目录0700、文件0600。以下 argv 由 A 的原受限入口以同一最终 checkout 的 `frontend` 为 cwd 直接调用；三个现有环境变量为 `COMMERCEOPS_WEB_BATCH=p5-m2-live`、本阶段 `COMMERCEOPS_B02_PRIVATE_DIR` 和 `COMMERCEOPS_LIVE_WEB_URL`。这些固定 argv 已由 e890 的 A 父入口实际调用；单独复制命令仍不授权另开资源或重复原审批。

```sh
npm exec -- playwright test --config playwright.live.config.ts --grep 'M2 source$'
npm exec -- playwright test --config playwright.live.config.ts --grep 'M2 restored$'
```

原带前导 `^` 的 grep 在实际 `--list` 中选中零测试，开发失败保留。Root 已裁决只去该前导符；M2 config 只选择 `m2.spec.ts`，两个修正命令分别实际选中一例、retries=0，不扩大阶段范围。source 只接受 `source_ready`，restored 只接受 `restored_pending_verified`；选错阶段在登录和业务请求前失败。原 Mock live 配置及其四类 reporter/结果保持原分支。

每段上限240秒，并核总stop减180秒清理预留。source首次Create前原approval尚不存在，`original_expires_at=null`合法，但仍须在consumer_stop前留60秒。restored启动须原expiry至少余300秒，批准及每次重放前再次核真实API原expiry和60秒写入余量。输入、FileRef字节、当前源码/tree/build与独占listener/PID不符则停止，不能以模板或端口探测代签。

source通过真实Web完成N01、参数明确确认、原请求准备和唯一Create；在原POST发送前用wx保存并fsync实际UTF-8 JSON字节。随后从实际receipt读同一task/report/plan，按logical_key与原seed/EXPECTED/金标逐项核四SKU、Q219、未知在途与完整四假设；当前approver只读原审批，source不批准。source-observed供A在子进程退出后核PG并生成canonical facts，consumer不等待运行中补写输入。合法pending审批始终先要求can_decide=true、有效nonce与disabled_reasons=[]；仅ready_at=null时，才在原consumer_stop内以当前approver会话和同一task/plan绑定做只读轮询，始终保留60秒；can_decide=false即使伴随null ready_at/nonce与NOT_DECIDABLE也立即拒绝；401/403、权限或绑定失效、终态、冲突立即退出。operator与approver均可读审批，创建能力按角色区分，读能力不代替当前can_decide授权。

restored用新context分别按当前operator/approver身份登录，读回同一原tuple/期限与复制原件。四个假设无默认勾选，明确确认后只准备和批准一次；成功后从同一原始decision文件读相同字节做合同指定的十次技术重放。每次必须duplicate=true且全部稳定决定字段一致；仅server_time/trace_id/duplicate及独立的resume_state可变化。resume只允许waiting_checkpoint→queued→consumed的非回退推进，并以最近一次confirmed replay为比较基线；consumed仅代表异步决定投递，不代表内部执行完成。任一真正不明立即停止POST，只GET原key一次后退出，不换键或自动重试。然后只读核同一execution及四个唯一SKU内部项的数量，总219；这不代替A的PG唯一性/checkpoint核账。报告DTO不含金额/退款汇总，consumer不填写对应通过项。

明确拒绝记录rejected；UNKNOWN保留原POST原件，最多GET原key一次并另存lookup，即使查到回执，本段逻辑仍unknown且非0退出，不换键/重发。各阶段只wx写机器合同允许的9/21个输出basename。`source-results.safe.json`、`restored-results.safe.json`只含逻辑结果、固定检查项、原件引用及安全码；实际native exit/reap与资源关闭由A父进程独立记录。

source固定检查项为admission、operator_identity、woo_n01、explicit_create、source_gold、pending_approval_readonly；restored为admission、operator_identity、restored_binding、explicit_decision、ten_original_byte_replays、execution_readback。每项分别标passed/failed/not_run；缺项不能计通过。关闭trace/video/HAR/自动截图；M2 reporter不复制原错误、stdout、步骤或DOM。Playwright仅技术性last-run目录放ignored `.audit/m2-live-pw`，不写进phase目录的业务原件集合；用例自行关闭context后才返回，A负责整个子树有界停止。

本批没有真实PG/API/Woo consumer运行；离线合同检查、类型/构建、精确源码独审、最终实际资源验收与CI分别记录。原No tests found及其他开发失败保留，不能将后续通过改写成首轮全绿。

## 历史失败与源码对应边界

父入口早期三处工具 P2、collector 字段误读、组合中途失败和后续未跑节点均按原记录保留；独审关闭不回填旧运行成功。历史 a1f Hosted CI 的迁移用例失败与 A 的后续新 owned 定位修正分别记账；8ad 的完整本地2778/590 excluded检查通过仍不构成修后新 Hosted 通过回执；不能用本地定向或完整检查替代最终 CI。

W01 的原文本副本与 START 摘要吻合，其与后续冻结文件的函数签名换行差异虽 AST 一致，仍不是同字节源码；保留原件、精确 diff 与 AST 摘要。该历史样本的实际 PG + ASGI + Fake Woo HTTP 层不能升级为实际 Woo HTTP 或 dump/restore。早期 lab 七份日志的非敏感原始字节丢失限制继续保留，不宣称日志完整恢复。

较早三次实际失败分别为公开 lab CLI 调用错误、父发起 Web TERM 的143退出误分类、以及 consumer 将动态 resume_state 当不可变字段；原 run/once 均保持失败，不重开旧任务补验。第三次首次决定 queued、首条 replay consumed 的真实差异触发 UNKNOWN，只 GET 原键一次后停止，后续九条 replay 与最终执行数量当时 UNKNOWN；其后 c6 新正例不能回填该旧样本的结果。c6 本身又在撤权负例失败，error code 未捕获与 expired 未跑继续保留；修正后目标合同为当前权限403/ACCESS_DENIED、真实到期410/APPROVAL_EXPIRED，两者不能由新静态代码推断旧 body。
