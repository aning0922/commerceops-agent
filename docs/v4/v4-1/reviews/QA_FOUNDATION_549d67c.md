# V41 QA 监督基础独立审查

日期：2026-11-04（台北）。source `549d67c17a9e67448cacc0f29517de07af6e70d2`，tree `f212aaf2df3123fdcddb74cc4c155242f0a6c067`。完整读取本提交六文件：tests/e2e/v41的README、包初始化、process、runner、simulated_child、test_runner。没有读取WIP或把后续SHA混入。

结论：HOLD_SUPERVISION_EXCEPTION_RECEIPT（P2）；正常固定recipe的结构可保留，但异常身份探测会中断最终资源回执，需修复后作为可信监督基础集成。此片无真实SQL/API/browser能力，所有模拟不得计入V41业务Gate。

## P2-Q01：清理身份探测异常使最终回执缺失

`process.py:47`在已登记group仍存在时直接调用identity(pid)，没有捕获ps非零/超时。组长已退出但同组后代仍存活时，group_absent为false而按leader PID取birth失败；平台探测异常也会进入同类路径。`runner.py:171`在finally中直接调用stop_registered，异常会跳过`:200`的outer.json持久化，从而失去worker实际退出、残余资源与未知清理状态的最终回执。

复现采用该精确提交AST中原stop_registered函数，临时目录仅一份登记JSON；group_absent桩返回false，identity桩抛CalledProcessError。实际结果为异常直接传播，未返回remaining列表。未启动任何进程/服务，故这是异常控制流纯复现，不是实际后代进程清理验证。

最小修复：按登记项捕获探测异常，不能确认身份则不signal、不报资源不存在，保留具体安全错误类别及UNKNOWN残余记录；单项失败不阻止其余可安全盘点。外层持久化应不受stop_registered异常影响，保留真实worker native exit并以非零结算清理未知。另将command的Popen后identity/注册写入纳入保证wait/reap的异常边界；当前`:93`只捕获CalledProcessError，TimeoutExpired或注册文件失败发生在其后wait/finally之前。补探测非零/超时、注册失败及组长退出的有限故障用例，不扩任意argv接口。

## 已核可保留内容

- 固定recipe和child mode白名单，不接受shell/任意命令；输入目录要求新绝对canonical路径，worker验证owner/0700，日志与JSON0600；绑定source/tree、输入和解释器hash并前后对照。
- probe native、observer原件存在、cleanup native、summary状态、worker native、outer CLI exit分层；information不混入required。observer0但无原件失败，cleanup4或summary失败不被checks_pass掩盖。
- checks持久化先于摘要，原子replace/fsync；正常finally执行group停止及wait，外层保留NOT_RUN stage_gate。源码测试覆盖六固定recipe及未知recipe/已有目录拒绝，但没有覆盖本P2异常路径。
- 原始业务UNKNOWN未被合成为COMMITTED；本片只记录进程模拟，不具业务回执语义。以后资源runner仍需Root绝对UTC/cleanup reserve/source绑定，不得直接拿当前25秒cap扩成服务窗口。

验证范围：完整静态审查及一次原函数AST纯异常复现；未运行固定recipe测试、ps/kill/受测子进程或任何服务，未核收作者执行次数。未知身份不得为清理方便而强杀；后续修复须单独精确SHA核验。本审查不重写V40原wrapper1/失败。
