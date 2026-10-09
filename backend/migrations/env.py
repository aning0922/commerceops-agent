"""只支持真实 PG online migration；连接由启动层注入。"""

from alembic import context

connection = context.config.attributes["connection"]
# 与 revision 同一事务创建 schema/version 表；失败不留下半次升级。
connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS business")
context.configure(connection=connection, version_table_schema="business")
with context.begin_transaction():
    context.run_migrations()
