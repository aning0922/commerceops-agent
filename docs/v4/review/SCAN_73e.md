# V4 discovery 残余精确绑定 73e0a58 窄审

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_PREPARED_SCAN_METADATA_DELTA，0 P1 / 0 P2。** 只签本次有限元数据/绑定增量；不替代最终全仓 dir/index/allrefs Gate，不重审此前分类机制或签发 PG/HTTP/Browser/Full 结果。

candidate `73e0a588eea2ed37c9418dc9003037e3c5340ccc` / tree `4bd922ac81eb4151f9366856749625d99c94abb2`，parent `dd8af584f8e80dc2bbd735193940bc4391dabaa0`。diff 恰为原七文件：.gitleaks.toml、gitleaks_rules.json、scan_secrets.py、vendor_gitleaks_rules.py、test_quality_gates.py、test_v4_scan_compat.py、SCAN_COMPAT.md。未读 WIP，未改作者文件。

## 授权范围与固定源核对

独立读取 ROOT 原 discovery `RESIDUAL_METADATA.json`，SHA256 实核 `e2ac056a3341b8015c5c577c89a33379f3d80f002ff425e0b62f4239c631d326`。9 个新增作者记录逐字段匹配该清单的 source/rule/path/行列/span hash/Match hash；9 个目录记录逐项匹配原 path、两 hash 与列边界。最终 owned_driver 固定位置由 557 更新到 735，review_fixes 类型行由 112 更新到 105，按已审 1684 精确源码绑定，没有模糊查找或未来自动移行。

逐项阅读九个作者原文，内容为合成 creation key、pytest 类型声明、request key/tenant 比较、固定测试 UUID、auth_version 标识符比较、请求键与 fixture 输入、静态 SEE_ACTUAL_COMMAND_RECORDS 标签。不是实际凭据。新增9目录+9作者只豁免这些精确记录，未为新 guard 测试、legacy wrapper 或未知未来命中增加通用例外。

13 个原 manifest anchor proposal 均精确出现在新增锚清单；额外两个锚只来自已接受的 `1684e0455978b46ddad607e09d85a1af5657ab1a`，分别为 owned_driver blob `9f168bab0b31f627843d05d65e391b99bc4ca438` 和 test_owned_review_fixes blob `0b51b2c3775c0052a9f009f857a1cf317d2aaebb`。独立 git rev-parse 核实全部15个新增 source:path 的完整 blob 与常量一致。旧12锚字典完整保留，总27；a990 候选锚未进入最终清单。

新增 copy-only 两条只绑定 owned_driver 原 557/540 的固定行列、完整 span/Match hash；没有加入目录豁免或作者精确历史表。approved_v4_merge_copy 仅把这两条加到原候选行集合并显式报告 binding_kind。原 git-only、真实至少双父、merge 全文件 blob 等于固定 anchor source 全文件 blob、精确 rule/path/行列/Match、anchor 源完整行 hash 的验证保持，未退化为任意祖先或行内容相似匹配。单父8196/1684即使对应同路径仍不能按copy接受。

## 原规则与历史不变

独立比较 parent 的222个规则，除逐条 allowlists 外所有字段完整相同；无规则删除或检测 regex/entropy/path 放宽。目录 allowlist 84→93；原84项仅 sessions 三项固定 source/位置151/170/197→155/174/201，完整 hash 不变。测试明确核除此之外旧项相同。

旧20+13+10+94=137条精确历史逐字典保留，新增9后146（preflight 94→103）。历史派生配置仍完整等于旧基线，移除48个目录专用条目后保留45个原生历史例外。原12个锚保留，新增两个copy-only绑定由provenance精确比对，不扩为作者豁免。

## 独立验证与证据边界

在精确 git archive 临时快照中运行有限选择：9项新增目录 literal 边界、元数据保留、2项copy-only原生定点与篡改/单父拒绝、精确快照及历史派生配置核对，共 **13 PASS / 215 deselected / 5.53s / native0**。使用独立临时 Git 元数据与只读共享对象；原仓库 refs/index 未修改。仅两个明确 commit 的定点历史原生扫描及合成临时目录扫描，没有 allrefs 扫描。

额外独立核验9 snapshot+9 author+2 copy-only共20项完整源 span hash；匹配 manifest 的九项 snapshot hash/列边界及九项 author 全字段；核15个新增真实 blob；核222规则/93目录/45历史原生例外与旧137记录保留。复用原 `native-git.json`，按原 manifest 的210个残余 fingerprint 精确选择并调用候选分类器，结果 **210/210 = 9 exact + 201 copy，UNKNOWN 0**；没有重新生成全仓报告。临时快照、测试报告与 Git 元数据已清理。

原 discovery exit1、dir/index各9原生命中及3个位置guard、git987=777已分类+210残余、refs_stable=false和此前invocation失败均保留。本次分类回放不把原扫描改写为绿。最终整合源码的完整工程检查仍由 ROOT 另行执行；F1的功能运行与后续元数据/文档源码必须分记，只能依据实际字节比较说明差异，不能把F1运行证据转签未来HEAD。ROOT本次消息中的pilotE/TTL/Full状态不属于本窄审独立运行证据。
