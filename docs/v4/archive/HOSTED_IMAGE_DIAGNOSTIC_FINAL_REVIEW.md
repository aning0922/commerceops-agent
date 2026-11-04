# 2513597 诊断读取预算增量核收

2026-11-04（台北）。结论：`ACCEPTED_BOUNDED_DIAGNOSTIC_READ / P2_CLOSED / NO_OPEN_P1_P2`。解除REVIEW_8835892_CORRECTION.md针对有界读取的HOLD；原报告与更正保留，不覆盖。883及本增量组合可交Root集成后按既有授权取得第三轮Hosted诊断，不预签其运行结果。

固定source2513597b742e029303097c6e7d8066063e59bea0 / treecfafd7b11be28b4c4fd74ba62abdabe53c26fd28，parent883589291cbc5d39db4f5e123486db86a3b5aa5b。完整差异仅helper/test。独立AST比较prepare_image剔除最外finally后完整相同，其核心build/stop/source/inspect/binding/receipt写入不变；其他原函数除read_private_log/build_output_facts之外也相同。Dockerfile精确字节不变。因此原300秒、85/75预留、实际架构/source guard及正式receipt继续保持，业务/版本/规则/工作流未改。

## 有界读取与时间保护

固定LOG_LIMIT=8MiB每日志。读取前先检查预算、O_NOFOLLOW打开、fstat regular/owner/0600/size；随后read(LOG_LIMIT+1)及读取后fstat共同拒绝超限与增长，final_size须等于实际完整读取长度。保留8MiB+1最多读取边界，不以截断prefix生成完整hash。

finally从min(5秒、原monotonic截止余量-75、实际UTC截止余量-75)计算诊断deadline；无预算直接跳读。每份日志只读一次，bytes供parser/hash复用；解析每输出及逐行检查时间，hash每文件前及总完成后复核。仅全部读取/解析/hash成功才发布parsed/完整logs_sha256。LOG_TOO_LARGE与BUDGET_EXHAUSTED保留diagnostic_stage/last_entered/last_completed为UNKNOWN，无部分hash、不输出raw。

这是一段固定大小本地regular-file读取加循环预算检查，不冒称能抢占内核IO的硬实时监督。有限读取消除了原无界输入/重复全读问题；已到预算时不继续解析或写报告、不侵占原75秒预留继续工作，亦不续窗。

## LOG_REFUSED与原镜像gate的明确语义

Root提出的异常分支变化已单独审查：OSError/ValueError现在仅登记LOG_REFUSED；safe JSON写失败登记LOG_WRITE_FAILED，诊断不再单独抛异常。这里接受其为附加诊断失败，不是放松原构建准入。

不安全日志仍在读取前被owner/mode/no-follow拒绝；读取失败不发布解析结果和hash。若原build/source/inspect/binding失败，原try中的异常仍向外传播，finally不return/不吞它，stage/code/native returncode/timedout/reaped/source事实保持。若原核心流程全部成功，formal binding与所有原门槛已经通过，诊断文件不可用可作为advisory，不需要新增一个改变旧image gate的日志成功门槛。

LOG_WRITE_FAILED发生于已完成安全解析后时可保留既有解析/hash观察，但diagnostic_stage转UNKNOWN、code明确失败；不能宣称safe文件已持久化。它不会令unsafe文件通过，也不会伪造核心成功。对本次合前取证，只有实际diagnostic_code=OK的摘要可作为完整诊断核收；其他状态仍表示诊断未取得，必要时Root按实际事实决定下一步。原始日志不对外打印。

## 定向证据

原件 /Users/aipuli/.codex/worktrees/commerceops-pr53-image-diagnostic/commerceops-agent/.audit/pr53-amd64-r1/budget-postcommit-ixtf4mfq/receipt.safe.json，独立SHA256 028e1ba75901a7acea9b3b5663010dbc7f9951e6a93e9d572b3aa08f8684f811。source/tree/parent精确251/treecf/883。native报告字节hash37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570，实际空数组，native0/findings0/blocking0；无新增例外。

实际budget-targeted-final.private.log为28passed/27deselected/0.30s，SHA256 77d1b328e2166f25eea1271382a5c0000e4fc8e7a6fc8b116601229289cb2b78；前一次同28/27/0.40s单列。回执记录Ruff/format/strict mypy两文件/diff通过。未全套重跑，883的48/146/69与原失败按原source继续保留。

新增测试覆盖fstat超限、读取后超限、逐行时间耗尽、预算不足零读取、每文件单次读取以及超限/预算失败不改写原BUILD_NONZERO/native9/reaped/source。没有通过额外本机构建、PG或新Hosted代签本增量。

本轮仅冻结源码、指定原件/hash与AST比对，无测试/扫描器/网络/服务/CI/push。一次辅助hash枚举误读目录触发IsADirectoryError，随后只枚举文件核验成功；不影响此前已完成AST结果，未重写原件。原review WT不变。旧两run根因UNKNOWN、本机唯一timeout与BuildKit内部UNKNOWN继续保留；本报告只关闭诊断读取P2。
