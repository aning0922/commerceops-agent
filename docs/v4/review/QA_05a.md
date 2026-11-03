# V4 QA准备代码独立审查

日期：2026-11-03（Asia/Taipei）。**结论：P2_REQUIRED_CHANGES，0 P1 / 3 P2，暂不签ACCEPT_PREPARED_HARNESS。** 问题限于HTTP场景的错误成功/失败判据；不要求为未接adapter补造运行证据。

## 精确范围

受审commit `05a875d2b3862befd832e1727c461fd59e8bb0c0`，tree `8bb4568e03de35243645cc7844da7ae136df7055`；相对已提交QA骨架48becf仅新增tests/e2e/v4九文件及QA_PLAN增量。只读精确Git对象，没有读取QA WIP，没有执行测试、进程、HTTP、PG、Node验证器或服务。身份设计的小增量在本次中途优先关闭，回执0516a6a独立保存；QA不继承其运行通过。

## QA-01 [P2] RATE_LIMITED可冒充cap3通过

位置：`tests/e2e/v4/http_probe.py:287–308`（capacity），尤其302–305。

先创建3个visitor后，对第4/5只要求429且code属于CAPACITY_LIMIT或RATE_LIMITED。若API根本未落实active cap3，但peer限流或scrypt忙恰好拒绝第4/5，场景也会返回成功；实际没有证明拒绝来自容量约束。与身份设计SEED_SPEC:117的“限流与容量分开、记录真实原因”相冲突。

最小修正：本capacity场景只接受CAPACITY_LIMIT，并校验有效正数Retry-After；RATE_LIMITED作为独立未完成/失败原因保留，不转容量PASS。结合已审PG adapter核实际活跃数与原三租户未被踢出。现代码串行建立前3、串行拒绝后2，只证明串行上限，不签“五并发只3提交”；并发容量验证保持另一个明确Gate，不能给当前场景贴并发结论。

## QA-02 [P2] 同key并发reset强制两次200，与旧CSRF拒绝不兼容

位置：`http_probe.py:364–399`，post:379–380默认expected=(200,)，385–387要求两份receipt相同。

两请求共享同一旧CSRF。符合受审身份设计的服务器在第一笔reset提交后轮换CSRF，第二笔获锁后必须验证当前CSRF，允许/应出现CSRF_INVALID 403，而不是跳过CSRF只返回旧receipt。现QA会把该正确路径判失败，反而鼓励实现者为测试放宽旧CSRF。

最小修正：明确并发的一个200 COMMITTED与另一个403/CSRF_INVALID的合法分支；若实现确能按合法事务序返回两个200，再校验相同原receipt，但不可要求它以放宽当前CSRF为代价。任何其他403/异常不自动接受。随后只用GET current+原key GET receipt核一次效果/唯一回执与epoch恰+1，实际PG证明唯一receipt/event；若无成功HTTP且无可证提交仍UNKNOWN，不标绿。用新current CSRF做显式对抗同key同body/异body实验可另保留，不能当客户端自动重试。

冻结身份设计I:393已明确两个旧CSRF并发请求后者可403；c4修订未改变该条。QA_PLAN如果还有“两200相同回执”的表述，应同步统一。

## QA-03 [P2] 普通回执GET未绑定请求operation/key

位置：`http_probe.py:198–208`（receipt）、`:227–241`（create_ack_loss body恢复）。

receipt只严格校验OperationEnvelope并返回，没有验证普通Receipt.operation/request_key对应URL。ack_body虽核current.creation_request_key，却直接接受随后GET回来的任意合法Receipt。因此服务端若误返回同owner另一操作/另一key的回执，schema仍合法，body丢失恢复场景会误称已核原创建。

最小修正：receipt方法对普通data.receipt及bootstrap最小data分支分别核operation/request_key与请求一致；bootstrap仅允许session_create，继续禁止身份字段。ack_body应确保返回COMMITTED的session_create原key receipt并与独立PG观察一致。现headers_and_body分支已对整个最小data作精确比较，保持；不能以当前schema格式合法代替原键绑定。

## Supervisor/时限/清理审查

`supervisor.py`静态观察：

- start:92–119仅接受绝对argv、不用shell、显式env、start_new_session=True；OwnedProcess由实际Popen返回，stop/wait按对象identity拒绝外来handle，每角色一次不自动重启。没有容器发现/全机清理能力。
- Budget:26–43要求显式UTC与reserve>=180，取wall和monotonic剩余较小值，工作截止扣reserve；超时不续窗。watchdog:70–90先停非PG工作，最终期限尝试清理全部owned。
- stop:160–187在leader已退出时仍尝试TERM/KILL同一自建组、等待/reap实际child，并独立观察组无live成员才置stopped。native_exit没有统一重写0。外层driver必须将正常probe非零/超时与cleanup出口分开记录。
- EPERM:148–158保存(signal,errno)，只有_no_live_group独立ps观察为空或全Z才可继续；未知/观察失败/live组拒绝。不会仅凭errno=1声称清理成功。全Z只代表无活跃writer，不等价全机零PID/容器/卷已清；不能把子进程测试升为资源Gate。
- stop_writers:189–205失败仍尝试其余owned角色并最终raise；close_pg:207–215要求writers均stopped后再停PG。常规最后PG snapshot应位于两者之间。最终watchdog是应急截止，不保证仍有时间采齐证据；watchdog_errors/未采集必须使Gate失败，不能吞掉后正常签收。

不增加容器cleaner或进程通用框架要求。运行前driver仍需已审foreground argv、PID/组/源窗口绑定，禁止daemon化/脱离owned组的进程；Docker CLI退出不代表容器退出。该方案已在QA_PLAN明确为adapter/资源owner待接线，当前不据此报“尚未实现全运行”的P1。

## Strict验证器、PG探针与HTTP边界

- `validate_response.mjs:16–39`从冻结OpenAPI按operation/status选response，仅把refs映射到$defs，Ajv2020 strict+formats，未知status/extra/format失败；不输出payload。`strict_response.py:13–28`使用固定Node路径、env空、当前Budget并要求native0及精确{valid:true}。未看到删schema字段/放宽验证选项。
- `pg_probe.py:29–55`拒绝非IDLE连接、只读事务、statement/lock timeout、prepared单tenant参数，要求唯一一行/精确七字段、tenant一致、非负真实int/hash/aware UTC。SQL与连接来自待审adapter，不自找DSN/旧env；这只是约束接缝，不证明任何SQL已真实取到DB事实。
- HTTP使用独立CookieJar、127.0.0.1显式端口、trust_env=False、不redirect/retry。每次timeout不是总场景期限；QA_PLAN要求probe在Supervisor子进程组运行，未来driver必须落实。
- lifecycle先取得成功logout的operation/key receipt，再GET current401（283–284），没有用401自行构造logout COMMITTED。bootstrap恢复严格最小data后current401也只验证未active（231–240）。transport异常向外抛出，不捕获为成功。
- source/cookie/context/source digest/当前店铺的完整业务断言不能仅由schema替代；当前lifecycle只用独立PG比A reset前后B摘要，其他PG计数/fixture/ACL专项仍在QA_PLAN待接，不宣称七场景即覆盖整个Q矩阵。

## 作者证据与界限

作者QA_PLAN记录：首collection/lint/npm launcher失败、首次冻结26pass/1fail、后续捕获PermissionError errno1（根因UNKNOWN）、修正定向及最终29pass/4.11s、Ruff/Mypy9/docs0。本次未重跑，均不得称Reviewer独立执行结果。

已读test_supervisor:61–225含native非零、unowned拒绝、TERM忽略/KILL/reap、PG关闭顺序、已退出leader后代、EPERM有/无独立证明；test_strict_response含格式/额外字段/最小恢复泄漏/DB失败null/未知status拒绝。它们没有运行HTTP七场景，也未覆盖QA-01/02/03的判据错误，因此29pass不能抵这些源码发现。

`adapter.py`仅Protocol；真实adapter/driver未存在，不允许skip/fallback签收。PG/API/Web/Full/Hosted仍NOT_RUN；资源窗口未开放。本报告不修改实现或测试，作者修订后交精确SHA增量审，保持首次失败与本轮三P2记录。

## d663增量复审：原三P2关闭，新增事件语义P2

受审commit `d66305205dc87affafc8caa3db0cbd52a3736bb6` / tree `c9730cb95d9810ab55bf27fcd812390ac5d3e0a6`，parent为05a。结论：**原QA-01/02/03 CLOSED_AT_CODE_REVIEW_LEVEL；新增QA-04 P2，0 P1 / 1 P2，暂不签ACCEPT_PREPARED_HARNESS。** 只读精确提交差异和新SQL/测试/QA_PLAN，不读取WIP，不执行任何SQL、HTTP或测试；原首审保留。

### 原三项关闭依据

- QA-01：http_probe.capacity_rejection要求精确CAPACITY_LIMIT及ASCII正整数Retry-After；capacity先核空库，三原tenant/session/creation receipt的3/3/3与逐key绑定，第4/5无receipt，原三身份不被踢出且最终cohort不变。QA_PLAN已明确仅串行cap3，未称并发容量已验。
- QA-02：concurrent_reset_result允许两相同200或一个200+精确403/CSRF_INVALID；其他拒绝/无成功不签。后续current+GET原key、当前CSRF显式对抗重放/异文冲突、PG唯一receipt/tenant/epoch+1及current再读保持，旧CSRF正确拒绝不再误判失败。事件类型的新增缺口见QA-04，不重新打开原“两200”问题。
- QA-03：receipt_binding在普通与最小分支核operation/key，最小分支限session_create；body丢失后核COMMITTED、current.creation_request_key、PG receipt ID/tenant，整体header丢失仍仅暴露最小状态。不同operation/key但schema合法的回执不再冒认原键。

### QA-04 [P2] operation事件只按数量统计，不能证明目标事件种类

位置：`tests/e2e/v4/design_pg_adapter.py:71–83`（OPERATION_SQL），尤其77–78；`http_probe.py`中的create_ack_loss、capacity、same_key_reset对facts.events==2或1的成功判据。

OPERATION_SQL只连接receipt_id/tenant_id后count(*)，没有检查event_kind。故session_create receipt若错误关联两条reset/logout事件，或reset receipt关联一条persona_changed事件，当前事件计数仍满足成功条件。receipt.operation正确也不能证明关联事件种类正确；独立QA应发现此类业务审计缺陷，而非依赖被验后端guard一定正确。

最小修正：读取该原receipt全部事件的有序种类集合（或返回明确的expected-kind计数及unexpected-kind计数），分别要求创建精确 `{demo.session_created, demo.seed_materialized}`，reset精确 `{demo.reset_committed}`，无遗漏/重复/额外事件。单纯WHERE event_kind过滤后只数期望事件仍会隐藏额外错事件，应同时拒绝unexpected。保留receipt/tenant/key/epoch已有绑定。增加“数量相同但种类错误”及“期望事件之外多一条”的离线判据拒绝，最终SQL正确性仍待授权PG核验。

这是新只读适配的具体语义误报，不要求添加新业务表/接口，也不把尚未运行SQL本身报成缺陷。修正可只在QA独占模块与对应测试完成。

### 新SQL适配的其余核验

DesignPgFacts不connect、不发现DSN、不继承配置、不带启动能力；连接显式注入。查询使用固定SQL和prepared参数，operation白名单、UUID key，事务只读/UTC/statement与lock timeout、空闲连接和唯一行/精确字段/type校验；未查询bearer/CSRF/password/credential秘密列。没有DML或可变表名拼接。

SNAPSHOT_SQL绑定tenant，按稳定顺序聚合shops/overlay摘要/receipts/events，排除观测时间，另回DB clock；receipt兼作tombstone的双count与c4设计一致，不宣称独立新表。该digest只覆盖明确列，QA_PLAN已明确不是全ACL/credential字节证明。

CAPACITY_SQL用MATERIALIZED单次DB时刻统计未revoke且未到期tenant/session，creation_receipts总数适用于本场景初始空库。OPERATION_SQL跨owner按operation/key搜索，当前随机唯一key的独立空库场景通过receipts==1再核预期tenant避免合并成单条；不是可公开的用户跨租户查询接口，不得照搬为API授权实现。

完整V4Adapter、实际后端表/运行配置、driver与容器清理仍待最终冻结接线，缺实现阻断不回占位值。supervisor/strict validator本轮未改，其旧静态结论沿用；不据此签实际进程/PG/API/Web/Full。

作者20项定向判据通过及Ruff/Mypy11/docs0只记作者证据；未重跑旧29项是明确事实。测试覆盖错误capacity reason/Retry秒、receipt错key/operation、两种并发结果及错误拒绝，但没有事件种类判据。Q18明确为ROOT登记的后续待后端细化分支，尚无实现/运行回执，不将其签已完成。Root的独立UI_FIXTURE22pass2fail/native1亦不在本SQL/HTTP候选结论内，不能代签或被本审查覆盖。
