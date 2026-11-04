# 首个 lifecycle pilot 的 init-fixture 失败与发布名核对

只读调查，2026-11-04 Asia/Taipei。唯一允许读取的case为新live树：
`/Users/aipuli/.codex/worktrees/commerceops-v4-live/commerceops-agent/.audit/v4qa_lifecycle_20261104a`。
源 `27f26e11aae2c927a31ae1b051563d25a06c0b25`，tree
`0c8b0a5b8ac364315218b5dddabc26ff8e434c60`。窗口已关闭、execution.once已消费；没有复跑。

## 已有记录与本次只读观察

driver.outer.log：image/config/empty/PG启动、migrate、setup-checkpointer、原grant-runtime
native0；v4_init-fixture native1。API/Web/HTTP未启动，browser/Full/Hosted NOT_RUN。
final PG tenant inventory为0，不把它误解为fixture表为空或原事务已回滚。
inner down0、容器/网络0、保留卷`v4qa_lifecycle_20261104a_pg_data`一份。
ROOT_OUTER.json确认driver native1、未强杀、注册组无live成员、18440/13440关闭、cleanup已确认。

export目录真实枚举：content.json、manifest.json、.MANIFEST.pending。均UID501/0600，
目录700。content 60412字节，SHA256
`59eaeab0006af3421fb3432d2c1c199d3064eb823dc0b5a4a8b18354822211e8`，与公开种子一致。
pending索引包含EXPORTED及同content digest，没有读取owner密码、CSRF或nonce文件。

初步“缺少MANIFEST.json”的表述仅据枚举而来，现予纠正：对该原case做只读exists/samefile
检查，manifest.json和MANIFEST.json都存在且same_inode=true；.MANIFEST.pending存在。
因此没有独立发布索引物理条目，大小写别名不能被当成索引成功。代码先写manifest.json，
再试link到MANIFEST.json，在该大小写不敏感映射上发生名称冲突，不能仅凭文件数认定完整导出。

Root另已用同顺序公开文件、无DB反例复现FileExistsError/errno17，并确认新owned Docker
hardlink/fsync本身通过。这是Root交付的独立复现；不是本会话启动Docker所得结果。
旧pilot CLI抑制了原错误，旧窗实际errno仍未捕获，不回填为已捕获17。
冻结CLI控制流在DB上下文返回后才写三个文件，因此现有布局支持失败落在发布末段，
不是require_owner失败的支持证据；没有连接保留卷补查，也没有据此签DB/seed Gate。

## 最小接线边界

Root已释放backend唯一owner将索引物理名改为INDEX.json/.INDEX.pending；seed内容、
manifest、digest/API不变。后端正式修复commit仍待Root精确转交后核对，不在QA代改CLI。
本QA driver只传新的export directory，不读取/硬编码MANIFEST.json、.MANIFEST.pending、
INDEX.json或.INDEX.pending；本次rg核tests/e2e/v4原实现无这些引用，无需改driver索引名。
因此撤下本轮尚未提交的seed诊断草稿，不为已定位问题再建重复工具、改权限或覆盖索引。
旧目录/文件/卷保持原状；后续必须新source/image/project/DB/目录/端口/UTC，不能重用失败窗。

已有独立准备提交保持：ce51五P2修正8196e62、自然TTL模式3dd1d2b、浏览器模式abae2a3。
它们的纯测试不转为HTTP/PG/Web通过。真实自然TTL/浏览器/Full/Hosted仍NOT_RUN，
200% GUI profile未验；actual token/cost UNKNOWN。本文件仅证据记录，不开放新窗口。
