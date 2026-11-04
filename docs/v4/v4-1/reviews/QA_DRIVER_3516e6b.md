# V41 owned lifecycle准备候选审查

日期：2026-11-04（台北）。source `3516e6bcda1b3badd18118b8805b5bc7ae62a03e` / tree `384b9ca2a06c6e351ee6af9d260439aaa2e637ac`。读取四文件增量及直接复用的V40 prepare/compose/model/image/ready、OwnedAdapter和Supervisor停止预算接缝。没有调用prepare/execute、Docker、HTTP或读取真实私配。

结论：HOLD_BEFORE_RUNTIME，准备骨架可继续，下面两项P2须在实际窗口前修。未就绪router/SQL/grant/handoff本身属于明确依赖，不因尚未实现而新增阻断；禁止补占位文件绕过。

## P2-D01：首次HTTP探测前没有实际监听归属证明

execute验证namespace初始为空和Compose声明，但在226/242行直接调用public.ready(API健康/Web页)。没有预先拒绝注册端口已被占用，也没有核实际监听属于本次API容器/本次Web进程。public.ready只证明所启动CLI/进程暂未退出与URL返回200；在绑定端口失败尚未退出的时间差内，旧listener仍可能满足ready，随后probe可能POST到无关演示服务。最终ports_closed失败来不及阻止先前访问。

最小修复：启动前明确拒绝已有监听，并在首次HTTP前核本次服务真实运行/端口绑定与owned身份，不能把存活的compose客户端等同API监听者。Web同理。占用/归属未知直接HOLD，不探测旧服务、更不发送业务请求。用无外部资源的控制流反例覆盖错误listener不会触发probe，实际窗再核真实绑定。

## P2-D02：终态证据不足以绑定完整运行来源和业务结果

初次case.validate核HEAD/tree/clean和五项输入，结束时没有对应source/input/private-seal复核；report仍输出初始source值。最终事实阶段301行只运行pg_observer schema，不采已登记tenant/操作的终态业务事实，无法证明stopwriters后的最终效果与probe中途事实一致。

最小修复：在既定截止内保存末次源/关键输入与私配seal比对，变化明确失败/UNKNOWN；把probe创建的owned tenant与操作安全引用预登记并在writers确停之后、PG关闭之前采集实际业务终态，失败不得抑制down。schema可保留为一项，不能冒充所有终态业务证明。原来源不变/终态未捕获须如实分列，不凭初始Case或probe exit0补签。

## 可保留内容与限界

新Case namespace/DB、随机私配和seal、显式Root窗口开关、缺精确handoff在Docker前拒绝、一次execution marker、不可变UTC/180秒reserve、固定镜像ID和no-build/pull-never配置、scoped namespace初始空、停止writers/API/oneoff后再观察、finally scoped down/容器网络端口盘点和保卷方向可保留。故障安全细节仍需实际owned运行验证。

runtime_handoff目前仅检查固定接口/文件存在及seal，不是业务代码独审通过证明；必须由Root按已核SQL/router/grant候选创建真正handoff。实际IPAM/镜像架构/受测容器源码与host源码的对应也需进入运行准入证据，不能从配置模型单独推断。

本片源码测试只覆盖新私配prepare及缺handoff在Docker前阻断；没有执行本报告的runtime场景。本次只读审查，不把作者13项pure或旧V40运行转签为新lifecycle验证。Q01固定短进程修复不自动证明此新driver的所有异常路径。
