# PR #53 Hosted 与主线合并门禁

2026-11-04 用户明确授权本次必要 Hosted CI，检查通过后正常合入 main 并核对合后结果；
不绕过保护，完成后继续暂停后续功能，等待新研究包。

## 首轮实际结果

[运行 41848095782](https://github.com/aning0922/commerceops-agent/actions/runs/41848095782) 的 PR head 为
`a1fc837d5e8ce161eb220edfb78295608a8ebdcb`，实际 checkout 为 GitHub 临时合并提交
`98ce4a1e523de5bae3eac683728d43f5c6a1c694`；其 tree 与该 head 相同。
运行终态五项失败，业务测试与 PG 配对未核收，不以原本地通过替代。

当前文件和 index 扫描均 native0；完整历史扫描 native1，1707项中1706已审、1项阻断。
唯一阻断是公开前端页面在临时合并提交中的完整文件副本：原机制仅接受既有精确 blob，
当前已验页面的完整 blob 不在该表，因此按设计拒绝。没有真实密钥泄漏结论。

整改限定为既有不可变来源表中增加该页面的精确已验 source、完整 blob 及原位置/内容绑定，
同步原衍生 provenance 配置和针对性正反例；检测规则、分类算法、扫描范围、业务和权限不变。
正规生成确认222条规则、96项精确行例外与 `.gitleaks.toml` 同字节，仅新增一个完整文件锚点。
修复的实际提交与独立检查另按冻结回执核对，不预填下一轮通过。

## 合并条件

使用本次精确候选完成 quality、phase3、frontend、n01-web 和 pg-pair 全部既有门禁；
PG 严格来源配对与清理证据另核，不能只看绿色状态。再次确认 main 与 PR HEAD，
在原保护规则下普通 merge 并保留分支，然后核对合并提交及其主线 CI。
首轮独立诊断见 [原始诊断](HOSTED_R1_DIAGNOSTIC.md) 与 [实际结果](HOSTED_R1_RESULT.json)。
实时结果见 [PR #53](https://github.com/aning0922/commerceops-agent/pull/53)。

Hosted 许可不授权真实模型/embedding、飞书/Woo业务外发、生产或下一阶段功能。
旧失败、原本地证据、UNKNOWN 与人工未验边界保持。

## 测试可移植性审查

首个锚点候选的生产元数据通过静态与真实原案核对；新增 pytest 曾硬编码旧 PR 临时合并对象，
冷 Hosted 不保证取得该不可达对象，独审因此保持 HOLD，没有释放新 CI。
回归用例须改为自行构造真实双亲合并并扫描，固定祖先来源与整文件内容不变；
真实旧案仅作为原始诊断材料，不添加网络 fetch、skip 或本机取证 ref 依赖。

## 精确整改与独立核收

生产锚点候选 `7ac8fa660cea05af3afb9d300a4066e6525c2bf2` 及测试可移植性增量
`8f03e90a35a7c2bffb38466133a468b1de05e8ea` 已独审，后者关闭前者的新增测试可移植性 P2。
Root 按普通提交集成；[原候选独审](HOSTED_SCAN_INITIAL_REVIEW.md)和
[最终增量核收](HOSTED_SCAN_FINAL_REVIEW.md)保留各自时点。

既有分类器复用原 63a5a4f 的精确第9行、列43–116与Match/span摘要，没有新增行例外；
只给已验261源码的整文件blob增加一个来源锚点，40变41。
本地原兼容组263项为261通过/2失败；中间13项为12通过/1失败，后续13/13与最后2/2分源记录。
可移植性最终模块12/12，另一个既有枚举用例此前已通过且源码未变；不拼成修后263全绿。
Ruff、格式、mypy及最后current/index原生检查均通过。
真实首轮合并对象的51项发现原生退出1、分类后0阻断，旧原始失败未回写。

当前无未闭合已报告P1/P2，允许对新候选运行正式Hosted；本段不预填该运行结果。

## 第二轮实际结果与诊断范围

[运行41852391468](https://github.com/aning0922/commerceops-agent/actions/runs/41852391468)
head为`cbd5d5464b9e2b4a62463f2ba51d100125326e8c`，实际checkout为
`de4d04db56e0de7f5f6df9eb740c84819ae554d7`，tree与候选一致。
历史扫描1707项全部核收、0阻断，关闭首轮精确副本问题；本轮五项最终失败。
四上游均停在M3镜像准备，只有固定generic诊断，底层原因UNKNOWN；
Full、PG、Mock/legacy Web、N01均未到达，artifact为空，[Web原件核验](HOSTED_R2_WEB_RESULT.json)。
不以旧本地通过替代，也不把镜像准备失败冒称业务断言失败或deadline已到。

不盲重跑第三轮。先在新owned本机以独立新tag、明确linux/amd64、冻结原始源码上下文，
执行一次最多300秒构建取证，固定新绝对截止和清理预留；不启动PG/业务服务、不覆盖正式镜像tag、
不生成正式prepared receipt、不清理未知缓存或资源。原始构建日志私有保存，
本机成功不能证明Hosted成功，新案错误也不追填原Hosted历史根因。
若仍不能定位，再独审原helper的最小固定阶段诊断增强；所有版本、hash、权限、时限和保护不放宽。

## 独立本机 amd64 案结果

[单次诊断回执](LOCAL_AMD64_DIAGNOSTIC.json)：冻结cbd5d54原始tracked上下文，
15:08:05Z建立600秒窗口；构建实际300.287秒超时，客户端native130、TERM并reaped，
15:13:08Z有界收口，后续独立只读核验在原截止内完成。没有成功新tag或正式prepared receipt。
日志只显示模拟amd64的APT安装收尾，未到开发包下载和编译；不解释或关闭旧Hosted根因。
已识别本案标签容器/网络/卷为空，17个登记客户端组不存在；BuildKit内部任务未独立暴露，
保留UNKNOWN，不签全daemon清理或清空未知缓存。本机不重试。

随后只为原构建入口增加安全诊断：独占私有日志、固定进入/完成阶段、有限错误枚举和原始退出/回收状态。
仍不打印原始输出，不改变包/版本/TLS/hash、构建命令顺序、300秒上限、85/75秒预留或源/架构核验。
该增量须冻结单测和独审后才释放新的Hosted；不添加下一阶段业务能力。

## 第三轮前的诊断代码核收

源码诊断8835892与有界读取增量2513597已独审，
[原审](HOSTED_IMAGE_DIAGNOSTIC_INITIAL_REVIEW.md)、[更正](HOSTED_IMAGE_DIAGNOSTIC_CORRECTION.md)与
[最终增量核收](HOSTED_IMAGE_DIAGNOSTIC_FINAL_REVIEW.md)各自保留。
最后28项受影响纯测通过、27未选中；此前相关146项与直接消费者69项按各自来源记录，
缺Node导致的38项准备失败不回写。Ruff/格式/mypy及作者提交后原生增量历史扫描通过，无新例外。

每日志最多8MiB，fstat/read(limit+1)/读取后尺寸检查，bytes一次读取复用于解析与hash；
诊断最多5秒且保留75秒预留，超限或预算不足不发布部分hash。
诊断不可用只拒收该诊断，原核心异常继续传播，核心成功不因可选诊断缺失而改挂失败。
构建300秒、TERM/KILL/reap、源/架构/正式receipt校验、所有包版本/哈希与原命令顺序不变。
第三轮用于获取精确Hosted证据，不预填通过，也不追填前两轮底层UNKNOWN。

旧main已正常备份，未来新阶段须从实时核准的最新已验main开始；本任务不启动V4-2。

## 第三轮实际结果与固定行位恢复

[运行41861157096](https://github.com/aning0922/commerceops-agent/actions/runs/41861157096)
实际checkout e973c64f/tree6905148，五项失败；[精确结果](HOSTED_R3_RESULT.json)。
这次是current/index公开固定行位约束失败，不是新的密钥命中或merge-copy历史分类失败。
预算测试顶部新增time导入导致原已审行191移至192；历史扫描仍1707已审、0阻断，镜像及业务未到达。
原审漏核完整wrapper的公开行位置合同，失败与更正不回写。

c70995f仅将time导入放入六个新增测试函数，恢复原191与完整hash；
[独立复审](HOSTED_ROW_RESTORATION_REVIEW.md)确认其余AST相同、未改helper/Dockerfile/规则/例外。
定向28项通过、27未选中；current/index原公开行校验与原生扫描、作者增量历史均通过。
下一次正式Hosted前，Root须对最终组合执行原完整scanner wrapper，
并将实际main与候选完整树构造的真实双亲merge纳入历史预检；
不再只以作者增量扫描代替完整快照约束。实际结果另按最终提交私有回执记录，不预填。


## 第四轮实际进展与分组容量整改

[运行41864322517](https://github.com/aning0922/commerceops-agent/actions/runs/41864322517)
head为bcebf10，实际checkout305d0d2e3547c3d11cc42ca8da4bb2b51485cd5e，
tree8f62a8a5e443916f55bf552e52276f641a8c3eab。完整scanner和镜像准备已通过；
frontend、n01-web已成功，Full4736通过/776排除、mypy617源码通过、Contract90，
五组Mock13/8/22/9/3；真实Web read7/write10/items7和N01六项通过，
原安全不变量/来源摘要/停止清理已独核。此处不替代PG与配对门禁。

quality首combined-existing组290节点在300秒命令上限耗尽：268项已有call通过、
269项开始，无已记录断言失败；266项在timeout前已有call通过，另2项在停止过程中完成。
后续306项未到达、G1未完成，cleanup0与stopping_confirmed保留；
sample_error的JSONDecodeError仍UNKNOWN。不将它表述为全部773通过。
[原始独审](HOSTED_R4_QUALITY_PARTIAL_REVIEW.md)与
[逐项时间/映射核算](HOSTED_R4_QUALITY_TIMING_MAPPING.md)保留失败来源。

第269项是在timeout事件后开始，不能认定其造成此前超时。
前268项setup/call/teardown累计287.848495秒支持首组累计容量不足。
最小修复仅在原分组函数抽出完整自然V40/V41模块，原首组变legacy236，
另四组7/19/23/5置于原legacy之后、P5/M3之前；全部596+177=773节点、
模块内部顺序、原300秒/总截止/清理预留/G1G2/严格配对保持。
不改业务、数据库、测试断言或workflow；增加命令启动开销能否满足总预算须由新实际运行核验。
修复需单owner冻结、独审及Root完整快照/合并历史预检后才释放新Hosted。
此时phase3与最终pair结果尚待收口，旧run不取消、不回写或盲重跑。
