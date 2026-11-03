# 0024 SQL CASE 括号机械增量独立审查

2026-11-03，Asia/Taipei。结论：**ACCEPT_SCOPED_SQL_SYNTAX_DELTA，0 P1 / 0 P2**。仅接受两处 IF 条件内 CASE 表达式的括号修正，可供 ROOT 安排新 owned schema 六节点组件验证；不证明迁移已成功运行，也不批准 API 运行或整体业务 Gate。

## 精确对象

- source：`12081e4f7dd326611b2be001aca4ed9a22acb9d1`。
- tree：`8c08f6897b61fb83d56f5ddabef9c7e3df73e716`。
- parent：`31d11cc76c13a7a56afc5fec541b1657dc747cab`。
- 唯一变更文件：`backend/migrations/versions/0024_v4_demo_foundation.py`。
- 候选文件 SHA256：`5b0c8bff8047d18c830976e966241fbf4fe5008a43f4cad6142334efb4b042fa`。

从精确 Git 对象独立核对，完整 diff 仅两个 hunk、三行替换，合计增加三对括号。两文件字节仅去掉括号后完全相同；没有其它字符、字段、常量、谓词、DDL、ACL 或调用变化。没有读取作者 WIP、执行迁移模块或启动 PG/服务/测试/扫描。

## 两处判断

1. 请求路径守卫：`v4_demo_request_valid` 把路径前缀与 CASE 结果的拼接整体括起，并把内层 CASE 表达式括起。operation 为 session_create 时仍映射 sessions，否则仍取 operation。`IS DISTINCT FROM`、POST 方法、完整对象/字段集合检查、失败返回 false 与后续 body/key 验证全部保留；没有增加允许路径或跳过检查。
2. 回执事件数守卫：把 count 比较右侧的 CASE 括起。session_create 仍要求恰好两个事件，其它操作仍恰好一个；比较符仍为不等，失配仍进入同一 binding invalid 异常。前后的 owner、epoch/generation、TTL、完整请求、事件存在性/绑定与 seed 事件要求未改。

这是给表达式明确边界的机械语法修正，不改变上述守卫的预期含义。ROOT 报告过实际新 PG 的 SQLSTATE 42601 / position 565 指向请求路径 IF CASE；本审查未独立读取该 PG 诊断原件，不将转交事实写作本会话实测。第二处同类 CASE 比较一起显式括起，仍须由后续实际 schema 组件运行确认解析及约束行为。

## 放行边界

只对本精确 source 的机械 delta 给代码审接受，不重审父提交整体 DDL/ACL 或身份设计。后续对象、UTC、清理与六节点执行由 ROOT 统一安排。本报告不签 PG PASS、迁移/完整 schema 验收，也不替代 Astra 对 API 候选 d578 的独审，更不因本报告授权运行 API。旧扫描范围、原件和历史失败均保留；actual token/cost UNKNOWN。
