# M3 内部文案主应用接线 v1

本地实现，真实资料、模型/embedding调用、对外发布均未验收。

默认不注册文案路由。`COMMERCEOPS_M3_COPY_ENABLED`只接受`true`或`false`；开启需要原P3 Web配置，以及显式`COMMERCEOPS_M3_COPY_CONFIG_FILE`与`COMMERCEOPS_M3_COPY_CONFIG_SHA256`。配置加载器验证固定文件权限、完整摘要和每个预注册查询的语义摘要，关闭时不读取文件。真实模型与发布开关仍禁止开启。

主应用使用原Web session边界，按显式配置构造CopyStore并注册已冻结五个文案操作。文案与日报开关独立；独立严格OpenAPI保存在app.state.copy_openapi，旧P3 OpenAPI不增加这些路径或类型。查询配置限定组织、店铺和query_ref，调用方不能提交任意资料或检索配置。

新部署由实际数据库owner先完成迁移、原grant-runtime，再显式执行`python -m commerceops.entrypoints.database grant-knowledge-copy-runtime`。该动作仅转交原有知识/文案窄权限helper；不自动启用API、不授予新角色或广泛表写入。原grant-runtime不隐式开启文案写权限。

Root本轮组合验证81个离线用例通过（6.12秒），包含日报/文案四种开关组合对旧OpenAPI的字节级结构比较、默认关闭和原认证错误封装；五个相关文件mypy通过。认证替身用例仅核验主应用封装，不证明真实PG身份、owner权限或完整浏览器流程。真实PG组件29项结果另按其实际source记录，不由本接线转签。
