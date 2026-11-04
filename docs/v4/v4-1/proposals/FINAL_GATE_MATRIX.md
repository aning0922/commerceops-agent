# V4-1 最终差异验证矩阵

2026-11-04（台北）。状态：**LOCAL_STAGE_GATE_ACCEPTED**。
当前代码 `261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e` / tree `34da95131e04d7360ea8aa5250ea40215bcb0713`。
原4fec完整工程/e7严格PG773/54ab四HTTP保持原source；261新影响检查和Mock33同源通过，
Root转交r10真实parent/probe0、两spec通过、11 consumer keys/10 mobile keys/32业务PNG、
最终SQL命令0、cleanup和独立closure=true。Main最终runtime/SQL/closure独审4e4741ad已核收。
AI视觉review `c7f508dc596878a327fbc8e175b4e9b369f538a6` 逐view/hash/IHDR核40原图无P1/P2，
人工视觉审批NOT_RUN。未读取作者WIP、身份或私有响应，未重跑任何验证。
本矩阵不宣布原19/99feature全覆盖或产品发布，本地阶段V41-01–06已按Root正式独审结论收口。


本地阶段 **V41-01–06 已完成并核收**，仅限合成owned环境与原合同受控范围。最终runtime独审
`4e4741ad56e5ee8d3a22bc9f4ac6564715d92955` / tree `85f0293eb07d3d648949df47674d7965c6294f18`，
[正式原件审查](https://github.com/aning0922/commerceops-agent/blob/4e4741ad56e5ee8d3a22bc9f4ac6564715d92955/docs/v4/v4-1/reviews/FINAL_RUNTIME_R10.md)采用该文件后续“完整实际运行追加核收”段；早期build-only/pending原文保留其时点。
r10同261/imagee834：2spec、11keys（10mobile子集）、4preview、7receipt/event、26当前effects及
2个历史替换tag分记，最终SQL0；source/tools与唯一允许next-env生成差异已核。原API清理130、
execution summary NOT_WRITTEN、Native browser exit NOT_EXPOSED、human审批NOT_RUN不改写。
旧4fec Full/e7 FullPG/54ab HTTP继续只属各自SHA；阶段接受不等于99功能、66页面、真机触摸、
外部业务、Hosted或生产发布通过，V4-2 NOT_STARTED。

## 1. 六卡功能与已有证据的实际层级

| 原卡 | 必须交付的真实功能 | 当前最高相关证据及剩余限制 |
| --- | --- | --- |
| V41-01 | 14模块导航、Shell、主题、加载/空/错误/恢复状态；未开放项明确标识 | 同261 Mock33及r10真实Shell的hidden/offline、迟到ACK、Native原生200%受控路径已最终核收；40原图AI视觉已核，人工审批NOT_RUN。可进入导航不等于全部业务页完成。 |
| V41-02 | 同源KPI、期间/币种/时区、Decimal指标及查询/钻取 | 54ab真实HTTP四案中的双店14/7/1日金标和成员核对；历史e466/r2 partial与同261 r10业务浏览器均按各自来源保留，r10受控路径和AI视觉已核。人工可读性审批NOT_RUN。 |
| V41-03 | 经营页、图表、规则洞察、异常待办及全局Copilot容器 | 54ab有限HTTP、历史partial与同261 r10读链、Shell覆盖层/焦点及Native受控路径分源核收，40原图AI视觉已核。模型未启用，规则解释不得称模型回答；人工审批NOT_RUN。 |
| V41-04 | 商品/订单授权列表与详情、标签及演示履约覆盖层 | HTTP目录案及PG专项、历史e466/r2 partial及同261 r10的4次标签/1次履约与逐键SQL已核；未知支付浏览器只核按钮禁用，不能声称实际拒绝POST；无真实Woo写入。 |
| V41-05 | 管理UI、筛选分页、详情关联、安全导出、身份/店铺切换清屏 | 历史e466/r2 partial及同261 r10分页、筛选、CSV下载、访客/店铺隔离按各自来源核收；不能推断每条独立路由、详情关联与全部权限矩阵已浏览器验收。新增当前页批量及真实390业务已执行，最终独审已核；逐页三尺寸及人工核对见UI清单。 |
| V41-06 | CSV/XLSX发现/映射/质量预览、原子确认、回执恢复和来源读回 | 54ab格式独立HTTP案、历史e466/r2 partial及同261 r10两次导入/4次preview与逐键SQL按各自来源核收；恶意输入与事务/权限由各专项及PG分账，不能据Mock或一次业务spec代签全部Gate。 |

逐卡预期以 [STAGE_SPEC](../STAGE_SPEC.md)、[CONTRACTS](../CONTRACTS.md) 为准；
逐页路径、截图槽位和人工判断以 [UI清单](UI_ACCEPTANCE_CHECKLIST.md) 为准。
本表描述最高相关证据，不把同一行尚未验证的预期自动提升为通过。

## 2. 严格来源账：不得跨SHA拼签

| 层 | 精确来源 / 现存核收 | 已核范围与未完成项 |
| --- | --- | --- |
| 完整工程 | `4fec4a7416d7b9434d979f461d5da78508cfb850` / tree `20044a26fe39850cc31943bf4e328abba3936f3e`；[回执](../../acceptance/v4-1/ENGINEERING_R3.json)、[935448独审](../reviews/ENGINEERING_4fec4a7_R3.md) | 原scripts.check三层native0，1529.567272s；4601 offline PASS、776 deselected、4 warnings；mypy616、文档312；npm audit0、pip-audit95包/vulns0/skip0。只属于4fec，不挂最终Shell源码。 |
| FullPG existing | `e7aeeca90e98cc4af5b5f8f8ba0faddd33182bd6` / tree `4e8349cfeec323668be316426871bc310b6ce53d`；[回执](../../acceptance/v4-1/PG_EXISTING_R2.json)、[独审](../reviews/PG_EXISTING_e7ae_R2.md) | actual=selected=passed596，24组，G1三/G2六；helper/worker/outer/cleanup0。预期unavailable命令native1保留；独立清理已核。 |
| FullPG phase3 / strict pair | 同e7来源；[最终回执](../../acceptance/v4-1/PG_PAIR_FINAL.json)、[7fc12c独审](../reviews/PG_PAIR_e7ae_FINAL.md) | phase3实际177通过，existing596；实际并集773、交集0，strict checker native0，G1三/G2六由existing认领，两线清理已核。只核精确e7，非未来UI新source的FullPG。 |
| 有限真实HTTP | `54ab68f054a136f98dac0a50986caced11362fbd` / tree `3b1ed40d717f7c0ed7fa7e85d626b9a9ca272990`；[四案独审](../reviews/HTTP54AB_FOUR_CASES.md) | dash/catalog/csv/xlsx四案driver/probe/outer0，各37 required命令，有限本地HTTP核收。API清理退出130保留；148命令记录不是148测试。不是最终浏览器或未来SHA的HTTP通过。 |
| 真实业务browser单项 | `e466f03436ba726b6050b10e879da68d80c7e372` / tree `3f1abf65275d01803aca93ec6976453f060ed209`；[partial独审](../reviews/BROWSER_E466_R2_BUSINESS_PARTIAL.md) | business spec8997ms/retry0，9业务POST/31journal、回执/effect来源已审；Shell失败，整案/Node1保持。部分业务通过不等于整案通过。 |
| Mock UI | [UI_MOCK_R4](../../acceptance/v4-1/UI_MOCK_R4.json)；[清单独审](../reviews/UI_CHECKLIST_83e343c.md) | 旧Mock来源与真实HTTP/浏览器分记；不代签4fec或逐页视觉验收。 |
| 261影响检查/Mock | `261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e`；[影响回执](../../acceptance/v4-1/COMBINATION_261F399.json)、[Mock33回执](../../acceptance/v4-1/UI_MOCK_BATCH_R4.json) | 235Python/74Node/Native40组件/TS通过，Mock33通过；组件40不启动browser，不代真实Native。非Full4601/773在新source重跑。 |
| 261最终扫描 | 同261；[回执](../../acceptance/v4-1/SCAN_261F399.json) | canonical wrapper0，dir/index0，history native1/1760reviewed/0blocking，refs变化保留。 |
| r10真实执行 | 同261；Root转交closedfinal SHA `0df4a06b87110816d449415bd5ad416b885de5d2f8191f10bf5781770462a192` | parent/probe0、双spec2PASS、consumer11keys/10mobilekeys、SQL命令0、独立closure=true；最终Main独审4e4741ad已核收。40PNG=32业务+3Shell+5Native，不推导全部页面覆盖。 |
| r10 AI视觉 | 同261；c7f508dc独审 | 40原图逐件hash/IHDR/view，无P1/P2；右侧表列需横滚/非真机touch/人工审批NOT_RUN保留，非运行权威替代。 |

原GC专项属于e54的两项有效actor锁屏障及三项合成历史GC，参见
[ADDITIONAL6独审](../reviews/ADDITIONAL6_e54c603.md)。自然24h/runtime过期INSERT未验证，
不将合成restore或历史STOPPED字段写成自然寿命/本轮真实parser reap证明。

### 浏览器失败与partial历史保留

来源取 [冻结运行账](../../acceptance/v4-1/RUNTIME_PROGRESS.json)；每案都须保留独立once、
原报告及cleanup，不能把后续修复覆盖旧失败。

| 案 | 来源 | 实际结果和缺口 |
| --- | --- | --- |
| e466/r1 | e466完整SHA同上 | 非root镜像读取失败，PG前停止，无浏览器业务核收。 |
| e466/r2 | e466完整SHA同上 | business partial通过；Shell390助手无可访问名，240036ms timeout；390截图/Native/offline/hidden/lateACK均未到。 |
| final/r3 | `8f6687560bb5c71804fd249068e2a9912fe35556` | business9504ms；Shell cookie按根URL检查，实际Path=/api/v4，失败。1440/1280/390截图存在不代表后续边界通过。 |
| final/r4 | `f7743310ff7a0808694efb40990b5a29ed251224` | business9077ms；offline恢复CDP response body不可取，原request身份UNKNOWN，不猜根因。 |
| final/r5 | e7完整SHA同上 | business8793ms；cover激活后visibility仍visible，拓扑/根因UNKNOWN；Native与lateACK未到。 |
| final/r6 | 4fec完整SHA同上 | business9619ms；bounds读为minimized但visibility仍visible，根因未确认；Native与lateACK未到。 |
| final/r7 | `2140fe22a97850a1c312393198b78a0225ff3b9a` | business10087ms；Shell首次currentFacts read_at失败，offline/hidden/Native/lateACK未到，整案failed_closed。 |
| final/r8 | `eb30d7b7ad26da95dcf1c03ea55c5b424fbd536d` | business10120ms；Shell Native TimeoutError，第一张Native PNG前失败，具体await未捕获；三次facts关联通过不代表Native成功，lateACK未到，整案failed_closed。 |
| final/r9 | `fbb29a429b7f680328ab4451a717adb3ad2d99c1` | 两spec通过但parent1，整案FAILED_OR_UNKNOWN；原错误码/stack未捕获，副本诊断PNG几何不符与phantom API count校正分层，最终SQL原native0保留，新consumer诊断不改旧parent。 |
| batch Mock/r1 | `5acf03ae30807c160aa110035127a4e308e95da9`；[回执](../../acceptance/v4-1/UI_MOCK_BATCH_R1.json) | 实际1PASS/1FAIL/31NOT_RUN，probe/worker/outer1、Web清理143；在最终write-lock完成前观察pending，requests长度0，原route时间线UNKNOWN。后续等待边界源码已审，不回写本案。 |

A/B及NoDefaults C只是独立实验：冻结账记四次hidden观察后2000ms意外normal，实验失败并闭合，
不是产品hidden通过。未来修片及新浏览器运行另记，旧business partial不提升为完整验收。

## 3. 最终组合差分与权威校正

历史fbb相对eb30的12路径增量覆盖批量/真实移动端与Native/父收验，已由此前矩阵记录；
261相对fbb的精确非文档差分为六路径，见 [最终来源核收](../reviews/FINAL_SOURCE_261F399.md)：

- frontend/v41-e2e/native-capture.ts
- tests/e2e/v41/native_zoom.cjs
- frontend/v41-tests/batch-tags.spec.ts
- frontend/v41-tests/lifecycle.spec.ts
- tests/e2e/v41/browser_shell.py
- tests/e2e/v41/test_browser_shell.py

Native模块/TS调用者/Python父三pin同为0023672bfb9f648a5df2deac397fd7159dfbbc4c1cb385c5cab9d3c97396c538。
公开ActionReceipt不含effect_count：consumer只接受显式None，缺字段/假0或1拒绝，
不得把None称数据库效果UNKNOWN；导入用真实row_count及同job/file uploads计数。
最终SQL逐原key receipt/event/effects/digest与canonical请求仍是独立权威。
新consumer核r9副本的通过不是原r9 parent0，也不是在旧registry上重放。

## 4. 当前实际层级及最终核收槽位

| 项 | 当前状态 | 不得扩大及剩余动作 |
| --- | --- | --- |
| D0冻结来源 | 261组合来源已独审 | 不把文档HEAD视作新的代码Full；六路径pin/审查与各历史source精确映射。 |
| D1受影响纯测 | 235Python/74Node/Native40组件同261通过 | Native组件40不含browser/截图；不称完整工程4601重跑。 |
| D2类型/Mock | TS与同261 Mock33通过，旧r1–r3失败保留 | Mock不代真实API/PG；旧r1的1PASS/1FAIL/31NOT_RUN不回写。 |
| D3真实浏览器 | r10双spec通过、11keys/10mobilekeys、32业务PNG，Root转交执行事实 | Main runtime/SQL/closure最终独审4e4741ad已核收；不从截图数推断原规划19/99或66页面全覆盖。 |
| D4批量/移动 | 当前页至少两商品串行、真实390商品/订单/CSV/XLSX和原键闭合已运行，已最终独审核收 | 只完整替换当前页标签，首错/取消停止；390 viewport不是实体手机，touch未测。 |
| D5 Native/视觉 | 五Native PNG已采集；40总图AI工程视觉无P1/P2 | Root另view三张Native200正常/底部可读；用户人工视觉NOT_RUN，静态图不证明所有交互/全部200%页面。 |
| D6扫描 | 261 canonical wrapper0/history native1/1760reviewed/0blocking | refs变化保持；不扩例外，不能给后续新refs预填通过。 |
| D7最终接受 | LOCAL_STAGE_GATE_ACCEPTED | Main确切runtime/SQL/closure独审4e4741ad已核收；Root单owner更新正式质量/manifest/review/PNG索引，本五文档不抢写。 |

r10原执行/closed原件、两spec原报告、journal、consumer与末态SQL、PNG索引分别交由Root/Main/Terra核。
本次文档未重新运行测试/collect/服务/扫描；所有临时服务已关闭，无持续URL。
复现须新Rootowned案，不自动重跑Full或真实外部provider。

## 5. 证据限制和必须保留的未知

- 4fec scanner：dir/index native0；history **native1、1760 reviewed、blocking0、wrapper0**。
  其中153 public false-positive、1607 merge-copy；不将native1重写为0。可达refs前后存在变化，
  原审查没有声称所有refs冻结，未来扫描数量须重新核。
- 工程source-before/after完整HEAD/tree/clean/tracked摘要、三层native及注册组收口有原件。
  after216安装字节、after identity/wrapper等值与停后ps不存在，只有当时owner封存声明；
  没有独立after map或ps stdout/stderr/returncode，不升级为逐项独立raw证明。
- 原e466工程mypy18项失败、202807工程offline16失败及其后13PASS/4FAIL目标验证、
  两次preflight阻断均保留。后续17PASS和4fec Full不改写旧失败；精确修片见
  [扫描测试独审](../reviews/SCAN_EXPECTATIONS_04b547c.md)。
- e7双线实际596+177=773、交集0与strict checker0已核，来源仍e7；旧8f668全局截止失败不拼接。
  后续source/集合/工具不一致或cleanup未知保持HOLD，不把e7的773转签261。
- HTTP/PG使用合成owned数据、模型未启用、外部Woo/飞书/provider未验；生产、Hosted、
  V4-2仍NOT_STARTED。实际模型费用UNKNOWN，工程公开registry/审计不写成完全零网络。

本次只更新Root指定五份正式收口草稿；未运行测试、collect、网络、服务、扫描Gate或任何资源。
提交前只做文档结构/差分及固定公开文件原生preflight；最终runtime独审结论已按4e4741ad普通收口，后续发布/人类审批不自动核收。
