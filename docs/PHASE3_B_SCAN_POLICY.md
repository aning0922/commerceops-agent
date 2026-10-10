# Phase3 B公开metadata历史误报的精确政策修复

状态：Root直接协调的单一owner政策批，源码独审/精确CI以PR37后续回执为准；不表示A02/B/完整阶段Gate通过。A02在制业务/迁移/Worker/Graph/公开DTO及其tests全部未暂存、不加入本政策commit，当前自有PG窗口保持原90min边界，不停止/重启测试或读取旧密码。

Root核实B本地普通提交`973bf6447211f084355d61b9d58adfd95dfa2788`发生在扫描非零后exec未停；当时未push。随后`6824db4877e74e0eb08ec17fa2a4300a3e46ca2f`普通修当前metadata，当前/index零，历史唯一generic-api-key误报是`frontend/evidence/b02-read/validation.json:27`公开扫描状态文案。Root及A用git show只核该历史整行，非凭据；不把删当前文件当清历史，不amend/reset/force、不使用.gitleaksignore。B编排错误和旧失败保留，政策独审后B才能正常merge此policy、复扫再push；当前remote B仍14dc。

新增第四例外仅generic-api-key +该精确文件路径 +完整原行，condition=AND、regexTarget=line、全行regex；原行SHA256 `2fd5c5a9ece651f39320ee19c19b067b6f388064fd47cc64bdd2c6dc78f53437`，来源973bf64/line27。文案没有真实key/token/password/DSN；正文不复制可能触发另一路径误报的完整JSON赋值。没有新增目录/keyword/skip/global豁免，原schema/规则自声明/OpenAPI三例外完整保留。生成器、固定provenance/config摘要和strict validator同步；安装依赖前仍只用stdlib导入常量。

2026-10-10 Asia/Shanghai，本批实际开始22:45:57，15min上限23:00:57。实际49 quality gate tests passed/65.08s（原42+新增7）：精确行current/index/fullgit通过；改一个字符、同文案异文件、邻接generic/PAT、移除当前合成值后仍阻断历史；扩大新B path且更新configSHA仍fail-closed，原OpenAPI的独立扩大path反例也仍阻断。逐规则比较确认222规则语义全部不变、原3 provenance例外逐字段不变，只追加1条。Ruff/format/mypy及最终三范围扫描另附同PR安全回执；不得把未运行的CI/独审写成通过。

这项必要解除从原预算内扣，人工H/L not_reported；无新业务分支/任务/扫描框架、零模型/平台业务写/生产/Phase4。A政策freeze正常推同PR37后继续原A02，Root安排独立政策审核；B不碰A在制目录，不上传未解除的历史阻断。
