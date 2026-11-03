# V4 legacy 单条类型 span f341 窄审

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_PREPARED_SINGLE_LEGACY_SCAN_BINDING，0 P1 / 0 P2。** 仅签本条元数据增量，不签最终完整 scripts.check。

candidate `f341a89a632d65e896323e840e0fc55f9ca77b91` / tree `82e9de5944273d9906a9269507e5210d98a0cc14`，parent 恰为已审 `73e0a588eea2ed37c9418dc9003037e3c5340ccc`。只读精确七文件delta，没有重审旧分类机制、读取WIP或启动服务。

唯一新增位置为 `4e267522c353074d583a29c89e9022d4f8d93f33:tests/e2e/v4/test_legacy_subnet.py` 第57行、22–52列，完整行为公开 `tmp_path: Path, monkeypatch: pytest.MonkeyPatch` 参数声明。独立git对象读取核完整行SHA256 `41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada`，完整blob `ac3098476addaa63aed5311afd49ff102360c737`；原生定点扫描核Match hash与登记 `617581412b474fb36e60639d980eddc44cbfa5a220bf98433eac96cd8e59f7e4` 一致。没有秘密，也没有按类型字符串泛化到其它文件/位置。

只追加1个目录精确例外、1个原作者精确历史和1个wholeblob锚。独立逐字典比较：旧93目录、146历史、27锚、两copy-only绑定均完整保留；现在为94目录、147历史、28锚。222规则逐项比较，除generic-api-key追加的一个精确allowlist外全部字段不变；历史派生配置仍等于原基线并保留45个原生历史例外。scan_secrets所有函数AST除validate_rules/history_config的数量断言外完全相同，新增项复用原严格分类器，没有新增模糊规则或作者/单父copy豁免。

精确快照独立有限验证：**5 PASS / 227 deselected / 2.40s / native0**。含本条byte/moved/duplicate/secret反例、真实4e author与F2 merge各自commit^!原生定点分类和字段/Match/fingerprint篡改拒绝、旧元数据前缀保持、精确快照及历史派生配置检查。原生author仅按exact history接受；真实merge仅按原双父/完整blob/精确span机制接受。临时Git元数据仅借用只读对象，测试目录均已清理；没有全repo/allrefs扫描或scripts.check重跑。

ROOT报告的F2完整scripts.check native1及原7blocking事实保留，不由本次5项有限测试改写为绿。此项代码/元数据阻断关闭，后续最终合批完整工程Gate仍由ROOT按实际结果记录；不转签F1/F2业务、TTL、Full、Hosted或发布。
