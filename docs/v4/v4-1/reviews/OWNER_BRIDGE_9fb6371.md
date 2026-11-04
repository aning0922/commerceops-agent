# V41 owner bridge 最终候选独立审查

日期：2026-11-04（台北）。source `9fb63719984c118040ad421cbeb0af6ae138aad4`，tree `61bc8290dae8ee0e347ce0848b0a1c1658ec1531`，parent `ebfdcfc06d2819a543281b415b3d531b7e0b7190`。只读精确提交及已审依赖源码，未读作者 WIP。

结论：HOLD_O01_STILL_OPEN。本片未关闭前次 P2 O01；新增 bridge 范围未发现另一项 P1/P2，但不据此签整体 helper、实际 owner SQL 或真实 HTTP 准入。

P2 O01 仍在 `tests/e2e/v41/owner_setup.py:496-507`：函数目录查询仍只有 app EXECUTE 和 PUBLIC EXECUTE，判定仍仅比较固定 runtime OID 集合；没有 EXECUTE WITH GRANT OPTION 查询和拒绝。与 ebfd 相比，本片增加的是实际七表集合、严格 JSON 和 action-once，原函数 ACL 查询与判定没有改变。README 的 delegation 描述只与已有列级检查对应，不能作为函数级转授权已修复的证据。修复仍应对全部 V41 函数显式核 app 有效 EXECUTE WITH GRANT OPTION 为 false，并补允许普通 EXECUTE、拒绝转授权的针对性负例；不要求新增 owner 动作。本发现不声称 grant_runtime 当前实际授予了转授权。

桥接已核部分：

- owner_recipe 严格列出原三动作和固定 standalone helper/inside-program hash，不再依赖 READY 或坏的 checkout CLI。runtime_handoff 要求实际 Root 私有 authorization 与 Case 的 source/tree/test+PG image、project/DB、目录、scenario、UID、ports、starts/deadline/parent_deadline 逐项相等；prepare 不生成 Root 批准。QA 分支本身不包含生产 V41 helper，仍须 Root 合入已审后端并冻结真实组合 source/tree/image。
- build receipt 保留 Root 强 proof 结构；raw expected 文件 SHA 与规范化 manifest SHA 分开核，host 期望清单与实际 Git/source 一致。sourcecheck 无宿主挂载、network none、read-only，固定 Python entrypoint 执行逐字节批准 verifier，包含实际 noneditable 安装包；owner helper 在生产导入前和提交前重验。没有给 archive 填假 .git。
- 固定 daemon 来自另一个 Root 私有原件，先核 binary/plugin pin，再以同一 shim 查询实际 server ID；新空 HOME/config、禁用 daemon override、初始 namespace/卷不存在、精确 immutable image 和 no-build/no-pull 保持。原 source/tool seal 与终态核验仍在。
- prepare 由本案新随机 API 材料派生 owner 配置，只重写固定 mount 路径；CSRF/nonce 内容相同。owner/app 密码及 API/owner JSON/key 文件纳入初始 config seal，七份 owner 输入另绑定每动作 manifest。已审 security.config_fingerprint 依据 key 内容、version、origins 和 transport 等语义，不把 owner/API 的文件路径差异误作不同 policy。
- 原 migrate/checkpointer/base grant/V4 seed 之后严格串行三动作。每次宿主先保存 operation/intent，helper 再消费原 UUID 和本案 action.once；换 UUID 不能重试失败动作。checked 保存实际 native/start/end/log hash，非零或 timeout 不进入后续动作；native0 后还须 stdout 与持久原回执完全一致，核 op/action/status/source/tree/image/DB/project/auth ID。后继 helper 再核前一 COMMITTED 回执 hash 与绑定。
- verify 成功原回执才复制给 API；API 启动位于三动作循环之后。SQL probe 消费同 Root 授权和 VERIFIED 回执，核 policy fingerprint/private verifier 不可读事实，不再把旧 metadata READY 当批准。原 helper 在已观察 COMMIT 后保存回执失败仍输出 COMMITTED、native非零；bridge 不升级为下一阶段或成功，原未知和原操作身份保留。
- 失败 finally 仍先停止 writers/API/owner oneoffs，再尝试最终只读事实；采集失败不跳过 scoped down 和容器/网络/端口、保卷 identity 检查。最终 source/build/expected/daemon/config seals 和 cleanup confirmed 共同决定是否仅进入 PENDING_REVIEW，不预写业务验收通过。

独立验证与限制：

1. 精确 Git archive 上尝试整个 `tests/e2e/v41 -m offline`，native exit 1：74 passed、7 failed、8 errors，8.74s。8 个 strict HTTP fixture 错误是其固定 git show 历史读取遇到 archive 无 .git；6 个 runner 场景及1个 supervision 测试的实际 worker.private.log 同样显示本 archive runner 的 Git 元数据读取失败。实际 worker native1/reaped、失败原件保留；不归为新 bridge 业务缺陷，也不改写成89通过。
2. 精确相同 archive 的直接相关五文件 owner_setup、owner_bridge、image_provenance、owned_driver、owned_manifest：24 passed，3.48s，native exit 0。包含 relocated stdlib verifier 的实际文件/安装包差异拒绝和短进程 stub；无容器/PG/真实 owner SQL。

作者报告89offline/type37/native0属于作者证据；本轮不据自身24测试代签其89或 type37。没有 Docker/PG/SDK、服务、真实 HTTP、Full/CI 或远端写入，未读取真实凭据。O01修复后的新精确候选仍需复审；H01表数由API独立处理，不在本片改写。
