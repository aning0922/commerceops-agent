# V4 SCAN a4f有限例外提案独立审查

日期：2026-11-03（Asia/Taipei）。**结论：ACCEPT_SCOPED_SCAN_COMPAT，0 P1 / 0 P2。** 只接受本次精确21快照span与89历史指纹的兼容，不签完整仓库dir/index/allrefs扫描、业务或阶段Gate。

## 来源与授权范围

candidate `a4f63589462a554c14514edcc870af14fbe2fcf7` / tree `14b00052559b55a37ad4e43a1145b44546377d19`，本次7文件差异只涉及原scanner/config/provenance/generator/tests和事实文档。读取提交对象，不读SCAN未提交WIP；唯一外部冻结证据为SCAN独占`.audit/v4-0/diff-preflight/SAFE_METADATA.json`，独立读得SHA256 `858a31d5b0987091e0cd82a2fdfcd10a03097ca1c68ed3d1cb368445044f4d73`，与提案一致。

其21 snapshots集合与固定V4_PREFLIGHT_SNAPSHOTS逐项一致；99 history记录中89个public_literal_observed_not_approved与固定V4_PREFLIGHT_HISTORY在完整source SHA/path/行范围/rule/span hash/Match hash/fingerprint上精确相等，其余10个already_reviewed未被重复登记为新增。89指纹各不相同、涉及19个来源提交。来源限定ea48和WEB63a及冻结元数据中其历史对象，不吸纳未来commit。

## 全部21快照的公开用途

逐项读取完整span和上下文，独立核完整span hash；不是仅按变量名、测试路径或相同值概括批准。

| 精确来源路径 | 行 | 已核用途 |
| --- | --- | --- |
| ea48 tests/e2e/v4/test_supervisor.py | 122 | tmp_path/monkeypatch测试参数类型声明 |
| ea48 tests/e2e/v4/test_strict_response.py | 12 | 固定UUID请求键测试输入，不是认证密钥 |
| ea48 tests/e2e/v4/http_probe.py | 147、259、364 | request_key/fixture_version请求字段与变量引用，未含运行凭据值 |
| ea48 tests/e2e/v4/http_probe.py | 394 | security_negatives中deliberately-wrong测试CSRF；用于拒绝路径 |
| ea48 docs/v4/design/IDENTITY_SQL_PLAN.md | 139–140、264 | request_key/canonical_request列声明；principal/auth_version检查说明 |
| ea48 backend/migrations/versions/0024_v4_demo_foundation.py | 118–119、220、222 | 两列声明；session_create/reset允许字段集合 |
| 同上0024 | 351、367、385、406 | 身份、回执、事件的版本/代际相等比较 |
| 同上0024 | 430 | 存储过程哈希参数及类型声明，不是哈希实值 |
| WEB63a frontend/app/v4/[[...path]]/page.tsx | 9 | approvedApiOrigin参数及local_http传输枚举，无实际origin/env值 |
| WEB63a frontend/lib/v4-context.mjs | 77、83、89、112 | logout/reset/persona/create的代际比较表达式 |

89历史记录的全部原始Git span/hash也独立核对。其20种不同span内容均为上述公开类型；相对21快照的内容集合额外出现一处缩进不同的代际比较和旧`(body->'body')-ARRAY['request_key','fixture_version']`字段集合表达式，同样为代码，不含秘密。保留不同commit/位置和merge -m命中，未按相同文字放宽到未来来源。

## 规则、派生配置和实际接线

独立解析TOML：所有222条检测规则保持，与旧0ca相比仅追加21个generic-api-key allowlist。旧58个目录例外完整保留，现合79（generic78/另1）；旧历史20、fa13、追加10三组JSON逐项未变。新21项均为精确路径AND完整行/span的Unicode regex；逐一独立重构并与生成结果相等，未使用目录通配/关键字/UUID形状豁免。config hash及每条provenance来源、行列、span/Match hash精确一致。

执行精确history_config函数的纯检查：移除全部34个V4 blocks后，解析对象与`7c262fb:.gitleaks.toml`完全相同，222 rules/45旧native allowlists。运行时git命令仍含`--all --full-history -m --text --no-textconv --no-ext-diff`；本proposal没有用限定预检命令替换正式全可达扫描。

approved_v4_history_finding仅scope=git，逐项匹配RuleID/File/Commit/起止行列/Fingerprint和redacted Match hash，再git show固定source重核完整span hash。dir/index不借用历史fingerprint。快照前置检查同时核固定行、完整span hash和新增重复位置；原位置重复的已登记两处同值行按各自固定集合处理，不扩到新位置。

## 独立检查结果

在Reviewer工作目录以精确提交源码提取纯函数/常量执行，临时合成文件全部放Reviewer `.audit`临时目录且已清理；未切作者分支或运行作者WIP。

- 21快照+89历史共110个完整source span及redacted Match hash核对通过。
- 89原历史对象被精确classifier接受；801次字段篡改、89次altered source全部拒绝，scope=dir也拒绝。
- 21快照各执行byte/duplicate/moved/secret追加，共84个纯前置拒绝检查通过。
- 原生有限历史扫描：0ca..ea48得到90个、eb82..WEB63a得到9个，均native1（发现项存在，非扫描器运行失败）；其中89新记录全部逐项核对原生行列/Match hash/Fingerprint通过，原已审10项另记。
- 原生有限21快照扫描使用保留45旧例外的派生基线，实际21个命中/native1，21条起止列及redacted Match hash全部匹配。Python模拟正则对Web page一行列号曾推算相差1；已用原生输出核准提案值，没有据模拟推算改写元数据或记成缺陷。
- 对21 span分别追加临时生成的合成高熵key形状值，候选原生规则全部检出对应21位置/native1；未使用真实凭据。

作者33pass及历史342pass/1fail/1deselect、后续单项1pass仍按原记录保留，本轮不重新命名其结果。上述有限原生扫描不等于完整目录/索引/全部refs通过；本轮full dir/index/allrefs **NOT_RUN**。没有PG/Docker/API/Web/Hosted/外部服务操作。

## 交接

本次只提交review文档，不改scanner、规则、业务或测试，不push/触CI。允许ROOT把本精确提案纳入后续冻结组合并按实际最终source运行完整扫描；未来源码变行/变内容/新指纹仍须重新审查，不从本结论推导自动新增例外授权。
