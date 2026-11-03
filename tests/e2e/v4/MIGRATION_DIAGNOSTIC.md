# 受限 migration 诊断入口

准备代码，不开放资源窗口。旧失败窗不可复用；Root在全新owned db-init容器中登记精确
source/image、对象、新凭据、UTC截止/cleanup reserve并通过外层supervisor后才执行。
该命令本身不创建容器、卷、数据库，不带重试或窗口延长；不是常驻诊断服务。

在仓库根目录、使用原db-init新owned环境（原`COMMERCEOPS_DB_*`配置与新password file）执行：

```sh
python -m tests.e2e.v4.migration_diagnostic \
  --public-migration-sha256 c46117966ad4129ac8a0cd6102a14f91d7039473fd120c2bcd8ea53ebbdc7f09
```

此SHA256来自只读git对象
`ea48a139:backend/migrations/versions/0024_v4_demo_foundation.py`。
若后续审查改变0024源码，Root应从新的已审精确提交计算指纹；不得绕过校验。
诊断模块须先普通合入实际运行源码/镜像，QA当前分支自身没有0024，不可直接拿它跑迁移。
`--help`不读配置、不连接数据库。CLI不接受DSN/password/SQL参数，也不读取旧私有配置。

执行路径固定为原`commerceops.entrypoints.database.migrate(DatabaseSettings())`，
使用原迁移/连接/事务逻辑，不调用grant-runtime、setup-checkpointer或任何测试；没有auth旁路。
PUBLIC_SOURCE_CHECK先核源码指纹、非symlink、文件大小，再建立静态公开SQL allowlist。
原migration/import输出（Python stdout/stderr与原生fd1/2）丢弃到devnull，不存raw日志。
仅最终安全JSON在恢复输出后打印。

失败退出1，输出固定status/stage/tests和最多8个去重异常链节点；只含受控异常类型、规范
SQLSTATE、有效statement_position、该公开文件最多4个traceback行号、可选公开SQL片段。
不打印exception message/str/repr、traceback全文、diag.context/internal_query/detail、
DSN、params、配置或凭据。片段最多160字符，只有异常statement与已校验公开源码的静态
SQL literal**完全相等**时允许，其他情况null；不会将运行SQL做脱敏替换后输出。
仅打印SQL片段并不能证明错误根因；SQLAlchemy编译后statement不再精确相等时也留null。
成功退出0，只输出MIGRATED/ORIGINAL_MIGRATE/tests=NOT_RUN，不签任何测试Gate。

纯验证命令：

```sh
.venv/bin/python -m pytest -q tests/e2e/v4/test_migration_diagnostic.py
```

7项通过/0.23s/native0；包含原生fd及Python流输出、消息/SQL参数/diag秘密哨兵不泄漏、
只有原文静态SQL可输出、异常链元数据、错误指纹不调用migrate、成功不签tests、固定原入口。
全部是替身/纯验证，未调用实际迁移或连接。初轮6pass/1fail/native1：仅fd重定向不能覆盖
被替换的Python流，修正为同时redirect_stdout/stderr后通过。初轮lint哨兵命名及类型测试
lambda问题也已修正；不是数据库错误定位结果。

Root转交的旧窗build/healthy成功、migration exit1/0tests、cleanup0/无存活资源仅作为接单
背景；原SQL根因仍UNKNOWN。本代码准备未启动Docker/PG/API/Web，实际migration/PG诊断、
Full与Hosted均NOT_RUN；actual token/cost UNKNOWN。
