# Phase 3 合同验收映射 v1

状态：测试设计；除 [首批交付](p3-contract-delivery.md) 的实际合同检查外，下表业务/PG/Web Gate **全部 not_run**。本文件不把既有Phase1/2实跑记成Phase3通过。依据 [#33](https://github.com/aning0922/commerceops-agent/issues/33)、[#34](https://github.com/aning0922/commerceops-agent/issues/34)、[TEST_PLAN](../TEST_PLAN.md) 和 [Web合同](p3-web-v1.md)。A的独立Review由总控安排，A自检不是独审。

| 批次 / Gate | 必要断言 | 计划证据 |
|---|---|---|
| 首批 schema | OpenAPI 3.1合法、所有ref/path参数解析、严格输入、无actor/role/approved旁路、固定禁用端点、所有POST Cookie+CSRF+Origin；错误与列表counts范围明确 | 冻结OpenAPI +独立validator命令/输出，不能证明运行时鉴权 |
| A01 / migration保留 | 自有真实PG加载P2completed task/immutable report/snapshot/官方checkpointer；迁移前后ID、state、version、content/hash、checkpoint字节和thread完全相同；P3另建task/thread | 迁移前后查询digest/rows，程序断言，非历史数据库 |
| A01 / T1、R01 from_report | HTTP自有受控入口T1后ACK前kill；重复10次同actor/operation/key只返回原P3 task/首个job/audit；只绑定已存在可信P2 report/snapshot，源P2 task/job/checkpoint完全不变、不新增或复活；原key异payload409；owner/scope/引用绑定拒绝 | barrier+真实PG+自有API，终止/重启证明；不新发飞书 |
| A01 / T1、R01 new_cycle | 显式提交新cycle创建新P2 analysis task/job及独立P3 task/job/T1回执；ACK前kill后同actor/operation/key重复10次仍同两task和原首个job/audit；原key异payload409，旧源task/旧审批不变 | 自有结构化mock入口、真实PG/进程kill；两个mode独立计断言，不将新周期回执套给from_report |
| A01 / T2 | 可信P2 report/snapshot/参数/质量绑定；空建议no_action、硬错误无可执行plan、21项SCOPE_REQUIRED、原raw null/effective0保留；同plan版本重放一plan/approval/blocked intent | 金标/纯hash测试与真实PG约束，固定canonical hash vectors |
| A02 / R05 | T2后interrupt checkpoint前kill；重放同plan/approval/outbox，未ready不放行意图 | 官方PG checkpointer、进程barrier/kill、DB持久回读 |
| A02 / R06 | checkpoint后ready_at前kill；同版本匹配中断后补ready，sender仍disabled | checkpoint read+协调器事实，缺匹配不能填ready |
| A02 / R07 | T3先于Worker观察中断；决定/resume持久，job延期重读直到匹配interrupt，一次消费 | 屏障控制T3先到，PG决定/resume检查，不随机sleep |
| A02 / R08 / A05–06 | 10次相同有效决定/T3后ACK丢失；一audit/decision/resume；两有权actor approve/reject并发一赢家；相反/不同集合/另一actor409 | 独立HTTP连接+事务barrier、真实PG唯一/CAS断言 |
| A02 / A01–04 | 普通approve在未知在途409且pending零job；联合完整集合一次T3；漏/多/重复/伪造bool/hash/version/nonce拒绝；reject_assumptions原因及零项 | typed payload负例+真实PG事务，不能只测试按钮 |
| A02–03 / A07–08、R09 | 新版本/quantity/risk/inbound null→known参数变化旧确认失效；当前权限/期限/跨店/硬质量拒绝；恢复后直接执行用例不能绕确认 | 锁后DB时钟边界、撤权竞态、当前role-bound scope、计划/确认存储复核 |
| A02 / R17 | API/Worker待审批跨进程重启，同thread/plan，固定interrupt，不从START新建；未知workflow_version needs_attention | 自有PG/官方checkpoint、旧PID已终止后新进程恢复 |
| A02 / S01–03 | 第二Worker拒启动；全局activeGraph≤1；待审批释放槽；失锁停止领取/取消/退出，未证明旧进程结束禁止替代Worker | 专用进程/锁连接、OS wait/reaped、原互斥回归；无热接管 |
| A03 / R10 | T4事务中途kill/rollback整计划全无；无半套items/execution/audit/outbox/consumed_at | 真实PG事务钩子/进程终止、事务前后全量断言 |
| A03 / R11 | T4 commit后checkpoint前kill；旧execution和各SKU原item返回；即使item已终态也不重建 | 提交后kill +官方checkpoint恢复 +永久operation_key查询 |
| A03 / R12 | 两task同共享库存池批准后串行执行；第二计划整批拒绝、没有部分项 | `(shop_id,pool) WHERE open`唯一约束与可控串行Graph，非多Worker |
| A03 / C01–02 | 同店approver单open项complete/close+必填原因+expected_version；operator/admin-only/跨店/空白原因/旧version拒绝；actor/time/reason/version/audit/outbox同事务 | 实际API+PG/无Woo写adapter调用；role与scope独立反例 |
| A03 / C03 | 原actor/operation/key/hash响应丢失重投同receipt，version/audit/projection只一次；同key异payload/new key终态冲突 | 原键重复和原语义hash/审计数量，当前查看权重校 |
| A03 / C04–05 | 终态释放open约束，新分析新审批新项；迟到旧resolve只作用旧item；complete/close并发一赢家；投影失败不回滚业务，旧execution不新建 | 新周期真实PG+本地controlled_stub failure（无平台API） |
| Auth / cookie会话 | 预置hash非明文、无dev selector、session登录轮换/注销/绝对与空闲期限/auth_version撤销，当前identity/scope查库、HTTPS Secure/local_http明确 | API真实PG+登录测试；无密码/hash进fixture/frontend/docs |
| Auth / Origin-CSRF | 同源与精确允许跨源读/登录/写/OPTIONS；missing/null/伪后缀/错误port拒绝；缺/旧/跨session CSRF拒绝；form/text/plain拒绝；未信任代理头不改来源 | 有权/无权、credential CORS与实际Browser测试；POST业务变更零行 |
| Auth / 列表无泄漏 | 多角色不同shop不能拼接；admin-only无业务scope；owner/eligible筛选，counts/total/detail同谓词；撤权/cursor跨actor拒绝；404存在与不可见一致；item可跟进不扩展源task读权 | 同一致快照真实PG+HTTP body equality；跨组织/同org跨店/无owner反例 |
| Contract-runtime | P3全局handler输出p3而非p203/p204；schema与响应一致；401/403/404/409/410/422；缺身份先于字段验证，不输出绑定信息/输入值 | 从实际FastAPI导出与候选OpenAPI比较，response JSON Schema检查 |
| B / API集成 | 预置真实session、完整20项/长中文/未知在途/历史、重复冲突/unknown原键恢复、新周期草稿、业务/sync分离、实际配置/server_time/null | A合同/API独审后接入，B真实Next Playwright，本阶段simulated_web明确 |
| B / UX | 导航刷新、dialog/Esc/focus restore/键盘，1440/1280/390、200%缩放、safe access/admin-only、原33tokens/18components | build/typecheck/真实页面截图，原型与Playwright均不当真人点击 |
| Final | 当前/index/完整历史敏感扫描、原离线/金标/真实PG回归、B typecheck/build/Playwright、无阻断冻结独审、精确head CI、总控合main后同SHA CI及恢复/金标/Web核收 | 同A Draft PR逐批证据；总控验收后结案，不由A merge |

BC01/05会话和必要读写、BC04真实恢复读取、BC07配置时钟在本阶段冻结；BC03仅新Workflow/版本失效/新周期。BC02飞书关联续答、BC06真实卡片容量、human_feishu、真实外部Base写/网络R13–16、生产/Phase4仍未实施。单Worker不证明多Worker R02–04；零新付费模型请求。D1=10-10、D30=11-08、300h及A32/B18/Review10的60h容量不变，人工工时not_reported。
