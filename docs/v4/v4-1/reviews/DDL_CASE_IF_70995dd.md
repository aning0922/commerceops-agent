# V41 parser配额IF括号最小修复独审

日期：2026-11-04（台北）。patch source `70995ddf1be0fda16d643a5ecabd106b9bd20f33`，tree `3bc16b5d5231863ceb32c2cbfadf1ec8cadec198`，parent `9033b53888815769523a73ba294cef4f82f2b523`。

结论：ACCEPT_EXACT_TWO_LINE_DDL_PATCH。接受范围仅该commit在0025的两处CASE括号，不包含903 owner CLI、e8 native测试祖先或任何其他文件。Root可将此单commit窄cherry-pick到已审405业务代码组合，再冻结实际新Root SHA/tree；本回执不预填该未来SHA。

独立逐字节核验：709父提交的0025与已审405f5e336bb58f84563e441f350e9b2a2968a0d2完全相同；两处旧字符串恰好出现两次，全部替换为括号版后与709文件完全相等。没有附带DDL/权限/业务变更。

reserve与publish中的配额算式均仍为active减去“parent为空时0，否则1”再比较>=3。括号只将完整SQL CASE表达式嵌套，避免CASE内部THEN被PL/pgSQL外层IF表达式读取当作顶层THEN分隔；active/parent/阈值、LIMIT_EXCEEDED与其余分支不变。此是与Root实际R3的PARSE_FUNCTIONS LINE110/SQLSTATE42601相符的最小解析修复，不宣称本轮已由PostgreSQL parser执行证明。

独立精确archive执行现有完整Alembic/SQLAlchemy迁移传输编译回归：1 passed，native0，0.94秒，无warning；所有升级语句params为空的既有回归保持。该检查无DBAPI，不验证PG函数语法、迁移COMMIT或运行效果。

可供Root接续新source/image、DDL-only新案，并在实际迁移/ACL核收后按原条件进入已准入最小PG7；不用等待CLI完整适配，也不能借此批准CLI、完整PG23/Full或公开API。旧R3失败、空/实际SQLSTATE分层、全事务rollback及closed按Root原回执保留，不回填。未运行PG、Docker、GRANT、服务、浏览器或远端操作。
