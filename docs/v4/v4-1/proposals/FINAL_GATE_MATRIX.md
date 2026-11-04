# V4-1 最终差异验证矩阵（DRAFT）

2026-11-04（台北）。状态：**DRAFT / PROPOSED / FINAL_SOURCE_PENDING**。
事实快照为 Root 冻结 `faf9a0725a5f1ffc326abf75ea57d49c453a65ed`，只读该 Git 对象内
合同、公开回执与独审；未读取任何作者 WIP、身份或私有响应。
本文件仅规划后续差异验证，不授权运行，不核收未来六路径，也不宣布六卡完成。
下述 phase3 running 是本快照状态，后续必须由 Root 更新真实闭合回执。

## 1. 六卡功能与已有证据的实际层级

| 原卡 | 必须交付的真实功能 | 当前最高相关证据及剩余限制 |
| --- | --- | --- |
| V41-01 | 14模块导航、Shell、主题、加载/空/错误/恢复状态；未开放项明确标识 | Mock、源码及部分真实Shell；完整真实hidden/offline、原生200%、迟到ACK、最终截图/人工可读性仍待核。可进入导航不等于全部业务页完成。 |
| V41-02 | 同源KPI、期间/币种/时区、Decimal指标及查询/钻取 | 54ab真实HTTP四案中的双店14/7/1日金标和成员核对；e466/r2业务浏览器partial有dashboard/期间/drilldown。HTTP数值通过不代签最终UI可读性。 |
| V41-03 | 经营页、图表、规则洞察、异常待办及全局Copilot容器 | 真实HTTP与业务browser partial支持部分读链；模型未启用，规则解释不得称模型回答。最终布局、覆盖层/焦点及Native仍待核。 |
| V41-04 | 商品/订单授权列表与详情、标签及演示履约覆盖层 | HTTP目录案及PG专项、e466/r2标签递增与单订单履约partial；未知支付浏览器只核按钮禁用，不能声称实际拒绝POST；无真实Woo写入。 |
| V41-05 | 管理UI、筛选分页、详情关联、安全导出、身份/店铺切换清屏 | e466/r2真实分页、筛选、CSV下载、访客/店铺隔离partial；不能推断每条独立路由、详情关联与全部权限矩阵已浏览器验收。逐页三尺寸及人工核对见UI清单。 |
| V41-06 | CSV/XLSX发现/映射/质量预览、原子确认、回执恢复和来源读回 | 54ab格式独立HTTP案与e466/r2导入浏览器partial，含一次效果/读回；恶意输入与事务/权限由各专项及PG分账，不能据Mock或一次业务spec代签全部Gate。 |

逐卡预期以 [STAGE_SPEC](../STAGE_SPEC.md)、[CONTRACTS](../CONTRACTS.md) 为准；
逐页路径、截图槽位和人工判断以 [UI清单](UI_ACCEPTANCE_CHECKLIST.md) 为准。
本表描述最高相关证据，不把同一行尚未验证的预期自动提升为通过。

## 2. 严格来源账：不得跨SHA拼签

| 层 | 精确来源 / 现存核收 | 已核范围与未完成项 |
| --- | --- | --- |
| 完整工程 | `4fec4a7416d7b9434d979f461d5da78508cfb850` / tree `20044a26fe39850cc31943bf4e328abba3936f3e`；[回执](../../acceptance/v4-1/ENGINEERING_R3.json)、[935448独审](../reviews/ENGINEERING_4fec4a7_R3.md) | 原scripts.check三层native0，1529.567272s；4601 offline PASS、776 deselected、4 warnings；mypy616、文档312；npm audit0、pip-audit95包/vulns0/skip0。只属于4fec，不挂最终Shell源码。 |
| FullPG existing | `e7aeeca90e98cc4af5b5f8f8ba0faddd33182bd6` / tree `4e8349cfeec323668be316426871bc310b6ce53d`；[回执](../../acceptance/v4-1/PG_EXISTING_R2.json)、[独审](../reviews/PG_EXISTING_e7ae_R2.md) | actual=selected=passed596，24组，G1三/G2六；helper/worker/outer/cleanup0。预期unavailable命令native1保留；独立清理已核。 |
| FullPG phase3 / strict pair | 同e7来源；[冻结运行账](../../acceptance/v4-1/RUNTIME_PROGRESS.json) | phase3在本快照仍RUNNING，最终native/actual/cleanup/独审PENDING；strict pair未完成。完整collection773、另一分区计划177只是计划，**不得写773 PASS或实际union完成**。 |
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

A/B及NoDefaults C只是独立实验：冻结账记四次hidden观察后2000ms意外normal，实验失败并闭合，
不是产品hidden通过。未来修片及新浏览器运行另记，旧business partial不提升为完整验收。

## 3. 最终Shell NoDefaults六路径合同（仅PROPOSED）

Root本轮只转交路径与职责，**内容/commit/tree/评审/运行全部PENDING**。不得读取WIP推定实现。

| 路径 | 冻结后最小核对 |
| --- | --- |
| `frontend/v41-e2e/owned-cdp.fixture.ts` | 仅Shell使用的owned浏览器fixture；无身份/launch默认回退，不改business原生PW路径；真实CDP、child及端口由新case绑定。 |
| `frontend/v41-e2e/owned-cdp.argv.json` | 完整固定argv作为独立数据审查；完整参数须与Root准入一致，不暗增权限或使用日常profile。实际最终内容及指纹待冻结。 |
| `frontend/v41-e2e/shell.live.spec.ts` | 只接已审fixture；原hidden/offline/cookie/五identity/creation key/create1/零额外POST/Native/lateACK断言完整保留。 |
| `tests/e2e/v41/browser_shell.py` | SourcePaths更新；父先登记loopback端点、child身份/出生/PGID，attach前ACK；验收最终native close和端口关闭，不能从正常return推断资源不存在。 |
| `tests/e2e/v41/test_browser_shell.py` | 固定父链与故障/清理纯测试按冻结差分定位，检查登记/ACK失败与identity漂移等原拒绝保护，不能用fake代签实际浏览器停止。 |
| `frontend/v41-tests/owned-cdp.fixture.test.mjs` | 无服务纯测试核固定fixture/argv边界及独立拒绝路径，具体节点数由最终代码实际collect/执行取得。 |

business spec、live-business.fixture、产品组件、backend、schema/权限、锁及正式scanner都不在
这六路径范围。若最终diff超出，Root须重新确定影响范围，不能沿用下节最小矩阵。

## 4. 冻结后的最小差异验证（全部PROPOSED / 本文NOT_RUN）

按顺序执行，均由Root另给精确来源/工具/新owned case/UTC/清理预留与执行owner。

| 步骤 | 固定对象/建议入口 | 必须保存的证据与完成判据 |
| --- | --- | --- |
| D0 差分准入 | 比较最终冻结树相对4fec工程、e7PG、54abHTTP及最后browser的实际diff | 六路径完整源码独审；产品/backend/scripts/锁等未变须有真实路径/hash清单，不能靠“只改harness”一句话。各层实际source分列，文档/ref新增也登记。 |
| D1 纯测试和静态检查 | Node固定版本 `node --test frontend/v41-tests/owned-cdp.fixture.test.mjs`；Python目标 `pytest tests/e2e/v41/test_browser_shell.py -m offline`；对应Ruff/format/mypy | 冻结后先确认原生入口/依赖均成立；全部原例及受影响拒绝/cleanup路径，无skip/retry，不扩大成Full重跑。无服务/身份读取，数量取实际。 |
| D2 TypeScript | 独立冻结依赖环境 `npm --prefix frontend run typecheck` | 核tsconfig确实覆盖新增fixture、Shell及相关调用者，无临时排除或忽略诊断；完整tsc原native0，类型检查不代替运行。 |
| D3 双spec联合collect | 同一固定Playwright config的business与Shell联合 `--list` | 固定实际两个title及原节点完整集合、workers1/retries0；新fixture仅Shell。冻结配置的readBrowserCase需要Root新安全manifest/工具pins，因此collect须单独准入，不能把无配置失败伪造为收集通过。不得启动server或测试体来补collect。 |
| D4 新真实browser | 同最终source+新镜像/工具/全新profile/单case，原business+Shell闭合入口 | 不复用旧once/subject。父注册与attach ACK原件、真实offline/hidden谓词及清敏感内容/恢复；cookie Path、五identity、creation key、create1/零额外POST；完整business来源journal/末态、Native200与受控lateACK；正常/失败退出与child/端口独立清理均按原合同。一次失败即停，无自动重试。 |
| D5 Native和视觉 | 原已审native模块/调用者、新同案会话/profile及三尺寸/200%截图 | 核实际zoom1→2/event/几何、截图hash和原退出层级；捕获状态只到待视觉审，不伪造浏览器native0。1440/1280/390、键盘/Esc/焦点/reduced-motion和逐页人工可读性须独立结论。 |
| D6 最终扫描 | 精确最终源码与可达refs上原 `python -m scripts.scan_secrets` | dir/index及all-reachable history完整执行，保留原native/包装分类/具体finding指纹、前后source与refs快照；原规则/例外来源不放宽。4fec的1760不能预填最终数量。 |
| D7 合批核收 | Root实际回执更新本矩阵/六卡清单；独审最终diff与运行 | phase3真实闭合及同e7严格pair待独立核；工程4fec、HTTP54ab、browser最终source各自写实。受影响检查闭合不把旧Full改标签；整体完成须有最终人工/产品与遗留项结论。 |

D1–D6是最小影响计划，不是本文件已执行的命令。Node/npm/Python实际绝对路径、collect argv与
scope须在最终源码冻结后确认，不读取历史身份配置。依赖独立、不触共享node_modules；安装/审计
若另需网络按Root范围准入。这里不授权再跑完整scripts.check、PG、HTTP或浏览器。
Root已核收4fec完整工程，后续仅按最终差异审定必要检查；不能强行把完整工程搬到新SHA，
也不因harness测试变化自动重复完整后端/四HTTP案。

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
- FullPG existing实际596通过，不代表phase3或pair。旧8f668全局截止失败不拼到e7新窗。
  后续source/集合/工具不一致或cleanup未知应保持HOLD，不补造实际773 PASS。
- HTTP/PG使用合成owned数据、模型未启用、外部Woo/飞书/provider未验；生产、Hosted、
  V4-2仍NOT_RUN。实际模型费用UNKNOWN，工程公开registry/审计不写成完全零网络。

本文只新增此路径；未运行测试、collect、网络、服务、扫描Gate或任何资源。
提交前只做文档结构/差分及固定公开文件原生preflight；最终运行结果留待Root实际回执更新。
