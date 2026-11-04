# 本地复现指南：ROOT 独立文档核收

接受 f7e6a67e7ce78e972643a36f442ed0cd7c9b296b 的唯一新增 LOCAL_RUN.md。ROOT 已完整读取，实际验证文档使用的公开 helper imports，并对拟新增文档执行单文件原生敏感扫描 native0/零命中；此检查不代签最终全仓扫描。

命令与当前实现的 Case 字段、prepare/execute、model/IPAM/image/source 校验、migration/checkpointer/grant/seed、API/Web 启动参数及精确 project 保卷清理一致。原 case/凭据不可重用，未授权服务/外发/生产边界和固定 UTC 看护责任明确。引用当前来源和可信同源 binding，不预填未来 SHA、不盲拷回执。

自动 runner 已有实际运行证据；手动分步模式只经源码核对/语法检查，文档明确尚未端到端实跑，不称一键部署或常驻服务。没有新增业务代码、依赖或服务，本核收仅接受操作文档，不扩大运行权限。
