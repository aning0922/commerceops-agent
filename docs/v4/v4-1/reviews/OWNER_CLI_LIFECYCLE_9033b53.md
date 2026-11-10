# V41 owner CLI与新增live-child lease候选复审

日期：2026-11-04（台北）。source `9033b53888815769523a73ba294cef4f82f2b523`，tree `39e9a15f0ff89abaaf66ef42e5d95d80e430c575`，parent `e8ec8fe9c15e938f4e4c77732f77795392e0e165`。完整读取相对405f5e3六文件增量、Dockerfile/安装配置及相关私配/helper路径；未读GC或其他WIP。

结论：ACCEPT_OWNER_CLI_REFUSAL_PREPARATION / ACCEPT_LIVE_LEASE_TEST_CANDIDATE / HOLD_ARCHIVE_IMAGE_CLI。新增lease测试作为实际PG候选可核收，未执行；owner CLI在现有非editable archive镜像中存在确定性来源绑定阻断P2-C01。不能把10pure、23collect或metadata inspect当新DB owner操作/ACL接受。

## P2-C01：安装模块位置与Git源码根假设不兼容实际镜像

v41_database.source第74行把__file__.resolve().parents[4]当源码Git根，并要求manifest source_root与之相等，再调用真实git rev-parse/status。现行infrastructure/Dockerfile的runtime/test阶段均uv sync --no-editable；安装模块来自venv site-packages，不是/app/backend/src。常规路径/app/.venv/lib/python3.12/site-packages/commerceops/entrypoints/v41_database.py的parents[4]为/app/.venv/lib，不能匹配实际复制源码根/app。

此外镜像只COPY pyproject/uv.lock/.python-version、backend、tests、scripts，Root提供的构建源也是archive，没有.git。即使把根推断改为/app，Git HEAD/tree检查仍不能通过。独立精确archive复现：source_root如实绑定该archive目录，真实git -C rev-parse native128，在任何私配/DB读取前拒绝；没有fake git、复制/构造Git metadata或执行owner操作。安装路径推导另以纯Path模型核实，未冒称检查了运行镜像。

修复需要诚实区分checkout与构建artifact来源：保留本机真实checkout路径的严格Git核验，或另以Root已有精确build/source/image manifest和实际安装模块字节证明容器代码；不能加伪.git、假git shim、改source_root到venv子目录或无条件跳过来源验证。当前CLI不应写入QA可启动handoff，也不能只凭模块已存在解锁owner setup。

## owner CLI已核与未覆盖边界

严格manifest仅inspect/activate-policy/grant-runtime，包含operation_id、source commit/tree、固定schema、owner/demo/web配置hash与deadline。私有文件逐级no-follow/0600/current UID，owner密码文件另有bounded校验；runtime与owner host/port/name相同，runtime角色固定app，实际连接再次核current_database/current_user、0025、PG/vector及表owner。动作在一个事务中调用原已审helpers，提交前重核source与DB/host截止，成功退出context后才输出COMMITTED；异常统一UNKNOWN/retryable=false，不输出私有key或异常链。

这些防拒绝边界合理，但没有正向真实owner操作证据。inspect只读policy是否初始化/version/generation，不能充当完整owner_verify_cli：它不验证全部runtime表/列/函数ACL，也不证明当前config fingerprint与policy匹配。JSON配置hash并非所引用secret文件全部字节的封存；Root仍需按原私配seal绑定实际key/password及目标。CLI不提供持久once或原生绝对stop监督；失败stdout也不含原operation_id，外层必须预先保存operation manifest身份/hash与native回执，UNKNOWN只读核实，不换id自动重试。

Root已允许的内部helper固定recipe可作为独立路线继续准备：在已验证的精确source/image及实际安装模块下，保留真实owner/DB/config/窗口校验，调用已审activate_policy/grant_runtime并另核真实ACL。此路线不是伪造Git或owner bypass，也不能因本回执自行扩大grant或新增未登记资源。当前仅说明允许沿既有授权边界准备，具体recipe/资源/UTC与实际结果仍由Root核定；未审CLI适配不能替代它。

## 新live-child测试候选

新增PG节点先用可信私有binding随机真实lease建立并COMMIT reservation；攻击方只拿猜测lease，分别在未bind及实际bind/PID存在后调用bind/stop，要求明确V41_PARSE_LEASE_INVALID。伪publish用合法格式但错误双段binding，要求SESSION_INVALID；读回同job RUNNING、slot非空、stop_proof为空，再由owner撤credential并COMMIT。

随后正常run_parser实际Popen handle communicate/wait，stop回调先要求该PID已不存在，再用保留真实lease持久stop。要求native0/reaped、STOPPED/slot NULL、保存真实proof；撤权后即便拿原私有binding/lease，publish仍SESSION_INVALID且preview_data为空。没有把真实私有lease给攻击者再假称无能力低权，符合已审能力边界。

该测试确实补准备中的未bind/live伪lease拒绝与撤权后reap/publish路径，但尚未实际运行；硬2秒child budget中的连接/断言时间不预判可容纳，不放宽deadline来签成功。os.kill(pid,0)是该Popen PID的存活观察，非单独完整/proc birth证据；测试通过还依赖最终同handle native0，不能把一条kill0或reaped布尔单独称内核回收证明。它不代替SIGKILL父亡、GC/非demo回归或confirm撤权的全部矩阵。

HTTP/native原测试变更仅类型标注。没有业务SQL、HMAC、权限grant实现在此提交被改写；已审405最小编译/PG7代码边界不会因CLI准备而扩大或被冒签。

## 验证

独立精确git archive：test_owner_cli.py 10 passed / native0 / 1.39秒；test_business_pg.py 23 collected / native0 / 1.50秒，仅collect、没有fixture；archive真实Git来源拒绝与wheel路径模型复现native0（内部预期Git128）。无warning。未运行PG、GRANT、Docker、native parser child、服务、浏览器、Full扫描或远端操作。
