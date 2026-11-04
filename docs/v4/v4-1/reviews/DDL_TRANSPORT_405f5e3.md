# V41 SQLAlchemy JSON bind字面量修复复审

日期：2026-11-04（台北）。source `405f5e336bb58f84563e441f350e9b2a2968a0d2`，tree `d82143a85ea6ff66956f59201abd45759a675447`，parent `9f10c8c5ad1a44fd487159b9f19955cab24af9b2`。精确两文件：0025单字面量空格及新完整upgrade编译回归。

结论：ACCEPT_MINIMAL_TRANSPORT_FIX_CODE_ONLY。独立逐字节核验生产迁移仅将reaped JSON冒号后加一空格；JSON解码对象相同，CHECK的业务谓词/表/列/权限/trigger/lease保护不变。保留op.execute原调用路径及SQLAlchemy的百分号处理，没有改成绕过编译的原始DBAPI调用。

回归通过实际MigrationContext/Operations.context调用migration.upgrade，用postgresql+psycopg方言create_mock_engine只替代最终DBAPI传输，编译每条op.execute语句；要求超过20条且所有compiled.params均为空。五SQL常量也逐一TextClause无bind。旧无空格JSON仍明确断言被识别出true bind，修后同字面量无bind，未抹去失败反例。

独立精确git archive执行该回归：1 passed，native0，0.67秒，无warning；不使用DBAPI、没有连接PG。可供Root为精确新source构建新镜像，并在新owned资源/UTC内接续DDL/ACL编译及此前已准入的最小PG7。此代码接受不是PG语法、迁移COMMIT、实际ACL或七节点通过；不自动准入完整22/Full、UI或未审CLI。

Root已报告旧772 ownerDDL R2的missing bind true、SQLSTATE为空，保留为实际失败；本轮编译结果仅支持最小修复解释，不回填旧运行成功。新PG仍须新回执，失败不自动重试。无Docker、PG、GRANT、服务、浏览器、Full扫描或远端操作。
