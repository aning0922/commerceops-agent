# V41 owner helper 首片独立审查

日期：2026-11-04（台北）。source `ebfdcfc06d2819a543281b415b3d531b7e0b7190`，tree `59825b3b2f3e3d90014f9ff4c741ffe71f36b334`，parent `f667d099857f69fef0938bc077953b5e05769e25`。只审该提交的 owner_setup.py、test_owner_setup.py、verify_inside.txt；未读 host bridge WIP。

结论：HOLD_VERIFY_RUNTIME_ACL，存在一项 P2。首片来源、固定动作和失败保留设计可以继续准备，但不签当前 verify-runtime 为完整 ACL 验收。

P2 O01：`tests/e2e/v41/owner_setup.py:486-497` 对全部 business.v41_ 函数只读取 app 的 EXECUTE 布尔值和 PUBLIC EXECUTE，再与固定 runtime OID 集合比较；没有读取或拒绝 app 的 EXECUTE WITH GRANT OPTION。因此某 runtime 函数从普通 EXECUTE 变成可转授权 EXECUTE 时，这两项观测完全相同，仍会返回 VERIFIED。现有 column ACL 已明确拒绝 SELECT WITH GRANT OPTION，函数部分也应查询 app 的有效转授权能力并对全部 V41 函数要求 false。建议补同一函数的普通执行允许、执行加转授权拒绝的纯谓词负例，后续在获准的新 PG 案验证实际 ACL；本轮未执行 GRANT/SQL。该发现不是声称当前生产 grant_runtime 已授予转授权，而是 verifier 不能识别此额外权限。

已核可保留部分：

- 三动作严格固定为 activate-policy、grant-runtime、verify-runtime，没有 bootstrap、迁移、seed、服务启动或重试入口。Root 私有 authorization、operation、build receipt 绑定 source/tree/image、UID、新 project/database、固定 scenario/ports、UTC 和父截止；实际宿主 image/namespace/挂载及外层限时仍由后续 bridge 负责，文本 authority 本身不是独立签名。
- 固定 stdlib verifier 先核 `/app` 完整清单和实际 noneditable 安装包，再导入生产 database/security/runtime helper，解决前次 C01 对 archive/.git 的不适配。固定 verifier SHA256 实际为 `20718b7cb02763253c453f6703687d45ceeb666f3d93b9149318a3822c24636e`，与常量相符；没有伪造 Git/READY 绕过。此为源码审查和 hash 核对，不冒充新的容器 inside proof。
- 七份 config/secret 均固定路径并绑定内容 hash；目录与文件检查 UID、权限、无 symlink，配置限制新 owner/app 数据库和本机固定 origins。进入 SQL 前和提交前再次核 seal/source，实际 DB/user/schema/版本由原 owner helper 与 target 核验。
- 操作原件固定 UUID/path/hash；尝试前 EXCL 写入并 fsync once 文件，失败不恢复可用；后继严格绑定前一 COMMITTED 回执。提交已观察到但回执保存失败时保持 COMMITTED，原回执不覆盖；未知错误保留 UNKNOWN/retryable=false。
- 表/列/Public、policy 私有 verifier、当前 config fingerprint、固定 runtime 签名和前后旧 ACL hash 检查均保留；verify-runtime 使用只读事务。O01 是上述函数 ACL 的具体遗漏，不要求扩大动作或恢复旧 CLI。

独立验证：从精确 Git archive 提取，只读使用锁定环境依赖，PYTHONPATH 指向该 archive。`tests/e2e/v41/test_owner_setup.py` 5 passed，0.97s，native exit 0。覆盖授权拒绝、raw/manifest hash、私有文件不覆盖、失败 once、已提交回执写失败；没有实际 SQL 或容器执行，不能代签 owner 三动作和后续 StageFull。

无 Docker/PG/服务/新 native child、secret 内容读取、浏览器、Full 扫描或远端写入。Root 新报 dc22 专项 22/22 尚未在本片核读私有回执，仍为另案、非 Full。
