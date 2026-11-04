# V4-0 B 独立审查计划

日期：2026-11-03（Asia/Taipei）。Owner：REVIEW；当前允许修改仅此审查计划，不修改实现或测试，不代替ROOT集成。

## 基线与已完成的只读核查

- 指定工作树：`/Users/aipuli/.codex/worktrees/commerceops-v4-review/commerceops-agent`，接单时detached且工作树干净。
- 受审文档基线commit：`fa96764cf2b8e3ab9adbb579b764f600a7d17e60`；tree：`10d9fad5c7457382d178086bedcab460aa01904d`。
- 产品祖先M3：`952e6246deb01ec763f2541d9f316753987744f3`；tree：`43e4e732824e23b991660a4f7882ba8f5a265df1`。
- 已核该基线相对M3仅AGENTS顶部、B授权与A文档导入，共39条文件路径；没有业务、测试、锁或workflow修改。未重新联网复查，远端HEAD的当前观察由ROOT负责。
- 已读[本批授权](../IMPLEMENTATION_AUTHORIZATION.md)、[TASK_PLAN](../baseline/TASK_PLAN.md)、四份冻结合同及相关OpenAPI；tracked八文件逐个SHA-256与[冻结清单](../baseline/evidence/CONTRACT_REVIEW_CANDIDATE_HASHES.json)相同（8/8）。旧NOT_STARTED/PENDING/B未授权为A历史，当前B授权有效。
- 复核导入：OpenAPI八端点；SessionData.shops为当前授权0–2店；DB不可读错误server_time可null。A结论沿用[最终合同审查](../baseline/reviews/CONTRACT_REVIEW_FINAL.md)，不重复全量A盘点。

本计划只接受文档基线/导入范围，**不签身份SQL设计、代码或本地Gate通过**。Backend两份专项设计尚未收到精确提交，不读取其他树的未提交WIP。actual token/cost UNKNOWN。

## 权限与交接规则

用户批准本地V40-01—05，到V4-0本地Gate后交付；不进入V4-1，不合Harness，不Hosted/push/PR/远端写/main/生产，不真实provider、embedding、飞书或Woo调用，无付费fallback。Reviewer仅在此指定cwd工作，不变更旧M3/Harness/README树。

先收ROOT转交的精确commit/tree、父基线、允许路径、作者证据索引及未跑项，再读对应Git对象。普通提交审查文档，保留首轮P1/P2及修订关闭依据；不amend/reset/force，不自行合入Backend。对不同SHA不转移测试或审核通过。

真实新owned PG/Web等运行虽在B原则授权范围，仍需ROOT先登记具体资源、source、命令、绝对UTC和cleanup reserve；本轮无窗口，不启动服务、测试/collect或读取旧runtime。允许本计划的文本/链接/差异检查不等于业务测试。

## G-DESIGN：专项SQL/身份与seed设计门禁

等待ROOT提交 `docs/v4/design/IDENTITY_SQL_PLAN.md` 与 `SEED_SPEC.md` 的精确commit。以下为检查项，不代表发现或要求未经批准的新功能。设计应给出足够具体的SQL/约束/事务序列，证明不变量；不能仅写“事务保障”“复用guard”。

| ID | 需审内容与拒绝条件 | 冻结合同锚 |
|---|---|---|
| D01 bearer隔离 | bootstrap/active token的命名空间、hash查找、日志/响应边界；公开V4 bearer绝不成为旧web_sessions可接受token，改名commerceops_session仍401；旧企业cookie也不能伪造V4身份。内部bound token不发布、不从hash还原。 | PERMISSION:11–13,39–47 |
| D02 完整身份链 | DemoSession→tenant/current binding→bound WebSession→credential/identity/principal的键、FK与当前enabled/auth_version检查；organization/principal/identity元组不能错配。不得以actor_guard代替完整credential检查；裸WebActor不绕V4上下文。 | PERMISSION:43 |
| D03 原子代际切换 | persona/reset的旧bound撤销、新bound建立、epoch/generation/CSRF变化、receipt同事务；旧actor迟到、同persona reset、operator→approver→operator均失效。失败回滚不得留下两个有效current binding；logout/到期/撤权即时拒绝，不依赖清理器及时执行。 | PERMISSION:19–23,45 |
| D04 数据库时间 | 成功授权、TTL、receipt时间为DB UTC；30分钟原绝对截止不延长，bootstrap为300秒；bound absolute/idle上界不超过DemoTTL。明确锁等待后的时间复核，不能以事务开始时间让已过期请求提交。DB不可读503/UNKNOWN及null时间不造COMMITTED。 | API:28,38–40；PERMISSION:15,41 |
| D05 锁序与线性化 | 明列cap准入、tenant/session、principal/credential/grants、receipt及overlay锁顺序与冲突路径。控制操作/撤权/seed/reset/读写避免逆序；身份核验到提交之间无授权TOCTOU。旧写先获锁可先提交，但reset提交后旧epoch不能写入新epoch。 | DOMAIN:23–25；PERMISSION:43–45 |
| D06 cap3并发 | 活跃租户定义、DB时钟到期计数、全局准入锁/原子约束、在创建事务内占位/提交；四五访客并发不能同时通过count后各自建tenant。失败不泄漏名额，已COMMIT但cookie丢失的旧空间仍计cap至TTL；不踢出既有租户，不用request key变更绕限流。 | PERMISSION:15；API:40 |
| D07 bootstrap恢复 | 原owner+精确单create key+300秒只读最小状态；提交后不能再写/换key创建。Set-Cookie已应用时current核creation key；整体丢cookie时不能换领bearer；过期/丢owner保持UNKNOWN。GET不能创建租户、重新授予身份或泄漏tenant/shop/principal/session ID。 | API:20,38–40 |
| D08 幂等与先后顺序 | 唯一(owner,operation,key)、canonical payload/hash含原epoch/generation；同key同文并发一次效果、异文409。检查receipt不能绕当前owner/到期/撤权，但也不能因当前generation已推进而误把安全GET回执当新POST。客户端UNKNOWN不自动重POST；服务端防重与客户端恢复分开。 | PERMISSION:23；API:46 |
| D09 reset/seed原子性 | seed manifest实际固定generator/seed/date/每店规模/关系，基线共享只读与tenant overlay明确；reset只当前tenant恢复同fixture，generation/epoch、旧绑定撤销与receipt同事务。保留去重tombstone与审计，明确安全保留期、旧key跨epoch处理及GC owner。无全库TRUNCATE或跨tenant cascade误删。 | DOMAIN:19–29；SEED manifest |
| D10 角色店铺 | 两店seed不等于全persona全店grant；SessionData能返回0/1/2店，restricted_admin不隐含业务权限。shop请求目标不能作为授权事实，跨tenant/shop拒绝，撤grant/credential即时生效；切persona为服务器allowlist，不接受客户端角色权威。 | API:42,52；PERMISSION:19,27 |
| D11 ACL/迁移 | head仍0023才新增0024，旧revision不改；逐表/列/函数低权权限、FK/unique/check、receipt不可变、调用者约束。若需SECURITY DEFINER，应审固定search_path/对象限定/owner及EXECUTE撤销，不能给runtime通用principal/grant写权。需旧helper/database.py变更先ROOT精确释放。 | TASK_PLAN:10–17,23,30；PERMISSION:47 |
| D12 HTTP与无外部副作用 | 默认关闭V4装配，旧/api/v1/schema不回退；cookie用途/Path/安全属性、GET同源例外与POST Origin+CSRF严格分开。V4-0仅同步PG与摘要，不投Graph/Worker，不开放旧mutating用例或实际外发。 | API:9–24,44,50；DOMAIN:31–33 |

关键现有源码对照保持精确M3基线：`web_sessions.py`的_session（173–219）、actor_guard（59–110）、role_scope（113–126）、authenticate（233–235）；`application/replenishment/contracts.py`的WebActor（132–140）；`replenishment_http.py`的web_boundary（152–190）。设计交接后只按受影响符号继续核读，不读私有runtime。既有WebActor没有V4 epoch/generation、旧路由不核V4边界，是必须由新窄桥接弥补的事实。

设计裁决：ACCEPT仅表示精确设计允许依相同范围实施；缺DDL约束、低权调用身份、实际锁序、cap原子策略或凭据生命周期时给可定位P1/P2，阻止受影响身份路径。未知或尚未实测项明确NOT_RUN，不要求在设计Gate伪造PG证据。

## G-CODE：冻结实现增量审查

收到已提交源码后独立按base→candidate diff审，不看作者未提交修复。检查实际函数/SQL是否落实D01–D12；尤其检视每个入口的鉴权与事务边界，而非只查测试数量。列出发现的触发条件、影响、最小修正、path/symbol/line与精确commit。

额外核对：

- 同一事务COMMIT前后故障语义、生成token的返回时点、Set-Cookie丢失与bootstrap保留；不能在数据库成功未知时发第二次创建。
- 被锁等待的请求在获锁后重新检查TTL/epoch/grants；同key冲突处理不要通过rollback后无锁重读造成跨tenant泄漏。
- 读端seed-summary要求请求epoch/generation，授权后产生context；晚到数据与current控制恢复不同。错误/匿名/最小receipt不携敏感业务context；失败时间可null。
- strict DTO及OpenAPI与生成前端类型同源；非法/多余字段、重复JSON字段、错误枚举与边界值不得转成权限事实。secret/token/CSRF/password不进入错误、SQL日志、截图或commit。
- migration/app角色的真实权限与设计一致；无隐式旧表/函数扩权。新组织初始化不能污染旧M3组织，默认开关关闭时旧API行为保持。
- WEB与QA只消费冻结API；三条V4入口、0店空态、unknown禁写、无自动重POST；多标签invalidate只是失效提示，hidden/offline清屏、恢复前current、可见页5秒核验与请求序列/context比较齐全，不虚称实时撤屏。

本地targeted/pure/实际PG/浏览器证据按其精确源分别审；作者自检不代独审。必要Reviewer重现另向ROOT登记资源与命令，不启动无窗口的新PG。

## G-LOCAL：本地Gate证据核收关注点

未来实际矩阵至少覆盖设计中的主要竞争与拒绝，不在本计划填pass：

| 组 | 必须可区分的实际事实 |
|---|---|
| 创建与容量 | 3活跃租户+第4/5拒绝；并发准入；COMMIT前失败回滚；COMMIT后丢ACK仍占cap；cookie已应用/整体丢失分列 |
| 身份/代际 | demo token改旧cookie拒绝；旧token进入V4拒绝；撤credential/grant/auth_version；同persona reset与往返切角色；旧WebActor迟到；边界TTL及锁等待超期 |
| 幂等/reset | 同key同payload并发唯一receipt/一次推进；异文409；reset与seed/业务写竞争；跨tenant digest不变；tombstone/GC不让旧key重执行 |
| Web | 真实API/PG上下文；0/1/2店；BC丢失、后台恢复、先发读后切换；UNKNOWN只读；1440/1280/390、键盘/focus/Esc/200%与失败空态 |
| 回归 | 当前动态完整PG集合及精确并集/交集、G1三/G2六、旧M3日报/询单/copy、旧Web/N01、scripts.check与来源/工具/锁/镜像/清理绑定；719/3684仅历史，不作新结果 |
| 资源 | 仅当前owned project/DB/ports/PID/volume，绝对UTC/cleanup实际出口；PG临时删卷与Web保卷按各窗口分列，失败/139/UNKNOWN不覆盖 |

历史native139根因UNKNOWN，不因新成功宣称根治；首次失败、未跑节点、非零native出口、清理缺证据各自保留。资源未停、证据源不匹配或完整集合缺项时，不能拼接多个旧run签整体通过。Hosted/amd64为独立NOT_RUN，不由本地Gate自动升级。

## 审查回执与当前交付

每轮报告最少包括：task/Gate、base/candidate/tree、精确路径与符号、P1/P2或ACCEPT、实际已读/已运行范围、失败/NOT_RUN、资源窗口来源、后续依赖。设计接受与代码接受、局部代码与最终同源集成、本地与Hosted必须分开。

当前状态：文档导入与B scope只读核查完成；REVIEW_PLAN_READY。IDENTITY_SQL_PLAN/SEED_SPEC精确提交待ROOT转交，专项设计/代码/PG/Web/Full均NOT_REVIEWED或NOT_RUN。首批审查不替ROOT放行后续阶段。

## 增量：CSV机械导入规范化静态核收

受ROOT转交，于2026-11-03只读审查control精确commit `eb82c9d626c210e8e982ba3d8889a4ffdd088c99` / tree `e4a9a7d51907828121ef709549ff00e0afd0a230`，父为 `fa96764cf2b8e3ab9adbb579b764f600a7d17e60`。未checkout/合入该提交；Reviewer自己的实现基线未变。

结论：**ACCEPT_MECHANICAL_IMPORT**，未发现P1/P2。两条变更路径仅 `docs/v4/baseline/v4-permission-matrix.csv` 与新增 `docs/v4/IMPORT_NORMALIZATION.json`，无业务/测试/whitespace检查或配置变更。

静态Git对象对比确认：原CSV有7个CRLF；新CSV无CR，且 `old_bytes.replace(CRLF, LF) == new_bytes` 精确成立；标准库CSV解析的全部行/单元格完全相等。旧SHA-256为 `139e04d028aae19b6f476e0f2f16c93f15ab9e649801c5138b96a896c9ab6cdd`，新为 `8c88490d92a704378e268122d0e8c0786d3f4519a5f543e1a96f3a03b15f71a3`；与登记记录一致。其余七份冻结文件逐字节未变且仍匹配A哈希；A的FROZEN_MANIFEST和八文件哈希清单也未变。

原始CSV字节已在fa96764 Git对象直接核实，外置原件路径只作为ROOT登记来源，本增量未重新读取外置文件。A归档清单继续描述原字节，不能冒称它匹配LF导入后的当前CSV或是一次B合同重签；B实际源manifest应使用新hash并引用本规范化登记。首次whitespace失败为ROOT报告的历史事实，本审查未执行locked docs检查或重现该失败，不将机械一致性当作工具链/业务Gate通过。
