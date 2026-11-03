# V4 current-head 十表预期 8ef545 窄审

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_PREPARED_CURRENT_HEAD_TABLE_EXPECTATIONS，0 P1 / 0 P2。** 仅签测试预期兼容增量；目标PG和完整existing/phase3实际运行尚待ROOT。

candidate `8ef54543aa0d32ba2caff4701650fcac1f03c208` / tree `0909c37a97ef2001cff4ddc3835fd5f58215b275`，parent `2332f738885ebd0608cbe1ce670ae434116588fb`。delta恰为 `tests/test_p4_history_pg.py` 20行新增、0行删除；没有迁移/业务/权限/helper/CI修改。

独立从精确0024 migration的CREATE TABLE定义提取十张表，逐项核两份新增名单同序、无遗漏/重复：v4_demo_fixture_versions、tenants、shops、personas、bootstraps、sessions、receipts、events、overlays、rate_attempts（后九项同v4_demo_前缀）。第一份加到current与0017 after之间的完整差集相等断言；第二份加到新增表全部为空断言。没有改成subset或忽略V4表，额外未知表及非空新表仍会失败。0024 upgrade创建表/函数/trigger并撤PUBLIC权限，函数内INSERT语句不是migration时执行的fixture初始化，因而新表空预期与此处仅migrate/grant的流程一致。

独立移除这20个新增字符串行后，整个文件与parent逐字节相同。原634–713历史段（0016→0017）前后SHA256均为 `f0972f16e6512c335961af86a7aef86471bef08beec46add43b37315bf74df6b`。原三表差集、旧rows/payload/hash/provider UUID、unknown/attempt1、current权限校验、head之后旧内容全等及低权读取断言全部保留。当前head revision断言已是0024，本次未改。

独立核parent测试blob `c1adda65b5d68c19697ca204e805b14f275be7b8` 与F1相同；候选0024 migration blob `018748c90bc4145e3147454052296ea4a8119071` 也与F1相同。因此这两名单针对真实F1 head定义，而非假定未来迁移内容。

精确候选临时快照执行唯一目标 `test_0016_upgrade_preserves_original_rows_payload_and_unknown_attempt` 的collect-only：**1 test collected / 3.02s / native0**；额外将psycopg.connect设为拒绝以防意外连接，未运行fixture/PG。两个既有依赖DeprecationWarning保留，不当作业务失败。临时目录清理，未运行其他迁移审计、服务、全量测试或扫描。

ROOT报告的F1 Full existing 555pass/1fail/12notrun、G1 NOT_RUN、G2六项记录与原具体assertline NOT_CAPTURED保持。此源码检查确定旧head集合漏掉0024十表并修正预期，但没有补造旧运行具体trace，也不能将collect成功等同原失败已实际修复。最终合批后由ROOT先目标PG、再完整双线及配对，分别绑定实际新source记录。

F1自然TTL独立核收已另以 `780148645136c5819dcfc713bc0ad138a5471642:docs/v4/review/F1_NATURAL_TTL_EVIDENCE.md` 提交；其成功及初/before/after UNKNOWN原件保留，不用于替代本测试或Full Gate。
