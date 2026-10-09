# Issue23 受控诊断记录

日期：2026-10-09（Asia/Shanghai）。任务 [Issue23](https://github.com/aning0922/commerceops-agent/issues/23)，异常 [CI37833575792](https://github.com/aning0922/commerceops-agent/actions/runs/37833575792)。**原 CI 的具体卡住用例及根因未定位，当前复验阻塞不解除。** 本地两轮成功不是原 CI 成功或故障修复证明。

## 隔离与预算

原 WT102d / codex/phase1-04-checkpoint / 9e21e27 保留。新的 managed Worktree 为 `/Users/aipuli/.codex/worktrees/phase1-ci-timeout-diagnostic/commerceops-agent`，分支 codex/phase1-ci-timeout-diagnostic，基线41323ec0d8a4ad1bd1b9a6eb2b70fc820f67ae94。所有本次编辑/实跑只在新WT，未读取P105私有配置/Secret/数据库/卷。

批准预算14:16:45–14:46:45，最多3轮；实际仅执行2轮，14:31左右决定停止，不进行无新线索的第三次重复。collection上限30秒、组上限300秒、支持单nodeid上限90秒和45秒无locals栈。没有延长budget或skip/修改原测试断言；没有修改Graph/Worker/迁移/权限/依赖锁/控制文档。

## 原异常来源

原PR22 head8f5572778d136ee2348915d60a419965db66c7be/base41323ec，实际checkout a6ee1108b593454a92e61974c6dd03e7a022e4d3，仅两份阶段文档差异。原run于03:39:30–04:04:50，终态cancelled，25分钟job上限；PGstep自03:41:19开始，03:42:14最后记录 real PG constraints and failure recovery，无pytest汇总或cleanup成功证据。终态完整log已保存本次WT受保护的忽略目录 `.audit/issue23/ci-terminal.log`，不上传原始运行文件。

源码可证：pg_smoke在compose返回后才打印capture_output；执行及cleanup无subprocess timeout。Graph finally新增async tasks等待和子barrier自身无期限，但父harness事件/OSwait有15秒上限，Worker故障取消有预算，故不能直接认定它们造成原CI超时。同步SQL/CREATE/DROP数据库没有显式语句期限，connect_timeout只约束连接。这些是等待/可观测性风险，不是已定位根因。

## 实际受控执行

仅新增 scripts/pg_diagnostic.py 和 tests/diagnostic_plugin.py 作为临时诊断工具。插件在test进程记录安全nodeid/setup-call-teardown；第1轮仅在两个测试harness的reader向原Queue转发事件时记录安全字段，第2轮关闭该reader替换。外层supervisor登记自建随机项目并有界执行compose，过滤输出，不采query/env/DSN/Secret或完整inspect。无平台API/真实审批，source_mode=postgres_technical/model_mode=not_used/approval_mode=simulated。

```sh
uv sync --frozen
uv run --frozen ruff check scripts/pg_diagnostic.py tests/diagnostic_plugin.py
uv run --frozen mypy scripts/pg_diagnostic.py tests/diagnostic_plugin.py
uv run --frozen python -m scripts.pg_diagnostic --deadline 2026-10-09T06:46:45+00:00 --round 1
uv run --frozen python -m scripts.pg_diagnostic --deadline 2026-10-09T06:46:45+00:00 --round 2 --combined --no-child-trace
```

第一轮14:23:43–14:25:05，项目p123-7ae309c36ba9：collection成功（79项）；分独立测试容器四组均exit0：test_postgres 13/0.33秒、test_worker_pg 19/7.09秒、test_checkpoint_pg 21/30.76秒、test_feishu_postgres 26/5.88秒。两个既有SDK DeprecationWarning保留。各组setup/call/teardown安全进度记录均已获得，没有超时。

第二轮14:27:42–14:28:56，项目p123-fa91acc375c7：完整tests collection、同pytest进程integration组合通过，79passed/140deselected/2warnings，47.26秒；不替换任何子事件Queue。此轮针对独立分组与原组合的进程/global collection差异，仍未复现长等待。没有原故障nodeid可供进一步缩小。

两轮各仅清理本轮登记项目/卷/构建镜像/秘密文件，cleanup_exit=0；14:31用各自project label过滤检查，容器/volume结果均为空。没有操作未知资源，也没有使用prune/killall。结构化逐项记录见 [CI_TIMEOUT_DIAGNOSTIC.json](CI_TIMEOUT_DIAGNOSTIC.json)：两轮每个nodeid的setup/call/teardown开始/结束、pytest PID、duration、outcome均已导出；未包含SQL query、env、DSN或错误原文。原详细安全事件流保留 `.audit/issue23/round-1.json` / round-2.json及stream日志，不上传。

## 限制与停止结论

没有触发超时采样，**未获得卡住时的PG wait/blocking PID/事务年龄快照**，也没有触发45秒栈；不能由成功进度猜数据库锁或async task根因。诊断工具的正常路径实际运行，失败终止/timeout分支尚未以故障注入验证，不能宣称它已是验收通过的正式安全修复。初期工具lint/type assignment问题已修正，只说明工具检查结果，不是原CI缺陷。

未进行正式业务修复，未推送/创建修复PR或rerun原CI，未改共享锁/业务状态机。2026-10-09主控批准将这四个最小文件保存为本地冻结提交供独立审核，提交前再次检查差异及dir/index/可达历史敏感信息；该review candidate不代表修复或Gate通过。诊断现停止，Issue23仍待主控决定后续可观测性补强及受控环境复现；仍须明确证据、必要实际组合/G1/G2、独立Review和精确CI后才能解除阻塞。未知停止不释放业务槽、不伪造死亡或正常退出，G3/main/Phase2边界保持。


## 第二段授权与诊断工具P1修正（2026-10-09）

主控转发用户新授权：15:02:35–15:32:35，本地最多30分钟、两轮，独立复审后最多一次CI；原quality25分钟上限不变，失败不自动重复。独立审核指出c959工具timeout的sample/inspect异常会绕过killpg/OSwait；**该P1是新增诊断工具问题，不是原CI根因**。

最小修正：抽出仅此诊断使用的pg_diag_shutdown；任何观察异常之后无条件finally处理自有CLI group TERM/必要KILL/OSwait。label未核验不stop；stop后仍活才kill，Docker wait成功且running=false才确认。reader必须结束才close，否则停止证据不确认。共享cleanup绝对期限不max1秒重置；正常命令的短停止核验期限与真正清理期限分开，避免初始化时误启动总cleanup倒计时。过期入口不注册或创建资源。日志失败不能阻止终止但总体证据不确认；KILL时进程恰好已退出仍OSwait。

第一轮15:12:46–15:13:10，p123-090cba6d67dd：新自有容器中Python故意卡住/忽略TERM，采样函数故意抛受控RuntimeError；另有本次自有CLI wrapper拒绝TERM。2秒诊断期限触发，容器经label核验stop、Docker wait确认exit137；CLI PID92718 TERM后必要KILL，OSwait确认exit-9；reader_end=true、stopping_confirmed=true、cleanup_exit0。该expected_diagnostic_timeout_confirmed仅表示诊断注入停止证据，不是业务Worker停止/恢复成功。之后按仅该project label查询，容器/卷为空、runtime秘密目录删除。

第二轮15:15:51–15:17:32，p123-65bd2e2fd2a7：新完整有界入口保留双初始化和原79 integration断言；79passed/150deselected/2warnings，42.06秒，六条G2结构化记录。保留G1 seed、PG重启、同卷重建、停库revision非零、恢复回读；task/thread18a4fc37-898b-4b06-a513-e136b6e8c4a5三次inbox/jobs/audit=1。所有CLI OSwait/reader确认，g1_complete=true/cleanup0，专属label容器/卷为空、秘密目录删除。未复现原长等待。

工具纯fake覆盖sample/inspect/label异常不漏TERM/KILL/wait、未确认reader不close/不报确认、绝对期限过期不重置、foreign label不操作、已停止容器不kill、wait失败不确认。实跑后补日志失败/KILL竞态和入口过期防御，由fake回归覆盖，没有新增第三轮Docker。日志/竞态防御不改变已实测正常和受控sample异常的终止顺序；独立复审须明确区分这些证据来源。

13项fake回归与新代码lint/format/mypy64文件实际通过。统一scripts.check在入口过期用例加入前实际152offline/55.11秒，79integration deselect、2既有warning，25Markdown/Node24.21.0/TypeScript及90Python包/npm漏洞查询0；新增过期用例后全offline再次实际复验，153passed（79integration deselect），具体耗时见最终回执；不以旧152项覆盖新增用例。无依赖/migration/权限/Graph/Worker/原pg_smoke/quality或阶段控制文档修改。结构化停止与G1/G2记录见 [CI_TIMEOUT_DIAGNOSTIC_FOLLOWUP.json](CI_TIMEOUT_DIAGNOSTIC_FOLLOWUP.json)。

拟唯一CI入口（须增量独立Review和主控核对后才启用，当前不推送）：在job最早的普通shell步骤保存当前UTC+23分钟的绝对预算文件，PG步骤调用pg_diagnostic --session ci --round1 --combined --full-smoke --no-child-trace --deadline该文件；原Foundation checks保留、job timeout-minutes25保持。collection30秒、组合测试300秒、45秒无locals栈、命令/终止/清理期限及G1完整生命周期均由本工具约束。禁止只因状态修改PR描述导致edited再触发；一次CI失败即保留证据并停，不自动重复。

任何未确认停止/reader/cleanup都非零，不释放业务槽或产生业务死亡确认。原CI根因仍未解释；即使唯一新CI成功，也不能将未定位改为根因已解决。此本地候选只修复诊断工具P1，等待主控增量独立复审；不合并/关闭Issue/Gate、不进入Phase2。


## 第三段最小normal/reaped修正与实际workflow候选

新授权预算2026-10-09 15:48:28–15:58:28，最多10分钟，仅源码/fake/离线检查，不进行本地PG/Docker。独立增量审核指出6e的finish会对已正常wait/reap的PID/PGID发送信号，存在数字复用风险；这是诊断工具P1，不是原CI根因。

最小修正先检查returncode；若已wait/reap，观察成功/失败均不killpg、不重复wait，只记录existing returncode，container/reader仍必须独立确认。若returncode None，只有本supervisor唯一reaper的Popen.poll仍None（活自有child）才TERM；TERM等待超时后再poll，仍未完成才KILL并wait。reader仅读stdout、不调用poll/wait；异常观察仍finally处理未完成自有child，未知确认仍非零。

新增6个completed returncode0×观察成功/异常/未确认×reader是否结束的fake，全部断言不得killpg或重复wait，不能借正常CLI返回绕过container/reader确认；原13项异常/timeout回归保留。另2项静态workflow测试检查只读权限、原触发条件/Foundation checks、job25min、唯一诊断步骤、预算步骤顺序及嵌入Python语法。因此本文件fake+workflow共21项，结果和全offline精确计数在最终Issue回执记录。

此次同预算内准备了实际 .github/workflows/quality.yml diff，尚未推送/触发：checkout之后、安装之前的最早普通shell保存UTC+23min绝对deadline；Foundation checks不变，原PG步骤一次调用pg_diagnostic --session ci --round1 --combined --full-smoke --no-child-trace，job25min及原事件触发列表保持。SafeLoader解析/static检查与嵌入PythonAST仅证明配置结构，不等于Actions已运行。独立统一Review/主控核对后才允许消费尚未触发的一次CI；description一次写完整，不edited反复触发，失败不自动重跑。

与前次realPG snapshot差异明确：本段无任何新的PG/Docker/故障注入，6e之前两轮证据及缺失imageID限制保留；本新源码normal/reaped策略和workflow只由fake/静态/离线检查验证，不能称最终SHA已实跑新的realPG或CI。业务Graph/Worker/G1/原79断言/迁移/权限/锁无变化。原CI具体阻塞/根因仍未定位，即使一次新CI成功也保留该事实。
