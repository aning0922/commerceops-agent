# K2 权限与不可变负例的窄测试修复候选

2026-11-03，普通合入 Root `3a184e9a74c1db524d58228ed90b7ea20388a722` 后只读诊断。
本片只改目标测试与本文；生产迁移、ACL、向量 SQL、镜像及 CI 均不改。新 PG 验证 NOT_RUN。

## 证据与分类

Root 回交 existing 全542集合在 K2 模块30项执行到29pass/1fail后停止，合计
387actual/386pass/1fail，后155项 NOT_RUN；源3a184e9，project p123-1024202881f4。
Root 已核 07:39:48.766015Z cleanup0、独立资源0。本 owner 不读取或复活该资源。

精确 3a184e9 的目标测试第278行为 runtime 的三条权限 SQL，第285行属于后一个 owner
UPDATE/DELETE/TRUNCATE 循环。因而 trace285 不支持把0A000归到 extension UPDATE。
PG17.11 官方 `ExecAlterExtensionStmt` 的扩展 owner 检查先于同版本 no-op 判断，不能以
“同版本先检查”解释该次失败，参见[固定17.11源码](https://github.com/postgres/postgres/blob/REL_17_11/src/backend/commands/extension.c)。

0023 的 p6_copy_candidates 对 p6_knowledge_registries 新增 FK。目标测试的单表
TRUNCATE 默认 RESTRICT；[PG17 TRUNCATE 合同](https://www.postgresql.org/docs/17/sql-truncate.html)
要求被引用的表连同引用表一起进入命令范围。17.11
[ExecuteTruncateGuts](https://github.com/postgres/postgres/blob/REL_17_11/src/backend/commands/tablecmds.c)
先调用 heap_truncate_check_FKs，后调用 ExecBSTruncateTriggers；
[heap_truncate_check_FKs](https://github.com/postgres/postgres/blob/REL_17_11/src/backend/catalog/heap.c)
对该 RESTRICT 情形报0A000。因此这个拒绝不能冒充触发器23514或权限42501。
这是精确源码与官方执行顺序的静态定位；原实际错误原文未取回，新实际 SQL 仍待 Root。

## 最小修正与保持的 Gate

目标 owner 命令改为 `TRUNCATE business.p6_knowledge_registries CASCADE`，将引用依赖纳入
命令范围，使既有 BEFORE TRUNCATE guard 真正受测。该 guard 在0020中复用0002的
`business.reject_inventory_mutation()`；严格要求 CheckViolation/23514，且固定诊断消息必须是
`inventory evidence is immutable`。不接受0A000或宽泛异常替代。原 UPDATE body 与 DELETE
chunks 的拒绝断言也保持，并核固定不可变消息；测试事务遇拒绝后回滚。

runtime 的 CREATE SCHEMA、CREATE TABLE、同版本 ALTER EXTENSION 三命令与
InsufficientPrivilege 预期原样保留。新增前后 catalog 核验：vector始终0.8.7、schema始终
knowledge_ext、runtime不是扩展owner。无需换版本、改安装路径、移交owner或补权限。

Ruff/format/mypy通过；原两个纯契约模块共88pass；PG模块30collected，节点不增减。
上述离线检查不证明新 CASCADE 命令已到达触发器，实际30项及原未跑155项仍由 Root
后续新 GO 窗口验证；不把原386pass转签给新源或把155 NOT_RUN记为通过。
