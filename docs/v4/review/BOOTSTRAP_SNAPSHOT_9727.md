# bootstrap_restart 快照复用 9727 窄审

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_PREPARED_BOOTSTRAP_COOKIE_SNAPSHOT_REUSE，0 P1 / 0 P2。** candidate `9727cf15aba3d2b2fa27bba6b82682c403903187` / tree `496336e508aa86805ef2729503981cedee9cc005`，parent `03c49da1101f299848e6b7881cc52eec28ba3080`。仅owned_negatives及必要cookie纯测试，未审整个API或启动实际场景。

原bootstrap_restart中两次保存和一次恢复改用已审snapshot_cookies；比较改为遍历各自.jar里的Cookie名称和值，保持原判据，避免迭代httpx.Cookies只得到名称。删除不再使用的copy/httpx imports，没有新helper或新协议分支。独立核依赖http_probe完整blob仍为 `d9579c346d2d035f7df06ccfef1eb003cc74260f`，与已审1c152逐字节相同。

独立将三处snapshot表达式及两处.jar遍历归一化回原形式后，owned_negatives全部函数AST与parent相同。前三访客创建、第四bootstrap、首次429/CAPACITY_LIMIT/REJECTED、原PG owner未消费绑定、显式重入bootstrap、新cookie值不同、新key再次拒绝、旧PG绑定不变/新owner ID不同、恢复原cookie后原key最小UNKNOWN回执、容量仍3/3/3及前三current读取顺序与断言均保持。没有UNKNOWN自动重发、改用404推导回滚或放宽容量/权限；其他negative分支及finally清理不变。

新增纯测试专门使用同名、同domain/path的新旧owner cookie：httpx容器名称迭代相同，jar值不同；恢复旧快照后活动cookie再次替换，不改变两个保存快照。旧cookie测试原文全部保留。精确提交临时快照+既有Node/锁定依赖，独立执行cookie_snapshot与http_criteria：**23 PASS / 0.49s / native0**。无HTTP传输、PG、浏览器或scanner，临时目录清理。

ROOT已报告原08在owned_driver.main边界捕获TypeError/RLock，内部具体抛错行仍未记录；本次不补写旧内部trace，也不把23pure当作原08或新bootstrap_restart实际通过。此处接受最小工具复用，后续新HTTPcase须绑定最终source、资源窗口及实际回执；后台Full R2仍保留原c6受测source，不因探针/扫描/文档合批而改签新SHA。
