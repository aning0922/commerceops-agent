# V41 CSV控制前缀P2关闭复审

日期：2026-11-04（台北）。source `8707c0ca47d688bad9618574e3cf7088c7413574`，tree `7dd94f0a305d92a491294487851227fad6d4d833`。读取三文件增量，结论ACCEPT_PURE_EXPORT_FIX，P2-E01在本纯服务源码关闭。

_safe_csv对全部文本先拒任何非isprintable字符，再将可打印文本中空白之后的公式前缀变为单引号字面值；canonical_tags同样拒不可打印字符，保护独立标签输入而不依赖导入parser。CSV writer仍负责引号/分隔符转义。拒绝策略是明确失败，不偷偷删控制字符后执行原公式。

精确git archive的test_queries.py独立执行：21 passed、0.23秒、native0。包含原5项查询/导出及10种控制/格式前缀双路径拒绝（导出与标签DTO）、5种可打印公式字面化、中文/emoji/引号/分隔符round-trip。隔离目录offline marker一项warning保留，不冒称作者95pure或真实Excel执行。

SQL标签字符规范仍需按SQL_ACTIONS_15ec5f4的S03跨层对齐；本次纯导出修复不关闭SQL授权S01/S02，也不证明浏览器Blob下载、HTTP/current context或生产安全。无PG/API/browser/network。
