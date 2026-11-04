# V41-1a 导入设计P2关闭复审

日期：2026-11-04（台北）。精确source `bf932cb7f0a4d67a6723dad23e656a73d11a33d1`，审查CONTRACTS.md三行增量，继承84db1ba完整七节审查。

结论：ACCEPT_DESIGN_AMENDMENT，P2-C01/P2-C02在合同设计层面关闭。允许继续精确SQL/解析实现候选；不签代码或运行安全通过。

C01：明确父进程/锁连接失联或身份不明不能因advisory锁自动释放而恢复容量；允许最小持久fail-closed占用，实际终止/回收证明之前拒新准入。新增父进程/连接失联、超时、后续准入实测要求，解决原设计忽略存活子进程的缺口，不要求通用回收框架。SQL中占用先落盘再spawn、失败后保持占用及受信回收授权仍需专项核实，TTL/reset/GC不能绕过活解析容量边界。

C02：preview保存创建data_revision及parser/schema version、文件/映射/normalized摘要；新确认要求preview/request/current三方匹配，数据变更重新预览，不能只换请求revision。既有当前权限先核、原keyreceipt优先、新效果才CAS的规则保持，不因该补充破坏已提交原请求恢复。

此关闭只消除合同缺项，监督模拟修复或DTO存在均不证明真实PG/advisory/parser已符合。原84db两P2及V40失败记录保留原时点。本次只读提交差异，无服务或测试运行。
