# V41 Shell NoDefaults IPC 与生命周期独审

日期：2026-11-04（台北）。结论：`ACCEPT_SOURCE_AND_BOUNDED_PURE_COMPONENTS_RUNTIME_NOT_RUN`。本次精确六文件候选无实质 P1/P2，可由 Root 普通集成；不签真实 browser/hidden/native exit、完整工程或阶段完成，也不释放运行资源。

source `c154777f8689da589a25a253a6c234bfb7891444` / tree `154bce6b6d82c3ccaf367e92ea7fc75773457391`，精确父 `4fec4a7416d7b9434d979f461d5da78508cfb850`。差分只有 owned-cdp argv/fixture、Shell spec、Node component test、browser_shell.py 及其pure tests，743+/6-；未改产品、业务spec、数据库、依赖锁或旧Native模块。

## 关键检查

1. **首次 attach 的父握手。** fixture先严格读取原case17字段、原runtime/source/tree/UID/project与固定PW版本，核CFT executable/framework/Node hash；新700私有profile、nonce、worker PID/birth及完整argv先写intent，原生spawn后写native PID。父从原case/runtime字节hash复核intent，独立ps检查worker ancestry到原Node PID/birth、native PID/PGID/birth与同UID成员、原binary/profile/完整argv；先持久registered，再检查DevToolsActivePort的规范两行、owner/mode/非链接及实际127.0.0.1精确端口监听PID，二次核native行未变才写ACK。现有ACK不刷新或续期。fixture等待原ACK且核完整identity/native PID/birth后仅一次connectOverCDP，不通过HTTP发现任意endpoint，无connect重试或fallback。文件fsync与原子rename是当前实现事实，不扩称目录断电恢复已验证。
2. **既有context/page与归属。** Shell专用fixture限定原标题，只消费唯一已存在default context与唯一about:blank页面，不创建替代context/page。记录实际target、window和可选browserContextId的presence/value；缺省ID合法并严格保留absence，出现时必须非空字符串。后续verify同时核case/runtime/ACK hash、唯一context/page对象、target/origin、context ID及window，未通过删除旧guard来放宽归属。三个goto改绝对127地址，reduced-motion通过公开emulateMedia恢复。
3. **NoDefaults依据。** 只读本机已安装playwright-core 1.64.0的coreBundle：默认focus override仅在非skipDefaultOverrides时执行，skip条件为noDefaults且当前context为默认context。候选使用公开connectOverCDP的noDefaults和公开CDP session接口，不调用PW私有primary session，不注入visibility事件或覆盖document属性。此源码依据支持接线目的，不保证实际CFT最小化一定hidden。
4. **原Shell Gate保留。** offline由真实setOffline及navigator.onLine核验；DOM includeHidden清除/cookie不变、恢复reload对应GET的五身份字段/creation key/create1、零额外POST、原Native及迟到ACK断言均保留。hidden前后核同target/window；真实minimized与document.hidden确认后检查DOM/cookie，再次确认仍minimized/hidden。finally恢复normal/visible，随后原GET恢复，不用截图或背景导致的可见性变化代替DOM移除。
5. **关闭与失败分账。** usingOwnedContext的finally覆盖setup/use失败；记录failure阶段，显式Browser.close ACK、CFT child原生exit与signal分列，限定native0/null才给NATIVE_CLOSED_PENDING_PARENT_CHECK。父另外消费bound page proof、ACK hash及独立native-exit文件，原Node退出记录/原两标题结果/wrapper native状态不由CFT退出代签。setup未连接、close异常、native UNKNOWN/非零/信号均失败；父按已登记连续PID/birth/PGID组清理，forced或remaining仍FAIL。精确ACK端口若存活或被复用则拒绝清理成功，不按端口向未知进程发信号。缺ACK或无法确认归属继续UNKNOWN/失败，不推断资源已关。

## 独立验证与边界

从精确Git archive创建新的review-owned临时源码树 `/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/v41-c154-review-0pdbw6h9`，未读作者工作树/WIP。使用现有锁定Python，仅运行 `tests/e2e/v41/test_browser_shell.py -k shell_cdp`：11 passed、22 deselected、0.42秒、native0。覆盖规范endpoint/链接拒绝、精确监听端口、复用端口不signal、birth/ancestry/native PID/argv/listener漂移、ACK保持原bytes、case/runtime/source/profile绑定及关闭原件拒绝。系统进程与监听调用在这些检查中使用mock，没有实际ps/lsof、信号或浏览器。

精确 `frontend/v41-tests/owned-cdp.fixture.test.mjs` 通过2项、native0，验证ACK漂移在connect前拒绝，以及setup/use/close异常均执行close且失败传播。此测试抽取原validator/lifecycle函数执行，未加载Playwright fixture、未启动资源；Node的stripTypeScriptTypes实验性提示保留。它不证明真实浏览器close ACK或原生退出。

源码SHA256：owned-cdp.fixture.ts `d05a1bb0079973fb77cf73ac8dd738958875205646d149e001401bd8c646b741`；browser_shell.py `12b453c7be0f6a9e5a921caaca874af0670a8951b1da1c7666ec13663b9b4765`；argv JSON `2803e2a82a61fab00484206898f6bd4eccbc07c0f9bbd1d500ebed6089c2b77e`；Shell spec `47cab3702a19d4ffe47dc104ebec54d3079951726f612aa43e6af841a5b2c7e0`。本机只读PW coreBundle SHA256 `2325ca4c1c83070e89dc49fb82525508f0a68e0cf12e2a624277968da216b7e0`；该本机解释依据不是未来实际runtime binding。

作者150pure/2Node/TS/mypy/Ruff/两标题collect全0是Root转交作者结果，本轮未重复完整矩阵或代签其原日志；开发首错原件继续保留，摘要不替代原始工具输出。browser6最小化读回通过而visibility仍visible的整案FAIL不改写，旧e466 business partial与4fec工程按原source分账，不挂到c154。真实NoDefaults attach、hidden清屏、完整Native/lateACK及关闭均待Root实际新案证据。

本轮未运行浏览器、服务、PG、Docker、build、collection、Full、CI、SDK或网络；只新增本审查文档，提交前执行指定changed-file/index预检，普通commit且不push。
