# V4-1 最终差异验证矩阵（DRAFT）

2026-11-04（台北）。状态：**DRAFT / SOURCE_REVIEWED_RUNTIME_PENDING**。
本次文档事实快照为 Root 冻结 `477b262f399293300ceb8db0e0f43bbbff50c267`；
待运行组合为 `fbb29a429b7f680328ab4451a717adb3ad2d99c1` / tree
`ef6d8230ac4b58401af2771d722064aadacc5eed`。只读冻结Git、公开回执及Root允许的
r9 incremental-source-proof，不读作者WIP、身份或私有响应。
该组合的批量/真实移动端/Native与父校验源码已独审，不等于新Mock/真实browser通过。
4fec工程与e7双线PG保持原source；本文不授权运行、不宣布六卡或19/99功能完成。

## 1. 六卡功能与已有证据的实际层级

| 原卡 | 必须交付的真实功能 | 当前最高相关证据及剩余限制 |
| --- | --- | --- |
| V41-01 | 14模块导航、Shell、主题、加载/空/错误/恢复状态；未开放项明确标识 | Mock、源码及部分真实Shell；完整真实hidden/offline、原生200%、迟到ACK、最终截图/人工可读性仍待核。可进入导航不等于全部业务页完成。 |
| V41-02 | 同源KPI、期间/币种/时区、Decimal指标及查询/钻取 | 54ab真实HTTP四案中的双店14/7/1日金标和成员核对；e466/r2业务浏览器partial有dashboard/期间/drilldown。HTTP数值通过不代签最终UI可读性。 |
| V41-03 | 经营页、图表、规则洞察、异常待办及全局Copilot容器 | 真实HTTP与业务browser partial支持部分读链；模型未启用，规则解释不得称模型回答。最终布局、覆盖层/焦点及Native仍待核。 |
| V41-04 | 商品/订单授权列表与详情、标签及演示履约覆盖层 | HTTP目录案及PG专项、e466/r2标签递增与单订单履约partial；未知支付浏览器只核按钮禁用，不能声称实际拒绝POST；无真实Woo写入。 |
| V41-05 | 管理UI、筛选分页、详情关联、安全导出、身份/店铺切换清屏 | e466/r2真实分页、筛选、CSV下载、访客/店铺隔离partial；不能推断每条独立路由、详情关联与全部权限矩阵已浏览器验收。新增当前页批量及真实390业务已冻结源码，运行待核；逐页三尺寸及人工核对见UI清单。 |
| V41-06 | CSV/XLSX发现/映射/质量预览、原子确认、回执恢复和来源读回 | 54ab格式独立HTTP案与e466/r2导入浏览器partial，含一次效果/读回；恶意输入与事务/权限由各专项及PG分账，不能据Mock或一次业务spec代签全部Gate。 |

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
| batch Mock/r1 | `5acf03ae30807c160aa110035127a4e308e95da9`；[回执](../../acceptance/v4-1/UI_MOCK_BATCH_R1.json) | 实际1PASS/1FAIL/31NOT_RUN，probe/worker/outer1、Web清理143；在最终write-lock完成前观察pending，requests长度0，原route时间线UNKNOWN。后续等待边界源码已审，不回写本案。 |

A/B及NoDefaults C只是独立实验：冻结账记四次hidden观察后2000ms意外normal，实验失败并闭合，
不是产品hidden通过。未来修片及新浏览器运行另记，旧business partial不提升为完整验收。

## 3. fbb组合的实际12路径增量与已审来源

下列是相对最后browser eb30的实际代码路径，不再是旧“六路径未冻结”提案。
Root `.audit/v41-final-r9/incremental-source-proof.json` 绑定fbb/tree ef6d；文档/refs变化另记。
证明列出backend、scripts、tests/v41/backend、frontend/app相同subtree，不能扩写为全部
frontend或全部tests未变。原4fec/e7 Gate只按该差分证明复用其未受影响范围，不换source标签。

| 精确路径 | 已审增量与待验证范围 |
| --- | --- |
| `frontend/components/v4/business-pending.module.css` | 当前页批量面板/进度与移动布局，真实三尺寸可读性待验。 |
| `frontend/components/v4/business-pending.tsx` | 显式多选/确认、替换标签与成功/拒绝/待核/未发送结果，不是整批原子写。 |
| `frontend/components/v4/demo.tsx` | 单项执行窄复用、批量串行与生命周期取消；COMMITTED后读回拒绝仍保待核/pending。 |
| `frontend/lib/v41-batch-tags.d.mts` | 批量协调类型边界，需组合tsc。 |
| `frontend/lib/v41-batch-tags.mjs` | 前项严格读回后才发送后项；revision/version/原key与首错停止，需组件/真实journal对账。 |
| `frontend/v41-e2e/business.live.spec.ts` | 真实1440/1280/390业务矩阵，至少两个当前页商品批量、原键与真实效果，不据collect称通过。 |
| `frontend/v41-e2e/native-capture.ts` | Native新模块pin接线与同案调用，不改成viewport/CSS缩放。 |
| `frontend/v41-tests/batch-tags.spec.ts` | Mock假后端原key/query校验、COMMITTED后409/403、UI结束边界；旧r1失败保留，新运行待核。 |
| `frontend/v41-tests/batch-tags.test.mjs` | 纯串行/首错/取消/revision和标签替换契约，非真实API提交。 |
| `tests/e2e/v41/browser_shell.py` | batch跨key原journal顺序、导入请求/文件/job/version/来源与图像验收、Native pin组合。 |
| `tests/e2e/v41/native_zoom.cjs` | 安全阶段定位/cleanup保持原失败；实际Native、五PNG及人工视觉待验。 |
| `tests/e2e/v41/test_browser_shell.py` | 父收验正例与顺序/导入job.version等拒绝例，只证明纯验证器。 |

源码依据：[批量产品及后续修复独审](../reviews/BATCH_TAGS_A7E5F9F.md)、
[Mock原键/等待边界独审](../reviews/MOCK_BATCH_4427f34.md)、
[真实移动业务spec独审](../reviews/BUSINESS_MOBILE_2AE7356.md)、
[父校验d36增量关闭](../reviews/QA_MOBILE_PARENT_9726885.md)、
[Native源码独审](../reviews/NATIVE_217baea.md)。报告内旧HOLD/P2/失败保留，
只采用其明确接受的后续冻结段；源码核收不代运行。
原NoDefaults Shell路径与business原生PW分离的已核约束继续保持，实际新browser需另案绑定。

## 4. fbb的最小差异验证（本文未执行，实际回执待Root更新）

按顺序执行，均由Root另给精确来源/工具/新owned case/UTC/清理预留与执行owner。

| 步骤 | 固定对象/建议入口 | 必须保存的证据与完成判据 |
| --- | --- | --- |
| D0 差分准入 | 比较最终冻结树相对4fec工程、e7PG、54abHTTP及最后browser的实际diff | 12路径组合源码/已审修片映射与独立指纹核对；产品UI已变，backend/scripts/锁的实际相等范围须有清单，不能称“只改harness”。各层实际source分列，文档/ref新增也登记。 |
| D1 纯测试和静态检查 | Node固定版本 `node --test frontend/v41-tests/batch-tags.test.mjs`、Native `--check`/原无浏览器self-test；Python目标 `pytest tests/e2e/v41/test_browser_shell.py -m offline`；对应Ruff/format/mypy | 冻结后先确认原生入口/依赖均成立；批量原组件与受影响父拒绝/cleanup路径，无skip/retry，不扩大成Full重跑。无服务/身份读取，数量取实际。 |
| D2 TypeScript | 独立冻结依赖环境 `npm --prefix frontend run typecheck` | 核tsconfig确实覆盖新增fixture、Shell及相关调用者，无临时排除或忽略诊断；完整tsc原native0，类型检查不代替运行。 |
| D2b 新Mock33计划 | 原四spec冻结配置的collect与新owned Mock运行 | 33只是待执行集合，不预填33PASS；含新batch spec与原三spec，保留r1的1PASS/1FAIL/31NOT_RUN，验证原key/UNKNOWN/409/403、取消/迟到和390Mock后仍不得代真实业务。 |
| D3 双spec联合collect | 同一固定Playwright config的business与Shell联合 `--list` | 固定实际两个title及原节点完整集合、workers1/retries0；新fixture仅Shell。冻结配置的readBrowserCase需要Root新安全manifest/工具pins，因此collect须单独准入，不能把无配置失败伪造为收集通过。不得启动server或测试体来补collect。 |
| D4 新真实browser | 同最终source+新镜像/工具/全新profile/单case，原business+Shell闭合入口 | 不复用旧once/subject。父注册与attach ACK原件、真实offline/hidden谓词及清敏感内容/恢复；cookie Path、五identity、creation key、create1/零额外POST；至少两商品真实batch串行/跨key原journal顺序、真实390商品/订单/CSV/XLSX操作与截图、完整来源journal/末态、Native200与受控lateACK；正常/失败退出与child/端口独立清理均按原合同。一次失败即停，无自动重试。 |
| D5 Native和视觉 | 原已审native模块/调用者、新同案会话/profile及三尺寸/200%截图 | 核实际zoom1→2/event/几何、截图hash和原退出层级；捕获状态只到待视觉审，不伪造浏览器native0。1440/1280/390、键盘/Esc/焦点/reduced-motion和逐页人工可读性须独立结论。 |
| D6 最终扫描 | 精确最终源码与可达refs上原 `python -m scripts.scan_secrets` | dir/index及all-reachable history完整执行，保留原native/包装分类/具体finding指纹、前后source与refs快照；原规则/例外来源不放宽。4fec的1760不能预填最终数量。 |
| D7 合批核收 | Root实际回执更新本矩阵/六卡清单；独审最终diff与运行 | e7 phase3与严格773配对已核；工程4fec、HTTP54ab、browser最终source各自写实。受影响检查闭合不把旧Full改标签；整体完成须有最终人工/产品与遗留项结论。 |

D1–D6是最小影响计划，不是本文件已执行的命令。Node/npm/Python实际绝对路径、collect argv与
scope须在最终源码冻结后确认，不读取历史身份配置。依赖独立、不触共享node_modules；安装/审计
若另需网络按Root范围准入。这里不授权再跑完整scripts.check、PG、HTTP或浏览器。
Root已核收4fec完整工程，后续仅按最终差异审定必要检查；不能强行把完整工程搬到新SHA，
本次产品UI/batch/mobile/Native增量必须完成受影响检查和新真实browser；后端/四HTTP案是否需补跑由精确差分决定，不自动重跑Full。

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
  后续source/集合/工具不一致或cleanup未知保持HOLD，不把e7的773转签fbb。
- HTTP/PG使用合成owned数据、模型未启用、外部Woo/飞书/provider未验；生产、Hosted、
  V4-2仍NOT_RUN。实际模型费用UNKNOWN，工程公开registry/审计不写成完全零网络。

本次仅更新本矩阵与LOCAL_DEMO_REPRODUCTION两份静态草稿；未运行测试、collect、网络、服务、扫描Gate或任何资源。
提交前只做文档结构/差分及固定公开文件原生preflight；最终运行结果留待Root实际回执更新。
