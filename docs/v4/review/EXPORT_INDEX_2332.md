# V4 导出入口文件名与纯 helper 增量独立审查

2026-11-04，Asia/Taipei。**结论：ACCEPT_SCOPED_EXPORT_INDEX_DELTA，0 P1 / 0 P2。** 接受本次物理索引命名与等价 helper 抽取的代码增量，供 ROOT 在全新 case 安排后续实际 CLI/HTTP 验证；不签 live pilot、旧失败 case 恢复或实际 DB/API Gate。

## 精确来源与范围

- source：`2332f738885ebd0608cbe1ce670ae434116588fb`。
- tree：`a6019db8abb4f4303833d0e38b64939d31df55b6`。
- parent：`2f1e98d26e466bcb1d0c287aedfb43c2536af62b`。
- 唯一四文件：`scripts/v4_demo_seed.py`、新增 `tests/v4/test_demo_seed_cli.py`、两份设计文档中本地导出包装说明。未改 backend、DDL、API、冻结核心合同或锁文件。
- CLI 文件 SHA256：`23c7141ffeaffda418b9c0a3117b0ce5184c1b7657a1ef5b3889920d92979f38`。
- 新测试文件 SHA256：`fb87ced4f40259c3f427469ef2586a0e4c3d96480f7b79526411038384571574`。

仅从精确 Git 对象静态审查，没有读作者 WIP、旧导出/配置/卷，没有执行 CLI、测试、PG、HTTP 或敏感扫描。ROOT 转交的 APFS samefile / EEXIST17 与 pilot init-fixture 失败、已停保卷不重试，均保留为 ROOT/作者证据，未冒称本会话独立实测。作者 7 pure 与真实新 tmp 发布结果也仅按作者结果记账。

## 发布边界核对

| 检查 | 结果 |
|---|---|
| 命名冲突 | 原 `.MANIFEST.pending` → `MANIFEST.json` 改为 `.INDEX.pending` → `INDEX.json`；新入口与 content.json、manifest.json 不仅大小写不同，消除已定位的名字别名条件。 |
| 独占及 no-follow | write 的固定名单只替换 pending 名；O_WRONLY / O_CREAT / O_EXCL / O_NOFOLLOW、0600 与 dir_fd 保持。无默认覆盖、宽化文件名参数或不支持平台时的降级 fallback。 |
| 目录边界 | new_directory 的 AST 与 parent 完全相同：绝对新目录、拒绝 .. 与根目录、逐级 O_DIRECTORY / O_NOFOLLOW、最终 mkdir 0700 并独占取得目录 fd；原有目录/符号链接拒绝路径不变。 |
| 原子发布及持久化顺序 | 每个文件 write/flush/fsync 后，仍通过同目录 dir_fd 的 hardlink、follow_symlinks=False 独占发布；已有 INDEX 或其平台别名导致失败，不 rename 覆盖。随后仅 unlink 本次 pending 并 fsync 目录，顺序不变。 |
| 异常与 fd | helper 使用调用者目录 fd，不新增打开目录或自行接管其生命周期。各文件 fd 仍由 fdopen 上下文关闭，文件写入/发布异常仍穿透到目录上下文 finally，逐级目录 fd 按原方式关闭。没有吞异常、补写、删除已有目标或自动重试分支。 |
| 部分发布失败 | hardlink 后 unlink 或目录 fsync 若失败，仍可能已有可见索引，CLI 仍报失败并保留原物件；不能据异常推断 DB 或文件回滚。该语义与原流程一致，不准用本修正恢复旧 case。 |
| canonical 与 DB | content 仍为 bundle.canonical_content()，manifest 仍为原 model_dump_json().encode()；索引 JSON 字段、sort_keys 与 digest 来源未变。DB connect/initialize_fixture 的退出提交仍先于 export；seed_contract 和基础设施 seed 模块 blob 与 parent 相同，没有 DB/API 行为变化。 |

独立 AST 对照进一步确认：把原 main 中的导出语句取出，只替换上述两个物理文件名后，与新 export_fixture（排除 docstring）AST 完全相同；将该段替换成 helper 调用后，main 其余 AST 完全相同。新增 SeedBundle 仅提供已有 seed_contract 模块的类型引用，不增加外部或 DB 调用。

新测试静态覆盖真实新目录成功发布及 casefold 模拟、原名字冲突、已有 INDEX/大小写别名不覆盖、已有目录拒绝及已有文件符号链接拒绝，并断言 content/manifest 字节、固定 digest 和 0700/0600。模拟 casefold 与作者真实 tmp 结果分记；本审查没有重新执行这些用例或把它们代签实际 APFS/PG/HTTP 验收。

## 核收边界

两设计文档仅同步本地物理包装名字与 hardlink 的真实语义，保留 DB COMMIT 与文件发布分离、EXPORT_INCOMPLETE/失败保留、不重试不覆盖及旧 case 不修补的边界。本精确增量未见阻断问题。ROOT 可据此安排全新 case 的实际 CLI+HTTP；critical DB cap 2f1 仍由 Astra 独审，不因本报告获得任何附带准入。原失败、原保留卷及未知证据不重置，actual token/cost UNKNOWN。
