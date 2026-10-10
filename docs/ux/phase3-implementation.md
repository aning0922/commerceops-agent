# Phase3 冻结 M1 前端实施

当前包含已核 B01 离线 Mock 页面、已核 `14dc` 离线类型/transport，以及本批 **B02 真实 PG 会话与只读页面候选**。本批正常合并已审 A01 `aeaa916`，登录/读取已在自有资源实跑；创建/决定/执行/resolve仍等待对应已审功能。新冻结独审/组合CI与Root签收以PR实时回执为准，不能当完整B02或Phase3完成。早期章节保留B01历史范围，当前只读批见末节。Issue [#33](https://github.com/aning0922/commerceops-agent/issues/33)、[#35](https://github.com/aning0922/commerceops-agent/issues/35) 为本阶段授权与文件所有权依据；本 PR 仅 Refs，不关闭阶段。

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
