# P4-A03 Base伴随投影与安全读合同切片候选

本批parent23bc268227cf7e6bb57043617bfac13f6e631d4e（已审runner最小14+14修复），前层A02为5ae94a2834096fa5eb80cf2e4524dc8abe909c9d；Root已核A02 Core无P1/P2/独立30PG53.159s+另1单Worker1.462s/Fake transport/platform0/三角色flagsfalse，首漏P123_DIAG的0test保留。本A03新source/PG/独审/精确CI分开，不冒称前层验证本层。

## 范围与安全边界

0010为新p4_base_deliveries/p4_base_links/p4_sender_state伴随账本，原P3 outbox identity/disabled sender/no sent/unknown规则原样。A既有唯一Worker维护回调注入Base adapter+默认关闭/固定绝对截止/明确最多5个task与单shop gate，B三个模块和冻结DTO/Protocol不改。不存在第二dispatcher或business rollback。

原outbox UUID/target/item/完整15字段snapshot/hash/version/mode永久固定；v1即使T6后才领取仍复原创建时open/null/time，v2只取既有不可变终态。网络前持久sending/attempt/原键，完整B bind_projection_result复核原版本/原record/所有字段才verified并建原v1稳定锚。v1 verified而当前v2只为历史证明，当前v2仍pending；再同锚/原v2 UUID update+完整readback。unknown_since首次未知后不可清/回pending或换write，即经sending中间态也仅reconcile；每projection≤3attempt，缺锚/冲突/更高版本/不完整保持hold/attention。角色/原审批auth当前重验，失败不复活或改内部item/原execution。

offline_fake与controlled_sdk mode按delivery行不可变；不会把旧Fake证明改成真平台或升级controlled_stub/probe outbox。发送许可由当前gate期限、真实Worker advisory lock与持久生命周期读取；ops/config/session返回safe alias/reason/verification mode/worker_ready，不出target/record/client_token/PID/open_id。当前CLI不构建SDK/读新旧认证，真实sender与资源窗口仍Root审后启用。

空终态三键的实际远端absent/null/empty行为not_verified。维持B已审规则：null/empty可归一，任一absent→unknown，不能recover link/sent。未来pilot仅原有限调用观察keyset/三键shape类别/预期版本与原record匹配bool，不额外get/count或记录原值/完整定位；实际absent必须停外部路径再有界修复。

## Web读增量候选

完整backend asset/docs OpenAPI字节一致、原21paths/22operations不增。sync为Task/Execution/Item共享safe投影：alias、target/observed、完整唯一verified、当前/历史版本、attempts/as_of/safe error/mode；当前summary取各aggregate最新版本，不让旧v1表示当前v2成功。config/ops真实gate及disabled/window/Worker理由取PG，Fake sender不表示外部启用。session可信同principal Feishu bridge只给linked_channels，不出平台身份定位；新周期严格completed+report/sameShop+当前该店operator。

events同authorized task及精确source关系输出audit trace/ref/T1–T6/deterministic工具事实，Base adapter操作与实际SDK方法调用/LLM动态工具选择分类型；当前仅记实际adapter invocation结果，sdk_method=null，尚无实际SDK method ledger，不能以trace_id冒工具链或假称SDK具体次数。IM card/result伴随发送/当前proof与真正method ledger仍待下一切片；四读组因此未放行。新schema需Root独审冻结后交C单owner同步generated/Mock/decoder/UI，不由A写前端。

## Fixture与作者离线证据

[稳定真实序列候选](contracts/p4-live-sequence.md)固定原twenty及known_inbound，P2/T2/T4同factory，私聊Q70/群20×100。拒绝先0items、成功冲突/重投同计划、同pool全部T6前不再次baseline T4，AC11空草稿显式新known参数/newkey；无新shop/成员/fixture平台。首pure2fail误字段/计划Q50被实际goldens70纠正，业务/金标不改；首read契约试用未安装jsonschema导致0test/import error，改用已有Pydantic严格DTO，不新增依赖/锁，实际wire仍可用原独立有版工具。

作者全offline1309pass/85.18s、372integration deselected、两旧SDK warnings；232mypy/319format/lint0、83MD0/diff0。随后worker_ready读字段专项8pure/0.66s+mypy同232。Base v1unknown→v2组合8pure2.08s、safe read6/示例20与private factory2；新PG5仅collect，未把收集当通过。新的定向36（5delivery+9clarification+21gateway+1schema）、低权flags/完整plugin/JUnit/源hash/镜像/stop在Root释放pool后的新固定owned窗口执行，结果另记，不预填。原545 frontend schema fail/610累计300秒超时及readunknown/旧Corecount not_verified全部保留。

本批不签M1：Card/result正式async发送、实际SDK方法计数/Rootcaps、四读组最终闭集/新C接线、clean Compose/human与真表均未完成。无新平台/provider/旧secret-env-DB读取，D1/D30/300h/P4原50h及人工H/L not_reported不重置。

## 作者实际PG与正常C集成

功能源4d98d71/tree9494本地冻结，Docker import collection对docs无依赖的单测试收口433c0b5另列。Root Core/Base对433静态/pure无P1/P2（独立Core91pure/2.56s、Base8pure/5.27s，新PG5仅collect而非运行）；正常merge已审C3d1758b2711830b4863d9e93d732bd1429603d49为e060ce3531dd6243ad8332d19ba08a3cffa943dd，parents433c+3d无冲突/47Cblob同原源。a5542bf只根CI加现8UI单行run_before_cleanup，独立增审无P1/P2，不放宽原Mock/B04/24/native200/23min/75cleanup；backend同433。尚未push本集成源，旧5aeCI38113580257整体frontendFAILURE、quality/phase3/pgpair成功367精确PG由Root核，不能记当前整合CI通过。

[作者实际安全摘要](contracts/p4-a03-author-evidence.json)绑定精确a1cd66936c3cd268d32c68bfafc8f34555e44aa7/tree62230b73a1760d1ffe8f71d6cf01413319a97b1b，testCOPY image sha256:62fbc307206a8fd57db86a78d106cc969f934fe56605f6641cc9fa87f8552ddf/232源码hash，无host源bind。原新owned20min05:19:15.391078→05:39:15.391078。首源a554镜像4b2484实际36=33pass/3fail/90.62s、command94.16、完整JUnit/plugin；三fail是新增测试helper错误未注册T6/items路径404，非未知恢复。只修至原/replenishment-items路由一行a1cd，Core精确增审无P1/P2，原断言/actor/reason/version无放宽，历史保持。

同原截止内重建完整36actual=callpass/84.04s（command87.060、JUnit36/fail0/84.038s），其中5Base新组合、9原澄清、21原Gateway/API、1schema全部expected/actual/plugin/JUnit一致。全20 runtime使用原twenty同factory贯穿P2/T2/T4/完整unknown集合/1永久execution，Fake Base20create+40list/20anchor/2000units均实证；v1unknown/T6v2原锚顺序、终态后首次v1复原、角色撤权无transport、不完整unknown不盲create/DB约束同轮通过。模式Mock/simulated_feishu/transportFake，platform/provider0，不称真实Feishu发送。

metadata实际三roleflagsfalse/tempDB0/revision0010，05:25:25.422309 stop0/全falsePID0；05:26:21.912292核UID/3本项目停止container和network/volume labels后仅own普通down0、network_removed/保卷image-private/JUnit，不-v/prune/rmi。池已交Root/C一次原7read，不再争网/新PG。Root将另安排独立PG复验，不能把静态审当复验；C b88的旧NOT_READY最小修复与safe失败捕获待其原窗口实证，610具体旧traceunknown仍保留。

用户15列表已向Root回复“已有”，仍需[有界只读preflight候选](contracts/p4-preflight-v1.md)核新目标/schema/type/app资源；旧.env/TABLE_ID或P1 Probe不推断新表，entry/Factory/方法账本未审不启动平台。C最终Generated/Mock/decoder需从审后最新backend安全读Schema同步，Root单owner协调，A不并写。
