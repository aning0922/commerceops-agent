# V4显式双subnet a990专项审查

日期：2026-11-04（Asia/Taipei）。**结论：P2_REQUIRED_CHANGES，0 P1 / 1 P2；暂不签该增量的pilot准备接受。** 唯一阻断是检查的Case范围与实际冻结IPAM未绑定，未要求重做旧API/扫描或其它已审计功能。

candidate `a990be0d5ac2fc9252adb77cb104d90face9c1ce` / tree `8b9c3e719abc260409f59e983e7952168460ba58`，parent63c。仅审6个相关已提交delta与实际复用scripts.pg_diagnostic.owned_subnet/no_build_model；未读WIP、未查询实际Docker网络或启动资源。

## SUBNET-01 [P2] Case通过nonoverlap检查不保证实际IPAM使用同一范围

位置：owned_driver.execute在verify_existing_subnets(case)之后展开compose.env并调用no_build_model；no_build_model只核image，未核model.networks的IPAM与case.pg_subnet/host_subnet一致。

prepare正常会把Case写入env，但execute没有验证其后两者仍一致。若case.json与compose.env不一致，当前程序检查一组网段、冻结另一组，然后进入服务创建。所检查范围未重叠不能为实际IPAM提供依据；缺失/不同/额外分配范围应该在任何资源创建前拒绝，不能依赖Docker后续创建失败来补充这个授权绑定。

独立纯反例使用精确函数及实际Compose config展开、没有daemon网络操作：Case请求PG=172.30.250.0/24、host=172.30.251.0/24；合成现有网络为172.30.252.0/24，真实verify_existing_subnets函数返回NO_OVERLAP_OBSERVED。env-file中host改为172.30.252.0/24后，三文件Compose展开及精确no_build_model仍接受，并冻结host IPAM为252，与合成现有网络重叠。全程只使用本次新临时占位env/config，不代表实际机器这些网段已占用。

最小修正：在冻结/使用模型前，对default及host_facing分别要求唯一明确IPAM subnet，精确等于已验证的case.pg_subnet/host_subnet；缺失、不同或额外范围拒绝。不要覆盖错误模型为新值、自动选址或在冲突后重试。补Case/env不同、两范围对调/缺失/额外IPAM的拒绝，以及正常展开后保留精确值的测试；不必修改共享compose/旧API或daemon。

## 已核正确部分

Case新增两个无默认字段，validate最先调用既有owned_subnet：必须canonical RFC1918 IPv4 /24，拒绝host bits/其它prefix/netmask写法、公开/CGNAT/link-local/loopback/IPv6/空白等，不自动normalize。两范围overlaps拒绝；旧manifest缺字段构造即失败。prepare的两env变量和overlay required插值均明确，没有默认池回退；PG/pg-test只接internal default，API额外host_facing且发布仍127.0.0.1，未新增服务/权限。

verify_existing_subnets使用无project过滤的network ls --no-trunc --quiet，严格64hex ID、无重复、最多1024；完整inspect只取id/name/driver/IPAM.Config，不读其它网络labels/secrets。行数等于ID数量、每行精确字段、唯一实际ID成员及已知driver；未知/坏JSON/漏行/无Subnet均拒绝，只有host/host和none/null内建无L3特例允许空IPAM。对所有实际Subnet解析，IPv4交叠拒绝，已知IPv6不与IPv4混比。最终再ls要求ID集合不变；checked原生失败/timeout会传播，未作重试。

通过时只落请求范围、网络数量、观察fingerprint和NO_OVERLAP_OBSERVED，不输出原网络详情。此快照不是daemon地址池锁；之后并发新增网络仍可能令实际Docker失败，应保留失败而不续窗/选新范围。这里的不可避免并发变化已在合同中分列，与SUBNET-01可确定拒绝的模型不一致是不同问题。

## 独立验证及交接

精确a990快照下test_owned_subnets+test_owned_driver+test_owned_networks：**48 PASS / 0.17s / native0**。随后上述额外绑定反例成立，现有48项没有覆盖Case与展开IPAM不同。实际只执行纯测试与Compose config解析，未运行network ls/inspect于真实daemon、未创建任何container/network/volume、未改daemon或prune。临时目录已清理。

请QA局部补SUBNET-01后交精确普通commit；原非重叠验证主体无需整体重写。Root的pilotD地址池耗尽/native1/0API/0tenant/cleanup/保卷记录及f56be31保持，不将本反例混为该次实际失败根因。该补丁复审通过前不能凭48pure给pilotE启动闭环签收；真实PG/HTTP/TTL/Full仍各按最终source和实际回执核定。

## 2026-11-04：1684e04 最小修复复审，SUBNET-01 关闭

**最新结论：ACCEPT_PREPARED_EXPLICIT_SUBNET_MODEL，0 P1 / 0 P2。** 上方 a990 的原 P2 和反例保留为修复前事实；此结论只覆盖下面精确增量，未重审无变动部分或签发真实资源运行结果。

fix candidate `1684e0455978b46ddad607e09d85a1af5657ab1a` / tree `931e2ea516393156eeaf6e9a2fd1fac45deaaf22`，parent 恰为原 candidate `a990be0d5ac2fc9252adb77cb104d90face9c1ce`。变更为 actual expanded model guard、对应纯测试/夹具及说明，没有改原 inventory、业务或服务入口。

no_build_model 首先调用 verify_expanded_model，在写 frozen JSON/hash、检查项目空资源和创建任何服务之前，对真实 Compose config JSON 校验：顶层网络恰好 default/host_facing；两个唯一 IPAM config 分别精确等于 Case 的 canonical CIDR；default internal=true、host_facing internal=false（接受正常规范输出省略 false），bridge/default IPAM、project 自动 name，拒绝 external/attachable/IPv6/custom options 和额外分配范围。PG/pg-test 仅 default 且不发布 ports；API 恰好两网络，不允许 network_mode、别名/static IP 附加项；唯一 TCP published/target 精确等于 Case.api_port，host_ip 恰好 127.0.0.1。失败直接拒绝，不覆盖错误值、重新分配或重试。旧 image 校验、移除 build、pull_policy=never 和三服务选择保持。

独立精确快照执行 test_owned_model_guard.py、test_owned_networks.py、test_owned_review_fixes.py：**44 PASS / 0.17s / native0**。另用本次全新占位路径/env 和实际 Docker Compose CLI 对三原文件展开：正常模型 native0 且被精确 no_build_model 接受，网络原值保持、最终仅三服务。随后把 env 的 host subnet 从 Case 的 172.30.251.0/24 改为 172.30.252.0/24，真实展开模型在冻结前被拒绝，错误为 `expanded IPAM differs from registered Case CIDR`；原 SUBNET-01 反例不再成立。对正常实际展开模型派生的两范围对调、缺失 IPAM、额外范围三个独立反例也均拒绝。

只运行纯测试和 Compose config，不执行真实 network ls/inspect、PG/HTTP/Web/TTL/browser，也未创建 container/network/volume。临时快照已清理。未用本次结果补签旧 pilotD 失败或 a990 源码；后续 ROOT 最终合批、具体资源/UTC 和运行回执仍单独记录。本项代码阻断已关闭，可作为 ROOT 冻结后续功能候选的准备证据。
