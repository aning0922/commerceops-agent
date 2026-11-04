# real-api-dashboard-r2 有限运行事实独立审查

2026-11-04（台北）。结论：`LIMITED_OWNER_AND_DASHBOARD_HTTP_FACTS_ACCEPTED / ORIGINAL_CASE_FAILED`。source `9e1beb0e967553a8d9dc24484f1d5845fee2e8ed`，tree `97bd376738e6fd03e7bc5ba91935891adc6ea98d`，实际镜像 `sha256:4cca6d7cabddcfed0c62d29ef45a7cf8e7fae51086692cceb06f740a39d4369d`。已执行步骤的有限事实可保留，整体case不能改成PASS。

## 已核原件与已执行范围

按Root限定只读GATES `.audit/v4-1/owner-ddl-build-r8/{receipt,closedfinal}.json`、`real-api-dashboard-r2/{execution,closedfinal}.json`、r2-prep的terminal-seal-diagnostic及next-env.generated.diff，并对限定安全manifest/回执核摘要。build receipt与其封存摘要一致；case中execution、once、source-before、image-build.safe、expected-runtime、docker-host.safe六项摘要与封存索引一致。未读取owner/app/CSRF/nonce/auth私配、subjects/session秘密或final-facts私有原始内容。

运行expected-runtime的705文件逐项与9e1 Git archive相等，216个package Python文件范围与build/runtime sourcecheck回执一致；build-r8封存为SOURCE_PROOF_PASS，源/锁/安装包与实际image绑定，不把镜像构建成功当HTTP成功。

`execution.required`恰37项，native_exit均0且无记录timeout。其中迁移0025、旧接点/seed设置、owner步骤、API/Web监听归属、固定probe、writers停止、末态采集与资源down均有完成记录。owner安全回执三项均绑定同source/tree/image/project/database：activate-policy COMMITTED、grant-runtime COMMITTED、verify-runtime VERIFIED；verify结果记录七表、22私有函数及app不可读private verifier。这里只接受这些实际回执的设置/校验范围，不扩大为全部权限矩阵已验。

真实API/Web已启动，`dashboard_same_source` probe native0。按精确9e1 `http_recipes.py:605-627`，该分支读取products/dashboard，以冻结seed/reference核KPI、fixture digest/source mode，并核两读data_revision一致；随后另一visitor读取自己商品/详情并对外来shop查询得到预期404。此分支未执行后续新ca69的全部12个GET、业务写/导入分支或浏览器旅程，不从probe0反推这些用例通过。末态facts步骤native0，公开摘要记录schema0025和DB UTC `2026-11-04T04:46:33.549343Z`，未额外读取含身份的私有导出。

## 整体失败必须保留

原execution仍为 `SCENARIO_COMPLETED_PENDING_CLEANUP`、summary NOT_WRITTEN、cleanup.confirmed=false；cleanup.failures记录 `terminal_source_seal / ValueError`。driver native1、outer native1、parent_timeout=false。writers退出分别probe0/web0/api130，不能写成所有子进程exit0；required步骤的api_stop0与被停止进程130分记。

原 `owned_driver.py:665-671` 在snapshot失败时尚未写source-after，且只保存异常类型。因此原始ValueError具体消息是 **NOT_CAPTURED**，source-after是 **NOT_WRITTEN_DUE_SOURCE_SEAL_REJECTION**。不得用后续诊断补造原错误全文或事后成功seal。

新只读诊断的scope为CURRENT_READONLY_TERMINAL_SEAL_DIAGNOSTIC_NO_REPLAY，实际报告 `ValueError:UNAPPROVED_UNTRACKED_RUNTIME_INPUT`，当前唯一被拒路径为 `frontend/next-env.d.ts`；tool_drift为空。所给diff重建后恰296字节，SHA-256 `0f70629890b72a0a82e91972cc032c04b658b26c265373cb711cf576bfbf8fcc`，与封存记录一致；HEAD无此项。内容为Next类型引用及generated routes/root-params导入，不是新增业务实现。

9e1 `source_seal.reject_new_inputs`独立于Git ignored状态遍历runtime目录，只排除既定生成目录和tsbuildinfo，因此这一新文件会被当前规则拒绝。该源码与新诊断支持当前失败定位，但仍与原消息未捕获分列。tracked_drift/tool_drift均空不等于完整seal通过；没有删除/恢复文件、扩大ignore、修改原once或重放来消除本案失败。

## 资源及剩余门槛

后续closedfinal核namespace容器/网络为空，18460/13460均关闭，四个明确记录的进程组检查stdout/stderr为空，一份原身份的PG卷保留。Root另报告43个PID absent；本次限定原件直接列出的是四组，未另读取PID诊断私件或把转交数字冒称逐PID独立核验。资源已停的后续事实不改原driver cleanup.confirmed=false；整体仍FAILED。

封存closedfinal摘要为 `90ca4f09c28b531680d78701c518055c40fc858170a7618bca03b76d36723deb`；fresh诊断摘要为 `b9a58c3583da81220e80b435e00b1df3058c1240340652ca512fc3c9effcc7ee`。这份文档只核上述有限owner/HTTP及清理事实，不授予续窗，不签ca69新矩阵、真实business browser、截图/原生200%、Full或阶段完成。本Reviewer未运行服务、浏览器、PG或重新snapshot原树。
