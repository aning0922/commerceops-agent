# Phase3 冻结 M1 前端实施

本交付是 **B01：真实 Next.js 页面上的离线 Mock UI**。B02 服务端会话与业务集成尚未开始，必须先收到总控下发的 A 合同/API 独审冻结 SHA。Issue [#33](https://github.com/aning0922/commerceops-agent/issues/33)、[#35](https://github.com/aning0922/commerceops-agent/issues/35) 为本阶段授权与文件所有权依据；本 PR 仅 Refs，不关闭阶段。

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

没有 API client、fetch、Server Action、真实 POST 或虚构 endpoint。页面与静态资源通过 Next.js 读取；实际 Playwright 监测中业务 API、非 GET 与站外请求均为零。所有资源仅固定模拟数据，未读 `.env` 或密钥，也未连接 P1/P2 PG、模型、飞书或电商服务。

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
