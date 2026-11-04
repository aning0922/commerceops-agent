# V4-1 本地演示复现说明草案

日期：2026-11-04，Asia/Taipei。当前代码 `261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e` / tree
`34da95131e04d7360ea8aa5250ea40215bcb0713`。状态：**LOCAL_STAGE_GATE_ACCEPTED**。
同源受影响检查与Mock33通过，Root转交r10两spec/consumer/SQL/closure实际完成；
AI工程视觉40原图无P1/P2，Main最终runtime独审4e4741ad已核收，用户人工视觉审批NOT_RUN。
没有持续有效URL，所有临时服务已关闭。本说明不授权重开旧案或声明产品发布。
需要再次演示时，Root必须给新source/tree核对、新镜像/资源/私配/once与绝对UTC，不能沿用历史窗口。


本地阶段 **V41-01–06 已完成并核收**，仅限合成owned环境与原合同受控范围。最终runtime独审
`4e4741ad56e5ee8d3a22bc9f4ac6564715d92955` / tree `85f0293eb07d3d648949df47674d7965c6294f18`，
[正式原件审查](https://github.com/aning0922/commerceops-agent/blob/4e4741ad56e5ee8d3a22bc9f4ac6564715d92955/docs/v4/v4-1/reviews/FINAL_RUNTIME_R10.md)采用该文件后续“完整实际运行追加核收”段；早期build-only/pending原文保留其时点。
r10同261/imagee834：2spec、11keys（10mobile子集）、4preview、7receipt/event、26当前effects及
2个历史替换tag分记，最终SQL0；source/tools与唯一允许next-env生成差异已核。原API清理130、
execution summary NOT_WRITTEN、Native browser exit NOT_EXPOSED、human审批NOT_RUN不改写。
旧4fec Full/e7 FullPG/54ab HTTP继续只属各自SHA；阶段接受不等于99功能、66页面、真机触摸、
外部业务、Hosted或生产发布通过，V4-2 NOT_STARTED。

## 当前证据与演示边界

- 四个有限真实 HTTP 场景已独立核收：同源看板、商品订单、CSV、XLSX，详见
  [54ab 四案核收](../reviews/HTTP54AB_FOUR_CASES.md)。它们证明各自冻结源及窗口，不能替代
  本文基线或后续组合的浏览器与 Full 验收。
- 完整工程检查在 source `4fec4a7416d7b9434d979f461d5da78508cfb850` 通过，详见
  [独审](../reviews/ENGINEERING_4fec4a7_R3.md)；仅签该源码，不代签新浏览器源码。
- FullPG 两线在 source `e7aeeca90e98cc4af5b5f8f8ba0faddd33182bd6` 严格配对：596 + 177，
  并集 773、交集 0；详见 [最终配对独审](../reviews/PG_PAIR_e7ae_FINAL.md)。该结论只属 e7，
  不代签其他源码或浏览器。
- 当前261批量/真实移动端/Native与父收验已实际运行，最终独审4e4741ad已核收；不能说旧Full已在新SHA重跑或实体手机/touch已验。
  相对eb30实际12代码路径与4fec/e7复用边界见 [最终矩阵](FINAL_GATE_MATRIX.md)。
- 原browser r8 source `eb30d7b7ad26da95dcf1c03ea55c5b424fbd536d` 业务单项10120ms通过，
  Shell Native在首张PNG前TimeoutError，具体原await未捕获；整案failed_closed，lateACK未到。
  新Native源码的阶段诊断不是历史根因证明，也不把超时修成通过。
- 原batch Mock r1 source `5acf03ae30807c160aa110035127a4e308e95da9` 实际1PASS/1FAIL/31NOT_RUN，
  原route时间线UNKNOWN；[原件](../../acceptance/v4-1/UI_MOCK_BATCH_R1.json)保留。
  原Mock r1–r3全部保留；261同源Mock33已通过。r9双spec通过但parent1的原失败保留，API计数权威校正不是伪造公开计数或改旧native。r10真实执行已获Main最终独审4e4741ad核收，AI视觉已核，人工审批NOT_RUN。
- 既有运行案均已关闭。本文只提供路由和新窗口中的 URL 生成方式，不承诺历史 URL 可用。
- 所有演示数据均为合成数据。飞书、Woo、真实模型／embedding 和外部业务调用保持关闭；
  Copilot 显示“模型未启用”，规则洞察不冒充模型回答。这里的本机 API HTTP、PG 和浏览器
  可以是真实进程；这不代表连接了真实商店、真实客户或生产平台。

## 页面与操作入口

新案通过启动及归属校验后，前端基址由该案 `web_port` 产生：
`http://127.0.0.1:<本案web_port>`。API 基址同理由 `api_port` 产生。
端口是 Root 新案参数，不是本文固定值；完整 URL 是该基址加下列路径。

先打开 `/v4`，点击“一键体验”，建立当前访客自己的演示空间；在“店铺”中明确选择当前
服务端授予的店铺。UI 角色选项不授予权限，`restricted_admin` 没有默认业务店铺。
不同访客、tenant/shop、身份代次和 reset epoch 的数据与请求键不能混用。

### 14 个导航项

| 导航 | 路由 | 本期含义 |
| --- | --- | --- |
| 经营驾驶舱 | `/v4/dashboard` | 已接业务视图，仍需当前会话和店铺授权 |
| AI智能工作台 | `/v4/ai` | 未来规划入口，业务未开放 |
| 经营分析中心 | `/v4/analytics` | 未来规划入口，业务未开放 |
| 商品中心 | `/v4/products` | 已接商品业务视图 |
| 订单中心 | `/v4/orders` | 已接订单业务视图 |
| 库存中心 | `/v4/inventory` | 未来规划入口，业务未开放 |
| 采购供应商 | `/v4/suppliers` | 未来规划入口，业务未开放 |
| 客户与售后 | `/v4/customers` | 未来规划入口，业务未开放 |
| 智能客服 | `/v4/support/inbox` | 未来规划入口，业务未开放 |
| 营销中心 | `/v4/marketing` | 未来规划入口，业务未开放 |
| 自动化中心 | `/v4/automations` | 未来规划入口，业务未开放 |
| 知识中心 | `/v4/knowledge` | 未来规划入口，业务未开放 |
| 审批与任务 | `/v4/work/todos` | 未来规划入口，业务未开放 |
| 数据与系统管理 | `/v4/settings/demo` | 演示身份／重置／退出控制，不是外部系统管理能力 |

导航可见、可点击或能返回页面，不构成该规划类别已交付业务的证明。

### 本期 12 个业务视图

| 视图 | 路径 | 复现内容 |
| --- | --- | --- |
| 经营首页 | `/v4/dashboard` | 当前授权店铺的指标、期间、趋势、来源与未知原因 |
| AI经营洞察 | `/v4/insights` | 同源确定性规则结果，模型未启用 |
| 指标明细钻取 | `/v4/dashboard/drilldown` | 从指标操作进入同期间的授权明细 |
| 商品列表 | `/v4/products` | 搜索、筛选、稳定分页、CSV 导出 |
| 商品详情 | `/v4/products/:productId` | 从当前列表取得真实 UUID，查看 SKU／来源／关联订单 |
| SKU规格 | `/v4/products/variants` | 当前有效商品 SKU 与库存未知状态 |
| 分类标签 | `/v4/products/categories` | 当前演示覆盖层标签读写 |
| 商品导入 | `/v4/products/import` | CSV/XLSX 上传、映射、预览、显式确认与原键恢复 |
| 订单列表 | `/v4/orders` | 期间／支付／履约筛选、分页、CSV 导出 |
| 订单详情 | `/v4/orders/:orderId` | 从当前列表取得真实 UUID，核商品关联和金额事实 |
| 异常订单 | `/v4/orders/anomalies` | 付款时间等未知事实，不推断为真实未付款 |
| 履约模拟 | `/v4/orders/fulfillment-demo` | 授权订单的受控演示履约覆盖层 |

`:productId` 和 `:orderId` 是占位符，不能原样请求或复制另一访客的 ID。
静态 `import/variants/categories` 等路由优先于 UUID；未知路径返回 404。

### 同源指标、导入与模拟覆盖层

同一店铺、时区、币种、期间与有效数据版本贯穿看板、钻取、列表、详情、导出和只读上下文。
选择 TWD 或 CNY 店铺分别核对，不跨币种相加；退款按事件期间，付款时间、成本、库存等未知
保持原因标记，不生成虚构毛利或真实结算结论。来源区分 `demo_fixture` 与含已确认上传的
`demo_mixed`，导入对象带 `demo_upload` 来源信息。

在商品导入页分别选择 CSV 或 XLSX，可用仅含合成数据的小文件测试。最小 CSV 示例：

```csv
sku,title,price,currency
QA-DEMO-UNIQUE,QA synthetic product,12.5,TWD
```

SKU 须在本店当前有效数据中唯一，币种须改为实际所选店铺币种。XLSX 使用同样四列表头的
受支持单 worksheet 文件；修改扩展名不能把 CSV 变成 XLSX。映射后核预览、质量结果与文件
摘要，再显式确认；只预览不能算商品已导入。修改映射按当前 UI 创建子版本，不确认旧版本。
确认后从当前列表按 SKU 查询，核详情来源、原 job/version/回执及看板商品数；预览与确认
之间若版本、权限或期限变化，按错误提示处理，不猜成功或自动再发。

导入只创建当前演示租户的新商品与 SKU，不导订单／客户／退款／库存，也不 upsert。
CSV/XLSX 的大小、行列、安全解析及拒绝规则以 [合同](../CONTRACTS.md) 为准。
商品／订单导出是严格 JSON 内的安全 `csv_text`，前端核当前上下文后生成 CSV 下载，
不是 XLSX 导出；导出覆盖全部筛选结果，不能只核当前页。

标签操作仅改变演示覆盖层；履约模拟不改库存、钱或真实物流。有效确认导入也仅进入本地
演示有效视图。结果 UNKNOWN 时保留原 operation/key，先按 UI 核对原操作，不换键重发。
重置和退出是显式控制动作，不是失败恢复工具，不能用来掩盖原请求状态。

## 当前页批量标签：仅新案窗口内演示

以下步骤对应261已实现并实际执行的受控交互，最终独审4e4741ad已核收；不是无运行材料即可执行的服务。

1. 在当前已授权店铺商品列表读取一页，显式选择至少两个本页去重商品。选择不跨页保留，
   不提供全查询/全店操作；改变搜索、筛选、排序或页码会清选择并取消本批运行许可。
2. 填写同一目标规范标签并确认选中数、对象及版本。语义是**完整替换**，空标签集合即清空，
   不是仅追加。确认冻结当前身份/店铺/页查询、IDs/版本、初始data_revision；界面须说明可部分成功。
3. 保持单串行：每项先以当前权限读取精确对象/version；首项revision等于确认页，后项只接
   前一项已核receipt.after_revision。只有原COMMITTED回执、fresh详情的version/revision/标签
   全部闭合后才计成功并发下一项；不要把POST返回或pending进度出现当作完成。
4. 查看已核成功、明确拒绝、待核对、未发送四种结果。首个UNKNOWN、401/403/409、持久化或
   读回失败停止剩余；COMMITTED后GET拒绝仍保留待核对与原pending，不误称回滚或明确未提交。
5. “停止余下操作”、关闭、刷新、路由/店铺/角色变化、reset/logout、hidden/offline均取消后续。
   已发POST不因Abort而回滚，已成功项不随后项失败回滚；迟到响应不能更新新范围或续发。
6. 有未决结果时保留原operation/request_key，使用现有只读核对入口，不换key重发，不以空回执
   推断未提交。即便恢复确认COMMITTED也不自动续行；重新读取当前页、选择并确认才是新批次。
   不手改sessionStorage或清pending来“恢复”；reset/logout不是掩盖未决请求的方法。

实际新browser需把至少两项不同原key、跨key串行journal与最终SQL效果/版本/来源逐一对账。
组件/Mock通过不等于真实权限或提交；完整范围见 [批量与移动补充合同](../BATCH_AND_MOBILE_ADDENDUM.md)。

## 真实业务移动布局与原生缩放：已执行，最终独审已核

在Root新窗口内用真实API/PG/Web分别核1440、1280、390；390必须实际操作商品列表/详情、
批量及单项标签确认、订单列表/详情/演示履约，以及CSV和XLSX映射控件、确认与来源读回。
保存每项操作、严格同源响应、原key/journal和真实截图，检查焦点/Esc、控件可达、局部表格
滚动、无意外页面横向溢出及无权限空态。Shell设置页三宽或旧Mock不代业务390；
390 viewport也不冒称实体手机硬件已验。最终图像/人工可读性结论单列。

原生200%仍使用精确已审模块与pin，同案会话/新profile，核实际zoom事件/geometry和PNG；
不是CSS/viewport模拟。必须连同hidden/offline、受控迟到ACK及正常/故障清理完成，
不能因新增batch/mobile而跳过旧Gate。r10已运行并有40图；Main最终运行独审4e4741ad已核收，AI40图核验不代用户人工审批。390表右列需横向滚动，图片不证明图外列/发现性/触摸。

## 新 owned 案的准备条件

代码入口公开，以下运行材料必须由 Root 针对新案提供和核收，不能从历史案复制或自行填一个
READY 标记。没有材料或没有新的实际 GO 时，只能阅读说明，不启动资源。

| 类别 | 必要条件 |
| --- | --- |
| 冻结源码与工具 | 正确且干净的专属 checkout、精确 source/tree、合同／迁移／schema／锁摘要；依赖和工具链已按冻结源准备，依赖安装及浏览器工具准备须由 Root 按新案授权、冻结源与工具 pin 安排，不能复用旧案配置或在运行时自动下载浏览器 |
| 镜像来源 | 精确 PG/test image ID；真实 build/inside-source/noneditable 安装证明，与本案源码和原始 expected-runtime 文件 bytes 绑定；不自动 build、拉取或 retag |
| 资源与时间 | 新 `v41qa_…` project、`v4_demo_v41_…` DB、新不存在的 canonical case 目录、当前 UID、两独立 loopback 端口、两独立子网及绝对 UTC starts/deadline/parent_deadline；原清理预留至少 180 秒，容量不足即 HOLD |
| 权限与宿主 | 本案 owner/app 分离、低权限 runtime；Root 核定的 Docker daemon/binary/Compose plugin 身份，不能采用当前默认 daemon 或已有监听器 |
| 私有绑定 | 本案 0600 runtime authorization、build receipt、原始 expected-runtime 清单、daemon receipt；父监督与独立关闭采集仍由 Root 安排 |
| Shell/native | 额外精确 browser runtime pin：浏览器、framework、实际 Node hash、Playwright 1.64.0；固定 headed 模式和新私有 HOME/TMPDIR/profile，无用户历史 profile |

`OwnedManifest` 的完整字段为 source_sha/source_tree/inputs/scenario/project/database/directory、
pg_image/test_image、api_port/web_port、pg_subnet/host_subnet、starts_at/deadline/parent_deadline/uid。
`inputs` 精确固定五项：`uv.lock`、`CONTRACTS.md`、`API_CONTRACT.json`、0025 migration 及
`frontend/lib/v41-schema.json`，以源码中的完整相对路径和 hash 为准。它不是运行授权文件。

## 公开命令模板与 Root 私有接线

下面是已核代码入口的模板，`/ABS/…` 均须由 Root 的新案真实绝对路径替换；不是现在可执行的
默认启动命令。在 Root 指定的冻结 checkout 中执行，先只读核身份：

```sh
pwd
git rev-parse --show-toplevel HEAD HEAD^{tree}
git status --short
```

Root 先在目标 case 目录之外登记本案 manifest，目标 `directory` 必须尚不存在；prepare 仅生成
本案新的 0700 目录与 0600 私配、封存摘要，不开服务、不继承运行许可：

```sh
.venv/bin/python -m tests.e2e.v41.owned_driver prepare --case /ABS/ROOT_NEW_MANIFEST.json
```

Root 核收后在新 case 中绑定 `runtime-authorization.json`、`image-build.safe.json`、
`expected-runtime.json`、`docker-host.safe.json`；Shell 另需 `browser-runtime.safe.json`。
本说明不附这些私有文件内容，不提供伪造授权、密码、Cookie、CSRF/nonce 或 raw headers 的样例。
Owner/profile 配置由现有 prepare/bridge 生成与核验，不从旧案回填。

只有 Root 释放该精确新案实际窗口，并安排外层监督后，才使用生成的 case 文件：

```sh
.venv/bin/python -m tests.e2e.v41.owned_driver execute --case /ABS/NEW_CASE/case.json --root-opened-window
```

`--root-opened-window` 只是显式入口条件，不授予权限，也不能绕过私有绑定和当前 UTC。
五个固定 scenario 为 `dashboard_same_source`、`catalog_orders`、`import_csv`、`import_xlsx`、
`shell_navigation`；各案分别绑定，不接受任意 argv、spec、all 或常驻部署模式。
Shell 场景固定两标题，不能用单业务 spec 通过代签整条 Shell/native；`--list` 只证明收集，
不会证明 UI、授权、进程或截图通过。不要绕过 driver 单独运行 owner helper／Playwright 来
延续过期窗口，也不要对旧资产执行这些模板。

## 执行、末态与关闭顺序

1. 启动前核源码／工具／私配封存、Root 窗口、镜像真实来源、daemon、空新 namespace、端口、
   子网与 expanded Compose model。PG 不发布宿主端口，API/Web 仅使用本案 loopback。
2. 新 PG 后执行原数据库 migrate 至 0025、setup-checkpointer、原 runtime grant，以及
   V4 seed 的 init-fixture/grant-runtime/verify-fixture。随后固定 owner helper 依次
   `activate-policy → grant-runtime → verify-runtime`；实际 owner 身份、policy 与 ACL 必须核实。
   三动作各自 once／回执串联，失败不重置，不需要操作者手拼 SQL 或另开 owner CLI。
3. 仅在这些前置通过后，由原父入口启动并核本案 API/Web 归属，运行固定 HTTP recipe 或
   Shell 双 spec。新窗核收的 readiness 与端口才能产生可用 URL；`/v4` 是欢迎入口，
   不以页面可见代签业务成功。
4. 结束或失败时先停止并核所有 writers：probe、Web/API、owner oneoff、解析／浏览器进程及
   已登记的原组和成员。leader 退出不代表整组为空；未知身份不误 signal，保持 HOLD。
5. PG 尚存活时，把原 scope/key/journal 冻结导出，执行只读 final facts，逐项核 job/version/
   parse slot、receipt/event/effect、来源／库存／金额事实；中途 counts 或 schema 元数据不代签。
6. 执行 scoped down（不删除卷），独立核本案容器／网络为空、端口关闭、进程停止及原创建卷
   identity 保留。停止或采集失败也必须尝试受限关闭并保留原失败；不得全局 prune 或删卷补绿。

检查本案 `execution.json`、外层 native exit／timeout、各阶段日志与 hash、独立关闭回执及
保卷事实。`SCENARIO_COMPLETED_PENDING_REVIEW` 只表示该案已完成待复核，不是阶段 complete。
r10五张Native图及全部40图已完成AI工程视觉审查；浏览器退出码 `NOT_EXPOSED` 与用户人工视觉审批 `NOT_RUN` 仍保持分账。
强停、清理 UNKNOWN、断言失败或来源漂移均保留原件，不自动重试／重放或续窗。需要修复时由
Root 另定新 source、资源和窗口。已关闭窗口的 URL 随之失效，本说明不提供重新启动旧服务的命令。
