# A07 正式受控 SDK Worker 装配与当前资源证据

2026-10-11，Asia/Shanghai。Root已授权原A继续正式运行装配的离线实施，同PR43、原Worktree与owner；当前主体尚未冻结，必要定向PG已通过，独审/精确CI和正式业务窗口仍待。main保持9d97，已核3a15精确四CI38128391205 SUCCESS及完整376PG是原源码证据，不验收本A07增量。无新迁移、权限、依赖锁、调度器、审批状态机或B/C产品修改。

## 实际资源预检与失败保留

Root授权读取明确六个历史非秘密身份/目标JSON及canonical Secret stat，实际Secret内容仅在显式官方SDK窗口由既有Factory读取；旧.env、旧PG、密码与凭据目录未读或复制。新自有PG使用commerceops_app，既有0012迁移与最小A/B绑定已准备，Root私包700/600、低权限与停止保卷证据分层保留。

| 实际窗口 | 事实 | 结果与停止 |
|---|---|---|
| 2d4，18:56:29–18:56:36 | 原Docker OCI向只读client下缺失的window.live.json创建mountpoint失败，entry125；parent/CLI/Factory/SDK未启动 | failed/not_run SDK；stop/down0/no-v/资源0；原字节+600非秘密占位后无Secret断网挂载验证exit0/1.461s |
| 426，18:59:48–19:00:03 | auth1/bot1/table1均HTTP200/code0；CLI只捕获ValueError类型，fields0，具体分支未捕获 | preflightFAILED；原owner/fullstartedstopped/OS absence/termination confirmation通过，task/job/outbox0，stop/down0/保卷；根因not_identified不追溯改写 |
| 4c，19:26:55–19:27:09 | 完整table单页items2/total2/morefalse，exact P4_M1_Internal_Items匹配0；固定P4_TARGET_NOT_UNIQUE；fields0 | 当前目标零匹配确证，暂停平台请求；四方法上限未扩，实际auth/bot/table各1 HTTP200/code0；同原outer内只读账本核收并于19:28:35释放0 |
| 654，19:48:42–19:48:56 | 用户授权Root同Base原生UI建正式表后，完整table单页3/total3，exact匹配1；fields15/total15/morefalse，missing/duplicate/type差异为空、extra0 | schema_verified；13text与Quantity/SyncVersion数字type2通过；auth/bot/table/field各1 HTTP200/code0；同原outer账本只读补证于19:50:23释放0，原19:50:42截止未重置 |

上表时间均为北京时间。654仅核当前唯一表与schema，记录读取/写入、IM、WS、provider均0；平台UI空白行是否实际默认记录未查，不称记录总数0。tenant/group/member当前API仍not_run，preflight不签写权限、真人或M1。原426失因未知与4c当前目标零匹配分别记账；不以新结果删除历史。

安全回执：[4c](https://github.com/aning0922/commerceops-agent/issues/40#issuecomment-6108544952)、[654](https://github.com/aning0922/commerceops-agent/issues/40#issuecomment-6108721318)。所有私证、原Token定位与卷仅保留在自有ignored目录，GitHub/本文不输出真实标识或原响应。

## 诊断与完成态只读交接

元数据诊断只有一个test-owned观察入口，原函数返回对象/原异常/调用次数保持；只写固定错误符号、结构与合同字段分类。原独审P2指出字段摘要可抢先改变畸形输入异常，已改先调用原validate_fields，再在安全finally内摘要，摘要失败不覆盖结果；同reviewer增量通过，6pure/原parent5pure通过。首扫描2→1个固定符号/合成文本误报与最终scan0历史保留，未改扫描规则。

原completed-read-4488窗口Root未派C，准确C_not_started_due_handoff_budget/authGET0/not_run，缺safe-result原父控AssertionError保留；18:51:55实际stop/down0/tempDB0/资源0/保卷。只读controller后续仅修成功状态比较为已审driver的readonly_completed_verified，新hash01f911537180203aecf8429e4ede5b040bdc972d059d491543fd35022633f76e；Root后续completed-read-0356f9824a38实际readonly_completed_verified，Root父控exit0、C Node0/browserclosed，loginPOST1/businesswrites0；原v2 completed/plan2 executed/approval consumed/新Q70 open1/独立execution_hash/旧known绑定前后保持，19:57:36实际stop/down0/tempDB0/容器网络监听0/保卷，源43/tree25d。该完成态只读证据不外推真人业务。后端原v2已由独立PG核completed/审批消费/新增1execution1itemQ70/旧21items2executions摘要保持，最终3executions22items2140；浏览器证据另列，旧M1部分失败不冒称全过。

## 最小正式运行装配

新增p4-worker-v1窗口默认enabled=false，显式1–5个原task UUID与原Gateway window UUID、同org/shop、SDK绝对截止最长300s、逐method cap。父/子CLI均须live opt-in，COMMERCEOPS_MODE=p4-controlled-test；runtime角色必须commerceops_app。默认关闭、Fake模式、空任务/过多任务、错误scope、过期/过长窗口或不受限auth/metadata cap均拒绝。

```bash
COMMERCEOPS_MODE=p4-controlled-test python -m commerceops.entrypoints.feishu_business worker \
  --live --config /run/owned/p4-business.json --window-file /run/owned/p4-worker.json
```

task名单须在原可信Gateway T1持久化后由Root核定。正式子进程先取得原全局WorkerSession，核原Gateway不可变完整JSON、当前org/app/tenant/Mock-test shop、同截止及原时间之后的Feishu T1任务与相同parameters；旧Fake delivery历史拒绝。此首包只接受该Gateway的Feishu任务，Web新周期外发及正式澄清后续门槛不被这份装配替代。

同一个Session内实例化PersistentSDKLedger与BusinessSDKFactory，复用原认证、bot、唯一表与严格15字段预检；验证成功的目标仅在同进程交BusinessRecordSDK/原B BusinessBaseAdapter，不输出或猜定位。将同一个受账本包裹的client/RequestOption接BusinessIMSDK与原IMDeliveryStore/BaseDeliveryStore，gate=controlled_sdk、固定task名单与同expiry；没有Fake替代或额外consumer。

原InventoryCompositeRunner/ApprovalRunner/单Worker与全局Graph槽复用原M1DemoFactory的twenty与known70；同collector贯穿P2/T2/T4，ProviderFactory默认禁实际调用，受控Mock/test模式不成为生产数据来源。原审批nonce/hash/当前role/原UUID/outbox/未知恢复规则不变。维护中IM或Base出现unknown/拒绝/冲突/延期即停止本窗口，不自动再发；原Worker增加维护设置stop后不再claim新Graph的两行停止检查。

父进程按原绝对期限terminate/wait/必要kill/reap，只有原child唯一完整started/stopped、同host/PIDnamespace且OS PID已消失，才调用现有confirm_termination；无pair/未回收/namespace不符保持失败，不伪确认。非合作Graph仍按原UnsafeShutdown退出75与未确认receipt处理。

## 当前验证与剩余Gate

作者定向58pure/5.86s通过，其中新增25项，其余原preflight/lifecycle保持；覆盖defaultoff、模式/TTL/task/cap、同Gateway参数/旧Fake拒绝、真实ports与同ledger/session接线（HTTP与PG均替身）、unknown后不再Base dispatch、原完整生命周期与维护stop后无新claim。首轮23fail/35pass/5.77s为合成DatabaseSettings遗漏三个必填字段，已补齐；不记为平台失败。Ruff初压缩写法/格式及类型标注修订历史保留，定向Ruff与4文件mypy最终0。

新必要PG共2节点：原Gateway任务/参数/时间/错scope零增量与同容器真实普通child的Session started/stopped/wait-reap/OSabsence/termination confirmation；不使用平台SDK/Secret/业务Graph。首新project p4a07-28078f1fb5e7先插件缺P123_DIAG exit3/0tests，原outer内仅环境修正后4节点3pass1fail/16.975s/JUnit13.870s；新正常scope被拒。作者实际源码错误为读取normalized_request.parameters，原T1权威参数在p3_task_sources；修复按同task/org/shop关联原sources.parameters，仍严格比较Gateway原parameters，未放宽准入。该两轮正常stop/down0/低权flagsfalse/tempDB0/保卷，不再运行。

新修复project p4a07fix-c2fd67aa5f6b，T0=20:20:31/outer20:30:31，当前WIP源码COPY+hashmanifest、UID501:GID20；一次新2+原Gateway1+原SDKLedger1共4实际全部passed，command14.953s/JUnit12.171s/失败错误skip各0，20:21:17正常stop/down no-v0/容器网络0/保卷。低权3flagsfalse/tempDB0，SDK/AppSecret/paid0，不读p4ro或旧M1库。完整PG日志/阶段plugin/JUnit/源码manifest与失败卷都保留，不能用Fake cursor替实际PG。

完整offline1426/94.62s（修复SQL前快照、integration377 deselected）、359format/262mypy/93MD/Ruff/uv锁均0；敏感误报4固定方法名/类型标注经正常格式与合成case名整理后dir/index/history各0，不改规则。最终修复源码完整offline1426 passed/378 integration deselected/118.78s，4PG实际call全pass/12阶段无fail且COPY镜像backend/scripts/tests与当前逐byte一致；最终source/独审/精确新CI不预填，暂存三scope扫描随freeze核。原CI自动按test_p4前缀将新增PG2纳phase3分区，无共享CI/锁改动。

最小真人pilot仍disabled：known70一任务、私聊请求/本版本批准/Web close三业务动作，Base create1/update1/单页最低list4与原approval/result IM2。正式装配会在同SDK窗口再核metadata，需Root冻结auth1/bot1/table≤2/field≤2及业务caps（最多14、单页正常12次HTTP），不能沿用不含metadata两项的早期10次候选预算。当前metadata与必要定向PG通过，不替代正式装配独审/精确CI、真人即发ready与实际record完整15读回。群20/跨入口/新周期/负例/重复/WSwire及原全M1仍另核；UX8/N01未实施，D1/D30/300h/50h估计、人工H/L not_reported、18页设计、原风险及保卷边界保持。

## 5fd独审P1首包配额修复候选

Root原Core对精确5fd发现P1：controlled-worker只检查IM/Base下限，通用SDKWindow的500次上限可被首包沿用。真人/SDK pilot暂停，5fd不是已验收候选。原授权known70首包预算仍是下表，未增加或改成全M1预算：

| 唯一允许的SDK方法 | 单窗口上限 |
|---|---|
| auth.v3.tenant_access_token.internal | 1 |
| bot.v3.info | 1 |
| bitable.v1.app_table.list | 2 |
| bitable.v1.app_table_field.list | 2 |
| im.v1.message.create | 2 |
| bitable.v1.app_table_record.create | 1 |
| bitable.v1.app_table_record.update | 1 |
| bitable.v1.app_table_record.list | 4 |

只在ControlledWorkerWindow增加不可变KNOWN70方法名单与逐项上限，最多14；原认证/bot/fields/table定位及IM/create/list必要下限保留，省略可选方法不能绕其正数/上限规则。额外方法、各类上限+1与500次放大都拒绝。通用SDKWindow、权限/迁移/B/C/锁/CI及原Gateway active、Worker不晚于Gateway expiry条件原字节保持；跨窗口恢复Gate仍not_run，不在本修复新增恢复设施。

作者先在旧源码用16个高配额回归复现8fail/8pass/3.27s（四IM/Base方法分别上限+1与500均未被拒），随后修复相关86pure/5.36s通过，含20新增配额/额外方法/合法14边界/通用500保持测试；定向mypy2/Ruff通过。新自有隔离project p4a07cap-c4203b9dc947，T0=20:43:40/outer20:53:40，UID501:GID20、新0012/credentials、AppSecret/平台/模型/业务Graph0；一次相关4PG全部passed，command14.868s/JUnit12.076s/0failure-error-skip，低权3flagsfalse/tempDB0，20:44:23正常stop/down no-v0/容器网络0/保卷。新精确SHA/原Core复审与CI另核，不由作者宣P1解除。

## 首known70 pilot的既有入口接续（全部disabled，未执行）

该接续仅使用现有API、Gateway、Worker和Web界面，供Root在精确复审/CI后安排真人时刻。所有待用配置保持enabled=false、未设置新T0；命令是操作顺序示例，本文不会启动服务或读Secret。Root先核新自有PG与已验schema的唯一Base目标、同A principal的Feishu/Web identity与当前operator/approver/shop权限。当前只读资源准备不自动意味着Web登录credential已准备；需按原身份桥接合同核定，不能借旧M1登录或复制旧密码。固定parameters取原DTO：source_mode=mock、dataset_version=inventory-v1、fixture_case=known_inbound、L=3/R=7/S=2，P2/T2/T4用同已审factory，model not_used。

1. Root准备私有business/web/Gateway/Worker JSON和只读单文件mount，核App无其他consumer与所有owned资源归属。Gateway使用新的原window UUID、唯一workflow/max_workflows=1、最多2次业务callback admission；admission不是WS物理帧次数，endpoint/handshake/frame/ACK仍not_verified。Worker使用自己的新SDK window UUID并指向同Gateway window UUID，expiry不晚于该Gateway；Root预定原绝对窗口，不能在捕获T1后延长Gateway。
2. Root在同PG启动现有API和原Gateway入口；分别用独立受控会话执行以下命令。明确时刻才启用原私有Gateway窗口，CLI的live也不能绕过enabled/expiry。真人A向原bot私聊发送“分析库存并生成补货建议”一次，此时还没有正式Worker分析/发卡。

```bash
COMMERCEOPS_P3_CONFIG_FILE=/run/owned/web.json \
  COMMERCEOPS_HOST=127.0.0.1 COMMERCEOPS_PORT=8000 \
  python -m commerceops.entrypoints.api

python -m commerceops.entrypoints.feishu_business gateway --live \
  --config /run/owned/p4-business.json --window-file /run/owned/p4-gateway.json
```

3. Root用commerceops_app只读原PG的p4_inbox_receipts/inbox_events与Gateway claim，核原claim之后唯一T1 task：同org/shop/app/tenant、Feishu channel、im.message.receive_v1，以及原p3_task_sources.parameters等于Gateway原parameters；结果必须恰好一个。task UUID只存600私配，不 stdout/粘贴公开。把该原task放Worker task_ids=[原task]，gateway_window_id保持原值；不造task、复制旧计划/nonce/approval或将Fake历史升级。由原trusted_scope再次完整核验，余量≤15s则not_run，不能换截止。Root此时才启用已约定Worker窗口并启动现有正式入口：

```bash
COMMERCEOPS_MODE=p4-controlled-test \
  python -m commerceops.entrypoints.feishu_business worker --live \
  --config /run/owned/p4-business.json --window-file /run/owned/p4-worker.json
```

4. Worker先原auth/bot/同表严格metadata验证，随后唯一Graph生成本版本plan与正式卡；真人A只在原版本卡approve一次。等待PG原execution1/item1 Q70以及Base v1原UUID、稳定record anchor和完整15字段唯一verified读回；SDK ACK不替代verified。原approval/result IM最多2，create最多1，两次投影共list最多4，metadata每类最多2；分页/对账也扣同上限，无额外get或补次数。
5. 原Base v1 verified后，真人A用同principal的既有Web登录，找到同一内部item执行close一次（保原任务/执行/批准不复活）。原T6生成v2 immutable outbox，由仍在原窗口内的同Worker对同稳定record update最多1，完整15字段读回；不增加T6通知或新工作流。records里nullable终态三键absent必须按原B strict binding置UNKNOWN/停止，不能自动填空、放宽B或盲重发；平台UI空白行是否实际默认记录仍未查。
6. Root提前停止时向原Gateway/Worker父进程发送SIGTERM，或沿各自既有绝对expiry正常收尾。Gateway父层terminate/wait/reap；Worker父层正常终止原child，并在同host/PIDnamespace读唯一完整started/stopped、核原PID OS消失后用既有confirm_termination。缺pair/未回收/namespace不符只报failed/not_verified；非合作Graph保退出75与未确认receipt，不从外层Docker PID0猜确认。之后仅owned正常stop/down no-v，核容器/网络/listener/tempDB0，保卷/原键/全部历史；未知外写与未确认调用保持原UUID账本，不续窗、不补发。Web或Base步骤余量不足即未完成，不把这首包当全M1通过。
