# V41 Root490构建、DDL、PG7与PG22有限运行核收

日期：2026-11-04（台北）。只读核四包既有私有原件，未重跑任何资源/命令。统一source `49077566c9ad8f3b1696aa3d8fc46b7ef1d57fbf`，tree `80c68225bfa60d946abb8e1add5fbc4f5f92ded7`；test image `sha256:f2ba3244b72fcf4a54bb4971437c9f1f9fee9b62c5b86dcb84b88f8775eda373`；PG image `sha256:bb26ccd46218e47cd66abecb2fc6ea36f3815584743b60e9b9eb9f7c1072d91f`。原件根为 `/Users/aipuli/.codex/worktrees/commerceops-v41-gates/commerceops-agent/.audit/v4-1/`。

结论：ACCEPT_BOUNDED_BUILD_DDL_PG7_EVIDENCE；PG22为VERIFIED_FAILED_CLOSED_NO_RETRY，不接受为22通过。四包source/image一致，408个命令stdout/stderr日志hash、closedfinal证据hash及safe-failure绑定全部独立匹配。仅核采集时点事实，不冒称本轮重新查询Docker或当前运行状态。

| 包 | 核收事实 | 原生/时间边界 |
| --- | --- | --- |
| owner-ddl-build-r4 | build成功；完整667运行文件和216安装Python文件来源证明成功 | build/sourcecheck各0；03:29:48—03:30:08 UTC；没有PG/secret创建 |
| owner-ddl-pilot-r4 | 实际迁移到0025；七表均0、policy0；29新函数PUBLIC/app EXECUTE均拒，七表仅owner ACL | migration0/outer0；closedfinal 03:31:11 UTC；一次，无runtime grant/fixture/checkpointer/API |
| pg7-root-r1 | collect7、执行7、通过7、失败/跳过0；六种撤权先后及旧双session/policy反例 | collect0/pytest0/outer0；JUnit8.145秒；closedfinal03:34:14 UTC；一次 |
| pg22-root-r2 | collect22；执行3，2通过、1失败、19 NOT_RUN、0 skipped | collect0/pytest1/outer1；JUnit3.843秒；closedfinal03:37:55 UTC；maxfail1、一次、无重跑 |

## source/image证据

archive SHA256 `3036c5ceb1e103433a5febdda882fe71b885719d4e90494b3fb084b8449462e2`实际匹配。独立用git cat-file读取精确490的667个文件，与archive成员、解包context及expected-runtime.json逐字节/hash比较，文件集合完全一致；其中backend/src/commerceops的Python文件恰216。

已读并核hash的overlay在原固定base上保留pyproject/uv.lock/.python-version版本检查，复制精确backend/tests/scripts，并以frozen/offline/no-editable重新安装commerceops包。镜像内verify_inside实际输出与receipt一致：核/app完整文件集，再用find_spec定位venv非editable包并比较216个安装.py文件，原生0。manifest canonical hash `493f9a364006b37c21c856aabb2b257a900d1296642cf1adb23c48dfe4230ecc`一致；不把仅镜像label/ID当作来源证明。

build的source_binding内PREPARED状态是准备快照；后续实际build、sourcecheck成功另有命令记录，不覆盖旧字段。19个注册CLI group最终ps返回1且无存活状态，named sourcecheck明确不存在。无新live复查。

## DDL与清理

三个PG案均先核注册namespace容器/卷为空、精确名称不存在，再创建各自data/socket卷；network=none、无发布ports。每次daemon命令前保存同server ID查询，均0且身份一致。实际ready为PG17.11/vector0.8.7；首次readiness2后第二次0是启动观察，不改写成首轮成功。名称不存在的inspect1也按预期负观察保留，不宣称全部命令0。

DDL最终owner facts独立匹配receipt与closedfinal：revision0025、七表精确集合/全空、policy0；七表PUBLIC权限空、app SELECT/INSERT/UPDATE/DELETE为false，原ACL只owner；29函数PUBLIC/app EXECUTE均false，owner/search_path事实保留。只能签DDL-only与未授权状态，不签runtime grant或业务行为。

三个closedfinal独立再次查询容器/网络为空，所有注册CLI group ps1且stdout/stderr空。各案两卷的Name/Driver/CreatedAt/Labels与创建及cleanup原件完全相同并保留；不用名称冒称其他不可变UUID。PG7/22停止前最终owner catalog只含postgres、template0、template1及该案管理DB，测试随机库已不在catalog，client_connections为空；app role为login且非superuser/createdb/createrole，仅存在于各自新owned cluster。容器/网络关闭、卷保留不等于删除该role或测试原件。

## PG7与PG22事实不合并冒签

PG7的JUnit七个testcase名称与collect名单一致，六个False/True×credential/scope/grant及一个policy反例全通过。它只证明此精确source、此窗口的七个主体；预期23514拒绝不记作业务故障。不能将其叠加到后案计数后写成“完整22通过”。

PG22两个通过节点为seven_tables_private_helpers_and_low_role_no_dml、sql_python_canonical_text_corpus；第三个golden_reads_tags_receipt_replay_original_after_later_effect失败，其余19没有运行，不是skipped。原PG日志42501共7为首ACL节点预期拒绝；实际失败23514共1。collect与实际JUnit/未跑名单一致，命令确有maxfail1且未超时。

私有trace独立核到测试第221行第二次store.action，错误V41_TAG_INVALID，v41_mutation_guard line43 RAISE，调用context为v41_apply_action的INSERT ... ON CONFLICT DO UPDATE。精确公开测试源此前构造expected_version=1，期望第二次效果版本2；实际该调用未成功返回。trace含临时bearer/CSRF，本报告没有复制原trace、临时身份或token；凭据文件未读取。

“upsert先走BEFORE INSERT、带入version2而撞INSERT必须1”是与源码和报错位置相符的解释，仍未捕获实际TG_OP、NEW.version或OR的具体触发分支，不能写成已抓到wire/唯一根因。safe-failure-facts对此明确标unverified hypothesis。本核收不补造第二次写后的DB逐行回执；fixture删除测试随机DB后的最终catalog只证明清理。

## 原件摘要与剩余边界

build receipt SHA256 `4fc2b99e1231acd433d4f85263aacca035a7797a71779304c8d7d88f368097ff`；DDL closedfinal `0c14e72d2c5a39e744a8f0d0e22611fa293e316704ae54b0584a9f1f87878686`；PG7 closedfinal `ca8923c784f65cc65e451a4047ba04dd9f03e90b949d3a640f18c1f2f662f119`；PG22 closedfinal `2bf5adbfc9abf26aef1337bee126c059fc67246fbd3053ceb3d494b655f46540`；PG22 safe-failure-facts `da56e9294d1e9d060beefa5bb4a9b87a3964c6a8582fd916e267e2b8e543cabc`。其链接的receipt/JUnit/log/final_owner_facts hash均核过，原件未改。

stageFull、真实HTTP/SDK、GC及未执行的业务主体保持NOT_RUN；旧R2/R3失败不被R4覆盖。新tag修复须独审精确patch、新组合source/image及独立新案，不能重写本PG22或自动重跑原窗口。本轮只有只读Git/文件/JSON/XML/hash检查，未执行Docker/PG/测试/外部网络操作。
