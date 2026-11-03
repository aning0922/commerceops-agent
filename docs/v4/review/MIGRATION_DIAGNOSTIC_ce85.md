# V4 migration diagnostic ce85 独立审查

日期：2026-11-03（Asia/Taipei）。**结论：P2_REQUIRED_CHANGES，0 P1 / 2 P2；暂不签诊断入口准备接受。** 两项均为本地纯合成输出保护反例，不是实际凭据泄漏或数据库根因结论。

## 精确范围与方法

candidate `ce85c9e968531edde48d6b343197b686b2a367c7` / tree `0b48dd5aeeab16c2243ab481783bcad67e65679d`，仅新增`tests/e2e/v4/migration_diagnostic.py`、`test_migration_diagnostic.py`、`MIGRATION_DIAGNOSTIC.md`。读取精确Git对象，不读QA未提交WIP。另读取同候选原database入口、DatabaseSettings、Dockerfile及现有supervisor核边界。

独立纯检查：标准库AST解析模块与测试；核公开迁移原始bytes SHA256；把精确诊断模块源码compile/exec到隔离Python子进程，替换public_sql为无资源固定allowlist、operation为合成函数，capture_output只报告exit/哨兵和traceback是否出现。未导入或调用实际DatabaseSettings/migrate，未读DB环境/密码，未连接PG、启动Docker/API/Web。作者7项pytest未在本轮复跑，其7pass和初轮6pass/1fail仍为作者事实。

## MD-01 [P2] 非Exception终止及诊断器自身失败可越过安全输出边界

位置：`migration_diagnostic.py:166–178` run，尤其175和176–177；main:193–195没有最终安全失败边界。

run只捕获Exception，suppress_raw_output的finally先恢复原输出。若operation抛SystemExit(message)，外层解释器随后可原样输出message；若在有原始错误上下文时中断为KeyboardInterrupt，解释器可输出完整异常链。普通Exception路径也存在同类缺口：diagnostic或第二次输出重定向失败时，其异常没有安全fallback，原migration错误成为__context__，恢复stderr后被打印。

纯子进程结果（仅使用合成REVIEW_SENTINEL）：

| 替身operation/故障 | native exit | 哨兵输出 | traceback输出 |
| --- | --- | --- | --- |
| os.write + RuntimeError哨兵，正常diagnostic | 1 | false | false |
| SystemExit哨兵 | 1 | true | false |
| RuntimeError哨兵的except内raise KeyboardInterrupt | -2 | true | true |
| RuntimeError哨兵，diagnostic替换为抛OSError | 1 | true | true |

后两例分别为中断和诊断器故障注入，不声称本候选实际迁移已出现这些异常。旧supervisor的TERM/KILL不会自行变成KeyboardInterrupt，不能将此结果归因于旧窗截止。但“失败native1且无raw trace”的诊断保证目前确实只覆盖普通Exception且诊断器成功的路径；资源/路径等错误仍可能令诊断器本身失败。

最小修正：在该专用CLI边界安全处理可捕获的BaseException，并对诊断器/重定向恢复错误设置无原异常文本的固定失败fallback；输出恢复后不得再抛带原__context__的异常。保持外层TERM/KILL截止与清理能力，不捕捉/绕过不可捕获SIGKILL，不将中断记MIGRATED。补独立子进程的SystemExit、带上下文中断和诊断器故障用例，断言无原消息/trace且退出符合明确失败合同。仅加except Exception包住operation不足。

## MD-02 [P2] fd重定向未覆盖原生stdio缓冲的延迟输出

位置：`migration_diagnostic.py:145–163` suppress_raw_output，尤其159–162。

当前只flush Python sys.stdout/stderr，原生C stdio的stdout缓冲与它们独立。在fd1指向devnull期间调用原生printf但不flush，内容可留在libc缓冲；退出context恢复fd1后，进程正常退出flush该缓冲时会写入外层日志。因此os.write用例通过不能证明文档宣称的原生输出全部被抑制。

独立纯子进程通过`ctypes.CDLL(None).printf(b"REVIEW_SENTINEL")`作为operation（无换行、无DB/网络），run返回MIGRATED/native0，但子进程捕获stdout仍含哨兵，未出现traceback。本事实来自当前本机环境，不冒充Linux pg-test镜像复现，也不声称实际psycopg已经输出敏感内容。

最小修正：保证原生缓冲在输出仍隔离时处理，或让执行迁移的进程stdout/stderr始终保持隔离、仅经独立受控通道发送结构化结果。不得只在恢复后的Python流上flush或用字符串替换来补救。保持方案局部；若使用libc flush须验证目标Linux环境行为及失败路径，不能把本机符号假定为跨平台保证。补原生带缓冲输出子进程测试，观察进程完整退出后的输出而非只检查context内部。

## 已核边界：公开源码信任与异常字段

独立核`ea48a139:backend/migrations/versions/0024_v4_demo_foundation.py` raw SHA256为`c46117966ad4129ac8a0cd6102a14f91d7039473fd120c2bcd8ea53ebbdc7f09`，与文档一致。public_sql要求64位小写hash、末级非symlink、读得bytes长度不超过1MB且hash一致，AST只取以指定SQL关键字开头的字符串常量；不执行0024以构造allowlist。异常statement必须与允许常量完整相等才输出最多160字符；动态拼接/编译变形SQL缺少精确匹配时null。它可包含f-string的静态片段，但这些仍来自同一公开hash字节，不允许运行参数拼接为输出。

CLI参数里的hash本身不是授权：ROOT仍须从已审精确source提供hash，并绑定不可变镜像/源码、工作目录与同owner新DB环境。此helper没有验证整个镜像/其余迁移、父目录symlink、执行期间源码不变，也没有独立截止；这些已由本次ROOT外层合同承担，不把单文件hash说成整条迁移来源证明。文件大小限制在read_bytes之后，属于可信冻结源码的解析限制，不是对任意巨型文件的内存保护。

diagnostic正常路径不读取str/repr/message/params、diag.detail/context/internal_query或配置；类名固定白名单，否则OTHER，SQLSTATE仅5位大写字母/数字，position限1–9999999（bool拒绝），只输出匹配公开路径的最多4个trace行号。orig/cause/context按对象id去重、最多输出8节点，循环链不会无限输出。不访问局部变量；未知类型保留OTHER而不推断数据库根因。以上正常路径限制不抵消MD-01的外逸路径。

## 已核副作用与执行载体

original_migrate只在受抑制作用域内import并调用原`migrate(DatabaseSettings())`。原migrate创建migration engine，在engine.begin事务内执行Alembic upgrade(head)，finally dispose；不调用grant-runtime/setup-checkpointer/tests，不增加重试或对象发现。**实际运行会执行原迁移及DB写入，不是只读诊断**；本次审查没有运行它。原DatabaseSettings读取COMMERCEOPS_DB_*及指定password file，无新增.env读取。新owned对象/凭据、UTC与cleanup必须由ROOT外层绑定，不能沿用旧失败窗。

已核Dockerfile：runtime只COPY backend，test target额外COPY tests/scripts。因此文档“db-init容器”措辞不能作为runtime目标可执行模块的证据；按ROOT明确安排使用test target(pg-test)携带同owner DB配置执行，且必须先将诊断模块与0024一起纳入实际冻结镜像。无需为此修改旧Dockerfile。QA当前分支缺0024的限制保留，不能直接拿该分支跑迁移。

## 交接

仅提交本审查文档，未改实现/测试/Dockerfile、未启动资源、未push/触CI。请QA局部修复两项后交精确普通commit复审。旧窗migration exit1/0tests、具体SQL根因UNKNOWN及cleanup事实不改；当前纯复现不能替代实际迁移/PG验证或ROOT窗口授权。


## 0f34增量复审：MD-01/02关闭

candidate `0f34f31c4a02469ce3f6caaec99a9a0dbafedd4d` / tree `5e003a5aaaf57ecf8b16db7c5ab73f9ed9c6e6b1`（parent166fb）。**结论：ACCEPT_PREPARED_DIAGNOSTIC，增量0 P1 / 0 P2。** 保留ce85首审反例，本结论只接受专用单进程CLI的准备代码，不签实际迁移、Linux镜像或资源窗口。

MD-01 CLOSED：run捕获BaseException，属性读取也安全处理可捕获中断；diagnostic提取失败返回固定FAILED/DIAGNOSTIC_FAILED/NOT_RUN/空chain。render在抑制域内序列化，序列化失败使用无需再次序列化的固定JSON。main参数解析也抑制错误原文（独立--help正常），最终仅os.write安全ASCII并SystemExit(code) from None。未捕捉SIGKILL、未改变外层清理；中断不记成功。

MD-02 CLOSED：进入抑制前保存外层Python/libc输出；操作结束时在devnull fd仍生效的域内flush Python sink及libc.fflush(NULL)，然后才恢复外层fd。若原生flush或恢复失败，abort_isolated向保存的原stdout fd写固定安全失败JSON并os._exit(1)，避免解释器退出再次flush敏感缓冲；即便fallback输出本身失败仍强制非0退出。没有新增子服务、重试、授权或迁移旁路。此全局fd策略明确仅供专用单进程CLI，不能当多线程宿主通用日志隔离。

独立复验从精确Git模块源码compile/exec装入隔离子进程，执行精确新增子进程测试正文（只将模块import替换为该精确内存模块）；public_sql/operation保持合成替身，未import实际backend。完整退出结果：SystemExit、带原异常上下文KeyboardInterrupt、diagnostic故障、serialization故障、native flush故障、fd恢复故障均native1/FAILED；无换行C printf正例native0/MIGRATED。7种全部stdout无哨兵、无traceback，stderr为空，可解析JSON且tests=NOT_RUN。这里MIGRATED只是合成operation成功标签，绝非实际迁移成功。

公开hash/CLI入口/固定原migrate调用未放宽；文档已明确runtime/db-init不含tests，ROOT应使用test/pg-test载体及同窗口owner环境。作者21pure/0.51s和首20pass/1fail的fallback丢失记录保留，不用本轮7子进程复验覆盖。目标Linux pg-test的libc符号及实际退出仍须ROOT在冻结镜像核验，本机结果不代签。实际SQL根因仍UNKNOWN；PG、Docker、API/Web、Hosted本轮0操作。资源准入仍由ROOT另给对象/新UTC与cleanup，旧失败窗不可复用。
