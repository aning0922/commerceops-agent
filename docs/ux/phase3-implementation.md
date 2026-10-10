# Phase3 冻结 M1 前端实施

当前包含已核 B01、B02 真实会话/只读批，以及本批 **B03 创建与审批候选**。正常合并 Root 已审 A02 `24856555` 后接入创建及 T3，执行/items/resolve 仍等待 A03 Gate。新冻结独审/组合 CI 与 Root 签收以 PR 实时回执为准，不能当完整 Phase3 完成。早期章节保留B01历史范围，当前只读批见末节。Issue [#33](https://github.com/aning0922/commerceops-agent/issues/33)、[#35](https://github.com/aning0922/commerceops-agent/issues/35) 为本阶段授权与文件所有权依据；本 PR 仅 Refs，不关闭阶段。

## 基线与范围

- 新独立 WT：`/Users/aipuli/.codex/worktrees/a266/commerceops-agent`；初始 clean、HEAD `59b350cb719a9d2fed3f68b1ee598fa0a9b97875`，普通新建 `codex/phase3-console`。
- 修改范围只有 `frontend/**`、`tests/e2e/web/**` 和本文件。后端/迁移/Worker/Graph/共享 DTO/Python 锁/根 CI/Compose/脚本及原 UX 资产没有修改。
- 冻结依据 `m1-ui/0.4.1-freeze-rc`，18 个逻辑页面 / 47 语义控件（B09 不渲染）/ 33 Native Token / 18 原组件，原生回读 revn 58。历史文件上的 candidate 标记不改写；本次按 Issue #33 的正式冻结授权实施。
- 已实际查看原生 task/report/approval/items/item-detail/login/admin/explanation/reanalysis 截图；保留旧 Penpot 文件、版本与备份，没有追加视觉批次。

## 页面与控件交接

| 冻结 ID | Next.js 路径或辅助层 | B01 实际范围 |
|---|---|---|
| S01 | `/login` | 预置账号登录壳；输入/登录禁用；不建立模拟会话，无身份选择器 |
| S02 | `/tasks` | 固定范围计数、本地筛选、任务导航、空结果、打开草稿 |
| S03 | `/tasks/[taskId]/report?version=1/2` | 固定报告版本、6/20 SKU、完整事实/风险、负库存/null、历史只读 |
| S04 | `/approvals/[approvalId]` | 完整冻结审批清单/未知集合、原回执核实样例；所有真实决定禁用 |
| S05 | `/replenishment-items` | 内部项列表、本地状态筛选，业务状态与独立同步状态 |
| S06 | `/tasks/[taskId]/events` | 业务步骤、可展开脱敏技术/既有恢复说明、同步事实；无通用恢复按钮 |
| S07 | `/access` | 无权/不存在统一反馈、过期/撤权样例，安全返回落点 |
| S08 | `/admin/operations` | admin-only 脱敏运维安全壳，只有运维导航；无业务对象/计数或审批权 |
| S09 | `/tasks/[taskId]` | 任务结果、相关事实入口；completed 才有新周期草稿入口 |
| S10 | `/approvals` | 待处理/历史本地筛选；无列表批准、批量动作或预勾选 |
| S11 | `/replenishment-items/[itemId]` | 来源版本、单项版本/原因/同步、终态只读、必要原因 Dialog |
| M01 | S11 Dialog | 原因 pristine 不报错，本地提交校验与关联字段错误；没有业务提交/回执 |
| M02 | S02/S09 Drawer | 空草稿、本地文本确认、脏草稿关闭确认；不解析候选、不创建任务 |
| M03 | S03 Dialog | 当前指定 report/version 的公式、参数、来源、时间、未知新鲜度 |
| M04 | S03 Drawer | 固定报告上下文、加载/失败/模板离线样例；不发送解释请求 |
| M05 | S03 Dialog | 版本与重新授权影响披露；未批准重算禁用 |
| F01/F02 | S09 边界说明 | Phase4 延后；没有发送飞书卡片或关联续答，B47 禁用 |

机器映射见 [freeze-map.json](../../frontend/evidence/b01/freeze-map.json)，包括全部 18 页原生实例 UUID、47 控件语义状态、33 Token 的 CSS 映射和 18 组件复用位置。它是 B01 实施映射，不能当作 47 个真实业务事件已实现或全部状态已验收。

B01/B02/B03/B04/B05/B07/B08/B11 的真实动作均禁用，说明服务合同/API 尚未独审。B32/B34/B36/B47 沿用冻结未接入禁用边界；B09 从未渲染。B12 仅回登录壳，明确没有会话可以退出。B35 仅确认本地输入，没有猜选 SKU 或产生可信参数。M01 的“检查原因（本地）”仅验证字段；正式 complete/close 仍禁用。

## Mock 与权限边界

`COMMERCEOPS_UI_MODE=mock` 必须显式启用。未启用时，即使设置角色样例变量也只返回安全壳。`COMMERCEOPS_MOCK_ROLE` 为服务端进程固定的 operator/approver/admin 样例；不读取客户端 actor/role/query/cookie，不设置登录 cookie，不允许浏览器切换身份。这不是正式鉴权，也不是开发身份替身用于真实审批的入口。

B01 UI 没有 API client 接入、fetch、Server Action、真实 POST 或虚构 endpoint；后续独立离线 client 仅测试注入 transport，见末节。页面与静态资源通过 Next.js 读取；实际 Playwright 监测中业务 API、非 GET 与站外请求均为零。所有资源仅固定模拟数据，未读 `.env` 或密钥，也未连接 P1/P2 PG、模型、飞书或电商服务。

固定服务器样例对象采用精确路径检查；无权/未知路径在渲染前跳到通用 `/access`，安全壳的 Client/RSC props 清空所有业务集合、编号、报告/快照/版本与业务状态。admin-only 不发送业务样例 payload。无效指定版本不能默认为最新版本。处理中任务的报告页不展示预生成冻结事实。

Mock 角色过滤只验证页面边界；不能证明实际 session、CSRF/Origin、逐角色 scope、兼任并集、撤权竞态或数据库授权成立。B02 只能按 A 已审服务器合同实现，不能拼接角色和任意店铺范围。

金额/需求/建议数量是预生成 Mock 事实，UI 不计算权威 Q。未知在途保留 null，按 0 估算只作为风险草案披露；未知库存硬阻断不豁免。审批记录、execution/内部项、sync 是独立事实。unknown/冲突/重复需核实原键原 payload；没有换键重发或猜测成功按钮。

## Token、布局与可访问性

语义 CSS 取冻结 `design-tokens.json.m1_candidate` 和 `assets-read.json` 的 33 Token；18 原组件的按钮/状态/ReadState/SKU/AppShell 语义复用，不建立新视觉系统，不宣称自动 Token 同步。224px Sidebar、72px Header、600px Drawer；间距 4/8/12/16/24/32，按钮至少 44px，桌面表格与 390px 完整事实卡片。所有风险均有文字，颜色不是唯一提示。

首批8e正文栈使用 Source Sans Pro / Noto Sans SC / 本机 CJK fallback，当时未打包字体。总控授权集中补齐后，新增固定5.3.0项目本地 Source Sans Pro 400/600 与 Noto Sans SC variable wght包（OFL-1.1），同冻结字体家族语义；许可随静态交付保留，见[字体记录](../../frontend/FONT_LICENSES.md)。没有全局字体安装或站外字体请求。Darwin实际Chromium字形断言确认h1中文字来自本地Noto自定义字体；Linux实际运行以OS专属记录为准，下载受限期间不外推为通过。真实读屏及真人 QA 尚未完成。

原生 `dialog.showModal()` 提供背景 inert；显式 Tab/Shift+Tab 边界循环、Esc 取消、关闭回到原触发控件，dirty 草稿先确认丢弃。`aria-labelledby`/字段 `aria-describedby`/`aria-invalid`/状态 announcement/语义行列及可见焦点已实现。

## 实际测试与证据

本机采用项目独立 Node **24.21.0** / npm **11.19.0**，官方下载并按既有 SHA256 校验；没有修改全局 Node/PATH。Next **16.4.0**、React **19.3.0**、Playwright **1.64.0**，版本通过官方 npm 元数据读取并固定在独立锁中。参考 [Next 安装文档](https://nextjs.org/docs/app/getting-started/installation)、[Playwright WebServer](https://playwright.dev/docs/test-webserver)。

命令从项目根运行，仅本条命令临时加入 PATH：

```sh
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend ci --ignore-scripts
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run check:toolchain
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run typecheck
PATH="$PWD/.tools/node/bin:$PATH" NEXT_TELEMETRY_DISABLED=1 npm --prefix frontend run build
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run test:web:install
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run test:web
uv run --frozen python -m pytest -m offline
uv run --frozen python -m scripts.check_docs
uv run --frozen python -m scripts.scan_secrets
```

Playwright 从 production build 独占启动六个自有 127.0.0.1:3410–3415 Next 服务（`reuseExistingServer=false`）；分别为 operator、approver/20SKU、admin、unknown、expired、未启用 Mock。全部 teardown 由 Playwright 完成，无 PG/业务 API。浏览器 Chromium 156，真实页面自动化，不冒称真人点击。

首轮 7/10，命中 Dialog Tab 边界和安全壳 RSC 固定编号残留；显式焦点循环/清空后第二轮 9/10，剩余请求者路径 ID 在 Next 路由元信息回显。渲染前通用 redirect 后第三轮 10/10。两份 [首轮摘要](../../frontend/evidence/b01/first-run-summary.json)、[第二轮摘要](../../frontend/evidence/b01/second-run-summary.json)保留，未把失败改写成通过。最终再加入无效版本/未生成报告断言并在同一构建复跑；精确最终结果以 [Playwright 报告](../../frontend/evidence/b01/playwright-results.json)与[验证记录](../../frontend/evidence/b01/validation.json)为准。

实际覆盖：导航/刷新/本地筛选；指定当前/历史报告与解释上下文；完整20SKU首项/末项未知风险；1440/1280/390无横裁切；Dialog Tab/Enter/Space/Esc/返回焦点；脏草稿关闭与completed新空草稿；原因空白/有效校验；终态只读；同步与内部项分离；admin安全落点/无业务导航/序列化无泄漏；过期；unknown原回执边界；默认未启Mock fail closed；非法版本与处理中未生成报告。

首批720 CSS px仅是200%等效reflow，原记录保留；集中补齐另以[官方Chrome tabs.setZoom](https://developer.chrome.com/docs/extensions/reference/api/tabs#method-setZoom)实现真正200% page zoom。自有临时profile/headed Chromium、零权限最小MV3 worker、只访问127.0.0.1自有Mock页，getZoom=2，innerWidth1440→720、outerWidth1440不变、DPR2→4、visualViewport.scale=1，完整20SKU/21行且scrollWidth720，head/tail实际截图。[实际记录](../../frontend/evidence/b01/actual-zoom.json)和[可复现脚本](../../frontend/tooling/zoom-proof.mjs)保留；最终font构建已再复验。不是CSS zoom/device metrics/pinch，也不是真人点击。初次原Chrome快捷键没有取得zoom回执、随后连接中断未记通过；已停止操作用户原profile，没有重置/删除/恢复未知页。实际服务端撤权/兼任scope、duplicate/conflict业务响应、决定竞态/持久幂等/PG恢复、正式登录仍留B02/全阶段Gate，不宣称通过。

离线 Python 回归实际 **896 passed / 236 deselected，84.51s**；两个既有 lark-oapi deprecation warning。没有执行真实 PG/Web 业务集成。依赖审计安装时 0 vulnerabilities；精确提交 GitHub CI 及独立 Review 由总控继续裁定。

敏感扫描初次只命中两处公用 HTTP header `key` 字面量；改为 Map 的名称/值声明，未改规则、未加豁免。随后当前/index/完整可达 Git 历史为 0 命中；提交前再次扫描。Python 文档检查首次系统 Python 缺 markdown_it，改用已有 uv 固定依赖后实际通过（56 Markdown，0 errors），不当作代码 Gate 失败或修改全局环境。

实际页面截图保存于 `frontend/evidence/b01/`，已实际查看桌面任务/报告/admin及390报告/20SKU审批全长截图。示例：[任务1440](../../frontend/evidence/b01/tasks-1440.png)、[报告1440](../../frontend/evidence/b01/report-1440.png)、[报告390](../../frontend/evidence/b01/report-390.png)、[审批20项390](../../frontend/evidence/b01/approval-20-390.png)、[admin1440](../../frontend/evidence/b01/admin-1440.png)。这是本次前端实施截图，不是新增 UX 设计批次。

## CI 与下一批

前端 root CI 增量已向总控/A 提供：独立 Node toolchain → npm ci → toolchain/typecheck → build → Chromium 安装 → test:web；Linux 安装可加 `--with-deps`。产物为 `frontend/evidence/b01/` 与 `frontend/test-results/`。B 不并写共享 workflow，当前已有根质量 CI 不自动替代新增 build/Playwright Gate。

B02 唯一前置：A 精确 OpenAPI/session/逐角色范围/request_key/error 与 API 代码独审冻结。届时正常同步合同，替换 UI-only fixture model 为已审 typed client，接服务端会话与真实动作并跑自有 PG/Web。当前 `/api/v1` 仅 A 提案，不据此发请求。F01/F02/真实飞书、未批准重算/续答、生产/公开部署/付费模型/Phase4均不在本批范围。

B 阶段容量18h属于原60h，不新增总预算。人工有效工时 not_reported；Agent墙钟和机器等待按实际记录，不把估计容量当作耗时。主控安排冻结 SHA 独审和内部合并，B 不合 main。

## 集中修复与最终冻结

总控安排独立Reviewer在自有隔离8e WT复验toolchain/typecheck/build/audit0/Chromium11项及390报告/20SKU/admin截图，没有新增P1/P2阻断；这不替代最终增量冻结回执。首批8e精确GitHub CI [38046425858](https://github.com/aning0922/commerceops-agent/actions/runs/38046425858)实际SUCCESS，只记历史SHA，不外推到本次修复。

交接补查两项修复集中在同一普通提交：ItemFact绑定自己的sourceTaskId/sourceReportVersion，详情文字与来源链接同v1；completed样例源task的report/snapshot关联独立，相关内部项按源task隔离，不能挂其他task的审批。实际页面断言核对来源文字/URL、无跨task内部项/审批、REPORT-DEMO-007上下文和两项SKU范围，不以重跑原未覆盖用例代替。

同批补项目字体、真正200%与一项实际CJK glyph断言。最终Web用例12项（原11项扩充上述定向断言，另加字体实际来源），截图等待document.fonts.ready。Linux官方镜像下载观察原live handle，不重启/加权限；如未完成，保持[下载记录](../../frontend/evidence/b01/linux-download.json)not_run，由A根CI Linux执行同字形/load/截图断言补证；fc-match或Darwin截图不能代替Linux实测。

Root已正式放行3e05c714289135ab6901159d7e9210d657967fc2（精确CI38047261517 SUCCESS）；合前用该提交的隔离扫描政策真实检查本WT，dir/index/fullgit各0，不改本分支旧扫描器。普通保存B本批后同步A精确合同与第三扫描例外政策，PR base由Root正常迁到codex/phase3-approval。B不修改扫描规则/豁免，也不改已有历史。最终新source SHA/增量独审/CI以PR36与总控实时回执为准；API主体独审之前仍零业务请求。

原生zoom后的Playwright默认clip出现裁切/尾部空白，旧PNG和8e记录标为截图失败保留；最终以不带CSS clip的CDP Page.captureScreenshot原生surface捕获head/tail/actions并实际查看，避免空白图冒称视觉通过。

原Linux下载handle40636最终exit0，镜像已完成；本checkpoint仍未启动Linux浏览器，未改写为Linux验收通过。B02真实会话/审批测试使用单一live配置trace=off，禁raw trace/HAR/body；CI只上传sanitized结果与不含密码/Cookie/session/CSRF/nonce的安全截图，不开发通用脱敏框架。

## 0bb独审两项P1与有界修复

0bb精确CI38049750572虽SUCCESS，独审仍阻断签收：approver/20SKU访问completed007报告时错误使用容量变体筛SKU-A/B而得到空报告；两采集工具固定3430、未验证服务归属，Reviewer对未知服务采集不计证据。此处不改写为通过。

007现在保留自身独立固定SKU-A/B来源，两项/建议172件含未知在途风险；report/snapshot007和唯一当前v1绑定，非v1拒绝，无其他历史版本入口，不回落008或把空选集当完整报告。13项真实页面自动化增加approver20从任务列表访问007、两行/风险/来源/版本/刷新/非法版本断言，实际全部通过。

zoom与Linux工具共用仅这两项证明的限定owned-mock模块：显式127.0.0.1:PORT，必须本checkout当前build的Next自有Mock启动成功；占用/未知服务立即拒绝，无访问或终止未知PID。DOM公开测试service marker与BUILD_ID前后核对，构建指纹/自有pid/来源入非秘密证据；它们不是身份授权或新业务endpoint。实际无base拒绝exit1、已有3430占用拒绝exit1；自有3443真正200%和自有3444到容器映射的Linux字体一次运行exit0，前后identity匹配，关闭各自child/container。

Linux实际为arm64/Node24.21.0/Chromium156.0.8078.4、本地Noto custom glyph4、1440/390无overflow、20SKU全量、无API/站外写。原首次Linux工具回执作为历史保存（当时缺marker不当作新工具的归属证明）；当前截图属于受控重采。[Linux当前记录](../../frontend/evidence/b01/linux-font.json)、[首次历史回执](../../frontend/evidence/b01/linux-font-first-receipt.json)、[拒绝/来源记录](../../frontend/evidence/b01/ownership-guards.json)分开。

B01此普通修复不含未提交typedclient/generated types。新冻结SHA独审与CI仍以Root/PR实时回执为准。


## B02 离线类型与 transport 独立批次

唯一输入为 Root 已放行的 A 合同 `3e05c714289135ab6901159d7e9210d657967fc2`。B01 `1e6b8da8b47ec6390de2f7034251183cb3f985b1` 的两项 P1 已由独立 Reviewer 实际增量核验解除；该 SHA 的 CI/集成签收仍按 Root 实时回执，不以本批取代。

`frontend/lib/p3-types.generated.ts` 从冻结 OpenAPI 的 21 paths / 22 operations / 67 schemas 生成 readonly 类型。项目 TS7.0.2 与固定 lock 不变：直接将 openapi-typescript 7.13.0 加到项目 devDependencies 时因其 TS5 peer 合同 ERESOLVE 失败，未 force/legacy-peer-deps 或降级；随后在临时 npm exec 环境明确使用生成器7.13.0和TS5.9.3。临时生成器环境未另建 transitive lock，不宣称等同生产锁保障。再次生成到 ignored `.audit` 后逐字节相同，合同与生成文件 SHA256 记录在 [generation.json](../../frontend/evidence/b02-offline/generation.json)。参考 [生成器官方 CLI](https://openapi-ts.dev/cli)。

```sh
PATH="$PWD/.tools/node/bin:$PATH" npm exec --yes --package openapi-typescript@7.13.0 --package typescript@5.9.3 -- openapi-typescript docs/contracts/p3-openapi.json --immutable -o frontend/lib/p3-types.generated.ts
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run typecheck
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run test:contract
PATH="$PWD/.tools/node/bin:$PATH" NEXT_TELEMETRY_DISABLED=1 npm --prefix frontend run build
```

`p3-transport.ts` 要求显式 origin 与注入 transport，没有默认 global fetch。HTTPS 或显式 loopback localHttp；credentials/include、cache/no-store、redirect/error。POST 固定 JSON/X-CSRF-Token，身份仅响应 session，不发送 actor/role/Origin 伪造 header；CSRF/principal/nonce 只存在实例内存/私有 closure，不写 URL、日志、存储或可序列化预备请求。未 bootstrap 不登录，匿名 bootstrap 不授业务写权，401/403 先清内存并回调清 UI 缓存，logout 即使故障也清本地会话。

预备 create/decision/resolve 固定白名单字段并在创建时捕获原 JSON 字节、原 key/nonce/version；变更当前 principal 后不能发送旧预备请求。网络失败、损坏成功响应或5xx写结果统一 unknown，不自动重投或换键；调用方须显式保留并重发原 PreparedWrite 或按原 operation/key 回读。404不推断写入失败。服务错误只显示本地固定文案与白名单 code/合法 traceId，不回显 server safe_message/原输入。指定 report_id/explanation 绑定、历史 plan_version 与分页查询按冻结路径传输，非法路径 UUID/版本本地拒绝。

这是 transport 离线批次，runtime 仅校验 envelope、身份模式和 session 必要字段；生成 TS 类型不等于完整响应 runtime schema 校验。后续 UI 适配必须核实完整 server DTO、披露完整性/数量/绑定/eligibility 后才启用决定，不能据 typed cast 宣称可批准。B01 UI 没有导入 client/generated types，所有业务动作仍禁用，无真实网络/PG/会话/审批 Gate，未接 A 未审 API。

实际注入测试首次4过1失败，因 PreparedWrite.send 身份变化时同步抛错不符合 Promise 签名；改 async 后通过，后加 unknown/17 GET/bootstrap与logout/创建输入定向用例，总计 **9/9**。这些测试没有启动浏览器或服务；[首轮摘要](../../frontend/evidence/b02-offline/first-run-summary.json)与[最终离线结果](../../frontend/evidence/b02-offline/contract-results.json)分开保存。最终 typecheck/build 成功，未因未接 UI 而重复 Mock 截图或将历史13PW记作新批次测试。

预置单独 `playwright.live.config.ts`，trace/video/自动 screenshot 全部 off。后续 live 用例只在 Root 放行窗口显式采集已清除密码/Cookie/session/CSRF/nonce 的截图与 sanitized 结果；禁止 raw trace/HAR/body。当前 live 目录/用例/API资源均未启用；配置存在不代表 live 测试已经执行。

本批初次敏感扫描命中3处声明为离线的密码占位字面量及1处公共合同hash相邻OpenAPI路径误报。未上传；测试改用显式低熵动态假值，生成回执将hash与路径各自分离排列，未改扫描规则/豁免，也未隐藏真实凭据。最终扫描结果以本批验证回执为准。


## B02 真实会话与只读页面候选

Root正式放行A01 `aeaa916a59341a6ffa4a89f863d065580599f6d3`（tree `3dde1cde536ce438e38aa7bdf1d1655bac7b4b81`、实际CI38055767391成功）后，在原B WT/branch普通fetch并merge为`5053f56000ca08872cad02bd437ac7f8156fef6b`，保留14dc及全部历史。14dc精确CI38051582409和独审均已通过；它们不覆盖本次组合源码。本批不读取A02未提交目录、不改后端/迁移/权限/共享schema/根CI/Compose/锁文件，不合main。

### 实现行为与门禁

显式 `COMMERCEOPS_UI_MODE=live`、有效 `COMMERCEOPS_API_ORIGIN` 与 `COMMERCEOPS_WEB_TRANSPORT=local_http|https` 才启用真实页面。缺配置关闭业务访问，不回退Mock身份。Next只呈现入口与公开origin；浏览器通过已审P3Client直连API，Cookie由API HttpOnly管理。账号密码只在本地表单/调用内存，提交前清密码DOM；CSRF/nonce不进URL、RSC、storage或公开日志。会话401/403立即清principal/全部业务页/配置/Dialog，异步epoch阻止失效前请求迟到重新填充；focus/可见性/显式刷新重查当前会话。登录/注销实际Cookie、CSRF及浏览器Origin按A合同，退出回执丢失显示待核实且先清本地业务数据。

服务端capabilities决定home/nav；role_shop_grants逐角色展示店铺绑定，无身份选择器、客户端actor、角色或跨店授权拼接。任务列表/筛选计数/total/cursor、本人或eligible详情/报告/计划/审批/事件/配置/原请求回执、admin脱敏运维都读取实际API。无权/不存在统一/access，读取失败不显示旧业务或猜测成功。P2 analysis_only与P3正式workflow、业务state/outcome与sync/outbox事实分开；unknown时间/配置不补0。库存建议/D/精确ratio/风险/原始null与有效值来自冻结服务器事实，UI不计算权威建议。

本批只用A01已实现17 operations中的16个read/auth：包含login/logout，排除T1 POST/tasks；执行、items、resolve、decision均未接入。live transport发送前白名单阻断业务POST及未实现GET，UI写入口disabled/pending，没有不存在API或模拟响应替身。解释只GET固定task/report的既有缓存，实际缺缓存NOT_READY；正向缓存HTTP仍not_run，没有模板冒充缓存或新模型调用。指定plan版本保留真实current/superseded状态，均只读；现自有数据仅实际v1，没有伪造第二历史版本。

固定Ajv8.20.0/ajv-formats3.0.1（npm audit0，独立frontend锁）校验从冻结OpenAPI复制的67 schemas与16操作response，使用[Ajv官方2020-12支持](https://ajv.js.org/json-schema.html)与[format校验](https://ajv.js.org/guide/formats.html)。无coerce/removeAdditional/default填充，拒绝身份模式/缺字段/额外actor/bool整数/非安全整数/坏时间；P2冻结导出的ge元数据显式按其边界验证，未修改shared schema。报告task/report/facts_hash、审批与plan id/version/hash、计划全量条目/精确件数/事实SKU与在途建议绑定另做UI一致性检查；typed cast不授审批权。生成文件和官方合同逐字节同步检查实际通过，命令`npm --prefix frontend run check:read-schema`。Root通知A02未来DecisionReceipt完整ack键max256→300（前缀21、合法SKU256合277），本批仍当前已审冻结，未提前同步或把未来DTO修正当已测。

### 自有资源、失败与实际运行

唯一项目`p3b02-8c4cee9d4102`、owner`phase3-B-WTa266`，PG54446/API3461/Next3460全部loopback，运行前登记，原绝对截止2026-10-10 23:27:53.909900+08。复用既有prepare_pg、原Compose与gitignored私有port overlay、A initialize_p3/预置/scrypt/单Worker，未写共享脚本或建通用资源框架。私有目录700/全部私有文件600、新卷独立；A旧库/账号、P1/P2资源、.env/平台key均未读。

首次seed误写p.plan_version/source report_id而UndefinedColumn失败，finally自动停PG保卷；仅B辅助代码修为migration实际p.version/source_report_id。第二次assert无plan，发现B换Worker配置却沿用旧TestClient store，T1 config_version不一致；第一次只读核查22旧P3中18 CONFIG_VERSION_UNSUPPORTED、plan0，不将未核4项笼统归因。改为同配置新TestClient后第三次在同项目/同原截止成功预置新组织五真实账号、22公开P2/P3记录、20SKU不可变plan/approval；先前组织数据完整保留隔离，没有reset/drop。后续实际Worker收敛后核33总P3中22旧配置失败、11真实plan；均为同新自有库的受控mock数据。没有把异常换成A API后门，也未扩窗口。

实际最终production build/typecheck、固定schema check成功；离线合同 **13/13（1.9s）**，包含原9、完整DTO反例、发送前未审操作零请求、全量事实绑定反例。第三个离线用例首次使用dynamic import触发Playwright ESM转译exports错误，11过1失败保留；改既有static import后通过。初次扫描只命中两条sku_key比较表达式的符号引用误报，改自然解构比较，未改规则或增例外；最终current/index/fullgit结果另列验证回执。

真实Playwright首轮6/7：operator390隐藏表头使可见row20而旧断言21；20 SKU未缺，改响应式计数后第二轮7/7。最后扫描表达式等价收口后的构建复验6/7，连续测试账号触及真实5分钟5次限流而最后登录未成立；未清计数/降限/自动重投，新增本次E2E专用只读滑窗就绪检查，等待自然释放。最终同构建 **7/7（22.45s）**：operator22条/20+2分页、报告20完整/长中文/null/刷新/固定report/来源/真实TTL1800新鲜度450/server_time/390无overflow、Dialog Esc返回焦点；approver eligible20项/无默认确认/全部决定禁用/指定v1只读/缺解释缓存/events；admin-only无业务nav/编号/计数且强制深链/access；同店另一operator非本人404与不存在同envelope形状；兼任operator-A/approver-B不拼A eligible；原create_task回执当前principal回读、缺CSRF拒绝、logout后真实401；合法scope撤销后真实401并清业务/身份且无Mock回退。业务POST仅auth/login/logout，没有T1/decision/resolve。跨店eligible集合由真实T2及读API证明，但不称本批T3决定Gate。

前三份safe summary分别见live-first-run/live-second-run/live-third-run，最终live-results；raw trace/HAR/HTTP body不记录。PW自动trace/video/screenshot全off，专用reporter仅test/status/duration/location白名单，不复制TestError、stdout、步骤或attachments。必要截图在成功认证且无密码input时显式保存，均实际查看：report1440、report390、admin1440。原生PW失败DOM error-context只留私有/忽略目录未上传，最后成功运行已清旧输出；为后续失败再加afterEach先导航自有about:blank，并将临时输出放600输入所属700私有窗口目录。此收尾仅source/typecheck核证，未重新制造登录失败来宣称实际清理探针通过，不开发通用脱敏框架。

退出前核实际DB model_calls0，app role rolsuper/createdb/createrole全false；全部任务69/jobs66/plan11/approval11/request33/outbox11包含前两次失败种子，不能称cleanup0。完成即提前停止自有API/Next/PG并保卷/600文件，实际PGrunning=false/PID0、已知child退出记录见resource-window.json。只有注册项目被管理，无未知PID/用户Chrome/profile操作。B01已证真正200%/跨平台字体没有无变化重跑，不追加视觉批次；真人QA/HTTPS部署/真实模型/飞书/生产/Phase4保持未跑。人工H/L not_reported，Agent墙钟按Git/窗口UTC回执、机器时间按报告记，原B18h/300h不重置。

```sh
# 自有窗口已登记/启动并核PID后，从根运行；目录为本次私有输入，不是.env。
PATH="$PWD/.tools/node/bin:$PATH" COMMERCEOPS_LIVE_WEB_URL=http://127.0.0.1:3460 COMMERCEOPS_B02_PRIVATE_DIR="$PWD/runtime/p3b02-8c4cee9d4102" npm --prefix frontend run test:live
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run test:contract
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run check:read-schema
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run typecheck
PATH="$PWD/.tools/node/bin:$PATH" NEXT_TELEMETRY_DISABLED=1 npm --prefix frontend run build
uv run --frozen ruff check tests/e2e/web/live_seed.py tests/e2e/web/live_ready.py tests/e2e/web/live_revoke.py
uv run --frozen mypy tests/e2e/web/live_seed.py tests/e2e/web/live_ready.py tests/e2e/web/live_revoke.py
uv run --frozen python -m scripts.check_docs
uv run --frozen python -m scripts.scan_secrets
```

本候选只退出登录/只读批；新source冻结/独审/组合CI待Root。A02/A03已审交接后再正常同步+生成类型/只读schema，后续按对应Gate接创建/决定/恢复/执行/resolve；当前真实B02完整业务、完整22操作runtime导出一致和全Phase3验收均未完成。

最终新增validation元数据的secrets字段的三scope扫描状态说明行再次命中generic-api-key；只是普通状态句，未包含凭据。B的exec编排误在失败返回后继续形成未上传973bf，已立即停止上传并普通修当前元数据；不amend/reset/rebase/force、不自行改共享扫描规则。973bf历史唯一误报待Root协调精确政策独审，current/index修后与完整history分别实记，不将此前0外推本次final通过。


## 独审P1：自有listener端口与build归属最小修复

独立Reviewer在启动资源前发现6824的Web E2E固定3460/3461，无法核自己的3470/3471；已停止未启动资源，不借B的账号/runtime/PG。本有界修复只改专用E2E/helper/此交接：从windowInfo已校验的web_origin/api_origin取显式TCP端口，要求canonical `http://127.0.0.1:PORT`，拒绝异主机/https/localhost/IPv6别名/userinfo/path/query/hash/隐式或无效端口；不回退旧端口。lsof用解析数字argv，正整数PID必须精确且唯一归属（同PID重复行允许，混入其他PID拒绝），无启动或终止进程。登记build_id还须匹配本checkout `.next/BUILD_ID`，缺失/不同即拒绝。

实际4/4纯函数反例（343ms）、typecheck/Prettier通过，覆盖3470/3471、旧端口、边界端口、19个非法Origin、入口不匹配/坏PID/不同listener与build。此仅使用既有离线runner，没有浏览器fixture/PG/API/Next启动，未把新的3470/3471实际Web记通过；独审续跑7项由Root派Reviewer在其自有资源进行。原13/7和失败记录不改写。对6824逐个Git blob核业务app/components/lib/public/配置与npm锁全部相同，证明见owned-listener-fix.json。当前history唯一973bf公开metadata误报仍待共享policy独审，不push、不改scanner或历史、不合A02未审内容。


## 第二个同类独审阻断：seed Origin登记贯通

Reviewer在12fa自有3470/3471资源完成迁移/预置后发现B seed的WebConfig.origins仍固定3460，将真实ORIGIN_DENIED；API/Next/PW未启动并停自有PG保卷，原截止不重置。本次一次辅助收口从600/no-follow/当前UID的私有window.json严格校验web_origin与api_origin，要求canonical http/127.0.0.1/显式有效非默认TCP端口，拒绝userinfo/path/query/hash/异主机等。校验发生在DB初始化前；最终seed WebConfig.origins仅登记web_origin，TestClient base_url登记api_origin，bootstrap/login/session/T1 seed请求明确用同登记web Origin与实际Cookie/CSRF，不沿用A fixture内部默认Origin，不降低真实校验或注入actor。

一次rg核live_seed/live_ready/live_revoke/live_origins/read.spec/owned-listeners/playwright.live/live-reporter/read client/page入口，运行链无3460/3461回退；页面origin/runner URL仅显式受控env，read.spec仍对登记值精确校验。旧固定端口只留历史资料/反例，不用作新Reviewer端点。22/22 Python纯离线反例（0.32s）包括3470/3471、20非法Origin与私有登记权限/双端点要求，Ruff/format/mypy三文件和frontend typecheck通过；未启动PG/API/Next/浏览器，不宣称新7项实际通过。业务22 blob与12fa逐字相同，seed-origin-fix.json留证；history仍原973bf误报1、no push。若续审仍有同源端点阻断，按Root合同集中报告并暂停live，不自动第三轮或另建框架。

组合ab57正常push后的精确CI38062624307实际FAILURE：预依赖与Foundation三scope扫描0、锁检查/63Markdown0/Ruff通过，但全仓库format仅live_revoke.py相邻SQL字面量需合成一行，PG完全skipped且其他后续检查未执行。Root同意≤3min辅助格式收口：项目锁定Ruff仅格式化此文件，AST与ab57完全相同，无SQL/校验/权限/端点/业务变化；完整ruff format --check .及ruff check .通过。普通新提交与新CI继续记账，不rerun或将policyCI当此组合通过；独审ab57业务窗口不取消，必要证据只由Reviewer核语义后继承。

本WT格式修正后完整scripts.check实际exit0：981offline passed/271 deselected/96.77s、2既有lark弃用warning；Ruff与226全仓格式、mypy159、63Markdown0、Node24.21工具链/frontend typecheck、Node audit0与95Python包漏洞0、三scope敏感0。没有执行作者PG/PW；独立Reviewer在ab57自有54710/3471/3470原截止内已实际7/7，无P1/P2，格式only证据继承仍须Reviewer核对，不把此前policy或14dc CI外推。


## B03 创建与审批候选（等待本批实际回执和独审）

Root 已批准 A02 `24856555fe23975fb19cd67ddcc033f6cac3905c`，B 在原 WT/branch/PR #36 正常 merge 为 `48ec0f91c0f9181fa1af4a659301768b251e0626`，没有历史改写。全部实现仍限定 frontend、专用 Web 测试和本文件；A03 未提交内容未读取，backend/shared DTO/Worker/Graph/迁移/CI/Compose/锁文件未改。

`CreateTaskDialog` 复用冻结 M02 Drawer：from_report 绑定当前可信 source_task/report/snapshot/facts_hash；new_cycle 显式确认 Mock case、operator 店铺与 L/R/S 整数参数，不做自然语言猜参。准备请求与明确 POST 分开，新 task/request_key 独立，源 completed 不恢复，不继承旧 nonce/hash/approval/假设勾选。T3 复用 S04/原生 Dialog：普通批准、拒绝、完整假设联合批准、拒绝假设分别按真实合同提交；raw inbound null 披露不改0，联合集合无默认勾选，缺/多/重复或绑定不全不能启用。

决定仅以服务器 can_decide、pending/current、精确 id/version/hash、完整20项披露、硬阻断、nonce/expiry及当前 scope 为准。浏览器使用 server_time 加单调时钟显示期限；服务器持锁再次判断。来源 observation/max-age/执行前重观察需求仍披露，不增加浏览器 freshness veto，A03新版本流程未实现。指定版本只读，变版本重新挂载确认组件，旧集合不沿用。

`Submission` 仅保留本次私有 closure 的原 key/JSON bytes：网络/丢 ACK/坏成功响应为 unknown，绝不自动重投或换键。只能显式同键原字节重投或 GET 原 operation/key 回读；404 仍待核实，不推断失败。receipt 严格 runtime schema、key/operation、决定 id/version/hash/action/完整假设绑定校验；显示“意见已记录 · 执行待处理”，不把批准当执行/采购/入库。身份撤销清页面及私有请求，nonce/CSRF/password 不进截图、URL、storage、日志或 RSC。创建 Dialog 对 pending/unknown 阻止 Esc/关闭丢失原字节；草稿关闭先确认丢弃。

18 个已审操作的运行时 response schema 已同步 A02；execution、items、resolve 四个未审操作在发送前仍拒绝，UI保持 disabled。无飞书/真实模型/生产/Phase4。冻结 m1-ui/0.4.1 18页/47控件、字体和 token 复用，没有新视觉批次。

当前离线证据：20/20 合同（2.4s）、Python 22/22 Origin 辅助测试、production build/typecheck/schema check；完整工程 check 1000 passed / 295 deselected（92.35s），两个既有 lark-oapi warnings，lint/format/mypy/锁/audit通过。该完整 check 在种子辅助调整前运行，最终增量 lint/mypy另核。合同首轮19过1失败来自旧“阻断T1”断言，A02已放行后改为阻断未审resolve/items，首轮回执保留。

新唯一窗口 p3b03-1cc9ff864a67，owner phase3-B-WTa266，PG54463/API3481/Next3480全部loopback；登记UTC 2026-10-10T16:22:29.733914Z，原 absolute stop 17:52:29.733914Z，目录700/私有文件600，独立新卷。首轮种子在同一仍存活PID重复启动 Worker 触发 TerminationRequired；seed/内部Worker PID7612退出2并reaped，API/Next/外部Worker未启动，PG16:22:42.059265Z stopped/running=false/PID0，保卷。按 immutable created_at 截至首停实际计数25tasks/24jobs/11plans/11approvals/12requests/model_calls0，包含fixture基础记录；PW未启动。

仅一次针对修复：已审B02种子子进程退出、原PID由既有 require_process_absent 核不存在后，B03一次连续 Worker 准备额外fixture，未改终止合同/删除记录。在同project/卷/原截止重新启动，种子成功；API11788/Next11789/单Worker11787的listener及 BUILD_ID 686Kj5pzHAmW3YtYVfMhM 已核。真实 PW 当前未结案，不将等待/成功提示当业务Gate。首失败 ledger 与时间边界计数分别在 resource-first-stop.json、first-seed-counts.json。

受控两项未知、ACK丢失、superseded fixture分别明示：ACK通过实际API提交后route.abort丢浏览器回执，属于受控 transport fault，不宣称自然故障；superseded由专用owner PG fixture设置状态，只验证旧版本禁用，不当作A03新版本重观察流程。首轮失败数据完整保留隔离，不称cleanup0。人工 H/L not_reported，B18h/总60h/300h/原目标日期不重置；Agent与机器实际时间按窗口/测试回执记录。


### B03 实际收口与剩余证据

首轮实际真实业务 PW **10/10 passed**，总287.26s含自然限流等待；测试本身合计约19.77s。全部 headless 独立 context；trace/video/自动screenshot/HAR均关闭，结果仅白名单字段。实际包含普通批准、拒绝、完整联合批准、两项假设拒绝；10次原key/原JSON字节POST的SHA256摘要唯一；漏/多/重复与错误版本拒绝；原键改动作IDEMPOTENCY_CONFLICT、新键相反意见DECISION_CONFLICT；真正API commit后受控abort造成unknown，无自动POST，GET原回执恢复后显式同键重投；from_report/new_cycle结构化创建；指定版/实际60s expiry/admin/dual隔离；受控superseded和预备后真实撤权401清全部业务/确认。没有用fake HTTP批准响应替代业务。

PG只读复核：combined20/approve/unknown各executing，停在A03 revalidate前；reject/decline/second_combined各rejected；上述六task每项decision/audit/resume_job恰1，revocation/supersede/expiry均0。源P2 completed未变，model_calls0，app rolsuper/createdb/createrole均false。测试标题里ACK“同键十次”由独立普通批准回放测试证明，ACK自身实际两次POST（一初投一显式回放），无重复计账。GET receipt保留原duplicate=false，重新POST返回duplicate=true，两者不混为执行状态。

截图实际检查1440回执、1280和390完整20SKU。1440截图显示读取时历史pending与本次已记录回执分别成立，不能以旧读取快照否定原回执。检查后5处旧“只读批”文案作纯文本修正，业务路径与action组件字节不变；最终build/typecheck另记，截图对应先前测试build，未冒称文本修正后重新跑业务PW。键盘本批实测Escape/触发焦点返回；Tab/Enter/Space本批未新跑，B01已核原生Modal组件字节保留，仅作为组件继承，不冒称新动作键盘实测。

真正200% **本批整体未完成**。首个自有临时可见Chromium probe无OS输入，但operator审批路由capability拒绝导致TimeoutError；已关闭自身context/profile。用户新增“不得影响正常电脑操作”边界后，一律headless，禁止可见浏览器、activate/bringToFront、OS全局键鼠、用户Chrome/profile。后台probe去掉window update并active:false，实际部分证据getZoom=2、innerWidth1440→720、outerWidth1440不变、DPR1→2、visualScale1、scrollWidth720、全20行；安全截图选择器无匹配导致TimeoutError，整体仍failed。diagnostic保留，没有CSS scale冒充。Root要求停止追加试验已遵从：原handle核退出1，finally关闭/删除自身profile，无该probe进程；选择器源代码收口但未重跑。B01旧真实200%只作为既有组件证据，不能替代本批完整live Gate；最小补证交Root独审裁决。

窗口已提前正常停止API11788/Next11789/单Worker11787并由原handle reaped，PG running=false/PID0，原absolute stop不变，卷和首轮失败数据保留。详见resource-window.json；后续未启动同窗/旧P1P2/A资源。最终SHA独审、精确CI、Root签收、200%缺项及完整Phase3剩余Gate均以Root/GitHub实时回执为准；本批不合main。

B03提交前首扫描仅dir/index各命中generation.json第5行公开合同SHA256与openapi字段名，git0；尚未提交/上传。元数据字段改为contract并保留scan-first-run.json，未改规则/新增例外；最终扫描以提交前工具和PR回执为准。


## B04 离线准备批（未接 A03 真实 API）

Root 在 B03 ed34 精确独审后授权安全并行离线准备；原 WT a266/codex/phase3-console/PR36，clean ed34 起步，本批只允许本地普通 commit，不push触发已知共享PG CI问题。B03独审实际结果与作者原失败分记：Reviewer独立自有8原套件+2等价probe、新动作键盘和后台真200%通过；B03完整Gate仍因精确CI38068569167 P3组command300触限pendingCI，不将本批离线测试代替该Gate。A唯一负责A03及共享CI分组评估。本批未读A03 WIP、未起PG、未连接API或实际业务写入，无新会话/分支/worktree/依赖。

纯`ExecutionFacts`/`ItemListFacts`/`ItemDetails`与`ResolveDialog`使用现有完整p3-web-v1 DTO，复用原Card/Status/Sync/Modal、冻结内部项列表/详情/原因/操作轨迹样式。execution completed、每项open/completed/closed及sync分别呈现；internal-only，不表示采购/入库/库存修改。只有Worker执行回执展示，没有用户execute/retry/外部发送按钮；B32/B34禁用，终态无重开。列表完整显示20项/长中文/数量/版本/统计与筛选，来源只有服务端可见ID，缺计划版本不猜补、无权来源不造链接。

Resolve只使用当前can_resolve/open/版本及完整记录一致性；准备前GET当前项复查，版本变化不自动生成新键。原因pristine无错误，提交后校验；局部明确按A提供的Python3.12 str.strip集合（U+001C–001F/0085等边界移除、FEFF保留）和1–1000 Unicode码点，不做NFC/NFKC/内部空白归一。已与自有固定字符串、Python3.12标准strip实际对照；尚未实际PG/HTTP Unicode Gate。规范reason/expected_version/action、item path与原请求key/JSON bytes由既有P3Client私有closure封存；预备时读取快照另冻结用于receipt绑定，hash不授权限、不自行创造server权威hash算法。首次receipt严格核item/key/action/reason/before-after版本/状态，后续核同原resolution id/actor/time/server digest；Mock digest明确低熵占位，不称实际canonical hash。

Unknown不自动POST/换键/相反动作，只有原operation/key回读或显式原字节重投；404仍待核实，不能推断失败。pending/unknown阻止Dialog关闭/卸载误丢请求并有beforeunload提示；未提交dirty需确认丢弃。冲突固定安全文案、保留原请求；401清Mock身份/业务/预备操作及异步迟到填充。成功后内部项采用原receipt终态，sync异常继续独立呈现；关闭Dialog焦点落到当前事实摘要，未提交Esc回原触发按钮。

`p3-live-client.ts`、`p3-read-schema.generated.json`、`p3-types.generated.ts`、`p3-transport.ts`与原`ui.tsx`相对ed34逐字节不变。正式runtime仍18operations，四未审接口execution/items/item/resolve在before-send零请求拒绝，未开放A03。新增schema校验只针对既有67components中的纯DTO；注入固定Mock transport无fetch、真实cookie或外部身份。预览仅显式UI_MODE=mock + MOCK_BATCH=b04 + operator样例启用，live/未启Mock/其他角色不走此分支；角色不能通过query改变。原read/T1/T3合同回归保留，B04新纯适配没有声明稳定server export。

实际离线合同首轮26/26（2.3s），包含原20与6个新增DTO/Unicode/门禁/回执绑定/原字节10次/401/404/冲突用例；四未审接口均零transport请求。Mock production headless UI首轮3/6（20.5s），两处断言与既有Sync文案不符、一处在异步准备完成前按Space；首失败sanitized摘要保留。断言/等待收口，同时补快照冻结/终态焦点/卸载防迟到后同批复验**6/6（4.3s）**：Tab/ShiftTab/Enter/Space/Esc/终态安全焦点、空白/1001emoji/FEFF组合原因、390完整20项及execution与sync分离、dirty关闭、terminal/readonly、ACK unknown原键恢复、404不推失败、版本/终态/损坏绑定冲突与401清缓存。全用注入response；业务API/非GET/站外网络请求均0，没有把Mock当真实结果。26合同最终复验另见实际回执。

Production build/typecheck/schema18 check实际通过；独占Next3490由Playwright `reuseExistingServer=false`启动/停止，结束lsof3490无listener，无PG/API/Worker。只headless独立browser/context，不涉及用户Chrome/OS键鼠/可见浏览器/缩放试验；trace/video/自动截图off，显式Mock截图items390和resolve1440已检查，非新设计批次。必要命令：

```sh
COMMERCEOPS_WEB_BATCH=b04-offline PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run test:contract
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run typecheck
PATH="$PWD/.tools/node/bin:$PATH" NEXT_TELEMETRY_DISABLED=1 npm --prefix frontend run build
# 从frontend目录，临时PATH指向项目自有.tools/node/bin
npm exec -- playwright test --config playwright.b04-offline.config.ts
```

证据在frontend/evidence/b04-offline/。最终敏感扫描/本地提交以工具回执为准；本批不推送、不触发CI、不合main、不标B04/阶段Gate通过。等Root给A03已审稳定SHA后普通merge，再同步完整22 runtime schema、真实Web/PG/Unicode/wire、独审和新精确CI，同PR36完整交付。人工H/L not_reported；估计0.75–1.5 Agent有效小时+机器检查计原B18/60/300容量，无新增预算、原日期不重置。

B04首敏感扫描dir/index各3、git0，仅request_key/stock_pool_key相等判断的符号引用误报；在未提交状态用正常字段解构/别名保持绑定，未改规则/新增豁免，首摘要保留。另核Mock20项导航，固定20个可见ID均有对应离线详情；不是任意对象/真实接口访问。最终组件build/合同/UI复核按最新回执。


## B04 已审业务源码代码接线批

Root放行精确748879e63c07185ae8c6f150827b7860ea66621e业务/API冻结（tree634d77b5925552b211b3219b7998447033d33fc2），从a82正常merge为05aa208181e62ff0a6b27abe56ab173a382a67d7；backend tree4519c7bb09e4f1eda9096e21224299b06abda66d与748相同。未读A WIP/私有目录，不改backend/DTO/Worker/Graph/共享CI/锁。完整22-response schema同步；readonly types按原生成器复生无byte差，未知路径/方法继续before-send拒绝。

接入task/events永久execution、server范围items分页/filter、单项detail/complete/close与resolve原receipt。current can_resolve与item版本由server判断，来源nullptr不猜旧task/plan链接；迟来approver无需读取无权的来源task便可按当前item权限处理。原approval意见回执不推断当前执行状态，任务/永久执行/每项终态/sync分记；无用户execute/retry或平台sender。

预备/unknown原请求在focus/可见性刷新时保留，仍GET当前session重查identity；401/403或200响应出现不同principal/org/auth_version时清全部业务/预备操作。原T1/T3亦采用此保留约束；每个新任务、新周期仍新key/空确认，不复用旧approval/nonce/hash。T6 Python3.12 strip、UTF8语义字段与server digest沿用已审合同，UI不计算权限或权威hash。

新增明确Mock wrapper只在server-gated UI_MODE=mock + MOCK_BATCH=b04-wiring + operator样例入口传入memory adapter复用正式LiveConsole加载/刷新/导航逻辑；实际live入口无factory/fixture flag，不回退Mock。API base为空，无cookie身份/backend/PG/Worker，全部API响应只内存注入；固定fixture角色按T6 approver字段构造，不代表鉴权Gate。26合同通过（2.9s），新headless联动UI8/8（20.8s）：原6纯组件语义、范围筛选/hidden source、unknown focus保原key及200身份变化清原操作，390/20末项/键盘/终态等。Mock Next3490两次PID67809/68418已停止/absent，无listener，时间/BUILD_ID见b04-wiring/mock-service*.json；业务API/nonGET/external0。类型/build/schema22通过；a82旧证据保留，新结果单独保存。标题纯文本修正后另build/typecheck，实际UI结果对应前一测试build，未冒称重复业务。

真实items.spec与窗口PID/origin/build/绝对期限/自然登录限流guards已准备，尚未执行。并发/撤权/ACK/native200/newcycle等真实样本需在Root放行的新窗口绑定本批新对象，旧B03 20collector若与baseline重观测不一致须真实needs_reapproval，不能冒称20项T4成功。本批仅代码/Mock，Root新052 CI-only放行后正常合入再真实联调；当前真实部分not_run，不标完整B04/Stage/main完成。

## B04 真实接线与可复现入口收口

本节为上述准备批之后的实际回执。Root核定稳定CI-only `052d4ecb9e24a8c8164938c1d7bb20a92ba89c3e`（parent748、treee383962）及精确CI38079599247全部成功后，原WT正常merge为 `bc15c2a300d626dfc91010d8c9de020a9455d5c2`。backend tree仍为4519c7bb09e4f1eda9096e21224299b06abda66d，与748业务冻结逐字相同；B未修改backend/共享DTO/迁移/Worker/Graph/根CI/Compose/Python锁。B实际业务Gate、独审、最终精确CI和阶段验收分别记账。

首次自有窗口p3b04-a8953024bc98于19:47:56.049905Z登记，原absolute stop21:17:56.049905Z保持；PG54481/API3501/Next3500全loopback，700目录/600私有文件。首次种子已经完成20项T4（20×100=2000），template-only解释已排队，记录model_calls0；窗口控制程序将Decimal数量写JSON时TypeError，故API/Next/Worker停止、PGfalse/PID0、保卷，PW未启动。一次转换修复后同卷/同截止恢复，没有重新seed/执行/清决定；template job实际done才启用后续测试。单Worker把初始与执行前重观察都绑定到相同明确20SKU collector；不绕过Worker/Graph/版本/权限/执行事务。template-only不读模型key、不调用provider。

首实际items全7为6passed/1failed（44.57s）；失败仅历史/缓存断言寻找不存在的字面量template，页面实际显示已有解释记录。测试断言修正后只重跑该只读tail，passed（suite150.42s含自然限流等待），先前approver已真实撤权，没有恢复权限或重做有副作用用例。联合覆盖永久执行与20项分页/390末项、Python strip Unicode组合原因、原键十次回放/一次v1→v2、迟来approver无权来源但有当前item处理权、operator只读/admin运维壳、真实commit后受控ACK丢失unknown保持原字节/GET恢复、两个当前approver同v1相反动作只有一胜者、旧版/dual隔离/缓存GET不新增模型/新周期新key、预备后真实撤权401清业务与原操作。原失败与tail回执分别保留，未称首轮7/7。

该窗口只读PG核20items/4terminal/1decision/model_calls0：resolve completed/v2、hidden-source/unknown/concurrent closed/v2，revoked保持open/v1。原窗口20:03:08.026226Z停止，全部已知child reaped，PGfalse/PID0，volume保留。原首失败与资源回执见b04-wiring/first-T4.json、live-first-stop.json与b04-live/resource-window-first.json、pg-first-complete.json。

真正native200%本批19:53:35Z实际passed：headless私有临时profile、无权限MV3 `chrome.tabs.setZoom(2)`后台tab，getZoom2、1440→720、DPR1→2、visualScale1、scrollWidth720、完整20行；CDP头尾安全截图已检查，profile最后删除，browser关闭。不是CSS/device仿真，也没有可见browser、OS键鼠/焦点或用户Chrome/profile。B03先前partial/failed证据保持，不用此回执改写旧批结果。

Root另要求项目专用薄CLI串行read/write/items，每段独立新PG卷/org/account/facts，避免前段撤权/终态污染。首共同截止20:41Z（作者登记，不声称已实测CI23min）的入口运行read完整7/7（28.50s）；write首8passed/2failed（333.16s），两个受控PG helper仍只允许旧p3b03-前缀，真实superseded/撤权断言未被执行。仅扩展明确p3b04-write-前缀后尾跑write完整10/10（326.89s）；受控superseded/真实撤权均保留，A业务状态机/权限无改动。首两个项目与尾跑write全部停/reaped/PGfalse/PID0/model_calls0。首失败batch-first*.json及write/live-first-run.json不覆盖；B03原截图/摘要保持原Git blob，新批另存b04-live/write。

最终薄入口`tests/e2e/web/run_live_batches.py`只复用现有种子、单Worker、配置、ready/PG probe、Playwright/reporter，不建立通用资源框架。外部第一步传不可变UTC截止（CI计划从第一步23min预算，job25min，由A维护CI）；脚本每段扣至少75s清理预留，不重置日期或预算，任何失败停止后续段并保留卷/私有事实。read/write/items分别新project/端口/org/account，空Compose env-file，不读.env；生产BUILD_ID与API/Next精确独占PID在用例前核对。trace/video/自动screenshot/HAR均off；结果只白名单名称/状态/耗时/源码位置，不复制原始error/body/token/nonce/password。业务API为真实session/CSRF/Origin，电商来源明确Mock fixture，ACK是受控transport故障，superseded是owned PG fixture；均不宣称自然故障或外部真实采购/库存。

闭合owner为`--owner b`（phase3-B-WTa266）、`--owner reviewer`（phase3-WebReviewer）、`--owner ci`（phase3-WebCI）。每次新登记保存实际UID、checkout、绝对私有目录与原截止；helper核当前执行checkout/UID、700当前UID目录、项目段及三类owner，未知/旧资源拒绝。这只是测试资源归属，不改变业务身份。10/10纯离线反例覆盖三类正向与陌生owner/UID/checkout/private/project/权限拒绝。首普通owner字段误报1已在未提交状态收口，规则/豁免/历史未改，随后三scope实际0。

独审/CI应在其自己的精确checkout构建后运行，不能用作者私有目录：

```sh
# WEB_STOP_AT_UTC由最早的任务步骤登记；不得在准备完成后重新计时。
PYTHONPATH="$PWD" uv run --frozen python tests/e2e/web/run_live_batches.py \
  --checkout "$PWD" --private-directory "$PWD/runtime/web-fresh-private" \
  --owner reviewer --stop-at-utc "$WEB_STOP_AT_UTC"
# CI同一完整入口仅将owner改为ci；目录须新建或为空的0700目录。
```

最终接线/完整入口实际结果、PG白名单不变量、最终quality/扫描与source冻结以本节后续最终回执为准。人工H/L仍not_reported，原B18/60/300容量和目标日期不重置；B不直接合main，完整Phase3仍由Root核必要Gate/独审/精确CI。

最终入口write段已核7只读之后完整10/10（327.17s）与PG不变量通过：approve实际completed；combined20与unknown因此段仍使用原B03受控初始来源、官方baseline执行前重观察而实际needs_reapproval/DATA_INCOMPLETE，未用同数量或审批成功推断20项执行成功。reject/decline/second_combined实际rejected；revocation/supersede仍awaiting_approval且决定0，expiry实际expired且决定0。六个有效意见各decision/audit/resume_job=1，P2源仍completed，model_calls0，app三个高权限flag均false。永久20项T4另由items段的明确同源collector和实际execution/items事务核证，两个证据不混用。

最终同一完整入口自20:24:18.490588Z开始，read **7/7（28.414s）**、write **10/10（327.172s）**、items **7/7（327.039s）** 全部通过，后两段包含真实300s登录滑窗等待。三段分别p3b04-read-bdf0d913a8、p3b04-write-bd5594d797、p3b04-items-e3696cd769，各新卷/账号/org/facts；共同stop20:41Z未延长，最后项目20:36:33Z前已停止，整个入口约12m14s（不包含之前依赖/build准备），不得外推为精确CI23min/整个job25min已通过。脚本中至少75s清理预留实际保留；seed/test/辅助命令/服务均登记独立新process group，先退出seed再起连续Worker。最终全部已知child reaped、owned listener0、PGfalse/PID0，volume保留。

最终items PG核：20items/2000units/4terminal、task completed及永久completed execution恰1；resolve completed/v2，hidden-source与unknown closed/v2，concurrent本轮completed/v2（另一方版本/状态冲突，不固定谁赢）；四项每份原receipt/audit/version2 item_projection恰1，UTF8 compact/sorted字段canonical SHA256逐项相同，sender disabled/external_id null。撤权项保持open/v1，receipt/audit/v2projection均0。全部model_calls与actual_provider_calls0，app高权限flag全false。20项实际T4与T6事务核证在batch-final-items-window.json，不以Mock UI或旧审批意见代替。

最终native200自动在items完整7之后、PG停之前实际passed，仍headless无权限MV3背景tab与私有临时profile，getZoom2/1440→720/DPR1→2/visualScale1/20行/无横溢出，安全头尾截图再次核查；finally关闭browser并删profile。first-actual-zoom*.json/png保留首次19:53通过的另一自有窗口证据，新actual-zoom*.json/png绑定最后project/PID/build。

最终合同复验26/26（2.8s）/22-operation schema check/typecheck及10/10owner反例、14个专用Python文件Ruff/mypy通过。正式Mock UI8/8仍使用先前明确Mock production回执，没有把实际Web结果算入Mock批。运行时HEAD为bc15基线加待提交辅助文件，三段登记13文件SHA256共39次逐项核同最后待提交blob；UI产品app/components/lib/public/npm锁相对bc15无差、production BUILD_ID 9fUL_TyAtnwYQ9NJLHijq，不宣称运行开始时已经存在最终提交SHA。最终source SHA/tree与精确CI见同PR36/GitHub实时回执，独审和整体Stage Gate仍待Root。

最终完整 `uv run --frozen python -m scripts.check` 实际exit0：**1057 offline passed / 337 integration deselected / 84.22s**，两个既有lark-oapi弃用warning；锁一致、68Markdown0、Ruff全仓lint/format、mypy、Node24.21工具链/frontend typecheck、npm audit0及95Python锁包漏洞0。开始前全部自有live资源已停止，不用npm ci干扰采证；前序production build/26合同/Mock8UI与本次真实完整24+native200均分开记账。该check没有执行337后端integration；已审A03根CI实际337 PG证据仅按Root冻结继承，组合最终CI仍待实时回执。首普通owner字段扫描误报1保留说明，未提交状态已修；最后提交前与提交后完整三scope结果以Git/PR回执记录，不提前声称未来扫描完成。
