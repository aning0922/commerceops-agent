# R2 有限扫描残余 e096 窄审

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_PREPARED_R2_SCAN_METADATA_DELTA，0 P1 / 0 P2。** candidate `e096a5996c83b0135eb99a988ab4c3295ad1b196` / tree `bda8ce7bb990ed829c759e9cdb58fa0d46c95979`，parent `f341a89a632d65e896323e840e0fc55f9ca77b91`。仅原七扫描owner文件；本审查不重写命中原文、不扫描全仓、不启动资源。

新增两条目录/作者记录限于 `docs/v4/acceptance/v4-0/TTL_F1.json:10:7–58` 和 `docs/v4/review/SCAN_f341.md:7:162–193`。分别是合成operation标识及已核公开类型引用；不授予身份，不包含实际私钥。独立核完整span hash为 `db49de282d54de455455c517d10e38ace8d1de2125cffeed47b8d1b902b169f3` / `53393d547dc8e044a97e4036e69d20147b037c6d0b5f3a7fcd8ceb1d086a852a`，精确source与完整blob等于常量；两单父author只走exact history。

http_probe仅将原四目录来源固定为已审1c152，位置147/259/364/394→154/266/371/401；原rule/path/列/完整span与Match hash均不变。四旧记录逐字典加copy_only标记后原样保留；不是删除旧位置或给予1c新作者豁免。新增三个source:path锚均独立核Git blob一致：两个文档及http_probe新完整blob。旧28锚、147精确历史、原两copy-only完整保留，现在96目录/149历史/31锚/6copy-only。

独立AST核scan_secrets除validate_rules/history_config数量断言外全部函数与parent相同。222规则逐项比较，除generic规则新增两个精确allowlist外完全相同；原四探针TOML表达式没有变化。历史派生配置仍等于原基线并保留45原生例外。原真实双父、完整blob、精确rule/path/行列/Match/源span准入均未拓宽。

精确快照独立有限测试 **13 PASS / 229 deselected / 5.67s / native0**，覆盖六当前span的byte/moved/duplicate/secret反例、两doc author及R2 merge字段篡改拒绝、旧绑定保留和完整历史派生。额外独立核六当前span、四旧copy span及三新增blob。读取原full-check-c6abe05/output.log精确选择20条git blocking，对其有限commit^!原生重捕获，逐fingerprint核 **20/20 = 2 exact author + 18 merge copy**；没有allrefs/fullscan或重新运行scripts.check。临时Git元数据只读借用对象，临时文件已清理。

原R2 c6完整scripts.check native1/110.962s、dir2/index2、git1373中20blocking及每scope固定位置guard残余保留；不因有限分类成功改写原Gate。此元数据准备阻断已闭合，最终完整工程Gate待ROOT统一运行。本提交不吸纳后续截图变更，也不转签业务/Full/TTL或未来HEAD。
