# V4 natural_ttl 3dd独立模式审查

日期：2026-11-04（Asia/Taipei）。**结论：P2_REQUIRED_CHANGES，0 P1 / 1 P2；natural_ttl新增模式暂不签准备接受。** 不撤销8196已接受的11个HTTP场景；ROOT明确授权的45分钟外层上限与固定业务30分钟本身没有被判为缺陷。

candidate `3dd1d2b880c35601cbb7482a2c29c6877603640f` / tree `0bb240eccb9a418128502c8a8efa46132433b690`，parent8196。只读6个已提交TTL增量及原supervisor调用链；未读browserMode或容量WIP。未等待真实30分钟、未连接PG/HTTP、未启动服务。

## TTL-01 [P2] 已取得的TTL事实只在finally写入，正常监督终止会丢部分证据

位置：`tests/e2e/v4/ttl_probe.py:run_natural_ttl`中observation.update/等待阶段与末尾finally；原Supervisor._stop发送SIGTERM后至多2秒再SIGKILL。

初始PG facts与API expiry核验后仅保存在内存，before/after也如此；直到成功或Python异常退出的finally才O_EXCL写natural_ttl.safe.json。默认SIGTERM会直接终止Python，不执行该finally。该信号正是现有supervisor在绝对工作截止/外层停止时采用的正常机制，所以一个已消耗大量自然等待时间的失败case可以只剩父进程native -15和observer的action/native记录，却丢失已观测的created/expires/DB UTC。observer安全日志不保存facts payload，不能补回这些事实。

独立精确源码纯子进程复现：合成Visitor/PG facts完成initial验证，进入wait替身后向自身发送SIGTERM，native -15、natural_ttl.safe.json不存在；同一点改抛TimeoutError时native1、文件存在且UNKNOWN/initial保留。两条均无网络/DB/真实等待，也没有把SIGTERM说成业务断言失败。现有13项TTL纯测试只测verify_ttl等，不覆盖这一执行中断路径。

最小修正：在长等待前即独占持久化初始安全事实，并在before/after阶段取得事实后分别写新的固定安全stage文件或采用有审计记录的原子更新；默认状态保持UNKNOWN，只有全部到期断言完成才能追加成功回执。应确保父最终receipt能定位这些stage事实，丢最终文件仍明确非成功。不要延迟/吞掉SIGTERM、延长窗口或为了补证据重开业务请求；仅加signal handler也不能替代SIGKILL前已经落盘的阶段事实。补完整子进程SIGTERM中断及正常Python异常测试，要求initial事实留存且从不产生成功标签。

## 已核TTL与资源边界

Case仅在scenario=natural_ttl允许总窗口≤2700秒，其余仍≤1800；Budget.reserve=180不变，ROOT具体新project/source/image/端口/UTC仍需逐case绑定。TTL模式不绑定或启动Web，web_port只为manifest兼容保留，api foreground/禁pull-build/停止及最终PG清理沿用已审8196路径，没有新增后台服务。

PG ttl observer使用固定参数化SELECT读取本tenant及DemoSession的created/expires、revoked布尔与clock_timestamp，不读token/凭据，不UPDATE时间；经DesignPgFacts._row真正只读事务与SQL timeout。verify_ttl要求精确字段、目标tenant、两者未撤销、恰30分钟、两created/expires相同、API expiry等于DB、initial DB时刻未到期；工作截止必须至少expiry+60秒且另留180秒清理，initial余量少于60秒拒绝，不续窗。

等待以已取得DB余量映射到monotonic，单次sleep≤30秒且反复核budget；不轮询业务或PG。到期前目标30秒取DB事实并GET current，必须DB仍在expiry前、响应authorized_at也在expiry前；到期后取DB事实要求DB已跨原expiry，除db_utc外原创建/期限/撤销事实全部不变。随后current、原两店及原creation receipt都必须401且code为SESSION_INVALID/EXPIRED。没有改短TTL、宿主时钟伪造DB timestamp、自动bootstrap或重试POST。

本模式仍是固定隔离环境中的自然到期观察，不凭泛化SESSION_INVALID证明任意环境所有鉴权错误均由TTL导致；同case不应并行进行owner撤权造态，ROOT Full若并行必须使用独立资源。错过边界、DB/传输/Python异常不会设置成功标签；TTL-01是部分事实保留的缺口，不是发现代码把失败伪造为成功。

## 独立验证与交接

精确3dd快照下原driver13+修复15+TTL13：**41 passed / 0.23s / native0**。另上述合成子进程SIGTERM/Python异常对照完成；所有临时文件已清理。未启动浏览器、容器、PG或API，未等待自然30分钟，真实SQL/HTTP/TTL事实仍NOT_RUN。ROOT先前native delta2与pilot安排不转记到本模式。

请QA仅补阶段证据持久化及中断测试后交普通精确commit；修复复审前不要用本模式消耗45分钟自然窗口。原11HTTP准备接受继续有效，browserMode/200%真实GUI与Full保持独立，不能由TTL纯测试代签。


## 385最小修复复审：TTL-01关闭

日期：2026-11-04（Asia/Taipei）。candidate `385c35599fc57a33ae2ebeeef881c6a4b8a1cbcc` / tree `8ecc9d42942865a343712cf49e9abc39261de3d4`，parent `f24ce12e4c8414978603f6b86c1ec633e8a10c19`。本次仅审4文件的TTL持久化增量，不将parent链中的browser模式或其他功能纳入本回执。**结论：TTL-01 CLOSED，增量0 P1 / 0 P2；ACCEPT_PREPARED_NATURAL_TTL_MODE。** 原3dd中断丢initial的反例保留。可以交ROOT为独立natural_ttl资源登记具体窗口，不自行启动资源或预签自然到期PASS。

新persist使用固定stage路径、O_CREAT|O_EXCL|O_NOFOLLOW、0600，写完flush/fsync文件并fsync父目录；已有文件拒绝覆盖。initial在第一次PG事实取得后、verify及长等待之前写出，before/after也各在事实取得后立即写出。初始和各阶段均保持UNKNOWN，错误事实也只作为UNKNOWN原始观察保留，不能因文件存在就记通过。

finally仍负责close和UNKNOWN摘要，但阶段取证已不依赖finally。只有全部TTL断言、预算检查、Python清理和摘要持久化都正常完成，函数才在finally之后追加独立natural_ttl.success.safe.json，标NATURAL_TTL_OBSERVED_PENDING_REVIEW；原UNKNOWN文件不改写。若中断/close/写盘错误传播，不能到达该成功写入。没有signal handler、延迟SIGTERM、重发POST或续窗；SIGKILL仍可能打断当前一次写入，ROOT应要求完整可解析阶段文件并结合native exit，而非凭success路径存在签PASS。

父execute回执新增ttl_planned_evidence_paths，明确列initial/before/after/success固定路径且只对natural_ttl填写；这是计划定位，不宣称各文件已经生成。父退出/cleanup失败与子native -15仍必须按实际保存，不能由存在initial文件解除运行失败。业务30分钟、TTL≤2700秒、其他场景≤1800秒及reserve180均未改变；本补丁没有改变等待或到期判据。

独立导出精确385源码快照，只运行test_ttl_probe.py，父测试进程psycopg.connect设为禁止调用：**16 PASS / 0.29s / native0**。其中完整合成子进程的SIGTERM实际-15、Python异常实际1，均验证initial UNKNOWN/原key仍在、0600、无success或任何成功标签；另验证stage不可覆盖。未等待真实30分钟、未访问HTTP/PG或启动浏览器/容器，临时文件已清理。未复跑无关driver/browser测试。

本回执仅关闭阶段证据保留缺陷并接受原natural_ttl准备模式。ROOT仍须绑定已审集成source/image、独立project/DB/API与具体UTC，确认pilot及所需运行前置条件后执行；与其它资源的Full PG回归分账。实际到期前/后DB时间、401及最终cleanup须新回执，不能从纯测试或准备接受推断完成。
