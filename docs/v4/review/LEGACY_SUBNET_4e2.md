# V4 legacy subnet wrapper 4e26752 专项审查

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_PREPARED_LEGACY_SUBNET_WRAPPER，0 P1 / 0 P2。** 本结论仅覆盖两个旧 launcher 的显式子网适配准备，不签旧 Web/N01 实际运行、V4 pilot 或 Full 验收。

candidate `4e267522c353074d583a29c89e9022d4f8d93f33` / tree `63462612d5045a3359a60b45c670ee1aaa9ce023`，parent `383e709467f0ab385874d9f03de9086f5e2c50bb`。提交只新增 `tests/e2e/v4/legacy_subnet.py` 与 `test_legacy_subnet.py`。本次只读精确提交及其复用的 pg_diagnostic/m3_pgvector/两个旧 launcher；未读作者 WIP，未修改其代码。

## 固定入口与配置绑定

入口只有 `tests.e2e.web.run_live_batches` 与 `tests.e2e.web.run_c09_n01`。Web 固定 read/write/items 全部三段，N01 固定单段；均强制原 M3 开关为 true，原 deadline、owner 和 private 路径透传。调用前要求明确完整 HEAD SHA 一致、tracked 内容相对 HEAD 无差异，以及新绝对规范 private 路径。临时替换各模块的 compose_flags，finally 恢复；没有新增通用模块加载入口或替代业务流程。

每段要求恰好一次、恰好原 private/stage/compose-port.json（N01 为 private/compose-port.json）的挂接。原函数返回的 Compose 文件列表与顺序保持；该 overlay 本来就在最后。wrapper 只对原 postgres 单个 127.0.0.1 发布端口的精确 JSON 结构添加 default IPAM。已有 network、额外 service 或其它端口形状拒绝，不创建替代端口文件，不复制旧私配，不改旧 Web 业务、请求、Gates 或清理代码。

子网复用 owned_subnet，要求显式 canonical RFC1918 IPv4 /24；不分配或 normalize。Web 三段在同次调用中必须各不相同。N01 是独立调用，第四段与 Web 三段的跨调用不同值仍须由 ROOT 的实际窗口登记保证；wrapper 不宣称持有全局地址池锁或跨调用历史登记。

## 文件边界与只读预检

private 目录要求当前 UID、0700、真实目录及规范路径。directory fd 使用 O_DIRECTORY/O_NOFOLLOW 并核 dev/inode；overlay 相对该 fd 打开，要求普通文件、当前 UID、0600、单硬链接、至多 4096 字节。先验证原结构，再独占创建 O_EXCL/O_NOFOLLOW 的 0600 safe receipt，记录 stage/subnet/owner/path 与原始及更新字节 SHA256；然后写原 overlay fd、truncate、fsync 文件与目录。失败不静默覆盖旧 receipt，重复挂接拒绝。receipt 是准备尝试证据；后续部分写入失败不能凭 receipt 存在认定配置已成功使用。

写入前复用原 check_subnet_available，执行全量 Docker network ls/inspect 的有界只读快照：规范 ID、数量上限、行数、JSON/子网解析、所有实际 IPv4 范围 overlap 检查和末次相同 ID 集合检查；非零/超时/格式错误/变化传播失败。复用 helper 对 IPAM.Config=null/空列表仍按其原语义处理，本次没有将其改写为 a990 的 driver/name 精细验证器，也不宣称两者完全等价。没有 prune、网络删除、daemon 设置变更或冲突后自动另选子网。快照之后的并发地址分配仍可能导致 Docker 拒绝，应保留实际失败。

## 独立验证

精确 candidate git archive 临时快照，独立执行 test_legacy_subnet.py 与 test_pg_owned_subnet.py：**57 PASS / 0.13s / native0**。覆盖固定入口/参数透传及 finally 恢复、完整阶段集合、重复范围、私有文件/链接/权限、原端口与摘要、单次 receipt、冲突拒绝、源码身份及 dirty 拒绝；Docker/launcher 调用均为 doubles。

另在同一快照构造四份全新临时 0700/0600 overlay，调用精确 bind_overlay（库存检查用显式测试替身），再用实际 Docker Compose CLI 对原 compose.yml + compose.m3.yml + 原 overlay 执行 config --format json。四段均 native0，核实唯一 default 网络的 IPAM 精确为所给范围、postgres 只接 default、原 127.0.0.1:32123:5432 发布值完整保留。该项验证真实 Compose 合并语义，没有查询实际 daemon 网络、启动 PG/API/Web/browser 或创建 container/network/volume。临时快照与测试文件已清理。

旧 launcher 自身的不可变 deadline/reserve、prepared image/source binding、配置文件标签校验及业务结果检查继续由旧代码执行；本增量没有放宽它们。此次实际服务/旧 Web/N01/清理结果均 NOT_RUN，不重签历史业务，也不关闭独立的 SUBNET-01。后续真实窗口仍由 ROOT 绑定最终合批 source、四个明确范围、资源所有权和 UTC 后按实际回执核定。
