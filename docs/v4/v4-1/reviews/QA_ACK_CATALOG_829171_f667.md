# V41 ACK终态、owner catalog与攻击校准复审

日期：2026-11-04（台北）。代码source `829171dee96b4c1da90e3f6e6b6a985036ecf13f` / tree `f83bb50817042c87a57f43eb845bd7bd79038471`；直接文档子提交 `f667d099857f69fef0938bc077953b5e05769e25` / tree `3706aa866c11f0057a32dcbadc28529ebb1db9c4`。读取两片完整增量及实际owner observation生成/消费路径，未读新helper WIP。

结论：ACCEPT_F01_Q01_Q02_PREPARATION_FIXES / ACCEPT_FROZEN_SUBJECT_INVENTORY。前次QA_PROBES_AND_F01_ef6ab0a的三项准备缺口在本片源码层关闭；不等于SQL攻击、业务或runtime Gate通过。没有新增必须等待API旧CLI修好的前置。

## F01关闭

preview_state现在对ACK_COMMITTED、COMMITTED_READBACK任一原观察都要求末态存在恰一published job；缺行/未发布硬拒。ACK_OK不升级，ACK_UNKNOWN/UNKNOWN_READBACK仍可保留UNKNOWN；函数不修改原attempt。SQL_ROLLBACK_VERIFIED后出现job仍拒绝，原事实与末态矛盾不会被重写消除。四个承诺×缺行/未发布组合及合法UNKNOWN路径测试通过。

## Q01 owner catalog与低权分离

schema/七表/policy行数由owner_run启动的固定pg_observer读取，observer新增实际current_user=commerceops_owner及current_database核验；Business.facts保存实际stdout原件结果，并携native0/source/tree/stdout hash包装给私有probe输入。probe核本次source/tree、新DB、owner身份、0025、精确七表及policy1，app身份检查只读自身可用的当前角色/DB/session，不再SELECT受保护alembic_version。没有扩大app元数据ACL。

该catalog包装是可信host调用链的观察记录，不是新的DB权限或来源签名；hash格式验证本身不能证明原件真实性。当前代码的生产者是固定真实owner子进程，原件由host保存，后续新helper/handoff还须绑定实际source/image/安装模块与该新DB，不能手填metadata冒充已运行。纯测试只验证包装拒绝条件，不签owner SQL成功。

## Q02双段攻击对齐

攻击使用token_urlsafe(32)生成43字符legacy段与43字符伪invocation，实际改legacy csrf_digest仅记录writable信息，不单独认定漏洞。合法正向read_guard后确认全新owned库没有活parse占槽，再发格式合法伪第二MAC reserve；拒绝必须SQLSTATE23514且message_primary=SESSION_INVALID，42501、配额拒绝和其他错误不能算此探针通过。

伪reserve若成功仍记失败，随后无spawn伪stop仅作为原利用链证据，不把持正确私有lease的可信监督器误称无能力攻击者。最终ROLLBACK并新事务核锚/六表恢复；host按新FORGED_RESERVE_REJECTED状态判定并只读原key，不重发。已有job无/错lease、live child、父亡和真实reap继续单列，组合攻击成功也只覆盖PARTIAL_S04。

## f667盘点接受为冻结历史说明

独立只读核验JSON的Root7f/后端55ce matrix字节相同，matrix与T01各自hash正确；AST逐项核15个测试函数的名称/行号/参数，声明22实例且最小7/其余15分组一致。16个API合同路由与QA12个别名逐项匹配，四个未定义drilldown/product export/order export/read-context如实列出。未用AST声明数代签collect/actual/passed。

文档明确runtime_definition仍为772历史HOLD、旧DDL失败与新修片分列、NOT_RUN仅指本QA包无运行证据。其旧“等待CLI”措辞属于冻结时点；Root现已明确授权QA固定owner helper recipe路线，优先于该历史导航，不应把API903的archive/Git适配问题变成永久唯一入口要求。实际owner activation/grant/ACLverify及artifact-installed-module来源证明仍必需，但可以由新精确QA helper实现并独审，不需要fake git或owner bypass。

## 剩余HOLD与Root实际进展分账

尚待精确提交独审的是QA-owned闭集owner bootstrap/activate/grant/ACLverify recipe、真实image/runtimefileset/installed-module证明和最终组合handoff；本片没有这些实现，不通过改READY或增加占位CLI解锁。现有无条件HOLD只能随完整新方案代码审查后窄调整，不替代具体新owned对象/UTC/清理准入。

Root本轮报告4907756/R4 build proof0及ownerDDL实际0025、七表空/policy0、29新函数PUBLIC/app拒绝、资源closed/保卷，并准备最小7。本回执未重新读取原始运行包，按Root报告保留该独立进展，不以本QA旧NOT_RUN覆盖，也不自行提升为最小7或完整业务通过。后续需核真实PG各子集、S04/lease/GC/非demo、16路由和角色/来源/事务及最终清理；具体缺覆盖项按当前最终源码更新，不能要求重做已独立核收的运行。

## 独立验证

精确f667 archive运行final_facts/subjects及owner_catalog拒绝向量：10 passed，native0，1.33秒，无warning；执行代码字节相对829保持。四个固定Python -I CLI调用显式载入该archive源码，均按期望native1、stderr空、在私配/DB前拒绝。另AST/hash/路由盘点通过。无PG、Docker、实际网络HTTP、GRANT、服务、浏览器、Full扫描或远端操作。
