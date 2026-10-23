# 固定 d97 历史 C0 fixture

仅供 `test_forward_0012_upgrade_preserves_original_c0_rows_and_checkpoint_bytes`。来源为已存在的提交 `d97c6ae8007eb5b69024e514210860f42359673d`，不是当前业务实现，也不作为平台 SDK 或真实身份验收。

`source.tar.gz` 保存原 Git blob 字节：从 `tests.p3_support`、`tests.p3_process`、`tests.test_p4_first_create_pg` 和 `commerceops.entrypoints.database` 递归追踪本地 import 与子进程模块入口，包含必要 package init、原 migration 树、inventory-v1 数据、两份包内 OpenAPI，以及原 Worker 初始化所需 tokenizer 数据与原 license/provenance。142 个 Python 模块、164 个文件；未复制整个项目。压缩包固定 gzip mtime=0、tar uid/gid/mtime=0。`manifest.json` 给出原 source/tree、archive SHA-256 和每个文件 SHA-256，入口同时固定 manifest hash，拒绝额外成员、重复路径、链接和非普通文件。

测试运行不执行 git、联网 fetch 或依赖 shallow checkout 的旧历史。提取到该节点的临时目录后，用 `python -I` 在独立进程运行原 d97 `grant_runtime`、`initialize_p3` 与完整 `original_c0`。原真实 API、PG、Graph、checkpoint 和 C0 子进程照常执行，保留旧断言与 stop/reap；没有 Noop collector、替代业务 INSERT 或生产兼容开关。P3Process 使用原 source hash 检查；历史主进程再核全部实际加载的 commerceops/tests 模块字节与清单一致。只有 Fake transport，原 `/never-read` 平台秘密路径不读；新自有 PG/合成会话凭据仍按原 fixture 管理。

迁移分两段：固定旧树仅移除0013后迁到0012并构造原 C0；独立0013树验证全部原 business/checkpoints 表的行数与逐行原始 JSON 文本 hash 完全相等；再用当前正式 migration 树到0015，完整保留原 keyset/hash，新增两表必须空，并执行当前明确 grant、低权 role 与列权限断言。所有数据库均为该节点在新 owned PG 项目内创建的随机测试 DB。

诊断保留阶段/class/SQLSTATE，私有子进程日志不进入公开事件。两段 migration、比较、revision、grant 和 client/DB/admin cleanup 均有 Fake 失败覆盖。9c CI 原失败现场的具体 stage/raw trace 未捕获，具体历史根因仍 unknown；源码确认的 fixture 不兼容和新测试结果分开记录。

本包 SHA-256：`daaefa581ada95e448c340da326a0ff0cfa6d88a274894d36f3c9b520a09f2d6`。manifest SHA-256：`8fcdfe5391dc1d512806ec3228a840c15946b08f8d51e48df50cca25b420ed6f`。这两个值同时固定在 `tests/p4_legacy_c0_d97.py`。

本批唯一新自有 PG 在历史 `initialize_p3` 得到 FileNotFoundError/SQLSTATE null，C0/两段迁移比较未运行。随后仅离线补齐 package OpenAPI 和 tokenizer 资产并核真实旧 API/ProviderFactory 构造、baseline/known_inbound fixture 加载；未开第二轮本地 PG，补齐后的真实验收待 Root 独审与新精确 CI。首包 archive/manifest 哈希和失败私有证据保留。manifest 改为 path/sha256 分行结构，消除扫描器将文件名相邻摘要误识别为 key 的3条命中；不修改规则或豁免。
