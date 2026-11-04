# 8835892 有界私有镜像诊断增量独审

2026-11-04（台北）。结论：`ACCEPTED_BOUNDED_DIAGNOSTIC_SOURCE / NO_OPEN_P1_P2`。接受该诊断源码供Root按已批准合同集成和取得新Hosted证据；不是镜像构建成功、底层问题已修复或全PG通过。

固定source883589291cbc5d39db4f5e123486db86a3b5aa5b / tree9171a0a08f06abf5600d1579ddbad6209c1bfbd7，basecbd5d5464b9e2b4a62463f2ba51d100125326e8c。精确增量仅scripts/m3_pgvector.py、infrastructure/knowledge_pgvector.Dockerfile、tests/test_m3_local_runtime.py，无业务、迁移、workflow、依赖pin或规则变更。

## 构建语义与生命周期

独立移除Dockerfile固定ENTER/DONE printf并归一原末行的必要shell续接后，全文与cbd原Dockerfile精确相等。基础镜像、APT版本/源、curl URL/TLS/timeout、hash、架构case、make参数、COPY及runtime命令保持。helper仅为Docker build增加--progress=plain，不增加--platform、缓存策略或其他构建行为。

helper中除prepare_image/main外所有原函数AST相同；input列表、IMAGE、receipt位置以及source_identity、image_metadata、inspect_image、validate_binding/validate_container保持。prepare继续使用同一绝对截止与单次monotonic换算、build min(300,剩余-85)、后续剩余-75、inspect/source查询min(5,left)。没有续窗、重试或并行构建。

Popen仍start_new_session；wait超时仅登记timedout/code再抛出；finally仍poll、TERM、wait5、必要KILL、wait5。reaped/returncode根据实际child状态登记；退出清理本身异常时仍失败，未捏造成功。build非0、source inputs/identity改变、inspect/架构不符、binding不符继续拒绝。日志不能授予运行准入或替代formal binding。

正式成功receipt仍只写原binding对象；不混入诊断字段。新写法采用独占/no-follow/0600 writer，保留fresh-only，不覆盖旧receipt。构建失败没有成功receipt。原native架构要求未放宽；本机amd64诊断不被改造为正式native receipt。

## 私有日志与安全摘要

.audit拒绝symlink及非本owner目录；新增mkdtemp目录要求0700和当前owner。日志/诊断/正式receipt writer使用O_EXCL|O_NOFOLLOW、0600，并fstat核regular/owner/mode；读日志也O_NOFOLLOW及同样fstat核验。已有.audit本身不强求0700（CI原有目录可能0755），新原始日志实际隔离在0700子目录；不把父目录模式误称已收紧。

stdout/stderr仅进入私有文件，CLI失败只序列化受控facts，不输出exception原文、raw日志、URL或远端片段。facts中的source/tree/input/log摘要来自固定源码及hash，不加入原始构建内容。日志解析/写入失败仍报LOGGING失败，不悄悄降级成成功。

marker解析仅在剥除固定BuildKit时间前缀后fullmatch独立M3_IMAGE_STAGE ENTER|DONE行，拒绝RUN程序回显、Dockerfile错误上下文及未知stage；last_entered/last_completed只是观察，不是根因。安全错误识别限定APT版本不存在/依赖冲突、curl DNS/TLS/HTTP数值、固定三文件digest和COMPILE期间make错误；未匹配为UNKNOWN。observed_error是匹配到的输出观察，不是经过因果证明的root cause；多个匹配时当前实现保留最后类别，不能把它当唯一故障归因。curl_http_status仅为所观察数值，不输出服务器文本。

该版本facts没有新增独立UTC/elapsed字段；时间继续取外层job时间及既有截止记录，不能声称JSON已包含耗时。CLI客户端reap不等于BuildKit内部任务终止证明，旧BuildKit UNKNOWN边界继续保留。以上限制不改变现有构建准入与生命周期，也不阻断获取本次最小新证据。

## 实际纯检查与原件

读取原件目录 /Users/aipuli/.codex/worktrees/commerceops-pr53-image-diagnostic/commerceops-agent/.audit/pr53-amd64-r1 。实际source-freeze.safe.json SHA256为44d63c2af6382437dd02b5511855097ddea57d2b4896b299ceceb6c29fb7d9f8；其source/tree精确883/tree9171。全部6项source_inputs_sha256与冻结Git对象匹配，41项private_log_sha256独立全部匹配。转交信息中的8affc32686e82ea8e1c1efeb35c7d574336ce220d3c347c02d191cb64614acf4未匹配本轮该文件，不能以该摘要引用此原件；本报告以实际44d63c为准。另一个receipt.json是原amd64构建案，hash8ad64dbbe7da33acb571766f1bdec2157f318225f1da81c2910ba344570874ee，不与源码冻结回执混记。

日志原文独立核：first-unit 27pass/1fail（旧argv未含已批准progress），second-unit48pass，related146pass，consumer先31pass/38fail（新WT缺固定Node），补工具后69pass/9.21s；类型日志两文件成功。原记录列Ruff/format/diff通过、current/index0、history native1/reviewed1862/blocking0，后续postcommit receipt精确883/tree9171、native0/findings0。各批来源和失败分账，不求和为新完整测试数。

新测试覆盖固定安全错误、RUN回显/未知marker拒绝、日志mode/symlink/已有文件拒绝、build/source/inspect/binding分阶段失败、原始私有文本不出摘要、timeout的TERM/KILL/reap以及Dockerfile原命令等价。是本地纯/Fake child证据；未测试第二步真实Docker build或Hosted。未因纯测通过认定旧Hosted问题根因。

本轮仅静态对象/原件/hash/AST核验，无新增测试、扫描、网络、Docker、PG、服务或CI；原review WT不变。后续新run须绑定实际checkout/tree、记录安全阶段与实际结果；原两次Hosted失败及本机唯一timeout继续保留。main备份、保护、FF/PR及最终merge由Root在用户授权下处理，本报告不代签远端状态或进入V4-2。
