# V4 API专用host-facing网络3b3增量审查

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_PREPARED_OWNED_NETWORK_DELTA，0 P1 / 0 P2。** 可交ROOT为全新pilot登记实际运行窗口；只接受本测试overlay拓扑，不签真实host连通、HTTP场景、TTL或Full通过。

candidate `3b3280844aa6d6bada70d16b2ce3889b13dbd69d` / tree `60c64c6ec9d8c9ab76f2c1025cb354b1605e3670`，parent `7913e728ea4c16a0141fededc371f0efa74951c9`。exactstat仅owned.compose.yml与test_owned_networks.py两文件。只读取精确提交和其引用的已审三文件Compose/no_build_model，未读WIP、未修改实现。

## 核准边界

postgres及pg-test显式networks=[default]；default仍internal=true，二者无ports或network_mode，不引入host网络。v4-api独自加入default+host_facing；新增host_facing是bridge/internal=false，模板无external或自定义跨project固定name，实际Compose名称随本case project隔离。

API宿主发布原样限定127.0.0.1:${V4_API_PORT}:${V4_API_PORT}，没有发布PG、增加其它服务、权限或挂载。command仍为已审tests.e2e.v4.owned_api；API仅挂/run/v4_api只读runtime目录，无owner secret及COMMERCEOPS_DB_*环境。旧Settings/API main、业务、认证、Dockerfile/共享compose未改。非internal bridge是ROOT本次明确授权的端口发布拓扑调整，不扩展任何外部provider/业务调用授权。

原no_build_model保留精确network定义和membership，同时仍只保留postgres/pg-test/v4-api、删除build并固定pull_policy=never；没有因模型冻结丢掉PG隔离或为API自动带上owner能力。driver原空project检查、按project标签查network、down并核network空的逻辑没有假设只能有一张网，因此新增项目网仍处于原owned清理范围；实际退出/网络删除仍须新窗口取证。

## 独立验证

精确3b3快照定向 **5 PASS / 0.13s / native0**：新增文件4节点（含两种normalization参数）加原overlay无PG发布/API无owner环境节点1。均为JSON/函数纯契约，无Docker资源调用。

另使用仅含本次合成占位路径/image ID的env-file，对精确根compose.yml+compose.m3.yml+owned overlay执行只读`docker compose --profile test config --format json`；交精确no_build_model后再次config重解析，均native0。实际展开验证：postgres/pg-test只有default、两者发布端口0；API只有default+host_facing、单一host_ip127.0.0.1；default internal、host_facing bridge非internal；两网名均为本次review project前缀，全部三服务无build且pull_policy=never；API无owner env/secrets。没有up/run、没有镜像获取、容器/网络/卷创建或服务探测。

ROOT转交pilotC“容器内health200而host ConnectError、原网络Gateway空/端口表现异常、native1、资源清理全0且保卷”的失败事实及f56be31回执保持原样。本次没有重跑或改写旧case，也未将模型展开称为该故障根因的运行复现或修后端口已通。

## 交接

ROOT可按已审组件整合新source/image、全新project/DB/配置/UTC进行下一pilot，先收实际网络/host端口/HTTP及cleanup事实；不能复用旧failed case。未读取或核收browser pin后续SHA，本网络接受不改变浏览器/原生200%/自然TTL的各自来源与运行Gate。Reviewer只提交本报告，临时配置/测试目录已清理，工作区实现未变。
